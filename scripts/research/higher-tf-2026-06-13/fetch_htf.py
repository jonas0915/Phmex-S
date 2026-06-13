#!/usr/bin/env python3
"""Fetch 1h + 4h OHLCV for liquid symbols from Phemex public API (no keys)."""
import ccxt, time, os, sys
import pandas as pd
from datetime import datetime, timezone

OUT = os.path.dirname(os.path.abspath(__file__)) + "/data"
os.makedirs(OUT, exist_ok=True)

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "LTC"]
TFS = ["1h", "4h"]
# ~7 months back
SINCE = "2025-11-15T00:00:00Z"

ex = ccxt.phemex({"enableRateLimit": True})

def fetch_all(symbol, tf, since_ms):
    out = []
    cur = since_ms
    while True:
        batch = ex.fetch_ohlcv(symbol, tf, since=cur, limit=1000)
        if not batch:
            break
        out += batch
        last = batch[-1][0]
        if len(batch) < 1000:
            break
        cur = last + 1
        time.sleep(ex.rateLimit / 1000)
        if last > ex.milliseconds():
            break
    # dedup
    seen = {}
    for r in out:
        seen[r[0]] = r
    rows = [seen[k] for k in sorted(seen)]
    return rows

results = {}
for s in SYMBOLS:
    pair = f"{s}/USDT:USDT"
    for tf in TFS:
        try:
            since_ms = ex.parse8601(SINCE)
            rows = fetch_all(pair, tf, since_ms)
            if not rows:
                print(f"{s} {tf}: EMPTY", flush=True)
                continue
            df = pd.DataFrame(rows, columns=["ts","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
            df = df[["timestamp","open","high","low","close","volume"]]
            fn = f"{OUT}/{s}_{tf}.csv"
            df.to_csv(fn, index=False)
            print(f"{s} {tf}: {len(df)} rows {df.timestamp.iloc[0]} -> {df.timestamp.iloc[-1]}", flush=True)
        except Exception as e:
            print(f"{s} {tf}: ERR {repr(e)[:150]}", flush=True)
print("DONE")
