"""Fetch data for microstructure/calendar edge search.

Read-only, public endpoints, no API keys.

1. Multi-year 1h OHLCV from binanceus (2021-2026) for majors+alts
   -> used for time-of-day, day-of-week, CME-gap tests
2. Phemex funding-rate history + timestamps (limited span ~195d)
   -> used for funding-settlement microstructure test
   (reuse prior pull if present, else fetch)

Writes JSON to ./data/.
"""
import ccxt, time, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

# binanceus symbols (spot). These have the longest clean public history on a US-accessible venue.
BUS_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "DOGE/USDT", "ADA/USDT", "LINK/USDT",
    "AVAX/USDT", "LTC/USDT",
]

OHLCV_START = ccxt.binanceus().parse8601("2021-01-01T00:00:00Z")


def fetch_ohlcv_1h(ex, sym, start):
    out = {}
    since = start
    limit = 1000
    end = ex.milliseconds()
    while since < end:
        for attempt in range(4):
            try:
                batch = ex.fetch_ohlcv(sym, timeframe="1h", since=since, limit=limit)
                break
            except Exception as e:
                print(f"  ohlcv err {sym} @ {since}: {repr(e)[:100]} (attempt {attempt})")
                time.sleep(2)
                batch = None
        if not batch:
            break
        for r in batch:
            out[r[0]] = r  # ts,o,h,l,c,v
        last_ts = batch[-1][0]
        if last_ts <= since:
            break
        since = last_ts + 1
        time.sleep(ex.rateLimit / 1000.0)
    rows = [out[k] for k in sorted(out.keys())]
    return rows


def main():
    # ---- binanceus 1h OHLCV ----
    ex = ccxt.binanceus({"enableRateLimit": True})
    ex.load_markets()
    ohlcv = {}
    for sym in BUS_SYMBOLS:
        if sym not in ex.markets:
            print(f"SKIP {sym}: not on binanceus")
            continue
        print(f"Fetching binanceus 1h {sym} ...", flush=True)
        rows = fetch_ohlcv_1h(ex, sym, OHLCV_START)
        if rows:
            first = ex.iso8601(rows[0][0])
            last = ex.iso8601(rows[-1][0])
            print(f"  {sym}: {len(rows)} bars  {first} .. {last}", flush=True)
            ohlcv[sym] = rows
        else:
            print(f"  {sym}: NO DATA")
    with open(os.path.join(DATA, "ohlcv1h_binanceus.json"), "w") as f:
        json.dump(ohlcv, f)
    print(f"Wrote ohlcv1h_binanceus.json ({len(ohlcv)} symbols)")


if __name__ == "__main__":
    main()
