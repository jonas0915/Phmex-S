"""TDD for scripts/st2_lab/walkforward.py — purged/embargoed expanding windows.

Replaces the single 70/30 chronological split (which let the vol-fade artifact pass
on one lucky window). Correctness here = no test row leaks into any train set, and
the label horizon is purged at every train/test boundary.
"""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import walkforward as wf  # noqa: E402


def _series(symbol="X", start=0, stop=1000, step=10):
    return {symbol: [{"ts": t, "price": 100.0 + t} for t in range(start, stop, step)]}


def _all_ts(by_symbol):
    return [r["ts"] for recs in by_symbol.values() for r in recs]


def test_produces_n_windows():
    splits = wf.walk_forward_splits(_series(), n_windows=4, embargo_secs=0)
    assert len(splits) == 4


def test_no_test_row_leaks_into_train():
    for s in wf.walk_forward_splits(_series(), n_windows=5, embargo_secs=0):
        train_ts = _all_ts(s["train"])
        test_ts = _all_ts(s["test"])
        if train_ts and test_ts:
            assert max(train_ts) < min(test_ts)  # strict time separation


def test_test_window_bounds_respected():
    for s in wf.walk_forward_splits(_series(), n_windows=4, embargo_secs=0):
        for ts in _all_ts(s["test"]):
            assert s["test_start"] <= ts < s["test_end"]


def test_embargo_purges_boundary_rows():
    embargo = 100
    for s in wf.walk_forward_splits(_series(), n_windows=4, embargo_secs=embargo):
        train_ts = _all_ts(s["train"])
        if train_ts:
            # No train row within `embargo` seconds before the test window starts.
            assert max(train_ts) < s["test_start"] - embargo + 1e-9
            assert min(_all_ts(s["test"])) >= s["test_start"]


def test_train_set_expands_across_windows():
    splits = wf.walk_forward_splits(_series(), n_windows=5, embargo_secs=0)
    sizes = [len(_all_ts(s["train"])) for s in splits]
    assert sizes == sorted(sizes)          # non-decreasing
    assert sizes[-1] > sizes[0]            # genuinely expanding


def test_test_blocks_tile_contiguously():
    splits = wf.walk_forward_splits(_series(), n_windows=4, embargo_secs=0)
    for earlier, later in zip(splits, splits[1:]):
        assert earlier["test_end"] == later["test_start"]  # contiguous, no overlap


def test_multi_symbol_uses_global_time_boundaries():
    by = {"A": [{"ts": t, "price": t} for t in range(0, 1000, 10)],
          "B": [{"ts": t, "price": t} for t in range(5, 1000, 10)]}
    splits = wf.walk_forward_splits(by, n_windows=4, embargo_secs=0)
    for s in splits:
        # both symbols' test rows obey the same global window bounds
        for ts in _all_ts(s["test"]):
            assert s["test_start"] <= ts < s["test_end"]
        assert set(s["test"].keys()) <= {"A", "B"}


def test_too_few_windows_raises():
    import pytest
    with pytest.raises(ValueError):
        wf.walk_forward_splits(_series(), n_windows=0, embargo_secs=0)
