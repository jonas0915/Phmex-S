import pandas as pd
import pytest
from sr_levels import atr, adx, find_pivots, cluster_zones, count_touches, validated_zones


def _df(rows):
    """rows = list of (high, low, close); open synthesized as prev close."""
    df = pd.DataFrame(rows, columns=["high", "low", "close"])
    df["open"] = df["close"].shift(1).fillna(df["close"])
    return df


def test_find_pivots_simple_v():
    # lows: descend to index 3 then ascend — index 3 is the swing low (k=3)
    lows = [10, 9, 8, 5, 8, 9, 10]
    rows = [(l + 1, l, l + 0.5) for l in lows]
    los, his = find_pivots(_df(rows), k=3)
    assert los == [3]


def test_find_pivots_edge_indices_excluded():
    lows = [1, 9, 8, 7, 8, 9, 10]   # index 0 is lowest but within k of edge
    rows = [(l + 1, l, l + 0.5) for l in lows]
    los, _ = find_pivots(_df(rows), k=3)
    assert los == []


def test_cluster_zones_merges_within_width():
    zones = cluster_zones([100.0, 100.3, 105.0], width=0.5)
    assert zones == [(100.0, 100.3), (105.0, 105.0)]


def test_count_touches_requires_close_outside_and_gap():
    # zone [99, 100]; candles: touch+close-out, inside-close (no), too-soon touch (no), later touch (yes)
    rows = [
        (101, 99.5, 100.5),   # enters zone, closes above → touch 1
        (100.5, 99.2, 99.5),  # enters, closes INSIDE → not a touch
        (101, 99.5, 100.4),   # enters, closes out, but only 2 after touch1 → gap fail
        (102, 101, 101.5),    # never enters
        (101, 99.8, 100.6),   # enters, closes out, gap ok → touch 2
    ]
    assert count_touches(_df(rows), lo=99.0, hi=100.0, min_gap=3) == 2


def test_validated_zones_min_touches_filters():
    # Build 40 candles: repeated bounces off ~100 (support, 3 touches),
    # single spike high at 120 (resistance, 1 touch) — only support survives.
    rows = []
    for cyc in range(4):
        base = [(106, 104, 105), (104, 102, 103), (102, 99.8, 101),
                (104, 101, 103.5), (106, 103, 105), (107, 104, 106),
                (108, 105, 107), (107, 104, 105), (106, 103, 104), (105, 102, 103)]
        rows.extend(base)
    zones = validated_zones(_df(rows), k=3, width_mult=0.25, min_touches=2)
    assert any(z["side"] == "support" and z["lo"] <= 100 <= z["hi"] + 1 for z in zones)
    assert all(z["touches"] >= 2 for z in zones)


def test_atr_and_adx_shapes():
    rows = [(i + 1.0, i, i + 0.5) for i in range(40)]
    df = _df(rows)
    assert len(atr(df)) == 40 and atr(df).iloc[-1] > 0
    assert len(adx(df)) == 40
