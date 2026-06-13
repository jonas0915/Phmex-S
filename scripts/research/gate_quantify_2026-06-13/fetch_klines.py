#!/usr/bin/env python3
"""Cache 5m OHLCV (60d) for every symbol appearing in the gate-quantify populations.
Continuous klines -> reliable forward-price lookup (flow_capture is too sparse).
Timestamps from fetch_history are UTC-naive (pd.to_datetime unit='ms')."""
import os, re, sys, json
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
from fetch_history import fetch_ohlcv

OUT = os.path.join(ROOT, "scripts/research/gate_quantify_2026-06-13/klines5m")
os.makedirs(OUT, exist_ok=True)
EDT = ZoneInfo("America/New_York")
ANSI = re.compile(r"\x1b\[[0-9;]*m")

def universe():
    syms = set()
    d = json.load(open("trading_state.json"))
    for t in d.get("closed_trades", []) or []:
        if t.get("strategy") == "htf_l2_anticipation":
            es = t.get("entry_snapshot") or {}
            if es.get("ob"):
                syms.add(es["symbol"])
    for line in open("logs/gotAway.jsonl"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("strategy") == "htf_l2_anticipation":
            syms.add(r["symbol"])
    TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    RX = re.compile(r"\[(?:TIME BLOCK|OB GATE|TAPE GATE)\] (\S+/USDT:USDT) ")
    for fn in os.listdir("logs"):
        if not fn.startswith("bot.log"):
            continue
        for raw in open("logs/" + fn, errors="ignore"):
            line = ANSI.sub("", raw)
            if not TS.match(line):
                continue
            g = RX.search(line)
            if g and ("blocked" in line or "skipped" in line):
                syms.add(g.group(1))
    return sorted(s for s in syms if s.endswith("/USDT:USDT"))

def main():
    syms = universe()
    print(f"{len(syms)} symbols: {[s.replace('/USDT:USDT','') for s in syms]}", flush=True)
    ok = fail = 0
    for i, sym in enumerate(syms, 1):
        safe = sym.replace("/", "_").replace(":", "_")
        path = os.path.join(OUT, f"{safe}.csv")
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            print(f"[{i}/{len(syms)}] {sym} cached, skip", flush=True)
            ok += 1
            continue
        try:
            df = fetch_ohlcv(sym, "5m", days=60)
            if df is None or len(df) == 0:
                print(f"[{i}/{len(syms)}] {sym} EMPTY", flush=True)
                fail += 1
                continue
            df.to_csv(path, index=False)
            ok += 1
        except Exception as e:
            print(f"[{i}/{len(syms)}] {sym} FAILED: {e}", flush=True)
            fail += 1
    print(f"DONE: {ok} ok, {fail} fail -> {OUT}", flush=True)

if __name__ == "__main__":
    main()
