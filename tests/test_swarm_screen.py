"""screen: catches lookahead, simulates closed-bar trades, finds a planted edge, writes out.json."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.swarm.lib import registrar as rg
from research.swarm.lib import screen as sc


def _frame(n=600, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    o = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, close) * 1.001, "low": np.minimum(o, close) * 0.999,
                         "close": close, "volume": 1.0}, index=idx)


CAUSAL = "import pandas as pd\ndef signals(df):\n    return ((df.close > df.close.shift(1)).astype(int)).where(df.index.hour == 0, 0)\n"
LOOKAHEAD = "import pandas as pd\ndef signals(df):\n    return (df.close.shift(-1) > df.close).astype(int)\n"


def _thesis(sig, tp=100, sl=100, hold=6, uni=("ETH",)):
    return {"id": "t_demo", "lens": "x", "mechanism": "m", "counterparty": "c", "prediction": "p",
            "nearest_dead_rows": [], "signal_py": sig,
            "spec": {"dataset": "mr_edge", "universe": list(uni), "timeframe": "1h", "tp_bps": tp, "sl_bps": sl,
                     "max_hold_bars": hold, "expected_trades_per_week": 3, "doa_line": "train CI95 upper < 0 → dead"}}


def test_causality_check_passes_causal_and_fails_lookahead(tmp_path: Path):
    df = _frame()
    ok = sc.load_signal_fn(_write(tmp_path, "ok.py", CAUSAL))
    sc.causality_check(ok, df)
    bad = sc.load_signal_fn(_write(tmp_path, "bad.py", LOOKAHEAD))
    with pytest.raises(sc.LookaheadError):
        sc.causality_check(bad, df)


def _write(d: Path, name: str, code: str) -> Path:
    p = d / name; p.write_text(code); return p


def test_simulate_enters_next_open_and_sl_wins_ties():
    idx = pd.date_range("2026-01-01", periods=5, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": [100, 100, 100, 100, 100], "high": [100, 100, 103, 100, 100],
                       "low": [100, 100, 97, 100, 100], "close": [100, 100, 100, 100, 100], "volume": 1}, index=idx)
    sig = pd.Series([0, 1, 0, 0, 0], index=idx)
    trades = sc.simulate(df, sig, tp_bps=200, sl_bps=200, max_hold_bars=3, cost_bps=11.5)
    assert len(trades) == 1
    t = trades.iloc[0]
    assert t.entry_ts == idx[2] and t.entry == 100 and t.exit_reason == "SL" and t.gross_bps == pytest.approx(-200)
    assert t.net_bps == pytest.approx(-211.5)


def test_simulate_max_hold_exits_at_close_and_one_position_per_symbol():
    idx = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": [100] * 6, "high": [100.5] * 6, "low": [99.5] * 6, "close": [100, 100, 100, 101, 100, 100], "volume": 1}, index=idx)
    sig = pd.Series([1, 1, 1, 0, 0, 0], index=idx)
    trades = sc.simulate(df, sig, tp_bps=500, sl_bps=500, max_hold_bars=2, cost_bps=0)
    assert len(trades) == 1 and trades.iloc[0].exit_reason == "TIME" and trades.iloc[0].gross_bps == pytest.approx(100)


def test_run_screen_finds_planted_edge_and_writes_out_json(tmp_path: Path, monkeypatch):
    # plant: after a down bar at hour 0, price rises 0.5% over the next 3 bars
    df = _frame(800, seed=5)
    mask = (df.index.hour == 0) & (df.close < df.close.shift(1))
    bump = pd.Series(0.0, index=df.index)
    for ts in df.index[mask]:
        loc = df.index.get_loc(ts)
        bump.iloc[loc + 1: loc + 4] += 0.0017
    factor = np.exp(bump.cumsum())
    for c in ("open", "high", "low", "close"):
        df[c] = df[c] * factor
    sig_code = "import pandas as pd\ndef signals(df):\n    return ((df.close < df.close.shift(1)) & (df.index.hour == 0)).astype(int)\n"
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda symbol, timeframe, era="train", dataset="mr_edge", token=None, root=None: sc.ld.split_era(df, era, token))
    frozen = rg.freeze(_thesis(sig_code, tp=60, sl=60, hold=3), tmp_path, "t")
    out = sc.run_screen(frozen, tmp_path)
    assert out["causality"] == "PASS" and out["n"] > 15 and out["net_bps_mean"] > 0
    saved = json.loads((tmp_path / "screens" / "t_demo" / "out.json").read_text())
    assert saved["ci95"][0] < saved["net_bps_mean"] < saved["ci95"][1] and saved["p_star"] == pytest.approx((60 + 11.5) / 120)
    assert (tmp_path / "screens" / "t_demo" / "trades.csv").exists()


def test_run_screen_refuses_lookahead_signal(tmp_path: Path, monkeypatch):
    df = _frame(300, seed=6)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(LOOKAHEAD), tmp_path, "t")
    with pytest.raises(sc.LookaheadError):
        sc.run_screen(frozen, tmp_path)


def test_run_screen_refuses_holdout_without_token(tmp_path: Path, monkeypatch):
    df = _frame(300, seed=7)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(CAUSAL), tmp_path, "t")
    with pytest.raises(sc.ld.HoldoutError):
        sc.run_screen(frozen, tmp_path, era="holdout")


def test_run_screen_holdout_preserves_train_artifacts_and_writes_era_suffixed_files(tmp_path: Path, monkeypatch):
    """Controller ruling: era != 'train' must write out.<era>.json / trades.<era>.csv and
    must never touch a prior train era's out.json / trades.csv."""
    df = _frame(800, seed=5)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(CAUSAL), tmp_path, "t")
    train_out = sc.run_screen(frozen, tmp_path)
    sdir = tmp_path / "screens" / "t_demo"
    train_json_path = sdir / "out.json"
    train_csv_path = sdir / "trades.csv"
    assert train_out["era"] == "train"
    train_json_before = train_json_path.read_bytes()
    train_csv_before = train_csv_path.read_bytes()

    holdout_out = sc.run_screen(frozen, tmp_path, era="holdout", token=sc.ld.COMMITTEE_TOKEN)

    assert holdout_out["era"] == "holdout"
    # train artifacts must be byte-identical (never overwritten)
    assert train_json_path.read_bytes() == train_json_before
    assert train_csv_path.read_bytes() == train_csv_before
    # era-suffixed holdout artifacts created alongside
    assert (sdir / "out.holdout.json").exists()
    assert (sdir / "trades.holdout.csv").exists()
    saved_holdout = json.loads((sdir / "out.holdout.json").read_text())
    assert saved_holdout["era"] == "holdout"
