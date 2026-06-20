"""Anti-artifact statistics for the ST2.0 lab.

The lab's whole job is to avoid manufacturing false confidence, so these are the
load-bearing functions:

- benjamini_hochberg  — FDR control across a batch of candidate hypotheses.
- probabilistic_sharpe_ratio / expected_max_sharpe / deflated_sharpe_ratio —
  Bailey & Lopez de Prado: deflate an observed Sharpe by how many candidates were
  tried, so a "winner" must clear a bar that accounts for selection.
- bootstrap_diff_ci — CI for mean(a) - mean(b) using INDEPENDENT resampling.
  Resampling a and b independently each iteration and differencing the draw-order
  means is mandatory: sorting each bootstrapped mean-array first couples them
  comonotonically and shrinks the CI ~2.4x (a real bug that once flipped a null
  into false significance — see memory/feedback_bootstrap_diff_ci).

Pure standard library (statistics.NormalDist + seeded random) — deterministic, no
numpy dependency, safe to run in the daily lab job.
"""
import math
import random
from statistics import NormalDist

_N = NormalDist()
_EULER = 0.5772156649015329  # Euler-Mascheroni constant


def benjamini_hochberg(pvalues, alpha=0.05):
    """Return a boolean mask (in input order) of which p-values are rejected under
    Benjamini-Hochberg FDR control at level alpha. Step-up: once the largest rank
    k* with p(k) <= (k/m)*alpha is found, ALL k* smallest p-values are rejected."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])  # ascending by p
    k_star = 0
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= (rank / m) * alpha:
            k_star = rank
    mask = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= k_star:
            mask[idx] = True
    return mask


def probabilistic_sharpe_ratio(sharpe, n_obs, sr_benchmark=0.0, skew=0.0, kurt=3.0):
    """P(true Sharpe > sr_benchmark) given an observed `sharpe` over `n_obs` returns,
    adjusting for non-normality (skew, kurtosis). SR==benchmark → 0.5."""
    if n_obs < 2:
        return 0.5
    denom = math.sqrt(max(1e-12, 1.0 - skew * sharpe + (kurt - 1.0) / 4.0 * sharpe ** 2))
    z = (sharpe - sr_benchmark) * math.sqrt(n_obs - 1) / denom
    return _N.cdf(z)


def expected_max_sharpe(n_trials, var_trial_sharpes):
    """Expected maximum Sharpe across `n_trials` independent trials under the null
    (true edge = 0), given the variance of the trial Sharpes. This is the selection
    bar a candidate must beat. One trial → no selection → 0."""
    if n_trials <= 1 or var_trial_sharpes <= 0:
        return 0.0
    sigma = math.sqrt(var_trial_sharpes)
    term = ((1.0 - _EULER) * _N.inv_cdf(1.0 - 1.0 / n_trials)
            + _EULER * _N.inv_cdf(1.0 - 1.0 / (n_trials * math.e)))
    return sigma * term


def deflated_sharpe_ratio(sharpe, n_obs, n_trials, var_trial_sharpes,
                          skew=0.0, kurt=3.0):
    """Probabilistic Sharpe Ratio with the benchmark set to the expected maximum
    Sharpe under selection — i.e. PSR deflated for the number of trials tried.
    More trials → higher bar → lower confidence."""
    sr0 = expected_max_sharpe(n_trials, var_trial_sharpes)
    return probabilistic_sharpe_ratio(sharpe, n_obs, sr_benchmark=sr0,
                                      skew=skew, kurt=kurt)


def bootstrap_diff_ci(a, b, n_boot=2000, alpha=0.05, seed=0):
    """Percentile CI for mean(a) - mean(b). Each iteration resamples a and b
    INDEPENDENTLY (with replacement) and records the difference of the two means.
    Never sort the per-side bootstrap means before differencing — that comonotonic
    coupling makes the CI ~2.4x too narrow."""
    rnd = random.Random(seed)
    na, nb = len(a), len(b)
    diffs = []
    for _ in range(n_boot):
        sa = sum(a[rnd.randrange(na)] for _ in range(na)) / na
        sb = sum(b[rnd.randrange(nb)] for _ in range(nb)) / nb
        diffs.append(sa - sb)
    diffs.sort()
    lo_i = int((alpha / 2.0) * n_boot)
    hi_i = min(int((1.0 - alpha / 2.0) * n_boot), n_boot - 1)
    return (diffs[lo_i], diffs[hi_i])
