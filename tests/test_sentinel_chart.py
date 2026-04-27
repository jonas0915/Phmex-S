"""Tests for Sentinel-era cumulative PnL chart helpers in web_dashboard.py."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web_dashboard import (
    SENTINEL_DEPLOY_TS,
    SENTINEL_CULL_TS,
    _cull_marker_index,
)


def test_sentinel_deploy_ts_matches_2026_04_02_06_01_utc():
    """Sentinel deployed 2026-04-01 23:01 PT = 2026-04-02 06:01 UTC."""
    from datetime import datetime, timezone
    expected = datetime(2026, 4, 2, 6, 1, 0, tzinfo=timezone.utc).timestamp()
    assert SENTINEL_DEPLOY_TS == expected


def test_sentinel_cull_ts_matches_commit_479f879():
    """Strategy cull (Option A) commit 479f879 landed 2026-04-26 19:22:55 PT."""
    from datetime import datetime, timezone
    expected = datetime(2026, 4, 27, 2, 22, 55, tzinfo=timezone.utc).timestamp()
    assert SENTINEL_CULL_TS == expected


def test_cull_marker_index_returns_first_post_cull_index():
    """Index is 1-based, matching the chart's x-axis (trade #1, #2, ...)."""
    trades = [
        {"opened_at": SENTINEL_CULL_TS - 100},  # pre-cull
        {"opened_at": SENTINEL_CULL_TS - 50},   # pre-cull
        {"opened_at": SENTINEL_CULL_TS + 10},   # first post-cull
        {"opened_at": SENTINEL_CULL_TS + 20},   # post-cull
    ]
    assert _cull_marker_index(trades) == 3


def test_cull_marker_index_returns_none_when_no_post_cull_trades():
    trades = [
        {"opened_at": SENTINEL_CULL_TS - 100},
        {"opened_at": SENTINEL_CULL_TS - 50},
    ]
    assert _cull_marker_index(trades) is None


def test_cull_marker_index_returns_none_for_empty_list():
    assert _cull_marker_index([]) is None


def test_cull_marker_index_falls_back_to_closed_at_when_opened_at_missing():
    """Mirrors the existing render-path filter at web_dashboard.py:1369."""
    trades = [
        {"closed_at": SENTINEL_CULL_TS - 50},
        {"closed_at": SENTINEL_CULL_TS + 10},
    ]
    assert _cull_marker_index(trades) == 2
