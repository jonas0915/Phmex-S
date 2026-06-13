"""Fetch funding-rate history + 8h OHLCV for Phemex USDT perps.

Read-only. Writes JSON to ./data/. No API keys (public endpoints).
"""
import ccxt, time, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

SYMBOLS = [
    "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
    "XRP/USDT:USDT", "DOGE/USDT:USDT", "INJ/USDT:USDT", "ARB/USDT:USDT",
    "AVAX/USDT:USDT", "LINK/USDT:USDT", "APT/USDT:USDT", "OP/USDT:USDT",
    "SUI/USDT:USDT", "TIA/USDT:USDT", "SEI/USDT:USDT", "WLD/USDT:USDT",
    "PEPE/USDT:USDT", "1000PEPE/USDT:USDT",
]

START = ccxt.phemex().parse8601("2025-12-01T00:00:00Z")  # ~6.5 months back

def fetch_funding(ex, sym):
    out = {}
    since = START
    while True:
        try:
            batch = ex.fetch_funding_rate_history(sym, since=since, limit=100)
        except Exception as e:
            print(f"  funding err {sym} @ {since}: {repr(e)[:120]}")
            break
        if not batch:
            break
        for r in batch:
            out[r["timestamp"]] = r["fundingRate"]
        last_ts = batch[-1]["timestamp"]
        if last_ts <= since:
            break
        since = last_ts + 1
        time.sleep(ex.rateLimit / 1000.0)
        if since > ex.milliseconds():
            break
    rows = sorted(([ts, rate] for ts, rate in out.items()), key=lambda x: x[0])
    return rows

def fetch_ohlcv_1h(ex, sym):
    """1h candles (Phemex has no native 8h); resampled to 8h downstream."""
    out = {}
    since = START
    while True:
        try:
            batch = ex.fetch_ohlcv(sym, timeframe="1h", since=since, limit=1000)
        except Exception as e:
            print(f"  ohlcv err {sym} @ {since}: {repr(e)[:120]}")
            break
        if not batch:
            break
        for c in batch:
            out[c[0]] = c
        last_ts = batch[-1][0]
        if last_ts <= since:
            break
        since = last_ts + 1
        time.sleep(ex.rateLimit / 1000.0)
        if since > ex.milliseconds():
            break
    return sorted(out.values(), key=lambda x: x[0])

def main():
    ex = ccxt.phemex({"enableRateLimit": True})
    ex.load_markets()
    avail = [s for s in SYMBOLS if s in ex.markets]
    print("Available:", len(avail), "of", len(SYMBOLS))
    funding_all, ohlcv_all = {}, {}
    for sym in avail:
        print("fetching", sym)
        f = fetch_funding(ex, sym)
        o = fetch_ohlcv_1h(ex, sym)
        funding_all[sym] = f
        ohlcv_all[sym] = o
        print(f"  funding={len(f)} ohlcv8h={len(o)}")
    with open(os.path.join(DATA, "funding.json"), "w") as fh:
        json.dump(funding_all, fh)
    with open(os.path.join(DATA, "ohlcv1h.json"), "w") as fh:
        json.dump(ohlcv_all, fh)
    print("WROTE data/funding.json, data/ohlcv8h.json")

if __name__ == "__main__":
    main()
