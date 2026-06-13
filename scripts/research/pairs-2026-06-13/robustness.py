#!/usr/bin/env python3
"""
Adversarial robustness checks on the walk-forward edge:
 1. Leave-one-pair-out on the top-N OOS portfolio: is one pair carrying it?
 2. Per-pair OOS contribution in walk-forward.
 3. Parameter robustness grid: zwin {15,20,30}, entry {1.5,2,2.5}, exit {0.0,0.5,1.0}.
    Report OOS (held-out test half) selectable top-10 portfolio Sharpe for each.
 4. Cost stress: taker 0.12 vs maker 0.02 vs pessimistic 0.20 per leg.
 5. Pick stability across walk-forward folds (turnover of selected pairs).
 6. Trade frequency / holding period sanity.
"""
import os, itertools
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller
from pairs_scan import load_daily, eg_pvalue, backtest_spread, perf

np.random.seed(11)
HERE = os.path.dirname(__file__)

panel = load_daily()
logp = np.log(panel)
syms = list(panel.columns)
pairs = list(itertools.combinations(syms, 2))

# ---- build sig set (train-cointegrated, single 50/50 split) ----
sig = pd.read_csv(os.path.join(HERE, "coint_train.csv"))
sig = sig[sig.train_adf_p < 0.05]

def build_series(zwin=20, entry=2.0, exit=0.5, fee=0.0012):
    series_te, train_sharpe, ntr = {}, {}, {}
    for _, r in sig.iterrows():
        A,B = r.A, r.B
        sub = logp[[A,B]].dropna()
        split = len(sub)//2
        d_tr,t_tr = backtest_spread(sub[A].iloc[:split], sub[B].iloc[:split], r.beta, zwin,entry,exit,fee)
        d_te,t_te = backtest_spread(sub[A].iloc[split:], sub[B].iloc[split:], r.beta, zwin,entry,exit,fee)
        train_sharpe[f"{A}/{B}"] = perf(d_tr)["sharpe"]
        series_te[f"{A}/{B}"] = d_te
        ntr[f"{A}/{B}"] = len(t_te)
    return pd.Series(train_sharpe), pd.DataFrame(series_te), ntr

ts, pf, ntr = build_series()
top10 = ts.sort_values(ascending=False).head(10).index.tolist()
port = pf[top10].mean(axis=1).dropna()
base = perf(port)["sharpe"]

print("="*90)
print("1) LEAVE-ONE-PAIR-OUT on Top-10 (single split) OOS portfolio. Base Sharpe = %.2f" % base)
print("="*90)
rows=[]
for p in top10:
    rest = [x for x in top10 if x!=p]
    s = perf(pf[rest].mean(axis=1).dropna())["sharpe"]
    rows.append((p, round(s,2), round(s-base,2), perf(pf[p].dropna())["sharpe"], ntr[p]))
loo = pd.DataFrame(rows, columns=["dropped","sharpe_wo","delta","pair_solo_sharpe","trades"]).sort_values("delta")
print(loo.to_string(index=False))
print(f"  Worst single-pair dependency: dropping {loo.iloc[0].dropped} changes Sharpe by {loo.iloc[0].delta}")
print(f"  Top-10 solo Sharpes range: {loo.pair_solo_sharpe.min():.2f} .. {loo.pair_solo_sharpe.max():.2f}; positive: {(loo.pair_solo_sharpe>0).sum()}/10")
print()

print("="*90)
print("2) PARAMETER ROBUSTNESS GRID (top-10 selectable OOS Sharpe, taker). Edge must persist across cells.")
print("="*90)
grid=[]
for zwin in [15,20,30]:
    for entry in [1.5,2.0,2.5]:
        for exit in [0.0,0.5,1.0]:
            tsx, pfx, _ = build_series(zwin,entry,exit)
            picks = tsx.sort_values(ascending=False).head(10).index.tolist()
            sh = perf(pfx[picks].mean(axis=1).dropna())["sharpe"]
            grid.append(dict(zwin=zwin,entry=entry,exit=exit,oos_sharpe=round(sh,2)))
g = pd.DataFrame(grid)
print(g.to_string(index=False))
print(f"  cells positive: {(g.oos_sharpe>0).sum()}/{len(g)}   median {g.oos_sharpe.median():.2f}   min {g.oos_sharpe.min():.2f}   max {g.oos_sharpe.max():.2f}")
print()

print("="*90)
print("3) COST STRESS (top-10 selectable OOS Sharpe at zwin20/entry2/exit0.5)")
print("="*90)
for fee,label in [(0.0002,"maker 0.02%/leg"),(0.0012,"taker 0.12%/leg"),(0.0020,"pessimistic 0.20%/leg")]:
    tsx, pfx, _ = build_series(fee=fee)
    picks = tsx.sort_values(ascending=False).head(10).index.tolist()
    pp = perf(pfx[picks].mean(axis=1).dropna())
    print(f"  {label:25s}-> OOS Sharpe {pp['sharpe']:+.2f}  total {pp['total']:+.3f}")
print()

print("="*90)
print("4) TRADE FREQUENCY / HOLDING (top-10, taker, OOS half)")
print("="*90)
for p in top10:
    A,B = p.split("/")
    sub = logp[[A,B]].dropna(); split=len(sub)//2
    beta = sig[(sig.A==A)&(sig.B==B)].beta.values[0]
    d,t = backtest_spread(sub[A].iloc[split:], sub[B].iloc[split:], beta)
    holds=[h for _,_,_,h in t]
    days=len(d)
    print(f"  {p:12s} trades={len(t):3d}  ~1 per {days/max(len(t),1):.0f}d  avg_hold={np.mean(holds):.0f}d  oos_total={d.sum():+.3f}")
