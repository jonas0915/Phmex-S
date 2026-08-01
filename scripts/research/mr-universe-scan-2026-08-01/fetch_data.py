#!/usr/bin/env python3
"""Fetch + cache OHLCV for the MR universe scan (pre-reg 2026-08-01).
5m for replay, 1h for scoring, ~400d, per pre-registration. Parquet cache.
Read-only wrt the bot; reuses backtest.fetch_ohlcv_full (paginated, rate-limited)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, _BOT_DIR)

import ccxt  # noqa: E402
import backtest  # noqa: E402

DAYS = 400
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

universe = json.load(open(os.path.join(HERE, "universe.json")))
pairs = [r["symbol"] for r in universe["pairs"]]
print(f"{len(pairs)} pairs, {DAYS}d, timeframes: 5m + 1h", flush=True)

ex = ccxt.phemex({"enableRateLimit": True})

manifest = {}
for sym in pairs:
    key = sym.replace("/", "_").replace(":", "_")
    for tf in ("1h", "5m"):
        path = os.path.join(CACHE, f"{key}_{tf}_{DAYS}d.parquet")
        if os.path.exists(path):
            print(f"[cached] {sym} {tf}", flush=True)
        else:
            df = backtest.fetch_ohlcv_full(ex, sym, tf, DAYS)
            if df.empty:
                print(f"[EMPTY] {sym} {tf}", flush=True)
                continue
            df.to_parquet(path)
        import pandas as pd
        df = pd.read_parquet(path)
        manifest.setdefault(sym, {})[tf] = {
            "rows": len(df),
            "first": str(df.index[0]),
            "last": str(df.index[-1]),
            "span_days": round((df.index[-1] - df.index[0]).total_seconds() / 86400, 1),
        }
        print(f"  {sym} {tf}: {len(df)} rows {df.index[0]} -> {df.index[-1]}", flush=True)

with open(os.path.join(HERE, "data_manifest.json"), "w") as fh:
    json.dump({"days_requested": DAYS, "pairs": manifest}, fh, indent=1)
print("DONE", flush=True)
