#!/usr/bin/env python3
"""Flow replay for the offline backtester.

Loads logs/flow_capture.jsonl (per-scan OB+tape snapshots the live bot recorded
since 2026-05-10) and replays them into backtest.py so the flow-dependent entry
gates fire exactly as they did live. Without this the sim has no flow -> the
flow gates can't block -> ~10x overfire vs live.

Two pieces:
  1. FlowIndex  -- load + (symbol, epoch) lookup of captured ob/flow snapshots.
  2. passes_flow_gates() -- faithful port of the live bot's flow-dependent entry
     gates that live OUTSIDE the strategy (in bot.py, applied after the strategy
     returns a signal). Citations to bot.py lines inline.

FIDELITY NOTES
  - Every flow field the gates need is captured (buy_ratio, cvd_slope, divergence,
    large_trade_bias, trade_count, ob.imbalance/walls/spread). Verified 2026-05-30.
  - Ensemble layer 5 (funding) is NOT captured (exchange API, not flow) -> treated
    as False in replay. Max replay confidence is 6/7 instead of 7/7. The gate is
    4/7, so this only matters when funding would have been the deciding 4th layer
    (rare). Documented, not silently dropped.
  - The strategy itself (htf_l2_anticipation) ALSO applies its own internal OB /
    tape-sufficiency / volume gates when it receives real ob+flow; those fire
    inside confluence_strategy(df, ob, htf_df, flow). This module only ports the
    gates that live in bot.py, not in the strategy.
"""
import json
import os
from bisect import bisect_right

# --- Ensemble gate threshold (live: Config.MIN_ENSEMBLE_CONFIDENCE, 4/7) ---
try:
    from config import Config
    MIN_ENSEMBLE_CONFIDENCE = int(getattr(Config, "MIN_ENSEMBLE_CONFIDENCE", 4))
except Exception:
    MIN_ENSEMBLE_CONFIDENCE = 4

# CVD-exempt strategies (bot.py:1104). htf_l2_anticipation is NOT exempt.
_CVD_EXEMPT = ("htf_confluence_pullback", "bb_mean_reversion")

# Hurst layer strategy sets (bot.py:313-314).
_TREND_STRATS = {"momentum_continuation", "trend_pullback", "keltner_squeeze",
                 "htf_confluence_pullback", "htf_l2_anticipation"}
_REVERSION_STRATS = {"vwap_reversion", "htf_confluence_vwap", "bb_mean_reversion"}


def _sanitize_ob(ob):
    """Coerce captured bid_walls/ask_walls (stored as int counts) to [] so the
    strategy's list-iteration (strategies.py:609-628) doesn't crash. Returns a
    shallow copy; leaves real lists untouched."""
    if not ob:
        return ob
    out = dict(ob)
    for k in ("bid_walls", "ask_walls"):
        v = out.get(k)
        if not isinstance(v, list):
            out[k] = []
    return out


class FlowIndex:
    """Loads flow_capture.jsonl and answers (symbol, epoch_seconds) -> (ob, flow)."""

    def __init__(self, path="logs/flow_capture.jsonl", tolerance_s=300):
        self.tolerance_s = tolerance_s
        # symbol -> (sorted list of ts, parallel list of (ob, flow))
        self._ts: dict[str, list[int]] = {}
        self._snap: dict[str, list[tuple]] = {}
        # symbol -> parallel list of captured prices (may contain None for old rows)
        self._px: dict[str, list] = {}
        self._load(path)

    def _load(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"flow capture not found: {path}")
        # accumulate per-symbol, then sort by ts
        rows: dict[str, list[tuple]] = {}
        n = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                sym = d.get("symbol")
                ts = d.get("ts")
                if sym is None or ts is None:
                    continue
                rows.setdefault(sym, []).append((int(ts), d.get("ob"), d.get("flow"), d.get("price")))
                n += 1
        for sym, items in rows.items():
            items.sort(key=lambda x: x[0])
            self._ts[sym] = [it[0] for it in items]
            self._snap[sym] = [(it[1], it[2]) for it in items]
            self._px[sym] = [it[3] for it in items]
        self.row_count = n
        self.symbol_count = len(rows)

    def coverage_window(self):
        lo = min((t[0] for t in self._ts.values() if t), default=None)
        hi = max((t[-1] for t in self._ts.values() if t), default=None)
        return lo, hi

    def get(self, symbol, epoch_s):
        """Snapshot at-or-just-before epoch_s within tolerance. Returns (ob, flow)
        or (None, None) if no snapshot is close enough (caller should skip the
        candle -- we can't faithfully replay flow we never captured).

        The captured `ob` stores bid_walls/ask_walls as INTEGER COUNTS, but
        strategies.py:609-628 iterates them as lists of [price, size]. Passing the
        raw int crashes the strategy (TypeError, silently swallowed by backtest.py's
        try/except -> candle dropped). We sanitize counts -> [] here so the strategy
        runs. Wall STRENGTH boosters (+0.02) can't be reconstructed from counts, but
        base strength 0.82 > 0.80 gate, so boosters don't change the entry decision."""
        ts_list = self._ts.get(symbol)
        if not ts_list:
            return None, None
        i = bisect_right(ts_list, epoch_s) - 1
        if i < 0:
            return None, None
        if epoch_s - ts_list[i] > self.tolerance_s:
            return None, None
        ob, flow = self._snap[symbol][i]
        return _sanitize_ob(ob), flow

    def snapshot_age(self, symbol, epoch_s):
        """Age in seconds of the snapshot get() would return at epoch_s, or None
        if no snapshot within tolerance. Diagnostics only (entry-time flow
        coverage measurement for the 2026-06-11 cohort-gate sims)."""
        ts_list = self._ts.get(symbol)
        if not ts_list:
            return None
        i = bisect_right(ts_list, epoch_s) - 1
        if i < 0:
            return None
        age = epoch_s - ts_list[i]
        return age if age <= self.tolerance_s else None

    def prices_between(self, symbol, t0, t1):
        """All captured (ts, price) snapshots with t0 < ts <= t1, in time order.

        Used by backtest.py's live-fidelity exit model as the intra-bar price
        path: the live bot's 60s exit loop saw a fresh price every cycle, and
        the capture writes one price per symbol per scan (~75s cadence), so
        these are the closest thing to the prices the live exit checks ran on.
        Rows with no captured price (pre-2026-05-10 schema) are skipped.
        """
        ts_list = self._ts.get(symbol)
        if not ts_list:
            return []
        i = bisect_right(ts_list, t0)
        j = bisect_right(ts_list, t1)
        px = self._px[symbol]
        return [(ts_list[k], float(px[k])) for k in range(i, j) if px[k]]


def replay_confidence(candle_row, ob, flow, htf_last, htf_prev, direction,
                      strat_name=""):
    """Faithful replica of bot.py:274-340 _compute_confidence. Returns (count, layers).

    candle_row : current 5m candle (Series) -- needs close, vwap, hurst.
    htf_last   : last 1h row (Series) or None -- ema_50.
    htf_prev   : the ONE-BAR-BACK 1h row (Series) or None -- for ema_50 slope (live
                 uses htf_df.iloc[-2], bot.py:289).
    funding (layer 5) is always absent in replay (not captured); see note below.
    """
    layers = {}
    is_long = direction == "long"
    price = float(candle_row.get("close", 0))

    # Layer 1: HTF trend -- EMA-50 SLOPE SIGN only (bot.py:286-293). No price-vs-ema.
    htf_ok = False
    if htf_last is not None and htf_prev is not None:
        ema50 = float(htf_last.get("ema_50", 0) or 0)
        ema50_prev = float(htf_prev.get("ema_50", 0) or 0)
        if ema50 and ema50_prev:
            slope = (ema50 - ema50_prev) / ema50_prev
            htf_ok = (slope > 0) if is_long else (slope < 0)
    layers["htf_trend"] = htf_ok

    # Layer 2: VWAP position (bot.py:296-300)
    vwap_ok = False
    c_vwap = float(candle_row.get("vwap", 0) or 0)
    if c_vwap and price:
        vwap_ok = (price > c_vwap) if is_long else (price < c_vwap)
    layers["vwap_pos"] = vwap_ok

    # Layer 3: CVD -- divergence-upgrade path OR slope sign (bot.py:304-310)
    cvd_ok = False
    if flow:
        cvd_slope = flow.get("cvd_slope", 0.0)
        div = flow.get("divergence")
        if (is_long and div == "bullish") or (not is_long and div == "bearish"):
            cvd_ok = True   # "cvd_divergence" (strongest)
        elif (is_long and cvd_slope > 0) or (not is_long and cvd_slope < 0):
            cvd_ok = True   # "cvd"
    layers["cvd"] = cvd_ok

    # Layer 4: Hurst regime -- must align with strategy type (bot.py:312-319)
    hurst = float(candle_row.get("hurst", 0.5) or 0.5)
    hurst_ok = False
    if hurst == hurst:  # not NaN
        if hurst > 0.55 and (not strat_name or strat_name in _TREND_STRATS):
            hurst_ok = True
        elif hurst < 0.45 and (not strat_name or strat_name in _REVERSION_STRATS):
            hurst_ok = True
    layers["hurst"] = hurst_ok

    # Layer 5: Funding -- NOT captured -> always False (fidelity gap; replay caps at
    # 6/7. Threshold stays 4/7, so this biases replay slightly STRICTER than live
    # for any signal that relied on funding as a confirming layer -- conservative.)
    layers["funding"] = False

    # Layer 6: OB imbalance (bot.py:328-331)
    ob_ok = False
    if ob:
        imb = ob.get("imbalance", 0)
        ob_ok = (imb > 0.1) if is_long else (imb < -0.1)
    layers["ob_imbalance"] = ob_ok

    # Layer 7: Order flow tape (bot.py:334-337) -- trade_count > 10
    flow_ok = False
    if flow and flow.get("trade_count", 0) > 10:
        buy_ratio = flow.get("buy_ratio", 0.5)
        flow_ok = (buy_ratio > 0.55) if is_long else (buy_ratio < 0.45)
    layers["order_flow"] = flow_ok

    count = sum(1 for v in layers.values() if v)
    return count, layers


def passes_flow_gates(strat_name, direction, ob, flow,
                      candle_row, htf_last, htf_prev, min_conf=None):
    """Faithful port of the live bot's post-signal flow gate block (bot.py:1082-1143).

    Returns (passed: bool, reason: str). reason is '' when passed.
    Mirrors live order: tape -> cvd -> divergence -> large_trade -> ensemble(4/7).

    min_conf: optional override of the ensemble floor (live default 4/7). Used by
    the 2026-06-11 Phase-3 cohort-gate sims (--min-conf). NOTE: funding (layer 5)
    is never captured, so replay confidence caps at 6/7 — min_conf=5 in replay is
    stricter than live 5/7 would be.
    """
    tc = flow.get("trade_count", 0) if flow else 0

    # ===== TAPE GATE -- bot.py:1082 =====
    if flow and tc >= 5:
        buy_ratio = flow.get("buy_ratio", 0.5)
        long_thresh, short_thresh = (0.40, 0.60) if tc <= 20 else (0.45, 0.55)
        if direction == "long" and buy_ratio < long_thresh:
            return False, f"tape(buy_ratio {buy_ratio:.2f}<{long_thresh})"
        if direction == "short" and buy_ratio > short_thresh:
            return False, f"tape(buy_ratio {buy_ratio:.2f}>{short_thresh})"

    # ===== CVD SLOPE GATE -- bot.py:1115 (INSIDE the tc>20 block; NOT tc>=5) =====
    # htf_l2_anticipation is NOT exempt. Live only applies this when trade_count>20.
    if flow and tc > 20 and strat_name not in _CVD_EXEMPT:
        cvd_slope = flow.get("cvd_slope", 0.0)
        if direction == "long" and cvd_slope < -0.3:
            return False, "cvd"
        if direction == "short" and cvd_slope > 0.3:
            return False, "cvd"

    # ===== DIVERGENCE GATE -- bot.py:1110 (always-on) =====
    divergence = flow.get("divergence") if flow else None
    if divergence == "bearish" and direction == "long":
        return False, "divergence"
    if divergence == "bullish" and direction == "short":
        return False, "divergence"

    # ===== LARGE TRADE BIAS GATE -- bot.py:1118 (trade_count > 20) =====
    if flow and tc > 20:
        lt_bias = flow.get("large_trade_bias", 0.0)
        if direction == "long" and lt_bias < -0.3:
            return False, "large_trade"
        if direction == "short" and lt_bias > 0.3:
            return False, "large_trade"

    # ===== ENSEMBLE CONFIDENCE GATE (4/7) -- bot.py:1138 =====
    conf, _ = replay_confidence(candle_row, ob, flow, htf_last, htf_prev, direction,
                                strat_name=strat_name)
    _floor = MIN_ENSEMBLE_CONFIDENCE if min_conf is None else int(min_conf)
    if conf < _floor:
        return False, f"ensemble({conf}/7)"

    return True, ""


if __name__ == "__main__":
    # quick self-test: load + report coverage
    idx = FlowIndex()
    lo, hi = idx.coverage_window()
    from datetime import datetime, timezone
    def fmt(t):
        return datetime.fromtimestamp(t, tz=timezone.utc).isoformat() if t else "n/a"
    print(f"loaded {idx.row_count} rows across {idx.symbol_count} symbols")
    print(f"window: {fmt(lo)} -> {fmt(hi)}")
    # sample lookup
    for sym in list(idx._ts.keys())[:3]:
        ts = idx._ts[sym][len(idx._ts[sym]) // 2]
        ob, flow = idx.get(sym, ts)
        print(f"  {sym} @ {fmt(ts)}: flow={flow}")
