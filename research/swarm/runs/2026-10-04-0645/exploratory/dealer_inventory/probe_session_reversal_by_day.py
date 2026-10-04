"""EXPLORATORY (not evidence) — dealer_inventory lens, run 2026-10-04-0645.
Robustness of probe_session_reversal: collapse to ONE observation per day (mean fade across symbols with |z|>k),
report day-count, day-level hit rate, by month, first vs second half of train, and BTC/ETH only.
Data: long_1h era=train only. Command: PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 <this file>
"""
import numpy as np, pandas as pd
from research.swarm.lib import load_data, bootstrap_ci
SYMS = [s for s in load_data.list_symbols("long_1h") if s != "GIGGLE"]
SESS = {"asia": (0, 7), "eu": (7, 14), "us": (14, 21)}
rows = []
for s in SYMS:
    c = load_data.load_ohlcv(s, "1h", era="train", dataset="long_1h")["close"]
    lr = np.log(c).diff()
    sd1 = lr.rolling(480, min_periods=240).std()
    for name, (h0, h1) in SESS.items():
        r = (np.log(c) - np.log(c.shift(h1 - h0))) * 1e4
        z = r / (sd1 * np.sqrt(h1 - h0) * 1e4)
        f48 = (np.log(c.shift(-48)) - np.log(c)) * 1e4  # exploratory forward label only
        m = (c.index.hour == h1) & (c.index.weekday < 5)
        rows.append(pd.DataFrame(dict(sym=s, sess=name, r=r[m], z=z[m], fwd=f48[m])))
d = pd.concat(rows).dropna()
d["day"] = d.index.normalize()
d["fade"] = -np.sign(d.r) * d.fwd
for k in (1.0, 1.5, 2.0):
    for name in SESS:
        x = d[(d.sess == name) & (d.z.abs() > k)]
        g = x.groupby("day").fade.mean()
        lo, hi = bootstrap_ci.mean_ci(g.values)
        half = g.index < g.index[len(g)//2]
        print(f"k={k} {name}: days={len(g)} day_mean={g.mean():.1f} ci95_day=[{lo:.1f},{hi:.1f}] day_hit={(g>0).mean():.3f} H1={g[half].mean():.1f} H2={g[~half].mean():.1f}")
    x = d[(d.sess == "us") & (d.z.abs() > k)]
    g = x.groupby("day").fade.mean()
    print("  us by month:", g.groupby(g.index.to_period("M")).agg(["count", "mean"]).round(1).to_dict("index"))
    for s in ("BTC", "ETH"):
        y = x[x.sym == s].fade
        if len(y) > 1:
            lo, hi = bootstrap_ci.mean_ci(y.values)
            print(f"  us {s}: n={len(y)} mean={y.mean():.1f} ci=[{lo:.1f},{hi:.1f}]")
# direction split for us
x = d[(d.sess == "us") & (d.z.abs() > 1.5)]
print("us k1.5 up-session (short fade):", x[x.r > 0].fade.mean().round(1), len(x[x.r > 0]), " down-session (long fade):", x[x.r < 0].fade.mean().round(1), len(x[x.r < 0]))
