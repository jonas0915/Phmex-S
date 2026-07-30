"""TDD tests for the generalized HTF replay engine (written before
htf_engine.py's implementation, per the 2026-07-29 SR_BOUNCE HTF re-scan
build plan). Covers:
  1. the parameterized no-lookahead zone-context filter (was hardcoded to
     3_600_000 / 1h in the frozen scripts/research/sr-bounce-scan/engine.py),
  2. the funding cost formula added for this scan,
  3. the frozen engine's three synthetic fill/exit scenarios, ported to run
     at a non-default zone/entry TF combo (4h zone / 15m entry) to prove the
     generalization didn't change fill/exit behavior.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from htf_engine import funding_cost, replay, zone_context

ZONE_4H_MS = 4 * 3_600_000
ENTRY_15M_MS = 900_000


# ---------------------------------------------------------------------------
# 1. Parameterized no-lookahead filter
# ---------------------------------------------------------------------------

def test_zone_context_respects_parameterized_bar_duration():
    df = pd.DataFrame({"ts": [0, 3_600_000], "open": [1, 1], "high": [1, 1],
                        "low": [1, 1], "close": [1, 1]})
    # With 1h zone bars, both bars have fully closed (ts + 1h <= 7.2M).
    ctx_1h = zone_context(df, current_ts=7_200_000, zone_tf_ms=3_600_000)
    assert len(ctx_1h) == 2
    # With 4h zone bars, neither bar's close (ts + 4h) has happened by 7.2M.
    ctx_4h = zone_context(df, current_ts=7_200_000, zone_tf_ms=ZONE_4H_MS)
    assert len(ctx_4h) == 0
    # Push current_ts out to exactly bar0's 4h close -> bar0 now included,
    # bar1 (closes at 3.6M + 4h) is not yet closed.
    ctx_4h_later = zone_context(df, current_ts=ZONE_4H_MS, zone_tf_ms=ZONE_4H_MS)
    assert len(ctx_4h_later) == 1
    assert int(ctx_4h_later["ts"].iloc[0]) == 0


def test_zone_context_tail_and_min_bars_are_independent_of_duration():
    # 150 zone bars regardless of spacing; tail(500) is a no-op here since
    # there are fewer than 500 candidates -- confirms the cap doesn't
    # silently interact with the duration parameter.
    n = 150
    df = pd.DataFrame({"ts": [i * ZONE_4H_MS for i in range(n)],
                        "open": [1.0] * n, "high": [1.0] * n,
                        "low": [1.0] * n, "close": [1.0] * n})
    ctx = zone_context(df, current_ts=120 * ZONE_4H_MS, zone_tf_ms=ZONE_4H_MS)
    assert len(ctx) == 120  # bars 0..119 have closed by ts=120*ZONE_4H_MS


# ---------------------------------------------------------------------------
# 2. Funding cost math
# ---------------------------------------------------------------------------

def test_funding_cost_24h_hold_50_notional_is_3x_8h_charges():
    # 0.01% of $50 per 8h = $0.005/period; 24h hold = 3 periods = $0.015.
    fc = funding_cost(notional=50.0, hold_seconds=24 * 3600)
    assert abs(fc - 0.015) < 1e-9


def test_funding_cost_scales_linearly_with_hold_time():
    fc_8h = funding_cost(notional=50.0, hold_seconds=8 * 3600)
    fc_16h = funding_cost(notional=50.0, hold_seconds=16 * 3600)
    assert abs(fc_8h - 0.005) < 1e-9
    assert abs(fc_16h - 2 * fc_8h) < 1e-9


def test_funding_cost_zero_hold_is_zero():
    assert funding_cost(notional=50.0, hold_seconds=0.0) == 0.0


def test_funding_cost_is_always_positive_i_e_always_a_cost():
    fc = funding_cost(notional=50.0, hold_seconds=60.0)
    assert fc > 0.0


# ---------------------------------------------------------------------------
# 3. Frozen engine's three synthetic scenarios, ported to 4h zone / 15m entry
# ---------------------------------------------------------------------------
# Numeric fixtures are the SAME price series as
# scripts/research/sr-bounce-scan/tests/test_engine.py -- ATR/pivot math
# operates on price arrays and index windows, not absolute timestamp deltas,
# so the same entry/sl/tp values apply regardless of candle spacing. Only the
# timestamp step sizes change (4h zone bars instead of 1h, 15m entry candles
# instead of 5m), and the entry-stream start point scales with the zone step
# so the same "120 closed zone bars available" precondition holds for any
# zone_tf_ms (index-based, not duration-based).

def _mk(rows, start_ts, step_ms):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["ts"] = [start_ts + i * step_ms for i in range(len(df))]
    df["volume"] = 100.0
    return df[["ts", "open", "high", "low", "close", "volume"]]


def _flat_zone(n=150, step_ms=ZONE_4H_MS):
    rows = []
    for i in range(n):
        ph = i % 10
        if ph < 5:
            px = 101 - 0.4 * ph
        else:
            px = 99 + 0.4 * (ph - 5)
        rows.append((px + 0.2, px + 0.5, px - 0.5, px))
    return _mk(rows, start_ts=0, step_ms=step_ms)


def test_replay_produces_win_on_scripted_bounce_at_4h_15m():
    df_zone = _flat_zone()
    ts0 = 120 * ZONE_4H_MS
    m = ENTRY_15M_MS
    fivem = [
        (100.0, 100.1, 99.9, 100.0),
        (98.8, 98.9, 98.3, 98.6),
        (98.6, 98.65, 98.55, 98.58),
        (98.58, 99.5, 98.5, 99.4),
    ]
    trades = replay(df_zone, _mk(fivem, ts0, m), "TEST", zone_tf_ms=ZONE_4H_MS)
    assert len(trades) == 1
    t = trades[0]
    assert t["side"] == "long" and t["exit_reason"] == "take_profit"
    assert t["net_usd"] > 0
    # Funding was deducted (hold time > 0) and is a positive cost.
    assert t["funding_usd"] > 0
    assert t["hold_s"] > 0


def test_replay_no_fill_drops_signal_at_4h_15m():
    df_zone = _flat_zone()
    ts0 = 120 * ZONE_4H_MS
    m = ENTRY_15M_MS
    fivem = [
        (98.8, 98.9, 98.3, 98.6),
        (98.6, 99.0, 98.65, 98.9),
        (98.9, 99.2, 98.85, 99.1),
    ]
    assert replay(df_zone, _mk(fivem, ts0, m), "TEST", zone_tf_ms=ZONE_4H_MS) == []


def test_replay_same_candle_sl_and_tp_counts_stop_at_4h_15m():
    df_zone = _flat_zone()
    ts0 = 120 * ZONE_4H_MS
    m = ENTRY_15M_MS
    fivem = [
        (98.8, 98.9, 98.3, 98.6),
        (98.6, 98.65, 98.55, 98.58),
        (98.58, 100.0, 98.0, 99.5),
    ]
    trades = replay(df_zone, _mk(fivem, ts0, m), "TEST", zone_tf_ms=ZONE_4H_MS)
    assert len(trades) == 1 and trades[0]["exit_reason"] == "stop_loss"
    assert trades[0]["net_usd"] < 0
