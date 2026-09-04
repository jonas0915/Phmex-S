#!/usr/bin/env python3
"""5m_mean_revert edge search — Phase C SIGNAL TABLE (one artifact, all families read it).

Regenerates every bb_mean_reversion signal bar-by-bar over the frozen window from the
Phase A OHLCV cache, attaches the entry context each hypothesis family needs, and
replays every signal through the LIVE exit cell plus the full H1 geometry grid on the
same 1m path. Downstream (`mr_edge_screen.py`) reads ONLY this JSON — no family gets
to touch price data again.

Reuses (lessons.md META-RULE #4 — no reinvention):
  * mean_revert_replay._build_path / _net / WARMUP / fee constants   (validated rig)
  * st2_lab.exit_replay._simulate(variant=True)  (SL/TP + tiered trail + breakeven)
  * indicators.add_all_indicators + strategies.bb_mean_reversion_strategy (exact slot signal)
  * st2_lab.dataset._normalize                    (flow_capture row parser)

Live fidelity added on top of the old regen:
  * long RSI(7) floor 22.0 (bot.py:3187-3206, Config.MEAN_REVERT_LONG_RSI_MIN) — blocks
    longs with rsi_fast < 22; the 6/30 replay omitted this.
  * adx1h built the live way (bot.py:901-916 _fetch_htf_data): 1h bars INCLUDING the
    forming bar at signal time, trailing 100 bars, add_all_indicators, last adx.
  * live time exit (risk_manager.py:260-277): 240 cycles ~ 4h, extended x1.5 (6h) when
    unrealized ROI >= 5% at the 4h mark. Cell "live" models exactly that; the grid twin
    tp1.6_sl1.2_t4h is the same geometry WITHOUT the extension.

HONESTY CAVEATS (printed at runtime; verbatim from mean_revert_replay's header where marked):
  * fill-all is OPTIMISTIC — real maker fill rate is ~27%. Maker-fill-all is an
    UPPER BOUND on the signal's edge, not a live expectation.       [verbatim]
  * no adverse selection modeled -> every dollar is an upper bound; only RELATIVE
    comparisons between cells/cohorts are decision metrics.
  * funding parity gap: live reads the PREDICTED next rate, this table joins the last
    SETTLED rate <= signal ts.
  * flow join is the nearest flow_capture row <= ts within 120 s; the live tape/OB gates
    are NOT re-applied (scanner_active tells you whether the scanner even had the symbol).
  * time exits are charged the MAKER exit fee (rig convention, `_net`); live closes a
    time exit with a market order (taker) -> +$0.075 optimistic per time exit at $150.
  * per-symbol cooldown is NOT applied to the rows (fidelity gate needs every candidate);
    `cooldown_ok` reproduces the rig's one-signal-per-4h-per-symbol set. Screens should
    default to cooldown_ok == true.
  * global occupancy (max_positions) not modeled -> affects count, not per-trade EV.
  * Per edge-hunt-exhaustion: this table can only REJECT; a survivor goes to a real-money
    forward verdict line, never straight to deploy.

Read-only vs the bot: never imports bot.py/exchange.py/config.py/risk_manager.py, never
touches trading_state*.json/.env. Run heavy jobs under `nice -n 19`.

Run from repo root:
    nice -n 19 python3 scripts/slot_lab/mr_edge_signal_table.py --limit-symbols 2 --dry-run
    nice -n 19 python3 scripts/slot_lab/mr_edge_signal_table.py \
        --cache-dir reports/cache/mr_edge_20260601_20260903 \
        --universe reports/mr_edge_2026/universe.json \
        --start 2026-06-01 --end 2026-09-03 \
        --out reports/mr_edge_2026/signals.json
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import pickle
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts", "slot_lab"))

import backtest  # noqa: E402  (trail engine globals used by exit_replay._simulate)
import mean_revert_replay as MR  # noqa: E402  (validated _build_path/_net/WARMUP/fees)
from st2_lab.exit_replay import _simulate  # noqa: E402
from st2_lab.dataset import _normalize  # noqa: E402
from indicators import add_all_indicators  # noqa: E402
from strategies import bb_mean_reversion_strategy, Signal  # noqa: E402

# Live trail arm (env TRAIL_ARM_ROI=8.0 since 2026-07-05); backtest.py default is 5.0.
# Same override as scripts/slot_lab/gate_block_counterfactual.py:86.
backtest.TRAIL_ARM_ROI = 8.0

# --- live economics for the $15 era (2026-08-18 cut; CLAUDE.md Current Parameters) ---
LEVERAGE = MR.LEVERAGE            # 10
MARGIN = 15.0                     # overrides MR.MARGIN (10.0)
NOTIONAL = MARGIN * LEVERAGE      # $150
MAKER_FEE = MR.MAKER_FEE          # 0.01 %/side
TAKER_FEE = MR.TAKER_FEE          # 0.06 %/side
TRAIL_ARM_ROI = backtest.TRAIL_ARM_ROI
WARMUP = MR.WARMUP                # 200 bars before ema_200 is meaningful
LONG_RSI_MIN = 22.0               # bot.py:3193 Config.MEAN_REVERT_LONG_RSI_MIN
COOLDOWN_S = 14400                # rig: one signal per symbol per live hold window
MIN_STRENGTH = 0.80               # slot gate (bot.py:3132)

# --- exit cells ---
LIVE_SL, LIVE_TP, LIVE_HOLD_S = 1.2, 1.6, 4 * 3600
LIVE_EXT_ROI = 5.0                # risk_manager.py:271 extend when roi >= 5%
LIVE_EXT_FACTOR = 1.5             # risk_manager.py:272 hard_limit * 1.5
TP_GRID = [1.0, 1.6, 2.0, 2.4, 3.0]
SL_GRID = [0.8, 1.2, 1.6, 2.0]
T_GRID_H = [2, 4, 6, 8]

# --- joins ---
FLOW_MAX_DT_S = 120               # nearest flow row <= ts must be this fresh
SCANNER_TOL_S = 600               # any flow row within +/-10 min = scanner had the symbol
SNAP_BAR_TOL_S = 300              # fidelity: same 5m bar +/- 1 bar
FIDELITY_MIN_PCT = 90.0
TOLERANCES = {"rsi_fast": 10.0, "htf_adx": 5.0, "vol_ratio": 0.5}  # forming-bar drift

# Sessions by PT hour (America/Los_Angeles, DST-aware):
#   europe = 0-5   (12 AM-5:59 AM PT  ~ 8 AM-2 PM London: EU cash hours before NY)
#   us     = 6-13  (6 AM-1:59 PM PT   ~ NY cash session incl. the London/NY overlap)
#   asia   = 14-23 (2 PM-11:59 PM PT  ~ 6 AM-4 PM Tokyo/HK the next calendar day)
SESSIONS = {"europe": (0, 6), "us": (6, 14), "asia": (14, 24)}
LA = ZoneInfo("America/Los_Angeles")

FILL_ALL_CAVEAT = ("fill-all is OPTIMISTIC — real maker fill rate is ~27%. Maker-fill-all is an\n"
                   "    UPPER BOUND on the signal's edge, not a live expectation.")
CAVEATS = [
    FILL_ALL_CAVEAT,
    "no adverse selection modeled -> every dollar is an upper bound; only RELATIVE "
    "comparisons between cells/cohorts are decision metrics",
    "funding parity gap: live uses the PREDICTED next rate, replay joins the last SETTLED "
    "rate <= signal ts",
    "flow join = nearest flow_capture row <= ts within 120 s; live OB/tape gates NOT "
    "re-applied; scanner_active = any flow row within +/-600 s",
    "time exits charged the MAKER exit fee (rig `_net` convention); live time exit is a "
    "market close (taker): +$0.075 optimistic per time exit at $150 notional",
    "per-symbol cooldown not applied to rows; cooldown_ok reproduces the rig's "
    "one-signal-per-4h-per-symbol set (screens default to cooldown_ok == true)",
    "signals regenerated on CLOSED 5m bars; live evaluates the forming bar every 60 s "
    "(fidelity gate tolerates +/-1 bar and reports feature drift)",
    "live 4h extension modeled with the adverse 1m extreme at the 4h mark (pessimistic)",
    "global max_positions occupancy not modeled -> affects count, not per-trade EV",
    "replay can only REJECT; survivors go to a real-money forward verdict line",
]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def symkey(symbol: str) -> str:
    """Cache file key, same convention as mean_revert_replay._cached."""
    return symbol.replace("/", "_").replace(":", "_")


def cache_path(cache_dir: str, symbol: str, tf: str) -> str:
    return os.path.join(cache_dir, f"{symkey(symbol)}_{tf}.pkl")


def hour_pt(ts: int) -> int:
    return datetime.fromtimestamp(int(ts), tz=LA).hour


def session_for_hour(h: int) -> str:
    for name, (lo, hi) in SESSIONS.items():
        if lo <= h < hi:
            return name
    raise ValueError(f"hour out of range: {h}")


def _cell_key(tp: float, sl: float, hours: int) -> str:
    return f"tp{tp}_sl{sl}_t{hours}h"


def cell_keys() -> list[str]:
    keys = ["live"]
    for tp in TP_GRID:
        for sl in SL_GRID:
            for h in T_GRID_H:
                keys.append(_cell_key(tp, sl, h))
    return keys


def cell_params(key: str) -> dict:
    if key == "live":
        return {"tp_pct": LIVE_TP, "sl_pct": LIVE_SL, "hold_secs": LIVE_HOLD_S}
    tp_s, sl_s, t_s = key.split("_")
    return {"tp_pct": float(tp_s[2:]), "sl_pct": float(sl_s[2:]),
            "hold_secs": int(t_s[1:-1]) * 3600}


def _epoch_index(df: pd.DataFrame) -> np.ndarray:
    return df.index.view("int64") // 1_000_000_000


# ---------------------------------------------------------------------------
# signal regeneration (rig loop shape + live RSI floor, no cooldown suppression)
# ---------------------------------------------------------------------------

def regen_signals(df5_raw: pd.DataFrame, symbol: str, start_ts: int | None = None,
                  end_ts: int | None = None, blocked: dict | None = None) -> list[dict]:
    """Walk closed 5m bars; emit every bb_mean_reversion signal (strength >= 0.80) whose
    bar-close ts is inside [start_ts, end_ts], after the live long RSI(7) floor.
    Entry features are read off the signal bar. `blocked` (optional Counter-like dict)
    receives 'mr_rsi_floor' counts. Rows carry cooldown_ok (rig 4h/symbol set)."""
    df5 = add_all_indicators(df5_raw)
    n = len(df5)
    epoch = _epoch_index(df5)
    vol = df5["volume"].to_numpy(dtype=float)
    sigs: list[dict] = []
    cooldown_until = 0
    for i in range(WARMUP, n):
        bar_open_ts = int(epoch[i])
        ts = bar_open_ts + 300                       # ccxt ts = bar open; +5m = decision
        if start_ts is not None and ts < start_ts:
            continue
        if end_ts is not None and ts > end_ts:
            break
        window = df5.iloc[i - 21:i + 1]              # strategy needs last, prev, last-20 vol
        sig = bb_mean_reversion_strategy(window, orderbook=None)
        if sig.signal == Signal.HOLD or sig.strength < MIN_STRENGTH:
            continue
        side = "long" if sig.signal == Signal.BUY else "short"
        last = df5.iloc[i]
        rsi_fast = float(last["rsi_fast"])
        if side == "long" and rsi_fast < LONG_RSI_MIN:  # bot.py:3193 live floor
            if blocked is not None:
                blocked["mr_rsi_floor"] = blocked.get("mr_rsi_floor", 0) + 1
            continue
        vol_avg = float(vol[i - 19:i + 1].mean())
        bb_mid = float(last["bb_mid"])
        bb_w = ((float(last["bb_upper"]) - float(last["bb_lower"])) / bb_mid) if bb_mid else 0.0
        h = hour_pt(ts)
        sigs.append({
            "symbol": symbol, "ts": ts, "bar_open_ts": bar_open_ts, "side": side,
            "entry_px": float(last["close"]), "strength": float(sig.strength),
            "rsi": float(last["rsi"]), "rsi_fast": rsi_fast,
            "vol_ratio": (float(last["volume"]) / vol_avg) if vol_avg else 0.0,
            "bb_width_pct": bb_w * 100.0, "adx5m": float(last["adx"]),
            "hour_pt": h, "session": session_for_hour(h),
            "cooldown_ok": ts >= cooldown_until,
        })
        if ts >= cooldown_until:
            cooldown_until = ts + COOLDOWN_S
    return sigs


# ---------------------------------------------------------------------------
# 1h ADX the live way (bot.py:901-916): 100 x 1h bars incl. the forming one
# ---------------------------------------------------------------------------

_H_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def adx1h_live(df5_raw: pd.DataFrame, bar_open_ts: int) -> float | None:
    """1h ADX as the live bot sees it at the signal bar: exchange.get_ohlcv('1h',
    limit=100) returns 99 closed hours + the forming hour, then add_all_indicators()
    and the last row's adx. Here the forming hour aggregates the 5m bars up to and
    including the signal bar. None when < 30 hourly bars exist (live returns None)."""
    cut = pd.Timestamp(int(bar_open_ts), unit="s", tz="UTC")
    lo = cut - pd.Timedelta(hours=101)
    sub = df5_raw.loc[lo:cut]
    if sub.empty:
        return None
    h = sub.resample("1h", label="left", closed="left").agg(_H_AGG).dropna(subset=["open"])
    h = h.tail(100)
    if len(h) < 30:
        return None
    ind = add_all_indicators(h)
    if ind.empty:
        return None
    v = ind.iloc[-1].get("adx")
    return None if v is None or pd.isna(v) else float(v)


# ---------------------------------------------------------------------------
# flow_capture join: streamed once, per-symbol numpy columns, bisect lookups
# ---------------------------------------------------------------------------

_FLOW_COLS = ("buy_ratio", "imbalance", "trade_count", "cvd_slope", "div",
              "large_trade_bias", "spread_pct")


class FlowIndex:
    """Per-symbol sorted ts arrays + parallel feature columns (no pandas, no dicts
    per row — 846k rows fit in ~60 MB)."""

    def __init__(self):
        self._ts: dict[str, np.ndarray] = {}
        self._cols: dict[str, dict[str, np.ndarray]] = {}
        self.n_rows = 0

    @classmethod
    def from_file(cls, path: str, symbols: set | None = None,
                  start_ts: int | None = None, end_ts: int | None = None) -> "FlowIndex":
        acc: dict[str, dict[str, list]] = {}
        idx = cls()
        if not os.path.exists(path):
            return idx
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec = _normalize(raw)
                if rec is None:
                    continue
                sym = rec["symbol"]
                if symbols is not None and sym not in symbols:
                    continue
                ts = rec["ts"]
                if (start_ts is not None and ts < start_ts) or (end_ts is not None and ts > end_ts):
                    continue
                a = acc.setdefault(sym, {"ts": [], **{c: [] for c in _FLOW_COLS}})
                a["ts"].append(ts)
                a["buy_ratio"].append(rec["buy_ratio"])
                a["imbalance"].append(rec["imbalance"])
                a["trade_count"].append(rec["trade_count"])
                a["cvd_slope"].append(rec["cvd_slope"])
                a["div"].append(1 if rec["divergence_bullish"] else (-1 if rec["divergence_bearish"] else 0))
                a["large_trade_bias"].append(rec["large_trade_bias"])
                a["spread_pct"].append(rec["spread_pct"])
        for sym, a in acc.items():
            ts = np.asarray(a["ts"], dtype=np.int64)
            order = np.argsort(ts, kind="stable")
            idx._ts[sym] = ts[order]
            idx._cols[sym] = {
                "buy_ratio": np.asarray(a["buy_ratio"], dtype=float)[order],
                "imbalance": np.asarray(a["imbalance"], dtype=float)[order],
                "trade_count": np.asarray(a["trade_count"], dtype=np.int64)[order],
                "cvd_slope": np.asarray(a["cvd_slope"], dtype=float)[order],
                "div": np.asarray(a["div"], dtype=np.int8)[order],
                "large_trade_bias": np.asarray(a["large_trade_bias"], dtype=float)[order],
                "spread_pct": np.asarray(a["spread_pct"], dtype=float)[order],
            }
            idx.n_rows += len(ts)
        return idx

    def symbols(self) -> list[str]:
        return sorted(self._ts)

    def nearest(self, symbol: str, ts: int, max_dt: int = FLOW_MAX_DT_S) -> dict | None:
        arr = self._ts.get(symbol)
        if arr is None or len(arr) == 0:
            return None
        i = int(np.searchsorted(arr, ts, side="right")) - 1
        if i < 0:
            return None
        dt = int(ts - arr[i])
        if dt > max_dt:
            return None
        c = self._cols[symbol]
        d = int(c["div"][i])
        return {
            "buy_ratio": float(c["buy_ratio"][i]),
            "imbalance": float(c["imbalance"][i]),
            "trade_count": int(c["trade_count"][i]),
            "cvd_slope": float(c["cvd_slope"][i]),
            "divergence": "bullish" if d == 1 else ("bearish" if d == -1 else None),
            "large_trade_bias": float(c["large_trade_bias"][i]),
            "spread_pct": float(c["spread_pct"][i]),
            "dt_s": dt,
        }

    def active(self, symbol: str, ts: int, tol: int = SCANNER_TOL_S) -> bool:
        arr = self._ts.get(symbol)
        if arr is None or len(arr) == 0:
            return False
        lo = int(np.searchsorted(arr, ts - tol, side="left"))
        hi = int(np.searchsorted(arr, ts + tol, side="right"))
        return hi > lo


# ---------------------------------------------------------------------------
# funding join: last SETTLED rate <= ts (cache: funding_{SYMKEY}.json = [{ts(ms), rate}])
# ---------------------------------------------------------------------------

def load_funding(cache_dir: str, symbol: str):
    path = os.path.join(cache_dir, f"funding_{symkey(symbol)}.json")
    if not os.path.exists(path):
        return None
    try:
        raw = json.load(open(path))
    except (json.JSONDecodeError, OSError):
        return None
    rows = [(int(r["ts"]) // 1000, float(r["rate"])) for r in raw
            if r.get("ts") is not None and r.get("rate") is not None]
    if not rows:
        return None
    rows.sort()
    ts = np.asarray([r[0] for r in rows], dtype=np.int64)
    rates = np.asarray([r[1] for r in rows], dtype=float)
    return {"ts": ts, "rate": rates}


def funding_at(fund, ts: int):
    if fund is None:
        return None, None
    i = int(np.searchsorted(fund["ts"], ts, side="right")) - 1
    if i < 0:
        return None, None
    return float(fund["rate"][i]), int(fund["ts"][i])


# ---------------------------------------------------------------------------
# outcomes: LIVE cell (+ extension rule) and the H1 grid on the same 1m path
# ---------------------------------------------------------------------------

def _roi_pct(side: str, entry_px: float, px: float) -> float:
    move = (px - entry_px) / entry_px if side == "long" else (entry_px - px) / entry_px
    return move * 100.0 * LEVERAGE


MAX_HOLD_S = max(max(T_GRID_H) * 3600, int(LIVE_HOLD_S * LIVE_EXT_FACTOR))


class _PathCache:
    """One rig `_build_path` call at the LONGEST hold per signal; shorter holds are a
    prefix (the path is ts-ordered and capped at entry+hold), so slicing by ts is
    identical to rebuilding — 82 cells cost one 1m scan instead of 82."""

    def __init__(self, df1m, entry_ts, side):
        self.full = MR._build_path(df1m, entry_ts, MAX_HOLD_S, side)
        self._ts = [p["ts"] for p in self.full]
        self.entry_ts = entry_ts

    def upto(self, hold_secs):
        return self.full[:bisect.bisect_right(self._ts, self.entry_ts + hold_secs)]


def _run_cell(symbol, side, entry_px, entry_ts, df1m, params, paths: _PathCache | None = None):
    """One _simulate pass; returns (exit_px, raw_reason, held_s) or None (no path)."""
    if paths is None:
        path = MR._build_path(df1m, entry_ts, params["hold_secs"], side)
    else:
        path = paths.upto(params["hold_secs"])
    if not path:
        return None
    return _simulate(symbol, side, entry_px, entry_ts, path, params, variant=True)


def _finish(side, entry_px, res, reason_map):
    exit_px, raw, _held = res
    net = MR._net(entry_px, exit_px, side, raw, NOTIONAL, MAKER_FEE)
    return float(net), reason_map.get(raw, raw)


_REASON_MAP = {"st2_hold": "time_exit"}
_REASON_MAP_EXT = {"st2_hold": "time_exit_ext"}


def simulate_cell(side, entry_px, entry_ts, df1m, params, symbol="X", paths=None):
    res = _run_cell(symbol, side, entry_px, entry_ts, df1m, params, paths)
    if res is None:
        return None, "no_path"
    return _finish(side, entry_px, res, _REASON_MAP)


def simulate_live(side, entry_px, entry_ts, df1m, symbol="X", paths=None):
    """Live cell: 4h hard exit, extended to 6h when unrealized ROI >= 5% at the 4h
    mark (risk_manager.py:260-277). The 6h pass replays the identical path prefix."""
    base = cell_params("live")
    res = _run_cell(symbol, side, entry_px, entry_ts, df1m, base, paths)
    if res is None:
        return None, "no_path"
    exit_px, raw, _ = res
    if raw == "st2_hold" and _roi_pct(side, entry_px, exit_px) >= LIVE_EXT_ROI:
        ext = dict(base, hold_secs=int(base["hold_secs"] * LIVE_EXT_FACTOR))
        res2 = _run_cell(symbol, side, entry_px, entry_ts, df1m, ext, paths)
        if res2 is not None:
            return _finish(side, entry_px, res2, _REASON_MAP_EXT)
    return _finish(side, entry_px, res, _REASON_MAP)


def outcomes(side, entry_px, entry_ts, df1m, symbol="X"):
    paths = _PathCache(df1m, entry_ts, side)
    net_by_cell, exit_by_cell = {}, {}
    for key in cell_keys():
        if key == "live":
            net, reason = simulate_live(side, entry_px, entry_ts, df1m, symbol, paths)
        else:
            net, reason = simulate_cell(side, entry_px, entry_ts, df1m, cell_params(key), symbol, paths)
        net_by_cell[key] = net
        exit_by_cell[key] = reason
    return net_by_cell, exit_by_cell


# ---------------------------------------------------------------------------
# per-symbol pipeline
# ---------------------------------------------------------------------------

def build_symbol_rows(symbol, df5_raw, df1m, flow: FlowIndex | None = None, funding=None,
                      start_ts=None, end_ts=None, blocked=None) -> list[dict]:
    rows = []
    for s in regen_signals(df5_raw, symbol, start_ts, end_ts, blocked=blocked):
        s["adx1h"] = adx1h_live(df5_raw, s["bar_open_ts"])
        s["flow"] = flow.nearest(symbol, s["ts"]) if flow is not None else None
        s["scanner_active"] = flow.active(symbol, s["ts"]) if flow is not None else False
        s["funding_rate"], s["funding_ts"] = funding_at(funding, s["ts"])
        s["net_by_cell"], s["exit_by_cell"] = outcomes(s["side"], s["entry_px"], s["ts"],
                                                       df1m, symbol)
        rows.append(s)
    return rows


# ---------------------------------------------------------------------------
# fidelity gate vs logs/entry_snapshots.jsonl (mirrors mr_variant_grid's V0 gate)
# ---------------------------------------------------------------------------

def load_snapshots(path: str, start_ts: int | None = None, end_ts: int | None = None,
                   slot: str = "5m_mean_revert") -> list[dict]:
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("slot") != slot:
                continue
            ts = r.get("ts")
            if ts is None:
                continue
            ts = int(ts)
            if (start_ts is not None and ts < start_ts) or (end_ts is not None and ts > end_ts):
                continue
            out.append(r)
    out.sort(key=lambda r: r["ts"])
    return out


def _tol_stats(diffs: list[float], tol: float) -> dict:
    if not diffs:
        return {"n": 0, "median_abs_diff": None, "max_abs_diff": None, "within_tol": None, "tol": tol}
    a = np.abs(np.asarray(diffs, dtype=float))
    return {"n": int(len(a)), "median_abs_diff": float(np.median(a)),
            "max_abs_diff": float(a.max()), "within_tol": float((a <= tol).mean()), "tol": tol}


def bar_reasons(df5_raw: pd.DataFrame, ts: int, offsets=(-300, 0, 300)) -> dict:
    """Diagnostics for a fidelity miss: what the CLOSED-bar strategy said at the
    snapshot's 5m bar and its neighbours (reason, rsi_fast, vol_ratio, close vs bands).
    Keys are the bar offsets in seconds as strings."""
    ind = add_all_indicators(df5_raw)
    epoch = _epoch_index(ind)
    bar_open = ts - ts % 300
    out = {}
    for off in offsets:
        pos = int(np.searchsorted(epoch, bar_open + off))
        if pos >= len(ind) or epoch[pos] != bar_open + off or pos < 21:
            out[str(off)] = None
            continue
        sig = bb_mean_reversion_strategy(ind.iloc[pos - 21:pos + 1], orderbook=None)
        r = ind.iloc[pos]
        vol_avg = float(ind["volume"].iloc[pos - 19:pos + 1].mean())
        out[str(off)] = {
            "signal": sig.signal.value, "reason": sig.reason, "rsi_fast": float(r["rsi_fast"]),
            "vol_ratio": (float(r["volume"]) / vol_avg) if vol_avg else 0.0,
            "close": float(r["close"]), "bb_upper": float(r["bb_upper"]),
            "bb_lower": float(r["bb_lower"]), "adx": float(r["adx"]),
        }
    return out


def fidelity_gate(snapshots: list[dict], signals: list[dict], symbols_checked: set,
                  min_pct: float = FIDELITY_MIN_PCT, diagnose=None) -> dict:
    """Every real MR entry (same symbol, same side, same 5m bar +/-1) must exist in the
    regenerated set. Snapshots for symbols not processed are reported, not counted.
    `diagnose(snap) -> dict` (optional) is attached to each miss as "diagnosis"."""
    by_key: dict[tuple, list[dict]] = {}
    for s in signals:
        by_key.setdefault((s["symbol"], s["side"]), []).append(s)
    for v in by_key.values():
        v.sort(key=lambda s: s["bar_open_ts"])
    opens = {k: [s["bar_open_ts"] for s in v] for k, v in by_key.items()}

    n_checked = n_matched = n_unchecked = 0
    misses, diffs = [], {"rsi_fast": [], "htf_adx": [], "vol_ratio": []}
    for snap in snapshots:
        sym, side, ts = snap.get("symbol"), snap.get("direction"), int(snap["ts"])
        if sym not in symbols_checked:
            n_unchecked += 1
            continue
        n_checked += 1
        bar_open = ts - ts % 300
        cands = by_key.get((sym, side), [])
        arr = opens.get((sym, side), [])
        i = bisect.bisect_left(arr, bar_open - SNAP_BAR_TOL_S)
        best = None
        while i < len(arr) and arr[i] <= bar_open + SNAP_BAR_TOL_S:
            c = cands[i]
            if best is None or abs(c["bar_open_ts"] - bar_open) < abs(best["bar_open_ts"] - bar_open):
                best = c
            i += 1
        if best is None:
            miss = {"symbol": sym, "direction": side, "ts": ts,
                    "ts_utc": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                    "price": snap.get("price"), "snap_rsi_fast": snap.get("rsi_fast"),
                    "snap_vol_ratio": (snap.get("regime") or {}).get("vol_ratio")}
            if diagnose is not None:
                try:
                    miss["diagnosis"] = diagnose(snap)
                except Exception as e:  # diagnostics must never break the gate
                    miss["diagnosis"] = {"error": repr(e)}
            misses.append(miss)
            continue
        n_matched += 1
        if snap.get("rsi_fast") is not None:
            diffs["rsi_fast"].append(float(snap["rsi_fast"]) - best["rsi_fast"])
        if snap.get("htf_adx") is not None and best.get("adx1h") is not None:
            diffs["htf_adx"].append(float(snap["htf_adx"]) - best["adx1h"])
        vr = (snap.get("regime") or {}).get("vol_ratio")
        if vr is not None:
            diffs["vol_ratio"].append(float(vr) - best["vol_ratio"])
    return _fidelity_report(len(snapshots), n_checked, n_matched, n_unchecked, misses,
                            diffs, min_pct)


def _fidelity_report(n_snapshots, n_checked, n_matched, n_unchecked, misses, diffs, min_pct):
    pct = (100.0 * n_matched / n_checked) if n_checked else 0.0
    return {
        "n_snapshots": n_snapshots, "n_checked": n_checked, "n_matched": n_matched,
        "n_unchecked": n_unchecked, "pct": pct, "min_pct": min_pct,
        "passed": bool(n_checked > 0 and pct >= min_pct), "misses": misses,
        "tolerance": {k: _tol_stats(v, TOLERANCES[k]) for k, v in diffs.items()},
        "_diffs": diffs,
    }


def merge_fidelity(reports: list[dict], n_snapshots: int, n_unchecked: int,
                   min_pct: float = FIDELITY_MIN_PCT) -> dict:
    """Combine per-symbol gate reports (run while each symbol's frames are loaded, so
    misses can carry bar-level diagnostics) into the single gate verdict."""
    diffs = {"rsi_fast": [], "htf_adx": [], "vol_ratio": []}
    misses, n_checked, n_matched = [], 0, 0
    for r in reports:
        n_checked += r["n_checked"]
        n_matched += r["n_matched"]
        misses.extend(r["misses"])
        for k in diffs:
            diffs[k].extend(r.get("_diffs", {}).get(k, []))
    misses.sort(key=lambda m: m["ts"])
    rep = _fidelity_report(n_snapshots, n_checked, n_matched, n_unchecked, misses, diffs, min_pct)
    return rep


# ---------------------------------------------------------------------------
# meta / IO
# ---------------------------------------------------------------------------

def build_meta(start_ts, end_ts, universe, fidelity, counts) -> dict:
    iso = lambda t: datetime.fromtimestamp(int(t), tz=timezone.utc).isoformat()  # noqa: E731
    return {
        "window": {"start": iso(start_ts), "end": iso(end_ts),
                   "start_ts": int(start_ts), "end_ts": int(end_ts)},
        "universe": list(universe), "n_symbols": len(universe),
        "margin": MARGIN, "notional": NOTIONAL, "leverage": LEVERAGE,
        "maker_fee": MAKER_FEE, "taker_fee": TAKER_FEE, "trail_arm": TRAIL_ARM_ROI,
        "long_rsi_min": LONG_RSI_MIN, "min_strength": MIN_STRENGTH,
        "cooldown_s": COOLDOWN_S, "warmup_bars": WARMUP,
        "live_cell": {"sl_pct": LIVE_SL, "tp_pct": LIVE_TP, "hold_secs": LIVE_HOLD_S,
                      "ext_roi": LIVE_EXT_ROI, "ext_factor": LIVE_EXT_FACTOR},
        "cells": cell_keys(),
        "cell_params": {k: cell_params(k) for k in cell_keys()},
        "sessions_pt": {k: list(v) for k, v in SESSIONS.items()},
        "flow_max_dt_s": FLOW_MAX_DT_S, "scanner_tol_s": SCANNER_TOL_S,
        "fidelity": ({k: v for k, v in fidelity.items() if not k.startswith("_")}
                     if fidelity else None),
        "counts": dict(counts),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "prereg_sha": None,
        "caveats": list(CAVEATS),
    }


def load_universe(path: str, cache_dir: str) -> list[str]:
    """universe.json: a list of symbols, or {"symbols": [...]} (strings or {"symbol":..}).
    Fallback (warned): derive from {SYMKEY}_5m.pkl files in the cache dir."""
    if os.path.exists(path):
        raw = json.load(open(path))
        items = raw.get("symbols", raw.get("universe", [])) if isinstance(raw, dict) else raw
        syms = [it["symbol"] if isinstance(it, dict) else it for it in items]
        return [s for s in syms if isinstance(s, str)]
    syms = []
    for fn in sorted(os.listdir(cache_dir)) if os.path.isdir(cache_dir) else []:
        if fn.endswith("_5m.pkl"):
            key = fn[:-len("_5m.pkl")]
            parts = key.split("_")
            if len(parts) >= 3:
                syms.append(f"{'_'.join(parts[:-2])}/{parts[-2]}:{parts[-1]}")
    print(f"  WARNING: {path} missing — universe derived from cache dir ({len(syms)} symbols)")
    return syms


def _load_pkl(path: str):
    """Only loads pickles our own fetch script wrote (self-generated DataFrames)."""
    with open(path, "rb") as fh:
        return pickle.load(fh)


def _parse_ts(s: str) -> int:
    t = pd.Timestamp(s)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return int(t.timestamp())


def _to_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index, utc=True)
    elif df.index.tz is None:
        df = df.tz_localize("UTC")
    return df.sort_index()


def _print_caveats():
    print("  CAVEATS:")
    for c in CAVEATS:
        print(f"   * {c}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="5m_mean_revert edge search — Phase C signal table")
    ap.add_argument("--cache-dir", default=os.path.join(_BOT_DIR, "reports", "cache",
                                                        "mr_edge_20260601_20260903"))
    ap.add_argument("--universe", default=os.path.join(_BOT_DIR, "reports", "mr_edge_2026",
                                                       "universe.json"))
    ap.add_argument("--start", default="2026-06-01", help="window start (UTC, inclusive)")
    ap.add_argument("--end", default="2026-09-03", help="window end (UTC, inclusive)")
    ap.add_argument("--flow", default=os.path.join(_BOT_DIR, "logs", "flow_capture.jsonl"))
    ap.add_argument("--snapshots", default=os.path.join(_BOT_DIR, "logs", "entry_snapshots.jsonl"))
    ap.add_argument("--out", default=os.path.join(_BOT_DIR, "reports", "mr_edge_2026", "signals.json"))
    ap.add_argument("--limit-symbols", type=int, default=None, help="process only the first N")
    ap.add_argument("--skip-fidelity", action="store_true", help="TEST ONLY: never abort on the gate")
    ap.add_argument("--dry-run", action="store_true", help="run everything, write nothing")
    args = ap.parse_args(argv)

    start_ts, end_ts = _parse_ts(args.start), _parse_ts(args.end)
    universe = load_universe(args.universe, args.cache_dir)
    if args.limit_symbols:
        universe = universe[:args.limit_symbols]

    print("5m_mean_revert edge search — Phase C SIGNAL TABLE")
    print(f"  window {args.start} -> {args.end} UTC | symbols={len(universe)} | "
          f"cache={args.cache_dir}")
    print(f"  ${MARGIN:.0f} @ {LEVERAGE}x = ${NOTIONAL:.0f} notional | fees maker {MAKER_FEE}% / "
          f"taker {TAKER_FEE}% | trail arm {TRAIL_ARM_ROI}% | long RSI floor {LONG_RSI_MIN}")
    print(f"  cells: {len(cell_keys())} (live + {len(cell_keys()) - 1} grid)")
    _print_caveats()

    t0 = time.time()
    print(f"\n  streaming {args.flow} ...", flush=True)
    flow = FlowIndex.from_file(args.flow, symbols=set(universe),
                               start_ts=start_ts - SCANNER_TOL_S, end_ts=end_ts + SCANNER_TOL_S)
    print(f"  flow rows kept: {flow.n_rows} across {len(flow.symbols())} symbols "
          f"({time.time() - t0:.0f}s)")

    snaps = load_snapshots(args.snapshots, start_ts, end_ts)
    snaps_by_sym: dict[str, list] = {}
    for sn in snaps:
        snaps_by_sym.setdefault(sn.get("symbol"), []).append(sn)

    rows, counts, processed, fid_reports = [], Counter(), set(), []
    for sym in universe:
        p5, p1 = cache_path(args.cache_dir, sym, "5m"), cache_path(args.cache_dir, sym, "1m")
        if not (os.path.exists(p5) and os.path.exists(p1)):
            print(f"\n[{sym}] cache missing ({os.path.basename(p5)} / {os.path.basename(p1)}) — skipping")
            counts["symbols_missing_cache"] += 1
            continue
        df5, df1m = _to_utc_index(_load_pkl(p5)), _to_utc_index(_load_pkl(p1))
        if df5.empty or df1m.empty or len(df5) < WARMUP + 22:
            print(f"\n[{sym}] insufficient data — skipping")
            counts["symbols_insufficient"] += 1
            continue
        fund = load_funding(args.cache_dir, sym)
        blocked = {}
        ts0 = time.time()
        sym_rows = build_symbol_rows(sym, df5, df1m, flow=flow, funding=fund,
                                     start_ts=start_ts, end_ts=end_ts, blocked=blocked)
        processed.add(sym)
        rows.extend(sym_rows)
        if snaps_by_sym.get(sym):
            fid_reports.append(fidelity_gate(
                snaps_by_sym[sym], sym_rows, {sym},
                diagnose=lambda sn, _df5=df5: bar_reasons(_df5, int(sn["ts"]))))
        counts["signals"] += len(sym_rows)
        counts["cooldown_ok"] += sum(1 for r in sym_rows if r["cooldown_ok"])
        counts["mr_rsi_floor_blocked"] += blocked.get("mr_rsi_floor", 0)
        counts["flow_joined"] += sum(1 for r in sym_rows if r["flow"] is not None)
        counts["scanner_active"] += sum(1 for r in sym_rows if r["scanner_active"])
        counts["funding_joined"] += sum(1 for r in sym_rows if r["funding_rate"] is not None)
        counts["adx1h_available"] += sum(1 for r in sym_rows if r["adx1h"] is not None)
        n_long = sum(1 for r in sym_rows if r["side"] == "long")
        print(f"\n[{sym}] 5m={len(df5)} 1m={len(df1m)} funding={'y' if fund else 'n'} -> "
              f"{len(sym_rows)} signals ({n_long}L/{len(sym_rows) - n_long}S), "
              f"rsi-floor blocked {blocked.get('mr_rsi_floor', 0)}, "
              f"flow {sum(1 for r in sym_rows if r['flow'])}, {time.time() - ts0:.0f}s")

    rows.sort(key=lambda r: (r["ts"], r["symbol"]))
    counts["symbols_processed"] = len(processed)

    n_unchecked = sum(len(v) for k, v in snaps_by_sym.items() if k not in processed)
    fid = merge_fidelity(fid_reports, len(snaps), n_unchecked)
    print(f"\nFIDELITY GATE vs {os.path.basename(args.snapshots)} (in-window MR rows: {fid['n_snapshots']})")
    print(f"  checked {fid['n_checked']} (symbols processed) | matched {fid['n_matched']} "
          f"({fid['pct']:.1f}%) | unchecked (symbol not processed) {fid['n_unchecked']}")
    for k, t in fid["tolerance"].items():
        if t["n"]:
            print(f"  {k:<9} n={t['n']:>3} median|d|={t['median_abs_diff']:.3f} "
                  f"max|d|={t['max_abs_diff']:.3f} within {t['tol']}: {t['within_tol'] * 100:.0f}%")
        else:
            print(f"  {k:<9} n=0 (no snapshot carries it)")
    for m in fid["misses"]:
        print(f"    MISS {m['symbol']} {m['direction']} {m['ts_utc']} px={m['price']} "
              f"snap rsi_fast={m.get('snap_rsi_fast')} vol_ratio={m.get('snap_vol_ratio')}")
        for off, d in (m.get("diagnosis") or {}).items():
            if d and "reason" in d:
                print(f"         bar {int(off):+5d}s closed-bar: {d['signal']:<4} rsi7={d['rsi_fast']:.1f} "
                      f"vr={d['vol_ratio']:.2f} | {d['reason'][:60]}")
    if fid["passed"]:
        print("  PASS — regenerated set reproduces the live entries.")
    else:
        why = "no checkable snapshots" if fid["n_checked"] == 0 else f"{fid['pct']:.1f}% < {FIDELITY_MIN_PCT}%"
        print(f"  *** FIDELITY GATE FAILED ({why}) ***")
        if not (args.skip_fidelity or args.dry_run):
            print("  ABORT: no table written (use --skip-fidelity ONLY for tests).")
            return 1
        print("  continuing (" + ("--skip-fidelity" if args.skip_fidelity else "--dry-run") + ")")

    live = [r["net_by_cell"]["live"] for r in rows if r["cooldown_ok"] and r["net_by_cell"]["live"] is not None]
    print(f"\nTOTAL rows {len(rows)} | cooldown_ok {counts['cooldown_ok']} | "
          f"live-cell net (cooldown_ok, fill-all UPPER BOUND) ${sum(live):+.2f} over n={len(live)} "
          f"-> ${(sum(live) / len(live)) if live else 0:+.4f}/trade")
    print(f"  counts: {dict(counts)}")
    print(f"  wall {time.time() - t0:.0f}s")

    if args.dry_run:
        print(f"\n  --dry-run: not writing {args.out}")
        return 0
    meta = build_meta(start_ts, end_ts, universe, fid, counts)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"meta": meta, "rows": rows}, fh, indent=1)
    print(f"\n  wrote {args.out} ({os.path.getsize(args.out) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
