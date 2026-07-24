"""U5a (2026-07-23 safety bundle): slot position peak_price must update per
cycle.

7/23 loss audit: peak_price == entry on ALL slot records (paper and live) —
MFE analysis was unrecoverable without tick archaeology. The main book updates
peak_price every cycle (via update_trailing_stop at bot.py main exit loop);
the slot exit loop never did. Fix mirrors the Position inline-update semantics
(risk_manager.py:141-144) WITHOUT calling update_trailing_stop — slots like
HTF_L2 are structurally trail-free and must stay that way.
"""
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
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_entry", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_exit", lambda *a, **k: None)
    return tmp_path


def _mk_slot():
    return StrategySlot(
        slot_id="HTF_L2", strategy_name="htf_l2_anticipation",
        timeframe="5m", max_positions=2, capital_pct=0.0, paper_mode=True,
        loss_cap_usdt=-999.0, kelly_min_trades=10**9,
        sl_percent=Config.HTF_L2_SL_PCT, tp_percent=Config.HTF_L2_TP_PCT,
    )


def _bare_bot(slot, monkeypatch):
    df = pd.DataFrame({"close": [100.0] * 60, "open": [100.0] * 60,
                       "high": [100.5] * 60, "low": [99.5] * 60,
                       "volume": [1000.0] * 60, "rsi": [50.0] * 60,
                       "vwap": [99.5] * 60, "ema_9": [100.4] * 60,
                       "ema_21": [100.2] * 60, "ema_50": [99.0] * 60,
                       "ema_200": [95.0] * 60, "adx": [30.0] * 60,
                       "atr": [0.5] * 60})
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = [slot]
    b.risk = SimpleNamespace(positions={}, closed_trades=[],
                             _drawdown_pause_until=0.0)
    b.cycle_count = 5
    b._last_entry_time = 0.0
    b._htf_cache = {}
    b._closing = set()
    b._ws_feed = SimpleNamespace(is_stale=lambda s: True,
                                 get_order_flow=lambda s: None)
    b.exchange = SimpleNamespace(
        get_ohlcv=lambda s, tf, limit=None: df,
        get_order_book=lambda s, depth=None: None,
    )
    b._fetch_htf_data = lambda s: None
    b._compute_confidence = lambda *a, **k: (0, [])
    b._classify_regime = lambda last, df=None: {"label": "TREND", "adx": 30.0}
    monkeypatch.setattr(botmod, "add_all_indicators", lambda d: d)
    return b


def test_long_slot_position_peak_ratchets_up(sandbox, monkeypatch):
    slot = _mk_slot()
    slot.risk.open_position(SYM, 100.0, 15.0, side="long",
                            sl_pct=slot.sl_percent, tp_pct=slot.tp_percent)
    assert slot.risk.positions[SYM].peak_price == 100.0
    b = _bare_bot(slot, monkeypatch)
    b._evaluate_slots([SYM], {SYM: 101.0})   # below TP 102.4 — stays open
    assert slot.risk.positions[SYM].peak_price == 101.0
    b._evaluate_slots([SYM], {SYM: 100.5})   # ratchet-only
    assert slot.risk.positions[SYM].peak_price == 101.0


def test_short_slot_position_peak_ratchets_down(sandbox, monkeypatch):
    slot = _mk_slot()
    slot.risk.open_position(SYM, 100.0, 15.0, side="short",
                            sl_pct=slot.sl_percent, tp_pct=slot.tp_percent)
    b = _bare_bot(slot, monkeypatch)
    b._evaluate_slots([SYM], {SYM: 99.0})    # above TP 97.6 — stays open
    assert slot.risk.positions[SYM].peak_price == 99.0
    b._evaluate_slots([SYM], {SYM: 99.8})
    assert slot.risk.positions[SYM].peak_price == 99.0


def test_peak_lands_on_closed_record(sandbox, monkeypatch):
    """A paper TP close must persist the cycle-updated peak (MFE), not entry."""
    slot = _mk_slot()
    slot.risk.open_position(SYM, 100.0, 15.0, side="long",
                            sl_pct=slot.sl_percent, tp_pct=slot.tp_percent)
    b = _bare_bot(slot, monkeypatch)
    b._evaluate_slots([SYM], {SYM: 103.0})   # >= TP 102.4 — paper close
    assert SYM not in slot.risk.positions
    assert slot.risk.closed_trades[-1]["peak_price"] == 103.0


def test_demoted_slot_paper_close_still_subtracts_sim_fees(sandbox):
    """U5b guard: a demoted (paper_mode) slot's closes must keep netting the
    0.12% sim fee model into pnl_usdt/net_pnl. Verified 2026-07-23 that the
    live state files already satisfy this (the 7/23 recon's 'fee recorded but
    not subtracted' finding double-subtracted; records match gross − 0.12%
    exactly) — this test pins the forward behavior."""
    slot = _mk_slot()
    slot.set_paper()  # demotion path — must re-sync risk.is_paper
    slot.risk.open_position(SYM, 100.0, 15.0, side="long",
                            sl_pct=slot.sl_percent, tp_pct=slot.tp_percent)
    pos = slot.risk.positions[SYM]
    slot.risk.close_position(SYM, 100.0, "hard_time_exit")  # flat exit
    t = slot.risk.closed_trades[-1]
    notional = 100.0 * pos.amount
    expected_fees = notional * 0.12 / 100  # maker 0.01 + taker 0.06 + slip 0.05
    assert t["fees_usdt"] == pytest.approx(expected_fees)
    assert t["pnl_usdt"] == pytest.approx(-expected_fees)
    assert t["net_pnl"] == pytest.approx(-expected_fees)
