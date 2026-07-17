"""F4 (2026-07-17): adoption records carry provenance (adopted/adopted_at).

Bug class: restart sync (strategy="synced", opened_at=now) and orphan adoption
mint entry-shaped records indistinguishable from real entries — the 6/14
"pause bypass" that wasn't, and prefill_toxicity.py already string-matches
"synced" to work around it. Additive fields only, .get()-defaulted on load
(same precedent as sl_ratcheted/scaled_out).
"""
import inspect
import json
import time

import bot as botmod
from risk_manager import Position, RiskManager


def _pos(**kw):
    base = dict(symbol="BTC/USDT:USDT", side="long", entry_price=60000.0,
                amount=0.001, margin=6.0, stop_loss=59280.0, take_profit=60960.0)
    base.update(kw)
    return Position(**base)


def _rm(tmp_path, name="test_state.json"):
    rm = RiskManager(state_file="nonexistent_f4_fixture.json")
    rm.state_file = str(tmp_path / name)
    rm.positions = {}
    rm.closed_trades = []
    return rm


def test_position_defaults_not_adopted():
    p = _pos()
    assert p.adopted is False
    assert p.adopted_at == 0.0


def test_sync_positions_sets_adopted_fields(tmp_path):
    rm = _rm(tmp_path)
    rm.sync_positions([{"symbol": "BTC/USDT:USDT", "side": "long",
                        "entry_price": 60000.0, "amount": 0.001,
                        "margin": 6.0}], current_cycle=5)
    pos = rm.positions["BTC/USDT:USDT"]
    assert pos.strategy == "synced"
    assert pos.adopted is True
    assert time.time() - pos.adopted_at < 60


def test_adopt_orphan_source_sets_adopted_fields():
    src = inspect.getsource(botmod.Phmex2Bot._adopt_orphan_position)
    assert "adopted = True" in src or "adopted=True" in src
    assert "adopted_at" in src


def test_adopted_fields_survive_save_load(tmp_path):
    rm = _rm(tmp_path)
    p = _pos()
    p.adopted = True
    p.adopted_at = 1234567890.0
    rm.positions["BTC/USDT:USDT"] = p
    rm._save_state()
    rm2 = _rm(tmp_path)
    rm2._load_state()
    p2 = rm2.positions["BTC/USDT:USDT"]
    assert p2.adopted is True
    assert p2.adopted_at == 1234567890.0


def test_old_state_file_defaults_adopted_false(tmp_path):
    state = {"peak_balance": 0, "closed_trades": [], "trade_results": [],
             "positions": {"BTC/USDT:USDT": {
                 "symbol": "BTC/USDT:USDT", "side": "long",
                 "entry_price": 60000.0, "amount": 0.001, "margin": 6.0,
                 "stop_loss": 59280.0, "take_profit": 60960.0}}}
    f = tmp_path / "old_state.json"
    f.write_text(json.dumps(state))
    rm = _rm(tmp_path)
    rm.state_file = str(f)
    rm._load_state()
    pos = rm.positions["BTC/USDT:USDT"]
    assert pos.adopted is False
    assert pos.adopted_at == 0.0


def test_closed_trade_carries_adopted(tmp_path):
    rm = _rm(tmp_path)
    p = _pos()
    p.adopted = True
    p.adopted_at = 1234567890.0
    p.opened_at = time.time() - 300
    rm.positions["BTC/USDT:USDT"] = p
    rm.close_position("BTC/USDT:USDT", 60600.0, "test_exit")
    t = rm.closed_trades[-1]
    assert t.get("adopted") is True
    assert t.get("adopted_at") == 1234567890.0


def test_normal_entry_not_marked_adopted(tmp_path):
    rm = _rm(tmp_path)
    pos = rm.open_position("BTC/USDT:USDT", 60000.0, 6.0, side="long",
                           strategy="htf_l2_anticipation")
    assert pos.adopted is False
