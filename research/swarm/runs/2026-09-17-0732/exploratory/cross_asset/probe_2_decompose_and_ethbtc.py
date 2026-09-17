"""EXPLORATORY — NOT THE SCREEN. Train era only (mr_edge, 1h).
(1) Decompose the 'BTC rally, alt lags' forward move: BTC's own forward return vs the
    alt's, and alt-minus-BTC excess; also non-overlapping (first bar of a cluster) events.
(2) ETH/BTC ratio regime: 24-bar ratio change as conditioning for alt forward 24h return.
Numbers here shape the thesis only; they are not evidence.
"""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc

LAG, FWD, THR = 4, 8, 100.0
syms = [s for s in ld.list_symbols("mr_edge") if s not in ("BTC", "ETH")]
btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="mr_edge")["close"]
eth = ld.load_ohlcv("ETH", "1h", era="train", dataset="mr_edge")["close"]
b_ret = np.log(btc / btc.shift(LAG)) * 1e4
b_fwd = np.log(btc.shift(-FWD) / btc) * 1e4
ratio = (eth / btc).dropna()
r24 = np.log(ratio / ratio.shift(24)) * 1e4

print("BTC own fwd8h after b>100:", end=" ")
x = b_fwd[b_ret > THR].dropna().to_numpy(); print(f"n={len(x)} mean {x.mean():.1f} CI {tuple(round(v,1) for v in bc.mean_ci(x))}")
print("BTC own fwd8h after b<-100:", end=" ")
x = b_fwd[b_ret < -THR].dropna().to_numpy(); print(f"n={len(x)} mean {x.mean():.1f} CI {tuple(round(v,1) for v in bc.mean_ci(x))}")

rows = []
for s in syms:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="mr_edge")
    c = df["close"]
    d = pd.DataFrame({"b": b_ret.reindex(df.index), "bf": b_fwd.reindex(df.index),
                      "a": np.log(c / c.shift(LAG)) * 1e4,
                      "fwd": np.log(c.shift(-FWD) / c) * 1e4,
                      "fwd24": np.log(c.shift(-24) / c) * 1e4,
                      "r24": r24.reindex(df.index)})
    d["sym"] = s
    fire = (d.b > THR) & (d.a < 0.5 * d.b)
    d["fire"] = fire
    d["first"] = fire & ~fire.shift(1, fill_value=False)
    rows.append(d)
D = pd.concat(rows)

m = D.fire
x = (D.loc[m, "fwd"] - D.loc[m, "bf"]).dropna().to_numpy()
print(f"B: alt fwd8h MINUS BTC fwd8h (excess): n={len(x)} mean {x.mean():.1f} CI {tuple(round(v,1) for v in bc.mean_ci(x))}")
m2 = D["first"]
x = D.loc[m2, "fwd"].dropna().to_numpy()
print(f"B first-bar-of-cluster only: n={len(x)} mean {x.mean():.1f} CI {tuple(round(v,1) for v in bc.mean_ci(x))} share<0 {(x<0).mean():.3f}")
sub = D.loc[m2]
print("B first-bar by month:", sub.groupby(sub.index.month)["fwd"].agg(["count", "mean"]).round(1).to_dict())
print("B first-bar per symbol count:", sub.groupby("sym").size().to_dict())

# capture threshold sensitivity (exploratory only; NOT a registered robustness read)
for cap in (0.0, 0.25, 0.5, 0.75):
    f = (D.b > THR) & (D.a < cap * D.b); f = f & ~f.shift(1, fill_value=False)
    x = D.loc[f, "fwd"].dropna().to_numpy()
    print(f"  capture<{cap}: n={len(x)} mean {x.mean():.1f} CI {tuple(round(v,1) for v in bc.mean_ci(x))}")

# ETH/BTC ratio regime -> alt 24h forward
print("--- ETH/BTC ratio 24h change regime -> alt fwd24 (all bars, overlapping) ---")
for lo, hi in ((-1e9, -150), (-150, 0), (0, 150), (150, 1e9)):
    mm = (D.r24 > lo) & (D.r24 <= hi)
    x = D.loc[mm, "fwd24"].dropna().to_numpy()
    print(f"  r24 in ({lo},{hi}]: n={len(x)} mean {x.mean():.1f} CI {tuple(round(v,1) for v in bc.mean_ci(x))}")
