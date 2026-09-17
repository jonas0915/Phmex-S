"""EXPLORATORY probe 3 (not the screen). Slow-diffusion version at multi-day horizon on long_1h
train only (2025-06-27 -> ~2026-04-24; no mr_edge data used). After a leader (ETH/BTC) K-hour move
of >= thr sigma, do laggard alts (moved < half) drift with the leader over the next H hours?
De-overlapped episodes (first bar the z crosses). """
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld
from research.swarm.lib import bootstrap_ci as bc
OUT = "research/swarm/runs/2026-09-17-0701/exploratory/informed_flow/probe3_out.json"
syms = ld.list_symbols("long_1h")
frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in syms}
res = {}
def ci(ev):
    ev = ev.dropna()
    if len(ev) < 8: return None
    lo, hi = bc.mean_ci(ev.to_numpy()*1e4)
    return {"n": int(len(ev)), "mean_bps": float(ev.mean()*1e4), "ci95": [float(lo), float(hi)], "hit": float((ev>0).mean())}
for leader in ("ETH","BTC"):
    L = np.log(frames[leader]["close"])
    for K in (24, 72):
        lr = L.diff(K); vol = L.diff().rolling(24*30).std()*np.sqrt(K); z = lr/vol
        for thr in (1.5, 2.0):
            hot = z.abs() >= thr; first = hot & ~hot.shift(1, fill_value=False); sgn = np.sign(z)
            res[f"{leader}_K{K}_thr{thr}_episodes"] = int(first.sum())
            for H in (24, 48, 72):
                res[f"{leader}_K{K}_thr{thr}_own_H{H}"] = ci(((L.shift(-H)-L)*sgn)[first])
                lag_ev, fol_ev = [], []
                for s, df in frames.items():
                    if s in ("ETH","BTC"): continue
                    c = np.log(df["close"]).reindex(L.index); ar = c.diff(K); fwd = c.shift(-H)-c
                    lag_ev.append((fwd*sgn)[first & (ar.abs() < 0.5*lr.abs())])
                    fol_ev.append((fwd*sgn)[first & (ar*sgn >= 0.5*lr.abs())])
                res[f"{leader}_K{K}_thr{thr}_laggard_H{H}"] = ci(pd.concat(lag_ev))
                res[f"{leader}_K{K}_thr{thr}_follower_H{H}"] = ci(pd.concat(fol_ev))
json.dump(res, open(OUT,"w"), indent=1)
for k,v in res.items(): print(k, v)
