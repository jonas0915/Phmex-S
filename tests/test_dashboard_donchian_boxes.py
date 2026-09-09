"""Dashboard SIGNALS section must carry a box for every forward-testing slot.
Regression for 2026-09-08 owner report: the Donchian BTC/ETH paper slots (built
2026-07-16) had trade history and open positions but no card, because
_SIGNAL_BOXES is a hand-maintained list and they were never added."""
import web_dashboard as wd


def test_donchian_slots_are_registered_signal_boxes():
    ids = [slot_id for slot_id, _title, _desc in wd._SIGNAL_BOXES]
    assert "DONCHIAN_BTC" in ids
    assert "DONCHIAN_ETH" in ids


def test_signals_section_renders_a_card_per_donchian_slot():
    states = {
        "DONCHIAN_BTC": {"closed_trades": [], "positions": {}, "peak_balance": 0},
        "DONCHIAN_ETH": {"closed_trades": [], "positions": {}, "peak_balance": 0},
    }
    html = wd._build_signals_section(states)
    assert 'id="sig-DONCHIAN_BTC"' in html
    assert 'id="sig-DONCHIAN_ETH"' in html
