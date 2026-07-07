"""Paper-slot fee model (2026-07-05 fix, docs/overnight-2026-07-05/r2_fee_research.md).

Old model charged (taker + slippage) x 2 = 0.22% RT on paper trades, but live
entries are ~99% PostOnly maker (0.01%, no slippage possible on a resting order).
New paper model: maker entry leg + (taker + slippage) exit leg = 0.12% RT —
still deliberately conservative vs the ~0.066% measured live RT.

Live trades must be COMPLETELY unaffected: their fees come from the exchange
fill (fees_usdt param), never from this simulation.
"""

import pytest

from config import Config
from risk_manager import RiskManager

SYMBOL = "DOGE/USDT:USDT"


@pytest.fixture(autouse=True)
def pinned_fees(monkeypatch):
    """Pin fee constants so env overrides can't skew the asserted 0.12% RT."""
    monkeypatch.setattr(Config, "MAKER_FEE_PERCENT", 0.01)
    monkeypatch.setattr(Config, "TAKER_FEE_PERCENT", 0.06)
    monkeypatch.setattr(Config, "SLIPPAGE_PERCENT", 0.05)


def _paper_rm(tmp_path):
    rm = RiskManager(state_file=str(tmp_path / "paper_state.json"))
    assert rm.is_paper
    return rm


def _live_rm(tmp_path):
    # Absolute tmp path keeps the test off the real trading_state.json;
    # force is_paper False to exercise the live code path.
    rm = RiskManager(state_file=str(tmp_path / "live_state.json"))
    rm.is_paper = False
    rm._log_prefix = ""
    return rm


def test_paper_close_charges_012_pct_round_trip(tmp_path):
    rm = _paper_rm(tmp_path)
    pos = rm.open_position(SYMBOL, entry_price=0.08, margin=10.0, side="long")
    notional = pos.entry_price * pos.amount
    rm.close_position(SYMBOL, exit_price=0.08, reason="take_profit")  # gross = 0

    trade = rm.closed_trades[-1]
    expected_fees = notional * 0.12 / 100  # maker 0.01 entry + (taker 0.06 + slip 0.05) exit
    assert trade["fees_usdt"] == pytest.approx(expected_fees)
    assert trade["pnl_usdt"] == pytest.approx(-expected_fees)  # paper nets fees into pnl
    assert trade["net_pnl"] == pytest.approx(-expected_fees)
    # Regression guard: the old 0.22% RT model must be gone.
    assert trade["fees_usdt"] < notional * 0.22 / 100


def test_paper_partial_close_charges_012_pct_on_half_notional(tmp_path):
    rm = _paper_rm(tmp_path)
    pos = rm.open_position(SYMBOL, entry_price=0.08, margin=10.0, side="long")
    half_notional = pos.entry_price * (pos.amount / 2)
    rm.partial_close_position(SYMBOL, exit_price=0.08)  # gross = 0

    trade = rm.closed_trades[-1]
    expected_fees = half_notional * 0.12 / 100
    assert trade["reason"] == "partial_tp"
    assert trade["fees_usdt"] == pytest.approx(expected_fees)
    assert trade["pnl_usdt"] == pytest.approx(-expected_fees)


def test_live_close_never_uses_simulated_fees(tmp_path):
    rm = _live_rm(tmp_path)
    rm.open_position(SYMBOL, entry_price=0.08, margin=10.0, side="long")
    # Live close with exchange-reported fee: gross pnl untouched by the sim model.
    rm.close_position(SYMBOL, exit_price=0.081, reason="take_profit", fees_usdt=0.0123)
    trade = rm.closed_trades[-1]
    gross = (0.081 - 0.08) * trade["amount"]
    assert trade["pnl_usdt"] == pytest.approx(gross)  # live keeps GROSS pnl_usdt
    assert trade["fees_usdt"] == pytest.approx(0.0123)  # exchange fee passed through
    assert trade["net_pnl"] == pytest.approx(gross - 0.0123)
    assert "fees_pending" not in trade


def test_live_close_missing_fee_stays_zero_and_pending(tmp_path):
    rm = _live_rm(tmp_path)
    rm.open_position(SYMBOL, entry_price=0.08, margin=10.0, side="long")
    rm.close_position(SYMBOL, exit_price=0.081, reason="take_profit")  # no fee known
    trade = rm.closed_trades[-1]
    gross = (0.081 - 0.08) * trade["amount"]
    assert trade["fees_usdt"] == 0.0  # NOT simulated for live
    assert trade["pnl_usdt"] == pytest.approx(gross)
    assert trade["fees_pending"] is True  # tagged for reconciler backfill
