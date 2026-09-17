"""load_data: era split + holdout refusal. Real-cache tests skip when the cache is absent."""
import sys

import numpy as np
import pandas as pd
import pytest

from research.swarm.lib import load_data as ld


def _frame(n=100, start="2026-01-01", freq="1h"):
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    v = np.linspace(100, 110, n)
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1, "close": v, "volume": 1.0}, index=idx)


def test_holdout_start_is_last_quarter():
    t0, t1 = pd.Timestamp("2026-06-01", tz="UTC"), pd.Timestamp("2026-09-02 23:55", tz="UTC")
    hs = ld.holdout_start(t0, t1)
    assert pd.Timestamp("2026-08-10", tz="UTC") <= hs <= pd.Timestamp("2026-08-11", tz="UTC")


def test_split_era_train_excludes_holdout_rows():
    df = _frame(100)
    train = ld.split_era(df, "train")
    assert len(train) == 75 and train.index.max() < ld.holdout_start(df.index.min(), df.index.max())


def test_split_era_holdout_requires_token():
    df = _frame(100)
    with pytest.raises(ld.HoldoutError):
        ld.split_era(df, "holdout")
    with pytest.raises(ld.HoldoutError):
        ld.split_era(df, "all")
    hold = ld.split_era(df, "holdout", token=ld.COMMITTEE_TOKEN)
    assert len(hold) == 25 and len(ld.split_era(df, "all", token=ld.COMMITTEE_TOKEN)) == 100


def test_split_era_rejects_unknown_era():
    with pytest.raises(ValueError):
        ld.split_era(_frame(10), "test")


def test_symbol_normalisation():
    assert ld._cache_name("ETH") == "ETH_USDT_USDT"
    assert ld._cache_name("ETH_USDT_USDT") == "ETH_USDT_USDT"
    assert ld._cache_name("ETH/USDT:USDT") == "ETH_USDT_USDT"


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_real_mr_edge_train_never_reaches_september():
    df = ld.load_ohlcv("ETH", "5m", era="train")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.tz is not None and df.index.max() < pd.Timestamp("2026-08-11", tz="UTC")


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_real_funding_schema():
    f = ld.load_funding("ETH")
    assert list(f.columns) == ["ts", "rate"] and f["ts"].dt.tz is not None and len(f) > 100


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_real_funding_train_default_excludes_holdout():
    t0, t1 = ld._mr_edge_1h_bounds("ETH")
    hs = ld.holdout_start(t0, t1)
    f = ld.load_funding("ETH")
    assert (f["ts"] < hs).all()


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_real_funding_holdout_requires_token():
    with pytest.raises(ld.HoldoutError):
        ld.load_funding("ETH", era="holdout")


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_real_funding_holdout_with_token_returns_only_holdout_rows():
    t0, t1 = ld._mr_edge_1h_bounds("ETH")
    hs = ld.holdout_start(t0, t1)
    f = ld.load_funding("ETH", era="holdout", token=ld.COMMITTEE_TOKEN)
    assert len(f) > 0 and (f["ts"] >= hs).all()


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_fetch_ohlcv_ccxt_gates_late_until_without_network(monkeypatch):
    # sys.modules["ccxt"] = None makes any "import ccxt" raise ImportError; if the holdout
    # guard did not fire before that import, this test would see ImportError, not
    # HoldoutError, proving the check runs before the lazy network-dependency import.
    monkeypatch.setitem(sys.modules, "ccxt", None)
    t0, t1 = ld._mr_edge_1h_bounds("ETH")
    late_until_ms = int(ld.holdout_start(t0, t1).timestamp() * 1000)
    with pytest.raises(ld.HoldoutError):
        ld.fetch_ohlcv_ccxt("ETH", "1h", since_ms=0, until_ms=late_until_ms)


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_fetch_ohlcv_ccxt_gates_none_until_as_now(monkeypatch):
    # until_ms=None means "now", which is always at/after the (long-past) holdout boundary.
    monkeypatch.setitem(sys.modules, "ccxt", None)
    with pytest.raises(ld.HoldoutError):
        ld.fetch_ohlcv_ccxt("ETH", "1h", since_ms=0, until_ms=None)
