"""Test the htf_confluence_pullback trend-flip exit rule."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd


def _fake_htf_df(ema21_over_ema50: bool) -> pd.DataFrame:
    """Build a minimal 1h dataframe with EMA21/50 in the requested state."""
    rows = []
    for i in range(60):
        close = 100.0
        rows.append({
            "timestamp": i * 3600 * 1000,
            "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000,
        })
    df = pd.DataFrame(rows)
    if ema21_over_ema50:
        df["ema_21"] = 105.0
        df["ema_50"] = 100.0
    else:
        df["ema_21"] = 95.0
        df["ema_50"] = 100.0
    return df


def test_htf_trend_flip_exit_fires_on_long_when_ema21_crosses_below_ema50():
    from bot import _check_htf_trend_flip_exit
    htf_df = _fake_htf_df(ema21_over_ema50=False)
    should_exit, reason = _check_htf_trend_flip_exit(side="long", htf_df=htf_df)
    assert should_exit is True
    assert reason == "htf_trend_flip_exit"


def test_htf_trend_flip_exit_does_not_fire_when_trend_still_valid():
    from bot import _check_htf_trend_flip_exit
    htf_df = _fake_htf_df(ema21_over_ema50=True)
    should_exit, reason = _check_htf_trend_flip_exit(side="long", htf_df=htf_df)
    assert should_exit is False


def test_htf_trend_flip_exit_mirror_for_short():
    from bot import _check_htf_trend_flip_exit
    htf_df = _fake_htf_df(ema21_over_ema50=True)  # trend turned up = bad for short
    should_exit, reason = _check_htf_trend_flip_exit(side="short", htf_df=htf_df)
    assert should_exit is True
    assert reason == "htf_trend_flip_exit"


def test_htf_trend_flip_exit_handles_none_df():
    from bot import _check_htf_trend_flip_exit
    should_exit, reason = _check_htf_trend_flip_exit(side="long", htf_df=None)
    assert should_exit is False


def test_htf_trend_flip_exit_handles_missing_ema_columns():
    from bot import _check_htf_trend_flip_exit
    df = pd.DataFrame([{"close": 100}])
    should_exit, reason = _check_htf_trend_flip_exit(side="long", htf_df=df)
    assert should_exit is False
