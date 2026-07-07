"""Tests for the "bot is blind" alerting (built 2026-07-06).

Covers:
  1. BlindMonitor.check_ws_blind — the stale→alert-once→cooldown→recovery
     state machine (bot.py).
  2. BlindMonitor.check_cycle_gap — the retroactive stall-recovery notice.
  3. overwatch.check_bot_log_freshness — the external log-freshness check.

All fixture-based: notify is a list collector, subprocess is stubbed,
log files live in tmp_path. No network, no Telegram, no live bot.
"""
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from bot import BlindMonitor

PT = ZoneInfo("America/Los_Angeles")

# Fixed anchor: 2026-07-06 05:34:00 PT (the real morning outage start).
T0 = datetime(2026, 7, 6, 5, 34, 0, tzinfo=PT).timestamp()


@pytest.fixture
def monitor():
    sent = []
    mon = BlindMonitor(notify=sent.append)
    return mon, sent


# ── WS-blind state machine ──────────────────────────────────────────────

def test_no_alert_before_threshold(monitor):
    """All-stale for less than BLIND_AFTER_S must stay silent."""
    mon, sent = monitor
    for dt in (0, 60, 120, 240, 299):
        mon.check_ws_blind(all_stale=True, now=T0 + dt)
    assert sent == []


def test_alert_once_after_threshold(monitor):
    """First alert fires once the blind duration exceeds BLIND_AFTER_S,
    and continued blindness within the cooldown does NOT re-alert."""
    mon, sent = monitor
    for dt in range(0, 1800, 60):  # 30 min of continuous blindness
        mon.check_ws_blind(all_stale=True, now=T0 + dt)
    assert len(sent) == 1
    msg = sent[0]
    assert "[BLIND]" in msg
    assert "entries effectively paused" in msg
    assert "exchange SL still armed" in msg
    # Blind-since time must be the 12-hour PT rendering of T0 (5:34 AM PT)
    expected = datetime.fromtimestamp(T0, tz=PT).strftime("%-I:%M %p")
    assert expected in msg and "PT" in msg
    assert "AM" in msg or "PM" in msg


def test_realert_after_cooldown(monitor):
    """Still blind after the 60-min cooldown → exactly one more alert."""
    mon, sent = monitor
    end = int(mon.BLIND_AFTER_S + mon.REALERT_COOLDOWN_S + 180)
    for dt in range(0, end, 60):
        mon.check_ws_blind(all_stale=True, now=T0 + dt)
    assert len(sent) == 2
    assert all("[BLIND]" in m for m in sent)


def test_recovery_message_once(monitor):
    """After an alert, the first fresh cycle sends one [BLIND-CLEARED];
    later fresh cycles stay silent and state is fully reset."""
    mon, sent = monitor
    for dt in range(0, 420, 60):
        mon.check_ws_blind(all_stale=True, now=T0 + dt)
    assert len(sent) == 1  # the [BLIND] alert
    mon.check_ws_blind(all_stale=False, now=T0 + 480)
    assert len(sent) == 2
    assert "[BLIND-CLEARED]" in sent[1]
    mon.check_ws_blind(all_stale=False, now=T0 + 540)
    mon.check_ws_blind(all_stale=False, now=T0 + 600)
    assert len(sent) == 2
    assert mon.blind_since is None
    assert mon.blind_alerted is False


def test_short_blip_no_messages(monitor):
    """Stale for under the threshold then fresh → nothing at all
    (no alert, and no recovery message for an episode never alerted)."""
    mon, sent = monitor
    mon.check_ws_blind(all_stale=True, now=T0)
    mon.check_ws_blind(all_stale=True, now=T0 + 120)
    mon.check_ws_blind(all_stale=False, now=T0 + 180)
    assert sent == []
    assert mon.blind_since is None


def test_flapping_respects_cooldown(monitor):
    """A second blind episode inside the cooldown window must not re-alert
    (today's failure mode was two episodes hours apart — those DO both alert,
    but a flapping link within an hour sends at most one [BLIND])."""
    mon, sent = monitor
    # Episode 1: blind 6+ min → alert, then recover
    for dt in range(0, 420, 60):
        mon.check_ws_blind(all_stale=True, now=T0 + dt)
    mon.check_ws_blind(all_stale=False, now=T0 + 480)
    assert len(sent) == 2  # [BLIND] + [BLIND-CLEARED]
    # Episode 2 starts 2 min later, blind another 6+ min — inside 60-min cooldown
    for dt in range(600, 1080, 60):
        mon.check_ws_blind(all_stale=True, now=T0 + dt)
    assert len(sent) == 2  # no third message
    # Episodes an hour apart alert again
    later = T0 + mon.REALERT_COOLDOWN_S + 700
    for dt in range(0, 420, 60):
        mon.check_ws_blind(all_stale=True, now=later + dt)
    assert len(sent) == 3
    assert "[BLIND]" in sent[2]


def test_notify_failure_is_swallowed():
    """A raising notify callable must never propagate into the cycle."""
    def boom(_msg):
        raise RuntimeError("telegram down")
    mon = BlindMonitor(notify=boom)
    for dt in range(0, 420, 60):
        mon.check_ws_blind(all_stale=True, now=T0 + dt)  # must not raise
    assert mon.blind_alerted is True


# ── cycle-stall recovery notice ─────────────────────────────────────────

def test_cycle_gap_normal_silence(monitor):
    """First-ever cycle and normal 60-180s gaps send nothing."""
    mon, sent = monitor
    assert mon.check_cycle_gap(T0) is False           # first call: no baseline
    assert mon.check_cycle_gap(T0 + 60) is False
    assert mon.check_cycle_gap(T0 + 240) is False     # 180s gap — watchdog-normal
    assert sent == []


def test_cycle_gap_notice_fires(monitor):
    """A 59-min gap (today's real 6:29→7:28 AM stall) → one retroactive notice
    with the gap length and both endpoints in 12-hour PT."""
    mon, sent = monitor
    start = datetime(2026, 7, 6, 6, 29, 31, tzinfo=PT).timestamp()
    end = datetime(2026, 7, 6, 7, 28, 11, tzinfo=PT).timestamp()
    mon.check_cycle_gap(start)
    assert mon.check_cycle_gap(end) is True
    assert len(sent) == 1
    msg = sent[0]
    assert "[BLIND-RECOVERED]" in msg
    assert "59 min" in msg
    assert "6:29 AM" in msg and "7:28 AM" in msg and "PT" in msg
    assert "now resumed" in msg


def test_cycle_gap_resets_baseline(monitor):
    """After a stall notice, the next normal gap is quiet again."""
    mon, sent = monitor
    mon.check_cycle_gap(T0)
    mon.check_cycle_gap(T0 + 3600)      # 60-min stall → notice
    mon.check_cycle_gap(T0 + 3660)      # normal 60s gap → silent
    assert len(sent) == 1


def test_cycle_gap_cross_midnight_includes_date(monitor):
    """A gap spanning a PT date boundary renders dates, not bare times."""
    mon, sent = monitor
    before = datetime(2026, 7, 5, 23, 50, 0, tzinfo=PT).timestamp()
    after = datetime(2026, 7, 6, 0, 40, 0, tzinfo=PT).timestamp()
    mon.check_cycle_gap(before)
    mon.check_cycle_gap(after)
    assert len(sent) == 1
    assert "Jul 5" in sent[0] and "Jul 6" in sent[0]


# ── overwatch bot.log freshness check ───────────────────────────────────

class _FakeProc:
    def __init__(self, stdout):
        self.stdout = stdout


@pytest.fixture
def ow(tmp_path, monkeypatch):
    import overwatch
    log = tmp_path / "bot.log"
    log.write_text("2026-07-06 05:34:00 [INFO] Cycle #1 | Positions: 0\n")
    monkeypatch.setattr(overwatch, "LOG_FILE", str(log))
    return overwatch, log


def test_overwatch_fresh_log_ok(ow, monkeypatch):
    overwatch, log = ow
    os.utime(log, (time.time(), time.time() - 60))  # written 1 min ago
    monkeypatch.setattr(overwatch.subprocess, "run",
                        lambda *a, **k: pytest.fail("must not check process when log is fresh"))
    res = overwatch.check_bot_log_freshness()
    assert res.severity == "OK"


def test_overwatch_stale_log_process_alive_critical(ow, monkeypatch):
    overwatch, log = ow
    stale = time.time() - 25 * 60  # 25 min silent
    os.utime(log, (stale, stale))
    monkeypatch.setattr(overwatch.subprocess, "run",
                        lambda *a, **k: _FakeProc("jonas 12345  0.0  Python main.py"))
    res = overwatch.check_bot_log_freshness()
    assert res.severity == "CRITICAL"
    assert "25 min" in res.message
    assert "PT" in res.message
    assert "12345" in res.diagnostics


def test_overwatch_stale_log_no_process_defers(ow, monkeypatch):
    """Dead bot is process_alive's job (it auto-restarts) — freshness stays OK."""
    overwatch, log = ow
    stale = time.time() - 25 * 60
    os.utime(log, (stale, stale))
    monkeypatch.setattr(overwatch.subprocess, "run", lambda *a, **k: _FakeProc(""))
    res = overwatch.check_bot_log_freshness()
    assert res.severity == "OK"
    assert "process_alive" in res.message


def test_overwatch_missing_log_warns(ow, monkeypatch):
    overwatch, log = ow
    monkeypatch.setattr(overwatch, "LOG_FILE", str(log) + ".nope")
    res = overwatch.check_bot_log_freshness()
    assert res.severity == "WARNING"


def test_overwatch_check_registered():
    """check_bot_log_freshness must actually run in run_all_checks."""
    import overwatch
    import inspect
    src = inspect.getsource(overwatch.run_all_checks)
    assert "check_bot_log_freshness" in src
