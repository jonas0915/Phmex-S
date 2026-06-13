"""Is the H5 1h-fade edge temporally stable, or concentrated in the early down-months
(same regime as the Thursday effect)? Monthly mean net return of fade k=3.0 hold=12
and k=2.5 hold=24, pooled symbols."""
import numpy as np, pandas as pd
from util import load_all, FEE_RT, SYMBOLS

def atr(df,n=14):
    h=df["high"];l=df["low"];c=df["close"].shift(1)
    tr=pd.concat([(h-l),(h-c).abs(),(l-c).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def trades(tf,atr_n,k,hold):
    data=load_all(tf); rows=[]
    for s in SYMBOLS:
        df=data[s].copy(); df["atr"]=atr(df,atr_n)
        ts=df["timestamp"].values
        o=df["open"].values;h=df["high"].values;l=df["low"].values;c=df["close"].values;a=df["atr"].values
        n=len(df);i=atr_n+1
        while i+1+hold<n:
            rng=h[i]-l[i]
            if a[i]>0 and rng>k*a[i]:
                dirn=-1 if c[i]>o[i] else 1
                entry=o[i+1];exit_=o[i+1+hold]
                net=dirn*(exit_/entry-1)-FEE_RT
                rows.append((pd.Timestamp(ts[i+1]),net))
                i+=hold
            else: i+=1
    return pd.DataFrame(rows,columns=["ts","net"])

for k,hd in [(3.0,12),(2.5,24)]:
    df=trades("1h",14,k,hd)
    df["month"]=df["ts"].dt.to_period("M")
    print(f"\n=== H5 1h FADE k={k} hold={hd}: monthly mean net & n ===")
    g=df.groupby("month")["net"].agg(["mean","count","sum"])
    for m,r in g.iterrows():
        print(f"  {m}  mean={r['mean']*100:+.3f}%  n={int(r['count']):>3}  monthPnL={r['sum']*100:+.1f}%")
    pos=(g['mean']>0).sum(); tot=len(g)
    print(f"  months positive: {pos}/{tot}")
