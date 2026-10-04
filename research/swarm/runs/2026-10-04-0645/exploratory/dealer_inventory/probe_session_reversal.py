"""EXPLORATORY (not evidence) — dealer_inventory lens, run 2026-10-04-0645.
Question: does the US-cash-session return (14:00->21:00 UTC, ETF/AP/dealer-intermediated hours)
reverse over the following 24h/48h more than the Asia-session (00:00->07:00 UTC) or EU (07:00->14:00) placebo?
Data: long_1h, era=train only (no mr_edge, no holdout). Descriptive only: per-session
mean forward return conditioned on |session ret| > k*rolling-sd, signed as a fade.
Command: PYTHONDONTWRITEBYTECODE=1 python3 research/swarm/runs/2026-10-04-0645/exploratory/dealer_inventory/probe_session_reversal.py
"""
import numpy as np, pandas as pd
from research.swarm.lib import load_data, bootstrap_ci
SYMS = [s for s in load_data.list_symbols("long_1h") if s != "GIGGLE"]
SESS = {"asia": (0, 7), "eu": (7, 14), "us": (14, 21)}
rows = []
for s in SYMS:
    df = load_data.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    c = df["close"]
    for name, (h0, h1) in SESS.items():
        ends = c.index[c.index.hour == h1]
        for t in ends:
            t0 = t - pd.Timedelta(hours=h1 - h0)
            if t0 not in c.index: continue
            r = (c[t] / c[t0] - 1) * 1e4
            hist = c[:t].pct_change().iloc[-24*20:]
            sd = hist.std() * np.sqrt(h1 - h0) * 1e4
            for H in (24, 48):
                t2 = t + pd.Timedelta(hours=H)
                if t2 not in c.index: continue
                f = (c[t2] / c[t] - 1) * 1e4
                rows.append(dict(sym=s, sess=name, ts=t, r=r, z=r / sd if sd > 0 else np.nan, H=H, fwd=f, wd=t.weekday()))
d = pd.DataFrame(rows)
d = d[d.wd < 5]
for H in (24, 48):
    for k in (0.0, 1.0, 1.5, 2.0):
        for name in SESS:
            x = d[(d.H == H) & (d.sess == name) & (d.z.abs() > k)]
            fade = -np.sign(x.r) * x.fwd
            lo, hi = bootstrap_ci.mean_ci(fade.values) if len(fade) > 1 else (np.nan, np.nan)
            print(f"H={H} k={k} {name}: n={len(x)} fade_gross_mean={fade.mean():.2f} ci95=[{lo:.2f},{hi:.2f}] corr(r,fwd)={x.r.corr(x.fwd):.3f}")
print("train range:", d.ts.min(), d.ts.max())
