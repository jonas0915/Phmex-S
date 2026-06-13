#!/usr/bin/env python3
"""Fetch (a) crashed/delisted coins from gateio for survivorship test, and
(b) a WIDER survivor universe from binanceus for universe-expansion test.
READ-ONLY public data. Writes <SYM>_1d.csv into data/ (same schema as engine)."""
import ccxt, time, os, sys
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "data")
SINCE = "2021-01-01T00:00:00Z"

# crashed/failed tokens (gateio keeps history through the crash)
CRASHED = ["LUNA","FTT","CEL","WAVES","RAY","LUNC","SRM"]
# wider binanceus survivor universe (smaller/weaker survivors beyond the 13)
WIDER = ["SUSHI","YFI","COMP","MKR","AAVE","SNX","CRV","1INCH","GRT","SAND",
         "MANA","APE","GALA","CHZ","ENJ","BAT","ZRX","EOS","XLM","TRX","ETC",
         "FIL","ICP","NEAR","ALGO","VET","THETA","FTM","XTZ","EGLD","FLOW","KSM"]

def fetch_all(ex, symbol, tf, since_ms, limit=1000):
    out, cursor = [], since_ms
    tf_ms = ex.parse_timeframe(tf) * 1000
    now = ex.milliseconds()
    stall = 0
    while cursor < now:
        try:
            batch = ex.fetch_ohlcv(symbol, tf, since=cursor, limit=limit)
        except Exception:
            time.sleep(2)
            try: batch = ex.fetch_ohlcv(symbol, tf, since=cursor, limit=limit)
            except Exception: break
        if not batch: break
        out += batch
        last = batch[-1][0]
        if last < cursor: break
        if last == cursor:
            stall += 1
            if stall > 2: break
            cursor = last + tf_ms
        else:
            stall = 0
            cursor = last + tf_ms
        time.sleep(ex.rateLimit/1000)
    return out

def save(base, data, tag):
    if not data or len(data) < 50:
        print(f"  {base}: only {len(data) if data else 0} rows, SKIP"); return None
    df = pd.DataFrame(data, columns=["ts","open","high","low","close","volume"])
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    path = os.path.join(OUT, f"{base}_1d.csv")
    df.to_csv(path, index=False)
    print(f"  {base} <- {tag}: {len(df)} rows {df['dt'].iloc[0].date()}..{df['dt'].iloc[-1].date()} "
          f"lastclose={df['close'].iloc[-1]:.6g}")
    return (len(df), str(df['dt'].iloc[0].date()), str(df['dt'].iloc[-1].date()))

def main():
    mode = sys.argv[1] if len(sys.argv)>1 else "all"
    bu = ccxt.binanceus({"enableRateLimit":True}); bu.load_markets()
    ge = ccxt.gateio({"enableRateLimit":True}); ge.load_markets()
    since = bu.parse8601(SINCE)

    if mode in ("all","wider"):
        print("=== WIDER survivor universe (binanceus) ===")
        for base in WIDER:
            sym=None
            for q in ["/USDT","/USD"]:
                if base+q in bu.markets: sym=base+q; break
            if not sym: print(f"  {base}: not on binanceus"); continue
            save(base, fetch_all(bu, sym, "1d", since), f"binanceus {sym}")

    if mode in ("all","crashed"):
        print("=== CRASHED/failed tokens (gateio) ===")
        for base in CRASHED:
            sym=None
            for q in ["/USDT","/USD"]:
                if base+q in ge.markets: sym=base+q; break
            if not sym: print(f"  {base}: not on gateio"); continue
            save("X"+base if base in ("LUNA",) else base, fetch_all(ge, sym, "1d", since), f"gateio {sym}")
    print("DONE")

if __name__=="__main__":
    main()
