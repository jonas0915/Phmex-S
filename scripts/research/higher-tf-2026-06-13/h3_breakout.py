"""H3: Trend-following / breakout.
(A) Donchian: long when close breaks N-bar high, short when breaks N-bar low.
    Exit on opposite M-bar channel OR after max_hold bars.
(B) MA crossover: long when fast MA > slow MA, flip on cross.
Net of fee per round trip. Chronological split, pooled across symbols."""
import numpy as np, pandas as pd
from util import load_all, FEE_RT, perf_stats, fmt, SYMBOLS

def donchian(tf, N, exit_N, max_hold):
    data = load_all(tf)
    bpy = (365*24) if tf=="1h" else (365*6)
    train_r, test_r, holds = [], [], []
    for s in SYMBOLS:
        df = data[s]; o=df["open"].values; h=df["high"].values; l=df["low"].values; c=df["close"].values
        n=len(df); sp=int(n*0.5)
        pos=0; entry=0.0; entry_i=0; dirn=0
        i=N
        while i < n-1:
            if pos==0:
                hh=h[i-N:i].max(); ll=l[i-N:i].min()
                if c[i] > hh:
                    pos=1; dirn=1; entry=o[i+1]; entry_i=i+1
                elif c[i] < ll:
                    pos=1; dirn=-1; entry=o[i+1]; entry_i=i+1
            else:
                bars_held = i - entry_i
                ex_hh=h[i-exit_N:i].max(); ex_ll=l[i-exit_N:i].min()
                exit_sig = (dirn==1 and c[i]<ex_ll) or (dirn==-1 and c[i]>ex_hh) or (bars_held>=max_hold)
                if exit_sig:
                    exit_p=o[i+1]
                    net = dirn*(exit_p/entry-1) - FEE_RT
                    if entry_i < sp: train_r.append(net)
                    else: test_r.append(net)
                    holds.append(bars_held)
                    pos=0
            i+=1
    return train_r, test_r, holds

def ma_cross(tf, fast, slow):
    data=load_all(tf)
    train_r,test_r,holds=[],[],[]
    for s in SYMBOLS:
        df=data[s]; o=df["open"].values; c=df["close"].values; n=len(df); sp=int(n*0.5)
        mf=pd.Series(c).rolling(fast).mean().values
        ms=pd.Series(c).rolling(slow).mean().values
        pos=0;entry=0.0;entry_i=0;dirn=0
        i=slow+1
        while i<n-1:
            sig = 1 if mf[i]>ms[i] else -1
            if pos==0:
                pos=1;dirn=sig;entry=o[i+1];entry_i=i+1
            elif sig!=dirn:
                exit_p=o[i+1]; net=dirn*(exit_p/entry-1)-FEE_RT
                if entry_i<sp: train_r.append(net)
                else: test_r.append(net)
                holds.append(i-entry_i)
                pos=1;dirn=sig;entry=o[i+1];entry_i=i+1
            i+=1
    return train_r,test_r,holds

def main():
    print("===== H3A DONCHIAN BREAKOUT =====")
    print("tf   N exitN maxH | medHold | TRAIN | TEST")
    for tf in ["1h","4h"]:
        bpy=(365*24) if tf=="1h" else (365*6)
        if tf=="1h":
            grid=[(24,12,168),(48,24,168),(72,24,336),(168,48,720),(24,24,72)]
        else:
            grid=[(6,3,42),(12,6,84),(18,6,120),(42,12,180),(6,6,24)]
        for N,eN,mh in grid:
            tr,te,hd=donchian(tf,N,eN,mh)
            medh=np.median(hd) if hd else 0
            st_tr=perf_stats(tr,bpy/max(medh,1)); st_te=perf_stats(te,bpy/max(medh,1))
            print(f"{tf:>3}{N:>4}{eN:>5}{mh:>6} | {medh:>5.0f}b | {fmt(st_tr)} | {fmt(st_te)}")
    print("\n===== H3B MA CROSSOVER =====")
    print("tf  fast slow | medHold | TRAIN | TEST")
    for tf in ["1h","4h"]:
        bpy=(365*24) if tf=="1h" else (365*6)
        if tf=="1h":
            grid=[(12,48),(24,72),(48,168),(24,168),(50,200)]
        else:
            grid=[(6,24),(12,42),(6,42),(12,84),(8,21)]
        for f,sl in grid:
            tr,te,hd=ma_cross(tf,f,sl)
            medh=np.median(hd) if hd else 0
            st_tr=perf_stats(tr,bpy/max(medh,1)); st_te=perf_stats(te,bpy/max(medh,1))
            print(f"{tf:>3}{f:>5}{sl:>5} | {medh:>5.0f}b | {fmt(st_tr)} | {fmt(st_te)}")

if __name__=="__main__":
    main()
