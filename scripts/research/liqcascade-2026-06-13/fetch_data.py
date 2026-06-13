#!/usr/bin/env python3
"""Fetch multi-year OHLCV from binanceus public API via ccxt. No keys.
5m AND 1h for a basket of majors+alts, back to listing (target 2021-2026)."""
import ccxt, time, json, os, sys
import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(OUT, "data")
os.makedirs(DATA, exist_ok=True)

SYMBOLS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","LTC","DOT","ATOM","MATIC","UNI","BCH"]
TFS = {"1h": 3600*1000, "5m": 300*1000}
# go back to Jan 2021; binanceus listed many of these mid-2021+
SINCE_MS = ccxt.binanceus().parse8601("2021-01-01T00:00:00Z")

ex = ccxt.binanceus({"enableRateLimit": True})
ex.load_markets()

def find_symbol(base):
    # prefer USDT spot (binanceus has no perps; spot OHLCV is fine for this study)
    cands = []
    for s, m in ex.markets.items():
        if m.get("base")==base and m.get("quote")=="USDT" and m.get("spot"):
            cands.append(s)
    if not cands:
        for s, m in ex.markets.items():
            if m.get("base")==base and m.get("quote")=="USD":
                cands.append(s)
    return cands[0] if cands else None

def fetch_all(symbol, tf, tf_ms):
    now = ex.milliseconds()
    cursor = SINCE_MS
    all_rows = []
    while cursor < now:
        try:
            batch = ex.fetch_ohlcv(symbol, tf, since=cursor, limit=1000)
        except Exception as e:
            print(f"   err {e}; retry"); time.sleep(2); continue
        if not batch:
            break
        all_rows += batch
        last = batch[-1][0]
        if last <= cursor:
            break
        cursor = last + tf_ms
        if len(batch) < 1000:
            break
        time.sleep(ex.rateLimit/1000)
    seen = {}
    for r in all_rows:
        seen[r[0]] = r
    return [seen[k] for k in sorted(seen)]

summary = {}
for base in SYMBOLS:
    sym = find_symbol(base)
    if not sym:
        print(f"{base}: NO SYMBOL"); continue
    summary[base] = {"symbol": sym}
    for tf, tf_ms in TFS.items():
        rows = fetch_all(sym, tf, tf_ms)
        if len(rows) < 500:
            print(f"{base} {tf} ({sym}): only {len(rows)} bars, skip"); continue
        df = pd.DataFrame(rows, columns=["ts","open","high","low","close","volume"])
        path = os.path.join(DATA, f"{base}_{tf}.csv")
        df.to_csv(path, index=False)
        t0 = pd.to_datetime(df.ts.iloc[0], unit="ms"); t1 = pd.to_datetime(df.ts.iloc[-1], unit="ms")
        print(f"{base} {tf} ({sym}): {len(df)} bars  {t0} -> {t1}", flush=True)
        summary[base][tf] = {"bars":len(df),"start":str(t0),"end":str(t1)}

with open(os.path.join(OUT,"fetch_summary.json"),"w") as f:
    json.dump(summary, f, indent=2)
print("DONE", len(summary), "symbols")
