#!/usr/bin/env python3
"""
Main rigorous analysis for liquidation-cascade reversion.
Anti-selection-bias: judge on FULL-SAMPLE sign + bootstrap CI, walk-forward, multi-regime.
KEY TEST: does volume-spike conditioning beat plain big-bar (the dead vol-fade)?
"""
import os, sys, json, math
import numpy as np, pandas as pd
import engine as E

TF = sys.argv[1] if len(sys.argv)>1 else "1h"
SYMS = E.list_symbols(TF)
print(f"### TIMEFRAME={TF}  symbols({len(SYMS)})={SYMS}")
btc = E.load("BTC", TF)
print(f"### span {btc.dt.iloc[0]} -> {btc.dt.iloc[-1]}  ({len(btc)} bars)")

HOLD_MAP = {"1h":{"1h":1,"4h":4,"12h":12,"24h":24}, "5m":{"1h":12,"4h":48,"12h":144,"24h":288}}
HOLDS = HOLD_MAP[TF]

# ---------- regime map from BTC monthly intramonth move ----------
btc["month"]=btc.dt.dt.strftime("%Y-%m")
mf=btc.groupby("month").close.first(); ml=btc.groupby("month").close.last()
mch=(ml/mf-1)*100
regime={m:("BULL" if mch[m]>5 else ("BEAR" if mch[m]<-5 else "CHOP")) for m in mch.index}

def add_regime(p):
    p=p.copy(); p["regime"]=p.month.map(regime); return p

def report(p, label):
    s=E.stats(p); lo,hi=E.bootstrap_ci(p.net.values) if len(p) else (float('nan'),float('nan'))
    sig = "" if len(p)<5 else (" CI>0!" if lo>0 else (" CI<0" if hi<0 else " CI~0"))
    print(f"  {label:34s} n={s['n']:5d} mean={s['mean_pct']:+.4f}% WR={s['wr']:4.1f}% "
          f"sh={s['sharpe']:+.2f} CI[{lo:+.4f},{hi:+.4f}]{sig}")
    return s,(lo,hi)

# ================================================================
# PART 1: HEAD-TO-HEAD  A=bigbar(dead) vs B=+volume vs C=+vol+dirclose
# best-effort default geometry, then we show legs. judge full-sample.
# ================================================================
print("\n"+"="*78)
print("PART 1 — DOES VOLUME CONDITIONING BEAT PLAIN BIG-BAR? (full-sample, hold=4h-equiv, no stop)")
H = HOLDS["4h"]
configs = [
    ("A bigbar only (k=3)",            dict(k=3.0,m=None,d=None)),
    ("B +volume (k=3,m=2)",            dict(k=3.0,m=2.0,d=None)),
    ("B +volume (k=3,m=3)",            dict(k=3.0,m=3.0,d=None)),
    ("C +vol+dir (k=3,m=2,d=0.6)",     dict(k=3.0,m=2.0,d=0.6)),
    ("C +vol+dir (k=3,m=3,d=0.6)",     dict(k=3.0,m=3.0,d=0.6)),
    ("C strong (k=4,m=3,d=0.6)",       dict(k=4.0,m=3.0,d=0.6)),
]
for label,cfg in configs:
    p=E.build_all(SYMS,TF,hold=H,**cfg)
    if len(p)==0: print(f"  {label}: no trades"); continue
    p=add_regime(p)
    report(p,label+" ALL")
    L=p[p.side==1]; S=p[p.side==-1]
    report(L,"   down-cascade BOUNCE(long)")
    report(S,"   up-cascade FADE(short)")

# ================================================================
# PART 2: full leg/hold/stop sweep on the FULL CASCADE config C
# ================================================================
print("\n"+"="*78)
print("PART 2 — FULL CASCADE C(k=3,m=3,d=0.6): hold x stop sweep (full-sample, per leg)")
CFG=dict(k=3.0,m=3.0,d=0.6)
for hl,H in HOLDS.items():
    for stp in [None,0.02,0.03]:
        p=E.build_all(SYMS,TF,hold=H,stop=stp,**CFG)
        if len(p)==0: continue
        slab=f"stop={stp if stp else 'none'}"
        L=p[p.side==1]; S=p[p.side==-1]
        sL=E.stats(L); sS=E.stats(S); sA=E.stats(p)
        loA,hiA=E.bootstrap_ci(p.net.values)
        print(f"  hold={hl:3s} {slab:9s} ALL n={sA['n']:4d} {sA['mean_pct']:+.4f}% CI[{loA:+.4f},{hiA:+.4f}] | "
              f"LONG n={sL['n']:4d} {sL['mean_pct']:+.4f}% | SHORT n={sS['n']:4d} {sS['mean_pct']:+.4f}%")

# ================================================================
# PART 3: per-regime decomposition (catch the regime-tilt trap)
# ================================================================
print("\n"+"="*78)
print("PART 3 — REGIME DECOMP C(k=3,m=3,d=0.6) hold=4h stop=3% (this is what killed vol-fade)")
p=add_regime(E.build_all(SYMS,TF,hold=HOLDS["4h"],stop=0.03,**CFG))
for reg in ["BULL","CHOP","BEAR"]:
    sub=p[p.regime==reg]
    if len(sub)==0: continue
    L=sub[sub.side==1]; S=sub[sub.side==-1]
    print(f"  {reg:4s} ALL n={len(sub):4d} {E.stats(sub)['mean_pct']:+.4f}% | "
          f"LONG n={len(L):4d} {E.stats(L)['mean_pct']:+.4f}% | SHORT n={len(S):4d} {E.stats(S)['mean_pct']:+.4f}%")

# ================================================================
# PART 4: WALK-FORWARD (5 expanding folds), tune on past, test next
# ================================================================
print("\n"+"="*78)
print("PART 4 — WALK-FORWARD 5 folds (tune k,m,hold,stop on past; test OOS). full cascade family.")
cache={}
def get(k,m,d,h,stp):
    key=(k,m,d,h,stp)
    if key not in cache: cache[key]=E.build_all(SYMS,TF,k=k,m=m,d=d,hold=h,stop=stp)
    return cache[key]
grid=[(k,m,0.6,HOLDS[hl],stp) for k in [3.0,4.0] for m in [2.0,3.0]
      for hl in ["1h","4h","12h"] for stp in [None,0.03]]
edges=np.linspace(0,len(btc)-1,7).astype(int)
seg_dt=[pd.to_datetime(btc.ts.iloc[e],unit="ms") for e in edges]
oos=[]
for f in range(1,6):
    tr_end=seg_dt[f]; te_end=seg_dt[f+1]; best=None
    for params in grid:
        pp=get(*params); trn=pp[pd.to_datetime(pp.dt)<tr_end]
        st=E.stats(trn)
        if st["n"]>=50 and (best is None or st["mean_pct"]>best[0]):
            best=(st["mean_pct"],params)
    if best is None: print(f"  fold{f}: no qualifying config"); continue
    params=best[1]; pp=get(*params)
    te=pp[(pd.to_datetime(pp.dt)>=tr_end)&(pd.to_datetime(pp.dt)<te_end)]
    st=E.stats(te); oos.append(st["mean_pct"])
    print(f"  fold{f}: train<{tr_end.date()} pick k={params[0]} m={params[1]} h={params[3]} stop={params[4]} | "
          f"OOS [{tr_end.date()}..{te_end.date()}] n={st['n']} mean={st['mean_pct']:+.4f}% sh={st['sharpe']:+.2f}")
if oos:
    print(f"  WF OOS mean-of-folds={np.mean(oos):+.4f}%  positive folds: {sum(1 for x in oos if x>0)}/{len(oos)}")

# ================================================================
# PART 5: COST STRESS on best-looking full-sample config
# ================================================================
print("\n"+"="*78)
print("PART 5 — COST STRESS C(k=3,m=3,d=0.6) hold=4h stop=3% (full-sample)")
for fee,slip,lab in [(0.00066,0,"0.066% one-way (taker)"),(0.0006,0.0006,"0.12% RT + 0.06% slip"),
                     (0.0006,0.001,"0.12% RT + 0.10% slip")]:
    p=E.build_all(SYMS,TF,hold=HOLDS["4h"],stop=0.03,fee=fee,slip=slip,**CFG)
    s=E.stats(p); lo,hi=E.bootstrap_ci(p.net.values)
    print(f"  {lab:26s}: n={s['n']} mean={s['mean_pct']:+.4f}% total={s['total_pct']:+.1f}% CI[{lo:+.4f},{hi:+.4f}]")
print("\nDONE", TF)
