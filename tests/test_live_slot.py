import os, json, time, tempfile, pytest
import strategy_slot
from strategy_slot import StrategySlot

@pytest.fixture
def slot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # state files land in tmp
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    s = StrategySlot(slot_id="t_revert", strategy_name="bb_mean_reversion",
                     timeframe="5m", max_positions=1, capital_pct=0.2, paper_mode=True)
    return s

def _fake_trade(pnl, mode=None, ts=None):
    t = {"pnl_usdt": pnl, "closed_at": ts or time.time()}
    if mode:
        t["mode"] = mode
    return t

def test_promote_persists_and_reloads(slot, tmp_path, monkeypatch):
    slot.set_live(capital_pct=0.2)
    assert slot.paper_mode is False
    assert slot.promoted_at > 0
    s2 = StrategySlot(slot_id="t_revert", strategy_name="bb_mean_reversion",
                      timeframe="5m", max_positions=1, capital_pct=0.5, paper_mode=True)
    assert s2.paper_mode is False
    assert s2.promoted_at == pytest.approx(slot.promoted_at)

def test_demote_persists(slot):
    slot.set_live(capital_pct=0.2)
    slot.set_paper()
    s2 = StrategySlot(slot_id="t_revert", strategy_name="bb_mean_reversion",
                      timeframe="5m", max_positions=1, capital_pct=0.2, paper_mode=False)
    assert s2.paper_mode is True

def test_live_pnl_excludes_paper_history(slot):
    slot.set_live()
    slot.risk.closed_trades = [
        _fake_trade(-20.0),
        _fake_trade(-2.0, mode="live"),
        _fake_trade(-1.5, mode="live"),
    ]
    assert slot.live_pnl() == pytest.approx(-3.5)

def test_auto_demote_on_loss_cap(slot):
    slot.set_live()
    slot.risk.closed_trades = [_fake_trade(-2.6, mode="live"), _fake_trade(-2.5, mode="live")]
    demote, reason = slot.should_auto_demote()
    assert demote and "loss cap" in reason

def test_auto_demote_on_negative_kelly_needs_10_trades(slot):
    slot.set_live()
    slot.risk.closed_trades = [_fake_trade(-0.4, mode="live")] * 9
    demote, _ = slot.should_auto_demote()
    assert not demote
    slot.risk.closed_trades = ([_fake_trade(0.1, mode="live")] * 3 +
                               [_fake_trade(-0.4, mode="live")] * 7)
    demote, reason = slot.should_auto_demote()
    assert demote and "kelly" in reason.lower()

def test_no_demote_when_healthy(slot):
    slot.set_live()
    slot.risk.closed_trades = ([_fake_trade(0.5, mode="live")] * 7 +
                               [_fake_trade(-0.4, mode="live")] * 5)
    demote, _ = slot.should_auto_demote()
    assert not demote

def test_close_position_records_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from risk_manager import RiskManager
    rm = RiskManager(state_file=str(tmp_path / "state.json"))
    rm.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")
    rm.close_position("DOGE/USDT:USDT", 0.081, "take_profit", mode="live")
    assert rm.closed_trades[-1]["mode"] == "live"
    rm.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")
    rm.close_position("DOGE/USDT:USDT", 0.081, "take_profit")
    assert "mode" not in rm.closed_trades[-1]

def test_owner_map_includes_live_slots(slot):
    from bot import _build_position_owners
    class _MainRisk:
        positions = {"BTC/USDT:USDT": object()}
    slot.set_live()
    slot.risk.positions = {"DOGE/USDT:USDT": object()}
    paper = StrategySlot(slot_id="t_paper", strategy_name="bb_mean_reversion",
                         timeframe="5m", paper_mode=True)
    paper.risk.positions = {"ETH/USDT:USDT": object()}
    owners = _build_position_owners(_MainRisk(), [slot, paper])
    assert "BTC/USDT:USDT" in owners and owners["BTC/USDT:USDT"][1] is None
    assert "DOGE/USDT:USDT" in owners and owners["DOGE/USDT:USDT"][1] is slot
    assert "ETH/USDT:USDT" not in owners
