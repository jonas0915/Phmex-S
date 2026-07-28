import os
import sys
import tempfile

sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import inspect

import pytest


def test_sr_bounce_slot_registered():
    import bot as botmod
    src = inspect.getsource(botmod.Phmex2Bot.__init__)
    assert 'slot_id="SR_BOUNCE"' in src
    assert '"sr_bounce"' in src        # strategy_name is a real STRATEGIES key


def test_sr_bounce_slot_is_paper_5_dollars():
    import bot as botmod
    src = inspect.getsource(botmod.Phmex2Bot.__init__)
    block = src[src.index('slot_id="SR_BOUNCE"'):src.index('slot_id="SR_BOUNCE"') + 900]
    assert "trade_amount_usdt=5.0" in block
    assert "paper_mode=True" in block
    assert "max_positions=1" in block


def test_slot_entry_paths_honor_structural_levels():
    import bot as botmod
    src = inspect.getsource(botmod.Phmex2Bot._evaluate_slots)
    assert src.count('getattr(signal, "sl_price", None)') >= 2  # paper + live sites


def test_shim_forces_atr0_short_geometry_verbatim():
    """2026-07-28 review fix, CRITICAL 3: open_position's atr>0 branch
    (risk_manager.py:565-599) clamps/widens sl_pct/tp_pct — caps realized R:R
    at 2:1 and can widen the stop up to 1.5x the structural distance. Both
    bot.py shim sites now force atr=0 when the shim is active, so the
    exact-percentage branch (risk_manager.py:593-599) applies the converted
    levels verbatim. Reproduces the exact shim math for a SHORT signal
    (sl_price above entry, tp_price below — the mirrored orientation from the
    long case already covered by test_slot_sl_tp_override) and asserts
    open_position(atr=0, ...) preserves it: stop_loss > entry > take_profit."""
    from risk_manager import RiskManager

    entry = 100.0
    sig_sl = 103.0   # short: structural stop ABOVE entry
    sig_tp = 94.0    # short: structural target BELOW entry

    # Exact shim conversion from bot.py's _evaluate_slots (both call sites):
    #   _sl_pct = abs(price - _sig_sl) / price * 100.0
    #   _tp_pct = abs(_sig_tp - price) / price * 100.0
    sl_pct = abs(entry - sig_sl) / entry * 100.0
    tp_pct = abs(sig_tp - entry) / entry * 100.0
    assert sl_pct == pytest.approx(3.0)
    assert tp_pct == pytest.approx(6.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        rm = RiskManager(state_file=os.path.join(tmpdir, "sr_bounce_geom_test.json"))
        pos = rm.open_position("TEST/USDT:USDT", entry, 10.0, side="short",
                               atr=0.0, sl_pct=sl_pct, tp_pct=tp_pct)

    assert pos.stop_loss > entry > pos.take_profit
    assert pos.stop_loss == pytest.approx(sig_sl)
    assert pos.take_profit == pytest.approx(sig_tp)
