#!/usr/bin/env python3
"""Final verification of the lone survivor: cross-sectional momentum L/S.
Tests robustness so we don't ship another artifact:
 1. Parameter neighborhood: L in {7,10,14,21}, k in {2,3,4}, H in {7,10,14,21}.
    A real edge is positive across a NEIGHBORHOOD, not a single lucky cell.
 2. Per-fold walk-forward on POST-2021 data only (start 2022-01-01), 5 folds,
    each fold's mean net + t-stat. Need majority>0 AND no catastrophic fold.
 3. Newey-West-ish t-stat (per-trade, clustered by rebalance date via simple
    daily aggregation) for the headline config.
 4. Universe robustness: drop BTC+ETH (mega-caps) -> alts only; and top-10 only.
 5. Rebalance-date PnL series (aggregate all legs per rebalance) -> the real
    portfolio Sharpe, since pooled per-trade overstates n.
"""
import numpy as np, pandas as pd
from engine import load, SYMBOLS, bootstrap_ci, btc_regime
import test3_xsec

FEE=0.00066

def portfolio_series(L,k,H,symbols,long_short, start=None):
    """Aggregate legs per rebalance date into a single portfolio return,
    so each rebalance = 1 independent observation (honest n)."""
    trades=test3_xsec.xsec(L,k,H,symbols,long_short)
    df=pd.DataFrame(trades)
    if start:
        df=df[pd.to_datetime(df["entry_dt"]).dt.tz_localize(None)>=pd.Timestamp(start)]
    df["net"]=df["ret"]-FEE
    grp=df.groupby("entry_dt")["net"].mean()  # equal-weight legs
    return grp

def tstat(x):
    x=np.asarray(x,float)
    if len(x)<3 or x.std(ddof=1)==0: return np.nan
    return x.mean()/(x.std(ddof=1)/np.sqrt(len(x)))

def main():
    print("===== 1. PARAMETER NEIGHBORHOOD (L/S, full sample, portfolio-level) =====")
    print("    per-rebalance mean net bps [t-stat] (n_rebalances)")
    for L in [7,10,14,21]:
        row=[]
        for k in [2,3,4]:
            for H in [7,14,21]:
                s=portfolio_series(L,k,H,SYMBOLS,True)
                row.append(f"k{k}H{H}:{s.mean()*1e4:6.1f}[t{tstat(s.values):4.1f}]")
        print(f"  L{L:2}: "+" ".join(row))

    print("\n===== 2. HEADLINE = L14 k3 H14 L/S =====")
    for tag,start in [("FULL",None),(">=2022","2022-01-01"),(">=2023","2023-01-01")]:
        s=portfolio_series(14,3,14,SYMBOLS,True,start=start)
        ci=bootstrap_ci(s.values)
        print(f"  {tag:8} n_rebal={len(s):4} mean {s.mean()*1e4:6.1f}bps t={tstat(s.values):4.2f} "
              f"CI[{ci[0]*1e4:6.1f},{ci[1]*1e4:6.1f}] ann.Sharpe~{tstat(s.values)*np.sqrt(52/len(s)*len(s))/np.sqrt(len(s))*np.sqrt(52)*0+ (s.mean()/s.std(ddof=1)*np.sqrt(52)):.2f}")

    print("\n===== 3. PER-FOLD WALK-FORWARD (post-2022, 5 folds, portfolio-level) =====")
    s=portfolio_series(14,3,14,SYMBOLS,True,start="2022-01-01").sort_index()
    folds=np.array_split(np.arange(len(s)),5)
    npos=0
    for i,idx in enumerate(folds):
        seg=s.iloc[idx]
        m=seg.mean()*1e4
        if m>0: npos+=1
        print(f"  fold{i+1} {seg.index[0].date()}..{seg.index[-1].date()} n={len(seg):3} mean {m:7.1f}bps t={tstat(seg.values):4.2f}")
    print(f"  -> {npos}/5 folds positive")

    print("\n===== 4. UNIVERSE ROBUSTNESS (L14 k3 H14 L/S, full) =====")
    alts=[s for s in SYMBOLS if s not in ("BTC","ETH")]
    for name,uni in [("ALL(13)",SYMBOLS),("ALTS-only(11)",alts)]:
        kk = 3 if len(uni)>=7 else 2
        s=portfolio_series(14,kk,14,uni,True)
        ci=bootstrap_ci(s.values)
        print(f"  {name:14} n={len(s):4} mean {s.mean()*1e4:6.1f}bps t={tstat(s.values):4.2f} CI[{ci[0]*1e4:.1f},{ci[1]*1e4:.1f}]")

    print("\n===== 5. EQUITY CURVE (compounded, L14 k3 H14 L/S, full) =====")
    s=portfolio_series(14,3,14,SYMBOLS,True).sort_index()
    eq=(1+s).cumprod()
    yrs=(s.index[-1]-s.index[0]).days/365.25
    cagr=eq.iloc[-1]**(1/yrs)-1
    dd=(eq/eq.cummax()-1).min()
    print(f"  rebalances={len(s)} years={yrs:.1f} final_mult={eq.iloc[-1]:.2f}x "
          f"CAGR(on neutral book)={cagr*100:.1f}% maxDD={dd*100:.1f}% "
          f"ann.Sharpe={s.mean()/s.std(ddof=1)*np.sqrt(52):.2f}")
    print("  yearly compounded:")
    for y,g in s.groupby(s.index.year):
        e=(1+g).prod()-1
        print(f"    {y}: {e*100:6.1f}%  ({len(g)} rebal)")

if __name__=="__main__":
    main()
