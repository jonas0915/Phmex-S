"""Test extended kill switches — daily loss halt, consecutive loss halt, 8% soft DD tier."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_compute_today_net_pnl_sums_only_today():
    from bot import _compute_today_net_pnl
    now = time.time()
    trades = [
        {"closed_at": now, "net_pnl": -1.0, "pnl_usdt": -1.0},
        {"closed_at": now - 86400 * 2, "net_pnl": 5.0, "pnl_usdt": 5.0},
        {"closed_at": now, "net_pnl": -0.5, "pnl_usdt": -0.5},
    ]
    assert _compute_today_net_pnl(trades) == -1.5


def test_daily_loss_halt_triggers_at_3_percent():
    from bot import _should_halt_daily_loss
    balance = 100.0
    assert _should_halt_daily_loss(today_net=-2.0, balance=balance) is False
    assert _should_halt_daily_loss(today_net=-3.0, balance=balance) is True
    assert _should_halt_daily_loss(today_net=-5.0, balance=balance) is True


def test_consecutive_loss_halt_triggers_at_5():
    from bot import _should_halt_consecutive_losses
    assert _should_halt_consecutive_losses(loss_streak=4) is False
    assert _should_halt_consecutive_losses(loss_streak=5) is True
    assert _should_halt_consecutive_losses(loss_streak=10) is True


def test_daily_loss_override_active_only_on_matching_pt_date(tmp_path):
    from bot import _daily_loss_override_active
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    f = tmp_path / ".daily_loss_override"
    # absent -> no override
    assert _daily_loss_override_active(str(f)) is False
    # today's PT date -> override active
    f.write_text(today + "\n")
    assert _daily_loss_override_active(str(f)) is True
    # stale date -> self-expired, no override
    f.write_text("2020-01-01\n")
    assert _daily_loss_override_active(str(f)) is False
    # garbage -> no override
    f.write_text("not-a-date\n")
    assert _daily_loss_override_active(str(f)) is False


def test_pause_sentinel_is_daily_loss_reads_reason(tmp_path):
    from bot import _pause_sentinel_is_daily_loss
    p = tmp_path / ".pause_trading"
    assert _pause_sentinel_is_daily_loss(str(p)) is False  # missing
    p.write_text("1700000000\nDAILY LOSS HALT: today net $-1.75 exceeds -3% of $56.51\n")
    assert _pause_sentinel_is_daily_loss(str(p)) is True
    p.write_text("1700000000\nManual pause via Telegram\n")
    assert _pause_sentinel_is_daily_loss(str(p)) is False
    p.write_text("1700000000\nCONSECUTIVE LOSS HALT: 5 losses in a row — 4h cooldown\n")
    assert _pause_sentinel_is_daily_loss(str(p)) is False


def _today_pt():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


def test_process_sentinels_clears_daily_loss_pause_when_override_active(tmp_path, monkeypatch):
    import bot as botmod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    (tmp_path / ".pause_trading").write_text(
        "1700000000\nDAILY LOSS HALT: today net $-1.75 exceeds -3% of $56.51\n")
    (tmp_path / ".daily_loss_override").write_text(_today_pt() + "\n")
    b = botmod.Phmex2Bot.__new__(botmod.Phmex2Bot)
    b.slots = []
    b._process_sentinels()
    assert b._trading_paused is False
    assert not (tmp_path / ".pause_trading").exists()  # daily-loss sentinel cleared


def test_process_sentinels_keeps_manual_pause_despite_override(tmp_path, monkeypatch):
    import bot as botmod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    (tmp_path / ".pause_trading").write_text("1700000000\nManual pause via Telegram\n")
    (tmp_path / ".daily_loss_override").write_text(_today_pt() + "\n")
    b = botmod.Phmex2Bot.__new__(botmod.Phmex2Bot)
    b.slots = []
    b._process_sentinels()
    assert b._trading_paused is True  # manual pause untouched by daily-loss override
    assert (tmp_path / ".pause_trading").exists()


def test_process_sentinels_keeps_daily_loss_pause_when_override_stale(tmp_path, monkeypatch):
    import bot as botmod
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    (tmp_path / ".pause_trading").write_text(
        "1700000000\nDAILY LOSS HALT: today net $-1.75 exceeds -3% of $56.51\n")
    (tmp_path / ".daily_loss_override").write_text("2020-01-01\n")  # stale date
    b = botmod.Phmex2Bot.__new__(botmod.Phmex2Bot)
    b.slots = []
    b._process_sentinels()
    assert b._trading_paused is True  # stale override does not clear the halt
    assert (tmp_path / ".pause_trading").exists()


def test_soft_dd_tier_at_8_percent_returns_pause_duration():
    from risk_manager import RiskManager
    rm = RiskManager.__new__(RiskManager)
    rm.peak_balance = 100.0
    pause_sec = rm._soft_dd_tier_pause_seconds(current_balance=92.0)
    assert pause_sec == 900
    pause_sec_none = rm._soft_dd_tier_pause_seconds(current_balance=96.0)
    assert pause_sec_none == 0
