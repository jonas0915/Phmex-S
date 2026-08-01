#!/usr/bin/env python3
"""Fetch daily OHLCV context for the stop days (cached). Read-only market data."""
import json, os, time
import ccxt

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_ohlcv_cache.json")

# (symbol, UTC day of interest) — stop days from fuse_replay.py (PT day of stop close;
# we fetch a 3-day UTC window around it so both overlapping UTC days are visible)
TARGETS = [
    ("ZEC/USDT:USDT", "2026-05-19"),
    ("WLD/USDT:USDT", "2026-05-23"),
    ("LTC/USDT:USDT", "2026-06-11"),
    ("AVAX/USDT:USDT", "2026-06-11"),
    ("XLM/USDT:USDT", "2026-06-24"),
    ("SOL/USDT:USDT", "2026-07-16"),
    ("INJ/USDT:USDT", "2026-07-17"),
    ("XRP/USDT:USDT", "2026-07-22"),
]

def main():
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    ex = ccxt.phemex({"enableRateLimit": True})
    for sym, day in TARGETS:
        key = f"{sym}|{day}"
        if key in cache:
            continue
        since = ex.parse8601(f"{day}T00:00:00Z") - 86400_000
        rows = ex.fetch_ohlcv(sym, "1d", since=since, limit=4)
        cache[key] = rows
        time.sleep(0.3)
    with open(CACHE, "w") as f:
        json.dump(cache, f, indent=1)
    for sym, day in TARGETS:
        rows = cache[f"{sym}|{day}"]
        print(f"\n{sym} around {day} (UTC daily candles):")
        for ts, o, h, l, c, v in rows:
            d = time.strftime("%Y-%m-%d", time.gmtime(ts / 1000))
            rng = (h - l) / o * 100
            chg = (c - o) / o * 100
            print(f"  {d}  O {o:<10g} H {h:<10g} L {l:<10g} C {c:<10g} "
                  f"chg {chg:+6.2f}%  range {rng:5.2f}%")

if __name__ == "__main__":
    main()
