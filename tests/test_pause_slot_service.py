"""F1 (2026-07-17): global pause must not freeze live-slot exits, and must
still block ALL slot entries (paper included).

Bug: bot.py's `_trading_paused` return fired BEFORE `_evaluate_all_slots`, so
during `.pause_trading` the live 5m_mean_revert slot's software exits and SL
ratchet froze (only the exchange-resting durable SL protected it). The
`.halt_main_entries` branch already solved this by servicing slots before its
return — the pause branch must mirror it. Subtlety: the paper-mode slot entry
branch had NO pause check (the live branch did, bot.py:2535), so naively
servicing slots during pause would resume PAPER entries mid-pause.
"""
import inspect
from types import SimpleNamespace

import bot as botmod


def _bare_bot(tmp_path, monkeypatch, drawdown_until=0.0):
    monkeypatch.chdir(tmp_path)
    b = object.__new__(botmod.Phmex2Bot)
    b.risk = SimpleNamespace(_drawdown_pause_until=drawdown_until)
    return b


def test_pause_branch_services_slots_before_return():
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    pause_idx = src.find("if getattr(self, '_trading_paused', False):")
    halt_idx = src.find('if os.path.exists(".halt_main_entries"):')
    assert pause_idx != -1 and halt_idx != -1 and pause_idx < halt_idx
    pause_block = src[pause_idx:halt_idx]
    assert "_evaluate_all_slots(" in pause_block, (
        "pause branch must service slots (exits/ratchet) before returning, "
        "mirroring the .halt_main_entries branch"
    )


def test_slot_entries_blocked_helper_pause_sentinel(tmp_path, monkeypatch):
    b = _bare_bot(tmp_path, monkeypatch)
    assert b._slot_entries_blocked() is False
    (tmp_path / ".pause_trading").write_text("test halt")
    assert b._slot_entries_blocked() is True


def test_slot_entries_blocked_helper_drawdown_pause(tmp_path, monkeypatch):
    import time
    b = _bare_bot(tmp_path, monkeypatch, drawdown_until=time.time() + 600)
    assert b._slot_entries_blocked() is True
    b.risk._drawdown_pause_until = 0.0
    assert b._slot_entries_blocked() is False


def test_both_slot_entry_branches_use_guard():
    src = inspect.getsource(botmod.Phmex2Bot._evaluate_slots)
    paper_idx = src.find("if slot.paper_mode:")
    assert paper_idx != -1
    live_idx = src.find("LIVE slot entry", paper_idx)
    assert live_idx != -1
    paper_branch = src[paper_idx:live_idx]
    live_branch = src[live_idx:live_idx + 2000]
    assert "_slot_entries_blocked()" in paper_branch, (
        "paper entry branch must check the global pause guard"
    )
    assert "_slot_entries_blocked()" in live_branch, (
        "live entry branch must use the shared guard"
    )
