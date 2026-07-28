import sys
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import inspect


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
