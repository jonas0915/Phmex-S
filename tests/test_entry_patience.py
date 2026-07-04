"""Slot-keyed entry patience (2026-07-03): extend PostOnly rest for 5m_mean_revert.

Basis: measured — 9 of the slot's 11 missed winners saw price return through
the limit within 60s (reports/mr_missed_fills.json misses + fresh 1m candles);
misses are winners for THIS slot (+$3.55/11) and mean-reversion wants to be
filled on the way back. Main bot stays at 20s — its patience buys back-of-queue
toxic fills (queue study 2026-07-03) and its misses are measured protective.

Wiring: exchange._try_limit_entry gains patience_s (default 20.0 = exact old
behavior); open_long/open_short pass it through; StrategySlot.entry_patience_s
(default None = 20s); only 5m_mean_revert sets 45.0 (not 60 — keeps worst-case
entry stall [45s + 20s re-quote] × 2 signals under the 180s cycle SIGALRM).
"""
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange import Exchange
from strategy_slot import StrategySlot

BOT_SRC = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "bot.py")).read()
EXCH_SRC = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "exchange.py")).read()


def test_try_limit_entry_has_patience_param_default_20():
    sig = inspect.signature(Exchange._try_limit_entry)
    assert "patience_s" in sig.parameters
    assert sig.parameters["patience_s"].default == 20.0


def test_open_long_short_pass_patience_default_20():
    for fn in (Exchange.open_long, Exchange.open_short):
        sig = inspect.signature(fn)
        assert "patience_s" in sig.parameters
        assert sig.parameters["patience_s"].default == 20.0


def test_poll_loop_derived_from_patience():
    # the 40×0.5s loop must be computed from patience_s, not hardcoded
    assert "range(40)" not in EXCH_SRC
    assert re.search(r"int\(\s*patience_s\s*/\s*0\.5\s*\)", EXCH_SRC)


def test_slot_field_defaults_none(tmp_path, monkeypatch):
    import risk_manager, strategy_slot
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    s = StrategySlot(slot_id="t_pat", strategy_name="bb_mean_reversion",
                     timeframe="5m", max_positions=1, capital_pct=0.2,
                     paper_mode=True)
    assert s.entry_patience_s is None


def test_only_mean_revert_opts_in_at_45():
    sets = re.findall(r"entry_patience_s\s*=\s*([\d.]+)", BOT_SRC)
    assert sets == ["45.0"], f"expected exactly one entry_patience_s=45.0, got {sets}"
    inst = re.search(r'slot_id="5m_mean_revert".{0,2500}?entry_patience_s=45\.0',
                     BOT_SRC, re.DOTALL)
    assert inst, "entry_patience_s=45.0 not on the 5m_mean_revert instantiation"


def test_slot_live_entry_passes_patience():
    # the first slot live entry call must forward the slot's patience
    m = re.search(
        r"order = \(self\.exchange\.open_long\(symbol, margin, price,\s*"
        r"patience_s=_patience\)", BOT_SRC)
    assert m, "slot live entry does not pass patience_s"
    assert "_patience = (slot.entry_patience_s" in BOT_SRC


def test_requote_stays_at_default_patience():
    # the re-quote must NOT inherit the long patience (worst-case stall bound):
    # inside the re-quote block, open_* is called without patience_s
    rq = re.search(r"if not order and slot\.requote_attempts > 0.{0,4000}?if not order:",
                   BOT_SRC, re.DOTALL).group(0)
    assert "patience_s" not in rq, "re-quote must use default 20s patience"


def test_one_patient_attempt_per_cycle():
    # After a long-patience MISS, the slot must stop attempting entries for the
    # rest of the cycle (bounds worst-case stall under the ~120s watchdog
    # budget — review #3 WARN). Pin: flag init before the symbol loop, break on
    # patient miss, and the symbol-loop early exit.
    assert "_patient_missed = False" in BOT_SRC
    assert re.search(r"if _patience > 20\.0:\s*\n\s*_patient_missed = True[^\n]*\n\s*break",
                     BOT_SRC)
    assert re.search(r"if _patient_missed:\s*\n\s*break", BOT_SRC)
