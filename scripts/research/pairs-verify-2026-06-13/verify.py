#!/usr/bin/env python3
"""
INDEPENDENT re-derivation of the pairs/cointegration edge claim.
Written from scratch (own backtest engine), data re-fetched via fetch.py.

Tests:
  P1.1  Selection result: top-N by TRAIN spread-Sharpe vs RANDOM -> OOS Sharpe + permutation p.
  P1.1b Predictiveness: corr(train Sharpe, OOS Sharpe).
  P1.2  THE SKEPTICAL TEST: many-fold walk-forward, per-fold contribution,
        confirm/deny "73% from recent 9 months". Plus: does selection survive a
        SECOND independent OOS window (held out from method choice)?
  P1.3  Survivorship: include dead/laggard coins; reason + measure.
  P1.4  Costs: maker 0.02% & taker 0.12%/leg, 2 legs.
  P2    Backtest over OUR live window 2026-04-07 -> 2026-06-13. Sharpe/PnL there.
        Which live-traded symbols appear in viable pairs.
"""
import os, itertools
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
RNG = np.random.default_rng(20260613)

# ---- our live window (from entry_snapshots.jsonl: 2026-04-07 -> 2026-06-13) ----
LIVE_START = pd.Timestamp("2026-04-07", tz="UTC")
LIVE_END   = pd.Timestamp("2026-06-13", tz="UTC")

# strategy params fixed a priori (same family as prior work; standard z-reversion)
ZWIN, ENTRY, EXITZ, MAXHOLD = 20, 2.0, 0.5, 60

def load_panel(min_rows=300):
    closes={}
    for f in sorted(os.listdir(DATA)):
        if not f.endswith(".csv"): continue
        sym=f[:-4]
        df=pd.read_csv(os.path.join(DATA,f),parse_dates=["dt"])
        if len(df)<min_rows: continue
        closes[sym]=df.drop_duplicates("dt").set_index("dt")["close"].sort_index()
    panel=pd.DataFrame(closes)
    full=pd.date_range(panel.index.min(),panel.index.max(),freq="D",tz="UTC")
    return panel.reindex(full)

def ols(y,x):
    X=np.column_stack([np.ones_like(x),x])
    coef,*_=np.linalg.lstsq(X,y,rcond=None)
    a,b=coef
    return a,b,y-(a+b*x)

def adf_p(resid):
    try: return adfuller(resid,maxlag=1,regression="c",autolag=None)[1]
    except Exception: return 1.0

def backtest(logA,logB,beta,fee_leg,zwin=ZWIN,entry=ENTRY,exitz=EXITZ,maxhold=MAXHOLD):
    """z-reversion on spread = logA - beta*logB. Daily dollar-neutral log-returns.
    Cost = 2 legs * fee at entry and 2 legs at exit."""
    spread=logA-beta*logB
    s=pd.Series(spread)
    z=(s-s.rolling(zwin).mean())/s.rolling(zwin).std()
    retA=logA.diff(); retB=logB.diff()
    pos=0; eidx=None; pnl=np.zeros(len(s)); idx=s.index; trades=0
    for i in range(1,len(s)):
        if pos!=0:
            pnl[i]+=pos*(retA.iloc[i]-beta*retB.iloc[i])
        zi=z.iloc[i]
        if np.isnan(zi): continue
        if pos==0:
            if zi>entry: pos=-1; eidx=i
            elif zi<-entry: pos=1; eidx=i
            if pos!=0: pnl[i]-=2*fee_leg
        else:
            held=i-eidx
            if (abs(zi)<exitz) or (held>=maxhold) or (pos==1 and zi>entry) or (pos==-1 and zi<-entry):
                pnl[i]-=2*fee_leg; trades+=1; pos=0; eidx=None
    return pd.Series(pnl,index=idx), trades

def perf(d,ann=365):
    d=d.dropna()
    if len(d)<2 or d.std()==0: return dict(sharpe=0.0,total=float(d.sum()),n=len(d))
    return dict(sharpe=float(d.mean()/d.std()*np.sqrt(ann)),total=float(d.sum()),n=len(d))

def main():
    panel=load_panel()
    logp=np.log(panel)
    syms=list(panel.columns)
    print(f"UNIVERSE: {len(syms)} symbols  {panel.index.min().date()} -> {panel.index.max().date()} ({len(panel)} days)")
    print(f"  symbols: {syms}\n")
    pairs=list(itertools.combinations(syms,2))
    TAKER=0.0012; MAKER=0.0002

    # ============ P1.1 selection vs random on a single train/test split ============
    print("="*94)
    print("P1.1  TRAIN(50%)->TEST(50%): cointegrate on train, backtest OOS. Selection vs RANDOM.")
    print("="*94)
    MINOV=400
    rows=[]
    for A,B in pairs:
        sub=logp[[A,B]].dropna()
        if len(sub)<2*MINOV: continue
        split=len(sub)//2
        tr,te=sub.iloc[:split],sub.iloc[split:]
        if len(tr)<MINOV or len(te)<MINOV: continue
        a,beta,resid=ols(tr[A].values,tr[B].values)
        pv=adf_p(resid)
        d_tr,_=backtest(tr[A],tr[B],beta,TAKER)
        d_te,nt=backtest(te[A],te[B],beta,TAKER)
        d_te_m,_=backtest(te[A],te[B],beta,MAKER)
        rows.append(dict(pair=f"{A}/{B}",adf_p=pv,beta=beta,
                         tr_sharpe=perf(d_tr)["sharpe"],
                         te_sharpe=perf(d_te)["sharpe"],te_total=perf(d_te)["total"],te_trades=nt,
                         te_sharpe_maker=perf(d_te_m)["sharpe"]))
    df=pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE,"split_results.csv"),index=False)
    coint=df[df.adf_p<0.05].copy()
    print(f"pairs tested: {len(df)}   cointegrating in TRAIN (ADF p<0.05): {len(coint)}\n")

    # selection rule: among coint pairs, top-N by TRAIN Sharpe -> measure mean OOS Sharpe
    sel_pool=coint.sort_values("tr_sharpe",ascending=False)
    def mean_oos(subset): return subset.te_sharpe.mean()
    for N in [5,10,20]:
        sel=sel_pool.head(N)
        # random baseline: N random pairs from ALL tested (not just coint), many draws
        rand=[mean_oos(df.sample(N,random_state=int(RNG.integers(1e9)))) for _ in range(2000)]
        rand=np.array(rand); sel_val=mean_oos(sel)
        p=(rand>=sel_val).mean()
        print(f"  Top-{N} by TRAIN-Sharpe (coint pairs): mean OOS Sharpe = {sel_val:+.3f}")
        print(f"     RANDOM-{N} mean OOS Sharpe = {rand.mean():+.3f} (sd {rand.std():.3f}); permutation p(random>=selected) = {p:.4f}")
    # predictiveness
    c=np.corrcoef(coint.tr_sharpe,coint.te_sharpe)[0,1]
    cap=np.corrcoef(coint.adf_p,coint.te_sharpe)[0,1]
    print(f"\n  corr(TRAIN Sharpe, OOS Sharpe) among coint pairs = {c:+.3f}   (want >0 for selection to work)")
    print(f"  corr(TRAIN ADF p, OOS Sharpe)               = {cap:+.3f}   (want <0)")
    # equal-weight portfolio of all coint pairs OOS
    print()

    # ============ P1.2 MANY-FOLD WALK-FORWARD + concentration ============
    print("="*94)
    print("P1.2  WALK-FORWARD: 10 expanding folds. Re-fit coint+beta on past, pick top-10 by")
    print("      trailing train Sharpe, trade next block OOS, chain. TAKER costs.")
    print("="*94)
    full=logp.index; n=len(full); NF=10; block=n//(NF+1)
    fold_rows=[]; oos_chunks=[]
    for k in range(1,NF+1):
        tr_end=block*k; te_end=min(block*(k+1),n)
        tr_idx=full[:tr_end]; te_idx=full[tr_end:te_end]
        if len(te_idx)<20: continue
        cand=[]
        for A,B in pairs:
            sub=logp[[A,B]].reindex(tr_idx).dropna()
            if len(sub)<200: continue
            a,beta,resid=ols(sub[A].values,sub[B].values)
            if adf_p(resid)>=0.05: continue
            sh=perf(backtest(sub[A],sub[B],beta,TAKER)[0])["sharpe"]
            cand.append((f"{A}/{B}",A,B,beta,sh))
        cand.sort(key=lambda x:-x[4]); picks=cand[:10]
        bs={}
        for name,A,B,beta,sh in picks:
            warm=ZWIN+5
            seg_idx=full[max(0,tr_end-warm):te_end]
            seg=logp[[A,B]].reindex(seg_idx).dropna()
            if len(seg)<warm+10: continue
            d,_=backtest(seg[A],seg[B],beta,TAKER)
            d=d.reindex(te_idx).dropna()
            if len(d): bs[name]=d
        if not bs: continue
        port=pd.DataFrame(bs).mean(axis=1).dropna()
        p=perf(port); oos_chunks.append(port)
        fold_rows.append(dict(fold=k,test=f"{te_idx[0].date()}->{te_idx[-1].date()}",
                              npicks=len(bs),sharpe=round(p["sharpe"],2),total=round(p["total"],4),days=p["n"]))
    fdf=pd.DataFrame(fold_rows)
    print(fdf.to_string(index=False))
    chained=pd.concat(oos_chunks).sort_index()
    cp=perf(chained)
    # concentration
    tot=fdf.total.sum()
    fdf["pct_of_profit"]=(fdf.total/tot*100).round(1)
    print("\n  per-fold % of total chained profit:")
    print(fdf[["fold","test","total","pct_of_profit"]].to_string(index=False))
    last_share=fdf.total.iloc[-1]/tot*100 if tot!=0 else float('nan')
    last2_share=fdf.total.iloc[-2:].sum()/tot*100 if tot!=0 else float('nan')
    print(f"\n  CHAINED WF Sharpe {cp['sharpe']:+.2f}  total {cp['total']:+.4f}  days {cp['n']}")
    print(f"  folds positive: {(fdf.sharpe>0).sum()}/{len(fdf)}")
    print(f"  final fold = {last_share:.0f}% of profit;  final 2 folds = {last2_share:.0f}% of profit")
    # ex-final-fold sharpe
    if len(oos_chunks)>1:
        ex=pd.concat(oos_chunks[:-1]).sort_index()
        print(f"  EX-FINAL-FOLD chained Sharpe: {perf(ex)['sharpe']:+.2f}  total {perf(ex)['total']:+.4f}")
    chained.to_csv(os.path.join(HERE,"chained_wf.csv"))

    # ============ P1.4 cost sensitivity on chained WF (re-run maker) ============
    print("\n"+"="*94)
    print("P1.4  COST SENSITIVITY (re-run walk-forward at MAKER 0.02%/leg)")
    print("="*94)
    oos_m=[]
    for k in range(1,NF+1):
        tr_end=block*k; te_end=min(block*(k+1),n)
        tr_idx=full[:tr_end]; te_idx=full[tr_end:te_end]
        if len(te_idx)<20: continue
        cand=[]
        for A,B in pairs:
            sub=logp[[A,B]].reindex(tr_idx).dropna()
            if len(sub)<200: continue
            a,beta,resid=ols(sub[A].values,sub[B].values)
            if adf_p(resid)>=0.05: continue
            sh=perf(backtest(sub[A],sub[B],beta,MAKER)[0])["sharpe"]
            cand.append((f"{A}/{B}",A,B,beta,sh))
        cand.sort(key=lambda x:-x[4]); picks=cand[:10]
        bs={}
        for name,A,B,beta,sh in picks:
            warm=ZWIN+5; seg_idx=full[max(0,tr_end-warm):te_end]
            seg=logp[[A,B]].reindex(seg_idx).dropna()
            if len(seg)<warm+10: continue
            d,_=backtest(seg[A],seg[B],beta,MAKER); d=d.reindex(te_idx).dropna()
            if len(d): bs[name]=d
        if bs: oos_m.append(pd.DataFrame(bs).mean(axis=1).dropna())
    cm=pd.concat(oos_m).sort_index()
    print(f"  MAKER chained WF Sharpe {perf(cm)['sharpe']:+.2f}  total {perf(cm)['total']:+.4f}")
    print(f"  TAKER chained WF Sharpe {cp['sharpe']:+.2f}  total {cp['total']:+.4f}")

    # ============ P2  OUR LIVE WINDOW ============
    print("\n"+"="*94)
    print(f"P2  OUR LIVE WINDOW {LIVE_START.date()} -> {LIVE_END.date()}")
    print("="*94)
    # Pick pairs the way you'd have to in real time: cointegrate + select on data BEFORE live start.
    pre_idx=full[full<LIVE_START]
    live_idx=full[(full>=LIVE_START)&(full<=LIVE_END)]
    print(f"  pre-live training days: {len(pre_idx)}   live days: {len(live_idx)}")
    cand=[]
    for A,B in pairs:
        sub=logp[[A,B]].reindex(pre_idx).dropna()
        if len(sub)<300: continue
        a,beta,resid=ols(sub[A].values,sub[B].values)
        if adf_p(resid)>=0.05: continue
        sh=perf(backtest(sub[A],sub[B],beta,TAKER)[0])["sharpe"]
        cand.append((f"{A}/{B}",A,B,beta,sh))
    cand.sort(key=lambda x:-x[4]); picks=cand[:10]
    print(f"  coint pairs (pre-live): {len(cand)}; trading top-10 by pre-live Sharpe:")
    bs={}; bs_m={}
    for name,A,B,beta,sh in picks:
        warm=ZWIN+5
        seg_idx=full[(full>=LIVE_START-pd.Timedelta(days=warm))&(full<=LIVE_END)]
        seg=logp[[A,B]].reindex(seg_idx).dropna()
        if len(seg)<warm+5: continue
        d,_=backtest(seg[A],seg[B],beta,TAKER); d=d.reindex(live_idx).dropna()
        dm,_=backtest(seg[A],seg[B],beta,MAKER); dm=dm.reindex(live_idx).dropna()
        if len(d): bs[name]=d; bs_m[name]=dm
        print(f"     {name:14s} pre-live Sharpe {sh:+.2f}")
    if bs:
        port=pd.DataFrame(bs).mean(axis=1).dropna()
        portm=pd.DataFrame(bs_m).mean(axis=1).dropna()
        p=perf(port)
        print(f"\n  LIVE-WINDOW portfolio (TAKER): Sharpe {p['sharpe']:+.2f}  total log-pnl {p['total']:+.4f}  days {p['n']}")
        print(f"  LIVE-WINDOW portfolio (MAKER): Sharpe {perf(portm)['sharpe']:+.2f}  total {perf(portm)['total']:+.4f}")
    else:
        print("  no tradable pairs over live window")

    # which live-traded symbols appear in viable pairs (coint pre-live)?
    live_syms={"BTC","ETH","SOL","INJ","ARB","DOGE","BNB","XRP","SUI","OP","RENDER","TIA","LINK","FET","XLM","ADA","AAVE","NEAR"}
    viable_syms=set()
    for name,A,B,beta,sh in cand:
        viable_syms.add(A); viable_syms.add(B)
    overlap=sorted(live_syms & viable_syms)
    print(f"\n  Live-traded symbols that appear in ANY coint (pre-live) pair: {overlap}")
    pairs_with_live=[c[0] for c in cand if (c[1] in live_syms or c[2] in live_syms)]
    print(f"  # coint pre-live pairs containing a live-traded symbol: {len(pairs_with_live)}")
    print(f"     examples: {pairs_with_live[:12]}")

if __name__=="__main__":
    main()
