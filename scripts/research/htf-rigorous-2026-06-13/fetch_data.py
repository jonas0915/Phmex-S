#!/usr/bin/env python3
"""Fetch max daily + 4h OHLCV via public ccxt. binanceus primary (geo-OK,
full Binance-quality history to 2021), gateio/htx fallback. READ-ONLY, no keys.

Validates forward pagination: a series is only saved if it actually advances
past `since` (guards against exchanges that ignore `since` like phemex)."""
import ccxt, time, os
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT, exist_ok=True)

SYMBOLS = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","LTC","DOT","MATIC","ATOM","UNI","BCH"]
TFS = ["1d","4h"]
SINCE = "2021-01-01T00:00:00Z"
PREFS = ["binanceus","gateio","htx"]

def make_ex(name):
    ex = getattr(ccxt, name)({"enableRateLimit": True})
    ex.load_markets()
    return ex

def fetch_all(ex, symbol, tf, since_ms, limit=1000):
    out, cursor = [], since_ms
    tf_ms = ex.parse_timeframe(tf) * 1000
    now = ex.milliseconds()
    while cursor < now:
        try:
            batch = ex.fetch_ohlcv(symbol, tf, since=cursor, limit=limit)
        except Exception as e:
            time.sleep(2)
            try:
                batch = ex.fetch_ohlcv(symbol, tf, since=cursor, limit=limit)
            except Exception:
                break
        if not batch:
            break
        out += batch
        last = batch[-1][0]
        if last < cursor:  # exchange ignored since / went backwards
            break
        if last == cursor and len(batch) == 1:
            break
        cursor = last + tf_ms
        time.sleep(ex.rateLimit/1000)
    return out

def main():
    exs = {}
    for n in PREFS:
        try:
            exs[n] = make_ex(n); print(f"loaded {n} ({len(exs[n].markets)} mkts)")
        except Exception as e:
            print(f"FAIL load {n}: {str(e)[:80]}")
    since = ccxt.binanceus().parse8601(SINCE)
    results = {}
    for tf in TFS:
        for base in SYMBOLS:
            done = False
            for exname, ex in exs.items():
                sym = None
                for c in [f"{base}/USDT", f"{base}/USD"]:
                    if c in ex.markets: sym = c; break
                if not sym: continue
                data = fetch_all(ex, sym, tf, since)
                if not data or len(data) < 100: continue
                df = pd.DataFrame(data, columns=["ts","open","high","low","close","volume"])
                df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
                df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
                # require it actually spans >1 year for daily, >6mo for 4h
                span_days = (df["dt"].iloc[-1] - df["dt"].iloc[0]).days
                need = 300 if tf == "1d" else 120
                if span_days < need:
                    print(f"  {base} {tf} <-{exname}: only {span_days}d span, skip")
                    continue
                path = os.path.join(OUT, f"{base}_{tf}.csv")
                df.to_csv(path, index=False)
                print(f"{base} {tf} <- {exname} {sym}: {len(df)} rows {df['dt'].iloc[0].date()}..{df['dt'].iloc[-1].date()} ({span_days}d)")
                results[f"{base}_{tf}"] = (exname, len(df), str(df['dt'].iloc[0].date()), str(df['dt'].iloc[-1].date()), span_days)
                done = True
                break
            if not done:
                print(f"{base} {tf}: NO DATA")
    with open(os.path.join(OUT, "_manifest.txt"), "w") as f:
        for k,v in sorted(results.items()):
            f.write(f"{k}\t{v[0]}\trows={v[1]}\t{v[2]}..{v[3]}\t{v[4]}d\n")
    print("DONE", len(results), "series")

if __name__ == "__main__":
    main()
