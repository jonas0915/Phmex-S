"""H5: Volatility breakout. When a bar's range expands beyond k*ATR (range expansion),
enter in the direction of the bar's close, hold M bars, exit at open. Net of fee.
Also classic 'open + k*yesterday-range' intraday-style on the chosen TF.
Chronological split, pooled across symbols."""
import numpy as np, pandas as pd
from util import load_all, FEE_RT, perf_stats, fmt, SYMBOLS

def atr(df, n=14):
    h=df["high"]; l=df["low"]; c=df["close"].shift(1)
    tr=pd.concat([(h-l),(h-c).abs(),(l-c).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def run(tf, atr_n, k_expand, hold):
    data=load_all(tf)
    bpy=(365*24) if tf=="1h" else (365*6)
    train_r,test_r=[],[]
    n_trig=0
    for s in SYMBOLS:
        df=data[s].copy()
        df["atr"]=atr(df,atr_n)
        o=df["open"].values;h=df["high"].values;l=df["low"].values;c=df["close"].values
        a=df["atr"].values
        n=len(df); sp=int(n*0.5)
        i=atr_n+1
        while i+1+hold<n:
            rng=h[i]-l[i]
            if a[i]>0 and rng > k_expand*a[i]:
                dirn = 1 if c[i]>o[i] else -1   # close direction of expansion bar
                entry=o[i+1]; exit_=o[i+1+hold]
                net=dirn*(exit_/entry-1)-FEE_RT
                if i+1<sp: train_r.append(net)
                else: test_r.append(net)
                n_trig+=1
                i+=hold  # non-overlap after trigger
            else:
                i+=1
    return train_r,test_r,n_trig

def run_revert(tf, atr_n, k_expand, hold):
    """Same trigger but FADE the move (mean-revert) instead of follow."""
    data=load_all(tf)
    train_r,test_r=[],[]
    for s in SYMBOLS:
        df=data[s].copy(); df["atr"]=atr(df,atr_n)
        o=df["open"].values;h=df["high"].values;l=df["low"].values;c=df["close"].values;a=df["atr"].values
        n=len(df); sp=int(n*0.5); i=atr_n+1
        while i+1+hold<n:
            rng=h[i]-l[i]
            if a[i]>0 and rng>k_expand*a[i]:
                dirn = -1 if c[i]>o[i] else 1   # fade
                entry=o[i+1]; exit_=o[i+1+hold]
                net=dirn*(exit_/entry-1)-FEE_RT
                if i+1<sp: train_r.append(net)
                else: test_r.append(net)
                i+=hold
            else: i+=1
    return train_r,test_r

def main():
    print("===== H5 VOLATILITY BREAKOUT (FOLLOW expansion bar) =====")
    print("tf  atrN  k  hold | nTrig | TRAIN | TEST")
    for tf in ["1h","4h"]:
        bpy=(365*24) if tf=="1h" else (365*6)
        if tf=="1h":
            grid=[(14,2.0,6),(14,2.0,24),(14,3.0,12),(14,2.5,24),(24,2.0,48)]
        else:
            grid=[(14,2.0,3),(14,2.0,6),(14,2.5,6),(14,3.0,12),(20,2.0,12)]
        for an,k,hd in grid:
            tr,te,nt=run(tf,an,k,hd)
            print(f"{tf:>3}{an:>5}{k:>5.1f}{hd:>5} | {nt:>5} | {fmt(perf_stats(tr,bpy/hd))} | {fmt(perf_stats(te,bpy/hd))}")
    print("\n===== H5 VOLATILITY BREAKOUT (FADE expansion bar) =====")
    print("tf  atrN  k  hold | TRAIN | TEST")
    for tf in ["1h","4h"]:
        bpy=(365*24) if tf=="1h" else (365*6)
        if tf=="1h":
            grid=[(14,2.0,6),(14,2.0,24),(14,3.0,12),(14,2.5,24)]
        else:
            grid=[(14,2.0,3),(14,2.0,6),(14,2.5,6),(14,3.0,12)]
        for an,k,hd in grid:
            tr,te=run_revert(tf,an,k,hd)
            print(f"{tf:>3}{an:>5}{k:>5.1f}{hd:>5} | {fmt(perf_stats(tr,bpy/hd))} | {fmt(perf_stats(te,bpy/hd))}")

if __name__=="__main__":
    main()
