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


def test_soft_dd_tier_at_8_percent_returns_pause_duration():
    from risk_manager import RiskManager
    rm = RiskManager.__new__(RiskManager)
    rm.peak_balance = 100.0
    pause_sec = rm._soft_dd_tier_pause_seconds(current_balance=92.0)
    assert pause_sec == 900
    pause_sec_none = rm._soft_dd_tier_pause_seconds(current_balance=96.0)
    assert pause_sec_none == 0
