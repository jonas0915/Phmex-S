"""Tests for scripts/slot_lab/mr_edge_fetch.py — fixed-window OHLCV/funding paginator.

No network: every exchange is a fake. The live bot is never imported.
"""
import json
import os
import sys

import pandas as pd
import pytest

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts", "slot_lab"))

import mr_edge_fetch as mef  # noqa: E402

TF5 = 300_000


# ---------------------------------------------------------------------------
# fakes
# ---------------------------------------------------------------------------

class FakeExchange:
    """Serves a synthetic candle series in chunks of `limit`, with an optional
    duplicate-boundary bar (returns one bar *before* `since` too) and optional
    transient errors on the first N calls."""

    def __init__(self, first_ts, n_bars, tf_ms=TF5, overlap=False, fail_first=0,
                 fail_exc=None, missing=()):
        self.series = [
            [first_ts + i * tf_ms, 1.0 + i, 2.0 + i, 0.5 + i, 1.5 + i, 100.0 + i]
            for i in range(n_bars) if i not in set(missing)
        ]
        self.tf_ms = tf_ms
        self.overlap = overlap
        self.fail_first = fail_first
        self.fail_exc = fail_exc
        self.calls = []

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls.append(("ohlcv", symbol, timeframe, since, limit))
        if self.fail_first > 0:
            self.fail_first -= 1
            raise self.fail_exc
        start = since - self.tf_ms if (self.overlap and since is not None) else since
        out = [r for r in self.series if r[0] >= start]
        return [list(r) for r in out[:limit]]


class FakeFunding:
    def __init__(self, first_ts, n, step_ms=8 * 3600_000):
        self.rows = [{"timestamp": first_ts + i * step_ms, "fundingRate": 0.0001 * (i + 1)}
                     for i in range(n)]
        self.calls = []

    def fetch_funding_rate_history(self, symbol, since=None, limit=None, params=None):
        self.calls.append((symbol, since, limit))
        out = [r for r in self.rows if r["timestamp"] >= (since or 0)]
        return [dict(r) for r in out[:limit]]


# ---------------------------------------------------------------------------
# symkey / expected bars
# ---------------------------------------------------------------------------

def test_symkey_replaces_slash_and_colon():
    assert mef.symkey("BTC/USDT:USDT") == "BTC_USDT_USDT"
    assert mef.symkey("1000PEPE/USDT:USDT") == "1000PEPE_USDT_USDT"


def test_expected_bars_math():
    start = mef.parse_utc_date("2026-06-01")
    until = mef.parse_utc_date("2026-09-03")
    assert until - start == 94 * 86_400_000
    assert mef.expected_bars(start, until, "5m") == 94 * 288
    assert mef.expected_bars(start, until, "1m") == 94 * 1440
    assert mef.expected_bars(start, until, "1h") == 94 * 24
    assert mef.expected_calls(mef.expected_bars(start, until, "5m"), 1000) == 28  # ceil(27072/1000)


def test_tf_ms_table():
    assert mef.TF_MS["1m"] == 60_000
    assert mef.TF_MS["5m"] == 300_000
    assert mef.TF_MS["1h"] == 3_600_000


# ---------------------------------------------------------------------------
# paginator
# ---------------------------------------------------------------------------

def test_paginate_chunks_and_stops_at_until():
    first = 1_700_000_000_000
    ex = FakeExchange(first, n_bars=2500)
    since = first
    until = first + 2100 * TF5           # 2100 bars in window
    rows = mef.paginate_ohlcv(ex, "X/USDT:USDT", "5m", since, until,
                              limit=1000, sleep_fn=lambda s: None)
    assert len(rows) == 2100
    assert rows[0][0] == since
    assert rows[-1][0] == until - TF5    # bar >= until dropped
    assert all(rows[i][0] < rows[i + 1][0] for i in range(len(rows) - 1))
    # 3 calls: 1000, 1000, then 100 needed (fake returns up to 1000 but we clip)
    assert len(ex.calls) == 3
    # since advanced by last_ts + tf_ms each call
    assert ex.calls[1][3] == first + 1000 * TF5
    assert ex.calls[2][3] == first + 2000 * TF5


def test_paginate_dedupes_duplicate_boundary_bars():
    first = 1_700_000_000_000
    ex = FakeExchange(first, n_bars=2500, overlap=True)
    since = first
    until = first + 1500 * TF5
    rows = mef.paginate_ohlcv(ex, "X/USDT:USDT", "5m", since, until,
                              limit=1000, sleep_fn=lambda s: None)
    ts = [r[0] for r in rows]
    assert len(ts) == len(set(ts)) == 1500
    assert ts == sorted(ts)


def test_paginate_stops_on_short_batch():
    """Series ends before `until` (symbol listed late / delisted) — no infinite loop."""
    first = 1_700_000_000_000
    ex = FakeExchange(first, n_bars=1300)
    until = first + 5000 * TF5
    rows = mef.paginate_ohlcv(ex, "X/USDT:USDT", "5m", first, until,
                              limit=1000, sleep_fn=lambda s: None)
    assert len(rows) == 1300
    assert len(ex.calls) == 2


def test_paginate_empty_batch_returns_empty():
    first = 1_700_000_000_000
    ex = FakeExchange(first, n_bars=0)
    rows = mef.paginate_ohlcv(ex, "X/USDT:USDT", "5m", first, first + 10 * TF5,
                              limit=1000, sleep_fn=lambda s: None)
    assert rows == []
    assert len(ex.calls) == 1


def test_paginate_retries_transient_errors():
    import ccxt
    first = 1_700_000_000_000
    slept = []
    ex = FakeExchange(first, n_bars=50, fail_first=2,
                      fail_exc=ccxt.NetworkError("boom"))
    rows = mef.paginate_ohlcv(ex, "X/USDT:USDT", "5m", first, first + 50 * TF5,
                              limit=1000, sleep_fn=slept.append)
    assert len(rows) == 50
    assert len(ex.calls) == 3          # 2 failures + 1 success
    assert any(s >= 5 for s in slept)  # backoff sleep happened


def test_paginate_gives_up_after_max_generic_errors():
    first = 1_700_000_000_000
    ex = FakeExchange(first, n_bars=50, fail_first=99, fail_exc=RuntimeError("perma"))
    with pytest.raises(mef.FetchFailed):
        mef.paginate_ohlcv(ex, "X/USDT:USDT", "5m", first, first + 50 * TF5,
                           limit=1000, sleep_fn=lambda s: None, max_errors=3)
    assert len(ex.calls) == 3


def test_paginate_spacing_sleep_between_calls():
    first = 1_700_000_000_000
    slept = []
    ex = FakeExchange(first, n_bars=2500)
    mef.paginate_ohlcv(ex, "X/USDT:USDT", "5m", first, first + 2100 * TF5,
                       limit=1000, sleep_fn=slept.append, spacing=0.6)
    # a spacing sleep after every call that is followed by another call
    assert slept.count(0.6) >= 2


# ---------------------------------------------------------------------------
# rows -> DataFrame (must match mean_revert_replay._cached convention)
# ---------------------------------------------------------------------------

def test_rows_to_df_matches_cache_convention():
    first = 1_700_000_000_000
    rows = [[first + i * TF5, 1, 2, 0.5, 1.5, 10] for i in range(3)]
    df = mef.rows_to_df(rows)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "timestamp"
    assert str(df.index.tz) == "UTC"
    assert df.index.is_monotonic_increasing
    assert len(df) == 3


def test_rows_to_df_empty():
    df = mef.rows_to_df([])
    assert df.empty


# ---------------------------------------------------------------------------
# gap detection
# ---------------------------------------------------------------------------

def test_gap_stats_finds_gaps_gt_two_bars():
    first = 1_700_000_000_000
    ts = [first + i * TF5 for i in range(20)]
    # remove bars 5,6,7 (gap of 3 missing => 4 bars between neighbours) and bar 12 (1 missing)
    ts = [t for i, t in enumerate(ts) if i not in (5, 6, 7, 12)]
    g = mef.gap_stats(ts, "5m")
    assert g["largest_gap_bars"] == 4            # 4..8 = 4 bar-steps
    assert g["missing_bars"] == 4                # 3 + 1
    assert len(g["gaps_gt2"]) == 1
    assert g["gaps_gt2"][0]["missing"] == 3


def test_gap_stats_empty_and_single():
    assert mef.gap_stats([], "5m")["largest_gap_bars"] == 0
    assert mef.gap_stats([1], "5m")["largest_gap_bars"] == 0


# ---------------------------------------------------------------------------
# resume-skip
# ---------------------------------------------------------------------------

def test_should_skip_requires_file_and_complete_manifest(tmp_path):
    path = tmp_path / "BTC_USDT_USDT_5m.pkl"
    key = "BTC_USDT_USDT_5m"
    manifest = {key: {"complete": True}}
    assert mef.should_skip(str(path), key, manifest, resume=True) is False  # no file
    path.write_bytes(b"x")
    assert mef.should_skip(str(path), key, manifest, resume=True) is True
    assert mef.should_skip(str(path), key, {key: {"complete": False}}, resume=True) is False
    assert mef.should_skip(str(path), key, {}, resume=True) is False
    assert mef.should_skip(str(path), key, manifest, resume=False) is False


# ---------------------------------------------------------------------------
# funding pagination
# ---------------------------------------------------------------------------

def test_paginate_funding_covers_window_and_stops():
    first = 1_700_000_000_000
    step = 8 * 3600_000
    fx = FakeFunding(first, n=400, step_ms=step)
    since = first
    until = first + 285 * step      # 285 settlements in window
    out = mef.paginate_funding(fx, "X/USDT:USDT", since, until, limit=100,
                               sleep_fn=lambda s: None)
    assert len(out) == 285
    assert out[0] == {"ts": first, "rate": pytest.approx(0.0001)}
    assert out[-1]["ts"] == until - step
    assert all(out[i]["ts"] < out[i + 1]["ts"] for i in range(len(out) - 1))
    assert len(fx.calls) == 3
    assert fx.calls[1][1] == first + 99 * step + 1   # since = last_ts + 1


def test_paginate_funding_short_series():
    first = 1_700_000_000_000
    fx = FakeFunding(first, n=10)
    out = mef.paginate_funding(fx, "X/USDT:USDT", first, first + 10 ** 12, limit=100,
                               sleep_fn=lambda s: None)
    assert len(out) == 10
    assert len(fx.calls) == 1


# ---------------------------------------------------------------------------
# June parity
# ---------------------------------------------------------------------------

def test_june_parity_match_rate(tmp_path):
    first = 1_780_000_000_000
    rows = [[first + i * TF5, 1, 2, 0.5, 1.5 + i, 10] for i in range(10)]
    df = mef.rows_to_df(rows)
    csv = tmp_path / "X_USDT_USDT_5m.csv"
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(6):   # overlap on 6 bars, one of them deliberately wrong
        t = pd.Timestamp(first + i * TF5, unit="ms", tz="UTC")
        close = 1.5 + i if i != 3 else 999.0
        lines.append(f"{t.strftime('%Y-%m-%d %H:%M:%S+00:00')},1,2,0.5,{close},10")
    csv.write_text("\n".join(lines) + "\n")
    res = mef.june_parity(df, str(csv))
    assert res["overlap_n"] == 6
    assert res["match_n"] == 5
    assert res["match_rate"] == pytest.approx(5 / 6)


def test_june_parity_no_overlap(tmp_path):
    df = mef.rows_to_df([[1_790_000_000_000, 1, 2, 0.5, 1.5, 10]])
    csv = tmp_path / "X.csv"
    csv.write_text("timestamp,open,high,low,close,volume\n2026-05-20 04:00:00+00:00,1,2,0.5,1.5,10\n")
    res = mef.june_parity(df, str(csv))
    assert res["overlap_n"] == 0
    assert res["match_rate"] is None


# ---------------------------------------------------------------------------
# plan (dry-run) + manifest checkpoint
# ---------------------------------------------------------------------------

def test_build_plan_counts():
    start = mef.parse_utc_date("2026-06-01")
    until = mef.parse_utc_date("2026-09-03")
    plan = mef.build_plan(["BTC/USDT:USDT", "ETH/USDT:USDT"], ["5m", "1h"], start, until,
                          funding=True)
    ohlcv = [p for p in plan if p["kind"] == "ohlcv"]
    fund = [p for p in plan if p["kind"] == "funding"]
    assert len(ohlcv) == 4 and len(fund) == 2
    b5 = next(p for p in ohlcv if p["tf"] == "5m")
    assert b5["expected"] == 94 * 288 and b5["calls"] == 28
    b1h = next(p for p in ohlcv if p["tf"] == "1h")
    assert b1h["expected"] == 94 * 24 and b1h["calls"] == 3
    assert fund[0]["expected"] == 94 * 3 and fund[0]["calls"] == 3


def test_manifest_roundtrip(tmp_path):
    path = str(tmp_path / "manifest.json")
    assert mef.load_manifest(path) == {}
    mef.save_manifest(path, {"a": {"complete": True}})
    assert json.load(open(path)) == {"a": {"complete": True}}
    assert mef.load_manifest(path) == {"a": {"complete": True}}
