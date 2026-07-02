"""5m_mean_revert RSI floor (2026-07-02): block deep-oversold LONGS.

Forward-test of the 2026-06-30 90d replay lead (reports/mr_replay_90d.json):
longs with RSI(7)<22 are the falling-knife cohort (n=21, maker −$4.08); the
22–30 band carried the edge (n=132, maker +$12.05). The floor blocks slot
longs below Config.MEAN_REVERT_LONG_RSI_MIN (0.0 = disabled), shorts and all
other slots untouched. These tests pin: the RSI parse from the signal reason,
the config knob, and the bot.py call site (gate fires bump_blocked +
continue, longs only, 5m_mean_revert only).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import _rsi_from_reason
from config import Config

BOT_SRC = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "bot.py")).read()


# ── RSI parse from signal reason ──────────────────────────────────────────

def test_parses_bb_long_reason():
    reason = "BB mean reversion LONG | lower BB bounce | RSI(7)=21.4 | vol=2.1x"
    assert _rsi_from_reason(reason) == 21.4


def test_parses_bb_short_reason():
    reason = "BB mean reversion SHORT | upper BB rejection | RSI(7)=82.5 | vol=1.3x"
    assert _rsi_from_reason(reason) == 82.5


def test_parses_integer_rsi():
    assert _rsi_from_reason("... RSI(7)=22 | ...") == 22.0


def test_no_rsi_returns_none():
    assert _rsi_from_reason("htf_l2_anticipation | ob_imbalance 0.3") is None


def test_none_reason_returns_none():
    assert _rsi_from_reason(None) is None


def test_empty_reason_returns_none():
    assert _rsi_from_reason("") is None


# ── Config knob ───────────────────────────────────────────────────────────

def test_config_knob_exists_and_is_float():
    assert isinstance(Config.MEAN_REVERT_LONG_RSI_MIN, float)


# ── Call-site contract (source-level pin, mirrors test_entry_snapshot_ob) ─

def _gate_block():
    """The mr_rsi_floor gate block in bot.py source."""
    m = re.search(
        r"if \(slot\.slot_id == \"5m_mean_revert\" and direction == \"long\""
        r".{0,4000}?continue\n",
        BOT_SRC, re.DOTALL)
    assert m, "mr_rsi_floor gate block not found in bot.py"
    return m.group(0)


def test_gate_exists_and_bumps_blocked_then_continues():
    block = _gate_block()
    assert 'bump_blocked("mr_rsi_floor")' in block
    assert block.rstrip().endswith("continue")


def test_gate_is_long_only_and_slot_keyed():
    block = _gate_block()
    assert 'slot.slot_id == "5m_mean_revert"' in block
    assert 'direction == "long"' in block


def test_gate_disabled_at_zero():
    # 0.0 must disable the gate entirely (default-off contract)
    assert "Config.MEAN_REVERT_LONG_RSI_MIN > 0" in _gate_block()


def test_gate_fails_open_without_rsi():
    # No RSI in reason -> no block (gate only fires on a parsed value)
    assert "_mr_rsi is not None" in _gate_block()
