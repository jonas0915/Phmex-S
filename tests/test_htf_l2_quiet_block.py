"""U1 (2026-07-23 safety bundle): QUIET-regime HARD-BLOCK on the HTF_L2 slot.

Main path hard-blocks quiet_regime entries (bot.py [REGIME GATE]); the slot
path only recorded the tag as a would-block. 7/23 loss audit: 3/6 slot losers
were quiet-tagged, −$3.57 = 57% of slot loss, 0 quiet winners. For
slot_id=="HTF_L2" ONLY, the same condition main blocks on must block the slot
entry too. Flag: Config.HTF_L2_QUIET_BLOCK_ENABLED (default true).
"""
import json
import os
from types import SimpleNamespace

import pandas as pd
import pytest

import bot as botmod
import risk_manager
import strategy_slot
from config import Config
from strategy_slot import StrategySlot

SYM = "BTC/USDT:USDT"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Isolate every state/sidecar/log write into tmp_path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_entry", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_exit", lambda *a, **k: None)
    return tmp_path


def _df_5m(n=60):
    """5m frame that satisfies htf_l2_anticipation's LONG setup at close=100."""
    rows = {
        "close": [100.0] * n, "open": [100.0] * n,
        "high": [100.5] * n, "low": [99.5] * n,
        "volume": [1000.0] * n,
        "rsi": [50.0] * n, "vwap": [99.5] * n,
        "ema_9": [100.4] * n, "ema_21": [100.2] * n, "ema_50": [99.0] * n,
        "ema_200": [95.0] * n, "adx": [30.0] * n, "atr": [0.5] * n,
    }
    return pd.DataFrame(rows)


def _htf_df(adx=25.0, n=40):
    return pd.DataFrame({
        "close": [110.0] * n, "ema_21": [105.0] * n, "ema_50": [100.0] * n,
        "adx": [adx] * n,
    })


def _flow(tc=80):
    return {"buy_ratio": 0.62, "cvd_slope": 0.5, "divergence": None,
            "large_trade_bias": 0.0, "trade_count": tc}


def _ob():
    return {"imbalance": 0.1, "bid_walls": [], "ask_walls": [],
            "spread_pct": 0.05, "bid_depth_usdt": 200000.0,
            "ask_depth_usdt": 100000.0, "illiquid": False}


def _mk_slot(slot_id="HTF_L2"):
    return StrategySlot(
        slot_id=slot_id, strategy_name="htf_l2_anticipation",
        timeframe="5m", max_positions=2, capital_pct=0.0, paper_mode=True,
        trade_amount_usdt=None, loss_cap_usdt=-999.0, kelly_min_trades=10**9,
        durable_trail_enabled=False,
        sl_percent=Config.HTF_L2_SL_PCT, tp_percent=Config.HTF_L2_TP_PCT,
    )


def _bare_bot(slot, monkeypatch, quiet=False):
    """Minimal bot able to run _evaluate_slots for one paper slot."""
    df, htf, flow, ob = _df_5m(), _htf_df(), _flow(), _ob()
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = [slot]
    b.risk = SimpleNamespace(positions={}, closed_trades=[],
                             _drawdown_pause_until=0.0)
    b.cycle_count = 5
    b._last_entry_time = 0.0
    b._htf_cache = {}
    b._ws_feed = SimpleNamespace(is_stale=lambda s: True,
                                 get_order_flow=lambda s: flow)
    b.exchange = SimpleNamespace(
        get_ohlcv=lambda s, tf, limit=None: df,
        get_order_book=lambda s, depth=None: ob,
    )
    b._fetch_htf_data = lambda s: htf
    b._compute_confidence = lambda *a, **k: (5, ["l"] * 5)
    label = "QUIET" if quiet else "TREND"
    b._classify_regime = lambda last, df=None: {"label": label, "adx": 22.0}
    monkeypatch.setattr(botmod, "add_all_indicators", lambda d: d)
    return b


def _run(b):
    b._evaluate_slots([SYM], {SYM: 100.0})


def test_quiet_blocks_htf_l2_slot_entry(sandbox, monkeypatch):
    slot = _mk_slot()
    b = _bare_bot(slot, monkeypatch, quiet=True)
    _run(b)
    assert SYM not in slot.risk.positions, "QUIET entry must be hard-blocked on HTF_L2"
    assert slot.blocked_counts.get("quiet_regime", 0) == 1
    # counter persisted to the blocked sidecar (dashboard propagation surface)
    with open(sandbox / "trading_state_HTF_L2_blocked.json") as f:
        assert json.load(f).get("quiet_regime") == 1


def test_not_quiet_entry_proceeds(sandbox, monkeypatch):
    slot = _mk_slot()
    b = _bare_bot(slot, monkeypatch, quiet=False)
    _run(b)
    assert SYM in slot.risk.positions
    assert slot.blocked_counts.get("quiet_regime", 0) == 0


def test_flag_off_restores_tag_only_behavior(sandbox, monkeypatch):
    monkeypatch.setattr(Config, "HTF_L2_QUIET_BLOCK_ENABLED", False)
    slot = _mk_slot()
    b = _bare_bot(slot, monkeypatch, quiet=True)
    _run(b)
    assert SYM in slot.risk.positions, "flag off: QUIET must not block (old behavior)"
    assert slot.blocked_counts.get("quiet_regime", 0) == 0


def test_other_slots_unaffected_by_quiet(sandbox, monkeypatch):
    """MR-style slots may legitimately trade quiet — only HTF_L2 hard-blocks."""
    slot = _mk_slot(slot_id="OTHER_SLOT")
    b = _bare_bot(slot, monkeypatch, quiet=True)
    _run(b)
    assert SYM in slot.risk.positions
    assert slot.blocked_counts.get("quiet_regime", 0) == 0
