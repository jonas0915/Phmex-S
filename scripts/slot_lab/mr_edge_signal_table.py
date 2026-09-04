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
  * FORMING-BAR evaluation (prereg amendment v2, 2026-09-03): the live bot evaluates
    `df.iloc[-1]` = the still-forming 5m candle every ~90 s cycle (bot.py:3012-3017 ->
    ws_feed.get_ohlcv, indicators on the partial bar). `--eval-mode forming` (default)
    rebuilds the partial candle from 1m bars at minute m = 1..5 (m = 5 == the closed
    bar), on a 300-bar frame (ws_feed.py:97/224 cache cap — NOT .env CANDLE_LOOKBACK=500,
    which only the REST fallback sees), and the FIRST firing minute is the signal.
    Rows carry fire_minute / confirmed_at_close / partial_vol_ratio. `--eval-mode closed`
    is the old closed-bar regen (kept for parity tests).
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
    nice -n 19 python3 scripts/slot_lab/mr_edge_signal_table.py --eval-mode forming \
        --prereg docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md \
        --cache-dir reports/cache/mr_edge_20260601_20260903 \
        --universe reports/mr_edge_2026/universe.json \
        --start 2026-06-01 --end 2026-09-03 \
        --out reports/mr_edge_2026/signals.json

signals.json is written ONLY when the fidelity gate passes (>= 90%); otherwise
reports/mr_edge_2026/fidelity_failed.json carries every miss + per-minute diagnosis.
reports/mr_edge_2026/fidelity_real_trades.{md,json} (real closed trades x snapshots x
regen match, confirmed_at_close cohorts) is written in both cases — it is a fidelity
artifact, not an outcome read.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import pickle
import random
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
from st2_lab.stats import bootstrap_diff_ci  # noqa: E402  (independent resample, house rule)
from indicators import add_all_indicators, ema, rsi, bollinger_bands, atr, adx as _adx_fn  # noqa: E402
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

# --- forming-bar evaluation (prereg amendment v2) ---
LIVE_LOOKBACK = 300               # ws_feed.py:97/224: cache capped at 300 candles -> the frame
                                  # bot.py:3013 hands add_all_indicators (.env CANDLE_LOOKBACK=500
                                  # only reaches the REST fallback at bot.py:3015)
FORMING_MINUTES = 5               # 1m bars per 5m candle; m = 5 == the closed bar
EVAL_MODES = ("closed", "forming")
_OHLCV = ["open", "high", "low", "close", "volume"]
_STRAT_CORE = ["ema_200", "rsi", "atr", "adx"]   # add_all_indicators' dropna subset minus macd
                                                 # (macd = ema diff, adjust=False -> never NaN)
TRADE_SNAP_TOL_S = 120            # real closed trade <-> entry snapshot join: |opened_at - ts|
N_BOOT = 2000                     # prereg: one-sample + diff bootstrap reps, fixed seed

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
    "fidelity gate tolerates +/-1 bar and reports feature drift vs the entry snapshot",
    "live 4h extension modeled with the adverse 1m extreme at the 4h mark (pessimistic)",
    "global max_positions occupancy not modeled -> affects count, not per-trade EV",
    "replay can only REJECT; survivors go to a real-money forward verdict line",
]
MODE_CAVEATS = {
    "closed": [
        "eval_mode=closed: signals regenerated on CLOSED 5m bars with full-history indicators; "
        "live evaluates the FORMING bar on a 300-bar frame — known to miss most live entries",
    ],
    "forming": [
        "eval_mode=forming: partial candle rebuilt from exchange 1m bars at minute m=1..5 and "
        "evaluated on a 300-bar frame (ws_feed cache cap); first firing minute = the signal",
        "timing parity gap: evaluation on a 60 s grid (1m closes) vs the live ~90 s cycle at "
        "arbitrary seconds into the bar -> the live bot can fire between grid points",
        "volume parity gap: ws-feed candle-builder volume != exchange 1m volume",
        "frame parity gap: REST fallback (ws stale) evaluates a 500-bar frame; ws path = 300",
    ],
}


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
            # closed-bar regen == the m=5 evaluation by definition
            "fire_minute": FORMING_MINUTES, "confirmed_at_close": True,
            "partial_vol_ratio": (float(last["volume"]) / vol_avg) if vol_avg else 0.0,
        })
        if ts >= cooldown_until:
            cooldown_until = ts + COOLDOWN_S
    return sigs


# ---------------------------------------------------------------------------
# FORMING-BAR regeneration (prereg amendment v2)
# ---------------------------------------------------------------------------

def strategy_frame(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Exactly the columns bb_mean_reversion_strategy reads, computed with the SAME
    indicators.py functions add_all_indicators calls (bit-identical, tested) and the
    same NaN-head drop. ~13x cheaper than the full 30-column set — needed because the
    forming walk calls this up to 5x per candidate bar."""
    df = df_raw[_OHLCV].copy()
    c, h, lo = df["close"], df["high"], df["low"]
    df["ema_9"] = ema(c, 9)
    df["ema_21"] = ema(c, 21)
    df["ema_50"] = ema(c, 50)
    df["ema_200"] = ema(c, 200)
    df["rsi"] = rsi(c, 14)
    df["rsi_fast"] = rsi(c, 7)
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(c)
    df["atr"] = atr(h, lo, c)
    df["adx"], df["plus_di"], df["minus_di"] = _adx_fn(h, lo, c)
    return df.dropna(subset=_STRAT_CORE)


def partial_candle(bars_1m: np.ndarray, m: int) -> dict:
    """Forming 5m candle after the first m 1m bars (rows of [o, h, l, c, v]) closed:
    open = first open, high/low = running extremes, close = m-th close, volume = sum."""
    if m < 1 or m > len(bars_1m):
        raise ValueError(f"m={m} outside 1..{len(bars_1m)}")
    a = bars_1m[:m]
    return {"open": float(a[0, 0]), "high": float(a[:, 1].max()), "low": float(a[:, 2].min()),
            "close": float(a[m - 1, 3]), "volume": float(a[:, 4].sum())}


def forming_frame(df5_raw: pd.DataFrame, i: int, partial: dict | None,
                  lookback: int = LIVE_LOOKBACK) -> pd.DataFrame:
    """The live-shaped frame at bar i: the trailing `lookback` raw bars ending at i, with
    bar i replaced by `partial` (the forming candle) when given, then strategy_frame."""
    raw = df5_raw.iloc[max(0, i - lookback + 1):i + 1][_OHLCV]
    if partial is not None:
        raw = raw.copy()
        raw.iloc[-1] = [partial[k] for k in _OHLCV]
    return strategy_frame(raw)


def forming_candidates(df5_raw: pd.DataFrame) -> np.ndarray:
    """Cheap prune: bar i can only fire if the previous CLOSED bar penetrated a band —
    the strategy's own prev_close/prev_wick tests (strategies.py:92-93 / 105-106). BB at
    the previous bar depends only on its trailing 20 closes, so the full-frame value is
    identical to the live frame's."""
    up, _, lo = bollinger_bands(df5_raw["close"])
    pc, pl, ph = df5_raw["close"].shift(1), df5_raw["low"].shift(1), df5_raw["high"].shift(1)
    up_p, lo_p = up.shift(1), lo.shift(1)
    pen = (pc <= lo_p) | (pl < lo_p * 0.998) | (pc >= up_p) | (ph > up_p * 1.002)
    return pen.fillna(False).to_numpy(dtype=bool)


def _verdict(sig) -> str | None:
    if sig.signal == Signal.HOLD or sig.strength < MIN_STRENGTH:
        return None
    return "long" if sig.signal == Signal.BUY else "short"


def regen_signals_forming(df5_raw: pd.DataFrame, df1m: pd.DataFrame | None, symbol: str,
                          start_ts: int | None = None, end_ts: int | None = None,
                          blocked: dict | None = None, stats: dict | None = None,
                          lookback: int = LIVE_LOOKBACK, keep_partial: bool = False) -> list[dict]:
    """Walk 5m bars the way the live bot sees them: for every candidate bar (prev bar
    penetrated a band) rebuild the forming candle after each 1m close (m = 1..5; m = 5
    is the closed 5m bar itself) on the trailing `lookback` frame and take the FIRST
    minute the strategy fires. ts = that 1m close, entry_px = that 1m close. Long RSI
    floor (live parses RSI(7) rounded to 0.1 from the reason string) and the 4h
    cooldown flag are applied at fire time. confirmed_at_close = the m = 5 evaluation
    fires the same side (and passes the floor). Bars whose 1m data is missing fall
    back to the closed-bar evaluation (fire_minute = 5). `stats` receives bars /
    candidates / prune_ratio / strategy_calls / bars_no_1m."""
    st = stats if stats is not None else {}
    st.update({"bars": 0, "candidates": 0, "strategy_calls": 0, "bars_no_1m": 0})
    n = len(df5_raw)
    epoch5 = _epoch_index(df5_raw)
    raw5 = df5_raw[_OHLCV].to_numpy(dtype=float)
    mask = forming_candidates(df5_raw)
    if df1m is not None and len(df1m):
        e1 = _epoch_index(df1m)
        a1 = df1m[_OHLCV].to_numpy(dtype=float)
    else:
        e1, a1 = np.zeros(0, dtype=np.int64), np.zeros((0, 5), dtype=float)
    sigs: list[dict] = []
    cooldown_until = 0
    for i in range(lookback - 1, n):
        b = int(epoch5[i])
        if end_ts is not None and b + 60 > end_ts:
            break
        if start_ts is not None and b + 300 < start_ts:
            continue
        st["bars"] += 1
        if not mask[i]:
            continue
        st["candidates"] += 1
        lo_1 = int(np.searchsorted(e1, b, side="left"))
        hi_1 = int(np.searchsorted(e1, b + 300, side="left"))
        blk = a1[lo_1:hi_1]
        have = {int(mm): k for k, mm in enumerate((e1[lo_1:hi_1] - b) // 60)}
        if hi_1 <= lo_1:
            st["bars_no_1m"] += 1
        closed_row = dict(zip(_OHLCV, (float(v) for v in raw5[i])))
        fired = None
        close_side = None
        floor_hit = False
        for m in range(1, FORMING_MINUTES + 1):
            if fired is not None and m < FORMING_MINUTES:
                continue                          # only the close verdict is still needed
            if m < FORMING_MINUTES:
                if (m - 1) not in have:
                    continue                      # no 1m close for this minute (gap / early end)
                partial = partial_candle(blk, have[m - 1] + 1)
            else:
                partial = closed_row              # exact closed bar, never the 1m aggregate
            ts = b + 60 * m
            if start_ts is not None and ts < start_ts:
                continue
            if end_ts is not None and ts > end_ts:
                break
            fr = forming_frame(df5_raw, i, None if m == FORMING_MINUTES else partial, lookback)
            st["strategy_calls"] += 1
            side = _verdict(bb_mean_reversion_strategy(fr, orderbook=None))
            if side == "long" and round(float(fr["rsi_fast"].iloc[-1]), 1) < LONG_RSI_MIN:
                floor_hit = True                  # bot.py:3195 (_rsi_from_reason -> 0.1 rounding)
                side = None
            if m == FORMING_MINUTES:
                close_side = side
            if side is not None and fired is None:
                fired = (m, side, fr, partial)
        if fired is None:
            if floor_hit and blocked is not None:
                blocked["mr_rsi_floor"] = blocked.get("mr_rsi_floor", 0) + 1
            continue
        m, side, fr, partial = fired
        ts = b + 60 * m
        last = fr.iloc[-1]
        vol_avg = float(fr["volume"].to_numpy()[-20:].mean())
        vr = (float(partial["volume"]) / vol_avg) if vol_avg else 0.0
        bb_mid = float(last["bb_mid"])
        bb_w = ((float(last["bb_upper"]) - float(last["bb_lower"])) / bb_mid) if bb_mid else 0.0
        h = hour_pt(ts)
        row = {
            "symbol": symbol, "ts": ts, "bar_open_ts": b, "side": side,
            "entry_px": float(partial["close"]), "strength": float(_strength_of(fr)),
            "rsi": float(last["rsi"]), "rsi_fast": float(last["rsi_fast"]),
            "vol_ratio": vr, "bb_width_pct": bb_w * 100.0, "adx5m": float(last["adx"]),
            "hour_pt": h, "session": session_for_hour(h),
            "cooldown_ok": ts >= cooldown_until,
            "fire_minute": m, "confirmed_at_close": bool(close_side == side),
            "partial_vol_ratio": vr,
        }
        if keep_partial:
            row["_partial"] = partial
        sigs.append(row)
        if ts >= cooldown_until:
            cooldown_until = ts + COOLDOWN_S
    st["prune_ratio"] = (st["candidates"] / st["bars"]) if st["bars"] else 0.0
    return sigs


def _strength_of(fr: pd.DataFrame) -> float:
    """Strength of the (already known non-HOLD) verdict on this frame — a second
    strategy call is cheaper to read than to thread through the loop."""
    return bb_mean_reversion_strategy(fr, orderbook=None).strength


# ---------------------------------------------------------------------------
# 1h ADX the live way (bot.py:901-916): 100 x 1h bars incl. the forming one
# ---------------------------------------------------------------------------

_H_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def adx1h_live(df5_raw: pd.DataFrame, bar_open_ts: int, partial: dict | None = None) -> float | None:
    """1h ADX as the live bot sees it at the signal bar: exchange.get_ohlcv('1h',
    limit=100) returns 99 closed hours + the forming hour, then add_all_indicators()
    and the last row's adx. Here the forming hour aggregates the 5m bars up to and
    including the signal bar — replaced by `partial` (the forming 5m candle at fire
    time) when given. None when < 30 hourly bars exist (live returns None)."""
    cut = pd.Timestamp(int(bar_open_ts), unit="s", tz="UTC")
    lo = cut - pd.Timedelta(hours=101)
    sub = df5_raw.loc[lo:cut]
    if sub.empty:
        return None
    if partial is not None and sub.index[-1] == cut:
        sub = sub[_OHLCV].copy()
        sub.iloc[-1] = [partial[k] for k in _OHLCV]
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
                      start_ts=None, end_ts=None, blocked=None, eval_mode: str = "closed",
                      stats: dict | None = None, lookback: int = LIVE_LOOKBACK,
                      timing: dict | None = None) -> list[dict]:
    """Signal rows + context joins + outcome cells for one symbol. eval_mode 'closed'
    (function default, parity tests) or 'forming' (CLI default)."""
    if eval_mode not in EVAL_MODES:
        raise ValueError(f"eval_mode must be one of {EVAL_MODES}, got {eval_mode!r}")
    t0 = time.time()
    if eval_mode == "forming":
        sigs = regen_signals_forming(df5_raw, df1m, symbol, start_ts, end_ts, blocked=blocked,
                                     stats=stats, lookback=lookback, keep_partial=True)
    else:
        sigs = regen_signals(df5_raw, symbol, start_ts, end_ts, blocked=blocked)
    t1 = time.time()
    rows = []
    for s in sigs:
        partial = s.pop("_partial", None)
        s["adx1h"] = adx1h_live(df5_raw, s["bar_open_ts"], partial=partial)
        s["flow"] = flow.nearest(symbol, s["ts"]) if flow is not None else None
        s["scanner_active"] = flow.active(symbol, s["ts"]) if flow is not None else False
        s["funding_rate"], s["funding_ts"] = funding_at(funding, s["ts"])
        s["net_by_cell"], s["exit_by_cell"] = outcomes(s["side"], s["entry_px"], s["ts"],
                                                       df1m, symbol)
        rows.append(s)
    if timing is not None:
        timing["regen_s"] = t1 - t0
        timing["outcomes_s"] = time.time() - t1
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


def forming_reasons(df5_raw: pd.DataFrame, df1m: pd.DataFrame | None, ts: int,
                    lookback: int = LIVE_LOOKBACK, offsets=(-300, 0, 300)) -> dict:
    """Diagnostics for a fidelity miss in forming mode: for the snapshot's 5m bar and its
    neighbours, what the strategy said after EACH 1m close (m = 1..5, m = 5 = closed
    bar) on the live-shaped frame. {offset_s: {m: {...}} | None}."""
    epoch = _epoch_index(df5_raw)
    raw5 = df5_raw[_OHLCV].to_numpy(dtype=float)
    if df1m is not None and len(df1m):
        e1, a1 = _epoch_index(df1m), df1m[_OHLCV].to_numpy(dtype=float)
    else:
        e1, a1 = np.zeros(0, dtype=np.int64), np.zeros((0, 5), dtype=float)
    bar_open = ts - ts % 300
    out = {}
    for off in offsets:
        b = bar_open + off
        pos = int(np.searchsorted(epoch, b))
        if pos >= len(epoch) or epoch[pos] != b or pos < lookback - 1:
            out[str(off)] = None
            continue
        lo_1, hi_1 = int(np.searchsorted(e1, b, side="left")), int(np.searchsorted(e1, b + 300, side="left"))
        blk = a1[lo_1:hi_1]
        have = {int(mm): k for k, mm in enumerate((e1[lo_1:hi_1] - b) // 60)}
        per_m = {}
        for m in range(1, FORMING_MINUTES + 1):
            if m < FORMING_MINUTES:
                if (m - 1) not in have:
                    per_m[str(m)] = None
                    continue
                partial = partial_candle(blk, have[m - 1] + 1)
                fr = forming_frame(df5_raw, pos, partial, lookback)
            else:
                partial = dict(zip(_OHLCV, (float(v) for v in raw5[pos])))
                fr = forming_frame(df5_raw, pos, None, lookback)
            sig = bb_mean_reversion_strategy(fr, orderbook=None)
            r = fr.iloc[-1]
            vol_avg = float(fr["volume"].to_numpy()[-20:].mean())
            per_m[str(m)] = {
                "signal": sig.signal.value, "reason": sig.reason, "rsi_fast": float(r["rsi_fast"]),
                "vol_ratio": (float(partial["volume"]) / vol_avg) if vol_avg else 0.0,
                "close": float(r["close"]), "bb_upper": float(r["bb_upper"]),
                "bb_lower": float(r["bb_lower"]), "adx": float(r["adx"]),
            }
        out[str(off)] = per_m
    return out


def _index_signals(signals: list[dict]):
    by_key: dict[tuple, list[dict]] = {}
    for s in signals:
        by_key.setdefault((s["symbol"], s["side"]), []).append(s)
    for v in by_key.values():
        v.sort(key=lambda s: s["bar_open_ts"])
    opens = {k: [s["bar_open_ts"] for s in v] for k, v in by_key.items()}
    return by_key, opens


def _match_signal(by_key, opens, sym: str, side: str, ts: int) -> dict | None:
    """Nearest regenerated signal with the same symbol+side whose 5m bar is the
    snapshot's bar +/- SNAP_BAR_TOL_S (one bar)."""
    bar_open = ts - ts % 300
    cands, arr = by_key.get((sym, side), []), opens.get((sym, side), [])
    i = bisect.bisect_left(arr, bar_open - SNAP_BAR_TOL_S)
    best = None
    while i < len(arr) and arr[i] <= bar_open + SNAP_BAR_TOL_S:
        c = cands[i]
        if best is None or abs(c["bar_open_ts"] - bar_open) < abs(best["bar_open_ts"] - bar_open):
            best = c
        i += 1
    return best


def fidelity_gate(snapshots: list[dict], signals: list[dict], symbols_checked: set,
                  min_pct: float = FIDELITY_MIN_PCT, diagnose=None) -> dict:
    """Every real MR entry (same symbol, same side, same 5m bar +/-1) must exist in the
    regenerated set. Snapshots for symbols not processed are reported, not counted.
    `diagnose(snap) -> dict` (optional) is attached to each miss as "diagnosis".
    Each match records the regen row's fire_minute / confirmed_at_close and the
    snapshot's seconds (and whole 1m bars) elapsed into its 5m bar."""
    by_key, opens = _index_signals(signals)

    n_checked = n_matched = n_unchecked = 0
    misses, matches, diffs = [], [], {"rsi_fast": [], "htf_adx": [], "vol_ratio": []}
    for snap in snapshots:
        sym, side, ts = snap.get("symbol"), snap.get("direction"), int(snap["ts"])
        if sym not in symbols_checked:
            n_unchecked += 1
            continue
        n_checked += 1
        bar_open = ts - ts % 300
        best = _match_signal(by_key, opens, sym, side, ts)
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
        matches.append({
            "symbol": sym, "direction": side, "ts": ts,
            "ts_utc": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "snap_sec_into_bar": ts % 300, "snap_minutes_elapsed": (ts % 300) // 60,
            "bar_offset_s": int(best["bar_open_ts"] - bar_open), "regen_ts": int(best["ts"]),
            "fire_minute": int(best.get("fire_minute", FORMING_MINUTES)),
            "confirmed_at_close": bool(best.get("confirmed_at_close", True)),
        })
        if snap.get("rsi_fast") is not None:
            diffs["rsi_fast"].append(float(snap["rsi_fast"]) - best["rsi_fast"])
        if snap.get("htf_adx") is not None and best.get("adx1h") is not None:
            diffs["htf_adx"].append(float(snap["htf_adx"]) - best["adx1h"])
        vr = (snap.get("regime") or {}).get("vol_ratio")
        if vr is not None:
            diffs["vol_ratio"].append(float(vr) - best["vol_ratio"])
    return _fidelity_report(len(snapshots), n_checked, n_matched, n_unchecked, misses,
                            diffs, min_pct, matches)


def _fidelity_report(n_snapshots, n_checked, n_matched, n_unchecked, misses, diffs, min_pct,
                     matches=None):
    matches = matches or []
    pct = (100.0 * n_matched / n_checked) if n_checked else 0.0
    hist = Counter(m["fire_minute"] for m in matches)
    return {
        "n_snapshots": n_snapshots, "n_checked": n_checked, "n_matched": n_matched,
        "n_unchecked": n_unchecked, "pct": pct, "min_pct": min_pct,
        "passed": bool(n_checked > 0 and pct >= min_pct), "misses": misses,
        "matches": matches,
        "fire_minute_hist": {m: int(hist.get(m, 0)) for m in range(1, FORMING_MINUTES + 1)},
        "n_confirmed_at_close": sum(1 for m in matches if m["confirmed_at_close"]),
        "tolerance": {k: _tol_stats(v, TOLERANCES[k]) for k, v in diffs.items()},
        "_diffs": diffs,
    }


def merge_fidelity(reports: list[dict], n_snapshots: int, n_unchecked: int,
                   min_pct: float = FIDELITY_MIN_PCT) -> dict:
    """Combine per-symbol gate reports (run while each symbol's frames are loaded, so
    misses can carry bar-level diagnostics) into the single gate verdict."""
    diffs = {"rsi_fast": [], "htf_adx": [], "vol_ratio": []}
    misses, matches, n_checked, n_matched = [], [], 0, 0
    for r in reports:
        n_checked += r["n_checked"]
        n_matched += r["n_matched"]
        misses.extend(r["misses"])
        matches.extend(r.get("matches", []))
        for k in diffs:
            diffs[k].extend(r.get("_diffs", {}).get(k, []))
    misses.sort(key=lambda m: m["ts"])
    matches.sort(key=lambda m: m["ts"])
    return _fidelity_report(n_snapshots, n_checked, n_matched, n_unchecked, misses, diffs,
                            min_pct, matches)


# ---------------------------------------------------------------------------
# real-money companion read (prereg amendment v2, Change 3): closed trades x snapshots
# x regen match -> confirmed_at_close cohorts. SCREENING GRADE, n ~ 30-45. READ ONLY.
# ---------------------------------------------------------------------------

REAL_TRADES_GRADE = ("SCREENING GRADE — n≈30-45 real trades; companion read reported alongside "
                     "the replay, never a verdict on its own (prereg amendment v2, Change 3)")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bootstrap_mean_ci(xs, n_boot: int = N_BOOT, alpha: float = 0.05, seed: int = 0):
    """One-sample percentile bootstrap CI of the mean (same seeded-random style as
    st2_lab.stats so the two CIs share conventions). (None, None) when empty."""
    xs = [float(x) for x in xs]
    if not xs:
        return None, None
    rnd = random.Random(seed)
    n = len(xs)
    means = sorted(sum(xs[rnd.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    lo_i = int((alpha / 2.0) * n_boot)
    hi_i = min(int((1.0 - alpha / 2.0) * n_boot), n_boot - 1)
    return means[lo_i], means[hi_i]


def load_closed_trades(path: str) -> list[dict]:
    """closed_trades of a slot state file. Opened read-only; never written back."""
    if not os.path.exists(path):
        return []
    with open(path, "r") as fh:
        d = json.load(fh)
    return list(d.get("closed_trades", []) or [])


def _cohort(xs, n_boot: int, seed: int) -> dict:
    xs = [float(x) for x in xs]
    lo, hi = bootstrap_mean_ci(xs, n_boot=n_boot, seed=seed)
    return {"n": len(xs), "net": float(sum(xs)), "wr": (sum(1 for x in xs if x > 0) / len(xs)) if xs else None,
            "mean": (sum(xs) / len(xs)) if xs else None, "ci95": [lo, hi]}


def real_trade_fidelity(trades: list[dict], snapshots: list[dict], signals: list[dict],
                        symbols_checked: set, tol_s: int = TRADE_SNAP_TOL_S,
                        n_boot: int = N_BOOT, seed: int = 0) -> dict:
    """Join every closed trade to its entry snapshot (same symbol+side, |opened_at - ts|
    <= tol_s, nearest), then to the regenerated signal set (same bar +/-1, same side).
    Cohorts on REAL money (mode == 'live', regen-matched only): confirmed_at_close
    True vs False — n, net, WR, mean, one-sample bootstrap CI each, and the
    independent-resample diff CI (st2_lab.stats.bootstrap_diff_ci)."""
    by_key, opens = _index_signals(signals)
    snaps_by: dict[tuple, list] = {}
    for sn in snapshots:
        if sn.get("ts") is None:
            continue
        snaps_by.setdefault((sn.get("symbol"), sn.get("direction")), []).append((int(sn["ts"]), sn))
    for v in snaps_by.values():
        v.sort(key=lambda x: x[0])

    out = []
    n_with = n_without = n_live = 0
    for t in trades:
        sym, side, opened = t.get("symbol"), t.get("side"), t.get("opened_at")
        if opened is None:
            continue
        opened = float(opened)
        mode = t.get("mode")
        best_sn, best_dt = None, None
        for ts, sn in snaps_by.get((sym, side), []):
            dt = abs(opened - ts)
            if dt <= tol_s and (best_dt is None or dt < best_dt):
                best_sn, best_dt = sn, dt
        rec = {
            "symbol": sym, "side": side, "opened_at": opened,
            "opened_utc": datetime.fromtimestamp(opened, tz=timezone.utc).isoformat(timespec="seconds"),
            "net_pnl": t.get("net_pnl"), "exit_reason": t.get("exit_reason") or t.get("reason"),
            "mode": mode, "has_snapshot": best_sn is not None,
            "snap_ts": int(best_sn["ts"]) if best_sn else None,
            "snap_dt_s": (round(best_dt, 1) if best_dt is not None else None),
            "snap_minutes_elapsed": ((int(best_sn["ts"]) % 300) // 60) if best_sn else None,
            "in_regen_universe": (sym in symbols_checked) if best_sn else None,
            "matched": None, "fire_minute": None, "confirmed_at_close": None, "regen_ts": None,
        }
        if mode == "live":
            n_live += 1
        if best_sn is None:
            n_without += 1
        else:
            n_with += 1
            if sym in symbols_checked:
                best = _match_signal(by_key, opens, sym, side, int(best_sn["ts"]))
                rec["matched"] = best is not None
                if best is not None:
                    rec["fire_minute"] = int(best.get("fire_minute", FORMING_MINUTES))
                    rec["confirmed_at_close"] = bool(best.get("confirmed_at_close", True))
                    rec["regen_ts"] = int(best["ts"])
        out.append(rec)
    out.sort(key=lambda r: r["opened_at"])

    live_matched = [r for r in out if r["mode"] == "live" and r["matched"] is True and r["net_pnl"] is not None]
    conf = [r["net_pnl"] for r in live_matched if r["confirmed_at_close"]]
    form = [r["net_pnl"] for r in live_matched if not r["confirmed_at_close"]]
    diff = bootstrap_diff_ci(conf, form, n_boot=n_boot, seed=seed) if (conf and form) else (None, None)
    live_unmatched = [r["net_pnl"] for r in out if r["mode"] == "live" and r["matched"] is False
                      and r["net_pnl"] is not None]
    live_unchecked = [r for r in out if r["mode"] == "live" and r["matched"] is None]
    return {
        "grade": REAL_TRADES_GRADE, "tol_s": tol_s, "n_boot": n_boot, "seed": seed,
        "n_closed_trades": len(out), "n_with_snapshot": n_with, "n_without_snapshot": n_without,
        "n_live": n_live, "n_live_matched": len(live_matched),
        "n_live_unmatched": len(live_unmatched), "n_live_unchecked": len(live_unchecked),
        "n_non_live": sum(1 for r in out if r["mode"] != "live"),
        "trades": out,
        "cohorts": {
            "confirmed": _cohort(conf, n_boot, seed),
            "forming_only": _cohort(form, n_boot, seed),
            "diff_ci95_confirmed_minus_forming": [diff[0], diff[1]],
            "live_unmatched": _cohort(live_unmatched, n_boot, seed),
            "n_boot": n_boot,
        },
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def _fmt(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}"


def real_trade_fidelity_md(rep: dict) -> str:
    c = rep["cohorts"]
    L = ["# 5m_mean_revert — real closed trades vs forming-bar regeneration",
         "", f"**{rep['grade']}**", "",
         f"Generated {rep['generated_at']} | join: same symbol+side, |opened_at − snapshot ts| ≤ {rep['tol_s']} s | "
         f"regen match: same 5m bar ±1, same side | bootstrap {rep['n_boot']} reps, seed {rep['seed']}",
         "",
         f"Closed trades {rep['n_closed_trades']} | with snapshot {rep['n_with_snapshot']} | without {rep['n_without_snapshot']} | "
         f"mode=live {rep['n_live']} (regen-matched {rep['n_live_matched']}, unmatched {rep['n_live_unmatched']}, "
         f"unchecked/out-of-universe {rep['n_live_unchecked']}) | non-live {rep['n_non_live']}",
         "", "## Cohorts on REAL money (mode=live, regen-matched)", "",
         "| cohort | n | net $ | WR | mean $/trade | 95% CI (one-sample bootstrap) |",
         "|---|---|---|---|---|---|"]
    for name, key in (("confirmed_at_close = True", "confirmed"), ("confirmed_at_close = False (forming-only)", "forming_only"),
                      ("live, snapshot but NO regen match", "live_unmatched")):
        k = c[key]
        wr = "—" if k["wr"] is None else f"{k['wr'] * 100:.0f}%"
        ci = "—" if k["ci95"][0] is None else f"[{k['ci95'][0]:+.3f}, {k['ci95'][1]:+.3f}]"
        L.append(f"| {name} | {k['n']} | {_fmt(k['net'])} | {wr} | {_fmt(k['mean'], 3)} | {ci} |")
    d = c["diff_ci95_confirmed_minus_forming"]
    dtxt = "—" if d[0] is None else f"[{d[0]:+.3f}, {d[1]:+.3f}]"
    L += ["", f"Diff CI (confirmed − forming-only, independent resample): {dtxt}", "",
          "## Per-trade", "",
          "| opened (UTC) | symbol | side | mode | net $ | exit | snap dt s | snap min | regen match | fire_minute | confirmed_at_close |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["trades"]:
        m = {True: "y", False: "n", None: "—"}[r["matched"]]
        cc = {True: "True", False: "False", None: "—"}[r["confirmed_at_close"]]
        L.append(f"| {r['opened_utc']} | {r['symbol']} | {r['side']} | {r['mode']} | {_fmt(r['net_pnl'])} | "
                 f"{r['exit_reason']} | {r['snap_dt_s'] if r['snap_dt_s'] is not None else '—'} | "
                 f"{r['snap_minutes_elapsed'] if r['snap_minutes_elapsed'] is not None else '—'} | {m} | "
                 f"{r['fire_minute'] if r['fire_minute'] is not None else '—'} | {cc} |")
    L += ["", "Notes: `regen match = —` means the trade has no snapshot, or its symbol is outside the regenerated "
          "universe/window. Cohorts use ONLY mode=live trades with a regen match. Screening grade; not a verdict."]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# meta / IO
# ---------------------------------------------------------------------------

def build_meta(start_ts, end_ts, universe, fidelity, counts, prereg_sha: str | None = None,
               eval_mode: str = "closed", lookback: int = LIVE_LOOKBACK,
               forming_stats: dict | None = None) -> dict:
    iso = lambda t: datetime.fromtimestamp(int(t), tz=timezone.utc).isoformat()  # noqa: E731
    return {
        "window": {"start": iso(start_ts), "end": iso(end_ts),
                   "start_ts": int(start_ts), "end_ts": int(end_ts)},
        "universe": list(universe), "n_symbols": len(universe),
        "eval_mode": eval_mode, "lookback_bars": int(lookback),
        "forming_minutes": FORMING_MINUTES, "forming_stats": dict(forming_stats or {}),
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
        "prereg_sha": prereg_sha,
        "caveats": list(CAVEATS) + list(MODE_CAVEATS.get(eval_mode, [])),
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


def _print_caveats(eval_mode: str):
    print("  CAVEATS:")
    for c in list(CAVEATS) + list(MODE_CAVEATS.get(eval_mode, [])):
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
    ap.add_argument("--trades", default=os.path.join(_BOT_DIR, "trading_state_5m_mean_revert.json"),
                    help="slot state file (READ ONLY) for the real-money companion read")
    ap.add_argument("--out", default=os.path.join(_BOT_DIR, "reports", "mr_edge_2026", "signals.json"))
    ap.add_argument("--fail-out", default=os.path.join(_BOT_DIR, "reports", "mr_edge_2026", "fidelity_failed.json"))
    ap.add_argument("--real-trades-out", default=os.path.join(_BOT_DIR, "reports", "mr_edge_2026",
                                                              "fidelity_real_trades"),
                    help="basename; .md and .json are written")
    ap.add_argument("--eval-mode", choices=EVAL_MODES, default="forming",
                    help="forming = live-faithful partial-candle walk (default); closed = old closed-bar regen")
    ap.add_argument("--lookback", type=int, default=LIVE_LOOKBACK,
                    help="bars in the live-shaped frame (ws_feed cache cap 300)")
    ap.add_argument("--prereg", default=os.path.join(_BOT_DIR, "docs", "superpowers", "specs",
                                                     "2026-09-03-mr-edge-search-prereg.md"),
                    help="prereg file; its sha256 is stored in meta.prereg_sha")
    ap.add_argument("--prereg-sha", default=None, help="explicit sha256 (overrides --prereg)")
    ap.add_argument("--limit-symbols", type=int, default=None, help="process only the first N")
    ap.add_argument("--skip-fidelity", action="store_true", help="TEST ONLY: never abort on the gate")
    ap.add_argument("--dry-run", action="store_true", help="run everything, write nothing")
    args = ap.parse_args(argv)

    start_ts, end_ts = _parse_ts(args.start), _parse_ts(args.end)
    universe = load_universe(args.universe, args.cache_dir)
    if args.limit_symbols:
        universe = universe[:args.limit_symbols]
    prereg_sha = args.prereg_sha
    if prereg_sha is None and args.prereg and os.path.exists(args.prereg):
        prereg_sha = sha256_file(args.prereg)

    print("5m_mean_revert edge search — Phase C SIGNAL TABLE")
    print(f"  window {args.start} -> {args.end} UTC | symbols={len(universe)} | "
          f"cache={args.cache_dir}")
    print(f"  eval_mode={args.eval_mode} | lookback={args.lookback} bars | prereg_sha={prereg_sha}")
    print(f"  ${MARGIN:.0f} @ {LEVERAGE}x = ${NOTIONAL:.0f} notional | fees maker {MAKER_FEE}% / "
          f"taker {TAKER_FEE}% | trail arm {TRAIL_ARM_ROI}% | long RSI floor {LONG_RSI_MIN}")
    print(f"  cells: {len(cell_keys())} (live + {len(cell_keys()) - 1} grid)")
    _print_caveats(args.eval_mode)

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
    forming_tot = Counter()
    for sym in universe:
        p5, p1 = cache_path(args.cache_dir, sym, "5m"), cache_path(args.cache_dir, sym, "1m")
        if not (os.path.exists(p5) and os.path.exists(p1)):
            print(f"\n[{sym}] cache missing ({os.path.basename(p5)} / {os.path.basename(p1)}) — skipping")
            counts["symbols_missing_cache"] += 1
            continue
        df5, df1m = _to_utc_index(_load_pkl(p5)), _to_utc_index(_load_pkl(p1))
        if df5.empty or df1m.empty or len(df5) < max(WARMUP, args.lookback) + 22:
            print(f"\n[{sym}] insufficient data — skipping")
            counts["symbols_insufficient"] += 1
            continue
        fund = load_funding(args.cache_dir, sym)
        blocked, fstats, timing = {}, {}, {}
        ts0 = time.time()
        sym_rows = build_symbol_rows(sym, df5, df1m, flow=flow, funding=fund,
                                     start_ts=start_ts, end_ts=end_ts, blocked=blocked,
                                     eval_mode=args.eval_mode, stats=fstats,
                                     lookback=args.lookback, timing=timing)
        processed.add(sym)
        rows.extend(sym_rows)
        if snaps_by_sym.get(sym):
            if args.eval_mode == "forming":
                diag = lambda sn, _d5=df5, _d1=df1m: forming_reasons(_d5, _d1, int(sn["ts"]), args.lookback)  # noqa: E731
            else:
                diag = lambda sn, _d5=df5: bar_reasons(_d5, int(sn["ts"]))  # noqa: E731
            fid_reports.append(fidelity_gate(snaps_by_sym[sym], sym_rows, {sym}, diagnose=diag))
        counts["signals"] += len(sym_rows)
        counts["cooldown_ok"] += sum(1 for r in sym_rows if r["cooldown_ok"])
        counts["mr_rsi_floor_blocked"] += blocked.get("mr_rsi_floor", 0)
        counts["flow_joined"] += sum(1 for r in sym_rows if r["flow"] is not None)
        counts["scanner_active"] += sum(1 for r in sym_rows if r["scanner_active"])
        counts["funding_joined"] += sum(1 for r in sym_rows if r["funding_rate"] is not None)
        counts["adx1h_available"] += sum(1 for r in sym_rows if r["adx1h"] is not None)
        counts["confirmed_at_close"] += sum(1 for r in sym_rows if r["confirmed_at_close"])
        counts["fired_before_close"] += sum(1 for r in sym_rows if r["fire_minute"] < FORMING_MINUTES)
        for k in ("bars", "candidates", "strategy_calls", "bars_no_1m"):
            forming_tot[k] += int(fstats.get(k, 0))
        n_long = sum(1 for r in sym_rows if r["side"] == "long")
        print(f"\n[{sym}] 5m={len(df5)} ({df5.index[0]:%m-%d}..{df5.index[-1]:%m-%d %H:%M}) 1m={len(df1m)} "
              f"funding={'y' if fund else 'n'} -> {len(sym_rows)} signals ({n_long}L/{len(sym_rows) - n_long}S), "
              f"rsi-floor blocked {blocked.get('mr_rsi_floor', 0)}, "
              f"flow {sum(1 for r in sym_rows if r['flow'])}")
        if args.eval_mode == "forming":
            print(f"      forming: bars {fstats.get('bars', 0)} -> candidates {fstats.get('candidates', 0)} "
                  f"(prune keeps {fstats.get('prune_ratio', 0) * 100:.1f}%), strategy calls "
                  f"{fstats.get('strategy_calls', 0)}, bars w/o 1m {fstats.get('bars_no_1m', 0)}, "
                  f"fired<close {sum(1 for r in sym_rows if r['fire_minute'] < FORMING_MINUTES)}, "
                  f"confirmed {sum(1 for r in sym_rows if r['confirmed_at_close'])}")
        print(f"      timing: regen {timing.get('regen_s', 0):.0f}s + outcomes {timing.get('outcomes_s', 0):.0f}s "
              f"= {time.time() - ts0:.0f}s (elapsed {time.time() - t0:.0f}s)", flush=True)

    rows.sort(key=lambda r: (r["ts"], r["symbol"]))
    counts["symbols_processed"] = len(processed)
    if forming_tot["bars"]:
        forming_tot["prune_ratio"] = forming_tot["candidates"] / forming_tot["bars"]

    n_unchecked = sum(len(v) for k, v in snaps_by_sym.items() if k not in processed)
    fid = merge_fidelity(fid_reports, len(snaps), n_unchecked)
    print(f"\nFIDELITY GATE vs {os.path.basename(args.snapshots)} (in-window MR rows: {fid['n_snapshots']})")
    print(f"  checked {fid['n_checked']} (symbols processed) | matched {fid['n_matched']} "
          f"({fid['pct']:.1f}%) | unchecked (symbol not processed) {fid['n_unchecked']}")
    print(f"  matched fire_minute hist {fid['fire_minute_hist']} | confirmed_at_close "
          f"{fid['n_confirmed_at_close']}/{fid['n_matched']}")
    for k, t in fid["tolerance"].items():
        if t["n"]:
            print(f"  {k:<9} n={t['n']:>3} median|d|={t['median_abs_diff']:.3f} "
                  f"max|d|={t['max_abs_diff']:.3f} within {t['tol']}: {t['within_tol'] * 100:.0f}%")
        else:
            print(f"  {k:<9} n=0 (no snapshot carries it)")
    for m in fid["matches"]:
        print(f"    MATCH {m['symbol']} {m['direction']} {m['ts_utc']} snap +{m['snap_sec_into_bar']}s "
              f"({m['snap_minutes_elapsed']} x 1m closed) -> regen fire_minute={m['fire_minute']} "
              f"confirmed={m['confirmed_at_close']} bar_offset={m['bar_offset_s']:+d}s")
    for m in fid["misses"]:
        print(f"    MISS {m['symbol']} {m['direction']} {m['ts_utc']} px={m['price']} "
              f"snap rsi_fast={m.get('snap_rsi_fast')} vol_ratio={m.get('snap_vol_ratio')}")
        for off, d in (m.get("diagnosis") or {}).items():
            if not d:
                continue
            if "reason" in d:      # closed-mode diagnosis
                print(f"         bar {int(off):+5d}s closed-bar: {d['signal']:<4} rsi7={d['rsi_fast']:.1f} "
                      f"vr={d['vol_ratio']:.2f} | {d['reason'][:60]}")
            else:                  # forming-mode: per minute
                for mm, e in d.items():
                    if e:
                        print(f"         bar {int(off):+5d}s m={mm}: {e['signal']:<4} rsi7={e['rsi_fast']:.1f} "
                              f"vr={e['vol_ratio']:.2f} | {e['reason'][:60]}")
    if fid["passed"]:
        print("  PASS — regenerated set reproduces the live entries.")
    else:
        why = "no checkable snapshots" if fid["n_checked"] == 0 else f"{fid['pct']:.1f}% < {FIDELITY_MIN_PCT}%"
        print(f"  *** FIDELITY GATE FAILED ({why}) ***")

    # --- real-money companion read (fidelity artifact; no outcome cells are read) ---
    all_snaps = load_snapshots(args.snapshots)          # every MR snapshot, any date
    trades = load_closed_trades(args.trades)
    real = real_trade_fidelity(trades, all_snaps, rows, processed)
    c = real["cohorts"]
    print(f"\nREAL TRADES x REGEN ({real['grade']})")
    print(f"  closed {real['n_closed_trades']} | with snapshot {real['n_with_snapshot']} | live {real['n_live']} "
          f"(matched {real['n_live_matched']}, unmatched {real['n_live_unmatched']}, unchecked {real['n_live_unchecked']})")
    for name in ("confirmed", "forming_only", "live_unmatched"):
        k = c[name]
        ci = "—" if k["ci95"][0] is None else f"[{k['ci95'][0]:+.3f}, {k['ci95'][1]:+.3f}]"
        wr = "—" if k["wr"] is None else f"{k['wr'] * 100:.0f}%"
        print(f"  {name:<15} n={k['n']:>2} net={_fmt(k['net'])} WR={wr} mean={_fmt(k['mean'], 3)} ci95={ci}")
    d = c["diff_ci95_confirmed_minus_forming"]
    print(f"  diff ci95 (confirmed - forming_only, independent resample): "
          f"{'—' if d[0] is None else f'[{d[0]:+.3f}, {d[1]:+.3f}]'}")
    if not args.dry_run:
        os.makedirs(os.path.dirname(args.real_trades_out) or ".", exist_ok=True)
        with open(args.real_trades_out + ".json", "w") as fh:
            json.dump(real, fh, indent=1)
        with open(args.real_trades_out + ".md", "w") as fh:
            fh.write(real_trade_fidelity_md(real))
        print(f"  wrote {args.real_trades_out}.md / .json")

    print(f"\nTOTAL rows {len(rows)} | cooldown_ok {counts['cooldown_ok']} | "
          f"fired<close {counts['fired_before_close']} | confirmed_at_close {counts['confirmed_at_close']}")
    if forming_tot["bars"]:
        print(f"  forming totals: bars {forming_tot['bars']} -> candidates {forming_tot['candidates']} "
              f"(prune keeps {forming_tot['prune_ratio'] * 100:.1f}%), strategy calls {forming_tot['strategy_calls']}, "
              f"bars w/o 1m {forming_tot['bars_no_1m']}")
    print(f"  counts: {dict(counts)}")
    print(f"  wall {time.time() - t0:.0f}s")

    if not fid["passed"] and not args.skip_fidelity:
        if args.dry_run:
            print(f"\n  --dry-run: gate failed; not writing {args.fail_out}")
            return 1
        os.makedirs(os.path.dirname(args.fail_out) or ".", exist_ok=True)
        with open(args.fail_out, "w") as fh:
            json.dump({"eval_mode": args.eval_mode, "lookback_bars": args.lookback, "prereg_sha": prereg_sha,
                       "window": {"start": args.start, "end": args.end}, "counts": dict(counts),
                       "forming_stats": dict(forming_tot),
                       "fidelity": {k: v for k, v in fid.items() if not k.startswith("_")},
                       "generated_at": datetime.now(tz=timezone.utc).isoformat()}, fh, indent=1)
        print(f"\n  ABORT: fidelity gate failed — wrote {args.fail_out}; NOT writing {args.out}")
        return 1
    if not fid["passed"]:
        print("  continuing (--skip-fidelity)")

    if args.dry_run:
        print(f"\n  --dry-run: not writing {args.out}")
        return 0
    meta = build_meta(start_ts, end_ts, universe, fid, counts, prereg_sha=prereg_sha,
                      eval_mode=args.eval_mode, lookback=args.lookback, forming_stats=forming_tot)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"meta": meta, "rows": rows}, fh, indent=1)
    print(f"\n  wrote {args.out} ({os.path.getsize(args.out) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
