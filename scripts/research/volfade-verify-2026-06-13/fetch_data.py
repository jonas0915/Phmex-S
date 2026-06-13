#!/usr/bin/env python3
"""Fetch fresh 1h OHLCV from phemex public API via ccxt. No keys."""
import ccxt, time, json, os, sys
import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
SYMBOLS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","LTC","TRX","DOT","MATIC","NEAR","ATOM"]
TF = "1h"
TARGET_BARS = 24*365  # aim ~1 year

ex = ccxt.phemex({"enableRateLimit": True})
ex.load_markets()

def find_symbol(base):
    # prefer USDT perpetual swap
    cands = []
    for s, m in ex.markets.items():
        if m.get("base")==base and m.get("quote")=="USDT" and m.get("swap"):
            cands.append(s)
    if not cands:
        for s, m in ex.markets.items():
            if m.get("base")==base and m.get("quote")=="USDT":
                cands.append(s)
    return cands[0] if cands else None

def fetch_all(symbol, target):
    tf_ms = 3600*1000
    now = ex.milliseconds()
    since = now - target*tf_ms
    all_rows = []
    cursor = since
    while True:
        try:
            batch = ex.fetch_ohlcv(symbol, TF, since=cursor, limit=1000)
        except Exception as e:
            print(f"   err {e}; retry"); time.sleep(2); continue
        if not batch:
            break
        all_rows += batch
        last = batch[-1][0]
        if last <= cursor:
            break
        cursor = last + tf_ms
        if cursor >= now or len(batch) < 1000:
            break
        time.sleep(ex.rateLimit/1000)
    # dedup
    seen = {}
    for r in all_rows:
        seen[r[0]] = r
    rows = [seen[k] for k in sorted(seen)]
    return rows

results = {}
for base in SYMBOLS:
    sym = find_symbol(base)
    if not sym:
        print(f"{base}: NO SYMBOL"); continue
    rows = fetch_all(sym, TARGET_BARS)
    if len(rows) < 200:
        print(f"{base} ({sym}): only {len(rows)} bars, skip"); continue
    df = pd.DataFrame(rows, columns=["ts","open","high","low","close","volume"])
    df.to_csv(os.path.join(OUT, f"ohlcv_{base}.csv"), index=False)
    t0 = pd.to_datetime(df.ts.iloc[0], unit="ms")
    t1 = pd.to_datetime(df.ts.iloc[-1], unit="ms")
    print(f"{base} ({sym}): {len(df)} bars  {t0} -> {t1}")
    results[base] = {"symbol":sym,"bars":len(df),"start":str(t0),"end":str(t1)}

with open(os.path.join(OUT,"fetch_summary.json"),"w") as f:
    json.dump(results, f, indent=2)
print("DONE", len(results), "symbols")
