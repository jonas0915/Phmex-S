#!/usr/bin/env python3
"""
Final anti-artifact gauntlet:
 1. NULL TEST: does the SELECTION rule beat random pair selection? Build distribution of
    OOS Sharpe from random 10-pair portfolios (from the coint set) vs the top-10-by-train-Sharpe.
 2. ALL-PAIRS baseline (no selection): trade every cointegrated pair OOS, equal weight.
    If 'all' ~= 'selected', selection adds nothing (still could be a real spread-reversion edge).
 3. PURGED walk-forward: confirm no warmup leak by purging warmup days from BOTH fit and OOS pnl
    (drop first `zwin` days of each OOS block entirely).
 4. SUBPERIOD sensitivity of chained WF: drop the huge fold 6, recompute.
 5. 4H sanity: does the same top pair (SAND/ATOM, FIL/NEAR) revert on 4h with proportional costs?
"""
import os, itertools
import numpy as np
import pandas as pd
from pairs_scan import load_daily, eg_pvalue, backtest_spread, perf

np.random.seed(123)
HERE = os.path.dirname(__file__)
panel = load_daily(); logp = np.log(panel); syms=list(panel.columns)
pairs=list(itertools.combinations(syms,2))
sig = pd.read_csv(os.path.join(HERE,"coint_train.csv")); sig=sig[sig.train_adf_p<0.05]

# precompute single-split OOS series + train sharpe
series={}; tsh={}
for _,r in sig.iterrows():
    A,B=r.A,r.B; sub=logp[[A,B]].dropna(); sp=len(sub)//2
    d_tr,_=backtest_spread(sub[A].iloc[:sp],sub[B].iloc[:sp],r.beta)
    d_te,_=backtest_spread(sub[A].iloc[sp:],sub[B].iloc[sp:],r.beta)
    tsh[f"{A}/{B}"]=perf(d_tr)["sharpe"]; series[f"{A}/{B}"]=d_te
pf=pd.DataFrame(series); tsh=pd.Series(tsh)
names=list(pf.columns)

print("="*90)
print("1) NULL: top-10-by-train-Sharpe vs 5000 random 10-pair portfolios (all from coint set)")
print("="*90)
top10=tsh.sort_values(ascending=False).head(10).index.tolist()
sel=perf(pf[top10].mean(axis=1).dropna())["sharpe"]
rng=np.random.default_rng(0); dist=[]
for _ in range(5000):
    pick=rng.choice(names,10,replace=False)
    dist.append(perf(pf[list(pick)].mean(axis=1).dropna())["sharpe"])
dist=np.array(dist)
pct=(dist<sel).mean()*100
print(f"  Selected top-10 OOS Sharpe = {sel:+.2f}")
print(f"  Random 10-pair dist: mean {dist.mean():+.2f}  median {np.median(dist):+.2f}  p5 {np.percentile(dist,5):+.2f}  p95 {np.percentile(dist,95):+.2f}")
print(f"  Selection percentile vs random = {pct:.1f}%  (p-value selection adds nothing = {(dist>=sel).mean():.3f})")
print()

print("="*90)
print("2) ALL-PAIRS baseline (trade every coint pair OOS, equal weight) — is the spread-reversion")
print("   edge present even WITHOUT cherry-picking?")
print("="*90)
allp=perf(pf.mean(axis=1).dropna())
print(f"  All {len(names)} coint pairs OOS Sharpe = {allp['sharpe']:+.2f}  total {allp['total']:+.3f}")
print(f"  (Recall single-split portfolio earlier = 0.41; per-pair median OOS Sharpe = {pf.apply(lambda c: perf(c.dropna())['sharpe']).median():+.2f})")
print()

print("="*90)
print("3) PURGED walk-forward (drop first 30 OOS days/block to kill any warmup leak), 6 folds, top-10")
print("="*90)
full=logp.index; n=len(full); folds=6; block=n//(folds+1)
chain=[]; frows=[]
for k in range(1,folds+1):
    tr_end=block*k; te_end=min(block*(k+1),n)
    tr_idx=full[:tr_end]; te_idx=full[tr_end:te_end]
    if len(te_idx)<60: continue
    cand=[]
    for A,B in pairs:
        sub=logp[[A,B]].reindex(tr_idx).dropna()
        if len(sub)<250: continue
        a,beta,pv=eg_pvalue(sub[A].values,sub[B].values)
        if pv>=0.05: continue
        d,_=backtest_spread(sub[A],sub[B],beta); cand.append((f"{A}/{B}",A,B,beta,perf(d)["sharpe"]))
    cand.sort(key=lambda x:-x[4]); picks=cand[:10]
    bs={}
    for name,A,B,beta,_ in picks:
        seg_idx=full[max(0,tr_end-30):te_end]
        seg=logp[[A,B]].reindex(seg_idx).dropna()
        if len(seg)<45: continue
        d,_=backtest_spread(seg[A],seg[B],beta)
        # PURGE: only keep OOS days AFTER first 30 days of the test block (no warmup overlap)
        keep=te_idx[30:]
        d=d.reindex(keep).dropna()
        bs[name]=d
    if not bs: continue
    bp=pd.DataFrame(bs).mean(axis=1).dropna(); chain.append(bp)
    frows.append(dict(fold=k,oos_sharpe=round(perf(bp)['sharpe'],2),total=round(perf(bp)['total'],3),days=perf(bp)['n']))
fdf=pd.DataFrame(frows); print(fdf.to_string(index=False))
ch=pd.concat(chain).sort_index(); cp=perf(ch)
arr=ch.values; bsr=[np.random.choice(arr,len(arr)).mean()/(np.random.choice(arr,len(arr)).std()+1e-12)*np.sqrt(365) for _ in range(3000)]
print(f"  PURGED chained WF Sharpe {cp['sharpe']:+.2f}  total {cp['total']:+.3f}  folds+ {(fdf.oos_sharpe>0).sum()}/{len(fdf)}")

print()
print("="*90)
print("4) SUBPERIOD: chained WF excluding the big final fold (fold 6)")
print("="*90)
ch_no6=pd.concat(chain[:-1]).sort_index() if len(chain)>1 else ch
print(f"  WF Sharpe w/o last fold: {perf(ch_no6)['sharpe']:+.2f}  total {perf(ch_no6)['total']:+.3f}  days {perf(ch_no6)['n']}")
