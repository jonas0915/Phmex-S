"""bootstrap_ci: correct independent-resample diff CI (feedback_bootstrap_diff_ci)."""
import numpy as np
import pytest

from research.swarm.lib import bootstrap_ci as bc


def test_mean_ci_contains_true_mean_and_is_ordered():
    rng = np.random.default_rng(1)
    x = rng.normal(5.0, 1.0, size=400)
    lo, hi = bc.mean_ci(x, n_boot=1000, seed=1)
    assert lo < 5.0 < hi and lo < hi


def test_mean_ci_empty_input_raises():
    with pytest.raises(ValueError):
        bc.mean_ci(np.array([]))


def test_diff_ci_contains_true_shift():
    rng = np.random.default_rng(2)
    a = rng.normal(0.0, 1.0, size=300)
    b = rng.normal(0.5, 1.0, size=300)
    lo, hi = bc.diff_ci(b, a, n_boot=1000, seed=2)
    assert lo < 0.5 < hi


def test_diff_ci_excludes_zero_for_clear_effect():
    rng = np.random.default_rng(3)
    a = rng.normal(0.0, 1.0, size=500)
    b = rng.normal(1.0, 1.0, size=500)
    lo, hi = bc.diff_ci(b, a, n_boot=1000, seed=3)
    assert lo > 0.0


def test_sort_first_bug_is_narrower_than_correct_ci():
    """Regression anchor: sorting each side before differencing shrinks the CI ~2x.
    The correct CI must be materially wider than the buggy one."""
    rng = np.random.default_rng(4)
    a = rng.normal(0.0, 1.0, size=200)
    b = rng.normal(0.0, 1.0, size=200)
    lo_ok, hi_ok = bc.diff_ci(a, b, n_boot=2000, seed=4)
    lo_bad, hi_bad = bc._buggy_diff_ci_sort_first(a, b, n_boot=2000, alpha=0.05, seed=4)
    assert (hi_ok - lo_ok) > 1.5 * (hi_bad - lo_bad)
