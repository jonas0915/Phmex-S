"""EXPLORATORY ONLY (cross_asset lens, run 2026-09-25-2036). NOT the screen; numbers are not evidence.
long_1h TRAIN era only; no mr_edge data. Q: does a large return in the NY 15:00-16:00 bar
(BRRNY benchmark window, ETF sponsor trades 'as close to the BRRNY as practical') reverse over
the next H hours, and is that different from placebo NY hours (10,13,14,17)?"""
import pandas as pd, numpy as np
from research.swarm.lib import load_data as ld
syms = ["BTC","ETH","SOL","XRP","DOGE","LINK","ADA","BNB","LTC","AAVE"]
H = [3, 6, 12]
for nyh in [15, 10, 13, 14, 17]:
    rows = []
    for s in syms:
        df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
        c = df["close"]; o = df["open"]
        r = np.log(c / o)
        ny = df.index.tz_convert("America/New_York") if df.index.tz is not None else df.index.tz_localize("UTC").tz_convert("America/New_York")
        mask = (ny.hour == nyh) & (ny.dayofweek < 5)
        rr = r[mask]
        sd = rr.rolling(40, min_periods=20).std().shift(1)
        z = rr / sd
        for k in [1.5, 2.0]:
            ev = z[z.abs() > k].index
            for h in H:
                fwd = (np.log(c.shift(-h) / c)).reindex(ev)   # exploratory forward return, fade sign
                fade = (-np.sign(z.reindex(ev)) * fwd * 1e4).dropna()
                rows.append((s, k, h, len(fade), fade.mean()))
    t = pd.DataFrame(rows, columns=["sym","k","h","n","fade_bps"])
    g = t.groupby(["k","h"]).apply(lambda x: pd.Series({"n": x.n.sum(), "wmean_fade_bps": (x.n*x.fade_bps).sum()/x.n.sum()}))
    print(f"NY hour {nyh}:"); print(g.round(1).to_string()); print()
