"""Bounded maker re-quote for slot live entries (2026-07-01).

The 5m_mean_revert slot loses ~85% of live entry attempts to PostOnly misses
(2 fills / 13 attempts since 6/17), and the missed-fill counterfactual
(reports/mr_missed_fills.json) showed the misses were net winners (+$3.55,
9W/2L). On a miss, the slot may now re-place ONE PostOnly order at the fresh
touch — still maker, never taker — unless price has drifted adversely past
Config.SLOT_REQUOTE_MAX_DRIFT_PCT from the signal price. Slot-keyed via
StrategySlot.requote_attempts (default 0 = off everywhere); only
5m_mean_revert opts in. The shared exchange._try_limit_entry is untouched, so
the main bot's entry path cannot be affected.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import _requote_drift_pct
from config import Config
from strategy_slot import StrategySlot

BOT_SRC = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "bot.py")).read()


# ── adverse-drift computation ─────────────────────────────────────────────

def test_long_drift_positive_when_price_ran_up():
    # long wanted 100, touch now 100.2 -> 0.2% adverse
    assert abs(_requote_drift_pct("long", 100.0, 100.2) - 0.2) < 1e-9


def test_short_drift_positive_when_price_ran_down():
    # short wanted 100, touch now 99.8 -> 0.2% adverse
    assert abs(_requote_drift_pct("short", 100.0, 99.8) - 0.2) < 1e-9


def test_long_drift_negative_when_price_came_back():
    # long wanted 100, touch now 99.9 -> better entry, drift negative
    assert _requote_drift_pct("long", 100.0, 99.9) < 0


def test_short_drift_negative_when_price_came_back():
    assert _requote_drift_pct("short", 100.0, 100.1) < 0


# ── slot field ────────────────────────────────────────────────────────────

def test_requote_attempts_defaults_off(tmp_path, monkeypatch):
    import risk_manager, strategy_slot
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    s = StrategySlot(slot_id="t_rq", strategy_name="bb_mean_reversion",
                     timeframe="5m", max_positions=1, capital_pct=0.2,
                     paper_mode=True)
    assert s.requote_attempts == 0


def test_config_drift_cap_exists_and_is_float():
    assert isinstance(Config.SLOT_REQUOTE_MAX_DRIFT_PCT, float)


# ── call-site contract (source-level pins) ────────────────────────────────

def _requote_block():
    m = re.search(
        r"if not order and slot\.requote_attempts > 0.{0,4000}?"
        r"if not order:",
        BOT_SRC, re.DOTALL)
    assert m, "re-quote block not found in bot.py live entry path"
    return m.group(0)


def test_requote_has_zombie_guard():
    # Review #2 hardening: never place a second entry while the first order
    # may still rest on the book (cancel + status fetch both failed).
    block = _requote_block()
    assert "fetch_open_orders" in block
    assert "reduceOnly" in block


def test_requote_outcomes_reach_telegram_and_dashboard():
    # CLAUDE.md propagation rule: every outcome persists via the slot counter
    # sidecar (renders in the md report + Telegram "Counters" line) and the
    # [MR REQUOTE] log tag feeds the dashboard gates panel.
    block = _requote_block()
    for tag in ("requote_fill", "requote_miss",
                "requote_abort_drift", "requote_abort_zombie"):
        assert f'bump_blocked("{tag}")' in block, f"missing counter: {tag}"


def test_requote_block_exists_and_is_slot_keyed():
    block = _requote_block()
    assert "slot.requote_attempts" in block


def test_requote_has_drift_guard():
    block = _requote_block()
    assert "Config.SLOT_REQUOTE_MAX_DRIFT_PCT" in block
    assert "_requote_drift_pct" in block


def test_requote_stays_maker_reuses_open_calls():
    # Re-quote must go through open_long/open_short (PostOnly path) — no
    # market/taker calls inside the block.
    block = _requote_block()
    assert "open_long" in block and "open_short" in block
    assert "market" not in block.lower()


def test_requote_logs_evidence_tag():
    # [MR REQUOTE] is the dashboard/analysis join key — must be logged.
    assert "[MR REQUOTE]" in _requote_block()


def test_only_mean_revert_opts_in():
    # requote_attempts must be set on exactly one slot: 5m_mean_revert.
    sets = re.findall(r"requote_attempts\s*=\s*(\d+)", BOT_SRC)
    # one field default in nothing (field lives in strategy_slot.py) + one
    # instantiation here
    assert len(sets) == 1 and sets[0] == "1", (
        f"expected exactly one requote_attempts=1 in bot.py, found {sets}")
    inst = re.search(r'slot_id="5m_mean_revert".{0,2000}?requote_attempts=1',
                     BOT_SRC, re.DOTALL)
    assert inst, "requote_attempts=1 not on the 5m_mean_revert instantiation"
