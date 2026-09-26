"""EXPLORATORY ONLY (cross_asset lens, run 2026-09-25-2036). NOT the screen; numbers are not evidence.
long_1h TRAIN era only (<= ~2026-04-24); no mr_edge data used.
Q: does the US-cash-session return (13:00->21:00 UTC close-to-close) predict the following
non-US session (21:00->13:00 next day), and vice versa?"""
import pandas as pd, numpy as np
from research.swarm.lib import load_data as ld
syms = ["BTC","ETH","SOL","XRP","DOGE","LINK","ADA","BNB","SUI","AAVE"]
for s in syms:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    c = df["close"]
    # close of bar opened at hh => price at hh+1
    p13 = c[c.index.hour == 12]; p13.index = p13.index.normalize()   # price at 13:00
    p21 = c[c.index.hour == 20]; p21.index = p21.index.normalize()   # price at 21:00
    d = pd.DataFrame({"p13": p13, "p21": p21}).dropna()
    d["us"] = np.log(d.p21 / d.p13)
    d["post"] = np.log(d.p13.shift(-1) / d.p21)        # 21:00 -> 13:00 next day (exploratory fwd)
    d["pre"] = np.log(d.p13 / d.p21.shift(1))          # 21:00 prev -> 13:00 today
    d = d.dropna()
    wk = d.index.dayofweek < 5
    dd = d[wk]
    r1 = dd.us.corr(dd.post); r2 = dd.pre.corr(dd.us)
    q = dd.us.quantile([0.2, 0.8])
    hi = dd.post[dd.us > q[0.8]].mean()*1e4; lo = dd.post[dd.us < q[0.2]].mean()*1e4
    q2 = dd.pre.quantile([0.2, 0.8])
    hi2 = dd.us[dd.pre > q2[0.8]].mean()*1e4; lo2 = dd.us[dd.pre < q2[0.2]].mean()*1e4
    print(f"{s:5s} n={len(dd)} corr(us->post)={r1:+.3f} post|usTop={hi:+.1f}bps post|usBot={lo:+.1f}bps | corr(pre->us)={r2:+.3f} us|preTop={hi2:+.1f} us|preBot={lo2:+.1f}  span {dd.index[0].date()}..{dd.index[-1].date()}")
