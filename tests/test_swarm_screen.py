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
# review fix round 1, finding 1: sparse lookahead — fires on only a few % of bars, so a
# last-value-only / small-random-sample causality check almost never lands on it.
SPARSE_LOOKAHEAD = ("import pandas as pd\ndef signals(df):\n"
                     "    return ((df.close.shift(-2) > df.close * 1.002) & (df.index.hour == 0)).astype(int)\n")
BAD_VALUES = "import pandas as pd\ndef signals(df):\n    return pd.Series(2, index=df.index)\n"
NEVER_FIRES = "import pandas as pd\ndef signals(df):\n    return pd.Series(0, index=df.index)\n"


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


def test_causality_check_catches_sparse_lookahead_signal(tmp_path: Path):
    """Review fix round 1, finding 1: a signal that only leaks on a handful of bars must
    still be caught — the fixed check tests every bar where the signal is nonzero, not a
    small random sample compared only at its own index."""
    df = _frame(600)
    bad = sc.load_signal_fn(_write(tmp_path, "sparse_bad.py", SPARSE_LOOKAHEAD))
    with pytest.raises(sc.LookaheadError):
        sc.causality_check(bad, df)


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


def test_simulate_signal_on_exit_bar_can_open_next_trade_at_next_open():
    """Review fix round 1, finding 2: flat at the exit bar's close means a signal on that
    same closed bar must still be tradeable — it opens the next trade at the NEXT open,
    not skipped as a one-bar dead zone."""
    idx = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": [100] * 6, "high": [100.2] * 6, "low": [99.8] * 6, "close": [100] * 6, "volume": 1}, index=idx)
    sig = pd.Series([0, 1, 0, 1, 0, 0], index=idx)  # second signal fires exactly on bar 3, the first trade's exit bar
    trades = sc.simulate(df, sig, tp_bps=1000, sl_bps=1000, max_hold_bars=1, cost_bps=0)
    assert len(trades) == 2
    assert trades.iloc[0].exit_ts == idx[3] and trades.iloc[0].exit_reason == "TIME"
    assert trades.iloc[1].entry_ts == idx[4] and trades.iloc[1].exit_reason == "TIME"


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


def test_run_screen_rejects_signal_values_outside_pm1_0(tmp_path: Path, monkeypatch):
    """Review fix round 1, finding 3: a score-valued signal (e.g. 2) must not silently
    multiply TP/SL distance and gross_bps through astype(int)."""
    df = _frame(300, seed=8)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(BAD_VALUES), tmp_path, "t")
    with pytest.raises(ValueError, match="signal values must be in"):
        sc.run_screen(frozen, tmp_path)


def test_run_screen_refuses_tampered_signal_file(tmp_path: Path, monkeypatch):
    """Review fix round 1, finding 4: overwriting screens/<id>/signal.py after a valid
    freeze must take the verify()-failure branch and refuse to run."""
    df = _frame(300, seed=9)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(CAUSAL), tmp_path, "t")
    (tmp_path / "screens" / "t_demo" / "signal.py").write_text(LOOKAHEAD)
    with pytest.raises(ValueError):
        sc.run_screen(frozen, tmp_path)


def test_run_screen_refuses_tampered_frozen_json(tmp_path: Path, monkeypatch):
    """Review fix round 1, finding 4: editing a thesis field inside frozen.json (without
    recomputing sha256) must fail rg.verify() and refuse to run."""
    df = _frame(300, seed=10)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(CAUSAL), tmp_path, "t")
    d = json.loads(frozen.read_text())
    d["thesis"]["spec"]["expected_trades_per_week"] = 999  # tamper without touching sha256
    frozen.write_text(json.dumps(d, indent=2, sort_keys=True))
    with pytest.raises(ValueError):
        sc.run_screen(frozen, tmp_path)


def test_run_screen_zero_trades_writes_strict_json_null_time_to_verdict(tmp_path: Path, monkeypatch):
    """Review fix round 1, finding 5: n==0 must serialize time_to_verdict_weeks as JSON
    null, not the non-strict-JSON `Infinity` token math.inf would otherwise produce."""
    df = _frame(300, seed=11)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(NEVER_FIRES), tmp_path, "t")
    out = sc.run_screen(frozen, tmp_path)
    assert out["n"] == 0 and out["time_to_verdict_weeks"] is None
    raw_text = (tmp_path / "screens" / "t_demo" / "out.json").read_text()
    assert "Infinity" not in raw_text
    saved = json.loads(raw_text)  # must not raise on strict json.loads
    assert saved["time_to_verdict_weeks"] is None


# ---------------------------------------------------------------------------
# screen-era context for reference symbols (2026-09-20 fix). A cross-asset signal loads
# its second symbol via load_data.load_reference; run_screen must supply the era/token it
# was given so the reference frame lands in the same era as the frame the signal is handed.
# ---------------------------------------------------------------------------

# reference-following signal: +1 on every bar where the REFERENCE symbol's close rose
# (intersected with df's own index, so a truncated prefix can never see future ref bars)
REF_SIGNAL = ("import pandas as pd\nfrom research.swarm.lib import load_data as ld\n"
              "def signals(df):\n"
              "    ref = ld.load_reference('ETH', '1h', dataset='mr_edge')\n"
              "    idx = df.index.intersection(ref.index)\n"
              "    up = (ref['close'] > ref['close'].shift(1)).reindex(idx).fillna(False)\n"
              "    return up.astype(int).reindex(df.index).fillna(0).astype(int)\n")
# the defect as frozen in 2026-09-19-1451/informed_flow_btc_alt_cascade: era hard-coded
HARDCODED_TRAIN_REF_SIGNAL = REF_SIGNAL.replace(
    "ld.load_reference('ETH', '1h', dataset='mr_edge')",
    "ld.load_ohlcv('ETH', '1h', era='train', dataset='mr_edge')")


def _two_symbol_loader(frames: dict):
    """monkeypatch stand-in for load_data.load_ohlcv keyed by symbol; honours era/token
    through the real split_era so holdout gating is exercised, not bypassed."""
    def _load(symbol, timeframe, era="train", dataset="mr_edge", token=None, root=None):
        return sc.ld.split_era(frames[symbol], era, token)
    return _load


def test_run_screen_sets_screen_context_so_load_reference_matches_frame_era(tmp_path: Path, monkeypatch):
    frames = {"ETH": _frame(800, seed=21), "SOL": _frame(800, seed=22)}
    monkeypatch.setattr(sc.ld, "load_ohlcv", _two_symbol_loader(frames))
    frozen = rg.freeze(_thesis(REF_SIGNAL, uni=("SOL",)), tmp_path, "t")
    hs = sc.ld.holdout_start(frames["SOL"].index.min(), frames["SOL"].index.max())

    train_out = sc.run_screen(frozen, tmp_path)
    assert train_out["causality"] == "PASS" and train_out["n"] > 0
    train_trades = pd.read_csv(tmp_path / "screens" / "t_demo" / "trades.csv", parse_dates=["entry_ts"])
    assert (train_trades["entry_ts"] < hs).all()
    assert sc.ld.get_screen_context() == ("train", None, None)  # cleared after the run

    hold_out = sc.run_screen(frozen, tmp_path, era="holdout", token=sc.ld.COMMITTEE_TOKEN)
    assert hold_out["causality"] == "PASS" and hold_out["n"] > 0   # reference series non-empty in holdout
    hold_trades = pd.read_csv(tmp_path / "screens" / "t_demo" / "trades.holdout.csv", parse_dates=["entry_ts"])
    assert (hold_trades["entry_ts"] >= hs).all()
    assert sc.ld.get_screen_context() == ("train", None, None)  # cleared after the run


def test_run_screen_clears_screen_context_when_signal_raises(tmp_path: Path, monkeypatch):
    df = _frame(300, seed=23)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(LOOKAHEAD), tmp_path, "t")
    with pytest.raises(sc.LookaheadError):
        sc.run_screen(frozen, tmp_path, era="holdout", token=sc.ld.COMMITTEE_TOKEN)
    assert sc.ld.get_screen_context() == ("train", None, None)


def test_run_screen_hardcoded_train_reference_is_void_in_holdout_regression(tmp_path: Path, monkeypatch):
    """Documents the 2026-09-19 defect: a signal that loads its reference with era='train'
    hard-coded gets an empty index intersection in a holdout run (n == 0) even though the
    same rule produces trades on train. load_reference is the fix, not a screen change."""
    frames = {"ETH": _frame(800, seed=21), "SOL": _frame(800, seed=22)}
    monkeypatch.setattr(sc.ld, "load_ohlcv", _two_symbol_loader(frames))
    frozen = rg.freeze(_thesis(HARDCODED_TRAIN_REF_SIGNAL, uni=("SOL",)), tmp_path, "t")
    assert sc.run_screen(frozen, tmp_path)["n"] > 0
    assert sc.run_screen(frozen, tmp_path, era="holdout", token=sc.ld.COMMITTEE_TOKEN)["n"] == 0


# reviewer probe (2026-09-20 follow-up): forward shift confined to the REFERENCE series and
# only then intersected on df.index. load_reference returns the full era series, so without
# clipping every prefix rerun sees the same reference rows and the check passes wrongly.
REF_LOOKAHEAD_SIGNAL = REF_SIGNAL.replace("ref['close'] > ref['close'].shift(1)", "ref['close'].shift(-3) > ref['close']")


def test_run_screen_catches_reference_confined_lookahead(tmp_path: Path, monkeypatch):
    frames = {"ETH": _frame(800, seed=21), "SOL": _frame(800, seed=22)}
    monkeypatch.setattr(sc.ld, "load_ohlcv", _two_symbol_loader(frames))
    frozen = rg.freeze(_thesis(REF_LOOKAHEAD_SIGNAL, uni=("SOL",)), tmp_path, "t")
    with pytest.raises(sc.LookaheadError):
        sc.run_screen(frozen, tmp_path)
    assert sc.ld.get_screen_context() == ("train", None, None)


def test_causality_check_clips_reference_to_each_prefix_end(tmp_path: Path, monkeypatch):
    """Direct check: the reference-confined lookahead fails causality_check itself, and the
    causal reference signal still passes (clipping the reference to the prefix end must not
    perturb a signal that only intersects on df.index)."""
    frames = {"ETH": _frame(800, seed=21), "SOL": _frame(800, seed=22)}
    monkeypatch.setattr(sc.ld, "load_ohlcv", _two_symbol_loader(frames))
    df = sc.ld.split_era(frames["SOL"], "train")
    with sc.ld.screen_context("train", None):
        sc.causality_check(sc.load_signal_fn(_write(tmp_path, "ref_ok.py", REF_SIGNAL)), df)
        with pytest.raises(sc.LookaheadError):
            sc.causality_check(sc.load_signal_fn(_write(tmp_path, "ref_bad.py", REF_LOOKAHEAD_SIGNAL)), df)


# ---------------------------------------------------------------------------
# Portfolio admission under spec.max_concurrent (2026-09-21, STANDARDS #17). After the
# per-symbol simulate, trades are admitted in (entry_ts, universe order) and a trade is
# dropped when max_concurrent admitted trades are still open at its entry. A frozen spec
# WITHOUT the key (every file under research/swarm/runs/ before this date) must produce
# byte-identical outputs to before — audits re-run old screens and diff them.
# ---------------------------------------------------------------------------

# signal fires wherever volume > 0; the per-symbol frames decide WHEN (hour 0 or hour 1)
VOLUME_SIGNAL = "import pandas as pd\ndef signals(df):\n    return (df.volume > 0).astype(int)\n"
LEGACY_OUT_KEYS = {"id", "spec_sha256", "era", "n", "net_bps_mean", "ci95", "wr", "p_star", "trades_per_week",
                   "time_to_verdict_weeks", "lot_check", "per_symbol", "train_span", "causality", "signal_sha256"}


def _overlap_frames():
    """A and B fire at hour 1 (enter 02:00), C fires at hour 0 (enter 01:00); hold 6 bars with
    TP/SL far away so every trade is a TIME exit — all three overlap every day."""
    frames = {}
    for sym, hour, seed in (("A", 1, 31), ("B", 1, 32), ("C", 0, 33)):
        df = _frame(600, seed=seed)
        df["volume"] = (df.index.hour == hour).astype(float)
        frames[sym] = df
    return frames


def _legacy_freeze(thesis: dict, run: Path) -> Path:
    """Write a frozen file the way registrar did BEFORE max_concurrent existed (no key)."""
    import hashlib
    (run / "specs").mkdir(parents=True, exist_ok=True); (run / "screens" / thesis["id"]).mkdir(parents=True, exist_ok=True)
    (run / "screens" / thesis["id"] / "signal.py").write_text(thesis["signal_py"])
    sha = hashlib.sha256(rg._canonical(thesis).encode()).hexdigest()
    p = run / "specs" / f"{thesis['id']}.frozen.json"
    p.write_text(json.dumps({"thesis": thesis, "sha256": sha, "frozen_at": "t"}, indent=2, sort_keys=True))
    return p


def _capped_thesis(k):
    th = _thesis(VOLUME_SIGNAL, tp=5000, sl=5000, hold=6, uni=("A", "B", "C"))
    th["spec"]["max_concurrent"] = k
    return th


def test_admit_trades_cap_one_keeps_first_in_time_and_breaks_ties_by_universe_order():
    ts = pd.date_range("2026-01-01", periods=10, freq="1h", tz="UTC")
    trades = pd.DataFrame([
        {"symbol": "A", "entry_ts": ts[2], "exit_ts": ts[5], "net_bps": 1.0},   # ties with B at ts[2]; A first in universe
        {"symbol": "B", "entry_ts": ts[2], "exit_ts": ts[5], "net_bps": 2.0},
        {"symbol": "C", "entry_ts": ts[1], "exit_ts": ts[4], "net_bps": 3.0},   # earliest — admitted first
        {"symbol": "B", "entry_ts": ts[6], "exit_ts": ts[8], "net_bps": 4.0},   # nothing open at ts[6]
        {"symbol": "A", "entry_ts": ts[8], "exit_ts": ts[9], "net_bps": 5.0},   # B still open AT ts[8] (exit_ts == entry_ts) → dropped
    ])
    got = sc.admit_trades(trades, 1, ["A", "B", "C"])
    assert list(got["net_bps"]) == [3.0, 4.0]
    got2 = sc.admit_trades(trades, 2, ["A", "B", "C"])
    assert list(got2["net_bps"]) == [3.0, 1.0, 4.0, 5.0]          # C, then A (tie → universe order), B dropped
    got3 = sc.admit_trades(trades, 3, ["A", "B", "C"])
    assert sorted(got3["net_bps"]) == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_admit_trades_empty_frame_is_a_noop():
    empty = pd.DataFrame(columns=["symbol", "entry_ts", "exit_ts", "net_bps"])
    assert sc.admit_trades(empty, 1, ["A"]).empty


def test_run_screen_cap_one_admits_only_the_first_in_time_trade_per_overlap(tmp_path: Path, monkeypatch):
    frames = _overlap_frames()
    monkeypatch.setattr(sc.ld, "load_ohlcv", _two_symbol_loader(frames))
    frozen = rg.freeze(_capped_thesis(1), tmp_path, "t")
    out = sc.run_screen(frozen, tmp_path)
    trades = pd.read_csv(tmp_path / "screens" / "t_demo" / "trades.csv")
    assert out["portfolio"]["max_concurrent"] == 1
    n0 = out["portfolio"]["n_unconstrained"]
    assert n0 > 0 and n0 == out["portfolio"]["n_admitted"] + out["portfolio"]["n_dropped"]
    assert out["n"] == out["portfolio"]["n_admitted"] == len(trades)
    assert set(trades["symbol"]) == {"C"}                    # C enters at 01:00, before A/B at 02:00
    assert out["per_symbol"] == {"A": 0, "B": 0, "C": len(trades)}
    assert out["net_bps_mean"] == pytest.approx(trades["net_bps"].mean())
    assert out["wr"] == pytest.approx((trades["net_bps"] > 0).mean())
    assert out["trades_per_week"] == pytest.approx(out["n"] / ((pd.Timestamp(out["train_span"][1]) - pd.Timestamp(out["train_span"][0])).total_seconds() / (7 * 86400)))


def test_run_screen_cap_two_breaks_ties_by_universe_order(tmp_path: Path, monkeypatch):
    frames = _overlap_frames()
    monkeypatch.setattr(sc.ld, "load_ohlcv", _two_symbol_loader(frames))
    frozen = rg.freeze(_capped_thesis(2), tmp_path, "t")
    out = sc.run_screen(frozen, tmp_path)
    trades = pd.read_csv(tmp_path / "screens" / "t_demo" / "trades.csv")
    assert set(trades["symbol"]) == {"A", "C"}                # A and B tie at 02:00; A is first in the universe
    assert out["per_symbol"]["B"] == 0 and out["per_symbol"]["A"] > 0 and out["per_symbol"]["C"] > 0
    assert out["portfolio"]["n_dropped"] == out["portfolio"]["n_unconstrained"] - out["n"] > 0


def test_run_screen_cap_three_admits_everything_and_matches_the_unconstrained_run(tmp_path: Path, monkeypatch):
    frames = _overlap_frames()
    monkeypatch.setattr(sc.ld, "load_ohlcv", _two_symbol_loader(frames))
    capped = sc.run_screen(rg.freeze(_capped_thesis(3), tmp_path / "capped", "t"), tmp_path / "capped")
    legacy = sc.run_screen(_legacy_freeze(_thesis(VOLUME_SIGNAL, tp=5000, sl=5000, hold=6, uni=("A", "B", "C")), tmp_path / "legacy"), tmp_path / "legacy")
    assert capped["portfolio"] == {"max_concurrent": 3, "n_unconstrained": legacy["n"], "n_admitted": legacy["n"], "n_dropped": 0}
    for k in ("n", "per_symbol"):
        assert capped[k] == legacy[k], k
    for k in ("net_bps_mean", "wr", "trades_per_week"):       # same trades, chronological order → fp rounding only
        assert capped[k] == pytest.approx(legacy[k]), k
    assert capped["ci95"] == pytest.approx(legacy["ci95"], rel=0.05)   # bootstrap resamples a differently ordered array
    ct = pd.read_csv(tmp_path / "capped" / "screens" / "t_demo" / "trades.csv")
    lt = pd.read_csv(tmp_path / "legacy" / "screens" / "t_demo" / "trades.csv")
    assert len(ct) == len(lt) and sorted(ct["net_bps"]) == sorted(lt["net_bps"])


def test_run_screen_legacy_spec_without_max_concurrent_keeps_todays_out_json_keys(tmp_path: Path, monkeypatch):
    """Old frozen specs (no key) must produce exactly today's out.json key set — no 'portfolio'
    key, no other addition — so audits that re-run old screens still diff clean."""
    frames = _overlap_frames()
    monkeypatch.setattr(sc.ld, "load_ohlcv", _two_symbol_loader(frames))
    th = _thesis(VOLUME_SIGNAL, tp=5000, sl=5000, hold=6, uni=("A", "B", "C"))
    assert "max_concurrent" not in th["spec"]
    out = sc.run_screen(_legacy_freeze(th, tmp_path), tmp_path)
    saved = json.loads((tmp_path / "screens" / "t_demo" / "out.json").read_text())
    assert set(out.keys()) == LEGACY_OUT_KEYS and set(saved.keys()) == LEGACY_OUT_KEYS
    k = out["per_symbol"]["A"]
    assert k > 0 and out["per_symbol"] == {"A": k, "B": k, "C": k} and out["n"] == 3 * k   # nothing dropped
    trades = pd.read_csv(tmp_path / "screens" / "t_demo" / "trades.csv")
    assert list(trades["symbol"]) == ["A"] * k + ["B"] * k + ["C"] * k   # unchanged symbol-grouped order
