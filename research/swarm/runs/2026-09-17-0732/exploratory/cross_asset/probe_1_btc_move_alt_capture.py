"""EXPLORATORY — NOT THE SCREEN. Train era only (mr_edge, 1h).
Conditions on BTC's 4-bar log return and the alt's capture of that move; reports the
alt's forward 8-bar log return (bps) with bootstrap_ci.mean_ci. Numbers here are for
shaping the thesis only and are not evidence.
"""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc

LAG, FWD, THR = 4, 8, 100.0
syms = [s for s in ld.list_symbols("mr_edge") if s not in ("BTC",)]
btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="mr_edge")["close"]
b_ret = np.log(btc / btc.shift(LAG)) * 1e4

rows = []
for s in syms:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="mr_edge")
    c = df["close"]
    b = b_ret.reindex(df.index)
    a = np.log(c / c.shift(LAG)) * 1e4
    fwd = (np.log(c.shift(-FWD) / c) * 1e4)  # exploratory forward return, NOT a signal
    d = pd.DataFrame({"b": b, "a": a, "fwd": fwd}).dropna()
    d["sym"] = s
    rows.append(d)
D = pd.concat(rows)
print("bars", len(D), "symbols", len(syms))
base = D["fwd"].to_numpy()
print(f"ALL bars: fwd{FWD}h mean {base.mean():.1f} bps CI {bc.mean_ci(base)}")

conds = {
    "A crash+alt_lag (b<-100, a>0.5b)": (D.b < -THR) & (D.a > 0.5 * D.b),
    "A' crash+alt_overshoot (b<-100, a<1.5b)": (D.b < -THR) & (D.a < 1.5 * D.b),
    "A'' crash all (b<-100)": (D.b < -THR),
    "B rally+alt_lag (b>100, a<0.5b)": (D.b > THR) & (D.a < 0.5 * D.b),
    "B' rally+alt_overshoot (b>100, a>1.5b)": (D.b > THR) & (D.a > 1.5 * D.b),
    "B'' rally all (b>100)": (D.b > THR),
}
for k, m in conds.items():
    x = D.loc[m, "fwd"].to_numpy()
    if len(x) < 5:
        print(k, "n", len(x)); continue
    lo, hi = bc.mean_ci(x)
    print(f"{k}: n={len(x)} fwd{FWD}h mean {x.mean():.1f} bps CI ({lo:.1f}, {hi:.1f}) share<0 {(x<0).mean():.3f}")
# month spread for A and B
for k in ["A crash+alt_lag (b<-100, a>0.5b)", "B rally+alt_lag (b>100, a<0.5b)"]:
    m = conds[k]
    sub = D.loc[m]
    print(k, "by month:", sub.groupby(sub.index.month)["fwd"].agg(["count", "mean"]).round(1).to_dict())
