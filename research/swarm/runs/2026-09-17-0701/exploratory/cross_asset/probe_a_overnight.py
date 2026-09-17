"""EXPLORATORY probe (not the screen; numbers are not evidence).
Overnight-session (NYSE-closed) drift on long_1h TRAIN only (no mr_edge data used).
Session: enter at open of the 22:00 UTC bar (signal on the 21:00 UTC closed bar), exit at
close of the 13:00 UTC bar (16 bars). Weekday nights only (signal bar Mon-Thu) vs all.
Filter: 21:00 close >= max close of prior 240 bars (10-day high)."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, fee_math as fm
rows=[]
for sym in ["BTC","ETH","SOL","XRP","DOGE"]:
    df = ld.load_ohlcv(sym,"1h",era="train",dataset="long_1h")
    hi10 = df["close"].rolling(240).max()
    o,c = df["open"], df["close"]
    for i in range(240, len(df)-17):
        ts = df.index[i]
        if ts.hour != 21: continue
        ent = o.iloc[i+1]; ex = c.iloc[i+16]
        ret = (ex/ent-1)*1e4
        intr = (c.iloc[i]/o.iloc[i-6]-1)*1e4  # 15:00-21:00 UTC intraday
        rows.append(dict(sym=sym, ts=ts, dow=ts.dayofweek, ret=ret, intraday=intr, at_hi=c.iloc[i]>=hi10.iloc[i]))
r = pd.DataFrame(rows)
print("train span", r.ts.min(), r.ts.max())
def rep(lbl, x):
    x = x.to_numpy()
    if len(x)<2: print(lbl,"n<2"); return
    ci = bc.mean_ci(x); print(f"{lbl}: n={len(x)} mean_gross_bps={x.mean():.1f} ci95={ci} net_mean={x.mean()-fm.C_BPS:.1f} pos_frac={(x>0).mean():.3f}")
for sym in r.sym.unique():
    s = r[r.sym==sym]
    rep(f"{sym} all nights overnight", s.ret)
    rep(f"{sym} all days intraday15-21", s.intraday)
    rep(f"{sym} Mon-Thu nights", s[s.dow<=3].ret)
    rep(f"{sym} Fri-Sun nights", s[s.dow>=4].ret)
    rep(f"{sym} at 10d high nights", s[s.at_hi].ret)
    rep(f"{sym} at 10d high Mon-Thu", s[s.at_hi & (s.dow<=3)].ret)
rep("ALL syms all nights", r.ret); rep("ALL syms at_hi", r[r.at_hi].ret)
