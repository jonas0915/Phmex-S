"""EXPLORATORY probe 2 (not the screen). Decompose probe1's negative laggard drift:
(a) leader's own forward return after its own z-spike (de-overlapped: first bar z crosses thr),
(b) alts that DID follow (non-laggards) vs laggards, de-overlapped events only,
(c) sign split: leader up vs leader down.
mr_edge 1h train only."""
import json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld
from research.swarm.lib import bootstrap_ci as bc

OUT = "research/swarm/runs/2026-09-17-0701/exploratory/informed_flow/probe2_out.json"
syms = ld.list_symbols("mr_edge")
frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="mr_edge") for s in syms}
K, thr = 4, 2.0
res = {}
def ci(ev):
    ev = ev.dropna()
    if len(ev) < 8: return None
    lo, hi = bc.mean_ci(ev.to_numpy()*1e4)
    return {"n": int(len(ev)), "mean_bps": float(ev.mean()*1e4), "ci95": [float(lo), float(hi)], "hit": float((ev>0).mean())}
for leader in ("ETH", "BTC"):
    L = np.log(frames[leader]["close"])
    lr = L.diff(K); vol = L.diff().rolling(24*14).std()*np.sqrt(K); z = lr/vol
    hot = z.abs() >= thr
    first = hot & ~hot.shift(1, fill_value=False)   # de-overlap: first bar of an episode
    sgn = np.sign(z)
    for H in (4, 8, 24):
        # (a) leader's own forward
        fwdL = (L.shift(-H) - L)
        res[f"{leader}_own_H{H}"] = ci((fwdL*sgn)[first])
        lag_ev, fol_ev, up_lag, dn_lag = [], [], [], []
        for s, df in frames.items():
            if s in ("ETH","BTC"): continue
            c = np.log(df["close"]).reindex(L.index)
            ar = c.diff(K); fwd = c.shift(-H) - c
            lagm = first & (ar.abs() < 0.5*lr.abs())
            folm = first & (ar*sgn >= 0.5*lr.abs())
            lag_ev.append((fwd*sgn)[lagm]); fol_ev.append((fwd*sgn)[folm])
            up_lag.append((fwd*sgn)[lagm & (sgn>0)]); dn_lag.append((fwd*sgn)[lagm & (sgn<0)])
        res[f"{leader}_laggard_deoverlap_H{H}"] = ci(pd.concat(lag_ev))
        res[f"{leader}_follower_deoverlap_H{H}"] = ci(pd.concat(fol_ev))
        res[f"{leader}_laggard_leaderUP_H{H}"] = ci(pd.concat(up_lag))
        res[f"{leader}_laggard_leaderDOWN_H{H}"] = ci(pd.concat(dn_lag))
    res[f"{leader}_n_episodes"] = int(first.sum())
json.dump(res, open(OUT,"w"), indent=1)
for k,v in res.items(): print(k, v)
