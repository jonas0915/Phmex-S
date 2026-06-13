#!/usr/bin/env python3
"""Independent re-fetch: binanceus daily OHLCV 2021-01-01 -> now.
Includes survivor majors PLUS some that struggled (MATIC, APE, SAND, MANA, ALGO, etc.)
and the coins our live bot actually trades where available on binanceus."""
import ccxt, time, os, sys
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT, exist_ok=True)

# Liquid majors + intentionally-included laggards (relative-value, so we want some that DUMPED)
SYMBOLS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","LTC",
           "DOT","ATOM","UNI","BCH","ETC","XLM","ALGO","FIL","AAVE",
           "NEAR","APE","MANA","SAND","CRV","COMP","MKR",
           # coins our live bot trades that may exist on binanceus:
           "INJ","ARB","OP","TIA","RENDER","RNDR","WLD","SUI","FET","SHIB","PEPE"]
QUOTE = "USDT"
SINCE = ccxt.binanceus().parse8601("2021-01-01T00:00:00Z")

def fetch_all(ex, symbol, since):
    out=[]; ms=ex.parse_timeframe("1d")*1000; cur=since; now=ex.milliseconds()
    while cur < now:
        try:
            b=ex.fetch_ohlcv(symbol,"1d",since=cur,limit=1000)
        except Exception as e:
            print("retry",symbol,e,file=sys.stderr); time.sleep(2); continue
        if not b: break
        out+=b; last=b[-1][0]
        if last<=cur: break
        cur=last+ms; time.sleep(ex.rateLimit/1000.0)
        if len(b)<1000: break
    return out

def main():
    ex=ccxt.binanceus({"enableRateLimit":True}); ex.load_markets()
    have=[]
    for s in SYMBOLS:
        sym=f"{s}/{QUOTE}"
        if sym not in ex.markets:
            print(f"SKIP {sym} (not on binanceus)"); continue
        fn=os.path.join(OUT,f"{s}.csv")
        if os.path.exists(fn): print("cached",sym); have.append(s); continue
        print("fetch",sym,"...",flush=True)
        data=fetch_all(ex,sym,SINCE)
        if not data: print("EMPTY",sym); continue
        df=pd.DataFrame(data,columns=["ts","o","h","l","close","vol"]).drop_duplicates("ts").sort_values("ts")
        df["dt"]=pd.to_datetime(df["ts"],unit="ms",utc=True)
        df.to_csv(fn,index=False)
        print(f"  {sym}: {len(df)} rows {df.dt.min().date()} -> {df.dt.max().date()}")
        have.append(s)
    print("\nAVAILABLE:",len(have),sorted(have))

if __name__=="__main__":
    main()
