#!/usr/bin/env python3
"""Fetch BTC/USDT:USDT (Phemex USDT perp — the market the slot would trade)
daily OHLCV as far back as Phemex serves, save in the same CSV schema as the
7/13 cached data (ts,open,high,low,close,volume,dt). Public endpoints only."""
import ccxt, csv, os, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data_phemex")
os.makedirs(OUT, exist_ok=True)

ex = ccxt.phemex({"enableRateLimit": True})
ex.load_markets()
SYM = "BTC/USDT:USDT"
tf = "1d"
since = ex.parse8601("2018-01-01T00:00:00Z")
rows = []
while True:
    batch = ex.fetch_ohlcv(SYM, tf, since=since, limit=1000)
    if not batch:
        break
    rows.extend(batch)
    if len(batch) < 2:
        break
    nxt = batch[-1][0] + 86400_000
    if nxt <= since:
        break
    since = nxt
    if batch[-1][0] > ex.milliseconds():
        break
    time.sleep(ex.rateLimit/1000)

# dedupe, sort, drop the (possibly partial) current UTC day
seen = {}
for r in rows:
    seen[r[0]] = r
rows = [seen[k] for k in sorted(seen)]
today_utc = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                microsecond=0).timestamp()*1000)
rows = [r for r in rows if r[0] < today_utc]

path = os.path.join(OUT, "BTC_1d.csv")
with open(path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["ts", "open", "high", "low", "close", "volume", "dt"])
    for ts, o, h, l, c, v in rows:
        dt = datetime.fromtimestamp(ts/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00")
        w.writerow([ts, o, h, l, c, v, dt])
print(f"wrote {len(rows)} rows -> {path}")
print("first:", rows[0][0], datetime.fromtimestamp(rows[0][0]/1000, tz=timezone.utc))
print("last: ", rows[-1][0], datetime.fromtimestamp(rows[-1][0]/1000, tz=timezone.utc))
