#!/usr/bin/env python3
"""Fetch 1m candles per position from Phemex (public OHLCV) and cache to disk.

Window:
- geometry-exit positions (exchange_close / trailing_stop / stop_loss / take_profit):
  entry -> entry + 24h (counterfactual geometries may hold longer than the actual exit)
- software-exit positions (early_exit / adverse_exit / flat_exit / hard_time_exit):
  entry -> actual close + 3 min (sim force-closes at the actual software exit)
"""
import json, os, sys, time
import ccxt

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
GEOM = {"exchange_close", "trailing_stop", "stop_loss", "take_profit"}
HORIZON_S = 24 * 3600

positions = json.load(open(os.path.join(HERE, "positions.json")))
ex = ccxt.phemex({"enableRateLimit": True})

ok = missing = 0
for i, p in enumerate(positions):
    out = os.path.join(CACHE, f"{i}.json")
    if os.path.exists(out):
        ok += 1
        continue
    start = int(p["opened_at"]) - 60
    if p["exit_reason"] in GEOM:
        end = int(p["opened_at"]) + HORIZON_S
    else:
        end = int(p["closed_at"]) + 180
    candles = []
    since = start * 1000
    try:
        while since < end * 1000:
            batch = ex.fetch_ohlcv(p["symbol"], "1m", since=since, limit=1000)
            if not batch:
                break
            candles.extend(batch)
            nxt = batch[-1][0] + 60000
            if nxt <= since:
                break
            since = nxt
            if len(batch) < 2:
                break
        candles = [c for c in candles if start * 1000 <= c[0] <= end * 1000]
        # dedupe on ts
        seen, ded = set(), []
        for c in candles:
            if c[0] not in seen:
                seen.add(c[0]); ded.append(c)
        ded.sort(key=lambda c: c[0])
        json.dump(ded, open(out, "w"))
        ok += 1
        if i % 20 == 0:
            print(f"[{i}/{len(positions)}] {p['symbol']} candles={len(ded)}", flush=True)
    except Exception as e:
        print(f"[{i}] {p['symbol']} FAILED: {e}", flush=True)
        missing += 1

print(f"done ok={ok} failed={missing}")
