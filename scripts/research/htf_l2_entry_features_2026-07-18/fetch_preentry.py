#!/usr/bin/env python3
"""Fetch PRE-ENTRY candles per htf_l2 position (public Phemex OHLCV, ccxt).

Reuses the geometry agent's positions.json (read-only). Its cache is 1m from
entry-60s onward -> unusable for pre-entry indicators, so we fetch our own:

Per position i:
  cache/{i}_5m.json : 5m candles from (floor(entry/300) - 505)*300 up to entry
                      (>=500 closed bars, mirroring CANDLE_LOOKBACK=500)
  cache/{i}_1m.json : 1m candles inside the entry's own 5m window
                      (to rebuild the FORMING 5m bar the bot evaluated on)

Partial-bar contract (fidelity note): bot evaluates df.iloc[-1] = forming bar,
close = live price at signal. opened_at == entry_snapshot.ts (+-1s, verified),
so we reconstruct the forming bar at t=opened_at from closed 1m bars + entry px.
"""
import json, os
import ccxt

HERE = os.path.dirname(os.path.abspath(__file__))
GEOM = os.path.join(HERE, "..", "htf_l2_geometry_2026-07-18")
CACHE = os.path.join(HERE, "cache")

positions = json.load(open(os.path.join(GEOM, "positions.json")))
ex = ccxt.phemex({"enableRateLimit": True})

ok = failed = 0
for i, p in enumerate(positions):
    out5 = os.path.join(CACHE, f"{i}_5m.json")
    out1 = os.path.join(CACHE, f"{i}_1m.json")
    if os.path.exists(out5) and os.path.exists(out1):
        ok += 1
        continue
    entry_ts = int(p["opened_at"])
    bar5 = (entry_ts // 300) * 300          # start of forming 5m bar
    since5 = (bar5 - 505 * 300) * 1000
    try:
        c5 = ex.fetch_ohlcv(p["symbol"], "5m", since=since5, limit=1000)
        c5 = [c for c in c5 if c[0] < entry_ts * 1000]  # nothing at/after entry instant
        c1 = ex.fetch_ohlcv(p["symbol"], "1m", since=bar5 * 1000, limit=10)
        c1 = [c for c in c1 if bar5 * 1000 <= c[0] and c[0] + 60000 <= entry_ts * 1000]  # closed 1m bars inside forming window
        json.dump(c5, open(out5, "w"))
        json.dump(c1, open(out1, "w"))
        ok += 1
        if i % 20 == 0:
            print(f"[{i}/{len(positions)}] {p['symbol']} 5m={len(c5)} 1m={len(c1)}", flush=True)
    except Exception as e:
        print(f"[{i}] {p['symbol']} FAILED: {e}", flush=True)
        failed += 1

print(f"done ok={ok} failed={failed}")
