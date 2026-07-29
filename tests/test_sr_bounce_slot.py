import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import inspect

import pandas as pd
import pytest


def _bot_shaped_htf(n, marker_last=True):
    """Shaped like what exchange.get_ohlcv() actually returns: a DatetimeIndex
    AS THE INDEX, no separate ts column (see test_sr_bounce.py's
    _bot_shaped_1h). marker_last tags the exchange's final row (the
    still-forming current-hour candle) with an out-of-band close value so
    tests can prove it was dropped rather than cached."""
    rows = []
    for i in range(n):
        rows.append((100.0 + i * 0.001, 100.5 + i * 0.001,
                     99.5 + i * 0.001, 100.0 + i * 0.001))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["volume"] = 100.0
    df.index = pd.to_datetime([i * 3_600_000 for i in range(n)], unit="ms")
    df.index.name = "timestamp"
    if marker_last:
        df.iloc[-1, df.columns.get_loc("close")] = 999999.0
    return df


def _bare_bot_for_fetch(df_to_return):
    import bot as botmod
    b = object.__new__(botmod.Phmex2Bot)
    b._sr_htf_cache = {}
    b.exchange = SimpleNamespace(get_ohlcv=lambda s, tf, limit=None: df_to_return)
    return b


def test_fetch_sr_bounce_htf_drops_forming_bar():
    """2026-07-28 review fix, N1: the exchange's last returned row is the
    still-forming current-hour candle — its high/low/close keep moving until
    the hour closes. Caching it for the whole hour (prior behavior) deflated
    ATR/zone width vs the scan's closed-bars-only discipline. The fetch must
    drop it before caching/returning."""
    import bot as botmod
    n = 150
    df = _bot_shaped_htf(n)
    b = _bare_bot_for_fetch(df)
    out = botmod.Phmex2Bot._fetch_sr_bounce_htf(b, "ETH/USDT:USDT")
    assert out is not None
    assert len(out) == n - 1
    # the marker value (forming bar) must not survive into the cached frame
    assert 999999.0 not in out["close"].values
    assert list(out.index) == list(range(n - 1))  # RangeIndex — scan-engine-faithful


def test_fetch_sr_bounce_htf_length_gate_applies_after_drop():
    """A 100-row exchange fetch yields only 99 CLOSED bars once the forming
    bar is dropped — that must fall under the >=100 floor (fall through to
    stale cache / None), not be cached as a full 100-row frame."""
    import bot as botmod
    df = _bot_shaped_htf(100)
    b = _bare_bot_for_fetch(df)
    out = botmod.Phmex2Bot._fetch_sr_bounce_htf(b, "ETH/USDT:USDT")
    assert out is None
    assert "ETH/USDT:USDT" not in b._sr_htf_cache


def test_fetch_sr_bounce_htf_101_rows_passes_gate_after_drop():
    """101 fetched rows -> 100 closed bars after the drop -> clears the gate."""
    import bot as botmod
    df = _bot_shaped_htf(101)
    b = _bare_bot_for_fetch(df)
    out = botmod.Phmex2Bot._fetch_sr_bounce_htf(b, "ETH/USDT:USDT")
    assert out is not None
    assert len(out) == 100


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
