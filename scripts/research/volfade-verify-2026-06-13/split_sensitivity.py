#!/usr/bin/env python3
"""How fragile is the +0.067% OOS? Sweep the train/test split point. Also full-sample sign."""
import os, numpy as np, pandas as pd
from backtest import load, gen_signals, realize, stats, SYMBOLS
FEE=0.00066
def build_all(k,hold):
    fr=[]
    for s in SYMBOLS:
        df=load(s); tr,dff=gen_signals(df,k,FEE if False else 14)
        # note atr_period default 14
        tr,dff=gen_signals(df,k,14)
        p=realize(tr,dff,hold,fee_oneway=FEE)
        if len(p): p["sym"]=s; fr.append(p)
    return pd.concat(fr,ignore_index=True)

btc=load("BTC")
pnl=build_all(3.0,12)
pnl["dt"]=pd.to_datetime(pnl.dt)
print("k=3.0 hold=12  OOS mean%/trade as a function of split fraction:")
for frac in [0.3,0.4,0.45,0.5,0.55,0.6,0.7]:
    cut=pd.to_datetime(btc.ts.iloc[int(len(btc)*frac)],unit="ms")
    te=pnl[pnl.dt>=cut]
    s=stats(te)
    print(f"  split@{int(frac*100)}% ({cut.date()}): OOS n={s['n']} mean={s['mean_pct']:+.4f}% sharpe={s['sharpe']:+.2f}")
print(f"\nFULL-SAMPLE k=3.0 h=12: mean={pnl.net.mean()*100:+.4f}% (this is the unbiased single number)")
# bootstrap CI on full-sample mean
x=pnl.net.values
rng=np.random.default_rng(42)
boot=np.array([rng.choice(x,len(x),replace=True).mean() for _ in range(2000)])*100
print(f"  full-sample bootstrap 95% CI: [{np.percentile(boot,2.5):+.4f}%, {np.percentile(boot,97.5):+.4f}%]")
# OOS bootstrap
te=pnl[pnl.dt>=pd.to_datetime(btc.ts.iloc[len(btc)//2],unit="ms")]
xo=te.net.values
booto=np.array([rng.choice(xo,len(xo),replace=True).mean() for _ in range(2000)])*100
print(f"  OOS(50%) bootstrap 95% CI: [{np.percentile(booto,2.5):+.4f}%, {np.percentile(booto,97.5):+.4f}%]  (straddles 0? {np.percentile(booto,2.5)<0<np.percentile(booto,97.5)})")
