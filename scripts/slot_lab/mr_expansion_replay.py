#!/usr/bin/env python3
"""MR expansion-candidate replay — SCREENING-GRADE (2026-07-13 overnight task).

Replays bb_mean_reversion over 90d on liquid Phemex perps OUTSIDE the current
scanner rotation, reusing the EXACT machinery of mean_revert_replay.py (imported,
not copied): same signal regen (strength>=0.80, 4h cooldown), same 1m price-path
exit sim, same fees/geometry.

Candidates chosen 2026-07-13 from live Phemex 24h quote volume (fetch_tickers),
top non-rotation symbols above the $3M scanner floor:
  BNB $23.9M, LINK $16.7M, SUI $14.2M, NEAR $4.95M, OP $3.5M
(small-caps NO-GO 7/7 respected — all are majors/mid-caps).

HONESTY:
  * Same caveats as mean_revert_replay.py (fill-all optimistic, OB/tape gates not
    modeled, occupancy not modeled, screening can only REJECT).
  * WINDOW MISMATCH: baseline mr_replay_90d.json was fetched 6/30 (window ~Apr 1 -
    Jun 30); this run fetches 90d ending at run time (~Apr 14 - Jul 13). Combined-
    book comparisons must restrict to the overlapping window (mr_symbol_map.py does).
  * Candidates were picked by LIQUIDITY, not by peeking at their PnL — no selection
    bias at the picking stage. Any "add the winners" set assembled AFTER seeing
    results is selection-biased and is hypothesis-generation only.

Read-only vs live. New cache pickles only (reports/cache/<SYM>_..._90d.pkl).

Run from repo root:
    python3 scripts/slot_lab/mr_expansion_replay.py \
        --dump-json reports/mr_expansion_90d.json
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts", "slot_lab"))

import ccxt  # noqa: E402
import backtest  # noqa: E402
from indicators import add_all_indicators  # noqa: E402
import mean_revert_replay as mrr  # noqa: E402  (the existing rig — reused, unmodified)

CANDIDATES = [
    "BNB/USDT:USDT", "LINK/USDT:USDT", "SUI/USDT:USDT",
    "NEAR/USDT:USDT", "OP/USDT:USDT",
]


def main():
    ap = argparse.ArgumentParser(description="MR expansion-candidate 90d replay")
    ap.add_argument("--pairs", nargs="+", default=CANDIDATES)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--dump-json", default="reports/mr_expansion_90d.json")
    args = ap.parse_args()

    print("MR EXPANSION replay — candidates OUTSIDE current rotation (screening-grade)")
    print(f"  pairs={args.pairs}")
    print(f"  days={args.days}  params={mrr.PARAMS}  fetched_at={int(time.time())}")

    ex = ccxt.phemex({"enableRateLimit": True})
    cache_dir = os.path.join(_BOT_DIR, "reports", "cache")
    os.makedirs(cache_dir, exist_ok=True)

    def _cached(sym, tf):
        """Pickle-cache OHLCV, same pattern as mean_revert_replay.py. SAFE: only loads
        cache files this rig itself wrote (self-generated DataFrames in our own
        reports/cache/) — never untrusted input, so pickle code-exec risk N/A."""
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
        if df5.empty or df1m.empty or len(df5) < mrr.WARMUP + 2:
            print("  insufficient data — skipping")
            continue
        df5 = add_all_indicators(df5)
        sigs = mrr._regen_signals(df5, sym)
        print(f"  {len(sigs)} signals regenerated")
        for s in sigs:
            r = mrr._replay(s, df1m)
            if r:
                all_rows.append(r)

    if not all_rows:
        print("\nNo replayable signals on any candidate.")
        return

    print(f"\n{'=' * 60}\nTOTAL candidate signals: {len(all_rows)}")
    m = mrr._summary(all_rows, "MAKER fill-all (candidates)", "maker_net")
    t = mrr._summary(all_rows, "TAKER fill-all (candidates)", "taker_net")

    path = os.path.join(_BOT_DIR, args.dump_json)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"maker": m, "taker": t, "rows": all_rows,
                   "fetched_at": int(time.time()), "pairs": args.pairs}, fh, indent=1)
    print(f"\n  dump: {args.dump_json}")


if __name__ == "__main__":
    main()
