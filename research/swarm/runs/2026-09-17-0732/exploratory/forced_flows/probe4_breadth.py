"""EXPLORATORY ONLY. Split probe2 trades (A, tp300, hold24/36) by how many symbols fired
on the same entry day (breadth = number of trades entered that calendar day across the 18
symbols). Tests whether the edge lives in market-wide cascade days vs idiosyncratic ones."""
import json, pandas as pd, numpy as np
from research.swarm.lib import bootstrap_ci as bc
OUT = "research/swarm/runs/2026-09-17-0732/exploratory/forced_flows"
res = {}
for key in ["A_tp300_hold24", "A_tp300_hold36"]:
    T = pd.read_csv(f"{OUT}/probe2_trades_{key}.csv")
    T["day"] = pd.to_datetime(T["entry_ts"]).dt.date
    T["breadth"] = T.groupby("day")["net_bps"].transform("size")
    T["bucket"] = pd.cut(T["breadth"], [0, 1, 3, 7, 100], labels=["1", "2-3", "4-7", "8+"])
    out = {}
    for b, g in T.groupby("bucket", observed=True):
        x = g["net_bps"].to_numpy()
        out[str(b)] = {"n": int(len(x)), "days": int(g["day"].nunique()), "mean": float(x.mean()), "ci95": list(bc.mean_ci(x)) if len(x) > 1 else None, "wr": float((x > 0).mean())}
    res[key] = out
    print(key, json.dumps(out))
json.dump(res, open(f"{OUT}/probe4_breadth.json", "w"), indent=2)
