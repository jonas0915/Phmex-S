"""Float-safe min-strength gate (_meets_min_strength).

Root cause (2026-07-07): XLM short signals printed "0.80" against
SCALP_MIN_STRENGTH=0.80 eleven times in one day and were all skipped.
The short penalty at bot.py:1491 computes 0.84 - 0.04, which in IEEE-754
is 0.7999999999999999 — displays as 0.80, fails `< 0.80` by float dust.
Additive strength ladders inside strategies (0.72 + 0.04 + ...) can
produce the same dust in either direction, so the gate must compare on
a rounded value, not raw floats.
"""
import pytest

from bot import _meets_min_strength


class TestFloatDustBoundary:
    def test_short_penalty_dust_passes(self):
        # The exact live failure: 0.84 - 0.04 = 0.7999999999999999
        assert (0.84 - 0.04) < 0.80  # prove the dust exists
        assert _meets_min_strength(0.84 - 0.04, 0.80)

    def test_additive_ladder_dust_passes(self):
        # momentum_cont-style accumulation landing on the boundary
        assert _meets_min_strength(0.72 + 0.04 + 0.04, 0.80)
        assert _meets_min_strength(0.72 + 0.03 + 0.03 + 0.02, 0.80)

    def test_exact_boundary_passes(self):
        assert _meets_min_strength(0.80, 0.80)

    def test_dust_above_boundary_passes(self):
        assert _meets_min_strength(0.8000000000000002, 0.80)


class TestGenuineRejections:
    def test_clearly_weak_fails(self):
        assert not _meets_min_strength(0.79, 0.80)

    def test_just_below_after_rounding_fails(self):
        # 0.7999 rounds to 0.7999 at 4dp — still below 0.80
        assert not _meets_min_strength(0.7999, 0.80)

    def test_penalized_weak_signal_fails(self):
        # raw 0.80 short minus 0.04 penalty = 0.76 — genuinely weak
        assert not _meets_min_strength(0.80 - 0.04, 0.80)

    def test_zero_fails(self):
        assert not _meets_min_strength(0.0, 0.80)


class TestOtherThresholds:
    def test_works_at_paper_slot_hardcoded_080(self):
        assert _meets_min_strength(0.84 - 0.04, 0.80)

    def test_respects_lower_minimum(self):
        assert _meets_min_strength(0.75, 0.75)
        assert not _meets_min_strength(0.74, 0.75)
