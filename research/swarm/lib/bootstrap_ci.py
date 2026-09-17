"""Percentile bootstrap CIs. diff_ci resamples A and B INDEPENDENTLY, differences the
draw-order means, and sorts only the diffs — the record's documented bug is sorting
each side first (2.4x too-narrow CI). Keep _buggy_* only as a regression oracle."""
from __future__ import annotations

import numpy as np


def _as_array(x) -> np.ndarray:
    arr = np.asarray(x, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError("empty sample")
    return arr


def mean_ci(x, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    arr = _as_array(x)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(n_boot, arr.size))
    means = arr[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def diff_ci(a, b, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """CI for mean(a) - mean(b)."""
    a_arr, b_arr = _as_array(a), _as_array(b)
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, a_arr.size, size=(n_boot, a_arr.size))
    ib = rng.integers(0, b_arr.size, size=(n_boot, b_arr.size))
    diffs = a_arr[ia].mean(axis=1) - b_arr[ib].mean(axis=1)   # draw-order pairing
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])   # sort ONLY the diffs
    return float(lo), float(hi)


def _buggy_diff_ci_sort_first(a, b, n_boot: int, alpha: float, seed: int) -> tuple[float, float]:
    """DO NOT USE. The historical bug: sort each side's bootstrap means, then difference."""
    a_arr, b_arr = _as_array(a), _as_array(b)
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, a_arr.size, size=(n_boot, a_arr.size))
    ib = rng.integers(0, b_arr.size, size=(n_boot, b_arr.size))
    diffs = np.sort(a_arr[ia].mean(axis=1)) - np.sort(b_arr[ib].mean(axis=1))
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)
