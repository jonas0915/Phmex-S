"""Robustness for the H5 FADE winner + H4 day-of-week fade/follow.
1. Parameter neighborhood of 1h fade (does the edge persist across nearby params, both halves?)
2. Per-symbol OOS breakdown (is it one symbol or broad?)
3. Long-only vs short-only legs OOS (is it just shorting in a down-market?)
4. H4 day-of-week tradable with FIXED prior (long Mon, short Thu) OOS."""
import numpy as np, pandas as pd
from util import load_all, FEE_RT, perf_stats, fmt, SYMBOLS

def atr(df,n=14):
    h=df["high"];l=df["low"];c=df["close"].shift(1)
    tr=pd.concat([(h-l),(h-c).abs(),(l-c).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def fade(tf, atr_n, k, hold, only=None, per_symbol=False, leg=None):
    data=load_all(tf)
    train_r,test_r={},{}
    agg_tr,agg_te=[],[]
    for s in SYMBOLS:
        if only and s!=only: continue
        df=data[s].copy(); df["atr"]=atr(df,atr_n)
        o=df["open"].values;h=df["high"].values;l=df["low"].values;c=df["close"].values;a=df["atr"].values
        n=len(df);sp=int(n*0.5);i=atr_n+1
        st,se=[],[]
        while i+1+hold<n:
            rng=h[i]-l[i]
            if a[i]>0 and rng>k*a[i]:
                dirn=-1 if c[i]>o[i] else 1
                if leg=="long" and dirn!=1: i+=1; continue
                if leg=="short" and dirn!=-1: i+=1; continue
                entry=o[i+1];exit_=o[i+1+hold]
                net=dirn*(exit_/entry-1)-FEE_RT
                (st if i+1<sp else se).append(net)
                i+=hold
            else: i+=1
        agg_tr+=st; agg_te+=se
        train_r[s]=st; test_r[s]=se
    if per_symbol: return train_r,test_r
    return agg_tr,agg_te

def main():
    bpy=365*24
    print("===== H5 FADE 1h PARAMETER NEIGHBORHOOD =====")
    print("atrN  k  hold | TRAIN | TEST")
    for an in [14]:
        for k in [2.0,2.5,3.0,3.5]:
            for hd in [8,12,18,24]:
                tr,te=fade("1h",an,k,hd)
                print(f"{an:>4}{k:>5.1f}{hd:>5} | {fmt(perf_stats(tr,bpy/hd))} | {fmt(perf_stats(te,bpy/hd))}")
    print("\n===== H5 FADE 1h k=3.0 hold=12 PER-SYMBOL OOS =====")
    tr_d,te_d=fade("1h",14,3.0,12,per_symbol=True)
    for s in SYMBOLS:
        te=te_d.get(s,[])
        if te:
            d=perf_stats(te,bpy/12)
            print(f"  {s:>5} TEST {fmt(d)}")
    print("\n===== H5 FADE 1h k=3.0 hold=12 LONG-leg vs SHORT-leg OOS =====")
    for leg in ["long","short"]:
        tr,te=fade("1h",14,3.0,12,leg=leg)
        print(f"  {leg:>5} TRAIN {fmt(perf_stats(tr,bpy/12))} | TEST {fmt(perf_stats(te,bpy/12))}")
    print("\n===== H5 FADE 1h k=2.5 hold=24 PER-SYMBOL OOS (the wider-n variant) =====")
    tr_d,te_d=fade("1h",14,2.5,24,per_symbol=True)
    for s in SYMBOLS:
        te=te_d.get(s,[])
        if te:
            print(f"  {s:>5} TEST {fmt(perf_stats(te,bpy/24))}")

    # H4 day-of-week with fixed economic prior, daily close-to-close, net fee per trade
    print("\n===== H4 DOW FIXED-PRIOR rule (long Mon bar, short Thu bar), daily, OOS =====")
    data=load_all("1h")
    tr_all,te_all=[],[]
    for s in SYMBOLS:
        df=data[s].set_index("timestamp")
        daily=pd.DataFrame({"open":df["open"].resample("1D").first(),
                            "close":df["close"].resample("1D").last()}).dropna()
        daily["dow"]=daily.index.dayofweek
        sp=int(len(daily)*0.5)
        for j in range(len(daily)):
            dow=daily["dow"].iloc[j]
            if dow==0: dirn=1      # Mon long
            elif dow==3: dirn=-1   # Thu short
            else: continue
            ret=daily["close"].iloc[j]/daily["open"].iloc[j]-1
            net=dirn*ret-FEE_RT
            (tr_all if j<sp else te_all).append(net)
    print(f"  TRAIN {fmt(perf_stats(tr_all,365))}")
    print(f"  TEST  {fmt(perf_stats(te_all,365))}")

if __name__=="__main__":
    main()
