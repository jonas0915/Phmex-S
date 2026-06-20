"""TDD for scripts/st2_lab/stats.py — the anti-artifact statistics backbone.

These functions are the whole point of the honest lab: a wrong deflated-Sharpe or a
too-narrow bootstrap CI manufactures false confidence. So they are tested against
known values and core properties, not just smoke-run.
"""
import math
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import stats  # noqa: E402


# ── Benjamini–Hochberg FDR ────────────────────────────────────────────────
def test_bh_rejects_two_smallest():
    # m=5, alpha=0.05 → thresholds k/m*alpha = [.01,.02,.03,.04,.05]
    # sorted p = [.001,.01,.5,.7,.9]; largest k with p(k)<=thresh is k=2.
    mask = stats.benjamini_hochberg([0.001, 0.01, 0.5, 0.7, 0.9], alpha=0.05)
    assert mask == [True, True, False, False, False]


def test_bh_step_up_property():
    # p(2)=0.026 exceeds its own threshold 0.025, but p(3)=0.03 <= 0.0375,
    # so the step-up procedure must still reject the first THREE.
    mask = stats.benjamini_hochberg([0.005, 0.026, 0.03, 0.9], alpha=0.05)
    assert mask == [True, True, True, False]


def test_bh_preserves_input_order():
    # Same p-values, shuffled: mask must track original positions.
    mask = stats.benjamini_hochberg([0.9, 0.001, 0.7, 0.01, 0.5], alpha=0.05)
    assert mask == [False, True, False, True, False]


def test_bh_none_significant():
    assert stats.benjamini_hochberg([0.4, 0.6, 0.8], alpha=0.05) == [False, False, False]


# ── Probabilistic Sharpe Ratio ────────────────────────────────────────────
def test_psr_half_at_zero_sharpe():
    # SR == benchmark (0) → PSR = Phi(0) = 0.5 exactly.
    assert abs(stats.probabilistic_sharpe_ratio(0.0, n_obs=100) - 0.5) < 1e-9


def test_psr_increases_with_sharpe():
    lo = stats.probabilistic_sharpe_ratio(0.1, n_obs=100)
    hi = stats.probabilistic_sharpe_ratio(0.5, n_obs=100)
    assert 0.5 < lo < hi <= 1.0


def test_psr_increases_with_sample_size():
    short = stats.probabilistic_sharpe_ratio(0.2, n_obs=30)
    long = stats.probabilistic_sharpe_ratio(0.2, n_obs=500)
    assert short < long


# ── Expected max Sharpe under the null (selection bar) ─────────────────────
def test_expected_max_sharpe_zero_for_single_trial():
    # One trial = no selection, expected max is 0.
    assert stats.expected_max_sharpe(n_trials=1, var_trial_sharpes=0.5) == 0.0


def test_expected_max_sharpe_rises_with_trials():
    few = stats.expected_max_sharpe(n_trials=10, var_trial_sharpes=0.25)
    many = stats.expected_max_sharpe(n_trials=1000, var_trial_sharpes=0.25)
    assert 0 < few < many


# ── Deflated Sharpe Ratio ─────────────────────────────────────────────────
def test_dsr_below_psr_under_selection():
    # With many trials the selection bar > 0, so DSR < PSR for the same SR.
    psr = stats.probabilistic_sharpe_ratio(0.5, n_obs=200)
    dsr = stats.deflated_sharpe_ratio(0.5, n_obs=200, n_trials=500,
                                      var_trial_sharpes=0.25)
    assert 0.0 <= dsr <= 1.0
    assert dsr < psr


def test_dsr_decreases_with_more_trials():
    a = stats.deflated_sharpe_ratio(0.5, n_obs=200, n_trials=50, var_trial_sharpes=0.25)
    b = stats.deflated_sharpe_ratio(0.5, n_obs=200, n_trials=5000, var_trial_sharpes=0.25)
    assert b < a  # more things tried → higher bar → lower confidence


# ── Bootstrap difference-of-means CI (the documented correctness bug) ──────
def test_bootstrap_diff_ci_is_deterministic_with_seed():
    a = [1.0, 2.0, 3.0, 4.0, 5.0] * 20
    b = [0.5, 1.5, 2.5, 3.5, 4.5] * 20
    ci1 = stats.bootstrap_diff_ci(a, b, n_boot=1000, alpha=0.05, seed=7)
    ci2 = stats.bootstrap_diff_ci(a, b, n_boot=1000, alpha=0.05, seed=7)
    assert ci1 == ci2


def test_bootstrap_diff_ci_matches_analytic_width():
    # Two independent samples; correct independent-resample CI half-width should
    # approximate z * sqrt(varA/nA + varB/nB).
    import numpy as np
    rng = np.random.default_rng(123)
    a = (rng.normal(0.0, 1.0, 800)).tolist()
    b = (rng.normal(0.5, 1.0, 800)).tolist()
    lo, hi = stats.bootstrap_diff_ci(a, b, n_boot=3000, alpha=0.05, seed=1)
    half = (hi - lo) / 2
    va, vb = (sum((x - sum(a) / len(a)) ** 2 for x in a) / (len(a) - 1),
              sum((x - sum(b) / len(b)) ** 2 for x in b) / (len(b) - 1))
    analytic = 1.959963985 * math.sqrt(va / len(a) + vb / len(b))
    assert 0.80 * analytic < half < 1.20 * analytic


def test_bootstrap_independent_resample_wider_than_comonotonic_bug():
    # The documented bug: sorting each bootstrapped mean-array before differencing
    # couples A and B comonotonically and shrinks the diff variance (~2.4x too
    # narrow). The correct independent-resample CI must be materially WIDER.
    import numpy as np
    rng = np.random.default_rng(99)
    a = (rng.normal(0.0, 1.0, 500)).tolist()
    b = (rng.normal(0.0, 1.0, 500)).tolist()
    lo, hi = stats.bootstrap_diff_ci(a, b, n_boot=2000, alpha=0.05, seed=2)
    correct_w = hi - lo

    # Reproduce the buggy comonotonic computation locally.
    import random as _r
    rnd = _r.Random(2)
    means_a, means_b = [], []
    for _ in range(2000):
        means_a.append(sum(a[rnd.randrange(len(a))] for _ in a) / len(a))
        means_b.append(sum(b[rnd.randrange(len(b))] for _ in b) / len(b))
    means_a.sort()
    means_b.sort()
    diffs = sorted(ma - mb for ma, mb in zip(means_a, means_b))
    lo_i = int(0.025 * len(diffs))
    hi_i = int(0.975 * len(diffs))
    buggy_w = diffs[hi_i] - diffs[lo_i]

    assert correct_w > 1.5 * buggy_w
