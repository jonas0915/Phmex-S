import pandas as pd
from engine import replay


def _mk(rows, start_ts, step_ms):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["ts"] = [start_ts + i * step_ms for i in range(len(df))]
    df["volume"] = 100.0
    return df[["ts", "open", "high", "low", "close", "volume"]]


def _flat_1h(n=150, lo=99.0, hi=101.0):
    """Ranging 1h series bouncing between ~99 and ~101 (low ADX by construction),
    with clean swing lows at 99 every 10 candles → validated support zone."""
    rows = []
    for i in range(n):
        ph = i % 10
        if ph < 5:
            px = 101 - 0.4 * ph
        else:
            px = 99 + 0.4 * (ph - 5)
        rows.append((px + 0.2, px + 0.5, px - 0.5, px))
    return _mk(rows, start_ts=0, step_ms=3_600_000)


# NOTE on the numeric fixtures below: with _flat_1h(), find_pivots on the "low"
# column locks the support pivot at exactly 98.5 (px=99, low=px-0.5) and the
# resistance pivot at exactly 101.5 (px=101, high=px+0.5) -- validated_zones()
# collapses each into a zero-width zone {"lo": 98.5, "hi": 98.5} /
# {"lo": 101.5, "hi": 101.5} (confirmed by direct inspection, not the "~99"
# eyeballed in an earlier draft of this fixture). confirmed_rejection() needs
# candle low <= 98.5 to actually enter that zone. plan_trade()'s room check
# (reward-to-nearest-opposing-zone >= risk) also requires the close-back entry
# to land close to the zone rather than drifting back up near resistance --
# entry=98.6 (barely above the zone) keeps risk small versus the 2.9-wide gap
# to the 101.5 resistance zone. Values below are taken from the actual
# replay() output (verified, not hand-derived): entry=98.6, sl~=98.4232,
# tp~=99.1304 for the two-candle-history case (tests 1); with only the signal
# candle as history (test 3) atr5 differs, giving sl=98.35, tp=99.35.


def test_replay_produces_win_on_scripted_bounce():
    df1h = _flat_1h()
    ts0 = 120 * 3_600_000          # 5m stream starts after 120 closed 1h candles
    m = 300_000
    fivem = [
        (100.0, 100.1, 99.9, 100.0),    # idle, does not touch either zone
        (98.8, 98.9, 98.3, 98.6),       # pierces support zone (hi=98.5) and closes back → signal, limit 98.6
        (98.6, 98.65, 98.55, 98.58),    # low 98.55 < 98.6 → FILL (no sl/tp touch this candle)
        (98.58, 99.5, 98.5, 99.4),      # high 99.5 >= tp(~99.13), low 98.5 > sl(~98.42) → take_profit
    ]
    trades = replay(df1h, _mk(fivem, ts0, m), "TEST")
    assert len(trades) == 1
    t = trades[0]
    assert t["side"] == "long" and t["exit_reason"] == "take_profit"
    assert t["net_usd"] > 0


def test_replay_no_fill_drops_signal():
    df1h = _flat_1h()
    ts0 = 120 * 3_600_000
    m = 300_000
    fivem = [
        (98.8, 98.9, 98.3, 98.6),       # signal, limit 98.6
        (98.6, 99.0, 98.65, 98.9),      # low 98.65 never trades below 98.6 → no fill
        (98.9, 99.2, 98.85, 99.1),
    ]
    assert replay(df1h, _mk(fivem, ts0, m), "TEST") == []


def test_replay_same_candle_sl_and_tp_counts_stop():
    df1h = _flat_1h()
    ts0 = 120 * 3_600_000
    m = 300_000
    fivem = [
        (98.8, 98.9, 98.3, 98.6),       # signal, limit 98.6
        (98.6, 98.65, 98.55, 98.58),    # low 98.55 < 98.6 → FILL
        (98.58, 100.0, 98.0, 99.5),     # touches BOTH sl(~98.35) and tp(~99.35) → stop_loss
    ]
    trades = replay(df1h, _mk(fivem, ts0, m), "TEST")
    assert len(trades) == 1 and trades[0]["exit_reason"] == "stop_loss"
    assert trades[0]["net_usd"] < 0
