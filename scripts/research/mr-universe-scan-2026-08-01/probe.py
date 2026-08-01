#!/usr/bin/env python3
"""Probe: (a) top-30 USDT perps by 24h turnover (>=$3M), (b) 5m history depth on Phemex.
Read-only, no bot files touched. Writes universe.json to this dir."""
import json
import os
import time
from datetime import datetime, timezone

import ccxt

HERE = os.path.dirname(os.path.abspath(__file__))

ex = ccxt.phemex({"enableRateLimit": True})
ex.load_markets()

# --- universe: top 30 USDT-settled linear perps by current 24h turnover, all >= $3M ---
swap_syms = [s for s, m in ex.markets.items()
             if m.get("swap") and m.get("linear") and m.get("settle") == "USDT"
             and m.get("active", True)]
tickers = ex.fetch_tickers(swap_syms)
rows = []
for sym, t in tickers.items():
    m = ex.markets.get(sym)
    if not m or not m.get("swap") or not m.get("linear") or m.get("settle") != "USDT":
        continue
    if not m.get("active", True):
        continue
    qv = t.get("quoteVolume")  # 24h turnover in USDT
    if qv is None:
        continue
    rows.append({"symbol": sym, "turnover_24h_usdt": float(qv)})

rows.sort(key=lambda r: -r["turnover_24h_usdt"])
top30 = [r for r in rows if r["turnover_24h_usdt"] >= 3_000_000][:30]
print(f"eligible >=3M: {len([r for r in rows if r['turnover_24h_usdt'] >= 3_000_000])}, taking top 30")
for r in top30:
    print(f"  {r['symbol']:<24} ${r['turnover_24h_usdt']:,.0f}")

with open(os.path.join(HERE, "universe.json"), "w") as fh:
    json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(),
               "rule": "top 30 USDT linear perps by current 24h quoteVolume, all >= $3M",
               "pairs": top30}, fh, indent=1)

# --- depth probe: how far back does 5m data go for a few pairs? ---
now_ms = ex.milliseconds()
for probe_sym in [top30[0]["symbol"], top30[min(14, len(top30)-1)]["symbol"], top30[-1]["symbol"]]:
    since = now_ms - 400 * 86400 * 1000
    batch = ex.fetch_ohlcv(probe_sym, "5m", since=since, limit=1000)
    if batch:
        first = datetime.fromtimestamp(batch[0][0] / 1000, tz=timezone.utc)
        print(f"depth {probe_sym}: since=now-400d -> first bar {first.isoformat()} ({(now_ms - batch[0][0]) / 86400000:.1f}d back), n={len(batch)}")
    else:
        print(f"depth {probe_sym}: since=now-400d -> EMPTY batch")
    time.sleep(0.5)
