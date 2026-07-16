#!/usr/bin/env python3
"""Honest walk-forward basket TSM test. READ-ONLY on repo data.

Data: scripts/research/htf-rigorous-2026-06-13/data/*_1d.csv
Source: binanceus primary (Binance-quality daily), gateio/htx fallback, from 2021-01-01.
Mechanism (pre-registered, matches deployed ETH_TSM_28 slot):
  - trailing L-day return; LONG if in top tercile of own EXPANDING PRIOR history
    (>= 66.667 pctl, current obs excluded, min_history=90); SIGN variant: long if trail>0.
  - min-hold H days; exit when signal leaves supporting tercile after min-hold, or -8% stop.
  - long-only primary; long/short variant (short if bottom tercile / trail<0).
  - taker cost 6 bps/side => charged on entry and on exit.
Portfolio: equal capital per coin over the FULL basket (inactive coin = 0 exposure).
Causal: tercile threshold at day t uses only trailing-returns strictly before t.
"""
import numpy as np, pandas as pd, os, sys
from scipy.stats import norm

DATA = "/Users/jonaspenaso/Desktop/Phmex-S/scripts/research/htf-rigorous-2026-06-13/data"
BASKET = ["BTC","ETH","SOL","BNB","ADA","DOGE","LTC","AVAX","LINK","DOT","ATOM","NEAR"]
COST_SIDE = 6.0/1e4
STOP = 0.08
ANN = 365.0

def load(sym):
    df = pd.read_csv(os.path.join(DATA, f"{sym}_1d.csv"), parse_dates=["dt"])
    df["dt"] = df["dt"].dt.tz_localize(None)
    return df.drop_duplicates("dt").sort_values("dt").reset_index(drop=True)

def coin_daily_returns(df, L, H, rule, direction, min_hist=90):
    """Daily strat return series for one coin (stop-capped, cost-charged) + trades.
    Decision at close t -> exposure established at close t, felt starting day t+1.
    No same-day re-entry after an exit (flat until next close decision)."""
    c=df["close"].values; lo=df["low"].values; hi=df["high"].values; n=len(c)
    trail=np.full(n,np.nan)
    for t in range(L,n): trail[t]=c[t]/c[t-L]-1.0
    sig=np.zeros(n,dtype=int); hist=[]
    for t in range(n):
        s=0
        if not np.isnan(trail[t]):
            if rule=="sign":
                if trail[t]>0: s=1
                elif trail[t]<0 and direction=="ls": s=-1
            else:
                if len(hist)>=min_hist:
                    if trail[t]>=np.percentile(hist,100*2/3): s=1
                    elif direction=="ls" and trail[t]<=np.percentile(hist,100*1/3): s=-1
            hist.append(trail[t])
        sig[t]=s
    r=np.zeros(n); expo=np.zeros(n)
    in_pos=0; entry_px=0.0; days=0; edir=0; trades=[]
    for t in range(1,n):
        exited=False
        if in_pos!=0:
            # exposure was established at close t-1 (or earlier); day t accrues.
            days+=1
            stop_px = entry_px*(1-STOP) if edir==1 else entry_px*(1+STOP)
            stopped = lo[t]<=stop_px if edir==1 else hi[t]>=stop_px
            expo[t]=1
            if stopped:
                r[t]+= edir*(stop_px/c[t-1]-1.0) - COST_SIDE
                trades.append({"reason":"stop","dir":edir,"days":days,"ret":edir*(stop_px/entry_px-1.0)})
                in_pos=0; edir=0; days=0; exited=True
            else:
                r[t]+= edir*(c[t]/c[t-1]-1.0)
                if days>=H and sig[t]!=edir:
                    r[t]-=COST_SIDE
                    trades.append({"reason":"sigoff","dir":edir,"days":days,"ret":edir*(c[t]/entry_px-1.0)})
                    in_pos=0; edir=0; days=0; exited=True
        # entry decision at close t (exposure into t+1); no re-entry the same day we exited
        if in_pos==0 and not exited and sig[t]!=0 and t<n-1:
            in_pos=sig[t]; edir=sig[t]; entry_px=c[t]; days=0
            r[t]-=COST_SIDE  # entry cost booked at close t
    return pd.Series(r,index=df["dt"]), pd.Series(expo,index=df["dt"]), trades

def run(basket,L=28,H=5,rule="tercile",direction="long"):
    rets={}; expos={}; alltr={}
    for s in basket:
        df=load(s); rr,ee,tr=coin_daily_returns(df,L,H,rule,direction)
        rets[s]=rr; expos[s]=ee; alltr[s]=tr
    idx=None
    for s in basket: idx=rets[s].index if idx is None else idx.union(rets[s].index)
    R=pd.DataFrame({s:rets[s].reindex(idx).fillna(0.0) for s in basket})
    E=pd.DataFrame({s:expos[s].reindex(idx).fillna(0.0) for s in basket})
    port=R.mean(axis=1)
    return port,R,E,alltr

def sharpe(x):
    x=np.asarray(x); return 0.0 if x.std()==0 else x.mean()/x.std()*np.sqrt(ANN)
def maxdd(eq):
    peak=np.maximum.accumulate(eq); return ((eq-peak)/peak).min()
def stats(port,label=""):
    eq=(1+port).cumprod();
    ann=(eq.iloc[-1])**(ANN/len(port))-1
    return {"label":label,"n_days":len(port),"ann_ret":ann,"sharpe":sharpe(port.values),
            "maxdd":maxdd(eq.values),"total_ret":eq.iloc[-1]-1}
def boot_sharpe(x,block=20,iters=3000,seed=1):
    rng=np.random.default_rng(seed); x=np.asarray(x); n=len(x); nb=int(np.ceil(n/block)); out=[]
    for _ in range(iters):
        st=rng.integers(0,n-block+1,nb)
        samp=np.concatenate([x[s:s+block] for s in st])[:n]
        if samp.std()>0: out.append(samp.mean()/samp.std()*np.sqrt(ANN))
    return np.percentile(out,[2.5,50,97.5])
def dsr(x,n_trials,sr_var_ann):
    x=np.asarray(x); T=len(x); sr=sharpe(x)/np.sqrt(ANN)
    g=pd.Series(x); sk=g.skew(); ku=g.kurt()+3
    v=sr_var_ann/ANN; emc=0.5772156649
    sr0=np.sqrt(v)*((1-emc)*norm.ppf(1-1/n_trials)+emc*norm.ppf(1-1/(n_trials*np.e))) if (n_trials>1 and v>0) else 0.0
    num=(sr-sr0)*np.sqrt(T-1); den=np.sqrt(1-sk*sr+((ku-1)/4)*sr**2)
    return {"sr_ann":sharpe(x),"sr0_ann":sr0*np.sqrt(ANN),"dsr":norm.cdf(num/den),"skew":sk}

if __name__=="__main__":
    pass
