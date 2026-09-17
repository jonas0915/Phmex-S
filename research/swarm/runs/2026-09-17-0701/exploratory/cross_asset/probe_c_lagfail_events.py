"""EXPLORATORY probe (not the screen). mr_edge 1h TRAIN. Non-overlapping event study:
event = BTC 4h log-return > +thr (thr fixed at 100 bps) AND alt 4h return < 0.5 * BTC 4h return.
Forward alt return over 8h from next open, one event per symbol per 8h. Compare with baseline of all bars.
Also test the mirror (BTC 4h < -thr, alt > 0.5*BTC) and monthly split."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, fee_math as fm
btc = ld.load_ohlcv("BTC","1h",era="train",dataset="mr_edge")
alts = [s for s in ld.list_symbols("mr_edge") if s not in ("BTC","ETH")]
THR=100; K=8
ev=[]; base=[]
for s in alts:
    df = ld.load_ohlcv(s,"1h",era="train",dataset="mr_edge")
    d = df.join(btc[["close"]].rename(columns={"close":"b"}), how="inner")
    b4 = np.log(d.b/d.b.shift(4))*1e4; a4 = np.log(d.close/d.close.shift(4))*1e4
    o=d.open.to_numpy(); c=d.close.to_numpy(); idx=d.index
    last=-10**9
    for i in range(4,len(d)-K-1):
        f = (c[i+K]/o[i+1]-1)*1e4
        base.append(f)
        if i-last<K: continue
        if b4.iloc[i]>THR and a4.iloc[i]<0.5*b4.iloc[i]:
            ev.append(dict(sym=s,ts=idx[i],kind="lagfail_up",f=f)); last=i
        elif b4.iloc[i]<-THR and a4.iloc[i]>0.5*b4.iloc[i]:
            ev.append(dict(sym=s,ts=idx[i],kind="lagfail_dn",f=f)); last=i
E=pd.DataFrame(ev); base=np.array(base)
print("baseline all bars 8h fwd: n=%d mean=%.1f ci=%s"%(len(base),base.mean(),bc.mean_ci(base)))
for k,g in E.groupby("kind"):
    x=g.f.to_numpy(); print(f"{k}: n={len(x)} mean={x.mean():.1f} ci={bc.mean_ci(x)} pos={ (x>0).mean():.3f}")
    print(g.assign(m=g.ts.dt.to_period("M")).groupby("m").f.agg(["count","mean"]))
    print(g.groupby("sym").f.agg(["count","mean"]).sort_values("mean"))
