#!/usr/bin/env python3
"""Fetch DAILY + 4h OHLCV from public binanceus via ccxt, 2021-2026, broad liquid set."""
import ccxt, time, os, sys
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT, exist_ok=True)

SYMBOLS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","LTC",
           "DOT","ATOM","UNI","BCH","ETC","XLM","ALGO","FIL","AAVE","MATIC",
           "NEAR","APE","MANA","SAND","CRV","COMP","MKR","SUSHI"]
QUOTE = "USDT"
SINCE = ccxt.binanceus().parse8601("2021-01-01T00:00:00Z")

def fetch_all(ex, symbol, timeframe, since):
    out = []
    ms_per = ex.parse_timeframe(timeframe) * 1000
    cur = since
    now = ex.milliseconds()
    while cur < now:
        try:
            batch = ex.fetch_ohlcv(symbol, timeframe, since=cur, limit=1000)
        except Exception as e:
            print(f"   retry {symbol} {timeframe}: {e}", file=sys.stderr); time.sleep(2); continue
        if not batch:
            break
        out += batch
        last = batch[-1][0]
        if last <= cur:
            break
        cur = last + ms_per
        time.sleep(ex.rateLimit/1000.0)
        if len(batch) < 1000:
            break
    return out

def main():
    ex = ccxt.binanceus({"enableRateLimit": True})
    ex.load_markets()
    have = {}
    for tf in ["1d","4h"]:
        for s in SYMBOLS:
            sym = f"{s}/{QUOTE}"
            if sym not in ex.markets:
                print(f"SKIP {sym} (not on binanceus)"); continue
            fn = os.path.join(OUT, f"{s}_{tf}.csv")
            if os.path.exists(fn):
                print(f"cached {sym} {tf}"); have.setdefault(tf,[]).append(s); continue
            print(f"fetch {sym} {tf} ...", flush=True)
            data = fetch_all(ex, sym, tf, SINCE)
            if not data:
                print(f"   EMPTY {sym} {tf}"); continue
            df = pd.DataFrame(data, columns=["ts","open","high","low","close","volume"])
            df = df.drop_duplicates("ts").sort_values("ts")
            df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
            df.to_csv(fn, index=False)
            print(f"   {sym} {tf}: {len(df)} rows {df['dt'].min()} -> {df['dt'].max()}")
            have.setdefault(tf,[]).append(s)
    print("\nSUMMARY available symbols:")
    for tf,lst in have.items():
        print(f"  {tf}: {len(lst)} -> {sorted(lst)}")

if __name__ == "__main__":
    main()
