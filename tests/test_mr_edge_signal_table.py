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
                     "funding_ts", "net_by_cell", "exit_by_cell",
                     "fire_minute", "confirmed_at_close", "partial_vol_ratio"}
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


# ---------------------------------------------------------------------------
# FORMING-BAR mode (prereg amendment v2): partial 5m candle evaluated minute by minute
# ---------------------------------------------------------------------------

def _block_for(df1m, bar_ts):
    return df1m[(df1m.index >= bar_ts) & (df1m.index < bar_ts + pd.Timedelta(minutes=5))]


def _craft_block(df5, bar_ts, closes, vols):
    """5 x 1m bars inside the 5m bar at bar_ts: minute-0 open = the 5m open, each
    later minute opens at the previous close; hi/lo = max/min(open, close)."""
    o = float(df5.loc[bar_ts, "open"])
    rows, idx = [], []
    for k in range(5):
        c = float(closes[k])
        rows.append((o, max(o, c), min(o, c), c, float(vols[k])))
        idx.append(bar_ts + pd.Timedelta(minutes=k))
        o = c
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"],
                        index=pd.DatetimeIndex(idx, name="timestamp"))


def _apply_block(df5, df1m, bar_ts, block):
    """Return (df5', df1m') with the 1m block substituted and the 5m bar re-aggregated
    from it, so m=5 == the closed bar by construction."""
    df1m2 = df1m.copy()
    df1m2.loc[block.index, ["open", "high", "low", "close", "volume"]] = block.values
    df5_2 = df5.copy()
    df5_2.loc[bar_ts, ["open", "high", "low", "close", "volume"]] = [
        block["open"].iloc[0], block["high"].max(), block["low"].min(),
        block["close"].iloc[-1], block["volume"].sum()]
    return df5_2, df1m2


def _fires(df5_raw, i, partial=None):
    """Direct strategy verdict on the live-shaped (lookback) frame at bar i with an
    optional partial candle replacing bar i. Returns side or None."""
    fr = T.forming_frame(df5_raw, i, partial)
    sig = bb_mean_reversion_strategy(fr, orderbook=None)
    if sig.signal == Signal.HOLD or sig.strength < T.MIN_STRENGTH:
        return None
    return "long" if sig.signal == Signal.BUY else "short"


@pytest.fixture(scope="module")
def df1m(df5):
    return _derive_1m(df5)


def test_strategy_frame_matches_add_all_indicators(df5):
    raw = df5.iloc[500:800]
    a = add_all_indicators(raw)
    b = T.strategy_frame(raw)
    assert a.index.equals(b.index)
    for c in ("ema_9", "ema_21", "ema_50", "ema_200", "rsi", "rsi_fast", "bb_upper",
              "bb_mid", "bb_lower", "atr", "adx", "plus_di", "minus_di",
              "open", "high", "low", "close", "volume"):
        assert np.allclose(a[c].to_numpy(), b[c].to_numpy(), rtol=0, atol=1e-12, equal_nan=True), c


def test_partial_candle_m1_to_5_and_m5_equals_closed_bar(df5, df1m):
    bar_ts = df5.index[700]
    blk = _block_for(df1m, bar_ts)
    assert len(blk) == 5
    arr = blk[["open", "high", "low", "close", "volume"]].to_numpy()
    for m in range(1, 6):
        c = T.partial_candle(arr, m)
        assert c["open"] == arr[0, 0]
        assert c["high"] == arr[:m, 1].max() and c["low"] == arr[:m, 2].min()
        assert c["close"] == arr[m - 1, 3]
        assert c["volume"] == pytest.approx(arr[:m, 4].sum())
    c5 = T.partial_candle(arr, 5)
    r = df5.loc[bar_ts]
    for k in ("open", "high", "low", "close", "volume"):
        assert c5[k] == pytest.approx(float(r[k]), rel=1e-12), k
    with pytest.raises(ValueError):
        T.partial_candle(arr, 0)
    with pytest.raises(ValueError):
        T.partial_candle(arr, 6)


def test_forming_frame_shape_is_live_lookback(df5):
    i = 900
    fr = T.forming_frame(df5, i, None)
    # live: 300 raw bars (ws cache cap) -> add_all_indicators drops the NaN head rows
    raw_len = T.LIVE_LOOKBACK
    exp = add_all_indicators(df5.iloc[i - raw_len + 1:i + 1])
    assert len(fr) == len(exp) and fr.index[-1] == df5.index[i]
    assert fr.index.equals(exp.index)
    assert float(fr["ema_200"].iloc[-1]) == pytest.approx(float(exp["ema_200"].iloc[-1]), abs=1e-12)
    # partial replaces the last row
    p = {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 7.0}
    fr2 = T.forming_frame(df5, i, p)
    assert fr2.index[-1] == df5.index[i]
    assert float(fr2["close"].iloc[-1]) == 1.5 and float(fr2["volume"].iloc[-1]) == 7.0


def test_forming_candidates_prune_is_prev_bar_band_penetration(df5):
    mask = T.forming_candidates(df5)
    assert mask.shape == (len(df5),) and mask.dtype == bool
    from indicators import bollinger_bands
    up, _, lo = bollinger_bands(df5["close"])
    prev_c, prev_l, prev_h = df5["close"].shift(1), df5["low"].shift(1), df5["high"].shift(1)
    up_p, lo_p = up.shift(1), lo.shift(1)
    exp = ((prev_c <= lo_p) | (prev_l < lo_p * 0.998) | (prev_c >= up_p) | (prev_h > up_p * 1.002))
    exp = exp.fillna(False).to_numpy()
    assert (mask == exp).all()
    assert 0 < mask.mean() < 0.5


def test_forming_only_evaluates_candidate_bars(df5, df1m, monkeypatch):
    seen = []
    real = T.bb_mean_reversion_strategy

    def spy(df, orderbook=None):
        seen.append(df.index[-1])
        return real(df, orderbook=orderbook)

    monkeypatch.setattr(T, "bb_mean_reversion_strategy", spy)
    stats = {}
    rows = T.regen_signals_forming(df5, df1m, SYM, stats=stats)
    mask = T.forming_candidates(df5)
    cand = set(df5.index[mask])
    assert seen and set(seen) <= cand
    assert stats["candidates"] == int(mask[T.LIVE_LOOKBACK - 1:].sum())
    assert stats["bars"] == len(df5) - (T.LIVE_LOOKBACK - 1)
    assert stats["prune_ratio"] == pytest.approx(stats["candidates"] / stats["bars"])
    assert stats["strategy_calls"] == len(seen)
    assert stats["strategy_calls"] <= 5 * stats["candidates"]
    epoch_c = {int(t.timestamp()) for t in cand}
    assert all(r["bar_open_ts"] in epoch_c for r in rows)


def _mid_bar_fixture(df5, df1m, regen):
    """A closed-mode short bar rebuilt so it is inside the band with full volume at
    minute 2 (fires) but collapses 1.5% by the close (RSI(7) < 70 -> HOLD at close).
    Returns (df5', df1m', bar_open_ts, original close)."""
    for r in [r for r in regen if r["side"] == "short"]:
        bar_ts = pd.Timestamp(r["bar_open_ts"], unit="s", tz="UTC")
        i = df5.index.get_loc(bar_ts)
        if i < T.LIVE_LOOKBACK:
            continue
        oc, V = float(df5.loc[bar_ts, "close"]), float(df5.loc[bar_ts, "volume"])
        blk = _craft_block(df5, bar_ts, [oc, oc, oc * 0.995, oc * 0.99, oc * 0.985], [0, V, 0, 0, 0])
        df5_2, df1m_2 = _apply_block(df5, df1m, bar_ts, blk)
        arr = blk.to_numpy()
        if _fires(df5_2, i, T.partial_candle(arr, 2)) != "short" or _fires(df5_2, i, None) is not None:
            continue  # lookback-frame drift on this candidate; try the next short
        return df5_2, df1m_2, r["bar_open_ts"], oc
    raise AssertionError("no short candidate survived the crafted mid-bar construction")


def test_forming_fires_mid_bar_but_not_at_close(df5, df1m, regen):
    """Forming mode emits fire_minute=2, confirmed_at_close=False; closed mode emits
    nothing for the same bar."""
    df5_2, df1m_2, b, oc = _mid_bar_fixture(df5, df1m, regen)
    closed_rows = T.regen_signals(df5_2, SYM, start_ts=b + 300, end_ts=b + 300)
    assert closed_rows == []
    rows = T.regen_signals_forming(df5_2, df1m_2, SYM, start_ts=b, end_ts=b + 300)
    assert len(rows) == 1
    row = rows[0]
    assert row["bar_open_ts"] == b and row["side"] == "short"
    assert row["fire_minute"] == 2 and row["confirmed_at_close"] is False
    assert row["ts"] == b + 120 and row["entry_px"] == pytest.approx(oc)
    assert row["partial_vol_ratio"] == pytest.approx(row["vol_ratio"])
    assert row["partial_vol_ratio"] > 1.3
    # whole-frame forming run contains that row too (cooldown/other bars untouched)
    allrows = T.regen_signals_forming(df5_2, df1m_2, SYM)
    assert any(r["bar_open_ts"] == b and r["fire_minute"] == 2 and not r["confirmed_at_close"] for r in allrows)


def test_forming_fires_only_at_close(df5, df1m, regen):
    """Volume arrives only in the last minute: minutes 1-4 fail vol_ok, minute 5 is
    the closed bar -> fire_minute=5, confirmed_at_close=True, ts = bar close."""
    done = False
    for r in regen:
        bar_ts = pd.Timestamp(r["bar_open_ts"], unit="s", tz="UTC")
        i = df5.index.get_loc(bar_ts)
        if i < T.LIVE_LOOKBACK or _fires(df5, i, None) != r["side"]:
            continue
        blk = _block_for(df1m, bar_ts).copy()
        V = float(df5.loc[bar_ts, "volume"])
        blk["volume"] = [0.0, 0.0, 0.0, 0.0, V]
        df5_2, df1m_2 = _apply_block(df5, df1m, bar_ts, blk)
        assert df5_2.loc[bar_ts, "close"] == pytest.approx(df5.loc[bar_ts, "close"])
        b = r["bar_open_ts"]
        rows = T.regen_signals_forming(df5_2, df1m_2, SYM, start_ts=b, end_ts=b + 300)
        assert len(rows) == 1
        row = rows[0]
        assert row["fire_minute"] == 5 and row["confirmed_at_close"] is True
        assert row["ts"] == b + 300 and row["side"] == r["side"]
        assert row["entry_px"] == pytest.approx(float(df5.loc[bar_ts, "close"]))
        assert row["vol_ratio"] == pytest.approx(row["partial_vol_ratio"])
        done = True
        break
    assert done


def test_forming_confirmed_flag_equals_direct_close_evaluation(df5, df1m):
    rows = T.regen_signals_forming(df5, df1m, SYM)
    assert rows, "fixture should fire in forming mode"
    for row in rows:
        i = df5.index.get_loc(pd.Timestamp(row["bar_open_ts"], unit="s", tz="UTC"))
        exp = _fires(df5, i, None) == row["side"]
        if row["side"] == "long" and exp:
            fr = T.forming_frame(df5, i, None)
            exp = round(float(fr["rsi_fast"].iloc[-1]), 1) >= T.LONG_RSI_MIN
        assert row["confirmed_at_close"] is exp, row
        assert 1 <= row["fire_minute"] <= 5
        assert row["ts"] == row["bar_open_ts"] + 60 * row["fire_minute"]
        if row["fire_minute"] == 5:
            assert row["confirmed_at_close"] is True
    assert any(r["fire_minute"] < 5 for r in rows), "derived 1m paths should fire early somewhere"


def test_forming_rsi_floor_and_cooldown(df5, df1m, monkeypatch):
    blocked = {}
    rows = T.regen_signals_forming(df5, df1m, SYM, blocked=blocked)
    assert all(round(r["rsi_fast"], 1) >= T.LONG_RSI_MIN for r in rows if r["side"] == "long")
    last_ok = None
    for r in sorted(rows, key=lambda r: r["ts"]):
        exp = last_ok is None or r["ts"] >= last_ok + T.COOLDOWN_S
        assert r["cooldown_ok"] == exp
        if r["cooldown_ok"]:
            last_ok = r["ts"]
    monkeypatch.setattr(T, "LONG_RSI_MIN", 100.0)
    b2 = {}
    rows2 = T.regen_signals_forming(df5, df1m, SYM, blocked=b2)
    assert all(r["side"] == "short" for r in rows2)
    # every long that fired in the base run + every bar the base floor already blocked
    assert b2.get("mr_rsi_floor", 0) == sum(1 for r in rows if r["side"] == "long") + blocked.get("mr_rsi_floor", 0)


def test_forming_early_ending_series(df5, df1m):
    """5m and 1m series that end before the window end: no crash, bars without 1m
    data fall back to the closed-bar evaluation (fire_minute=5)."""
    end_ts = int(df5.index[-1].timestamp()) + 10 * 86400   # window runs past both series
    full = T.regen_signals_forming(df5, df1m, SYM, end_ts=end_ts)
    conf = [r for r in full if r["confirmed_at_close"]]
    assert conf
    r_cut = conf[-1]
    cut_ts = pd.Timestamp(r_cut["bar_open_ts"], unit="s", tz="UTC")
    df1m_short = df1m[df1m.index < cut_ts]                 # 1m data ends BEFORE this bar
    stats = {}
    rows = T.regen_signals_forming(df5, df1m_short, SYM, end_ts=end_ts, stats=stats)
    assert stats["bars_no_1m"] >= 1
    tail = [r for r in rows if r["bar_open_ts"] >= r_cut["bar_open_ts"]]
    assert tail and all(r["fire_minute"] == 5 and r["confirmed_at_close"] is True for r in tail)
    assert (r_cut["bar_open_ts"], r_cut["side"]) in {(r["bar_open_ts"], r["side"]) for r in tail}
    # every closed-bar fire in the 1m-less tail was also a confirmed fire on the full data
    full_conf = {(r["bar_open_ts"], r["side"]) for r in full if r["confirmed_at_close"]}
    assert {(r["bar_open_ts"], r["side"]) for r in tail} <= full_conf
    # build_symbol_rows in forming mode on the truncated 1m frame: outcomes -> no_path
    out = T.build_symbol_rows(SYM, df5, df1m_short, flow=None, funding=None,
                              start_ts=r_cut["bar_open_ts"], end_ts=end_ts, eval_mode="forming")
    assert out and all(r["exit_by_cell"]["live"] == "no_path" for r in out)
    # a 5m series that itself ends early (truncate) with a window past its end: fine too
    df5_short = df5.iloc[:-50]
    rows2 = T.regen_signals_forming(df5_short, df1m, SYM, end_ts=end_ts)
    assert all(r["bar_open_ts"] <= int(df5_short.index[-1].timestamp()) for r in rows2)


def test_closed_rows_carry_forming_fields(regen):
    for r in regen:
        assert r["fire_minute"] == 5 and r["confirmed_at_close"] is True
        assert r["partial_vol_ratio"] == r["vol_ratio"]


def test_build_symbol_rows_forming_schema(df5, df1m):
    rows = T.build_symbol_rows(SYM, df5, df1m, flow=None, funding=None, eval_mode="forming")
    assert rows
    closed = T.build_symbol_rows(SYM, df5, df1m, flow=None, funding=None, eval_mode="closed")
    assert set(rows[0]) == set(closed[0])
    assert {"fire_minute", "confirmed_at_close", "partial_vol_ratio"} <= set(rows[0])
    json.dumps({"rows": rows})
    with pytest.raises(ValueError):
        T.build_symbol_rows(SYM, df5, df1m, eval_mode="bogus")


def test_adx1h_live_partial_row(df5):
    bar_open = int(pd.Timestamp("2026-07-05 13:15:00", tz="UTC").timestamp())
    r = df5.loc[pd.Timestamp(bar_open, unit="s", tz="UTC")]
    same = {k: float(r[k]) for k in ("open", "high", "low", "close", "volume")}
    assert T.adx1h_live(df5, bar_open, partial=same) == pytest.approx(T.adx1h_live(df5, bar_open), abs=1e-12)
    bumped = dict(same, high=same["high"] * 1.05)
    assert T.adx1h_live(df5, bar_open, partial=bumped) != pytest.approx(T.adx1h_live(df5, bar_open), abs=1e-6)


def test_fidelity_gate_reports_fire_minute_for_mid_bar_snapshot(df5, df1m):
    rows = T.regen_signals_forming(df5, df1m, SYM)
    early = [r for r in rows if r["fire_minute"] < 5]
    late = [r for r in rows if r["fire_minute"] == 5]
    assert early and late
    e, l = early[0], late[0]
    snaps = [_snap(e, ts_off=137), _snap(l, ts_off=299)]
    rep = T.fidelity_gate(snaps, rows, {SYM})
    assert rep["n_matched"] == 2
    m0 = rep["matches"][0]
    assert m0["fire_minute"] == e["fire_minute"] and m0["confirmed_at_close"] == e["confirmed_at_close"]
    assert m0["snap_sec_into_bar"] == 137 and m0["snap_minutes_elapsed"] == 2
    assert m0["bar_offset_s"] == 0 and m0["symbol"] == SYM
    assert rep["matches"][1]["snap_minutes_elapsed"] == 4
    assert rep["fire_minute_hist"][e["fire_minute"]] >= 1 and rep["fire_minute_hist"][5] >= 1
    merged = T.merge_fidelity([rep], n_snapshots=2, n_unchecked=0)
    assert len(merged["matches"]) == 2 and merged["fire_minute_hist"] == rep["fire_minute_hist"]
    meta = T.build_meta(0, 1, [SYM], merged, {}, prereg_sha="deadbeef", eval_mode="forming")
    assert meta["prereg_sha"] == "deadbeef" and meta["eval_mode"] == "forming"
    assert meta["fidelity"]["fire_minute_hist"]
    json.dumps(meta)


def test_forming_miss_diagnosis_per_minute(df5, df1m):
    rows = T.regen_signals_forming(df5, df1m, SYM)
    r = rows[0]
    d = T.forming_reasons(df5, df1m, r["bar_open_ts"] + 137)
    assert set(d) == {"-300", "0", "300"}
    assert set(d["0"]) == {"1", "2", "3", "4", "5"}
    m = d["0"][str(r["fire_minute"])]
    assert m["signal"] == ("BUY" if r["side"] == "long" else "SELL")
    assert m["rsi_fast"] == pytest.approx(r["rsi_fast"]) and m["vol_ratio"] == pytest.approx(r["vol_ratio"])
    for k in range(1, r["fire_minute"]):
        assert d["0"][str(k)]["signal"] == "HOLD"
    json.dumps(d)


# ---------------------------------------------------------------------------
# real-money companion read: closed trades x snapshots x regen match
# ---------------------------------------------------------------------------

def test_sha256_file(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("hello\n")
    import hashlib
    assert T.sha256_file(str(p)) == hashlib.sha256(b"hello\n").hexdigest()


def test_bootstrap_mean_ci_deterministic():
    xs = [1.0, -0.5, 2.0, 0.3, -1.2, 0.8]
    lo, hi = T.bootstrap_mean_ci(xs, n_boot=500, seed=0)
    assert lo <= float(np.mean(xs)) <= hi
    assert (lo, hi) == T.bootstrap_mean_ci(xs, n_boot=500, seed=0)
    assert T.bootstrap_mean_ci([], n_boot=10) == (None, None)


def test_real_trade_fidelity_join_and_cohorts(df5, df1m, regen):
    df5_2, df1m_2, b, _ = _mid_bar_fixture(df5, df1m, regen)
    rows = T.regen_signals_forming(df5_2, df1m_2, SYM)
    early = [r for r in rows if r["fire_minute"] < 5 and not r["confirmed_at_close"]]
    late = [r for r in rows if r["confirmed_at_close"] and r["bar_open_ts"] != b]
    assert early and len(late) >= 2
    early = early + early                        # two forming-only trades on the same signal
    snaps, trades = [], []
    for k, r in enumerate(early[:2] + late[:2]):
        sn = _snap(r, ts_off=60 * r["fire_minute"] - 30)
        snaps.append(sn)
        trades.append({"symbol": SYM, "side": r["side"], "opened_at": sn["ts"] + 7.5 + k,
                       "net_pnl": [0.4, -0.3, 0.9, -0.2][k], "exit_reason": "tp", "mode": "live"})
    # a live trade whose snapshot is 200 s away -> no snapshot; a paper trade; an out-of-universe symbol
    trades.append({"symbol": SYM, "side": "short", "opened_at": snaps[0]["ts"] + 200,
                   "net_pnl": 5.0, "exit_reason": "sl", "mode": "live"})
    trades.append(dict(trades[0], mode=None, net_pnl=9.0, opened_at=trades[0]["opened_at"] + 1))
    snaps.append(dict(snaps[0], symbol="ZZZ/USDT:USDT"))
    trades.append({"symbol": "ZZZ/USDT:USDT", "side": snaps[0]["direction"], "opened_at": snaps[0]["ts"],
                   "net_pnl": 1.0, "exit_reason": "tp", "mode": "live"})
    rep = T.real_trade_fidelity(trades, snaps, rows, {SYM})
    assert rep["n_closed_trades"] == 7
    assert rep["n_with_snapshot"] == 6 and rep["n_without_snapshot"] == 1
    assert rep["n_live"] == 6
    by = {(t["symbol"], t["opened_at"]): t for t in rep["trades"]}
    z = by[("ZZZ/USDT:USDT", snaps[0]["ts"])]
    assert z["matched"] is None and z["fire_minute"] is None
    t0 = by[(SYM, snaps[0]["ts"] + 7.5)]
    assert t0["matched"] is True and t0["confirmed_at_close"] is False and t0["fire_minute"] == early[0]["fire_minute"]
    assert t0["net_pnl"] == 0.4 and t0["exit_reason"] == "tp" and t0["mode"] == "live"
    c = rep["cohorts"]
    assert c["confirmed"]["n"] == 2 and c["forming_only"]["n"] == 2
    assert c["confirmed"]["net"] == pytest.approx(0.7) and c["forming_only"]["net"] == pytest.approx(0.1)
    assert c["confirmed"]["wr"] == pytest.approx(0.5) and c["forming_only"]["mean"] == pytest.approx(0.05)
    for k in ("confirmed", "forming_only"):
        assert len(c[k]["ci95"]) == 2 and c[k]["ci95"][0] <= c[k]["mean"] <= c[k]["ci95"][1]
    assert len(c["diff_ci95_confirmed_minus_forming"]) == 2
    assert c["n_boot"] == 2000 and "screening" in rep["grade"].lower()
    json.dumps(rep)
    md = T.real_trade_fidelity_md(rep)
    assert "screening" in md.lower() and "confirmed_at_close" in md


def test_load_closed_trades_read_only(tmp_path):
    p = tmp_path / "trading_state_5m_mean_revert.json"
    p.write_text(json.dumps({"closed_trades": [{"symbol": SYM, "side": "long", "opened_at": 1.0,
                                                 "net_pnl": 0.1, "exit_reason": "tp", "mode": "live"}],
                             "positions": {}}))
    before = p.stat().st_mtime_ns
    got = T.load_closed_trades(str(p))
    assert len(got) == 1 and got[0]["symbol"] == SYM
    assert p.stat().st_mtime_ns == before
    assert T.load_closed_trades(str(tmp_path / "missing.json")) == []
