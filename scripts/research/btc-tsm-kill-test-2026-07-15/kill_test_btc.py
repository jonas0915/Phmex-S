#!/usr/bin/env python3
"""BTC-TSM (28,5) KILL TEST — 2026-07-15. READ-ONLY vs the live bot.

PURPOSE: adjudicate whether the BTC-TSM slot (unblocked at $250 balance) deserves
to be built, by replaying the EXACT deployed ETH-TSM-28 rule on BTC daily bars
using our own data and the EXACT 7/13 in-house methodology.

METHODOLOGY (reused verbatim, zero new variants):
  tsm_basket.py in this directory is a byte-identical copy (shasum
  d827ca61f8e5f18a37edb2c35c038ffabd9a21ed) of the 2026-07-13 basket walk-forward
  script (session da6fc410 scratchpad) that produced the memory-recorded numbers
  "12-coin post-2022 Sharpe 0.39, deflated-Sharpe prob 0.63, ETH-only 0.71".
  Rule: daily close, 28d trailing return >= 66.667 pctile of own EXPANDING PRIOR
  history (current excluded, min 90 obs) -> LONG; 5d min hold; exit on tercile
  exit after min-hold or -8% stop; long-only; taker 6 bps/side (12 bps RT — our
  real taker rate per r5_slow_horizon_research.md; ETH-TSM slot would pay less
  as maker, so taker here is conservative). Causal/expanding = walk-forward:
  no parameter is ever fit on future data.

DATA: scripts/research/htf-rigorous-2026-06-13/data/BTC_1d.csv (binanceus
  primary daily, 2021-01-01 .. 2026-06-13, 1990 bars) — the same cached file the
  7/13 study ran on. Secondary robustness: fresh ccxt Phemex BTC/USD daily
  (fetch_phemex_btc.py) to extend through 2026-07-15 and as far back as Phemex
  serves.

PRESPECIFIED KILL BAR (written BEFORE first run, per task order):
  BUILD only if ALL of:
    (1) post-2022 (>= 2022-01-01) walk-forward net Sharpe > 0;
    (2) deflated-Sharpe PASS: DSR prob > 0.95 using the SAME 36-config grid
        (L in {14,28,56} x H in {3,5,10} x rule in {tercile,sign} x dir in
        {long,ls}) as the 7/13 study, run BTC-only;
    (3) beats buy-and-hold BTC risk-adjusted post-2022: Sharpe(TSM) >
        Sharpe(B&H) AND the block-bootstrap diff-CI (resample arms
        INDEPENDENTLY, difference draw-order Sharpes, THEN sort diffs —
        feedback_bootstrap_diff_ci.md) has 2.5th pctile > 0... relaxed to:
        point estimate higher AND diff-CI not clearly negative (95% CI upper
        > 0) — but if CI straddles 0 the verdict is at best "unproven", which
        under kill-test logic = DO NOT BUILD.
  Anything short of (1)+(2)+(3) => DO NOT BUILD.

REPORTS: full-sample and post-2022-only: net expectancy/trade, annualized
  Sharpe (daily M2M, sqrt(365)), max DD, % time in position, n trades; per-year
  breakdown; ETH-only line reproduced as cross-check against the memory-recorded
  0.71; buy-and-hold comparison; DSR.
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from tsm_basket import (load, run, stats, sharpe, maxdd, boot_sharpe, dsr,
                        BASKET, ANN, DATA)

def seg(p, start, end=None):
    q = p[p.index >= start]
    return q[q.index < end] if end else q

def trade_stats(trades):
    if not trades:
        return dict(n=0, exp=float('nan'), wr=float('nan'), stops=0)
    rets = [t["ret"] - 2*6.0/1e4 for t in trades]  # net of 12bps RT
    return dict(n=len(trades),
                exp=float(np.mean(rets)),
                wr=float(np.mean([r > 0 for r in rets])),
                stops=sum(1 for t in trades if t["reason"] == "stop"),
                avg_days=float(np.mean([t["days"] for t in trades])))

def line(label, p, e=None):
    st = stats(p)
    if len(p) < 60:  # too short for block bootstrap (block=20)
        expo = float(e.reindex(p.index).mean()) if e is not None else float('nan')
        print(f"{label:32} n={st['n_days']:4} annRet={st['ann_ret']*100:7.1f}% "
              f"Sharpe={st['sharpe']:5.2f} (segment too short for boot CI) "
              f"maxDD={st['maxdd']*100:6.1f}% expo={expo*100:5.1f}%")
        return st
    ci = boot_sharpe(p.values)
    expo = float(e.reindex(p.index).mean()) if e is not None else float('nan')
    print(f"{label:32} n={st['n_days']:4} annRet={st['ann_ret']*100:7.1f}% "
          f"Sharpe={st['sharpe']:5.2f} boot95[{ci[0]:5.2f},{ci[2]:5.2f}] "
          f"maxDD={st['maxdd']*100:6.1f}% tot={st['total_ret']*100:7.1f}% "
          f"expo={expo*100:5.1f}%")
    return st

def bh_series(sym, data_dir=None):
    """Buy-and-hold daily close-to-close returns for sym."""
    if data_dir:
        import tsm_basket as tb
        old = tb.DATA; tb.DATA = data_dir
        df = load(sym); tb.DATA = old
    else:
        df = load(sym)
    c = df["close"].values
    r = np.zeros(len(c)); r[1:] = c[1:]/c[:-1] - 1.0
    return pd.Series(r, index=df["dt"])

def diff_ci_sharpe(a, b, block=20, iters=3000, seed=1):
    """Block-bootstrap Sharpe diff (a - b). Arms resampled INDEPENDENTLY,
    draw-order Sharpes differenced, THEN diffs sorted (never sort arms first).
    Per feedback_bootstrap_diff_ci.md."""
    rng_a = np.random.default_rng(seed)
    rng_b = np.random.default_rng(seed + 1000)
    a = np.asarray(a); b = np.asarray(b)
    def draws(x, rng):
        n = len(x); nb = int(np.ceil(n/block)); out = []
        for _ in range(iters):
            st = rng.integers(0, n-block+1, nb)
            samp = np.concatenate([x[s:s+block] for s in st])[:n]
            out.append(samp.mean()/samp.std()*np.sqrt(ANN) if samp.std() > 0 else 0.0)
        return np.array(out)
    diffs = draws(a, rng_a) - draws(b, rng_b)   # draw-order difference
    return np.percentile(diffs, [2.5, 50, 97.5])  # sort AFTER differencing

def full_report(tag, data_dir=None):
    if data_dir:
        import tsm_basket as tb
        tb.DATA = data_dir
    print("="*120)
    print(f"[{tag}] SECTION A — BTC standalone, tercile long-only L=28 H=5, taker 6bps/side")
    print("="*120)
    p, R, E, tr = run(["BTC"], 28, 5, 'tercile', 'long')
    e = E["BTC"]
    st_full = line("BTC full sample", p, e)
    st_p22  = line("BTC post-2022 (>=2022-01-01)", seg(p, '2022-01-01'), e)
    line("BTC post-2023 (>=2023-01-01)", seg(p, '2023-01-01'), e)
    for y in sorted(set(p.index.year)):
        line(f"  BTC {y} only", seg(p, f'{y}-01-01', f'{y+1}-01-01'), e)
    trades = tr["BTC"]
    ts_all = trade_stats(trades)
    # post-2022 trades can't be split from trade list directly (no ts recorded in
    # 7/13 trade dicts) — report full-sample trade stats + count entries by expo.
    print(f"BTC trades (full sample): n={ts_all['n']}  net exp/trade={ts_all['exp']*100:+.2f}%  "
          f"WR={ts_all['wr']*100:.0f}%  stops={ts_all['stops']}  avg hold={ts_all['avg_days']:.1f}d")
    print(f"  (at 0.001 BTC ~ $64 notional: net exp/trade ~ ${ts_all['exp']*64:+.2f})")

    print()
    print(f"[{tag}] SECTION B — buy-and-hold BTC comparison (same windows)")
    bh = bh_series("BTC")
    st_bh_full = line("B&H BTC full sample", bh)
    st_bh_p22  = line("B&H BTC post-2022", seg(bh, '2022-01-01'))
    d_full = diff_ci_sharpe(p.values, bh.reindex(p.index).fillna(0.0).values)
    a22 = seg(p, '2022-01-01'); b22 = seg(bh, '2022-01-01').reindex(a22.index).fillna(0.0)
    d_p22 = diff_ci_sharpe(a22.values, b22.values)
    print(f"Sharpe diff (TSM - B&H) full:     med={d_full[1]:+.2f}  95%CI[{d_full[0]:+.2f},{d_full[2]:+.2f}]")
    print(f"Sharpe diff (TSM - B&H) post-22:  med={d_p22[1]:+.2f}  95%CI[{d_p22[0]:+.2f},{d_p22[2]:+.2f}]")

    print()
    print(f"[{tag}] SECTION C — deflated Sharpe, SAME 36-config grid as 7/13 study, BTC-only, post-2022")
    all_sh = []
    for L in [14, 28, 56]:
        for H in [3, 5, 10]:
            for rule in ['tercile', 'sign']:
                for direction in ['long', 'ls']:
                    q, _, _, _ = run(["BTC"], L, H, rule, direction)
                    all_sh.append(stats(seg(q, '2022-01-01'))['sharpe'])
    n_trials = len(all_sh); sr_var = float(np.var(all_sh, ddof=1))
    d = dsr(seg(p, '2022-01-01').values, n_trials, sr_var)
    print(f"trials N={n_trials}  var(Sharpe)={sr_var:.3f}  grid post-22 Sharpe min={min(all_sh):.2f} "
          f"median={np.median(all_sh):.2f} max={max(all_sh):.2f}")
    print(f"primary Sharpe(ann)={d['sr_ann']:.3f}  Sharpe0(exp-max-null)={d['sr0_ann']:.3f}  "
          f"skew={d['skew']:.2f}  DEFLATED SHARPE prob = {d['dsr']:.3f}  "
          f"({'PASS' if d['dsr'] > 0.95 else 'FAIL'} at 0.95)")

    print()
    print(f"[{tag}] SECTION D — kill-bar adjudication")
    c1 = st_p22['sharpe'] > 0
    c2 = d['dsr'] > 0.95
    c3 = (st_p22['sharpe'] > st_bh_p22['sharpe']) and (d_p22[0] > 0)
    print(f"(1) post-2022 Sharpe > 0:            {st_p22['sharpe']:5.2f}  -> {'PASS' if c1 else 'FAIL'}")
    print(f"(2) deflated-Sharpe prob > 0.95:      {d['dsr']:5.3f}  -> {'PASS' if c2 else 'FAIL'}")
    print(f"(3) beats B&H risk-adj (diff-CI>0):   TSM {st_p22['sharpe']:.2f} vs B&H {st_bh_p22['sharpe']:.2f}, "
          f"diff CI lo {d_p22[0]:+.2f}  -> {'PASS' if c3 else 'FAIL'}")
    print(f"VERDICT [{tag}]: {'BUILD' if (c1 and c2 and c3) else 'DO NOT BUILD'}")
    return p

if __name__ == "__main__":
    print("#"*120)
    print("# CROSS-CHECK: reproduce the 7/13 recorded ETH-only post-2022 Sharpe (memory says 0.71)")
    print("#"*120)
    pe, _, Ee, _ = run(["ETH"], 28, 5, 'tercile', 'long')
    line("ETH post-2022 (cross-check)", seg(pe, '2022-01-01'), Ee["ETH"])
    print()
    full_report("PRIMARY cached-7/13-data")
    phemex_dir = os.path.join(HERE, "data_phemex")
    if os.path.exists(os.path.join(phemex_dir, "BTC_1d.csv")):
        print()
        full_report("SECONDARY phemex-extended", data_dir=phemex_dir)
