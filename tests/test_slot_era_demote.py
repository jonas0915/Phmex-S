"""U6 (2026-07-23 safety bundle): era-based should_auto_demote.

HTF_L2 lifetime live net is −$6.22 ≤ the −$5 loss cap, so any re-promotion
would insta-demote on its first close. should_auto_demote now sums only live
trades with closed_at >= promoted_at (mode sidecar), giving each promotion era
a fresh loss_cap budget. promoted_at == 0 (never promoted / legacy) keeps the
old all-live-trades behavior.
"""
import time

import pytest

import risk_manager
import strategy_slot
from strategy_slot import StrategySlot


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    return tmp_path


def _mk_slot(loss_cap=-5.0, kelly_min=10):
    return StrategySlot(
        slot_id="ERA_X", strategy_name="htf_l2_anticipation",
        timeframe="5m", paper_mode=True,
        loss_cap_usdt=loss_cap, kelly_min_trades=kelly_min,
    )


def _live(net, closed_at):
    return {"symbol": "ETH/USDT:USDT", "mode": "live", "net_pnl": net,
            "pnl_usdt": net, "closed_at": closed_at,
            "opened_at": closed_at - 300}


def test_pre_era_losses_excluded(sandbox):
    slot = _mk_slot()
    now = time.time()
    slot.risk.closed_trades = [_live(-6.22, now - 3600)]  # old era: past the cap
    slot.promoted_at = now - 60                           # fresh promotion
    demote, _ = slot.should_auto_demote()
    assert demote is False, "pre-era losses must not consume the new era's budget"


def test_era_losses_at_cap_demote(sandbox):
    slot = _mk_slot()
    now = time.time()
    slot.promoted_at = now - 600
    slot.risk.closed_trades = [_live(-6.22, now - 3600),  # pre-era (ignored)
                               _live(-2.6, now - 120), _live(-2.5, now - 60)]
    demote, reason = slot.should_auto_demote()
    assert demote is True
    assert "loss cap" in reason
    assert "-5.10" in reason  # era sum only, not lifetime −11.32


def test_era_resets_on_new_promotion(sandbox):
    slot = _mk_slot()
    now = time.time()
    slot.promoted_at = now - 600
    slot.risk.closed_trades = [_live(-2.6, now - 120), _live(-2.5, now - 60)]
    assert slot.should_auto_demote()[0] is True
    slot.set_live()  # re-promotion stamps a fresh promoted_at
    assert slot.promoted_at >= now - 1
    assert slot.should_auto_demote()[0] is False  # fresh budget


def test_legacy_zero_promoted_at_counts_all_live(sandbox):
    slot = _mk_slot()
    slot.promoted_at = 0.0
    slot.risk.closed_trades = [_live(-6.22, time.time() - 86400 * 30)]
    assert slot.should_auto_demote()[0] is True  # old behavior preserved


def test_kelly_demote_is_era_scoped(sandbox):
    slot = _mk_slot(loss_cap=-999.0, kelly_min=3)
    now = time.time()
    slot.promoted_at = now - 600
    # Pre-era: 3 losers (negative Kelly on their own). Era: 3 winners.
    slot.risk.closed_trades = [
        _live(-1.0, now - 7200), _live(-1.0, now - 7100), _live(-1.0, now - 7000),
        _live(0.5, now - 300), _live(0.5, now - 200), _live(0.5, now - 100),
    ]
    assert slot.should_auto_demote()[0] is False, "era winners must not inherit pre-era Kelly"
