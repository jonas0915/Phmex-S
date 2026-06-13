#!/usr/bin/env python3
"""Deep dive on claim params k=3.0/3.5 hold=12: leg decomp, regime, walk-forward, costs, stops."""
import os, json, math
import numpy as np, pandas as pd
from backtest import load, gen_signals, realize, stats, SYMBOLS

DIR=os.path.dirname(os.path.abspath(__file__))
FEE=0.00066

def build_all(k,hold,atr_period=14,fee=FEE,slip=0.0,stop=None,tp=None):
    fr=[]
    for s in SYMBOLS:
        df=load(s); tr,dff=gen_signals(df,k,atr_period)
        p=realize(tr,dff,hold,fee_oneway=fee,slip=slip,stop=stop,tp=tp)
        if len(p): p["sym"]=s
        fr.append(p)
    return pd.concat(fr,ignore_index=True)

btc=load("BTC"); mid_dt=pd.to_datetime(btc.ts.iloc[len(btc)//2],unit="ms")

# ---------- CLAIM PARAMS leg decomp full + OOS ----------
for k in [3.0,3.5]:
    print("="*70); print(f"CLAIM PARAMS k={k} hold=12 — leg decomposition")
    pnl=build_all(k,12)
    for label,sub in [("FULL",pnl),("OOS(last50%)",pnl[pd.to_datetime(pnl.dt)>=mid_dt])]:
        L=sub[sub.side==1]; S=sub[sub.side==-1]
        print(f"  [{label}] ALL n={len(sub)} mean={sub.net.mean()*100:+.4f}% sharpe={stats(sub)['sharpe']:+.2f} WR={(sub.net>0).mean()*100:.1f}%")
        print(f"           LONG(fade down) n={len(L)} mean={L.net.mean()*100:+.4f}% sharpe={stats(L)['sharpe']:+.2f}")
        print(f"           SHORT(fade up)  n={len(S)} mean={S.net.mean()*100:+.4f}% sharpe={stats(S)['sharpe']:+.2f}")

# ---------- BTC REGIME classification ----------
print("\n"+"="*70); print("REGIME: classify each month by BTC trend (close MoM)")
btc["month"]=btc.dt.dt.strftime("%Y-%m")
mclose=btc.groupby("month").close.last()
mret=mclose.pct_change()*100
# also intramonth: first->last
mfirst=btc.groupby("month").close.first(); mlast=btc.groupby("month").close.last()
mch=(mlast/mfirst-1)*100
regime={}
for m in mch.index:
    r=mch[m]
    regime[m] = "BULL" if r>5 else ("BEAR" if r<-5 else "CHOP")
print("BTC monthly intramonth % change and regime:")
for m in sorted(mch.index):
    print(f"  {m}: {mch[m]:+6.1f}%  {regime[m]}")

# ---------- edge per regime, per leg (k=3.0 and 3.5 combined view) ----------
for k in [3.0,3.5]:
    print("\n"+"="*70); print(f"EDGE BY REGIME — k={k} hold=12 (FULL sample, all symbols)")
    pnl=build_all(k,12); pnl["regime"]=pnl.month.map(regime)
    print("  regime | n | allMean% | LONGn LONGmean% | SHORTn SHORTmean%")
    for reg in ["BULL","CHOP","BEAR"]:
        sub=pnl[pnl.regime==reg]
        if len(sub)==0: continue
        L=sub[sub.side==1]; S=sub[sub.side==-1]
        print(f"  {reg:5s} | {len(sub):4d} | {sub.net.mean()*100:+.4f} | {len(L):4d} {L.net.mean()*100 if len(L) else 0:+.4f} | {len(S):4d} {S.net.mean()*100 if len(S) else 0:+.4f}")
    # per-month
    print("  per-month all-mean%:")
    mm=pnl.groupby("month").net.agg(["count","mean"])
    for m in mm.index:
        print(f"     {m} {regime.get(m,'?'):4s} n={int(mm.loc[m,'count']):4d} mean={mm.loc[m,'mean']*100:+.4f}%")

# ---------- WALK FORWARD 5 folds ----------
print("\n"+"="*70); print("WALK-FORWARD 5 expanding folds: tune k,hold on past, test on next chunk")
pnl_cache={}
def get(k,h):
    if (k,h) not in pnl_cache: pnl_cache[(k,h)]=build_all(k,h)
    return pnl_cache[(k,h)]
ts_all=btc.ts.values
edges=np.linspace(0,len(btc)-1,7).astype(int)  # 6 segments
seg_dt=[pd.to_datetime(btc.ts.iloc[e],unit="ms") for e in edges]
grid=[(k,h) for k in [2.5,3.0,3.5,4.0] for h in [6,12,18,24]]
oos_means=[]
for f in range(1,6):
    train_end=seg_dt[f]; test_end=seg_dt[f+1]
    # pick best on all data < train_end
    best=None
    for k,h in grid:
        p=get(k,h); tr=p[pd.to_datetime(p.dt)<train_end]
        st=stats(tr)
        if st["n"]>=30 and (best is None or st["mean_pct"]>best[0]):
            best=(st["mean_pct"],k,h)
    _,k,h=best
    p=get(k,h)
    te=p[(pd.to_datetime(p.dt)>=train_end)&(pd.to_datetime(p.dt)<test_end)]
    st=stats(te)
    oos_means.append(st["mean_pct"])
    print(f"  fold{f}: train<{train_end.date()} pick k={k} h={h} | OOS [{train_end.date()}..{test_end.date()}] n={st['n']} mean={st['mean_pct']:+.4f}% sharpe={st['sharpe']:+.2f}")
print(f"  WF OOS mean of fold-means: {np.mean(oos_means):+.4f}%  positive folds: {sum(1 for x in oos_means if x>0)}/{len(oos_means)}")

# ---------- COST STRESS (claim params k=3.0 h=12) ----------
print("\n"+"="*70); print("COST STRESS k=3.0 hold=12 (FULL & OOS)")
for fee,slip,lab in [(0.00066,0,"0.066% one-way"),(0.0006,0,"0.12% RT"),(0.00066,0.0003,"0.066%+0.03% slip")]:
    p=build_all(3.0,12,fee=fee,slip=slip)
    full=stats(p); oos=stats(p[pd.to_datetime(p.dt)>=mid_dt])
    print(f"  {lab:22s}: FULL mean={full['mean_pct']:+.4f}% | OOS mean={oos['mean_pct']:+.4f}% (n={oos['n']})")

# ---------- EXIT VARIANTS: stop / tp ----------
print("\n"+"="*70); print("EXIT VARIANTS k=3.0 hold=12 (FULL sample, net%)")
variants=[("time only",None,None),("stop 2%",0.02,None),("stop 3%",0.03,None),
          ("stop 1.5%",0.015,None),("tp 2%",None,0.02),("stop3 tp3",0.03,0.03),("stop2 tp4",0.02,0.04)]
for lab,stp,tp in variants:
    p=build_all(3.0,12,stop=stp,tp=tp)
    st=stats(p)
    print(f"  {lab:12s}: n={st['n']} mean={st['mean_pct']:+.4f}% total={st['total_pct']:+.1f}% sharpe={st['sharpe']:+.2f} WR={st['wr']:.1f}%")

# ---------- FREQUENCY ----------
print("\n"+"="*70); print("FREQUENCY k=3.0 hold=12")
p=build_all(3.0,12)
days=(btc.dt.iloc[-1]-btc.dt.iloc[0]).days
print(f"  total trades={len(p)} over {days} days = {len(p)/days:.2f} trades/day across {len(SYMBOLS)} symbols")
print(f"  hold fixed=12h. trades per symbol avg={len(p)/len(SYMBOLS):.0f}")
