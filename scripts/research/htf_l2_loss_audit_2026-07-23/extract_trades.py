#!/usr/bin/env python3
"""Extract all htf_l2_anticipation LIVE trades 7/20 8:00 PM PT -> now, both books.
Read-only. Prints full records as JSON lines for audit."""
import json, datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = "/Users/jonaspenaso/Desktop/Phmex-S"
START = datetime.datetime(2026, 7, 20, 20, 0, 0, tzinfo=PT).timestamp()
UNHALT = datetime.datetime(2026, 7, 21, 21, 25, 0, tzinfo=PT).timestamp()

def pt(ts):
    return datetime.datetime.fromtimestamp(ts, PT).strftime("%a %m-%d %I:%M:%S %p")

books = [
    ("SLOT(HTF_L2.json)", "trading_state_HTF_L2.json", "slot"),
    ("SLOT(HTF_L2_PAPER.json)", "trading_state_HTF_L2_PAPER.json", "slot"),
    ("MAIN", "trading_state.json", "main"),
]
tot = {}
for label, fname, kind in books:
    try:
        data = json.load(open(f"{ROOT}/{fname}"))
    except FileNotFoundError:
        print(f"### {label}: FILE MISSING")
        continue
    print(f"### {label} closed_trades={len(data.get('closed_trades', []))}")
    for i, t in enumerate(data.get("closed_trades", [])):
        ca = t.get("closed_at", 0)
        if ca < START:
            continue
        if kind == "slot":
            if t.get("mode") != "live":
                continue
        else:
            if t.get("strategy") != "htf_l2_anticipation":
                continue
            if t.get("opened_at", ca) < UNHALT and ca < UNHALT:
                continue
        tot.setdefault(label, [0, 0.0])
        tot[label][0] += 1
        tot[label][1] += t.get("net_pnl", 0.0)
        print(f"[{label} idx={i}] opened={pt(t.get('opened_at',0))} closed={pt(ca)}")
        print(json.dumps(t, default=str))
    # open positions too
    for sym, p in (data.get("positions") or {}).items():
        if isinstance(p, dict):
            strat = p.get("strategy", "")
            if kind == "main" and strat != "htf_l2_anticipation":
                continue
            print(f"[{label} OPEN] {sym}: {json.dumps(p, default=str)[:400]}")
print("--- totals ---")
for k, (n, s) in tot.items():
    print(f"{k}: {n} trades net={s:+.3f}")
