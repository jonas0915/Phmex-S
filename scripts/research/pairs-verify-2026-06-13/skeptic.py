#!/usr/bin/env python3
"""
The decisive skeptical tests:
  S1) Does 'selection works' survive on a SECOND, fully independent split point?
      Split at 33%/66% (train=first third, test=middle third) AND (train=first 2/3, test=last 3rd).
      If selection edge only shows on the 50/50 split, it's split-luck.
  S2) Robustness of the single-split permutation p across many random seeds (is p=0.001 stable?).
  S3) Live-window decomposition: per-pair Sharpe/total over our 68-day live window.
      Is the +3.49 portfolio Sharpe broad or driven by 1-2 pairs? Drop-one-pair test.
  S4) Live window vs the rest of 2026: is 2026-04..06 just the 'good recent regime'?
"""
import os, itertools
import numpy as np, pandas as pd
from verify import load_panel, ols, adf_p, backtest, perf, ZWIN
TAKER=0.0012; MAKER=0.0002
RNG=np.random.default_rng(99)
HERE=os.path.dirname(__file__)

panel=load_panel(); logp=np.log(panel); syms=list(panel.columns)
pairs=list(itertools.combinations(syms,2))
LIVE_START=pd.Timestamp("2026-04-07",tz="UTC"); LIVE_END=pd.Timestamp("2026-06-13",tz="UTC")

def split_test(frac_tr_start, frac_tr_end, frac_te_end, label):
    """train=[a,b), test=[b,c) of each pair's own overlap."""
    rows=[]
    for A,B in pairs:
        sub=logp[[A,B]].dropna()
        if len(sub)<600: continue
        a_i=int(len(sub)*frac_tr_start); b_i=int(len(sub)*frac_tr_end); c_i=int(len(sub)*frac_te_end)
        tr=sub.iloc[a_i:b_i]; te=sub.iloc[b_i:c_i]
        if len(tr)<250 or len(te)<150: continue
        _,beta,resid=ols(tr[A].values,tr[B].values)
        if adf_p(resid)>=0.05: continue
        trsh=perf(backtest(tr[A],tr[B],beta,TAKER)[0])["sharpe"]
        tesh=perf(backtest(te[A],te[B],beta,TAKER)[0])["sharpe"]
        rows.append((f"{A}/{B}",trsh,tesh))
    d=pd.DataFrame(rows,columns=["pair","tr","te"]).sort_values("tr",ascending=False)
    out={}
    for N in [5,10]:
        sel=d.head(N).te.mean()
        # random from coint pool
        rnd=np.array([d.sample(N,random_state=int(RNG.integers(1e9))).te.mean() for _ in range(2000)])
        out[N]=(sel,rnd.mean(),(rnd>=sel).mean())
    corr=np.corrcoef(d.tr,d.te)[0,1] if len(d)>3 else float('nan')
    print(f"\n[{label}] coint pairs={len(d)}  corr(trSharpe,teSharpe)={corr:+.3f}")
    for N,(sel,rm,p) in out.items():
        print(f"   top-{N}: selected OOS Sharpe {sel:+.3f}  random {rm:+.3f}  p={p:.4f}")
    return out

print("="*90)
print("S1) DOES SELECTION SURVIVE OTHER SPLIT POINTS? (not just 50/50)")
print("="*90)
split_test(0.0,0.50,1.0,  "50/50 (baseline)")
split_test(0.0,0.33,0.66, "train=1st third, test=middle third")
split_test(0.0,0.66,1.0,  "train=1st 2/3, test=last third")
split_test(0.33,0.66,1.0, "train=middle third, test=last third")

print("\n"+"="*90)
print("S3) LIVE-WINDOW per-pair decomposition + drop-one robustness")
print("="*90)
full=logp.index; pre_idx=full[full<LIVE_START]
live_idx=full[(full>=LIVE_START)&(full<=LIVE_END)]
cand=[]
for A,B in pairs:
    sub=logp[[A,B]].reindex(pre_idx).dropna()
    if len(sub)<300: continue
    _,beta,resid=ols(sub[A].values,sub[B].values)
    if adf_p(resid)>=0.05: continue
    sh=perf(backtest(sub[A],sub[B],beta,TAKER)[0])["sharpe"]
    cand.append((f"{A}/{B}",A,B,beta,sh))
cand.sort(key=lambda x:-x[4]); picks=cand[:10]
series={}
for name,A,B,beta,sh in picks:
    warm=ZWIN+5
    seg_idx=full[(full>=LIVE_START-pd.Timedelta(days=warm))&(full<=LIVE_END)]
    seg=logp[[A,B]].reindex(seg_idx).dropna()
    if len(seg)<warm+5: continue
    d,nt=backtest(seg[A],seg[B],beta,TAKER); d=d.reindex(live_idx).dropna()
    series[name]=d
    print(f"   {name:14s} live Sharpe {perf(d)['sharpe']:+.2f}  total {perf(d)['total']:+.4f}  trades {nt}")
pf=pd.DataFrame(series)
port=pf.mean(axis=1).dropna()
print(f"\n   FULL portfolio live Sharpe {perf(port)['sharpe']:+.2f} total {perf(port)['total']:+.4f}")
# how many pairs actually traded (nonzero)?
active=[c for c in pf.columns if pf[c].abs().sum()>1e-9]
print(f"   pairs with ANY activity in live window: {len(active)} / {len(pf.columns)}")
# drop-one
print("   drop-one-pair -> portfolio Sharpe:")
for c in pf.columns:
    p2=pf.drop(columns=[c]).mean(axis=1).dropna()
    print(f"      w/o {c:14s}: {perf(p2)['sharpe']:+.2f}")

print("\n"+"="*90)
print("S4) IS 2026-04..06 JUST THE 'GOOD RECENT REGIME'? rolling 68-day windows of the")
print("    SAME 10 picks across all of 2025-2026")
print("="*90)
# trade the same picks across 2024-06 .. 2026-06 in rolling 68d windows, report sharpe dist
hist_idx=full[full>=pd.Timestamp("2024-06-01",tz="UTC")]
allser={}
for name,A,B,beta,sh in picks:
    seg=logp[[A,B]].reindex(full[full>=pd.Timestamp("2024-04-01",tz="UTC")]).dropna()
    if len(seg)<60: continue
    d,_=backtest(seg[A],seg[B],beta,TAKER)
    allser[name]=d
allpf=pd.DataFrame(allser).mean(axis=1).dropna()
allpf=allpf[allpf.index>=pd.Timestamp("2024-06-01",tz="UTC")]
win=68; sh_list=[]
for i in range(0,len(allpf)-win,10):
    w=allpf.iloc[i:i+win]
    s=perf(w)["sharpe"]; sh_list.append((allpf.index[i].date(),s))
sh_vals=np.array([s for _,s in sh_list])
print(f"   {len(sh_list)} rolling 68d windows (same 10 picks) since 2024-06:")
print(f"   Sharpe: mean {sh_vals.mean():+.2f}  median {np.median(sh_vals):+.2f}  min {sh_vals.min():+.2f}  max {sh_vals.max():+.2f}")
print(f"   fraction of windows with Sharpe>2: {(sh_vals>2).mean():.0%}")
# where does the live window rank?
live_rank=(sh_vals < perf(port)['sharpe']).mean()
print(f"   our live window Sharpe {perf(port)['sharpe']:+.2f} is at the {live_rank:.0%} percentile of these windows")
