"""informed_flow_btc_alt_cascade_v2 paper-slot tests (2026-09-20 build, resume).

Fixture-based, no network. Pre-registration (binding verdict line):
docs/superpowers/specs/2026-09-20-informed_flow_btc_alt_cascade_v2-prereg.md.
Frozen spec: research/swarm/runs/2026-09-19-1451/specs/
informed_flow_btc_alt_cascade_v2.frozen.json; frozen signal:
research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/
signal.py (read-only here — never edited, never imported for anything but
parity).

Covers: (a) signal parity vs the frozen file on synthetic frames, (a2) parity
on the research cache's real TRAIN frames (skips when the cache is absent),
(b) forming-bar exclusion, (c) exit golden cases identical to
research.swarm.lib.screen.simulate, (d) sidecar state IO, (e) AST wiring in
bot.py, (f) bare-bot orchestration on a FakeExchange (paper book, live guard
BEFORE any exchange call), (f2) the owner-authorised reference feed (one
BTC fetch per cycle, closed bars only, lag/empty handling).
"""
import datetime as dt
import importlib.util
import json
import logging
import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

import informed_flow_btc_alt_cascade_v2_slot as mod
import risk_manager
import strategy_slot
from strategy_slot import StrategySlot

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_DIR = os.path.join(BOT_DIR, "research", "swarm", "runs", "2026-09-19-1451")
FROZEN_SPEC = os.path.join(RUN_DIR, "specs", "informed_flow_btc_alt_cascade_v2.frozen.json")
FROZEN_SIGNAL = os.path.join(RUN_DIR, "screens", "informed_flow_btc_alt_cascade_v2", "signal.py")
SLOT_ID = "informed_flow_btc_alt_cascade_v2"
DOGE = "DOGE/USDT:USDT"
ADA = "ADA/USDT:USDT"
XRP = "XRP/USDT:USDT"
BTC = "BTC/USDT:USDT"


def _spec() -> dict:
    with open(FROZEN_SPEC) as f:
        return json.load(f)["thesis"]["spec"]


def _frozen_module():
    """Import the frozen signal file from its path (read-only)."""
    spec = importlib.util.spec_from_file_location("frozen_informed_flow_v2_signal", FROZEN_SIGNAL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── frame builders ─────────────────────────────────────────────────────────

def _ohlcv(closes, index, jitter=0.0):
    """OHLCV frame with open==prev close, high/low = close ± jitter."""
    closes = [float(c) for c in closes]
    opens = [closes[0]] + closes[:-1]
    return pd.DataFrame({
        "open": opens,
        "high": [c + jitter for c in closes],
        "low": [c - jitter for c in closes],
        "close": closes,
        "volume": [1.0] * len(closes),
    }, index=pd.DatetimeIndex(index))


def _hour_grid(n, end=None, tz=None):
    """n hourly bars ENDING at `end` (default: a fixed, long-closed past bar)."""
    end = end or pd.Timestamp("2026-01-10 12:00:00")
    idx = pd.date_range(end=end, periods=n, freq="h")
    return idx.tz_localize(tz) if tz else idx


# ── (a) signal parity — synthetic ──────────────────────────────────────────

def test_signal_constants_match_frozen_file():
    fz = _frozen_module()
    assert mod.K == fz.K == 3
    assert mod.THRESH_BPS == fz.THRESH_BPS == 150.0
    assert mod.LAG_RATIO == fz.LAG_RATIO == 0.5


def test_signal_parity_synthetic_with_intersection(monkeypatch):
    """Alt and reference on one 1h grid, with rows each side lacks (so the
    intersection is exercised) and enough BTC-pump / alt-laggard rows that
    the signal fires at least once and stays 0 elsewhere. Frozen signals(df)
    (loader monkeypatched to the synthetic reference) must equal the module's
    signals(df, ref_df) exactly — index, values, dtype."""
    grid = _hour_grid(40, tz="UTC")
    # BTC: flat 100, one +2% step at bar 20 (trailing-3 return = 200 bps at
    # bars 20..22), then flat; a second, smaller +1% step at bar 30 (100 bps,
    # below THRESH — must stay 0).
    btc = [100.0] * 20 + [102.0] * 10 + [103.02] * 10
    # alt: flat (captures 0% of BTC's move) except it catches up fully at bar
    # 22 (alt_ret 200 bps >= btc_ret * 0.5 -> 0 there).
    alt = [50.0] * 22 + [51.0] * 18
    alt_df = _ohlcv(alt, grid)
    ref_df = _ohlcv(btc, grid)
    # rows the alt lacks (drop 2 alt bars) and rows the reference lacks (drop
    # 2 other bars): both sides of the intersection are exercised.
    alt_df = alt_df.drop(grid[[5, 6]])
    ref_df = ref_df.drop(grid[[10, 21]])

    fz = _frozen_module()
    monkeypatch.setattr(fz.ld, "load_reference", lambda *a, **k: ref_df)
    expected = fz.signals(alt_df)
    got = mod.signals(alt_df, ref_df)
    pdt.assert_series_equal(expected, got)
    assert set(got.unique()) <= {-1, 0}
    assert (got == -1).sum() >= 1
    # bar 20: BTC 200 bps, alt 0 -> -1; bar 21 is missing from the reference
    # -> reindex/fillna 0; bar 22: alt caught up (200 bps) -> 0.
    assert got.loc[grid[20]] == -1
    assert got.loc[grid[21]] == 0
    assert got.loc[grid[22]] == 0
    assert got.loc[grid[30]] == 0          # 100 bps BTC step < THRESH_BPS


# ── (a2) signal parity — REAL TRAIN DATA (proves the transcription) ────────

def test_signal_parity_real_train_frames():
    from research.swarm.lib import load_data as ld
    spec = _spec()
    cache_dir = os.path.join(BOT_DIR, ld.DATASETS[spec["dataset"]]["dir"])
    if not os.path.isdir(cache_dir):
        pytest.skip(f"research cache absent: {cache_dir}")
    fz = _frozen_module()
    ref = ld.load_ohlcv("BTC", "1h", era="train", dataset=spec["dataset"])
    syms = spec["universe"][:4]
    assert len(syms) >= 3
    any_nonzero = False
    for sym in syms:
        df = ld.load_ohlcv(sym, spec["timeframe"], era="train", dataset=spec["dataset"])
        expected = fz.signals(df)              # real path: no screen context -> train load
        got = mod.signals(df, ref)
        pdt.assert_series_equal(expected, got)
        assert set(got.unique()) <= {-1, 0}
        any_nonzero = any_nonzero or bool((got != 0).any())
    assert any_nonzero, "all-zero parity proves nothing"


# ── (b) forming-bar exclusion ──────────────────────────────────────────────

def test_complete_bars_drops_forming_bar_and_keeps_closed():
    idx = pd.date_range("2026-01-10 09:00:00", periods=4, freq="h")   # naive UTC
    df = _ohlcv([1, 2, 3, 4], idx)
    # last bar opens 12:00, closes 13:00. At 12:59:59 it is forming -> dropped.
    now = dt.datetime(2026, 1, 10, 12, 59, 59, tzinfo=dt.timezone.utc)
    closed = mod.complete_bars(df, now_utc=now)
    assert list(closed["close"]) == [1.0, 2.0, 3.0]
    # exactly at 13:00 it is closed -> kept.
    now2 = dt.datetime(2026, 1, 10, 13, 0, 0, tzinfo=dt.timezone.utc)
    assert list(mod.complete_bars(df, now_utc=now2)["close"]) == [1.0, 2.0, 3.0, 4.0]
    # tz-aware index (research-cache shape) follows the same rule
    df_tz = _ohlcv([1, 2, 3, 4], idx.tz_localize("UTC"))
    assert list(mod.complete_bars(df_tz, now_utc=now)["close"]) == [1.0, 2.0, 3.0]
    # None / empty are safe
    assert len(mod.complete_bars(None)) == 0
    assert len(mod.complete_bars(df.iloc[0:0])) == 0
    # default clock: a long-past frame is fully closed
    assert len(mod.complete_bars(df)) == 4


# ── (c) exit rule golden cases (== research.swarm.lib.screen.simulate) ─────

def test_frozen_geometry_constants():
    spec = _spec()
    assert mod.TP_BPS == spec["tp_bps"] == 250
    assert mod.SL_BPS == spec["sl_bps"] == 150
    assert mod.MAX_HOLD_BARS == spec["max_hold_bars"] == 7
    assert mod.TIMEFRAME == spec["timeframe"] == "1h"
    assert mod.UNIVERSE == spec["universe"]
    assert mod.SYMBOLS == [f"{b}/USDT:USDT" for b in spec["universe"]]
    assert mod.OHLCV_LIMIT in (5, 10, 50, 100, 500, 1000)
    assert mod.OHLCV_LIMIT > mod.K + 1 + 1     # K lookback + the bar itself + forming
    assert mod.REF_SYMBOL == BTC and mod.REF_TIMEFRAME == "1h"


def test_exit_check_short_sl_and_tp_same_bar_sl_wins():
    entry = 100.0
    sl = entry * (1 + 150 / 1e4)   # 101.5
    tp = entry * (1 - 250 / 1e4)   # 97.5
    # one bar touching BOTH: high >= sl and low <= tp -> stop_loss at SL level
    assert mod.exit_check("short", entry, 102.0, 97.0, 99.0, 0) == ("stop_loss", sl)
    # TP-only bar -> take_profit at the TP level
    assert mod.exit_check("short", entry, 100.5, 97.4, 98.0, 3) == ("take_profit", tp)
    # exact touches count (>= / <=)
    assert mod.exit_check("short", entry, sl, 99.0, 100.0, 0) == ("stop_loss", sl)
    assert mod.exit_check("short", entry, 100.5, tp, 98.0, 0) == ("take_profit", tp)
    # no touch, below max_hold -> None
    assert mod.exit_check("short", entry, 101.0, 99.0, 100.0, 6) is None


def test_exit_check_long_sl_and_tp_same_bar_sl_wins():
    entry = 100.0
    sl = entry * (1 - 150 / 1e4)   # 98.5
    tp = entry * (1 + 250 / 1e4)   # 102.5
    assert mod.exit_check("long", entry, 103.0, 98.0, 101.0, 0) == ("stop_loss", sl)
    assert mod.exit_check("long", entry, 102.6, 99.0, 102.0, 2) == ("take_profit", tp)
    assert mod.exit_check("long", entry, 101.0, 99.0, 100.0, 6) is None


def test_exit_check_time_exit_at_max_hold_bar_close():
    """simulate: bars j = entry_i .. entry_i + max_hold_bars; the entry bar is
    bars_held 0, so the time exit fires on the bar with bars_held ==
    MAX_HOLD_BARS (the max_hold-th bar after entry) at ITS close."""
    entry = 100.0
    for held in range(mod.MAX_HOLD_BARS):
        assert mod.exit_check("short", entry, 101.0, 99.0, 100.3, held) is None
    assert mod.exit_check("short", entry, 101.0, 99.0, 100.3, mod.MAX_HOLD_BARS) == ("time_exit", 100.3)
    assert mod.exit_check("long", entry, 101.0, 99.0, 99.7, mod.MAX_HOLD_BARS + 1) == ("time_exit", 99.7)
    # SL still wins over the time exit on the same bar (simulate checks SL/TP first)
    sl = entry * (1 + 150 / 1e4)   # simulate's exact arithmetic (101.49999999999999)
    assert mod.exit_check("short", entry, 102.0, 99.0, 100.3, mod.MAX_HOLD_BARS) == ("stop_loss", sl)


def test_exit_check_matches_simulate_on_random_paths():
    """Cross-check against research.swarm.lib.screen.simulate on random
    walks: for every simulated trade, replaying exit_check bar by bar from the
    entry bar must reproduce (exit bar, reason, exit price)."""
    from research.swarm.lib import screen
    rng = np.random.default_rng(3)
    n = 400
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.008, n)))
    idx = _hour_grid(n, tz="UTC")
    df = _ohlcv(closes, idx, jitter=0.0)
    df["high"] = df[["open", "close"]].max(axis=1) * (1 + rng.uniform(0, 0.006, n))
    df["low"] = df[["open", "close"]].min(axis=1) * (1 - rng.uniform(0, 0.006, n))
    sig = pd.Series(0, index=idx, dtype=int)
    # keep every trade clear of the frame's end: simulate truncates the last
    # trade at n-1 (last = min(entry_i + max_hold, n-1)), an end-of-data
    # artifact a live replay never sees.
    sig.iloc[rng.choice(n - mod.MAX_HOLD_BARS - 3, size=40, replace=False)] = -1
    trades = screen.simulate(df, sig, mod.TP_BPS, mod.SL_BPS, mod.MAX_HOLD_BARS)
    assert len(trades) >= 10
    reason_map = {"SL": "stop_loss", "TP": "take_profit", "TIME": "time_exit"}
    for _, tr in trades.iterrows():
        entry_i = idx.get_loc(tr["entry_ts"])
        entry = float(tr["entry"])
        found = None
        for held, j in enumerate(range(entry_i, n)):
            bar = df.iloc[j]
            hit = mod.exit_check("short", entry, float(bar["high"]), float(bar["low"]),
                                 float(bar["close"]), held)
            if hit is not None:
                found = (idx[j], hit[0], hit[1])
                break
        assert found is not None
        assert found[0] == tr["exit_ts"]
        assert found[1] == reason_map[tr["exit_reason"]]
        assert found[2] == pytest.approx(float(tr["exit"]), rel=0, abs=1e-12)


def test_sl_tp_levels_helper():
    sl, tp = mod.sl_tp_levels("short", 100.0)
    assert sl == pytest.approx(101.5) and tp == pytest.approx(97.5)
    sl, tp = mod.sl_tp_levels("long", 100.0)
    assert sl == pytest.approx(98.5) and tp == pytest.approx(102.5)


# ── sandbox: everything below writes only inside tmp_path ──────────────────

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    monkeypatch.setattr(risk_manager, "PERSISTENCE_FILE", str(tmp_path / "trading_state.json"))
    monkeypatch.setattr(mod, "STATE_FILE", str(tmp_path / f"{SLOT_ID}_slot_state.json"))
    monkeypatch.setattr(mod, "SIGNAL_FILES", {
        sym: str(tmp_path / f"{SLOT_ID}_signal_{sym.split('/')[0]}.json")
        for sym in mod.SYMBOLS})
    return tmp_path


# ── (d) sidecar state ──────────────────────────────────────────────────────

def test_state_save_load_roundtrip_atomic(sandbox):
    state = mod.load_state()
    assert set(state) == set(mod.SYMBOLS)
    state[DOGE]["last_bar_ts"] = "2026-01-10T12:00:00Z"
    state[DOGE]["bars_held"] = 3
    mod.save_state(state)
    assert os.path.exists(mod.STATE_FILE)
    assert not os.path.exists(mod.STATE_FILE + ".tmp")     # atomic replace
    assert mod.load_state() == state


def test_load_state_missing_or_corrupt_yields_defaults(sandbox):
    assert mod.load_state() == {sym: mod.default_symbol_state() for sym in mod.SYMBOLS}
    with open(mod.STATE_FILE, "w") as f:
        f.write("{not json")
    st = mod.load_state()
    assert st[DOGE] == mod.default_symbol_state()
    assert mod.default_symbol_state()["last_bar_ts"] is None
    assert mod.default_symbol_state()["bars_held"] == 0


def test_save_state_never_raises(sandbox, monkeypatch):
    monkeypatch.setattr(mod, "STATE_FILE", str(sandbox / "no_such_dir" / "x.json"))
    mod.save_state({DOGE: mod.default_symbol_state()})       # OSError swallowed


def test_sidecar_names_not_prefixed_trading_state():
    assert not os.path.basename(mod.STATE_FILE).startswith("trading_state")
    assert os.path.basename(mod.STATE_FILE) == f"{SLOT_ID}_slot_state.json"
    assert set(mod.SIGNAL_FILES) == set(mod.SYMBOLS)
    for sym, p in mod.SIGNAL_FILES.items():
        assert not os.path.basename(p).startswith("trading_state")
        assert os.path.basename(p) == f"{SLOT_ID}_signal_{sym.split('/')[0]}.json"


def test_append_signal_bars_idempotent_per_ts_and_bounded(sandbox):
    path = mod.SIGNAL_FILES[DOGE]
    mod.append_signal_bars(DOGE, [{"ts": "2026-01-10T12:00:00Z", "signal": 0}])
    mod.append_signal_bars(DOGE, [{"ts": "2026-01-10T12:00:00Z", "signal": -1}])
    with open(path) as f:
        bars = json.load(f)["bars"]
    assert len(bars) == 1 and bars[0]["signal"] == -1        # re-eval replaced, not duped
    many = [{"ts": f"t{i}", "signal": 0} for i in range(mod._MAX_BAR_RECORDS + 5)]
    mod.append_signal_bars(DOGE, many)
    with open(path) as f:
        bars = json.load(f)["bars"]
    assert len(bars) == mod._MAX_BAR_RECORDS
    mod.append_signal_bars("NOPE/USDT:USDT", [{"ts": "x"}])   # unknown symbol: no-op


# ── (e) bot wiring (source + AST — no network, no bot construction) ────────

def test_bot_slot_config_matches_rails_optout():
    """Exactly one StrategySlot(...) in bot.py carries this slot, with the
    rails opt-out and a strategy name NOT in STRATEGIES (that absence is what
    keeps every scalper exit path away — _evaluate_slots skips the slot)."""
    import ast
    from strategies import STRATEGIES
    spec = _spec()
    src = open(os.path.join(BOT_DIR, "bot.py")).read()
    assert SLOT_ID not in STRATEGIES
    tree = ast.parse(src)
    slots = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "StrategySlot"):
            kw = {k.arg: ast.unparse(k.value) for k in node.keywords}
            if kw.get("slot_id", "").strip("'\"") == SLOT_ID:
                slots.append(kw)
    assert len(slots) == 1
    kw = slots[0]
    assert kw["strategy_name"].strip("'\"") == SLOT_ID
    assert kw["timeframe"].strip("'\"") == spec["timeframe"]
    assert kw["max_positions"] == str(len(spec["universe"]))
    assert kw["capital_pct"] == "0.0"
    assert kw["paper_mode"] == "True"
    assert kw["trade_amount_usdt"] == "None"
    assert kw["loss_cap_usdt"] == "-999.0"
    assert kw["kelly_min_trades"] == "10 ** 9"
    assert kw["durable_trail_enabled"] == "False"
    assert "self._evaluate_informed_flow_btc_alt_cascade_v2(prices)" in src
    assert "import informed_flow_btc_alt_cascade_v2_slot" in src


def test_strategy_slot_derives_dashboard_state_filename(sandbox):
    """web_dashboard.read_all_slot_states globs trading_state_*.json — the
    StrategySlot-derived state path is exactly that file for this slot."""
    slot = _make_slot()
    assert os.path.basename(slot.risk.state_file) == f"trading_state_{SLOT_ID}.json"


def test_notional_is_fee_math_position_notional():
    from research.swarm.lib import fee_math
    assert mod.NOTIONAL_USDT == fee_math.position_notional() == 200.0


# ── bare-bot orchestration (paper book, no network) ────────────────────────

def _make_slot(paper=True):
    return StrategySlot(slot_id=SLOT_ID, strategy_name=SLOT_ID,
                        timeframe="1h", max_positions=16, capital_pct=0.0,
                        paper_mode=paper, trade_amount_usdt=None,
                        loss_cap_usdt=-999.0, kelly_min_trades=10**9,
                        durable_trail_enabled=False)


def _bare_bot(slots, state=None):
    import bot as botmod
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = slots
    b._informed_flow_btc_alt_cascade_v2_state = state or mod.load_state()
    b._informed_flow_btc_alt_cascade_v2_live_warned = {}
    b.cycle_count = 7
    return b


class FakeExchange:
    """Per-symbol OHLCV frames; records every call."""
    def __init__(self, frames=None, ticker_price=None):
        self.frames = frames or {}
        self.ticker_price = ticker_price
        self.calls = []

    def get_ohlcv(self, symbol, timeframe, limit=100):
        self.calls.append(("get_ohlcv", symbol, timeframe, limit))
        return self.frames.get(symbol)

    def get_ticker(self, symbol):
        self.calls.append(("get_ticker", symbol))
        if self.ticker_price is None:
            return None
        return {"last": self.ticker_price}

    def ohlcv_calls(self, symbol):
        return [c for c in self.calls if c[0] == "get_ohlcv" and c[1] == symbol]


def _pump_frames(n=30, end=None, fire=True, alt_close=50.0):
    """Reference + alt frames (exchange shape: naive-UTC hourly) whose LAST
    bar carries a BTC 3-bar +2% pump (200 bps > 150) with the alt flat
    (captured 0% < 50%) -> signal -1 at the last closed bar when fire=True;
    fire=False keeps BTC flat -> 0 everywhere."""
    idx = _hour_grid(n, end=end)
    btc = [100.0] * n
    if fire:
        btc[-1] = 102.0
    alt = [alt_close] * n
    return _ohlcv(btc, idx, jitter=0.1), _ohlcv(alt, idx, jitter=0.01)


def _append_bar(df, close, high=None, low=None):
    ts = df.index[-1] + pd.Timedelta(hours=1)
    row = pd.DataFrame({"open": [float(df["close"].iloc[-1])],
                        "high": [float(high if high is not None else close)],
                        "low": [float(low if low is not None else close)],
                        "close": [float(close)], "volume": [1.0]},
                       index=pd.DatetimeIndex([ts]))
    return pd.concat([df, row])


@pytest.fixture
def small_universe(monkeypatch):
    monkeypatch.setattr(mod, "SYMBOLS", [DOGE, ADA, XRP])
    monkeypatch.setattr(mod, "SIGNAL_FILES", {
        sym: os.path.join(os.getcwd(), f"{SLOT_ID}_signal_{sym.split('/')[0]}.json")
        for sym in [DOGE, ADA, XRP]})
    return [DOGE, ADA, XRP]


def _pace_frames(n=30, end=None):
    """An alt that KEEPS PACE with the reference pump (+2% on the last bar:
    alt_ret 200 bps >= btc_ret * 0.5) -> never a laggard, signal 0 whether or
    not BTC pumps. Used for the 'other' universe symbols."""
    idx = _hour_grid(n, end=end)
    return _ohlcv([50.0] * (n - 1) + [51.0], idx, jitter=0.01)


# ── (f) orchestration ──────────────────────────────────────────────────────

def test_closed_bar_signal_opens_one_paper_short_at_fresh_price(sandbox, small_universe):
    slot = _make_slot()
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=True)
    frames = {BTC: ref, DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.2)     # fresh REST > cached
    b._evaluate_informed_flow_btc_alt_cascade_v2({DOGE: 50.0, ADA: 50.0, XRP: 50.0})
    assert list(slot.risk.positions) == [DOGE]
    pos = slot.risk.positions[DOGE]
    assert pos.side == "short"
    assert pos.entry_price == pytest.approx(50.2)
    assert pos.margin == pytest.approx(mod.NOTIONAL_USDT)          # 1x: margin == notional
    assert pos.amount == pytest.approx(mod.NOTIONAL_USDT / 50.2)
    assert pos.stop_loss == pytest.approx(50.2 * (1 + 150 / 1e4))
    assert pos.take_profit == pytest.approx(50.2 * (1 - 250 / 1e4))
    assert pos.strategy == SLOT_ID
    assert slot.total_entries == 1
    st = b._informed_flow_btc_alt_cascade_v2_state
    assert st[DOGE]["last_bar_ts"] == mod.ts_key(doge.index[-1])
    assert st[DOGE]["bars_held"] == 0
    assert st[ADA]["last_bar_ts"] == mod.ts_key(doge.index[-1])   # flat alts stamped too
    with open(mod.STATE_FILE) as f:                                  # persisted
        assert json.load(f)[DOGE]["last_bar_ts"] == mod.ts_key(doge.index[-1])
    with open(mod.SIGNAL_FILES[DOGE]) as f:
        bars = json.load(f)["bars"]
    assert bars[-1]["signal"] == -1 and bars[-1]["ts"] == mod.ts_key(doge.index[-1])
    with open(os.path.join(str(sandbox), f"trading_state_{SLOT_ID}.json")) as f:
        assert DOGE in json.load(f)["positions"]                    # dashboard file


def test_same_closed_bar_not_evaluated_twice(sandbox, small_universe):
    slot = _make_slot()
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=True)
    frames = {BTC: ref, DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    prices = {DOGE: 50.0, ADA: 50.0, XRP: 50.0}
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert slot.total_entries == 1
    n_calls = len(b.exchange.calls)
    # second cycle, same bars: nothing re-evaluated, no new entry, no ticker.
    # Perf gate (2026-09-20): every symbol is already stamped to the
    # reference's newest closed bar, so the alt fetch is skipped entirely —
    # only the once-per-cycle reference fetch is added, zero alt fetches.
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert slot.total_entries == 1
    assert len(slot.risk.positions) == 1
    added = b.exchange.calls[n_calls:]
    assert added == [("get_ohlcv", mod.REF_SYMBOL, mod.REF_TIMEFRAME, mod.OHLCV_LIMIT)]


def test_later_bar_touching_sl_closes_stop_loss_at_level(sandbox, small_universe):
    slot = _make_slot()
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=True)
    frames = {BTC: ref, DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    prices = {DOGE: 50.0, ADA: 50.0, XRP: 50.0}
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    pos = slot.risk.positions[DOGE]
    sl = pos.entry_price * (1 + 150 / 1e4)            # 50.75
    # next closed bar: high through the SL (and BTC keeps pace so no lag)
    frames[BTC] = _append_bar(ref, 102.0)
    frames[DOGE] = _append_bar(doge, 50.6, high=51.0, low=49.9)
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert DOGE not in slot.risk.positions
    t = slot.risk.closed_trades[-1]
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_price"] == pytest.approx(sl)
    assert t["side"] == "short"
    st = b._informed_flow_btc_alt_cascade_v2_state[DOGE]
    assert st["last_bar_ts"] == mod.ts_key(frames[DOGE].index[-1])
    assert st["bars_held"] == 0


def test_bars_held_counts_closed_bars_then_time_exits(sandbox, small_universe):
    slot = _make_slot()
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=True)
    frames = {BTC: ref, DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    prices = {DOGE: 50.0, ADA: 50.0, XRP: 50.0}
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    st = b._informed_flow_btc_alt_cascade_v2_state[DOGE]
    # bars 0..6 after entry: no touch -> held; bar 7 (bars_held == MAX_HOLD) -> time_exit
    for k in range(mod.MAX_HOLD_BARS):
        frames[BTC] = _append_bar(frames[BTC], 102.0)
        frames[DOGE] = _append_bar(frames[DOGE], 50.1, high=50.2, low=49.9)
        b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
        assert DOGE in slot.risk.positions
        assert st["bars_held"] == k + 1
    frames[BTC] = _append_bar(frames[BTC], 102.0)
    frames[DOGE] = _append_bar(frames[DOGE], 50.3, high=50.4, low=50.0)
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert DOGE not in slot.risk.positions
    t = slot.risk.closed_trades[-1]
    assert t["exit_reason"] == "time_exit"
    assert t["exit_price"] == pytest.approx(50.3)


def test_killed_slot_returns_before_any_fetch(sandbox, small_universe):
    slot = _make_slot()
    slot.enabled = False
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=True)
    b.exchange = FakeExchange(frames={BTC: ref, DOGE: doge}, ticker_price=50.0)
    b._evaluate_informed_flow_btc_alt_cascade_v2({DOGE: 50.0})
    assert b.exchange.calls == []
    assert slot.risk.positions == {}
    assert b._informed_flow_btc_alt_cascade_v2_state[DOGE]["last_bar_ts"] is None


def test_missing_slot_is_a_noop(sandbox, small_universe):
    b = _bare_bot([])
    b.exchange = FakeExchange()
    b._evaluate_informed_flow_btc_alt_cascade_v2({})
    assert b.exchange.calls == []


def test_entries_blocked_no_new_entry_but_exits_still_run(sandbox, small_universe, monkeypatch):
    slot = _make_slot()
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=True)
    frames = {BTC: ref, DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    prices = {DOGE: 50.0, ADA: 50.0, XRP: 50.0}
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert DOGE in slot.risk.positions
    # global entry block: the open position's SL still closes it ...
    monkeypatch.setattr(b, "_slot_entries_blocked", lambda: True)
    frames[BTC] = _append_bar(ref, 104.0)                       # a fresh BTC pump -> new signal
    frames[DOGE] = _append_bar(doge, 50.6, high=51.0, low=49.9)  # ... and DOGE touches its SL
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert DOGE not in slot.risk.positions
    assert slot.risk.closed_trades[-1]["exit_reason"] == "stop_loss"
    assert slot.total_entries == 1                               # no NEW entry while blocked
    # ... and it retries (bar not stamped) once the block lifts
    st = b._informed_flow_btc_alt_cascade_v2_state[DOGE]
    assert st["last_bar_ts"] == mod.ts_key(doge.index[-1])
    monkeypatch.setattr(b, "_slot_entries_blocked", lambda: False)
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert DOGE in slot.risk.positions
    assert slot.total_entries == 2
    assert st["last_bar_ts"] == mod.ts_key(frames[DOGE].index[-1])


def test_live_mode_touches_nothing_even_with_sl_touched(sandbox, small_universe, caplog):
    """The live guard sits BEFORE the exit path: _close_slot_position on a
    non-paper slot places a REAL market order, so a promoted slot with an
    open paper position and an SL-touching bar must make NO exchange call of
    any kind (reference fetch included), leave the position untouched, and
    log one error per UTC day."""
    slot = _make_slot(paper=False)
    b = _bare_bot([slot])
    # a paper-era position already on the book
    pos = slot.risk.open_position(DOGE, 50.0, mod.NOTIONAL_USDT, side="short",
                                  atr=0.0, regime="medium", cycle=1, strategy=SLOT_ID)
    pos.amount = mod.NOTIONAL_USDT / 50.0
    pos.margin = mod.NOTIONAL_USDT
    ref, doge = _pump_frames(fire=True)
    doge = _append_bar(doge, 50.6, high=51.0, low=49.9)          # touches SL 50.75
    ref = _append_bar(ref, 102.0)
    b.exchange = FakeExchange(frames={BTC: ref, DOGE: doge}, ticker_price=50.6)
    closes = []
    b._close_slot_position = lambda *a, **k: closes.append(a) or True
    with caplog.at_level(logging.ERROR, logger="DegenCryt"):
        b._evaluate_informed_flow_btc_alt_cascade_v2({DOGE: 50.6})
        b._evaluate_informed_flow_btc_alt_cascade_v2({DOGE: 50.6})   # same day: no 2nd log
    assert b.exchange.calls == []                                # nothing fetched, nothing ordered
    assert DOGE in slot.risk.positions and slot.risk.positions[DOGE] is pos
    assert closes == []
    assert slot.risk.closed_trades == []
    assert b._informed_flow_btc_alt_cascade_v2_live_warned[SLOT_ID] == mod.utc_date_str()
    live_logs = [r for r in caplog.records if r.levelno >= logging.ERROR
                 and "LIVE" in r.getMessage() and SLOT_ID.upper() in r.getMessage()]
    assert len(live_logs) == 1
    assert b._informed_flow_btc_alt_cascade_v2_state[DOGE]["last_bar_ts"] is None


# ── (f2) reference feed orchestration ──────────────────────────────────────

def test_reference_fetched_exactly_once_per_cycle(sandbox, small_universe):
    slot = _make_slot()
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=False)
    frames = {BTC: ref, DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    b._evaluate_informed_flow_btc_alt_cascade_v2({DOGE: 50.0, ADA: 50.0, XRP: 50.0})
    assert len(b.exchange.ohlcv_calls(BTC)) == 1
    assert b.exchange.ohlcv_calls(BTC)[0] == ("get_ohlcv", mod.REF_SYMBOL, mod.REF_TIMEFRAME, mod.OHLCV_LIMIT)
    for sym in small_universe:
        assert len(b.exchange.ohlcv_calls(sym)) == 1
        assert b.exchange.ohlcv_calls(sym)[0] == ("get_ohlcv", sym, mod.TIMEFRAME, mod.OHLCV_LIMIT)
    # the reference fetch precedes every alt fetch
    first_alt = min(b.exchange.calls.index(b.exchange.ohlcv_calls(s)[0]) for s in small_universe)
    assert b.exchange.calls.index(b.exchange.ohlcv_calls(BTC)[0]) < first_alt
    assert slot.risk.positions == {}                           # flat BTC: no signal


def test_alt_fetch_skipped_when_already_synced_to_reference_bar(sandbox, small_universe):
    """Perf gate (2026-09-20): the alt fetch happens only after
    `self.exchange.get_ohlcv(symbol, ...)` in the OLD code; the new gate
    checks the stored stamp against the reference's newest closed bar
    BEFORE that fetch. When every symbol is already synced to that bar,
    two consecutive cycles must each make exactly ONE get_ohlcv call (the
    reference) and ZERO alt fetches."""
    slot = _make_slot()
    ref, doge = _pump_frames(fire=False)
    ref_bar_key = mod.ts_key(mod.complete_bars(ref).index[-1])
    state = {sym: mod.default_symbol_state() for sym in small_universe}
    for sym in small_universe:
        state[sym]["last_bar_ts"] = ref_bar_key
    b = _bare_bot([slot], state=state)
    frames = {BTC: ref, DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    prices = {DOGE: 50.0, ADA: 50.0, XRP: 50.0}
    for _ in range(2):
        n = len(b.exchange.calls)
        b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
        added = b.exchange.calls[n:]
        assert added == [("get_ohlcv", mod.REF_SYMBOL, mod.REF_TIMEFRAME, mod.OHLCV_LIMIT)]
    for sym in small_universe:
        assert b.exchange.ohlcv_calls(sym) == []
    assert slot.risk.positions == {}


def test_alt_fetch_resumes_once_reference_rolls_to_new_closed_bar(sandbox, small_universe):
    """Once the reference advances to a new closed bar, the stale stamp no
    longer matches ref_bar_key, so the gate lets the fetch through again for
    every symbol."""
    slot = _make_slot()
    ref, doge = _pump_frames(fire=False)
    ref_bar_key = mod.ts_key(mod.complete_bars(ref).index[-1])
    state = {sym: mod.default_symbol_state() for sym in small_universe}
    for sym in small_universe:
        state[sym]["last_bar_ts"] = ref_bar_key
    b = _bare_bot([slot], state=state)
    frames = {BTC: ref, DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    prices = {DOGE: 50.0, ADA: 50.0, XRP: 50.0}
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    for sym in small_universe:
        assert b.exchange.ohlcv_calls(sym) == []                # steady state: still gated
    n = len(b.exchange.calls)
    frames[BTC] = _append_bar(ref, 102.0)                        # reference rolls one closed bar
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    added = b.exchange.calls[n:]
    assert added[0] == ("get_ohlcv", mod.REF_SYMBOL, mod.REF_TIMEFRAME, mod.OHLCV_LIMIT)
    for sym in small_universe:
        assert len(b.exchange.ohlcv_calls(sym)) == 1             # all 3 alts fetched this cycle


def test_forming_reference_bar_pump_does_not_fire_but_closed_does(sandbox, small_universe):
    """The reference frame handed to the signal is CLOSED-bar only: a BTC
    pump living only in the forming reference bar must not fire, while the
    same pump on a closed bar does."""
    slot = _make_slot()
    b = _bare_bot([slot])
    now_floor = pd.Timestamp.now(tz="UTC").floor("h").tz_localize(None)
    end_closed = now_floor - pd.Timedelta(hours=1)               # last CLOSED bar
    ref, doge = _pump_frames(fire=False, end=end_closed)
    # forming reference bar (opens at now_floor, not yet closed) carries the pump
    ref_forming = _append_bar(ref, 102.0)
    assert ref_forming.index[-1] == now_floor
    doge_forming = _append_bar(doge, 50.0)
    frames = {BTC: ref_forming, DOGE: doge_forming, ADA: _pace_frames(end=end_closed),
              XRP: _pace_frames(end=end_closed)}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    prices = {DOGE: 50.0, ADA: 50.0, XRP: 50.0}
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert slot.risk.positions == {}
    assert b._informed_flow_btc_alt_cascade_v2_state[DOGE]["last_bar_ts"] == mod.ts_key(end_closed)
    # same pump on a CLOSED bar -> fires
    slot2 = _make_slot()
    b2 = _bare_bot([slot2], state={s: mod.default_symbol_state() for s in small_universe})
    ref2, doge2 = _pump_frames(fire=True, end=end_closed)
    b2.exchange = FakeExchange(frames={BTC: ref2, DOGE: doge2, ADA: _pace_frames(end=end_closed),
                                       XRP: _pace_frames(end=end_closed)}, ticker_price=50.0)
    b2._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert list(slot2.risk.positions) == [DOGE]


@pytest.mark.parametrize("ref_value", [None, "empty"])
def test_reference_fetch_empty_evaluates_nothing(sandbox, small_universe, caplog, ref_value):
    slot = _make_slot()
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=True)
    frames = {BTC: (None if ref_value is None else ref.iloc[0:0]),
              DOGE: doge, ADA: _pace_frames(), XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    with caplog.at_level(logging.WARNING, logger="DegenCryt"):
        b._evaluate_informed_flow_btc_alt_cascade_v2({DOGE: 50.0, ADA: 50.0, XRP: 50.0})
    assert slot.risk.positions == {}
    assert len(b.exchange.ohlcv_calls(BTC)) == 1
    for sym in small_universe:                                   # no alt evaluated
        assert b.exchange.ohlcv_calls(sym) == []
        assert b._informed_flow_btc_alt_cascade_v2_state[sym]["last_bar_ts"] is None
    assert any("reference" in r.getMessage() and "retrying next cycle" in r.getMessage()
               for r in caplog.records if r.levelno == logging.WARNING)
    # next cycle with a good reference: evaluated, entry opens
    frames[BTC] = ref
    b._evaluate_informed_flow_btc_alt_cascade_v2({DOGE: 50.0, ADA: 50.0, XRP: 50.0})
    assert list(slot.risk.positions) == [DOGE]


def test_reference_lagging_alt_skipped_then_retried(sandbox, small_universe):
    """Last closed reference ts < last closed alt ts (BTC bar not in yet):
    that alt is neither evaluated nor stamped this cycle — a fillna(0) at the
    newest bar would silently drop a signal — and is retried next cycle."""
    slot = _make_slot()
    b = _bare_bot([slot])
    ref, doge = _pump_frames(fire=True)
    ref_lagging = ref.iloc[:-1]                                  # BTC's newest bar missing
    ada = _pace_frames().iloc[:-1]                               # ADA at the reference's pace
    frames = {BTC: ref_lagging, DOGE: doge, ADA: ada, XRP: _pace_frames()}
    b.exchange = FakeExchange(frames=frames, ticker_price=50.0)
    prices = {DOGE: 50.0, ADA: 50.0, XRP: 50.0}
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    st = b._informed_flow_btc_alt_cascade_v2_state
    assert slot.risk.positions == {}
    assert st[DOGE]["last_bar_ts"] is None                       # skipped, not stamped
    assert st[XRP]["last_bar_ts"] is None
    assert st[ADA]["last_bar_ts"] == mod.ts_key(ada.index[-1])   # in step with BTC: evaluated
    # reference catches up: DOGE evaluated, signal fires, stamped
    frames[BTC] = ref
    b._evaluate_informed_flow_btc_alt_cascade_v2(prices)
    assert list(slot.risk.positions) == [DOGE]
    assert st[DOGE]["last_bar_ts"] == mod.ts_key(doge.index[-1])
    assert st[XRP]["last_bar_ts"] == mod.ts_key(doge.index[-1])


def test_last_signal_is_safe_on_bad_reference():
    ref, doge = _pump_frames(fire=True)
    assert mod.last_signal(doge, ref) == -1
    assert mod.last_signal(doge, None) == 0
    assert mod.last_signal(doge, ref.iloc[0:0]) == 0
    assert mod.last_signal(doge, ref.iloc[:-1]) == 0             # reference older than alt
    assert mod.last_signal(doge.iloc[0:0], ref) == 0
    assert mod.last_signal(None, ref) == 0
    assert mod.last_signal(doge, ref.tz_localize("UTC")) == 0    # mixed tz: never raises
    # reference AHEAD of the alt is fine (intersection drops the extra bar)
    assert mod.last_signal(doge, _append_bar(ref, 102.0)) == -1


def test_no_kelly_no_demote_rails(sandbox):
    """-999 loss cap + kelly@1e9: paper losses inside the verdict line's
    -$10 kill cap must not trip the slot's own auto-demote rails."""
    slot = _make_slot(paper=False)
    slot.set_live(capital_pct=0.0)
    import time as _time
    slot.risk.closed_trades = [
        {"pnl_usdt": -2.0, "mode": "live", "closed_at": _time.time()}
        for _ in range(4)]
    demote, _ = slot.should_auto_demote()
    assert demote is False
    assert slot.is_killed is False
