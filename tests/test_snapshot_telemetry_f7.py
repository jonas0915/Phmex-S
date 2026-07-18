"""F7 (2026-07-17): entry_snapshot must store the axes the signal R&D could
not test — RSI, EMA21/50 distance, VWAP distance, raw depths, wall prices.

Verified absent from all 214 historical snapshots (bot.py:3095-3098 stored
wall COUNTS only, no RSI/EMA/VWAP/raw-depth). Without these, pullback-depth
and RSI-band questions were UNVERIFIABLE. Additive fields; consumers read
snapshots defensively via .get.
"""
import pandas as pd

import bot as botmod


def _bare_bot():
    b = object.__new__(botmod.Phmex2Bot)
    return b


def _row():
    return pd.Series({"close": 100.0, "rsi": 44.0, "rsi_fast": 38.0,
                      "ema_21": 101.0, "ema_50": 98.0, "vwap": 102.0,
                      "open": 99.5, "high": 100.5, "low": 99.0, "volume": 5.0,
                      "adx": 22.0, "ema_9": 100.2, "atr": 0.5})


def test_snapshot_stores_new_axes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    b = _bare_bot()
    ob = {"imbalance": 0.1, "bid_walls": [[99.0, 500.0]], "ask_walls": [],
          "spread_pct": 0.02, "best_bid": 99.98, "best_ask": 100.02,
          "bid_depth_usdt": 12000.0, "ask_depth_usdt": 9000.0}
    flow = {"buy_ratio": 0.6, "cvd_slope": 0.1, "divergence": None,
            "large_trade_bias": 0.0, "trade_count": 30}
    snap = b._log_entry_snapshot("BTC/USDT:USDT", "long", "5m_scalp",
                                 "htf_l2_anticipation", 0.82, 100.0, 5,
                                 ob, flow, ohlcv_last=_row(), htf_adx=28.0)
    assert snap["rsi"] == 44.0
    assert snap["rsi_fast"] == 38.0
    assert abs(snap["ema21_dist_pct"] - ((100.0 - 101.0) / 101.0 * 100)) < 1e-3
    assert abs(snap["ema50_dist_pct"] - ((100.0 - 98.0) / 98.0 * 100)) < 1e-3
    assert abs(snap["vwap_dist_pct"] - ((100.0 - 102.0) / 102.0 * 100)) < 1e-3
    assert snap["ob"]["bid_depth_usdt"] == 12000.0
    assert snap["ob"]["ask_depth_usdt"] == 9000.0
    assert snap["ob"]["first_bid_wall"] == 99.0
    assert snap["ob"]["first_ask_wall"] is None


def test_snapshot_missing_fields_default_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").mkdir()
    b = _bare_bot()
    snap = b._log_entry_snapshot("BTC/USDT:USDT", "long", "5m_scalp",
                                 "htf_l2_anticipation", 0.82, 100.0, 5,
                                 None, None, ohlcv_last=None, htf_adx=None)
    assert snap["rsi"] is None
    assert snap["ema21_dist_pct"] is None
    assert snap["vwap_dist_pct"] is None
    assert snap["ob"] is None
