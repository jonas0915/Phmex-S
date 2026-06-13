#!/usr/bin/env python3
"""
CLEANEST differentiator test: take ALL big-bar events (the dead vol-fade universe),
then split each by whether a volume spike was present. If liquidation cascades are
real, the HIGH-VOLUME subset should revert better than the LOW-VOLUME subset.
If the high-vol subset is no better (or worse), volume adds nothing -> it's the dead
vol-fade with extra steps.

Also splits DOWN-cascade (bounce/long) vs UP-cascade (fade/short) within each vol bucket.
Full-sample, all symbols, both TFs. Net of taker fees.
"""
import sys, numpy as np, pandas as pd
import engine as E

TF = sys.argv[1] if len(sys.argv)>1 else "1h"
SYMS = E.list_symbols(TF)
HOLD = {"1h":4, "5m":48}[TF]   # 4h-equivalent hold
K = 3.0

def all_bigbar_with_volratio(sym):
    """generate big-bar (k only) trades but keep volratio for bucketing, both legs as reversion."""
    df=E.load(sym,TF)
    tr,dff=E.gen_signals(df,K,None,None)   # m,d None -> big-bar only
    p=E.realize(tr,dff,HOLD)
    if len(p): p["sym"]=sym
    return p

frames=[all_bigbar_with_volratio(s) for s in SYMS]
frames=[f for f in frames if len(f)]
p=pd.concat(frames,ignore_index=True)
p=p.dropna(subset=["volratio"])
print(f"### TF={TF} hold={HOLD} k={K}  total big-bar reversion trades n={len(p)}")
print(f"### volratio distribution: p50={p.volratio.median():.2f} p75={p.volratio.quantile(.75):.2f} p90={p.volratio.quantile(.90):.2f}")

def line(lab, sub):
    if len(sub)<5: print(f"  {lab:42s} n={len(sub):5d} (too few)"); return
    s=E.stats(sub); lo,hi=E.bootstrap_ci(sub.net.values)
    sig=" CI>0!" if lo>0 else (" CI<0" if hi<0 else " ~0")
    print(f"  {lab:42s} n={s['n']:5d} mean={s['mean_pct']:+.4f}% WR={s['wr']:4.1f}% CI[{lo:+.4f},{hi:+.4f}]{sig}")

print("\n--- ALL big-bar reversion, bucketed by volume ratio ---")
for lo_v,hi_v,lab in [(0,1.0,"vol<1.0x (BELOW avg)"),(1.0,1.5,"vol 1.0-1.5x"),
                      (1.5,2.0,"vol 1.5-2.0x"),(2.0,3.0,"vol 2.0-3.0x"),
                      (3.0,5.0,"vol 3.0-5.0x"),(5.0,1e9,"vol >5x (extreme spike)")]:
    sub=p[(p.volratio>=lo_v)&(p.volratio<hi_v)]
    line(lab, sub)

print("\n--- DOWN-cascade BOUNCE (long) by volume bucket ---")
L=p[p.side==1]
for lo_v,hi_v,lab in [(0,1.5,"long vol<1.5x"),(1.5,3.0,"long vol1.5-3x"),(3.0,1e9,"long vol>3x")]:
    line(lab, L[(L.volratio>=lo_v)&(L.volratio<hi_v)])

print("\n--- UP-cascade FADE (short) by volume bucket ---")
S=p[p.side==-1]
for lo_v,hi_v,lab in [(0,1.5,"short vol<1.5x"),(1.5,3.0,"short vol1.5-3x"),(3.0,1e9,"short vol>3x")]:
    line(lab, S[(S.volratio>=lo_v)&(S.volratio<hi_v)])

print("\n--- VERDICT NUMBERS: high-vol minus low-vol mean (per leg) ---")
def mean_pct(sub): return sub.net.mean()*100 if len(sub) else float('nan')
hiL=L[L.volratio>=3.0]; loL=L[L.volratio<1.5]
hiS=S[S.volratio>=3.0]; loS=S[S.volratio<1.5]
print(f"  LONG : high(>3x)={mean_pct(hiL):+.4f}%  low(<1.5x)={mean_pct(loL):+.4f}%  delta={mean_pct(hiL)-mean_pct(loL):+.4f}%")
print(f"  SHORT: high(>3x)={mean_pct(hiS):+.4f}%  low(<1.5x)={mean_pct(loS):+.4f}%  delta={mean_pct(hiS)-mean_pct(loS):+.4f}%")
print("DONE", TF)
