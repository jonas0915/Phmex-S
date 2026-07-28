import sys
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import pandas as pd
import pytest
import sr_bounce as sb


def _mk(rows, start_ts=0, step_ms=3_600_000):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["ts"] = [start_ts + i * step_ms for i in range(len(df))]
    df["volume"] = 100.0
    return df[["ts", "open", "high", "low", "close", "volume"]]


def _flat_1h(n=150):
    """Scan's proven fixture: triangle wave 99-101, zero-width zones at
    98.5 (support) / 101.5 (resistance), low ADX by construction."""
    rows = []
    for i in range(n):
        ph = i % 10
        px = 101 - 0.4 * ph if ph < 5 else 99 + 0.4 * (ph - 5)
        rows.append((px + 0.2, px + 0.5, px - 0.5, px))
    return _mk(rows)


def _5m(rows):
    return _mk(rows, start_ts=120 * 3_600_000, step_ms=300_000)


def test_ported_math_matches_scan():
    df1h = _flat_1h()
    zones = sb.validated_zones(df1h)
    assert any(z["side"] == "support" and abs(z["lo"] - 98.5) < 1e-9 for z in zones)
    assert any(z["side"] == "resistance" and abs(z["hi"] - 101.5) < 1e-9 for z in zones)


def test_evaluate_fires_long_on_confirmed_rejection():
    df1h = _flat_1h()
    # last CLOSED candle (iloc[-2]) is the rejection; iloc[-1] is forming
    fivem = _5m([(100.6, 100.7, 100.5, 100.6),
                 (100.5, 100.6, 98.3, 98.6),     # pierce 98.5, close back above
                 (98.6, 98.7, 98.5, 98.65)])     # forming candle — ignored
    r = sb.evaluate(fivem, None, df1h)
    assert r["signal"] == "buy"
    assert r["sl_price"] < 98.5 < r["tp_price"]
    assert r["strength"] == 0.82


def test_evaluate_holds_without_rejection():
    df1h = _flat_1h()
    fivem = _5m([(100.6, 100.7, 100.5, 100.6),
                 (100.5, 100.6, 100.4, 100.5),
                 (100.5, 100.6, 100.4, 100.45)])
    assert sb.evaluate(fivem, None, df1h)["signal"] == "hold"


def test_evaluate_holds_on_trending_adx(monkeypatch):
    df1h = _flat_1h()
    monkeypatch.setattr(sb, "adx", lambda df, n=14: pd.Series([35.0] * len(df)))
    fivem = _5m([(100.5, 100.6, 98.3, 98.6), (98.6, 98.7, 98.5, 98.65),
                 (98.6, 98.7, 98.5, 98.6)])
    r = sb.evaluate(fivem, None, df1h)
    assert r["signal"] == "hold" and "ADX" in r["reason"]


def test_evaluate_holds_without_htf():
    fivem = _5m([(1, 1, 1, 1)] * 3)
    assert sb.evaluate(fivem, None, None)["signal"] == "hold"


def test_tradesignal_backward_compatible():
    from strategies import TradeSignal, Signal
    s = TradeSignal(Signal.HOLD, "x", 0.0)          # old positional form
    assert s.sl_price is None and s.tp_price is None


def test_strategies_registers_sr_bounce():
    from strategies import STRATEGIES, Signal
    fn = STRATEGIES["sr_bounce"]
    df1h = _flat_1h()
    fivem = _5m([(100.6, 100.7, 100.5, 100.6),
                 (100.5, 100.6, 98.3, 98.6),
                 (98.6, 98.7, 98.5, 98.65)])
    sig = fn(fivem, None, htf_df=df1h)
    assert sig.signal == Signal.BUY
    assert sig.sl_price is not None and sig.tp_price is not None


def _bot_shaped_1h(n=150):
    """Same triangle-wave fixture as _flat_1h, but shaped exactly like what
    exchange.get_ohlcv() actually returns: a DatetimeIndex AS THE INDEX
    (timestamp set_index'd), no separate ts column — NOT the scan's plain
    RangeIndex frames _mk()/_flat_1h() build. This is the frame
    _fetch_sr_bounce_htf() starts from before its .reset_index(drop=True)."""
    rows = []
    for i in range(n):
        ph = i % 10
        px = 101 - 0.4 * ph if ph < 5 else 99 + 0.4 * (ph - 5)
        rows.append((px + 0.2, px + 0.5, px - 0.5, px))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["volume"] = 100.0
    df.index = pd.to_datetime([i * 3_600_000 for i in range(n)], unit="ms")
    df.index.name = "timestamp"
    return df


def test_dedicated_context_reset_index_enables_signal():
    """2026-07-28 review fix, CRITICAL 1b: sr_bounce's ported count_touches()
    does `i - last` while iterating df.iterrows() — arithmetic that assumes a
    plain RangeIndex (how the original scan built its frames). Handed the
    real DatetimeIndex frame exchange.get_ohlcv() returns, it raises
    TypeError, which the OLD generic slot-loop dispatch silently swallowed as
    a signature mismatch (re-dispatching with htf_df=None -> permanent HOLD).

    This proves both halves: (1) the bot-shaped DatetimeIndex frame breaks
    count_touches exactly as diagnosed, and (2) the fix — reset_index(drop=True),
    exactly what _fetch_sr_bounce_htf() now does before handing the frame to
    the strategy — clears it and lets a real signal fire end-to-end through
    the actual STRATEGIES entry point."""
    df1h_bot_shaped = _bot_shaped_1h()

    with pytest.raises(TypeError):
        sb.count_touches(df1h_bot_shaped, 98.4, 98.6)

    df1h_fixed = df1h_bot_shaped.reset_index(drop=True)  # the fix
    assert len(df1h_fixed) >= 100  # also clears sr_bounce's own len < 100 floor

    from strategies import STRATEGIES, Signal
    fivem = _5m([(100.6, 100.7, 100.5, 100.6),
                 (100.5, 100.6, 98.3, 98.6),
                 (98.6, 98.7, 98.5, 98.65)])
    sig = STRATEGIES["sr_bounce"](fivem, None, htf_df=df1h_fixed)
    assert sig.signal in (Signal.BUY, Signal.SELL)
    assert sig.sl_price is not None and sig.tp_price is not None
