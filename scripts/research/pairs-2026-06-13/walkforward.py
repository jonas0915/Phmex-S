#!/usr/bin/env python3
"""
The decisive tests:
 A) TRAIN->TEST predictability: does in-sample cointegration p-value OR train Sharpe
    predict OOS Sharpe? (correlation). If not, selection is impossible.
 B) Selectable portfolio: pick top-N pairs by TRAIN Sharpe (a tradable rule), trade them OOS.
    This is the honest "could you have done it" test.
 C) Walk-forward: 6 expanding folds. At each fold, re-estimate beta/coint on data-so-far,
    select pairs by recent train Sharpe, trade next block OOS. Chain all OOS blocks.
 D) Regime breakdown: split full OOS into bull/bear/chop by BTC trend, report Sharpe per regime.
"""
import os, itertools
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller
from pairs_scan import load_daily, ols_beta, eg_pvalue, backtest_spread, perf

np.random.seed(7)
HERE = os.path.dirname(__file__)

def main():
    panel = load_daily()
    logp = np.log(panel)
    syms = list(panel.columns)
    pairs = list(itertools.combinations(syms, 2))

    # ---------- A) predictability of OOS from in-sample ----------
    oos = pd.read_csv(os.path.join(HERE, "oos_backtest.csv"))
    c_p = np.corrcoef(oos.train_adf_p, oos.te_sharpe)[0,1]
    c_s = np.corrcoef(oos.tr_sharpe, oos.te_sharpe)[0,1]
    print("="*90)
    print("A) CAN WE SELECT WINNERS EX-ANTE? (correlation of in-sample signal vs OOS Sharpe)")
    print("="*90)
    print(f"  corr( TRAIN ADF p-value , TEST Sharpe ) = {c_p:+.3f}  (want strongly negative: lower p -> better OOS)")
    print(f"  corr( TRAIN Sharpe      , TEST Sharpe ) = {c_s:+.3f}  (want strongly positive: good train -> good OOS)")
    # bucket: top-quartile train sharpe vs their oos
    q = oos.tr_sharpe.quantile(0.75)
    top = oos[oos.tr_sharpe >= q]
    bot = oos[oos.tr_sharpe < oos.tr_sharpe.quantile(0.25)]
    print(f"  Top-quartile TRAIN-Sharpe pairs -> mean TEST Sharpe = {top.te_sharpe.mean():+.2f} (n={len(top)})")
    print(f"  Bot-quartile TRAIN-Sharpe pairs -> mean TEST Sharpe = {bot.te_sharpe.mean():+.2f} (n={len(bot)})")
    print()

    # ---------- B) selectable portfolio: top-N by TRAIN sharpe, traded OOS ----------
    print("="*90)
    print("B) SELECTABLE PORTFOLIO: pick top-N pairs by TRAIN Sharpe (tradable), equal-weight OOS")
    print("="*90)
    # rebuild daily OOS series per pair (need both coint & cost)
    # restrict to pairs that cointegrate in train AND have positive train sharpe
    sig = pd.read_csv(os.path.join(HERE, "coint_train.csv"))
    sig = sig[sig.train_adf_p < 0.05]
    series = {}
    train_sharpe = {}
    for _, r in sig.iterrows():
        A, B = r.A, r.B
        sub = logp[[A, B]].dropna()
        split = len(sub)//2
        d_tr,_ = backtest_spread(sub[A].iloc[:split], sub[B].iloc[:split], r.beta)
        d_te,_ = backtest_spread(sub[A].iloc[split:], sub[B].iloc[split:], r.beta)
        train_sharpe[f"{A}/{B}"] = perf(d_tr)["sharpe"]
        series[f"{A}/{B}"] = d_te
    ts = pd.Series(train_sharpe).sort_values(ascending=False)
    pf = pd.DataFrame(series)
    for N in [5, 10, 20]:
        picks = ts.head(N).index.tolist()
        port = pf[picks].mean(axis=1).dropna()
        pp = perf(port)
        # bootstrap
        arr = port.values
        bs = [ (lambda s: s.mean()/(s.std()+1e-12)*np.sqrt(365))(np.random.choice(arr,len(arr),replace=True)) for _ in range(3000)]
        lo,hi = np.percentile(bs,[2.5,97.5])
        print(f"  Top-{N} by TRAIN Sharpe -> OOS Sharpe {pp['sharpe']:+.2f}  total {pp['total']:+.3f}  CI[{lo:+.2f},{hi:+.2f}]  picks={picks[:5]}{'...' if N>5 else ''}")
    print()

    # ---------- C) walk-forward expanding folds ----------
    print("="*90)
    print("C) WALK-FORWARD: 6 folds. Re-fit coint+beta on past, select top-10 by trailing train Sharpe,")
    print("   trade next block OOS, chain. TAKER costs.")
    print("="*90)
    # use a common dense date range where most majors exist (drop sparse late-listers handled by dropna per pair)
    full_idx = logp.index
    n = len(full_idx)
    n_folds = 6
    # expanding: train on [0, t), test on [t, t+block)
    block = n // (n_folds + 1)
    all_oos = []
    fold_rows = []
    for k in range(1, n_folds+1):
        tr_end = block * k
        te_end = min(block * (k+1), n)
        tr_idx = full_idx[:tr_end]
        te_idx = full_idx[tr_end:te_end]
        if len(te_idx) < 30: continue
        # screen pairs on train slice
        cand = []
        for A,B in pairs:
            sub = logp[[A,B]].reindex(tr_idx).dropna()
            if len(sub) < 250: continue
            a,beta,pv = eg_pvalue(sub[A].values, sub[B].values)
            if pv >= 0.05: continue
            d_tr,_ = backtest_spread(sub[A], sub[B], beta)
            sh = perf(d_tr)["sharpe"]
            cand.append((f"{A}/{B}", A, B, beta, sh))
        cand.sort(key=lambda x: -x[4])
        picks = cand[:10]
        # trade picks OOS on test block (beta fixed from train)
        block_series = {}
        for name,A,B,beta,sh in picks:
            sub = logp[[A,B]].reindex(full_idx)  # full so rolling window has warmup from before te
            # backtest only over warmup+test, then slice test
            warm = 30
            seg_idx = full_idx[max(0,tr_end-warm):te_end]
            seg = sub.reindex(seg_idx).dropna()
            if len(seg) < warm+10: continue
            d,_ = backtest_spread(seg[A], seg[B], beta)
            d = d.reindex(te_idx).dropna()
            block_series[name] = d
        if not block_series: continue
        bdf = pd.DataFrame(block_series)
        bport = bdf.mean(axis=1).dropna()
        bp = perf(bport)
        all_oos.append(bport)
        fold_rows.append(dict(fold=k, train_end=str(tr_idx[-1].date()),
                              test=f"{te_idx[0].date()}->{te_idx[-1].date()}",
                              n_picks=len(block_series), oos_sharpe=round(bp['sharpe'],2),
                              oos_total=round(bp['total'],3), days=bp['n']))
    fdf = pd.DataFrame(fold_rows)
    print(fdf.to_string(index=False))
    chained = pd.concat(all_oos).sort_index()
    cp = perf(chained)
    arr = chained.values
    bs = [ (lambda s: s.mean()/(s.std()+1e-12)*np.sqrt(365))(np.random.choice(arr,len(arr),replace=True)) for _ in range(5000)]
    lo,hi = np.percentile(bs,[2.5,97.5])
    print(f"\n  CHAINED walk-forward OOS Sharpe: {cp['sharpe']:+.2f}  total {cp['total']:+.3f}  days {cp['n']}")
    print(f"  Bootstrap 95% CI: [{lo:+.2f}, {hi:+.2f}]")
    print(f"  Folds positive: {(fdf.oos_sharpe>0).sum()}/{len(fdf)}")
    print()

    # ---------- D) regime breakdown of chained OOS ----------
    print("="*90)
    print("D) REGIME BREAKDOWN of chained walk-forward OOS (by BTC 50d trend)")
    print("="*90)
    btc = np.log(panel["BTC"]).reindex(chained.index)
    sma = btc.rolling(50).mean()
    regime = pd.Series(np.where(btc > sma, "bull", "bear"), index=chained.index)
    for reg in ["bull","bear"]:
        seg = chained[regime==reg]
        p = perf(seg)
        print(f"  {reg}: Sharpe {p['sharpe']:+.2f}  total {p['total']:+.3f}  days {p['n']}")

if __name__ == "__main__":
    main()
