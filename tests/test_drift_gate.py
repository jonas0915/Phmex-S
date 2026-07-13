"""Concurrent-entry drift gate (r1 A.3, OOS-confirmed 2026-07-12).

New htf_l2 entries opened while an existing position is underwater ran 11% WR
on fresh OOS data (n=9, all losers 7/10-7/11); blocking costs ~14% of flow.
Gate: block a new htf_l2_anticipation entry when ANY open main-bot position's
side-signed drift from entry is negative. Fail-open on missing/stale prices.
"""
import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import _underwater_positions, _tape_gate_blocks_buy_ratio


def _pos(entry, side="long"):
    return SimpleNamespace(entry_price=entry, side=side)


def _lookup(prices, age=1.0):
    """prices: {sym: last} -> price_lookup(sym) = (last, age) or None."""
    def fn(sym):
        if sym not in prices or prices[sym] is None:
            return None
        return prices[sym], age
    return fn


class TestUnderwaterPositions:
    def test_long_underwater_listed(self):
        out = _underwater_positions({"XRP": _pos(1.00, "long")}, _lookup({"XRP": 0.99}))
        assert len(out) == 1
        sym, drift = out[0]
        assert sym == "XRP"
        assert drift < 0

    def test_long_green_not_listed(self):
        out = _underwater_positions({"XRP": _pos(1.00, "long")}, _lookup({"XRP": 1.01}))
        assert out == []

    def test_short_underwater_listed(self):
        # short loses when price rises above entry
        out = _underwater_positions({"ETH": _pos(1800.0, "short")}, _lookup({"ETH": 1815.0}))
        assert len(out) == 1
        assert out[0][1] < 0

    def test_short_green_not_listed(self):
        out = _underwater_positions({"ETH": _pos(1800.0, "short")}, _lookup({"ETH": 1780.0}))
        assert out == []

    def test_flat_position_not_listed(self):
        out = _underwater_positions({"XRP": _pos(1.00, "long")}, _lookup({"XRP": 1.00}))
        assert out == []

    def test_missing_price_fails_open(self):
        out = _underwater_positions({"XRP": _pos(1.00, "long")}, _lookup({}))
        assert out == []

    def test_stale_price_fails_open(self):
        out = _underwater_positions(
            {"XRP": _pos(1.00, "long")}, _lookup({"XRP": 0.90}, age=300.0))
        assert out == []

    def test_zero_entry_price_skipped(self):
        out = _underwater_positions({"XRP": _pos(0.0, "long")}, _lookup({"XRP": 1.0}))
        assert out == []

    def test_mixed_book_reports_only_underwater(self):
        positions = {
            "XRP": _pos(1.00, "long"),    # green
            "DOGE": _pos(0.080, "long"),  # underwater
        }
        out = _underwater_positions(positions, _lookup({"XRP": 1.02, "DOGE": 0.079}))
        assert [s for s, _ in out] == ["DOGE"]

    def test_lookup_exception_fails_open(self):
        def boom(sym):
            raise RuntimeError("ws down")
        out = _underwater_positions({"XRP": _pos(1.00, "long")}, boom)
        assert out == []


class TestMrTapeBuyRatioExemption:
    """bb_mean_reversion SHORTS are exempt from the buy_ratio block — fading a
    buying frenzy IS the MR short thesis.

    Replay receipts (2026-07-12, 25 blocked signals through validated sim):
    buy_ratio-blocked shorts n=10 +$6.19, CI [+0.11, +1.08] excludes zero;
    blocked LONGS lost −$1.13 and divergence blocks were correct — so the
    exemption is shorts-only, buy_ratio-only.
    """

    def test_mr_short_high_buy_ratio_exempt(self):
        assert _tape_gate_blocks_buy_ratio("bb_mean_reversion", "short", 0.90) is False

    def test_mr_long_low_buy_ratio_still_blocked(self):
        # blocked-long replay cohort was net negative — longs keep the gate
        assert _tape_gate_blocks_buy_ratio("bb_mean_reversion", "long", 0.10) is True

    def test_other_strategy_long_blocked_below_045(self):
        assert _tape_gate_blocks_buy_ratio("htf_l2_anticipation", "long", 0.44) is True

    def test_other_strategy_short_blocked_above_055(self):
        assert _tape_gate_blocks_buy_ratio("htf_l2_anticipation", "short", 0.56) is True

    def test_other_strategy_neutral_ratio_passes(self):
        assert _tape_gate_blocks_buy_ratio("htf_l2_anticipation", "long", 0.50) is False
        assert _tape_gate_blocks_buy_ratio("htf_l2_anticipation", "short", 0.50) is False

    def test_boundary_values_pass(self):
        # checks are strict < 0.45 / > 0.55 — boundaries pass
        assert _tape_gate_blocks_buy_ratio("htf_l2_anticipation", "long", 0.45) is False
        assert _tape_gate_blocks_buy_ratio("htf_l2_anticipation", "short", 0.55) is False
