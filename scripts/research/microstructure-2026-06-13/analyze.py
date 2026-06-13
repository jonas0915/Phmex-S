"""Rigorous microstructure / calendar edge search.

Tests:
  1. Funding-settlement microstructure (pre/post 8h funding stamp drift, by funding sign)
  2. Time-of-day seasonality (24 UTC hours, multiple-testing corrected)
  3. Day-of-week (7 days, multiple-testing corrected)
  4. CME weekend-gap fill (BTC)

Every effect: full-sample block-bootstrap CI, walk-forward 5 folds, multi-regime
(per calendar year), net of fees where a trade is implied.
Fees: TAKER 0.066%/side round-trip 0.132% ; MAKER ~0.012%/side. We report gross
and net-of-taker and net-of-maker for short-hold trade-like effects.
"""
import json, os, sys
import numpy as np
import pandas as pd
from stats_lib import (block_bootstrap_ci, benjamini_hochberg, bonferroni,
                       make_time_folds, fmt_pct)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

FEE_TAKER_RT = 0.00132   # 0.066% * 2
FEE_MAKER_RT = 0.00024   # 0.012% * 2  (Phemex maker ~0.01-0.012%)

np.set_printoptions(suppress=True)


def load_ohlcv():
    d = json.load(open(os.path.join(DATA, "ohlcv1h_binanceus.json")))
    out = {}
    for sym, rows in d.items():
        df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
        df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.sort_values("ts").reset_index(drop=True)
        # mark gaps: ret valid only if previous bar is exactly 1h before
        df["dt_prev"] = df["dt"].shift(1)
        df["gap"] = (df["dt"] - df["dt_prev"]).dt.total_seconds() / 3600.0
        df["ret"] = df["c"].pct_change()
        df.loc[df["gap"] != 1.0, "ret"] = np.nan  # drop returns spanning gaps
        df["hour"] = df["dt"].dt.hour
        df["dow"] = df["dt"].dt.dayofweek  # Mon=0
        df["year"] = df["dt"].dt.year
        out[sym] = df
    return out


def section(t):
    print("\n" + "=" * 86)
    print(t)
    print("=" * 86)


# ---------------------------------------------------------------------------
# TEST 2 — TIME OF DAY (per UTC hour mean 1h return)
# ---------------------------------------------------------------------------
def test_time_of_day(data):
    section("TEST 2 — TIME-OF-DAY SEASONALITY (mean 1h return by UTC hour)")
    print("Pooled across symbols (equal-weight). 24 hypotheses -> BH-FDR + Bonferroni.")
    print("Hour h return = close[h] / close[h-1] - 1, i.e. the bar STAMPED at hour h.\n")

    # pool all symbols' hourly returns
    frames = []
    for sym, df in data.items():
        sub = df.dropna(subset=["ret"])[["hour", "ret", "year", "ts"]].copy()
        sub["sym"] = sym
        frames.append(sub)
    allr = pd.concat(frames, ignore_index=True).sort_values("ts").reset_index(drop=True)

    rows = []
    pvals = []
    for h in range(24):
        x = allr.loc[allr["hour"] == h, "ret"].values
        m, lo, hi, p = block_bootstrap_ci(x, n_boot=4000, block=24, seed=h)
        rows.append((h, len(x), m, lo, hi, p))
        pvals.append(p)
    pvals = np.array(pvals)
    bh_pass, bh_t = benjamini_hochberg(pvals, 0.05)
    bf_pass, bf_t = bonferroni(pvals, 0.05)

    print(f"{'hr':>3} {'n':>7} {'meanRet%':>9} {'ci_lo%':>8} {'ci_hi%':>8} {'p':>7} {'BH':>3} {'Bonf':>4}")
    for i, (h, n, m, lo, hi, p) in enumerate(rows):
        print(f"{h:3d} {n:7d} {fmt_pct(m):>9} {fmt_pct(lo):>8} {fmt_pct(hi):>8} "
              f"{p:7.4f} {'Y' if bh_pass[i] else '.':>3} {'Y' if bf_pass[i] else '.':>4}")
    print(f"\nBH-FDR threshold p<= {bh_t:.5f} ; Bonferroni threshold p<= {bf_t:.5f}")
    surv = [rows[i][0] for i in range(24) if bh_pass[i]]
    print(f"Hours surviving BH-FDR: {surv if surv else 'NONE'}")

    # walk-forward on the single best (largest |mean|) hour
    best = max(range(24), key=lambda i: abs(rows[i][2]))
    bh = rows[best][0]
    print(f"\nWalk-forward on most-extreme hour = {bh:02d}:00 UTC (full mean {fmt_pct(rows[best][2])}%):")
    sub = allr[allr["hour"] == bh].reset_index(drop=True)
    folds = make_time_folds(len(sub), 5)
    full_sign = np.sign(rows[best][2])
    fold_means = [sub["ret"].values[idx].mean() for idx in folds]
    same = sum(1 for f in fold_means if np.sign(f) == full_sign)
    print("  fold means%:", [round(f*100, 4) for f in fold_means])
    print(f"  folds matching full-sample sign: {same}/5")

    # per-year regime for that hour
    print(f"\nPer-year mean% for hour {bh:02d}:00:")
    yr = sub.groupby("year")["ret"].agg(["mean", "count"])
    for y, r in yr.iterrows():
        print(f"  {y}: {r['mean']*100:8.4f}%  (n={int(r['count'])})")
    return surv


# ---------------------------------------------------------------------------
# TEST 3 — DAY OF WEEK (mean DAILY return by weekday)
# ---------------------------------------------------------------------------
def test_day_of_week(data):
    section("TEST 3 — DAY-OF-WEEK (mean daily return by UTC weekday)")
    print("Daily return = close(00:00 next) / close(00:00) - 1, labeled by the day it covers.")
    print("7 hypotheses -> BH-FDR + Bonferroni. Confirm/kill prior 'Thursday weakness'.\n")

    frames = []
    for sym, df in data.items():
        d = df.set_index("dt")["c"].resample("1D").last().to_frame("c")
        d["ret"] = d["c"].pct_change()
        d["dow"] = d.index.dayofweek
        d["year"] = d.index.year
        d = d.dropna(subset=["ret"])
        d["sym"] = sym
        frames.append(d.reset_index())
    allr = pd.concat(frames, ignore_index=True).sort_values("dt").reset_index(drop=True)

    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rows, pvals = [], []
    for dow in range(7):
        x = allr.loc[allr["dow"] == dow, "ret"].values
        m, lo, hi, p = block_bootstrap_ci(x, n_boot=4000, block=7, seed=100 + dow)
        rows.append((dow, len(x), m, lo, hi, p))
        pvals.append(p)
    pvals = np.array(pvals)
    bh_pass, bh_t = benjamini_hochberg(pvals, 0.05)
    bf_pass, bf_t = bonferroni(pvals, 0.05)

    print(f"{'day':>4} {'n':>6} {'meanRet%':>9} {'ci_lo%':>8} {'ci_hi%':>8} {'p':>7} {'BH':>3} {'Bonf':>4}")
    for i, (dow, n, m, lo, hi, p) in enumerate(rows):
        print(f"{names[dow]:>4} {n:6d} {fmt_pct(m):>9} {fmt_pct(lo):>8} {fmt_pct(hi):>8} "
              f"{p:7.4f} {'Y' if bh_pass[i] else '.':>3} {'Y' if bf_pass[i] else '.':>4}")
    print(f"\nBH-FDR threshold p<= {bh_t:.5f} ; Bonferroni p<= {bf_t:.5f}")
    surv = [names[rows[i][0]] for i in range(7) if bh_pass[i]]
    print(f"Days surviving BH-FDR: {surv if surv else 'NONE'}")

    # walk-forward + per-year on Thursday specifically (prior claim) and on best
    for label, dow in [("Thu (prior-claim)", 3),
                       ("most-extreme", max(range(7), key=lambda i: abs(rows[i][2])))]:
        sub = allr[allr["dow"] == dow].reset_index(drop=True)
        full = rows[dow][2]
        folds = make_time_folds(len(sub), 5)
        fm = [sub["ret"].values[idx].mean() for idx in folds]
        same = sum(1 for f in fm if np.sign(f) == np.sign(full))
        print(f"\nWalk-forward {label} = {names[dow]} (full {fmt_pct(full)}%): "
              f"fold means% {[round(f*100,4) for f in fm]} | sign-match {same}/5")
        yr = sub.groupby("year")["ret"].mean()
        print("  per-year%:", {int(y): round(v*100, 4) for y, v in yr.items()})
    return surv


if __name__ == "__main__":
    data = load_ohlcv()
    print(f"Loaded {len(data)} symbols.")
    for s, df in data.items():
        vr = df['ret'].notna().sum()
        print(f"  {s:10s} bars={len(df):6d} valid_ret={vr:6d} "
              f"{df['dt'].min().date()} .. {df['dt'].max().date()}")
    test_time_of_day(data)
    test_day_of_week(data)
