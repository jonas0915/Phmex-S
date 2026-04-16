#!/usr/bin/env python3
"""One-shot: backfill `exit_reason` from `reason` on closed_trades."""
import json, os, sys

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trading_state.json")

def backfill(path):
    with open(path, "r") as f:
        state = json.load(f)
    closed = state.get("closed_trades", [])
    n = 0
    for t in closed:
        er = t.get("exit_reason")
        if not er:
            r = t.get("reason")
            if r:
                t["exit_reason"] = r
                n += 1
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)
    # distribution
    dist = {}
    ae = 0
    for t in closed:
        er = t.get("exit_reason") or "MISSING"
        dist[er] = dist.get(er, 0) + 1
        if er and "adverse" in str(er).lower():
            ae += 1
    total = len(closed)
    ae_rate = (ae / total * 100) if total else 0
    print(f"{path}: backfilled {n} of {total} closed. dist={dist} ae_rate={ae_rate:.1f}%")

def main():
    paths = sys.argv[1:] or [DEFAULT_PATH]
    for p in paths:
        backfill(p)

if __name__ == "__main__":
    main()
