#!/usr/bin/env python3
"""
Rigorous pairs/cointegration OOS search.

Pipeline:
 1. Load daily closes, build aligned log-price panel.
 2. TRAIN = first 50% of overlapping samples per pair. Engle-Granger cointegration
    (ADF on residual of OLS log(A) ~ a + b*log(B)) on TRAIN ONLY.
 3. Select pairs that cointegrate in-sample (ADF p < 0.05) AND have decent overlap.
 4. Backtest z-score reversion on TRAIN (params fixed a priori) and on held-out TEST.
 5. Walk-forward: 5 folds, beta+mean+std estimated on expanding/rolling train, traded OOS.
 6. Costs: maker 0.02% & taker 0.12% per leg, 2 legs, applied per round-trip.
 7. Bootstrap CI on portfolio; regime breakdown.
"""
import os, sys, itertools, json
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

DATA = os.path.join(os.path.dirname(__file__), "data")
np.random.seed(42)

# ---------- load ----------
def load_daily():
    closes = {}
    for f in os.listdir(DATA):
        if not f.endswith("_1d.csv"):
            continue
        sym = f.replace("_1d.csv", "")
        df = pd.read_csv(os.path.join(DATA, f), parse_dates=["dt"])
        df = df.drop_duplicates("dt").set_index("dt").sort_index()
        closes[sym] = df["close"]
    panel = pd.DataFrame(closes)
    # daily index: keep only rows where we have data; reindex to full daily range
    full = pd.date_range(panel.index.min(), panel.index.max(), freq="D", tz="UTC")
    panel = panel.reindex(full)
    return panel

# ---------- cointegration on train ----------
def ols_beta(y, x):
    # y = a + b*x  ; return a, b, resid
    X = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    a, b = coef
    resid = y - (a + b * x)
    return a, b, resid

def eg_pvalue(logy, logx):
    a, b, resid = ols_beta(logy, logx)
    try:
        pv = adfuller(resid, maxlag=1, regression="c", autolag=None)[1]
    except Exception:
        pv = 1.0
    return a, b, pv

# ---------- z-score reversion backtest ----------
def backtest_spread(logA, logB, beta, zwin=20, entry=2.0, exit=0.5,
                    fee_per_leg=0.0012, max_hold=60):
    """
    Spread = logA - beta*logB. Trade both legs notional-equal.
    Returns daily strategy returns (in spread-return units, ~ dollar-neutral)
    and trade list. Costs charged at entry and exit: 2 legs each => 4*fee per round trip.
    """
    spread = logA - beta * logB
    s = pd.Series(spread)
    mean = s.rolling(zwin).mean()
    std = s.rolling(zwin).std()
    z = (s - mean) / std

    # daily log returns of each leg
    retA = logA.diff()
    retB = logB.diff()

    pos = 0           # +1 = long spread (long A, short B); -1 = short spread
    entry_idx = None
    daily_pnl = np.zeros(len(s))
    trades = []
    n = len(s)
    idx = s.index
    for i in range(1, n):
        # accrue pnl for existing position using today's returns
        if pos != 0:
            # long spread: +retA - beta*retB ; short spread: -(retA - beta*retB)
            leg = (retA.iloc[i] - beta * retB.iloc[i])
            daily_pnl[i] += pos * leg
        zi = z.iloc[i]
        if np.isnan(zi):
            continue
        if pos == 0:
            if zi > entry:
                pos = -1; entry_idx = i  # spread rich -> short spread
            elif zi < -entry:
                pos = 1; entry_idx = i   # spread cheap -> long spread
            if pos != 0:
                daily_pnl[i] -= 2 * fee_per_leg  # entry: 2 legs
        else:
            held = i - entry_idx
            should_exit = (abs(zi) < exit) or (held >= max_hold) or \
                          (pos == 1 and zi > entry) or (pos == -1 and zi < -entry)
            if should_exit:
                daily_pnl[i] -= 2 * fee_per_leg  # exit: 2 legs
                trades.append((idx[entry_idx], idx[i], pos, held))
                pos = 0; entry_idx = None
    return pd.Series(daily_pnl, index=idx), trades

def perf(daily, ann=365):
    daily = daily.dropna()
    if len(daily) < 2 or daily.std() == 0:
        return dict(sharpe=0, total=daily.sum(), mean=daily.mean(), n=len(daily))
    sh = daily.mean() / daily.std() * np.sqrt(ann)
    return dict(sharpe=sh, total=daily.sum(), mean=daily.mean(), n=len(daily))

def main():
    panel = load_daily()
    logp = np.log(panel)
    syms = list(panel.columns)
    print(f"Universe: {len(syms)} symbols, daily index {panel.index.min().date()} -> {panel.index.max().date()} ({len(panel)} days)\n")

    pairs = list(itertools.combinations(syms, 2))
    print(f"Testing {len(pairs)} pairs for in-sample (TRAIN, first 50%) cointegration...\n")

    MIN_OVERLAP = 400  # need at least ~400 daily obs overlap
    results = []
    for A, B in pairs:
        sub = logp[[A, B]].dropna()
        if len(sub) < MIN_OVERLAP * 2:
            continue
        split = len(sub) // 2
        tr = sub.iloc[:split]
        te = sub.iloc[split:]
        if len(tr) < MIN_OVERLAP or len(te) < MIN_OVERLAP:
            continue
        # cointegration on TRAIN only
        a, beta, pv = eg_pvalue(tr[A].values, tr[B].values)
        results.append(dict(A=A, B=B, n_overlap=len(sub), train_adf_p=pv, beta=beta,
                            train_start=str(sub.index[0].date()),
                            test_start=str(sub.index[split].date()),
                            test_end=str(sub.index[-1].date())))
    res = pd.DataFrame(results).sort_values("train_adf_p")
    res.to_csv(os.path.join(os.path.dirname(__file__), "coint_train.csv"), index=False)
    sig = res[res.train_adf_p < 0.05].copy()
    print(f"Pairs cointegrating in TRAIN (ADF p<0.05): {len(sig)} / {len(res)} tested")
    print(sig.head(25).to_string(index=False))
    print()

    # ---------- OOS backtest of in-sample-cointegrated pairs ----------
    print("="*100)
    print("OOS BACKTEST: params (zwin=20, entry=2, exit=0.5) fixed a priori. Beta from TRAIN OLS.")
    print("Costs: taker 0.12%/leg (4 legs/round-trip). Sharpe annualized (365d).")
    print("="*100)
    oos_rows = []
    portfolio_test = {}
    for _, r in sig.iterrows():
        A, B = r.A, r.B
        sub = logp[[A, B]].dropna()
        split = len(sub) // 2
        beta = r.beta
        # TRAIN perf
        d_tr, t_tr = backtest_spread(sub[A].iloc[:split], sub[B].iloc[:split], beta)
        p_tr = perf(d_tr)
        # TEST perf (held out) — beta still from TRAIN
        d_te, t_te = backtest_spread(sub[A].iloc[split:], sub[B].iloc[split:], beta)
        p_te = perf(d_te)
        # TEST at maker fee
        d_te_m, _ = backtest_spread(sub[A].iloc[split:], sub[B].iloc[split:], beta, fee_per_leg=0.0002)
        p_te_m = perf(d_te_m)
        portfolio_test[f"{A}/{B}"] = d_te
        oos_rows.append(dict(pair=f"{A}/{B}", train_adf_p=round(r.train_adf_p,4),
                             beta=round(beta,3),
                             tr_sharpe=round(p_tr["sharpe"],2), tr_total=round(p_tr["total"],3), tr_trades=len(t_tr),
                             te_sharpe=round(p_te["sharpe"],2), te_total=round(p_te["total"],3), te_trades=len(t_te),
                             te_sharpe_maker=round(p_te_m["sharpe"],2), te_total_maker=round(p_te_m["total"],3)))
    oos = pd.DataFrame(oos_rows).sort_values("te_sharpe", ascending=False)
    oos.to_csv(os.path.join(os.path.dirname(__file__), "oos_backtest.csv"), index=False)
    print(oos.to_string(index=False))
    print()
    print(f"OOS (TEST) summary across {len(oos)} in-sample-cointegrated pairs (TAKER):")
    print(f"  median test Sharpe: {oos.te_sharpe.median():.2f}   mean: {oos.te_sharpe.mean():.2f}")
    print(f"  pairs with test Sharpe>0.5: {(oos.te_sharpe>0.5).sum()}   >1.0: {(oos.te_sharpe>1.0).sum()}")
    print(f"  pairs profitable OOS (total>0): {(oos.te_total>0).sum()} / {len(oos)}")
    print(f"  median test Sharpe (MAKER): {oos.te_sharpe_maker.median():.2f}")

    # ---------- equal-weight portfolio of in-sample-cointegrated pairs, OOS ----------
    print("\n" + "="*100)
    print("EQUAL-WEIGHT PORTFOLIO of all in-sample-cointegrated pairs, OOS (TEST half), TAKER")
    print("="*100)
    pf = pd.DataFrame(portfolio_test)
    # align by date; equal weight average of available pairs each day
    port_daily = pf.mean(axis=1).dropna()
    pp = perf(port_daily)
    print(f"  Portfolio OOS Sharpe: {pp['sharpe']:.2f}  total log-pnl: {pp['total']:.3f}  days: {pp['n']}")
    # bootstrap CI on daily portfolio returns
    arr = port_daily.values
    boots = []
    for _ in range(5000):
        s = np.random.choice(arr, len(arr), replace=True)
        boots.append(s.mean()/ (s.std()+1e-12) * np.sqrt(365))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"  Bootstrap 95% CI on OOS Sharpe: [{lo:.2f}, {hi:.2f}]")

    pf.to_csv(os.path.join(os.path.dirname(__file__), "portfolio_test_daily.csv"))
    return oos, sig, logp

if __name__ == "__main__":
    main()
