import os, json, time, tempfile, pytest
import risk_manager
import strategy_slot
from strategy_slot import StrategySlot

@pytest.fixture
def slot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # state files land in tmp
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    # RiskManager anchors state_file to its own module dir — patch it too, or slot
    # test trades leak trading_state_t_revert.json into the live bot directory.
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
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

def test_live_pnl_prefers_net_over_gross(slot):
    slot.set_live()
    slot.risk.closed_trades = [
        {"pnl_usdt": -1.0, "net_pnl": -1.2, "mode": "live"},   # net preferred
        {"pnl_usdt": -0.5, "mode": "live"},                     # gross fallback
    ]
    assert slot.live_pnl() == pytest.approx(-1.7)

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

def test_sync_records_slot_close_into_slot_risk(slot, monkeypatch):
    """Live slot position gone from exchange → recorded into slot.risk with mode=live,
    NOT adopted into main risk (the double-management bug this code prevents)."""
    import bot as bot_mod

    slot.set_live()
    slot.risk.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")

    class _FakeExchange:
        def get_open_positions(self):
            return []  # exchange is flat
        def cancel_open_orders(self, symbol):
            pass
        class client:
            @staticmethod
            def fetch_my_trades(symbol, limit=10):
                return []

    class _MainRisk:
        positions = {}
        def close_position(self, *a, **k):
            raise AssertionError("main risk must not record slot close")

    b = bot_mod.Phmex2Bot.__new__(bot_mod.Phmex2Bot)
    b.exchange = _FakeExchange()
    b.risk = _MainRisk()
    b.slots = [slot]
    b._closing = set()
    b._slot_pending_exit_reason = {}  # mirrors __init__ state (st2_hold reason map); __new__ skips __init__

    monkeypatch.setattr(bot_mod, "notifier", type("N", (), {
        "notify_exit": staticmethod(lambda *a, **k: None),
        "send": staticmethod(lambda *a, **k: None),
    })())

    b._sync_exchange_closes(prices={"DOGE/USDT:USDT": 0.081})

    assert slot.risk.positions == {}
    assert slot.risk.closed_trades[-1]["mode"] == "live"
    assert slot.risk.closed_trades[-1]["exit_reason"] == "exchange_close"

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

def test_demote_slot_closes_position_and_flips_mode(slot, monkeypatch):
    import bot as bot_mod
    slot.set_live()
    slot.risk.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")
    calls = {}
    class _FakeExchange:
        def close_long(self, s, a, **kw):  calls["closed"] = (s, a); return {"average": 0.079}
        def close_short(self, s, a, **kw): calls["closed"] = (s, a); return {"average": 0.079}
        def cancel_open_orders(self, s): calls["cancelled"] = s
        def extract_order_fee(self, o, s=None): return 0.0
    monkeypatch.setattr(bot_mod, "notifier", type("N", (), {
        "send": staticmethod(lambda *a, **k: None),
        "notify_exit": staticmethod(lambda *a, **k: None)})())
    b = bot_mod.Phmex2Bot.__new__(bot_mod.Phmex2Bot)
    b.exchange = _FakeExchange()
    b._demote_slot(slot, "test reason")
    assert slot.paper_mode is True
    assert calls.get("closed", (None,))[0] == "DOGE/USDT:USDT"
    assert calls.get("cancelled") == "DOGE/USDT:USDT"
    assert slot.risk.positions == {}
    assert slot.risk.closed_trades[-1]["mode"] == "live"
    assert slot.risk.closed_trades[-1]["exit_reason"] == "slot_demote"

def test_close_slot_position_live_closes_on_exchange(slot, monkeypatch):
    import bot as bot_mod
    slot.set_live()
    slot.risk.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")
    pos = slot.risk.positions["DOGE/USDT:USDT"]
    calls = {}
    class _FakeExchange:
        def close_long(self, s, a, **kw):  calls["closed"] = (s, a); return {"average": 0.0805}
        def close_short(self, s, a, **kw): calls["closed"] = (s, a); return {"average": 0.0805}
        def cancel_open_orders(self, s): calls["cancelled"] = s
        def extract_order_fee(self, o, s=None): return 0.01
    monkeypatch.setattr(bot_mod, "notifier", type("N", (), {
        "send": staticmethod(lambda *a, **k: None),
        "notify_exit": staticmethod(lambda *a, **k: None),
        "notify_paper_exit": staticmethod(lambda *a, **k: None)})())
    b = bot_mod.Phmex2Bot.__new__(bot_mod.Phmex2Bot)
    b.exchange = _FakeExchange()
    ok = b._close_slot_position(slot, "DOGE/USDT:USDT", pos, 0.0805, "adverse_exit")
    assert ok is True
    assert "DOGE/USDT:USDT" not in slot.risk.positions
    t = slot.risk.closed_trades[-1]
    assert t["mode"] == "live" and t["exit_reason"] == "adverse_exit"

def test_live_close_triggers_auto_demote_on_loss_cap(slot, monkeypatch):
    """A live cycle exit that breaches the -$5 live loss cap must demote the slot."""
    import bot as bot_mod
    slot.set_live()
    # Pre-existing live losses just under the cap
    slot.risk.closed_trades = [
        {"pnl_usdt": -2.5, "mode": "live"},
        {"pnl_usdt": -2.4, "mode": "live"},
    ]
    slot.risk.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")
    pos = slot.risk.positions["DOGE/USDT:USDT"]
    class _FakeExchange:
        def close_long(self, s, a, **kw):  return {"average": 0.0799}
        def close_short(self, s, a, **kw): return {"average": 0.0799}
        def cancel_open_orders(self, s): pass
        def extract_order_fee(self, o, s=None): return 0.0
    monkeypatch.setattr(bot_mod, "notifier", type("N", (), {
        "send": staticmethod(lambda *a, **k: None),
        "notify_exit": staticmethod(lambda *a, **k: None),
        "notify_paper_exit": staticmethod(lambda *a, **k: None)})())
    b = bot_mod.Phmex2Bot.__new__(bot_mod.Phmex2Bot)
    b.exchange = _FakeExchange()
    ok = b._close_slot_position(slot, "DOGE/USDT:USDT", pos, 0.0799, "adverse_exit")
    assert ok is True
    # The close pushed live PnL past -$5 → auto-demote must have fired
    assert slot.paper_mode is True

def test_set_live_flips_risk_manager_semantics(slot):
    assert slot.risk.is_paper is True
    slot.set_live()
    assert slot.risk.is_paper is False
    slot.set_paper()
    assert slot.risk.is_paper is True

def test_mode_reload_restores_risk_semantics(slot):
    slot.set_live()
    s2 = StrategySlot(slot_id="t_revert", strategy_name="bb_mean_reversion",
                      timeframe="5m", max_positions=1, capital_pct=0.2, paper_mode=True)
    assert s2.paper_mode is False
    assert s2.risk.is_paper is False
