"""Shared rigorous-stats helpers for the microstructure/calendar edge search.

All returns are SIMPLE (close-to-close fractional). Fees handled by caller.
"""
import numpy as np


def block_bootstrap_ci(x, n_boot=5000, block=24, ci=0.95, seed=0):
    """Stationary-ish moving-block bootstrap CI for the MEAN of x.

    block default 24 (=~1 day of hourly obs) to respect autocorrelation.
    Returns (mean, lo, hi, p_two_sided_vs_zero).
    """
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < block * 3:
        m = float(np.mean(x)) if n else float("nan")
        return m, float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    means = np.empty(n_boot)
    max_start = n - block
    for b in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[b] = x[idx].mean()
    lo = np.percentile(means, (1 - ci) / 2 * 100)
    hi = np.percentile(means, (1 + ci) / 2 * 100)
    # two-sided bootstrap p: fraction of resampled means on the opposite side of 0
    m = float(np.mean(x))
    centered = means - m
    p = 2.0 * min((centered >= m).mean(), (centered <= m).mean())
    p = min(1.0, p)
    return m, float(lo), float(hi), float(p)


def benjamini_hochberg(pvals, alpha=0.05):
    """Return boolean array of which hypotheses survive BH-FDR at alpha,
    plus the BH critical threshold."""
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]
    crit = (np.arange(1, n + 1) / n) * alpha
    passed = ranked <= crit
    if not passed.any():
        thresh = 0.0
        survive = np.zeros(n, dtype=bool)
    else:
        kmax = np.max(np.where(passed)[0])
        thresh = ranked[kmax]
        survive = p <= thresh
    return survive, float(thresh)


def bonferroni(pvals, alpha=0.05):
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    return p <= (alpha / n), alpha / n


def walk_forward_sign(values_by_period, fold_indices):
    """Generic walk-forward consistency: given a list of per-period mean values
    (e.g. mean return for the chosen bucket within each fold), report how many
    folds keep the same sign as the full sample, and the per-fold means.
    """
    full = np.nanmean(values_by_period)
    sign = np.sign(full)
    folds = []
    for idx in fold_indices:
        vals = np.asarray(values_by_period)[idx]
        folds.append(float(np.nanmean(vals)))
    same = sum(1 for f in folds if np.sign(f) == sign and f == f)
    return full, folds, same


def make_time_folds(n, k=5):
    """Contiguous time folds (no shuffle) — preserves walk-forward semantics."""
    bounds = np.linspace(0, n, k + 1).astype(int)
    return [np.arange(bounds[i], bounds[i + 1]) for i in range(k)]


def fmt_pct(x, d=4):
    return "nan" if x != x else f"{x*100:.{d}f}"
