#!/usr/bin/env python3
"""ADVERSARIAL re-derivation of the apparent survivors. The session's recurring
failure: an edge that lives in ONE sub-period (here strongly suspected: the
parabolic early-2021 alt bull + the 2021 'na' SMA-warmup window).

For the top candidates from each family, re-run with:
  A) drop the 'na' regime entirely (no trades before BTC 200d SMA is defined,
     i.e. exclude ~first 200 days = the 2021 parabola)
  B) ALSO drop calendar 2021 entirely (start 2022-01-01) -> pure post-bubble
  C) winsorize per-trade returns at 1/99 pct (kill single-trade moonshots)
  D) report per-CALENDAR-YEAR mean net (the honest regime cut) so we see if
     it's positive in MULTIPLE years or just 2021/2023.
Judged: full-sample CI>0 AND positive in a MAJORITY of calendar years AND
the post-2021 subsample CI>0.
"""
import numpy as np, pandas as pd
from engine import load, SYMBOLS, evaluate, bootstrap_ci, btc_regime
import test1_tsm, test2_trend, test3_xsec

FEE=0.00066

def yearly(trades):
    df=pd.DataFrame(trades); df["net"]=df["ret"]-FEE
    df["yr"]=pd.to_datetime(df["entry_dt"]).dt.year
    out={}
    for y,g in df.groupby("yr"):
        out[int(y)]=(len(g), float(g["net"].mean()*1e4))
    return out

def winsorize(trades, lo=1, hi=99):
    df=pd.DataFrame(trades)
    a,b=np.percentile(df["ret"],[lo,hi])
    df["ret"]=df["ret"].clip(a,b)
    return df.to_dict("records")

def subsample(trades, start=None, drop_na=False):
    out=[]
    for t in trades:
        if drop_na and t["regime"]=="na": continue
        if start and pd.Timestamp(t["entry_dt"]).tz_localize(None) < pd.Timestamp(start): continue
        out.append(t)
    return out

def report(name, trades):
    print(f"\n##### {name} #####  (raw n={len(trades)})")
    # full
    full=evaluate(trades, name+" FULL")
    print(f"  FULL      n={full['n']:5} net {full['mean_base_bps']:7.1f}bps CI[{full['ci_base_bps'][0]:7.1f},{full['ci_base_bps'][1]:7.1f}]")
    # winsorized
    w=evaluate(winsorize(trades), name+" wins")
    print(f"  WINSOR1/99 n={w['n']:5} net {w['mean_base_bps']:7.1f}bps CI[{w['ci_base_bps'][0]:7.1f},{w['ci_base_bps'][1]:7.1f}]")
    # drop na
    dn=subsample(trades, drop_na=True)
    if dn:
        r=evaluate(dn, name+" no-na")
        print(f"  DROP 'na'  n={r['n']:5} net {r['mean_base_bps']:7.1f}bps CI[{r['ci_base_bps'][0]:7.1f},{r['ci_base_bps'][1]:7.1f}]")
    # post-2021
    p22=subsample(trades, start="2022-01-01")
    if p22:
        r=evaluate(p22, name+" >=2022")
        print(f"  >=2022     n={r['n']:5} net {r['mean_base_bps']:7.1f}bps CI[{r['ci_base_bps'][0]:7.1f},{r['ci_base_bps'][1]:7.1f}]")
    # post-2021 winsorized -- the harshest
    if p22:
        r=evaluate(winsorize(p22), name+" >=2022 wins")
        print(f"  >=2022 wins n={r['n']:4} net {r['mean_base_bps']:7.1f}bps CI[{r['ci_base_bps'][0]:7.1f},{r['ci_base_bps'][1]:7.1f}]")
    # yearly
    yr=yearly(trades)
    ys=" ".join(f"{y}:{v[1]:.0f}({v[0]})" for y,v in sorted(yr.items()))
    npos=sum(1 for y,v in yr.items() if v[1]>0 and v[0]>=10)
    ntot=sum(1 for y,v in yr.items() if v[0]>=10)
    print(f"  YEARLY net bps (n): {ys}")
    print(f"  positive years (n>=10): {npos}/{ntot}")

def main():
    # TSM top
    report("TSM N=7 M=7", test1_tsm.tsm_trades(7,7,SYMBOLS))
    report("TSM N=1 M=7", test1_tsm.tsm_trades(1,7,SYMBOLS))
    # Trend top
    report("MAx 20/50 L/S", test2_trend.ma_cross(20,50,SYMBOLS,True))
    report("MAx 10/30 long", test2_trend.ma_cross(10,30,SYMBOLS,False))
    report("Donchian 20 long", test2_trend.donchian(20,SYMBOLS,False))
    # XS top (long_short flag is 5th positional arg: True=L/S, False=long-only)
    report("XS L7 k3 H14 long", test3_xsec.xsec(7,3,14,SYMBOLS,False))
    report("XS L7 k2 H14 L/S", test3_xsec.xsec(7,2,14,SYMBOLS,True))
    report("XS L14 k3 H14 L/S", test3_xsec.xsec(14,3,14,SYMBOLS,True))

if __name__=="__main__":
    main()
