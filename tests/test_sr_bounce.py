import sys
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import pandas as pd
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
