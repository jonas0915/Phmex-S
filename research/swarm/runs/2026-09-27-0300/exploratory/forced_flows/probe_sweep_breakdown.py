"""EXPLORATORY (not the screen, not evidence). long_1h TRAIN only via load_data.
Breakdown of the N=72 sweep-fade forward returns (same definition as probe_sweep_reclaim.py) by symbol and
by calendar month, at h=12 and h=24, plus a de-overlapped count (first event per symbol per 24 bars).
Also: mean Phemex funding rate per 8h over train for the universe (load_funding era=train)."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data
SYMS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","BTC","DOGE","ETH","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]
N = 72; rows = []
for s in SYMS:
    df = load_data.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    ph = df.high.rolling(N).max().shift(1); pl = df.low.rolling(N).min().shift(1)
    sd = np.where((df.high > ph) & (df.close < ph), -1, np.where((df.low < pl) & (df.close > pl), 1, 0))
    o, c = df.open.to_numpy(), df.close.to_numpy(); last = -10**9
    for i in np.nonzero(sd)[0]:
        if i + 25 >= len(c): continue
        e = o[i+1]; first = (i - last) >= 24
        if first: last = i
        rows.append([s, df.index[i], sd[i], first, sd[i]*(c[i+12]/e-1)*1e4, sd[i]*(c[i+24]/e-1)*1e4])
a = pd.DataFrame(rows, columns=["sym","ts","side","first","h12","h24"])
print("all n", len(a), "mean h12", round(a.h12.mean(),2), "h24", round(a.h24.mean(),2))
f = a[a["first"]]; print("de-overlapped n", len(f), "mean h12", round(f.h12.mean(),2), "h24", round(f.h24.mean(),2),
      "long h24", round(f[f.side==1].h24.mean(),2), "short h24", round(f[f.side==-1].h24.mean(),2))
print("weeks in train:", round((a.ts.max()-a.ts.min()).days/7, 2), "de-overlapped events/week:", round(len(f)/((a.ts.max()-a.ts.min()).days/7), 2))
print("\nby symbol (de-overlapped): n, mean h24"); print(f.groupby("sym").h24.agg(["count","mean"]).round(1).to_string())
print("\nby month (de-overlapped): n, mean h12, mean h24"); print(f.groupby(f.ts.dt.strftime("%Y-%m")).agg(n=("h24","count"), h12=("h12","mean"), h24=("h24","mean")).round(1).to_string())
fr = []
for s in SYMS:
    try:
        fd = load_data.load_funding(s, era="train"); fr.append([s, len(fd), fd["rate"].mean()*1e4])
    except Exception as e:
        fr.append([s, 0, float("nan")])
print("\nfunding (train) per-settlement mean, bps:"); print(pd.DataFrame(fr, columns=["sym","n","mean_bps"]).round(3).to_string())
