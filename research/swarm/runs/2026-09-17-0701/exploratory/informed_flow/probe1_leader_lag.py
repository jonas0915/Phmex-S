"""EXPLORATORY probe (not the screen; numbers are not evidence).
Lens informed_flow. Question: after a large K-hour move in a leader (ETH/BTC), do laggard alts
that have NOT yet moved drift in the leader's direction over the next H hours on Phemex?
Dataset mr_edge, 1h, era=train only."""
import json, sys
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld
from research.swarm.lib import bootstrap_ci as bc

OUT = "research/swarm/runs/2026-09-17-0701/exploratory/informed_flow/probe1_out.json"
syms = ld.list_symbols("mr_edge")
frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="mr_edge") for s in syms}
res = {}
for leader in ("ETH", "BTC"):
    L = frames[leader]["close"]
    for K in (4, 8):
        lr = np.log(L).diff(K)
        vol = np.log(L).diff().rolling(24*14).std() * np.sqrt(K)
        z = lr / vol
        for thr in (2.0, 2.5):
            for H in (4, 8, 12, 24):
                fwd_all, catch_all = [], []
                for s, df in frames.items():
                    if s in ("ETH", "BTC"):
                        continue
                    c = np.log(df["close"]).reindex(L.index)
                    ar = c.diff(K)
                    fwd = c.shift(-H) - c   # forward return (probe only; NOT a signal)
                    zz = z.reindex(c.index)
                    # laggard: alt moved less than half of the leader's move (in log terms) in same window
                    lag_mask = (zz.abs() >= thr) & (ar.abs() < 0.5 * lr.reindex(c.index).abs())
                    sgn = np.sign(zz)
                    ev = (fwd * sgn)[lag_mask].dropna()
                    fwd_all.append(ev)
                ev = pd.concat(fwd_all) if fwd_all else pd.Series(dtype=float)
                if len(ev) >= 10:
                    lo, hi = bc.mean_ci(ev.to_numpy() * 1e4)
                    res[f"{leader}_K{K}_thr{thr}_H{H}"] = {"n": int(len(ev)), "mean_bps": float(ev.mean()*1e4),
                                                            "ci95": [float(lo), float(hi)], "hit": float((ev>0).mean())}
json.dump(res, open(OUT, "w"), indent=1)
for k, v in res.items():
    print(k, v)
