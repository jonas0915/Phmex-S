"""Purged, embargoed, expanding walk-forward splits over the lab's snapshot stream.

Replaces the single 70/30 chronological split. The full time span is divided into
n_windows+1 equal segments; window i trains on everything before test block i and
tests on block i (expanding train, tiled non-overlapping test blocks). An embargo
gap is removed at each train/test boundary so a snapshot's forward-return label (the
~15-min horizon) cannot leak from train into the test window.

A candidate that only wins on one window is regime-luck, not edge — callers should
require it to hold across the aggregate of these out-of-sample blocks.
"""


def _select(by_symbol, lo, hi):
    """Records with lo <= ts < hi (hi=None means no upper bound), per symbol.
    Symbols with no qualifying records are dropped from the returned dict."""
    out = {}
    for sym, recs in by_symbol.items():
        kept = [r for r in recs
                if r.get("ts", 0) >= lo and (hi is None or r.get("ts", 0) < hi)]
        if kept:
            out[sym] = kept
    return out


def walk_forward_splits(by_symbol, n_windows, embargo_secs=0):
    """Return a list of n_windows dicts:
        {"train": by_symbol, "test": by_symbol, "test_start": ts, "test_end": ts}

    Train = records with ts < test_start - embargo_secs (purged).
    Test  = records with test_start <= ts < test_end.
    """
    if n_windows < 1:
        raise ValueError("n_windows must be >= 1")

    ts_all = [r.get("ts", 0) for recs in by_symbol.values() for r in recs]
    if not ts_all:
        raise ValueError("no records to split")
    t_min, t_max = min(ts_all), max(ts_all)
    span = t_max - t_min
    if span <= 0:
        raise ValueError("all records share one timestamp — cannot walk-forward")

    seg = span / (n_windows + 1)  # segment 0 is the initial training burn-in
    splits = []
    for i in range(n_windows):
        test_start = t_min + seg * (i + 1)
        test_end = t_min + seg * (i + 2) if i < n_windows - 1 else t_max + 1
        train = _select(by_symbol, t_min, test_start - embargo_secs)
        test = _select(by_symbol, test_start, test_end)
        splits.append({
            "train": train,
            "test": test,
            "test_start": test_start,
            "test_end": test_end,
        })
    return splits
