"""Partial take-profit scale-out (2026-06-19 loss-asymmetry fix).

Covers RiskManager.partial_close_position: it must close HALF the position,
record a 'partial_tp' closed_trades entry, leave the runner half open under the
existing trail/TP machinery (stop_loss / take_profit / trailing_stop_price /
peak_price untouched), and flag the position scaled_out so it can only fire once.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from risk_manager import Position, RiskManager

SYMBOL = "BTC/USDT:USDT"


def _make_position(**overrides):
    base = dict(
        symbol=SYMBOL, side="long", entry_price=100.0, amount=1.0,
        margin=10.0, stop_loss=98.8, take_profit=101.6,
        trailing_stop_price=100.6, peak_price=100.7,
    )
    base.update(overrides)
    return Position(**base)


def _rm_with(pos):
    rm = RiskManager.__new__(RiskManager)  # no state-file I/O
    rm.positions = {pos.symbol: pos}
    rm.closed_trades = []
    rm.is_paper = False
    rm._log_prefix = ""
    rm._save_state = lambda: None  # stub persistence
    return rm


def test_partial_close_halves_position_and_keeps_runner(monkeypatch):
    # Isolate baseline behaviour: no runner-TP lift (that has its own tests).
    monkeypatch.setattr(Config, "PARTIAL_RUNNER_TP_ROI", 0.0)
    pos = _make_position(amount=1.0, margin=10.0)
    rm = _rm_with(pos)

    result = rm.partial_close_position(SYMBOL, exit_price=100.6, fees_usdt=0.0)

    # Runner half stays open
    assert SYMBOL in rm.positions
    runner = rm.positions[SYMBOL]
    assert abs(runner.amount - 0.5) < 1e-9
    assert abs(runner.margin - 5.0) < 1e-9
    assert runner.scaled_out is True
    # Runner exit levels are untouched — managed by the existing machinery
    assert runner.stop_loss == 98.8
    assert runner.take_profit == 101.6
    assert runner.trailing_stop_price == 100.6
    assert runner.peak_price == 100.7
    # Returns (pnl, pnl_pct) for the closed half
    assert result is not None
    pnl, pnl_pct = result
    # long, entry 100, exit 100.6, half 0.5 -> gross 0.30 USDT on 5 USDT margin = +6%
    assert abs(pnl - 0.30) < 1e-9
    assert abs(pnl_pct - 6.0) < 1e-6


def test_partial_close_records_partial_tp_trade():
    pos = _make_position(amount=1.0, margin=10.0)
    rm = _rm_with(pos)
    rm.partial_close_position(SYMBOL, exit_price=100.6, fees_usdt=0.01)

    assert len(rm.closed_trades) == 1
    t = rm.closed_trades[0]
    assert t["exit_reason"] == "partial_tp"
    assert t["reason"] == "partial_tp"
    assert abs(t["amount"] - 0.5) < 1e-9
    assert abs(t["margin"] - 5.0) < 1e-9
    # live mode: pnl_usdt is GROSS, net_pnl carries the fee deduction
    assert abs(t["pnl_usdt"] - 0.30) < 1e-9
    assert abs(t["net_pnl"] - (0.30 - 0.01)) < 1e-9
    assert "peak_price" in t


def test_runner_tp_lifted_to_configured_roi_long(monkeypatch):
    """With PARTIAL_RUNNER_TP_ROI=25 and 10x leverage, a long runner's take_profit
    is lifted to entry × (1 + 25/100/10) = entry × 1.025."""
    monkeypatch.setattr(Config, "PARTIAL_RUNNER_TP_ROI", 25.0)
    monkeypatch.setattr(Config, "LEVERAGE", 10)
    pos = _make_position(side="long", entry_price=100.0, amount=1.0, margin=10.0,
                         take_profit=101.6)
    rm = _rm_with(pos)
    rm.partial_close_position(SYMBOL, exit_price=101.0, fees_usdt=0.0)
    runner = rm.positions[SYMBOL]
    assert abs(runner.take_profit - 102.5) < 1e-9  # +25% ROI = +2.5% price


def test_runner_tp_lifted_to_configured_roi_short(monkeypatch):
    monkeypatch.setattr(Config, "PARTIAL_RUNNER_TP_ROI", 25.0)
    monkeypatch.setattr(Config, "LEVERAGE", 10)
    pos = _make_position(side="short", entry_price=100.0, amount=1.0, margin=10.0,
                         take_profit=98.4)
    rm = _rm_with(pos)
    rm.partial_close_position(SYMBOL, exit_price=99.0, fees_usdt=0.0)
    runner = rm.positions[SYMBOL]
    assert abs(runner.take_profit - 97.5) < 1e-9  # short +25% ROI = -2.5% price


def test_runner_tp_unchanged_when_flag_zero(monkeypatch):
    monkeypatch.setattr(Config, "PARTIAL_RUNNER_TP_ROI", 0.0)
    monkeypatch.setattr(Config, "LEVERAGE", 10)
    pos = _make_position(side="long", entry_price=100.0, amount=1.0, margin=10.0,
                         take_profit=101.6)
    rm = _rm_with(pos)
    rm.partial_close_position(SYMBOL, exit_price=101.0, fees_usdt=0.0)
    assert rm.positions[SYMBOL].take_profit == 101.6  # untouched


def test_partial_close_short_side():
    pos = _make_position(side="short", entry_price=100.0, amount=1.0, margin=10.0,
                         stop_loss=101.2, take_profit=98.4,
                         trailing_stop_price=99.4, peak_price=99.3)
    rm = _rm_with(pos)
    # short profit: price below entry. exit 99.4 -> gross (100-99.4)*0.5 = 0.30
    pnl, pnl_pct = rm.partial_close_position(SYMBOL, exit_price=99.4, fees_usdt=0.0)
    assert abs(pnl - 0.30) < 1e-9
    assert abs(pnl_pct - 6.0) < 1e-6
    assert rm.positions[SYMBOL].scaled_out is True


def test_partial_close_fires_only_once_via_flag():
    pos = _make_position(amount=1.0, margin=10.0)
    rm = _rm_with(pos)
    rm.partial_close_position(SYMBOL, exit_price=100.6, fees_usdt=0.0)
    assert rm.positions[SYMBOL].scaled_out is True
    # A second call still halves whatever is open, but the bot.py gate checks
    # scaled_out before ever calling this — assert the flag is the guard.
    assert getattr(rm.positions[SYMBOL], "scaled_out", False) is True


def test_partial_close_missing_symbol_returns_none():
    rm = RiskManager.__new__(RiskManager)
    rm.positions = {}
    rm.closed_trades = []
    rm.is_paper = False
    rm._log_prefix = ""
    rm._save_state = lambda: None
    assert rm.partial_close_position("NOPE/USDT:USDT", 100.0) is None


def test_sync_positions_preserves_scaled_out(monkeypatch):
    """Regression (review 2026-06-19): a scaled-out runner restored from disk must
    keep scaled_out=True after sync_positions rebuilds it from the exchange — else
    the partial-TP block re-fires on the runner half."""
    monkeypatch.setattr(Config, "MODE", "live")
    rm = RiskManager.__new__(RiskManager)
    rm.positions = {}
    rm.closed_trades = []
    rm.is_paper = False
    rm._log_prefix = ""
    rm._save_state = lambda: None
    # Disk-restored runner: half size, already scaled out, with an entry_snapshot
    disk = _make_position(amount=0.5, margin=5.0)
    disk.scaled_out = True
    disk.entry_snapshot = {"foo": "bar"}
    disk.take_profit = 102.5  # lifted +25% runner TP
    rm.positions[SYMBOL] = disk
    # Exchange reports the remaining half on restart
    exch = [{"symbol": SYMBOL, "side": "long", "entry_price": 100.0,
             "amount": 0.5, "margin": 5.0}]
    rm.sync_positions(exch, current_cycle=1)
    synced = rm.positions[SYMBOL]
    assert synced.scaled_out is True, "scaled_out must survive restart/sync"
    assert synced.entry_snapshot == {"foo": "bar"}
    # The lifted runner TP must NOT be recomputed back to the entry-time level
    assert abs(synced.take_profit - 102.5) < 1e-9, "lifted runner TP must survive sync"


def test_sync_positions_does_not_lift_tp_for_normal_position(monkeypatch):
    """A non-scaled-out position gets its TP recomputed from config as before —
    the preservation must only apply to scaled-out runners."""
    monkeypatch.setattr(Config, "MODE", "live")
    monkeypatch.setattr(Config, "TAKE_PROFIT_PERCENT", 1.6)
    rm = RiskManager.__new__(RiskManager)
    rm.positions = {}
    rm.closed_trades = []
    rm.is_paper = False
    rm._log_prefix = ""
    rm._save_state = lambda: None
    exch = [{"symbol": SYMBOL, "side": "long", "entry_price": 100.0,
             "amount": 1.0, "margin": 10.0}]
    rm.sync_positions(exch, current_cycle=1)
    # No existing position → standard TP from config (+1.6% price)
    assert abs(rm.positions[SYMBOL].take_profit - 101.6) < 1e-9


def test_paper_mode_nets_fees_into_pnl():
    pos = _make_position(amount=1.0, margin=10.0)
    rm = _rm_with(pos)
    rm.is_paper = True
    pnl, _ = rm.partial_close_position(SYMBOL, exit_price=100.6)  # fees auto-simulated
    # paper: pnl_usdt is net of simulated round-trip fees, so strictly below gross 0.30
    assert pnl < 0.30
    assert rm.closed_trades[0]["pnl_usdt"] == pnl
