"""Tests for scripts/slot_lab/mr_edge_signal_table.py (Phase C of the MR edge search).

Synthetic data only — no network, no cache, no live bot import. The 5m fixture is a
seeded fat-tailed random walk that ORGANICALLY fires bb_mean_reversion_strategy
(seed 19: two shorts, three longs incl. one deep long RSI(7)<22 for the floor).
Every "expected" set is computed by calling the strategy DIRECTLY so the test does not
depend on hard-coded bar indices.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts", "slot_lab"))

import mr_edge_signal_table as T  # noqa: E402
from indicators import add_all_indicators, adx as _adx  # noqa: E402
from strategies import bb_mean_reversion_strategy, Signal  # noqa: E402

SYM = "TEST/USDT:USDT"
T0 = pd.Timestamp("2026-07-01 00:00:00", tz="UTC")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _synth_5m(seed=19, n=2000, sigma=0.0015, dof=3, vol_sigma=0.9):
    """Seeded fat-tailed random walk with lognormal volume. Seed 19 fires the MR
    strategy organically (verified during fixture design with numpy 2.x)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(T0, periods=n, freq="5min")
    ret = rng.standard_t(dof, n) * sigma
    close = 100 * np.exp(np.cumsum(ret))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.0003, n)))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.0003, n)))
    vol = 100 * rng.lognormal(0, vol_sigma, n)
    df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": vol}, index=idx)
    df.index.name = "timestamp"
    return df


def _direct_signals(df5_raw, apply_floor=True):
    """Ground truth: the strategy called bar-by-bar exactly like the rig, plus the
    live long RSI(7) floor. Returns [(bar_open_ts, side, rsi_fast)]."""
    d = add_all_indicators(df5_raw)
    out = []
    epoch = d.index.view("int64") // 1_000_000_000
    for i in range(T.WARMUP, len(d)):
        ts = bb_mean_reversion_strategy(d.iloc[i - 21:i + 1], orderbook=None)
        if ts.signal == Signal.HOLD or ts.strength < 0.80:
            continue
        side = "long" if ts.signal == Signal.BUY else "short"
        rf = float(d.iloc[i]["rsi_fast"])
        if apply_floor and side == "long" and rf < T.LONG_RSI_MIN:
            continue
        out.append((int(epoch[i]), side, rf))
    return out


def _flat_1m(entry_ts, hours, price):
    """1m frame of `hours` after entry_ts at a constant price (hi=lo=price)."""
    n = int(hours * 60)
    idx = pd.date_range(pd.Timestamp(entry_ts + 60, unit="s", tz="UTC"), periods=n, freq="1min")
    p = np.full(n, float(price))
    df = pd.DataFrame({"open": p, "high": p, "low": p, "close": p, "volume": 1.0}, index=idx)
    df.index.name = "timestamp"
    return df


@pytest.fixture(scope="module")
def df5():
    return _synth_5m()


@pytest.fixture(scope="module")
def direct(df5):
    return _direct_signals(df5)


@pytest.fixture(scope="module")
def regen(df5):
    return T.regen_signals(df5, SYM)


# ---------------------------------------------------------------------------
# cells / sessions
# ---------------------------------------------------------------------------

def test_cell_keys_live_plus_80_grid():
    keys = T.cell_keys()
    assert len(keys) == 81
    assert len(set(keys)) == 81
    assert keys[0] == "live"
    assert "tp1.6_sl1.2_t4h" in keys
    assert T.cell_params("tp2.0_sl0.8_t6h") == {"tp_pct": 2.0, "sl_pct": 0.8, "hold_secs": 6 * 3600}
    assert T.cell_params("live") == {"tp_pct": 1.6, "sl_pct": 1.2, "hold_secs": 4 * 3600}
    assert T.cell_params("tp1.6_sl1.2_t4h") == T.cell_params("live")


def test_session_bucketing_by_pt_hour():
    for h in range(0, 6):
        assert T.session_for_hour(h) == "europe"
    for h in range(6, 14):
        assert T.session_for_hour(h) == "us"
    for h in range(14, 24):
        assert T.session_for_hour(h) == "asia"
    # 2026-07-01 12:00 UTC = 5:00 AM PDT
    ts = int(pd.Timestamp("2026-07-01 12:00:00", tz="UTC").timestamp())
    assert T.hour_pt(ts) == 5
    assert T.session_for_hour(T.hour_pt(ts)) == "europe"
    # DST-aware: 2026-01-15 12:00 UTC = 4:00 AM PST
    ts_w = int(pd.Timestamp("2026-01-15 12:00:00", tz="UTC").timestamp())
    assert T.hour_pt(ts_w) == 4


# ---------------------------------------------------------------------------
# signal regeneration
# ---------------------------------------------------------------------------

def test_fixture_fires_long_and_short(direct):
    sides = {s for _, s, _ in direct}
    assert sides == {"long", "short"}, direct


def test_regen_matches_direct_strategy_with_floor(regen, direct):
    got = {(r["bar_open_ts"], r["side"]) for r in regen}
    exp = {(b, s) for b, s, _ in direct}
    assert got == exp
    for r in regen:
        assert r["ts"] == r["bar_open_ts"] + 300
        assert r["symbol"] == SYM
        assert r["side"] in ("long", "short")
        assert r["entry_px"] > 0
        assert 0 <= r["hour_pt"] <= 23
        assert r["session"] in ("asia", "europe", "us")
        for k in ("rsi", "rsi_fast", "vol_ratio", "bb_width_pct", "adx5m"):
            assert isinstance(r[k], float), k
        assert r["vol_ratio"] > 1.3  # strategy's own volume gate
        assert r["adx5m"] <= 30.0


def test_rsi_floor_blocks_deep_long(df5, regen):
    """A long whose RSI(7) < 22 exists in the raw strategy output (fixture property)
    and must be absent from the regenerated table."""
    pre = _direct_signals(df5, apply_floor=False)
    deep = [(b, s) for b, s, rf in pre if s == "long" and rf < T.LONG_RSI_MIN]
    assert deep, "fixture no longer contains a deep long — regenerate the seed"
    got = {(r["bar_open_ts"], r["side"]) for r in regen}
    for k in deep:
        assert k not in got
    assert all(r["rsi_fast"] >= T.LONG_RSI_MIN for r in regen if r["side"] == "long")
    blocked = {}
    T.regen_signals(df5, SYM, blocked=blocked)
    assert blocked.get("mr_rsi_floor") == len(deep)


def test_rsi_floor_raised_blocks_every_long(df5, monkeypatch, regen):
    monkeypatch.setattr(T, "LONG_RSI_MIN", 100.0)
    rows = T.regen_signals(df5, SYM)
    assert all(r["side"] == "short" for r in rows)
    assert len(rows) == sum(1 for r in regen if r["side"] == "short")


def test_cooldown_flag_marks_same_symbol_overlap(regen):
    """Rows are NOT suppressed by the 4h per-symbol cooldown (so the fidelity gate can
    see every candidate) but carry cooldown_ok=False when inside the previous
    cooldown_ok signal's hold window — the rig's (mean_revert_replay) signal set is
    exactly rows with cooldown_ok=True."""
    last_ok = None
    for r in sorted(regen, key=lambda r: r["ts"]):
        exp = last_ok is None or r["ts"] >= last_ok + T.COOLDOWN_S
        assert r["cooldown_ok"] == exp
        if r["cooldown_ok"]:
            last_ok = r["ts"]
    assert any(not r["cooldown_ok"] for r in regen), "fixture should contain one overlap"


def test_window_filter(df5, regen):
    mid = regen[len(regen) // 2]["ts"]
    rows = T.regen_signals(df5, SYM, start_ts=mid, end_ts=None)
    assert rows and all(r["ts"] >= mid for r in rows)
    rows2 = T.regen_signals(df5, SYM, start_ts=None, end_ts=mid)
    assert rows2 and all(r["ts"] <= mid for r in rows2)
    assert len(rows) + len(rows2) == len(regen) + 1  # `mid` is in both (inclusive)


# ---------------------------------------------------------------------------
# 1h ADX built the live way
# ---------------------------------------------------------------------------

def test_adx1h_live_equals_direct_computation(df5):
    # signal bar in the middle of an hour -> the forming 1h bar has 4 x 5m bars
    bar_open = int(pd.Timestamp("2026-07-05 13:15:00", tz="UTC").timestamp())
    got = T.adx1h_live(df5, bar_open)
    assert got is not None

    # direct: floor-hour groupby (no resample), trailing 100 bars, indicators.adx
    sub = df5[df5.index <= pd.Timestamp(bar_open, unit="s", tz="UTC")]
    hour = sub.index.floor("1h")
    g = sub.groupby(hour)
    h = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(),
                      "low": g["low"].min(), "close": g["close"].last(),
                      "volume": g["volume"].sum()}).tail(100)
    assert len(h) == 100
    # forming bar = the 4 bars 13:00, 13:05, 13:10, 13:15
    assert h.index[-1] == pd.Timestamp("2026-07-05 13:00:00", tz="UTC")
    assert h["close"].iloc[-1] == df5.loc[pd.Timestamp(bar_open, unit="s", tz="UTC"), "close"]
    exp_adx, _, _ = _adx(h["high"], h["low"], h["close"])
    assert got == pytest.approx(float(exp_adx.iloc[-1]), abs=1e-9)

    # the forming bar is INCLUDED: perturbing the signal bar's high changes the value
    df_p = df5.copy()
    df_p.loc[pd.Timestamp(bar_open, unit="s", tz="UTC"), "high"] *= 1.05
    assert T.adx1h_live(df_p, bar_open) != pytest.approx(got, abs=1e-6)
    # and bars AFTER the signal bar are not: perturbing the next bar changes nothing
    df_q = df5.copy()
    df_q.loc[pd.Timestamp(bar_open + 300, unit="s", tz="UTC"), "high"] *= 1.05
    assert T.adx1h_live(df_q, bar_open) == pytest.approx(got, abs=1e-12)


def test_adx1h_none_when_history_short(df5):
    bar_open = int(df5.index[20].timestamp())  # < 30 hourly bars available
    assert T.adx1h_live(df5, bar_open) is None


# ---------------------------------------------------------------------------
# flow_capture join (streamed, per-symbol numpy arrays)
# ---------------------------------------------------------------------------

def _flow_line(ts, sym, br, imb=0.1, tc=40, cvd=0.2, div=None, ltb=-0.1, spread=0.01):
    return json.dumps({"ts": ts, "symbol": sym, "price": 1.0,
                       "ob": {"imbalance": imb, "spread_pct": spread, "illiquid": False},
                       "flow": {"buy_ratio": br, "cvd_slope": cvd, "divergence": div,
                                "large_trade_bias": ltb, "trade_count": tc}})


def test_flow_join_nearest_within_120s(tmp_path):
    base = 1_780_000_000
    p = tmp_path / "flow.jsonl"
    lines = [
        _flow_line(base - 500, SYM, 0.10),
        _flow_line(base - 90, SYM, 0.20, div="bearish", tc=55),
        _flow_line(base - 30, SYM, 0.30, div="bullish"),
        _flow_line(base + 40, SYM, 0.40),          # AFTER ts -> never picked
        _flow_line(base - 10, "OTHER/USDT:USDT", 0.90),
        "not json at all",
        json.dumps({"ts": base - 5, "symbol": SYM, "price": 0}),  # _normalize rejects
    ]
    p.write_text("\n".join(lines) + "\n")
    fx = T.FlowIndex.from_file(str(p), symbols={SYM, "OTHER/USDT:USDT"})

    f = fx.nearest(SYM, base)
    assert f is not None
    assert f["buy_ratio"] == pytest.approx(0.30)
    assert f["dt_s"] == 30
    assert f["divergence"] == "bullish"
    assert set(f) == {"buy_ratio", "imbalance", "trade_count", "cvd_slope", "divergence",
                      "large_trade_bias", "spread_pct", "dt_s"}

    f2 = fx.nearest(SYM, base - 31)   # rows at -500 and -90 qualify; -90 is nearest
    assert f2["buy_ratio"] == pytest.approx(0.20) and f2["dt_s"] == 59
    assert f2["divergence"] == "bearish" and f2["trade_count"] == 55

    assert fx.nearest(SYM, base - 200) is None       # nearest <= is -500 (dt 300 > 120)
    assert fx.nearest(SYM, base - 600) is None       # nothing before
    assert fx.nearest("NOPE/USDT:USDT", base) is None
    assert fx.nearest(SYM, base - 500 + 120)["dt_s"] == 120  # boundary inclusive (-500 row)
    assert fx.nearest(SYM, base - 500 + 121) is None         # one second too stale


def test_scanner_active_window(tmp_path):
    base = 1_780_000_000
    p = tmp_path / "flow.jsonl"
    p.write_text(_flow_line(base, SYM, 0.5) + "\n")
    fx = T.FlowIndex.from_file(str(p))
    assert fx.active(SYM, base + 600) is True
    assert fx.active(SYM, base - 600) is True
    assert fx.active(SYM, base + 601) is False
    assert fx.active(SYM, base - 601) is False
    assert fx.active("NOPE/USDT:USDT", base) is False


def test_flow_index_symbol_and_window_filter(tmp_path):
    base = 1_780_000_000
    p = tmp_path / "flow.jsonl"
    p.write_text("\n".join([_flow_line(base, SYM, 0.5), _flow_line(base + 5000, SYM, 0.6),
                            _flow_line(base, "X/USDT:USDT", 0.7)]) + "\n")
    fx = T.FlowIndex.from_file(str(p), symbols={SYM}, start_ts=base - 10, end_ts=base + 10)
    assert fx.n_rows == 1 and fx.symbols() == [SYM]


# ---------------------------------------------------------------------------
# funding join
# ---------------------------------------------------------------------------

def test_funding_join_last_settled(tmp_path):
    cache = tmp_path
    base = 1_780_000_000
    rows = [{"ts": (base + 8 * 3600 * i) * 1000, "rate": 0.0001 * (i + 1)} for i in range(3)]
    rows = rows[::-1]  # unsorted on disk
    (cache / f"funding_{T.symkey(SYM)}.json").write_text(json.dumps(rows))
    fund = T.load_funding(str(cache), SYM)
    assert fund is not None
    assert T.funding_at(fund, base - 1) == (None, None)
    assert T.funding_at(fund, base) == (pytest.approx(0.0001), base)
    assert T.funding_at(fund, base + 8 * 3600 - 1) == (pytest.approx(0.0001), base)
    assert T.funding_at(fund, base + 8 * 3600) == (pytest.approx(0.0002), base + 8 * 3600)
    assert T.funding_at(fund, base + 10 ** 6) == (pytest.approx(0.0003), base + 16 * 3600)
    assert T.load_funding(str(cache), "NOPE/USDT:USDT") is None


def test_symkey_matches_cache_convention():
    assert T.symkey("1000PEPE/USDT:USDT") == "1000PEPE_USDT_USDT"
    assert T.cache_path("/c", "BTC/USDT:USDT", "5m") == "/c/BTC_USDT_USDT_5m.pkl"


# ---------------------------------------------------------------------------
# outcomes: live cell + grid on the 1m path
# ---------------------------------------------------------------------------

def test_live_cell_extension_when_roi_ge_5pct_at_4h():
    """Long from 100: +0.6% (ROI +6%) held flat past 4h, TP (101.6) tagged at 4h30.
    Live cell extends to 6h (roi >= 5% at the 4h mark) -> take_profit; the grid twin
    tp1.6_sl1.2_t4h has no extension -> time_exit at 100.6."""
    entry_ts = 1_780_000_000
    df1m = _flat_1m(entry_ts, 6, 100.6)
    tp_bar = pd.Timestamp(entry_ts + 4 * 3600 + 30 * 60, unit="s", tz="UTC")
    df1m.loc[tp_bar:, ["open", "high", "low", "close"]] = 101.7
    net, ex = T.outcomes("long", 100.0, entry_ts, df1m)
    assert ex["live"] == "take_profit"
    assert net["live"] == pytest.approx(1.6 / 100 * 150 - 2 * 150 * 0.01 / 100)
    assert ex["tp1.6_sl1.2_t4h"] == "time_exit"
    assert net["tp1.6_sl1.2_t4h"] == pytest.approx(0.6 / 100 * 150 - 2 * 150 * 0.01 / 100)
    assert ex["tp1.6_sl1.2_t6h"] == "take_profit"
    assert set(net) == set(T.cell_keys()) == set(ex)


def test_live_cell_no_extension_below_5pct():
    entry_ts = 1_780_000_000
    df1m = _flat_1m(entry_ts, 6, 100.3)   # ROI +3% < 5% -> no extension
    net, ex = T.outcomes("long", 100.0, entry_ts, df1m)
    assert ex["live"] == "time_exit"
    assert net["live"] == pytest.approx(0.3 / 100 * 150 - 2 * 150 * 0.01 / 100)


def test_live_cell_extension_then_time_exit_at_6h():
    entry_ts = 1_780_000_000
    df1m = _flat_1m(entry_ts, 8, 100.6)   # never reaches TP; extended cell runs to 6h
    net, ex = T.outcomes("long", 100.0, entry_ts, df1m)
    assert ex["live"] == "time_exit_ext"
    assert net["live"] == pytest.approx(0.6 / 100 * 150 - 2 * 150 * 0.01 / 100)


def test_short_stop_loss_is_taker_exit():
    entry_ts = 1_780_000_000
    df1m = _flat_1m(entry_ts, 3, 100.0)
    df1m.iloc[10:, :4] = 101.3   # +1.3% against a short -> SL 1.2%
    net, ex = T.outcomes("short", 100.0, entry_ts, df1m)
    assert ex["live"] == "stop_loss"
    assert net["live"] == pytest.approx(-1.2 / 100 * 150 - 150 * 0.01 / 100 - 150 * 0.06 / 100)
    assert ex["tp1.0_sl2.0_t2h"] == "time_exit"   # wider SL survives, 2h clock


def test_outcomes_no_path_returns_none_cells():
    entry_ts = 1_780_000_000
    df1m = _flat_1m(entry_ts - 10 * 3600, 2, 100.0)  # all before entry
    net, ex = T.outcomes("long", 100.0, entry_ts, df1m)
    assert net["live"] is None and ex["live"] == "no_path"


def test_trail_arm_override_is_8pct():
    import backtest
    assert backtest.TRAIL_ARM_ROI == 8.0
    assert T.MARGIN == 15.0 and T.NOTIONAL == 150.0


# ---------------------------------------------------------------------------
# fidelity gate vs entry_snapshots rows
# ---------------------------------------------------------------------------

def _snap(sig, side=None, ts_off=137, **extra):
    row = {"ts": sig["bar_open_ts"] + ts_off, "symbol": sig["symbol"],
           "direction": side or sig["side"], "slot": "5m_mean_revert",
           "strategy": "bb_mean_reversion", "price": sig["entry_px"]}
    row.update(extra)
    return row


def test_fidelity_gate_passes_on_matching_snapshots(regen):
    snaps = [_snap(regen[0], rsi_fast=regen[0]["rsi_fast"] + 1.0,
                   htf_adx=None, regime={"vol_ratio": regen[0]["vol_ratio"]}),
             _snap(regen[-1], ts_off=299),
             _snap(regen[1], ts_off=-300)]   # previous bar (±1 bar tolerance)
    rep = T.fidelity_gate(snaps, regen, {SYM})
    assert rep["n_checked"] == 3 and rep["n_matched"] == 3
    assert rep["pct"] == pytest.approx(100.0)
    assert rep["passed"] is True and rep["misses"] == []
    tol = rep["tolerance"]
    assert tol["rsi_fast"]["n"] == 1 and tol["rsi_fast"]["max_abs_diff"] == pytest.approx(1.0)
    assert tol["vol_ratio"]["n"] == 1 and tol["vol_ratio"]["max_abs_diff"] == pytest.approx(0.0)
    assert tol["htf_adx"]["n"] == 0


def test_fidelity_gate_fails_on_mismatch(regen):
    flipped = "short" if regen[0]["side"] == "long" else "long"
    snaps = [_snap(regen[0]), _snap(regen[0], side=flipped)] + \
            [_snap(regen[0], ts_off=-601)] * 8   # 2 bars earlier -> miss
    rep = T.fidelity_gate(snaps, regen, {SYM})
    assert rep["n_checked"] == 10 and rep["n_matched"] == 1
    assert rep["passed"] is False
    assert len(rep["misses"]) == 9
    m = rep["misses"][0]
    assert m["symbol"] == SYM and m["direction"] == flipped and "ts" in m


def test_fidelity_gate_ignores_unprocessed_symbols_and_reports_them(regen):
    other = dict(regen[0], symbol="ZZZ/USDT:USDT")
    snaps = [_snap(regen[0]), _snap(other)]
    rep = T.fidelity_gate(snaps, regen, {SYM})
    assert rep["n_checked"] == 1 and rep["n_unchecked"] == 1
    assert rep["passed"] is True


def test_load_snapshots_filters_slot_and_window(tmp_path):
    p = tmp_path / "snap.jsonl"
    rows = [{"ts": 100, "slot": "5m_mean_revert", "symbol": SYM, "direction": "long"},
            {"ts": 200, "slot": "5m_narrow", "symbol": SYM, "direction": "long"},
            {"ts": 300, "slot": "5m_mean_revert", "symbol": SYM, "direction": "short"},
            {"ts": 400, "slot": "5m_mean_revert", "symbol": SYM, "direction": "short"}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\nbroken\n")
    got = T.load_snapshots(str(p), 100, 300)
    assert [r["ts"] for r in got] == [100, 300]


# ---------------------------------------------------------------------------
# per-symbol pipeline + schema
# ---------------------------------------------------------------------------

def _derive_1m(df5):
    """5 x 1m bars per 5m bar: linear open->close, bar hi/lo respected."""
    rows, idx = [], []
    for ts, r in df5.iterrows():
        path = np.linspace(r.open, r.close, 6)
        for k in range(5):
            o, c = path[k], path[k + 1]
            rows.append((o, max(o, c, r.high if k == 2 else 0), min(o, c, r.low if k == 2 else 1e9),
                         c, r.volume / 5))
            idx.append(ts + pd.Timedelta(minutes=k))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                      index=pd.DatetimeIndex(idx, name="timestamp"))
    return df


def test_build_symbol_rows_schema(df5, regen, tmp_path):
    df1m = _derive_1m(df5)
    fx = T.FlowIndex.from_file(str(tmp_path / "missing.jsonl"))  # absent file -> empty index
    rows = T.build_symbol_rows(SYM, df5, df1m, flow=fx, funding=None)
    assert len(rows) == len(regen)
    expected_keys = {"symbol", "ts", "bar_open_ts", "side", "entry_px", "strength", "rsi",
                     "rsi_fast", "vol_ratio", "bb_width_pct", "adx5m", "adx1h", "hour_pt",
                     "session", "cooldown_ok", "flow", "scanner_active", "funding_rate",
                     "funding_ts", "net_by_cell", "exit_by_cell"}
    for r in rows:
        assert set(r) == expected_keys, set(r) ^ expected_keys
        assert r["flow"] is None and r["scanner_active"] is False
        assert r["funding_rate"] is None and r["funding_ts"] is None
        assert set(r["net_by_cell"]) == set(T.cell_keys())
        assert set(r["exit_by_cell"]) == set(T.cell_keys())
        assert r["adx1h"] is None or isinstance(r["adx1h"], float)
    # the JSON must round-trip (no numpy scalars)
    json.dumps({"rows": rows})


def test_meta_schema_and_caveat_verbatim():
    meta = T.build_meta(start_ts=0, end_ts=1, universe=[SYM], fidelity=None, counts={})
    for k in ("window", "universe", "margin", "notional", "maker_fee", "taker_fee",
              "trail_arm", "cells", "generated_at", "prereg_sha", "caveats"):
        assert k in meta, k
    assert meta["prereg_sha"] is None
    assert meta["cells"] == T.cell_keys()
    assert meta["margin"] == 15.0 and meta["notional"] == 150.0 and meta["trail_arm"] == 8.0
    import mean_revert_replay as MR
    assert T.FILL_ALL_CAVEAT in MR.__doc__
    assert T.FILL_ALL_CAVEAT in meta["caveats"]
    json.dumps(meta)


def test_isolation_no_live_module_imports():
    src = open(T.__file__).read()
    for bad in ("import bot", "from bot", "import exchange", "from exchange",
                "import config", "from config", "import risk_manager", "from risk_manager"):
        assert bad not in src, bad


def test_path_cache_prefix_equals_fresh_build(df5):
    """Slicing the 8h path by ts must equal a fresh rig `_build_path` at each hold."""
    import mean_revert_replay as MR
    df1m = _derive_1m(df5)
    entry_ts = int(df5.index[600].timestamp()) + 300
    for side in ("long", "short"):
        pc = T._PathCache(df1m, entry_ts, side)
        for h in (2, 4, 6, 8):
            assert pc.upto(h * 3600) == MR._build_path(df1m, entry_ts, h * 3600, side)


def test_bar_reasons_diagnostic(df5, regen):
    sig = regen[0]
    d = T.bar_reasons(df5, sig["bar_open_ts"] + 137)
    assert set(d) == {"-300", "0", "300"}
    assert d["0"]["signal"] == ("BUY" if sig["side"] == "long" else "SELL")
    assert d["0"]["rsi_fast"] == pytest.approx(sig["rsi_fast"])
    assert d["0"]["vol_ratio"] == pytest.approx(sig["vol_ratio"])
    assert d["-300"]["signal"] == "HOLD"
    # off the end of the frame -> None entries
    d2 = T.bar_reasons(df5, int(df5.index[-1].timestamp()) + 137)
    assert d2["300"] is None and d2["0"] is not None


def test_fidelity_miss_carries_diagnosis_and_merge(regen, df5):
    flipped = "short" if regen[0]["side"] == "long" else "long"
    snaps = [_snap(regen[0], side=flipped), _snap(regen[-1])]
    rep = T.fidelity_gate(snaps, regen, {SYM},
                          diagnose=lambda sn: T.bar_reasons(df5, int(sn["ts"])))
    assert rep["n_matched"] == 1 and len(rep["misses"]) == 1
    assert "diagnosis" in rep["misses"][0] and "0" in rep["misses"][0]["diagnosis"]
    assert rep["misses"][0]["snap_rsi_fast"] is None
    other = T.fidelity_gate([_snap(regen[1], rsi_fast=regen[1]["rsi_fast"])], regen, {SYM})
    merged = T.merge_fidelity([rep, other], n_snapshots=5, n_unchecked=2)
    assert merged["n_checked"] == 3 and merged["n_matched"] == 2
    assert merged["n_snapshots"] == 5 and merged["n_unchecked"] == 2
    assert merged["pct"] == pytest.approx(200 / 3)
    assert merged["passed"] is False
    assert merged["tolerance"]["rsi_fast"]["n"] == 1
    meta = T.build_meta(0, 1, [SYM], merged, {})
    assert "_diffs" not in meta["fidelity"]
    json.dumps(meta)
