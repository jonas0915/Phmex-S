#!/usr/bin/env python3
"""5m_mean_revert taker-vs-maker fill replay — SCREENING-GRADE.

Question: does the maker-only (PostOnly) entry cost `5m_mean_revert` real edge?
Regenerates the strategy's signals over N days of REAL Phemex OHLCV and replays
each one twice — filled as a MAKER vs filled as a TAKER — through the live exit
geometry, then reports NET (after-fee) edge for each policy so we can read the
decision matrix:

                taker net > 0            taker net <= 0
  maker net>0   taker fallback is a      signal real but execution-constrained
                live-forward candidate   -> keep maker-only
  maker net<=0  (rare)                    signal has no edge -> fill moot

Reuses (lessons.md META-RULE #4 — no reinvention):
  * backtest.fetch_ohlcv_full          (90d 5m signal bars + 1m exit path)
  * indicators.add_all_indicators      (same indicators the live bot computes)
  * strategies.bb_mean_reversion_strategy  (the exact slot signal, bar-by-bar)
  * st2_lab.exit_replay._simulate      (validated price-path SL/TP/trail engine)
  * st2_lab.stats.bootstrap_diff_ci    (bug-fixed independent-resample diff CI)

Live geometry replicated EXACTLY: under the live config (STOP_LOSS_PERCENT=1.2,
TAKE_PROFIT_PERCENT=1.6, tp_ratio=2.0) the ATR-adaptive SL/TP at
risk_manager.py:519-528 collapses algebraically to flat 1.2% SL / 1.6% TP (the
R:R cap forces sl_dist to the 1.2% floor every time). Trail+breakeven on
(durable_trail_enabled=True). 4h (14400s) hard time exit. adverse_exit DISABLED.

HONESTY CAVEATS (also printed at runtime; this is SCREENING-grade, not a forecast):
  * fill-all is OPTIMISTIC — real maker fill rate is ~27%. Maker-fill-all is an
    UPPER BOUND on the signal's edge, not a live expectation.
  * OB/tape gates (bot.py:1895-1948) are NOT modeled (no historical L2/flow) — so
    the regenerated signal set is a slight SUPERSET of what live would take.
    This inflates trade COUNT, not per-trade EV (the decision metric).
  * No historical spread -> taker entry modeled as close worsened by a fixed
    SLIPPAGE_PCT (0.05%); maker entry modeled at close. The maker->taker delta is
    therefore (slippage + fee gap), the same ~7bp ballpark the ST2.0 research found.
  * global max_positions=1 occupancy NOT modeled (per-symbol cooldown only) ->
    affects total $ and count, not per-trade expectancy.
  * Per edge-hunt-exhaustion: backtesting this data can only REJECT, never confirm.
    A positive read is a candidate for a BOUNDED LIVE FORWARD TEST, not a deploy.

Read-only. Touches no live state, no bot, no restart.

Run from repo root:
    python scripts/slot_lab/mean_revert_replay.py                 # default universe, 90d
    python scripts/slot_lab/mean_revert_replay.py --pairs ETH/USDT:USDT XLM/USDT:USDT --days 30
    python scripts/slot_lab/mean_revert_replay.py --dump-json reports/mr_replay.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

# repo root + scripts/ on path (backtest.py at root; st2_lab package under scripts/)
_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))

import ccxt  # noqa: E402
import backtest  # noqa: E402  (sets TRAIL_ARM_ROI=5.0 etc. used by _simulate's trail)
from indicators import add_all_indicators  # noqa: E402
from strategies import bb_mean_reversion_strategy, Signal  # noqa: E402
from st2_lab.exit_replay import _simulate  # noqa: E402
from st2_lab import stats as ST  # noqa: E402

# --- live constants (CLAUDE.md Current Parameters / .env) ---
LEVERAGE = 10
MARGIN = 10.0                       # .env TRADE_AMOUNT_USDT; slot sets no override
NOTIONAL = MARGIN * LEVERAGE        # $100
MAKER_FEE = 0.01                    # exchange.py:365 comment (no config constant)
TAKER_FEE = 0.06                    # config.py:75 TAKER_FEE_PERCENT
SLIPPAGE_PCT = 0.05                 # backtest.py:46 SLIPPAGE_PCT
PARAMS = {"sl_pct": 1.2, "tp_pct": 1.6, "hold_secs": 14400}  # flat SL/TP (see header), 4h hold

# Default universe: the pairs 5m_mean_revert actually traded (live+paper history) plus
# liquid majors. The live slot uses a dynamic scanner (top-12 by 24h vol); a fixed set
# is required for a historical replay. Override with --pairs.
DEFAULT_PAIRS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT",
    "ADA/USDT:USDT", "AVAX/USDT:USDT", "LTC/USDT:USDT", "XLM/USDT:USDT",
    "ARB/USDT:USDT", "AAVE/USDT:USDT", "TAO/USDT:USDT", "WLD/USDT:USDT",
    "ONDO/USDT:USDT", "RENDER/USDT:USDT", "1000PEPE/USDT:USDT",
]

WARMUP = 200          # bars before ema_200 is meaningful
SL_PRICE_FRAC = SLIPPAGE_PCT / 100.0


def _taker_entry(close: float, side: str) -> float:
    """Cross the spread: taker fill is worse than the resting maker price by slippage."""
    return close * (1 + SL_PRICE_FRAC) if side == "long" else close * (1 - SL_PRICE_FRAC)


def _net(entry_price, exit_price, side, reason, notional, entry_fee_pct):
    """Net PnL: gross - entry fee (policy) - exit fee. Exit fee is IDENTICAL across
    policies (taker on stop/trail via market trigger, maker on TP/hold) so the
    maker-vs-taker difference isolates the ENTRY mechanism. Mirrors exit_replay._net
    (exit_replay.py:68) except the entry leg fee is parameterized."""
    if side == "short":
        gross = (entry_price - exit_price) / entry_price * notional
    else:
        gross = (exit_price - entry_price) / entry_price * notional
    entry_fee = notional * entry_fee_pct / 100.0
    is_taker_exit = reason in ("stop_loss", "trailing_stop", "catastrophe")
    exit_fee = notional * (TAKER_FEE if is_taker_exit else MAKER_FEE) / 100.0
    return gross - entry_fee - exit_fee


def _build_path(df1m, entry_ts, hold_secs, side):
    """Forward 1m price path after entry, capped to the hold window. Each 1m bar is
    expanded to TWO points — adverse extreme first, then favorable — so _simulate's
    'stop wins if both inside one point' rule is pessimistic intrabar."""
    end_ts = entry_ts + hold_secs
    sub = df1m[(df1m.index.view("int64") // 1_000_000_000 > entry_ts) &
               (df1m.index.view("int64") // 1_000_000_000 <= end_ts)]
    path = []
    for ts_ns, row in zip(sub.index.view("int64"), sub.itertuples()):
        ts = ts_ns // 1_000_000_000
        hi, lo = float(row.high), float(row.low)
        if side == "long":
            path.append({"ts": ts, "price": lo})   # adverse first
            path.append({"ts": ts, "price": hi})
        else:
            path.append({"ts": ts, "price": hi})   # adverse first (short)
            path.append({"ts": ts, "price": lo})
    return path


def _regen_signals(df5, symbol):
    """Walk 5m bars, regenerate every non-HOLD bb_mean_reversion signal (strength>=0.80
    slot gate; per-symbol cooldown = hold window to avoid overlapping same-symbol).
    Captures entry features (rsi/vol_mult/adx/bb_width_pct/hour_pt) for filter analysis."""
    sigs = []
    cooldown_until = 0
    n = len(df5)
    idx_epoch = df5.index.view("int64") // 1_000_000_000
    for i in range(WARMUP, n):
        bar_close_ts = int(idx_epoch[i]) + 300  # ccxt ts = bar open; +5m = close/decision
        if bar_close_ts < cooldown_until:
            continue
        window = df5.iloc[i - 21:i + 1]          # strategy needs last, prev, last-20 vol
        ts = bb_mean_reversion_strategy(window, orderbook=None)
        if ts.signal == Signal.HOLD or ts.strength < 0.80:
            continue
        side = "long" if ts.signal == Signal.BUY else "short"
        last = df5.iloc[i]
        close = float(last["close"])
        vol_avg = float(df5["volume"].iloc[i - 19:i + 1].mean())
        bb_w = ((float(last["bb_upper"]) - float(last["bb_lower"])) / float(last["bb_mid"])
                if last["bb_mid"] else 0.0)
        sigs.append({
            "symbol": symbol, "side": side, "close": close,
            "entry_ts": bar_close_ts, "strength": ts.strength, "reason": ts.reason,
            "rsi": float(last.get("rsi_fast", 50)),
            "vol_mult": (float(last["volume"]) / vol_avg) if vol_avg else 0.0,
            "adx": float(last.get("adx", 0)),
            "bb_width_pct": bb_w * 100,
            "hour_pt": (int((bar_close_ts - 7 * 3600) // 3600) % 24),  # PT = UTC-7
        })
        cooldown_until = bar_close_ts + PARAMS["hold_secs"]
    return sigs


def _replay(sig, df1m):
    """Replay one signal as maker AND taker; return both net PnLs + exit reasons."""
    path = _build_path(df1m, sig["entry_ts"], PARAMS["hold_secs"], sig["side"])
    if not path:
        return None
    maker_px = sig["close"]
    taker_px = _taker_entry(sig["close"], sig["side"])
    m_exit, m_reason, _ = _simulate(sig["symbol"], sig["side"], maker_px,
                                    sig["entry_ts"], path, PARAMS, variant=True)
    t_exit, t_reason, _ = _simulate(sig["symbol"], sig["side"], taker_px,
                                    sig["entry_ts"], path, PARAMS, variant=True)
    return {
        "sym": sig["symbol"].split("/")[0], "side": sig["side"], "ts": sig["entry_ts"],
        "maker_net": _net(maker_px, m_exit, sig["side"], m_reason, NOTIONAL, MAKER_FEE),
        "taker_net": _net(taker_px, t_exit, sig["side"], t_reason, NOTIONAL, TAKER_FEE),
        "maker_reason": m_reason, "taker_reason": t_reason,
        "rsi": sig.get("rsi"), "vol_mult": sig.get("vol_mult"), "adx": sig.get("adx"),
        "bb_width_pct": sig.get("bb_width_pct"), "hour_pt": sig.get("hour_pt"),
    }


def _boot_mean_ci(xs, n_boot=2000, alpha=0.05, seed=0):
    """One-sample bootstrap CI for the mean (deterministic seed)."""
    import random
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(n_boot):
        s = sum(xs[rng.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    lo = means[int(alpha / 2 * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return (lo, hi)


def _summary(rows, label, key):
    nets = [r[key] for r in rows]
    n = len(nets)
    tot = sum(nets)
    wins = sum(1 for x in nets if x > 0)
    exp = tot / n if n else 0.0
    lo, hi = _boot_mean_ci(nets)
    rmix = Counter(r[key.replace("_net", "_reason")] for r in rows)
    print(f"\n=== {label} (n={n}) ===")
    print(f"  net total   ${tot:+.3f}")
    print(f"  expectancy  ${exp:+.4f}/trade   95% CI [{lo:+.4f}, {hi:+.4f}]")
    print(f"  win rate    {wins}/{n} ({wins/n*100:.1f}%)" if n else "  win rate    n/a")
    print(f"  exit mix    {dict(rmix)}")
    return {"label": label, "n": n, "net": tot, "exp": exp, "ci": [lo, hi],
            "wins": wins, "exit_mix": dict(rmix)}


def _walkforward(rows, key, folds=3):
    """Purged-ish walk-forward: chronological folds, report per-fold expectancy sign."""
    if len(rows) < folds * 2:
        print(f"\n  walk-forward: too few trades ({len(rows)}) for {folds} folds")
        return []
    srt = sorted(rows, key=lambda r: r["ts"])
    sz = len(srt) // folds
    out = []
    print(f"\n  walk-forward ({folds} chronological folds), {key}:")
    for f in range(folds):
        seg = srt[f * sz:(f + 1) * sz] if f < folds - 1 else srt[f * sz:]
        nets = [r[key] for r in seg]
        exp = sum(nets) / len(nets) if nets else 0.0
        out.append(exp)
        print(f"    fold {f+1}: n={len(seg):>4}  exp ${exp:+.4f}/trade  {'+' if exp>0 else '-'}")
    return out


def _verdict(m, t):
    print("\n--- DECISION MATRIX ---")
    m_pos, t_pos = m["exp"] > 0 and m["ci"][0] > 0, t["exp"] > 0 and t["ci"][0] > 0
    m_any, t_any = m["exp"] > 0, t["exp"] > 0
    if not m_any:
        print("  Maker-fill (optimistic upper bound) is NOT positive -> the SIGNAL has")
        print("  no edge even with ideal execution. Fill mechanism is moot. Do NOT add")
        print("  taker; the lever is the signal, not execution. (Consistent w/ edge-hunt.)")
    elif m_any and not t_any:
        print("  Signal is positive at maker but NEGATIVE at taker -> the slot is")
        print("  EXECUTION-CONSTRAINED. A taker fallback would convert edge into fee/")
        print("  slippage drag. KEEP maker-only; chase signal frequency or a tighter")
        print("  maker (queue/price), not aggressive fills.")
    elif t_pos and m_pos:
        print("  BOTH maker and taker net positive with CI excluding 0 -> a taker")
        print("  fallback is a CANDIDATE for a BOUNDED LIVE FORWARD TEST (not a deploy).")
        print("  Screening-grade only; confirm live before arming.")
    else:
        print("  Mixed/weak (positive point estimate but CI spans 0). Inconclusive at")
        print("  this sample. Gather more live data; do NOT change execution yet.")
    print(f"\n  maker->taker per-trade drag: ${t['exp']-m['exp']:+.4f}/trade")


def main():
    ap = argparse.ArgumentParser(description="5m_mean_revert taker-vs-maker fill replay")
    ap.add_argument("--pairs", nargs="+", default=DEFAULT_PAIRS, help="symbols to replay")
    ap.add_argument("--days", type=int, default=90, help="lookback days (default 90)")
    ap.add_argument("--dump-json", type=str, default=None, help="write rows+summary to PATH")
    args = ap.parse_args()

    print("5m_mean_revert taker-vs-maker fill replay — SCREENING-GRADE")
    print(f"  pairs={len(args.pairs)}  days={args.days}  params={PARAMS}")
    print(f"  fees: maker {MAKER_FEE}% / taker {TAKER_FEE}% per side | slippage {SLIPPAGE_PCT}% (taker entry)")
    print("  CAVEATS: fill-all is OPTIMISTIC (real ~27%); OB/tape gates NOT modeled;")
    print("  occupancy not modeled; can only REJECT, never confirm (forward-test adjudicates).")

    ex = ccxt.phemex({"enableRateLimit": True})
    cache_dir = os.path.join(_BOT_DIR, "reports", "cache")
    os.makedirs(cache_dir, exist_ok=True)

    def _cached(sym, tf):
        """Pickle OHLCV per (sym,tf,days) so re-runs (filter sweeps) skip the slow fetch.
        SAFE: only loads cache files THIS script wrote (self-generated OHLCV DataFrames in
        our own reports/cache/ dir) — never untrusted input, so pickle code-exec risk N/A."""
        import pickle
        key = f"{sym.replace('/', '_').replace(':', '_')}_{tf}_{args.days}d.pkl"
        path = os.path.join(cache_dir, key)
        if os.path.exists(path):
            return pickle.load(open(path, "rb"))
        df = backtest.fetch_ohlcv_full(ex, sym, tf, args.days)
        pickle.dump(df, open(path, "wb"))
        return df

    all_rows = []
    for sym in args.pairs:
        print(f"\n[{sym}]")
        try:
            df5 = _cached(sym, "5m")
            df1m = _cached(sym, "1m")
        except Exception as e:
            print(f"  fetch failed: {e} — skipping")
            continue
        if df5.empty or df1m.empty or len(df5) < WARMUP + 2:
            print("  insufficient data — skipping")
            continue
        df5 = add_all_indicators(df5)
        sigs = _regen_signals(df5, sym)
        print(f"  {len(sigs)} signals regenerated")
        for s in sigs:
            r = _replay(s, df1m)
            if r:
                all_rows.append(r)

    if not all_rows:
        print("\nNo replayable signals. Try more pairs or a longer window.")
        return

    print(f"\n{'='*60}\nTOTAL replayable signals: {len(all_rows)}")
    m = _summary(all_rows, "MAKER fill-all (optimistic upper bound)", "maker_net")
    t = _summary(all_rows, "TAKER fill-all (realistic aggressive)", "taker_net")
    diff_ci = ST.bootstrap_diff_ci([r["taker_net"] for r in all_rows],
                                   [r["maker_net"] for r in all_rows])
    print(f"\n  taker - maker diff 95% CI: [{diff_ci[0]:+.4f}, {diff_ci[1]:+.4f}]/trade")
    _walkforward(all_rows, "taker_net")
    _verdict(m, t)

    if args.dump_json:
        os.makedirs(os.path.dirname(args.dump_json) or ".", exist_ok=True)
        with open(args.dump_json, "w") as fh:
            json.dump({"maker": m, "taker": t, "diff_ci": list(diff_ci),
                       "rows": all_rows}, fh, indent=1)
        print(f"\n  dump: {args.dump_json}")


if __name__ == "__main__":
    main()
