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


# ---------------------------------------------------------------------------
# screen-era context for reference symbols (2026-09-20 fix: a cross-asset signal
# must not hard-code era="train" — the screen supplies the era via screen_context and
# the signal loads its second symbol through load_reference / load_reference_funding).
# All frames below are synthetic (written to tmp_path); no real holdout rows are read.
# ---------------------------------------------------------------------------

def _synthetic_cache(tmp_path, monkeypatch, n=100):
    """A tmp dataset 'synth' with an ETH 1h pkl, plus mr_edge re-pointed at the same dir
    (with a funding json) so load_funding's bounds anchor works without the real cache."""
    d = tmp_path / "cache"
    d.mkdir()
    df = _frame(n)
    df.to_pickle(d / "ETH_USDT_USDT_1h.pkl")
    ts_ms = [int(t.timestamp() * 1000) for t in df.index]
    (d / "funding_ETH_USDT_USDT.json").write_text(
        pd.Series([{"ts": t, "rate": 0.0001} for t in ts_ms]).to_json(orient="values"))
    spec = {"dir": "cache", "pattern": "{sym}_{tf}.pkl", "timeframes": ("1h",), "span": "synthetic"}
    monkeypatch.setitem(ld.DATASETS, "synth", spec)
    monkeypatch.setitem(ld.DATASETS, "mr_edge", spec)
    return df


def test_screen_context_default_is_train_without_token():
    assert ld.get_screen_context() == ("train", None, None)


def test_load_reference_without_context_is_a_train_load(tmp_path, monkeypatch):
    df = _synthetic_cache(tmp_path, monkeypatch)
    ref = ld.load_reference("ETH", "1h", dataset="synth", root=tmp_path)
    train = ld.load_ohlcv("ETH", "1h", era="train", dataset="synth", root=tmp_path)
    assert len(ref) == 75 and ref.equals(train)
    assert ref.index.max() < ld.holdout_start(df.index.min(), df.index.max())


def test_load_reference_inside_holdout_context_with_token_returns_holdout_rows(tmp_path, monkeypatch):
    df = _synthetic_cache(tmp_path, monkeypatch)
    hs = ld.holdout_start(df.index.min(), df.index.max())
    with ld.screen_context("holdout", ld.COMMITTEE_TOKEN):
        ref = ld.load_reference("ETH", "1h", dataset="synth", root=tmp_path)
    assert len(ref) == 25 and (ref.index >= hs).all()


def test_load_reference_inside_holdout_context_without_token_raises(tmp_path, monkeypatch):
    _synthetic_cache(tmp_path, monkeypatch)
    with ld.screen_context("holdout", None):
        with pytest.raises(ld.HoldoutError):
            ld.load_reference("ETH", "1h", dataset="synth", root=tmp_path)


def test_screen_context_is_restored_after_block_and_on_exception(tmp_path, monkeypatch):
    _synthetic_cache(tmp_path, monkeypatch)
    with ld.screen_context("holdout", ld.COMMITTEE_TOKEN):
        assert ld.get_screen_context() == ("holdout", ld.COMMITTEE_TOKEN, None)
        with ld.screen_context("train", None):
            assert ld.get_screen_context() == ("train", None, None)
        assert ld.get_screen_context() == ("holdout", ld.COMMITTEE_TOKEN, None)
    assert ld.get_screen_context() == ("train", None, None)
    with pytest.raises(RuntimeError):
        with ld.screen_context("holdout", ld.COMMITTEE_TOKEN):
            raise RuntimeError("boom")
    assert ld.get_screen_context() == ("train", None, None)
    # the context alone never grants holdout: a plain load_ohlcv outside it is still train-only
    with pytest.raises(ld.HoldoutError):
        ld.load_ohlcv("ETH", "1h", era="holdout", dataset="synth", root=tmp_path)


def test_set_screen_context_returns_reset_handle(tmp_path, monkeypatch):
    handle = ld.set_screen_context("holdout", ld.COMMITTEE_TOKEN)
    try:
        assert ld.get_screen_context() == ("holdout", ld.COMMITTEE_TOKEN, None)
    finally:
        ld.reset_screen_context(handle)
    assert ld.get_screen_context() == ("train", None, None)


def test_load_reference_funding_follows_screen_context(tmp_path, monkeypatch):
    df = _synthetic_cache(tmp_path, monkeypatch)
    hs = ld.holdout_start(df.index.min(), df.index.max())
    f_train = ld.load_reference_funding("ETH", root=tmp_path)
    assert list(f_train.columns) == ["ts", "rate"] and (f_train["ts"] < hs).all() and len(f_train) == 75
    with ld.screen_context("holdout", ld.COMMITTEE_TOKEN):
        f_hold = ld.load_reference_funding("ETH", root=tmp_path)
    assert len(f_hold) == 25 and (f_hold["ts"] >= hs).all()
    with ld.screen_context("holdout", None):
        with pytest.raises(ld.HoldoutError):
            ld.load_reference_funding("ETH", root=tmp_path)


def test_load_reference_clips_to_until_and_reference_until_keeps_era_token(tmp_path, monkeypatch):
    df = _synthetic_cache(tmp_path, monkeypatch)
    cut = df.index[40]
    with ld.screen_context("train", None, until=cut):
        ref = ld.load_reference("ETH", "1h", dataset="synth", root=tmp_path)
        f = ld.load_reference_funding("ETH", root=tmp_path)
    assert len(ref) == 41 and ref.index.max() == cut
    assert len(f) == 41 and f["ts"].max() == cut
    hs = ld.holdout_start(df.index.min(), df.index.max())
    cut_h = df.index[80]
    with ld.screen_context("holdout", ld.COMMITTEE_TOKEN):
        with ld.reference_until(cut_h):
            assert ld.get_screen_context() == ("holdout", ld.COMMITTEE_TOKEN, cut_h)
            ref = ld.load_reference("ETH", "1h", dataset="synth", root=tmp_path)
        assert ld.get_screen_context() == ("holdout", ld.COMMITTEE_TOKEN, None)
    assert (ref.index >= hs).all() and ref.index.max() == cut_h and len(ref) == 6
    assert ld.get_screen_context() == ("train", None, None)
