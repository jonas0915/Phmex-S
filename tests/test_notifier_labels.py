"""Pin the 2026-07-03 Telegram truthfulness fixes (audit findings 1-6).

Staged for the next audited restart — the live bot imported the old notifier
at its start, so these behaviors go live only after a /pre-restart-audit restart.
"""
import os

import pytest

import notifier

BOT_PY = os.path.join(os.path.dirname(__file__), "..", "bot.py")


@pytest.fixture
def sent(monkeypatch):
    """Capture notifier.send() messages instead of hitting Telegram."""
    msgs = []
    monkeypatch.setattr(notifier, "send", msgs.append)
    return msgs


# --- Finding 1: partial-TP copy no longer lies about breakeven SL ------------

def test_partial_tp_copy_no_breakeven_lie(sent):
    notifier.notify_partial_tp("BTC/USDT:USDT", "long", 100.0, 0.55, 11.0)
    assert len(sent) == 1
    msg = sent[0]
    assert "breakeven" not in msg.lower()
    # Truthful copy: runner keeps the ORIGINAL SL/trail and targets +25% ROI.
    assert "ORIGINAL SL/trail" in msg
    assert "+25% ROI" in msg  # PARTIAL_RUNNER_TP_ROI=25.0 in .env / default


# --- Finding 2: paper entry/exit accept + render a slot label ----------------

def test_paper_entry_accepts_slot_label(sent):
    notifier.notify_paper_entry("ETH/USDT:USDT", "long", 2500.0, 10.0, 0.8,
                                "test reason", slot="5m_mean_revert")
    assert "[5m_mean_revert]" in sent[0]


def test_paper_exit_accepts_slot_label(sent):
    notifier.notify_paper_exit("ETH/USDT:USDT", "short", 2500.0, 2490.0,
                               0.4, 4.0, "take_profit", slot="ST2.0")
    assert "[ST2.0]" in sent[0]


def test_paper_notifs_slot_optional_backcompat(sent):
    # Old positional call signature must keep working (live main-path callers).
    notifier.notify_paper_entry("X/USDT:USDT", "long", 1.0, 5.0, 0.5, "r")
    notifier.notify_paper_exit("X/USDT:USDT", "long", 1.0, 1.1, 0.1, 1.0, "r")
    assert len(sent) == 2
    assert "[]" not in sent[0] and "[] " not in sent[1]


# --- Finding 3: exit-reason matching handles slot suffixes -------------------

def test_exit_reason_slot_suffix_stop_loss(sent):
    notifier.notify_exit("SOL/USDT:USDT", "long", 100.0, 98.8, -1.2, -12.0,
                         "stop_loss [slot 5m_mean_revert]")
    msg = sent[0]
    assert "STOP LOSS" in msg          # pretty label rendered, not raw upper()
    assert "🔴" in msg                 # matching emoji
    assert "[slot 5m_mean_revert]" in msg  # suffix still displayed


def test_exit_reason_slot_suffix_take_profit_and_trail(sent):
    notifier.notify_exit("SOL/USDT:USDT", "long", 100.0, 101.6, 1.6, 16.0,
                         "take_profit [slot 5m_mean_revert]")
    notifier.notify_exit("SOL/USDT:USDT", "long", 100.0, 101.0, 1.0, 10.0,
                         "trailing_stop [slot ST2.0]")
    assert "TAKE PROFIT" in sent[0] and "✅" in sent[0]
    assert "TRAILING STOP" in sent[1] and "🎯" in sent[1]


def test_exit_reason_plain_still_matches(sent):
    notifier.notify_exit("SOL/USDT:USDT", "long", 100.0, 101.6, 1.6, 16.0,
                         "take_profit")
    assert "TAKE PROFIT" in sent[0]


# --- Finding 4: entry TP line flags the backstop when partial-TP armed -------

def test_entry_tp_backstop_hint_when_armed(sent, monkeypatch):
    monkeypatch.setenv("PARTIAL_TP_ROI", "10.0")
    monkeypatch.setenv("PARTIAL_RUNNER_TP_ROI", "25.0")
    notifier.notify_entry("BTC/USDT:USDT", "long", 100.0, 10.0, 98.8, 101.6,
                          0.9, "test")
    msg = sent[0]
    assert "backstop" in msg
    assert "+10% ROI" in msg and "runner +25%" in msg


def test_entry_tp_no_hint_when_partial_tp_off(sent, monkeypatch):
    monkeypatch.setenv("PARTIAL_TP_ROI", "0")
    notifier.notify_entry("BTC/USDT:USDT", "long", 100.0, 10.0, 98.8, 101.6,
                          0.9, "test")
    assert "backstop" not in sent[0]


# --- Finding 5: startup line reports the strategy that actually trades -------

def test_startup_mentions_htf_l2_anticipation(sent):
    notifier.notify_startup(58.44, ["BTC/USDT:USDT"], "live", "confluence")
    msg = sent[0]
    assert "htf_l2_anticipation" in msg
    assert "confluence router" in msg


# --- Finding 6: shadow gate-tags no longer hardcode retired blocked hours ----

def test_bot_no_hardcoded_shadow_hour_set():
    with open(BOT_PY) as f:
        src = f.read()
    assert "{0, 1, 2, 17, 18, 19, 20}" not in src
    assert "Config.TRADING_BLOCKED_HOURS_UTC" in src
