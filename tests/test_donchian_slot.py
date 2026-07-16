"""Donchian ensemble slot tests (2026-07-16 build).

Fixture-based, no network: golden hand-computable micro-cases for the
sub-model mechanics (entry at the N-day close-high, midline stop, upward-only
ratchet, close<=stop exit), the combo weight (mean of 9 positions x
vol_scalar, 2.0 cap, 0.25/sigma), the rebalance rules (20% relative
threshold on vol-only drift, immediate on any sub-model flip), sidecar state
(atomic roundtrip, advance_state idempotency / catch-up / reseed), a
regression anchor run over the repo BTC daily CSV, and the bot orchestration
(_evaluate_donchian / _donchian_adjust_position on a bare bot with a fake
exchange — same pattern as test_eth_tsm.py). Spec (frozen):
docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md
"""
import datetime as dt
import json
import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import donchian_slot
import risk_manager
import strategy_slot
from strategy_slot import StrategySlot

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BTC = "BTC/USDT:USDT"
ETH = "ETH/USDT:USDT"
N = len(donchian_slot.LOOKBACKS)  # 9
FLAT_POS = [0] * N
NO_STOPS = [None] * N


# ── golden micro-cases: sub-model mechanics (hand-computable) ──────────────

def test_submodel_enters_exactly_at_n_day_close_high():
    """(a)+(b): with 5 closes, only the lb=5 model evaluates. close 14 == the
    5-day close-high -> enter; stop = midline = (14+10)/2 = 12."""
    pos, stops, w, info = donchian_slot.advance_day(
        FLAT_POS, NO_STOPS, 0.0, [10, 11, 12, 13, 14])
    assert pos[0] == 1
    assert stops[0] == pytest.approx(12.0)          # midline at entry
    assert info["sig_event"] is True
    assert pos[1:] == [0] * (N - 1)                 # windows not full -> untouched
    assert w == 0.0                                 # no vol estimate -> fail closed

    # close 13 is NOT the 5-day high (14 is) -> no entry
    pos2, stops2, _, info2 = donchian_slot.advance_day(
        FLAT_POS, NO_STOPS, 0.0, [10, 11, 12, 14, 13])
    assert pos2[0] == 0 and stops2[0] is None
    assert info2["sig_event"] is False


def test_stop_ratchets_up():
    """(c): entered at close 14 with stop 12; next close 15 -> window
    [11..15], midline (15+11)/2 = 13 > 12 -> stop ratchets up to 13."""
    pos, stops, w, _ = donchian_slot.advance_day(
        FLAT_POS, NO_STOPS, 0.0, [10, 11, 12, 13, 14])
    pos2, stops2, _, _ = donchian_slot.advance_day(
        pos, stops, w, [10, 11, 12, 13, 14, 15])
    assert pos2[0] == 1
    assert stops2[0] == pytest.approx(13.0)


def test_stop_never_ratchets_down():
    """(c): stop 13, window [10,10,10,10,13.5] -> midline 11.75 < 13; close
    13.5 > stop -> stop STAYS 13 (max(prev, mid)), never lowered."""
    pos = [1] + [0] * (N - 1)
    stops = [13.0] + [None] * (N - 1)
    pos2, stops2, _, info = donchian_slot.advance_day(
        pos, stops, 0.0, [10, 10, 10, 10, 13.5])
    assert pos2[0] == 1
    assert stops2[0] == pytest.approx(13.0)
    assert info["sig_event"] is False


def test_exit_exactly_when_close_at_or_below_stop():
    """(d): close == stop exits (<=, inclusive); close a hair above holds."""
    pos = [1] + [0] * (N - 1)
    stops = [13.0] + [None] * (N - 1)
    pos2, stops2, w2, info = donchian_slot.advance_day(
        pos, stops, 0.5, [10, 10, 10, 10, 13.0])
    assert pos2[0] == 0 and stops2[0] is None
    assert info["stop_fired"] is True and info["sig_event"] is True
    assert w2 == 0.0                                # flip -> w takes target (flat)

    pos3, _, _, info3 = donchian_slot.advance_day(
        pos, stops, 0.0, [14, 14, 14, 14, 13.00001])
    assert pos3[0] == 1
    assert info3["stop_fired"] is False


def test_combo_weight_is_mean_of_nine_times_vol_scalar():
    """(e)+(f cap): 90 monotonic +0.1%/day closes -> the 6 models with full
    windows (lb 5..90) are all long, the 3 slow models (150/250/360) can't
    evaluate yet; sigma is tiny -> vol_scalar hits the 2.0 cap.
    w = (6/9) x 2.0 = 4/3 exactly."""
    closes = [100.0 * (1.001 ** i) for i in range(90)]
    pos, stops, w, infos = donchian_slot.run_history(closes)
    assert sum(pos) == 6
    assert infos[-1]["n_long"] == 6
    assert infos[-1]["vol_scalar"] == pytest.approx(2.0)   # cap
    assert w == pytest.approx(6 * 2.0 / 9)


def test_vol_scalar_formula_cap_and_fail_closed():
    """(f): alternating +/-10% daily returns over the 90-return window ->
    sigma known in closed form: std(ddof=1) of 90 zero-mean returns of
    magnitude r is r*sqrt(90/89); annualized x sqrt(365). scalar = 0.25/sigma
    (uncapped). Tiny returns -> capped at 2.0. Zero sigma / short history ->
    None (fail closed)."""
    c = [100.0]
    for i in range(90):
        c.append(c[-1] * (1.1 if i % 2 == 0 else 0.9))
    sigma = 0.1 * np.sqrt(90 / 89) * np.sqrt(365)
    assert donchian_slot._vol_scalar(c) == pytest.approx(0.25 / sigma)

    tiny = [100.0]
    for i in range(94):
        tiny.append(tiny[-1] * (1 + (1e-6 if i % 2 == 0 else -1e-6)))
    assert donchian_slot._vol_scalar(tiny) == pytest.approx(2.0)   # cap

    assert donchian_slot._vol_scalar([100.0] * 95) is None   # sigma == 0
    assert donchian_slot._vol_scalar([100.0] * 89) is None   # < VOL_WINDOW


# ── rebalance rules ────────────────────────────────────────────────────────

def _warm_state(days=120):
    """Deterministic warm ensemble: monotonic +0.1%/day -> 6 models long,
    vol_scalar capped at 2.0, w = 4/3. Returns (pos, stops, w, closes)."""
    closes = [100.0 * (1.001 ** i) for i in range(days)]
    pos, stops, w, _ = donchian_slot.run_history(closes)
    return pos, stops, w, closes


def test_vol_only_drift_below_threshold_holds():
    pos, stops, w, closes = _warm_state()
    day = closes + [closes[-1] * 1.001]  # still the high -> no flips
    _, _, _, info = donchian_slot.advance_day(pos, stops, w, day)
    assert info["sig_event"] is False
    w_prev = info["w_target"] * 1.1      # |dw| = 0.1*wt < 0.2*w_prev -> hold
    _, _, w_new, info2 = donchian_slot.advance_day(pos, stops, w_prev, day)
    assert w_new == w_prev               # NOT rebalanced
    assert info2["w"] == w_prev          # published info carries the held w


def test_vol_only_drift_above_threshold_rebalances():
    pos, stops, w, closes = _warm_state()
    day = closes + [closes[-1] * 1.001]
    _, _, _, info = donchian_slot.advance_day(pos, stops, w, day)
    w_prev = info["w_target"] * 1.5      # |dw| = 0.5*wt > 0.2*w_prev -> move
    _, _, w_new, info2 = donchian_slot.advance_day(pos, stops, w_prev, day)
    assert w_new == info2["w_target"]


def test_submodel_flip_updates_regardless_of_threshold():
    """Close just below the 5d stop: exactly one model stops out. Even with
    w_prev within the 20% band of the new target, the flip forces w=target."""
    pos, stops, w, closes = _warm_state()
    day = closes + [stops[0] - 0.001]    # below 5d stop, above the 10d stop
    _, _, _, info = donchian_slot.advance_day(pos, stops, w, day)
    assert info["sig_event"] is True and info["stop_fired"] is True
    assert info["n_long"] == sum(pos) - 1
    w_prev = info["w_target"] * 1.05     # within the 20% band
    assert abs(info["w_target"] - w_prev) <= 0.2 * w_prev
    _, _, w_new, info2 = donchian_slot.advance_day(pos, stops, w_prev, day)
    assert w_new == info2["w_target"]    # immediate update anyway


def test_rebalance_from_flat_takes_target():
    """w_prev == 0.0 always takes the target, threshold not consulted."""
    pos, stops, _, closes = _warm_state()
    day = closes + [closes[-1] * 1.001]
    _, _, w_new, info = donchian_slot.advance_day(pos, stops, 0.0, day)
    assert info["sig_event"] is False
    assert w_new == info["w_target"] > 0


# ── sandbox: everything below writes only inside tmp_path ──────────────────

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    monkeypatch.setattr(risk_manager, "PERSISTENCE_FILE", str(tmp_path / "trading_state.json"))
    monkeypatch.setattr(donchian_slot, "STATE_FILE", str(tmp_path / "donchian_slot_state.json"))
    monkeypatch.setattr(donchian_slot, "SIGNAL_FILES", {
        sym: str(tmp_path / f"donchian_signal_{sym.split('/')[0]}.json")
        for sym in donchian_slot.SYMBOLS})
    return tmp_path


# ── state: atomic persistence + advance_state semantics ────────────────────

def test_state_save_load_roundtrip_atomic(sandbox):
    state = donchian_slot.load_state()          # defaults for both coins
    state[BTC]["submodel_pos"] = [1, 1, 0, 0, 1, 0, 0, 0, 0]
    state[BTC]["submodel_stops"] = [101.5, 99.0, None, None, 88.25, None, None, None, None]
    state[BTC]["w"] = 0.7412
    state[BTC]["last_close_date"] = "2026-07-14"
    state[BTC]["last_eval_utc_date"] = "2026-07-15"
    state[BTC]["stop_fired_pending"] = True
    donchian_slot.save_state(state)
    assert os.path.exists(donchian_slot.STATE_FILE)
    assert not os.path.exists(donchian_slot.STATE_FILE + ".tmp")  # atomic replace
    assert donchian_slot.load_state() == state


def test_load_state_missing_or_corrupt_yields_defaults(sandbox):
    assert donchian_slot.load_state() == {
        BTC: donchian_slot.default_coin_state(),
        ETH: donchian_slot.default_coin_state()}
    with open(donchian_slot.STATE_FILE, "w") as f:
        f.write("{not json")
    st = donchian_slot.load_state()
    assert st[BTC] == donchian_slot.default_coin_state()


def _dates_closes(n, start="2024-01-01", ret=0.001):
    d0 = dt.date.fromisoformat(start)
    dates = [(d0 + dt.timedelta(days=i)).isoformat() for i in range(n)]
    closes = [100.0 * ((1 + ret) ** i) for i in range(n)]
    return dates, closes


def test_advance_state_bootstrap_then_idempotent():
    dates, closes = _dates_closes(450)
    st = donchian_slot.default_coin_state()
    infos = donchian_slot.advance_state(st, dates, closes)
    assert len(infos) == 1 and "bootstrap" in infos[0]["note"]
    assert st["last_close_date"] == dates[-1]
    snapshot = json.loads(json.dumps(st))
    # same window again: nothing new, state untouched (retry-cycle shape)
    assert donchian_slot.advance_state(st, dates, closes) == []
    assert st == snapshot


def test_advance_state_catches_up_three_day_gap():
    dates, closes = _dates_closes(453)
    st = donchian_slot.default_coin_state()
    donchian_slot.advance_state(st, dates[:450], closes[:450])
    infos = donchian_slot.advance_state(st, dates, closes)   # 3 missed days
    assert [i["date"] for i in infos] == dates[450:]
    assert all("note" not in i for i in infos)               # true catch-up, no reseed
    # incremental catch-up must equal the from-scratch fold of the full series
    _, _, w_full, _ = donchian_slot.run_history(closes)
    assert st["w"] == pytest.approx(w_full, abs=1e-12)
    assert st["last_close_date"] == dates[-1]


def test_advance_state_reseeds_on_unbridgeable_gap():
    """Downtime so deep the last processed close predates the fetched window
    (> the 500-bar fetch, i.e. gap > 360d lookback horizon) -> full reseed."""
    dates, closes = _dates_closes(450)
    st = donchian_slot.default_coin_state()
    st["last_close_date"] = "2020-01-01"          # long before window start
    st["submodel_pos"] = [1] * N                  # stale state must be discarded
    st["submodel_stops"] = [1.0] * N
    st["w"] = 1.23
    infos = donchian_slot.advance_state(st, dates, closes)
    assert len(infos) == 1 and "reseeded" in infos[0]["note"]
    _, _, w_full, _ = donchian_slot.run_history(closes)
    assert st["w"] == pytest.approx(w_full, abs=1e-12)


def test_advance_state_reseeds_when_catchup_prefix_too_shallow():
    """last close inside the window but with < 360 bars of prefix: the frozen
    sub-model state can't bridge the gap -> reseed over the whole window."""
    dates, closes = _dates_closes(450)
    st = donchian_slot.default_coin_state()
    donchian_slot.advance_state(st, dates[:100], closes[:100])
    infos = donchian_slot.advance_state(st, dates, closes)
    assert len(infos) == 1 and "catch-up too deep" in infos[0]["note"]
    _, _, w_full, _ = donchian_slot.run_history(closes)
    assert st["w"] == pytest.approx(w_full, abs=1e-12)


def test_append_signal_days_idempotent_per_date_and_bounded(sandbox):
    path = donchian_slot.SIGNAL_FILES[BTC]
    rec = {"date": "2026-07-14", "w": 0.5}
    donchian_slot.append_signal_days(BTC, [rec])
    donchian_slot.append_signal_days(BTC, [{"date": "2026-07-14", "w": 0.6}])
    with open(path) as f:
        days = json.load(f)["days"]
    assert len(days) == 1 and days[0]["w"] == 0.6   # re-eval replaced, not duped
    many = [{"date": f"d{i}", "w": 0.1} for i in range(805)]
    donchian_slot.append_signal_days(BTC, many)
    with open(path) as f:
        days = json.load(f)["days"]
    assert len(days) == 800                          # _MAX_DAY_RECORDS cap


def test_complete_daily_bars_drops_in_progress_candle():
    now = dt.datetime(2026, 7, 15, 13, 0, tzinfo=dt.timezone.utc)
    idx = pd.to_datetime(["2026-07-12", "2026-07-13", "2026-07-14", "2026-07-15"])
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    dates, closes = donchian_slot.complete_daily_bars(df, now_utc=now)
    assert closes == [1.0, 2.0, 3.0]                 # today's partial candle dropped
    assert dates == ["2026-07-12", "2026-07-13", "2026-07-14"]
    assert donchian_slot.complete_daily_bars(None) == ([], [])


# ── regression vs repo CSV (anchors pin today's verified behavior) ─────────

def test_regression_run_history_btc_csv_anchors():
    """REGRESSION ANCHORS: w values read from running THIS module's
    run_history on the repo CSV on 2026-07-15 (the build-time verified,
    reference-parity behavior). If any anchor moves, the signal math changed
    — that is a spec violation (FROZEN), not a test to update casually."""
    csv = os.path.join(BOT_DIR, "scripts", "research",
                       "htf-rigorous-2026-06-13", "data", "BTC_1d.csv")
    df = pd.read_csv(csv)
    dates = [d[:10] for d in df["dt"]]
    closes = [float(x) for x in df["close"]]
    assert dates[0] == "2021-01-01" and dates[-1] == "2026-06-13"
    assert len(closes) == 1990
    _, _, w_final, infos = donchian_slot.run_history(closes)
    idx = {d: i for i, d in enumerate(dates)}
    anchors = {  # date: (w, n_long) — hard-coded from the 2026-07-15 run
        "2024-01-01": (0.574226433009, 9),
        "2024-06-01": (0.227551250126, 5),
        "2025-01-01": (0.278682277257, 5),
        "2025-06-01": (0.310231261796, 6),
        "2026-06-13": (0.141673042212, 2),
    }
    for date, (w_exp, n_exp) in anchors.items():
        info = infos[idx[date]]
        assert info["w"] == pytest.approx(w_exp, abs=1e-9), date
        assert info["n_long"] == n_exp, date
    assert w_final == pytest.approx(0.141673042212, abs=1e-9)
    # 2024-06-01 is a live rebalance-threshold HOLD in real data: the executed
    # w differs from that day's target (drift inside the 20% band).
    i = infos[idx["2024-06-01"]]
    assert i["w_target"] == pytest.approx(0.228444405042, abs=1e-9)
    assert i["w"] != i["w_target"]


# ── bot wiring (source + AST — no network, no bot construction) ────────────

def test_bot_slot_config_matches_rails_optout():
    """The slots wired into bot.py must carry the rails opt-out and a strategy
    name NOT in STRATEGIES (that absence is what keeps every scalper exit path
    away — _evaluate_slots skips the whole slot, same trick as ETH-TSM)."""
    import ast
    from strategies import STRATEGIES
    src = open(os.path.join(BOT_DIR, "bot.py")).read()
    assert "donchian_ensemble" not in STRATEGIES
    tree = ast.parse(src)
    slots = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "StrategySlot"):
            kw = {k.arg: ast.unparse(k.value) for k in node.keywords}
            if kw.get("slot_id", "").strip("'\"").startswith("DONCHIAN_"):
                slots[kw["slot_id"].strip("'\"")] = kw
    assert set(slots) == {"DONCHIAN_BTC", "DONCHIAN_ETH"}
    for kw in slots.values():
        assert kw["strategy_name"].strip("'\"") == "donchian_ensemble"
        assert kw["paper_mode"] == "True"
        assert kw["loss_cap_usdt"] == "-999.0"
        assert kw["kelly_min_trades"] == "10 ** 9"
        assert kw["durable_trail_enabled"] == "False"
        assert kw["timeframe"].strip("'\"") == "1d"
        assert kw["max_positions"] == "1"
    # the daily evaluator is actually wired into the per-cycle slot pass
    assert "self._evaluate_donchian(prices)" in src


def test_slot_ids_map_matches_bot_slots():
    assert donchian_slot.SLOT_IDS == {BTC: "DONCHIAN_BTC", ETH: "DONCHIAN_ETH"}
    assert donchian_slot.SYMBOLS == [BTC, ETH]
    # sidecar names must NOT collide with the trading_state_* dashboard glob
    assert not os.path.basename(donchian_slot.STATE_FILE).startswith("trading_state")
    for p in donchian_slot.SIGNAL_FILES.values():
        assert not os.path.basename(p).startswith("trading_state")


# ── bot orchestration on a bare bot (paper book, no network) ───────────────

def _make_donchian_slot(slot_id="DONCHIAN_BTC", paper=True):
    return StrategySlot(slot_id=slot_id, strategy_name="donchian_ensemble",
                        timeframe="1d", max_positions=1, capital_pct=0.0,
                        paper_mode=paper, loss_cap_usdt=-999.0,
                        kelly_min_trades=10**9, durable_trail_enabled=False)


def _bare_bot(slots, state=None):
    import bot as botmod
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = slots
    b._donchian_state = state or donchian_slot.load_state()
    b._donchian_live_warned = {}
    b.cycle_count = 7
    return b


class FakeExchange:
    def __init__(self, df=None, ticker_price=None):
        self.df = df
        self.ticker_price = ticker_price
        self.calls = []

    def get_ohlcv(self, symbol, timeframe, limit=100):
        self.calls.append(("get_ohlcv", symbol, timeframe, limit))
        return self.df

    def get_ticker(self, symbol):
        self.calls.append(("get_ticker", symbol))
        if self.ticker_price is None:
            return None
        return {"last": self.ticker_price}


def _daily_df(n=460, start="2024-01-01", ret=0.001):
    closes = [100.0 * ((1 + ret) ** i) for i in range(n)]
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({"close": closes}, index=idx)


def test_daily_eval_bootstraps_and_opens_paper_position(sandbox):
    """Fresh state + 460 complete bars: bootstrap folds the whole window
    (all 9 models long on the monotonic series, vol capped -> w=2.0), the
    paper book opens BASE_NOTIONAL x w with 1x semantics (margin == notional,
    no SL, no TP), the day stamps, and the replica record lands."""
    slot = _make_donchian_slot()
    b = _bare_bot([slot])
    df = _daily_df()
    b.exchange = FakeExchange(df=df)
    today = donchian_slot.utc_date_str()
    st = b._donchian_state[BTC]
    b._donchian_daily_eval(slot, BTC, st, today, {BTC: 158.0})
    assert st["w"] == pytest.approx(2.0)
    assert st["submodel_pos"] == [1] * N
    assert st["last_eval_utc_date"] == today
    pos = slot.risk.positions[BTC]
    notional = donchian_slot.BASE_NOTIONAL_USDT * 2.0
    assert pos.margin == pytest.approx(notional)          # 1x: margin == notional
    assert pos.amount == pytest.approx(notional / 158.0)
    assert pos.stop_loss == 0.0                           # close-only daily stops
    assert pos.take_profit is None                        # spec: no TP
    with open(donchian_slot.SIGNAL_FILES[BTC]) as f:
        days = json.load(f)["days"]
    assert days[-1]["w"] == pytest.approx(2.0)
    assert "bootstrap" in days[-1]["note"]
    with open(donchian_slot.STATE_FILE) as f:             # fold persisted to disk
        assert json.load(f)[BTC]["last_eval_utc_date"] == today


def test_evaluate_donchian_skips_already_stamped_day(sandbox):
    slot_b = _make_donchian_slot("DONCHIAN_BTC")
    slot_e = _make_donchian_slot("DONCHIAN_ETH")
    b = _bare_bot([slot_b, slot_e])
    b.exchange = FakeExchange(df=None)
    today = donchian_slot.utc_date_str()
    for sym in donchian_slot.SYMBOLS:
        b._donchian_state[sym]["last_eval_utc_date"] = today
    b._evaluate_donchian({})
    assert b.exchange.calls == []                         # once-per-UTC-day guard


def test_daily_eval_insufficient_history_no_stamp(sandbox):
    slot = _make_donchian_slot()
    b = _bare_bot([slot])
    b.exchange = FakeExchange(df=_daily_df(n=100))        # < MIN_BARS (450)
    st = b._donchian_state[BTC]
    b._donchian_daily_eval(slot, BTC, st, donchian_slot.utc_date_str(), {BTC: 100.0})
    assert st["last_eval_utc_date"] is None               # retries next cycle
    assert st["last_close_date"] is None                  # nothing folded
    assert BTC not in slot.risk.positions


def test_daily_eval_no_price_retries_then_stop_tag_survives(sandbox):
    """The stop_fired latch: a crash close stops every model out, but the
    price fetch fails that cycle -> the fold persists, the day does NOT stamp,
    stop_fired_pending latches. The retry (advance_state returns nothing new)
    must still close the book with the donchian_stop tag, then stamp."""
    slot = _make_donchian_slot()
    b = _bare_bot([slot])
    df = _daily_df()
    b.exchange = FakeExchange(df=df)
    st = b._donchian_state[BTC]
    day1 = "2098-01-01"
    b._donchian_daily_eval(slot, BTC, st, day1, {BTC: 158.0})
    assert BTC in slot.risk.positions                     # long after bootstrap

    # next day: crash close below every ratcheting stop, but no price
    crash = df["close"].iloc[-1] * 0.5
    idx2 = df.index.append(pd.DatetimeIndex([df.index[-1] + pd.Timedelta(days=1)]))
    df2 = pd.DataFrame({"close": list(df["close"]) + [crash]}, index=idx2)
    b.exchange = FakeExchange(df=df2, ticker_price=None)
    day2 = "2098-01-02"
    b._donchian_daily_eval(slot, BTC, st, day2, {})
    assert st["w"] == 0.0                                 # fold happened
    assert st["stop_fired_pending"] is True               # latched
    assert st["last_eval_utc_date"] == day1               # day NOT stamped
    assert BTC in slot.risk.positions                     # book not yet synced

    # retry with a price: position closes as donchian_stop, latch clears
    b._donchian_daily_eval(slot, BTC, st, day2, {BTC: float(crash)})
    assert BTC not in slot.risk.positions
    assert slot.risk.closed_trades[-1]["exit_reason"] == "donchian_stop"
    assert st["stop_fired_pending"] is False
    assert st["last_eval_utc_date"] == day2


def test_adjust_position_signal_exit_vs_donchian_stop_tags(sandbox):
    slot = _make_donchian_slot()
    b = _bare_bot([slot])
    today = donchian_slot.utc_date_str()
    assert b._donchian_adjust_position(slot, BTC, 0.0, 100.0, False, today) \
        == "flat — no position"
    b._donchian_open_paper(slot, BTC, 100.0, 150.0, 1.5)
    note = b._donchian_adjust_position(slot, BTC, 0.0, 100.0, False, today)
    assert note == "closed (signal_exit)"
    assert slot.risk.closed_trades[-1]["exit_reason"] == "signal_exit"
    b._donchian_open_paper(slot, BTC, 100.0, 150.0, 1.5)
    note = b._donchian_adjust_position(slot, BTC, 0.0, 100.0, True, today)
    assert note == "closed (donchian_stop)"
    assert slot.risk.closed_trades[-1]["exit_reason"] == "donchian_stop"


def test_adjust_position_rebalance_close_and_reopen(sandbox):
    slot = _make_donchian_slot()
    b = _bare_bot([slot])
    today = donchian_slot.utc_date_str()
    b._donchian_open_paper(slot, BTC, 100.0, 200.0, 2.0)
    # unchanged weight -> hold, no paper churn
    note = b._donchian_adjust_position(slot, BTC, 2.0, 105.0, False, today)
    assert note.startswith("holding")
    assert slot.risk.closed_trades == []
    # w 2.0 -> 1.0: close-and-reopen at the new notional
    note = b._donchian_adjust_position(slot, BTC, 1.0, 105.0, False, today)
    assert "rebalanced" in note
    assert slot.risk.closed_trades[-1]["exit_reason"] == "donchian_rebalance"
    pos = slot.risk.positions[BTC]
    assert pos.margin == pytest.approx(100.0)
    assert pos.amount == pytest.approx(100.0 / 105.0)
    assert pos.entry_price == pytest.approx(105.0)


def test_adjust_position_live_mode_places_no_orders(sandbox):
    """Live execution is a spec non-goal: a promoted slot must never place
    orders from this path — book untouched, one warn per day per slot."""
    slot = _make_donchian_slot(paper=False)
    b = _bare_bot([slot])
    b.exchange = FakeExchange()                           # any call would be a bug
    today = donchian_slot.utc_date_str()
    note = b._donchian_adjust_position(slot, BTC, 1.0, 100.0, False, today)
    assert "LIVE mode unsupported" in note
    assert b._donchian_live_warned["DONCHIAN_BTC"] == today
    assert b.exchange.calls == []
    assert BTC not in slot.risk.positions


def test_adjust_position_disabled_slot_no_entry(sandbox):
    slot = _make_donchian_slot()
    slot.enabled = False
    b = _bare_bot([slot])
    today = donchian_slot.utc_date_str()
    note = b._donchian_adjust_position(slot, BTC, 1.0, 100.0, False, today)
    assert "disabled" in note
    assert BTC not in slot.risk.positions


def test_no_kelly_no_demote_rails(sandbox):
    """-999 loss cap + kelly@1e9: paper losses inside the spec's -$15 kill
    line must not trip the slot's own auto-demote rails."""
    slot = _make_donchian_slot(paper=False)
    slot.set_live(capital_pct=0.0)
    import time as _time
    slot.risk.closed_trades = [
        {"pnl_usdt": -2.0, "mode": "live", "closed_at": _time.time()}
        for _ in range(7)]
    demote, _ = slot.should_auto_demote()
    assert demote is False
    assert slot.is_killed is False
