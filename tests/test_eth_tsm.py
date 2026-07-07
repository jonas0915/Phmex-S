"""ETH-TSM-28 slot tests (2026-07-06 build).

Fixture-based, no network: pure signal math (tercile boundary, history
exclusion, incomplete-candle drop), min-hold / replica behavior, rails
opt-out (no Kelly / no loss-cap demote), main-bot ETH ownership lock +
Telegram dedup, paper entry/disaster-stop, live-entry merge guard +
leverage sequencing, and the adjudicator kill-criteria grader.
"""
import datetime as dt
import os
import sys
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import risk_manager
import strategy_slot
import tsm_slot
from strategy_slot import StrategySlot

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))
from lab_adjudicator import adjudicate as adj  # noqa: E402

SYM = tsm_slot.TSM_SYMBOL


# ── pure signal math ───────────────────────────────────────────────────────

def test_tercile_boundary_is_inclusive():
    """Declared interpretation: current >= 66.667th pctile of PRIOR returns
    => top tercile => ON. Boundary tie counts as ON."""
    # lookback=1 => returns are consecutive ratios; history = first 4 returns
    hist_rets = [0.00, 0.02, 0.05, 0.10]
    thr = float(np.percentile(hist_rets, tsm_slot.TSM_TERCILE_PCTL))
    closes = [1.0]
    for r in hist_rets:
        closes.append(closes[-1] * (1 + r))
    closes_on = closes + [closes[-1] * (1 + thr)]           # current == threshold
    sig = tsm_slot.compute_signal(closes_on, lookback=1, min_history=4)
    assert sig["signal_on"] is True
    assert sig["threshold"] == pytest.approx(thr)
    closes_off = closes + [closes[-1] * (1 + thr - 1e-6)]   # just below
    sig2 = tsm_slot.compute_signal(closes_off, lookback=1, min_history=4)
    assert sig2["signal_on"] is False


def test_history_excludes_current_observation():
    hist_rets = [0.01, 0.02, 0.03, 0.04, 0.05]
    closes = [1.0]
    for r in hist_rets:
        closes.append(closes[-1] * (1 + r))
    closes.append(closes[-1] * 2.0)  # current = +100%, would drag the pctile up
    sig = tsm_slot.compute_signal(closes, lookback=1, min_history=5)
    assert sig["threshold"] == pytest.approx(
        float(np.percentile(hist_rets, tsm_slot.TSM_TERCILE_PCTL)))
    assert sig["n_history"] == 5
    assert sig["signal_on"] is True


def test_insufficient_history_fails_closed():
    assert tsm_slot.compute_signal([1.0] * 30) is None  # default min_history=90
    assert tsm_slot.compute_signal([], lookback=1, min_history=3) is None


def test_complete_daily_closes_drops_in_progress_candle():
    now = dt.datetime(2026, 7, 6, 13, 0, tzinfo=dt.timezone.utc)
    idx = pd.to_datetime(["2026-07-03", "2026-07-04", "2026-07-05", "2026-07-06"])
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]}, index=idx)
    closes = tsm_slot.complete_daily_closes(df, now_utc=now)
    assert closes == [1.0, 2.0, 3.0]  # today's (in-progress) candle dropped


def test_min_hold_five_days():
    assert tsm_slot.held_days("2026-07-01", "2026-07-06") == 5
    assert tsm_slot.min_hold_met("2026-07-01", "2026-07-06") is True
    assert tsm_slot.min_hold_met("2026-07-02", "2026-07-06") is False
    assert tsm_slot.min_hold_met(None, "2026-07-06") is True  # never trap a position


def test_replica_enters_holds_through_min_hold_then_exits():
    st = tsm_slot.default_state()
    rep = tsm_slot.advance_replica(st, True, "2026-07-01")
    assert rep["position"] and rep["entry_date"] == "2026-07-01"
    rep = tsm_slot.advance_replica(st, False, "2026-07-03")   # day 2: min-hold holds
    assert rep["position"] is True
    rep = tsm_slot.advance_replica(st, False, "2026-07-06")   # day 5: exits
    assert rep["position"] is False and rep["entry_date"] is None


# ── slot construction / rails opt-out ─────────────────────────────────────

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    monkeypatch.setattr(risk_manager, "PERSISTENCE_FILE", str(tmp_path / "trading_state.json"))
    monkeypatch.setattr(tsm_slot, "STATE_FILE", str(tmp_path / "eth_tsm_28_signal.json"))
    return tmp_path


def _make_tsm_strategy_slot(paper=True):
    return StrategySlot(slot_id=tsm_slot.TSM_SLOT_ID, strategy_name="eth_tsm_28",
                        timeframe="1d", max_positions=1, capital_pct=0.0,
                        paper_mode=paper, loss_cap_usdt=-999.0,
                        kelly_min_trades=10**9, durable_trail_enabled=False)


def test_bot_slot_config_matches_rails_optout():
    """The slot wired into bot.py must carry the rails opt-out and a strategy
    name that is NOT in STRATEGIES (that absence is what keeps every scalper
    exit path away from the position — _evaluate_slots skips the whole slot)."""
    import ast
    from strategies import STRATEGIES
    src = open(os.path.join(BOT_DIR, "bot.py")).read()
    assert 'strategy_name="eth_tsm_28"' in src
    assert "eth_tsm_28" not in STRATEGIES
    assert "loss_cap_usdt=-999.0" in src
    assert "kelly_min_trades=10**9" in src
    ast.parse(src)  # bot.py stays parseable


def test_no_kelly_no_demote_rails(sandbox):
    slot = _make_tsm_strategy_slot(paper=False)
    slot.set_live(capital_pct=0.0)
    # -$9 of live losses: inside the -$10 adjudicator line, and the slot's own
    # rails (-999 cap, kelly@1e9) must NOT demote
    slot.risk.closed_trades = [
        {"pnl_usdt": -1.5, "mode": "live", "closed_at": time.time()} for _ in range(6)]
    demote, _ = slot.should_auto_demote()
    assert demote is False
    # kill switch (neg Kelly @50 trades) can't arm inside the test horizon either
    assert slot.is_killed is False


def test_fixed_sizing_is_not_kelly():
    """Sizing must be the fixed 0.01 ETH, independent of any Kelly output."""
    assert tsm_slot.TSM_AMOUNT_ETH == 0.01
    src = open(os.path.join(BOT_DIR, "bot.py")).read()
    block = src.split("def _tsm_try_entry")[1].split("def _close_slot_position")[0]
    assert "calculate_kelly_margin" not in block
    assert "TSM_AMOUNT_ETH" in block


# ── ownership lock + telegram dedup ────────────────────────────────────────

def _bare_bot(slots, state=None, entry_active=False):
    import bot as botmod
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = slots
    b._tsm_state = state or tsm_slot.default_state()
    b._tsm_entry_active = entry_active
    b._tsm_ownership_notified = {}
    b.risk = SimpleNamespace(positions={}, _drawdown_pause_until=0.0)
    b.cycle_count = 7
    b._leverage_set = set()
    b._last_entry_time = 0.0
    return b


def test_main_bot_skips_eth_while_slot_owns(sandbox):
    slot = _make_tsm_strategy_slot(paper=False)
    slot.set_live(capital_pct=0.0)
    slot.risk.positions[SYM] = SimpleNamespace(side="long")
    b = _bare_bot([slot])
    assert b._tsm_locks_symbol(SYM) is not None          # live holding → locked
    assert b._tsm_locks_symbol("BTC/USDT:USDT") is None  # other symbols untouched


def test_no_lock_in_paper_mode_or_when_flat(sandbox):
    slot = _make_tsm_strategy_slot(paper=True)
    slot.risk.positions[SYM] = SimpleNamespace(side="long")
    b = _bare_bot([slot])
    assert b._tsm_locks_symbol(SYM) is None  # paper position has no exchange footprint
    slot2 = _make_tsm_strategy_slot(paper=True)
    b2 = _bare_bot([slot2])
    assert b2._tsm_locks_symbol(SYM) is None


def test_lock_from_leverage_flag_and_entry_active(sandbox):
    slot = _make_tsm_strategy_slot(paper=True)
    st = tsm_slot.default_state()
    st["leverage_3x_set"] = True
    b = _bare_bot([slot], state=st)
    assert "leverage" in b._tsm_locks_symbol(SYM)
    st["leverage_3x_set"] = False
    b2 = _bare_bot([slot], entry_active=True)
    assert "in flight" in b2._tsm_locks_symbol(SYM)


def test_ownership_notify_dedup_per_day(sandbox, monkeypatch):
    import bot as botmod
    sent = []
    monkeypatch.setattr(botmod.notifier, "send", lambda m: sent.append(m))
    b = _bare_bot([_make_tsm_strategy_slot()])
    b._tsm_notify_ownership("main_skip", "main-bot ETH entry skipped (test)")
    b._tsm_notify_ownership("main_skip", "main-bot ETH entry skipped (test)")
    assert len(sent) == 1  # same kind, same day → one Telegram
    b._tsm_notify_ownership("tsm_skip", "TSM entry skipped (main bot holds ETH)")
    assert len(sent) == 2  # different kind still alerts


# ── paper entry / disaster stop / signal exit ─────────────────────────────

def _daily_df(rets, start="2024-01-01"):
    closes = [100.0]
    for r in rets:
        closes.append(closes[-1] * (1 + r))
    idx = pd.date_range(start, periods=len(closes), freq="D")
    return pd.DataFrame({"close": closes}, index=idx)


class FakeExchange:
    def __init__(self, df=None, open_positions=None):
        self.df = df
        self.open_positions = open_positions if open_positions is not None else []
        self.calls = []
        self.client = SimpleNamespace(fetch_positions=lambda syms=None: [])

    def get_ohlcv(self, symbol, timeframe, limit=100):
        self.calls.append(("get_ohlcv", symbol, timeframe, limit))
        return self.df if symbol == SYM else None

    def get_ticker(self, symbol):
        return {"last": float(self.df["close"].iloc[-1])} if self.df is not None else None

    def get_open_positions(self):
        self.calls.append(("get_open_positions",))
        return self.open_positions

    def set_symbol_leverage(self, symbol, leverage):
        self.calls.append(("set_symbol_leverage", symbol, leverage))

    def open_long(self, symbol, margin, price, patience_s=20.0):
        self.calls.append(("open_long", symbol, margin, price))
        return {"symbol": symbol, "id": "ord1", "average": price, "filled": 0.01}

    def open_long_market(self, symbol, amount):
        self.calls.append(("open_long_market", symbol, amount))
        return {"symbol": symbol, "id": "ord2", "average": None, "filled": amount}

    def place_stop_loss(self, symbol, side, amount, sl_price):
        self.calls.append(("place_stop_loss", symbol, side, amount, sl_price))
        return "sl123"

    def cancel_open_orders(self, symbol):
        self.calls.append(("cancel_open_orders", symbol))

    def close_long(self, symbol, amount, urgent=True):
        self.calls.append(("close_long", symbol, amount, urgent))
        return {"symbol": symbol, "id": "cls1", "average": None}

    def pop_reduce_only_abort(self, symbol):
        return False

    def extract_order_fee(self, order, symbol=None):
        return 0.01


def test_paper_entry_fixed_size_stop_and_no_tp(sandbox):
    slot = _make_tsm_strategy_slot(paper=True)
    b = _bare_bot([slot])
    b.exchange = FakeExchange()
    st = b._tsm_state
    st.update({"entry_pending_date": "2026-07-06", "ret_28d": 0.12})
    b._tsm_try_entry(slot, st, "2026-07-06", {SYM: 1770.0})
    pos = slot.risk.positions[SYM]
    assert pos.amount == pytest.approx(0.01)
    assert pos.stop_loss == pytest.approx(1770.0 * 0.92)   # −8% disaster stop
    assert pos.take_profit is None                          # spec: NO TP
    assert st["entry_date"] == "2026-07-06"
    assert st["entry_pending_date"] is None
    assert st["leverage_3x_set"] is False                   # paper never touches leverage


def test_paper_disaster_stop_closes_position(sandbox):
    slot = _make_tsm_strategy_slot(paper=True)
    b = _bare_bot([slot])
    b.exchange = FakeExchange()
    st = b._tsm_state
    st.update({"entry_pending_date": "2026-07-01", "ret_28d": 0.10})
    b._tsm_try_entry(slot, st, "2026-07-01", {SYM: 2000.0})
    st["last_eval_date"] = tsm_slot.utc_date_str()  # suppress daily eval in this cycle
    b._evaluate_eth_tsm({SYM: 2000.0 * 0.91})       # below the −8% stop
    assert SYM not in slot.risk.positions
    assert slot.risk.closed_trades[-1]["exit_reason"] == "disaster_stop"
    assert st["entry_date"] is None


def test_daily_eval_signal_exit_respects_min_hold(sandbox):
    """Signal OFF at day 2 → hold; signal OFF at day 5+ → exit_pending."""
    slot = _make_tsm_strategy_slot(paper=True)
    b = _bare_bot([slot])
    # 460 flat days then a −20% crash over the last 28 → bottom tercile (OFF)
    rets = [0.001] * 430 + [-0.008] * 28
    b.exchange = FakeExchange(df=_daily_df(rets))
    slot.risk.positions[SYM] = SimpleNamespace(side="long")
    st = b._tsm_state
    today = tsm_slot.utc_date_str()
    d = dt.date.fromisoformat(today)
    st["entry_date"] = (d - dt.timedelta(days=2)).isoformat()
    b._tsm_daily_eval(slot, st, today, {})
    assert st["exit_pending"] is False           # min-hold not met → hold
    assert st["last_eval_date"] == today
    st["last_eval_date"] = None                  # re-eval with 6-day-old entry
    st["entry_date"] = (d - dt.timedelta(days=6)).isoformat()
    b._tsm_daily_eval(slot, st, today, {})
    assert st["exit_pending"] is True            # min-hold met + signal off → exit
    assert st["days"][-1]["signal_on"] is False
    assert st["days"][-1]["replica_position"] in (True, False)


def test_daily_eval_signal_on_sets_entry_pending(sandbox):
    slot = _make_tsm_strategy_slot(paper=True)
    b = _bare_bot([slot])
    rets = [0.0] * 430 + [0.01] * 28             # +32% last 28d → top tercile
    b.exchange = FakeExchange(df=_daily_df(rets))
    st = b._tsm_state
    today = tsm_slot.utc_date_str()
    b._tsm_daily_eval(slot, st, today, {})
    assert st["signal_on"] is True
    assert st["entry_pending_date"] == today
    assert st["days"][-1]["actual_position"] is False


def test_live_tsm_skips_day_when_main_bot_holds_eth(sandbox, monkeypatch):
    import bot as botmod
    sent = []
    monkeypatch.setattr(botmod.notifier, "send", lambda m: sent.append(m))
    slot = _make_tsm_strategy_slot(paper=False)
    slot.set_live(capital_pct=0.0)
    b = _bare_bot([slot])
    rets = [0.0] * 430 + [0.01] * 28
    b.exchange = FakeExchange(df=_daily_df(rets))
    b.risk.positions[SYM] = SimpleNamespace(side="short")   # main bot owns ETH
    st = b._tsm_state
    today = tsm_slot.utc_date_str()
    b._tsm_daily_eval(slot, st, today, {})
    assert st["entry_pending_date"] is None                 # skipped, no retry today
    assert "SKIP-DAY" in st["days"][-1]["note"]
    assert any("TSM entry skipped" in m for m in sent)      # owner sees it


# ── live entry: merge guard + leverage sequencing ─────────────────────────

def test_live_entry_aborts_on_unattributed_exchange_eth(sandbox, monkeypatch):
    """Belt-and-suspenders: exchange shows an ETH position not owned by the
    slot → NO leverage call, NO order, day skipped, Telegram sent."""
    import bot as botmod
    sent = []
    monkeypatch.setattr(botmod.notifier, "send", lambda m: sent.append(m))
    slot = _make_tsm_strategy_slot(paper=False)
    slot.set_live(capital_pct=0.0)
    b = _bare_bot([slot])
    b.exchange = FakeExchange(open_positions=[
        {"symbol": SYM, "side": "long", "entry_price": 1700.0, "amount": 0.05, "margin": 8.5}])
    st = b._tsm_state
    today = tsm_slot.utc_date_str()
    st.update({"entry_pending_date": today, "ret_28d": 0.1})
    b._tsm_try_entry(slot, st, today, {SYM: 1770.0})
    assert st["entry_pending_date"] is None
    assert SYM not in slot.risk.positions
    called = [c[0] for c in b.exchange.calls]
    assert "set_symbol_leverage" not in called
    assert "open_long" not in called and "open_long_market" not in called
    assert any("ABORTED" in m for m in sent)


def test_live_entry_sets_3x_before_order_and_places_stop_only(sandbox, monkeypatch):
    import bot as botmod
    monkeypatch.setattr(botmod.notifier, "send", lambda m: None)
    monkeypatch.setattr(botmod.Phmex2Bot, "_extract_fill_price",
                        lambda self, order, fallback, is_exit=False: fallback)
    slot = _make_tsm_strategy_slot(paper=False)
    slot.set_live(capital_pct=0.0)
    b = _bare_bot([slot])
    b.exchange = FakeExchange(open_positions=[])
    st = b._tsm_state
    today = tsm_slot.utc_date_str()
    st.update({"entry_pending_date": today, "ret_28d": 0.1})
    b._tsm_try_entry(slot, st, today, {SYM: 1770.0})
    names = [c[0] for c in b.exchange.calls]
    assert names.index("set_symbol_leverage") < names.index("open_long")  # 3x FIRST
    lev_call = next(c for c in b.exchange.calls if c[0] == "set_symbol_leverage")
    assert lev_call[2] == tsm_slot.TSM_LEVERAGE                            # 3x
    assert st["leverage_3x_set"] is True                                   # flag persisted
    pos = slot.risk.positions[SYM]
    assert pos.amount == pytest.approx(0.01)
    assert pos.take_profit is None
    assert pos.sl_order_id == "sl123"
    assert pos.exchange_sl_price == pytest.approx(1770.0 * 0.92)
    sl_call = next(c for c in b.exchange.calls if c[0] == "place_stop_loss")
    assert sl_call[4] == pytest.approx(1770.0 * 0.92)
    assert pos.margin == pytest.approx(0.01 * 1770.0 / 3)                  # ≈ $5.90


def test_leverage_restore_after_flat(sandbox):
    slot = _make_tsm_strategy_slot(paper=False)
    slot.set_live(capital_pct=0.0)
    b = _bare_bot([slot])
    b.exchange = FakeExchange(df=_daily_df([0.0] * 430 + [0.01] * 28))
    st = b._tsm_state
    st["leverage_3x_set"] = True
    st["last_eval_date"] = tsm_slot.utc_date_str()
    st["signal_on"] = False
    b._evaluate_eth_tsm({})           # flat + flag set → restore fires
    lev_calls = [c for c in b.exchange.calls if c[0] == "set_symbol_leverage"]
    assert lev_calls and lev_calls[0][2] == 10  # Config.LEVERAGE
    assert st["leverage_3x_set"] is False


# ── adjudicator registration + kill criteria ──────────────────────────────

def _tsm_cfg():
    return adj.EXPERIMENTS["eth_tsm_28"]


def test_adjudicator_registered_and_wired():
    cfg = _tsm_cfg()
    assert cfg["kill_net_usd"] == -10.0
    assert cfg["kill_disaster_stops"] == 2
    assert cfg["tracking_err_daily"] == pytest.approx(0.001)
    assert str(adj.TSM_SIGNAL_FILE).endswith("eth_tsm_28_signal.json")
    src = open(os.path.join(BOT_DIR, "scripts", "lab_adjudicator", "adjudicate.py")).read()
    assert "grade_eth_tsm(load_json(TSM_STATE_FILE" in src  # in build_digest


def test_grader_n0_honesty():
    r = adj.grade_eth_tsm({}, {}, _tsm_cfg())
    assert r["status"] == adj.WATCH and "n=0" in r["note"]


def test_grader_net_kill_line():
    state = {"closed_trades": [
        {"mode": "live", "net_pnl": -6.0, "exit_reason": "signal_exit"},
        {"mode": "live", "net_pnl": -4.5, "exit_reason": "signal_exit"}]}
    r = adj.grade_eth_tsm(state, {}, _tsm_cfg())
    assert r["status"] == adj.REVERT and "kill line" in r["note"]


def test_grader_two_disaster_stops_trip():
    state = {"closed_trades": [
        {"mode": "live", "net_pnl": -1.4, "exit_reason": "exchange_close"},
        {"mode": "live", "net_pnl": -1.5, "exit_reason": "exchange_close"},
        {"mode": "live", "net_pnl": +2.0, "exit_reason": "signal_exit"}]}
    r = adj.grade_eth_tsm(state, {}, _tsm_cfg())
    assert r["status"] == adj.REVERT and "disaster-stop" in r["note"]
    assert r["disaster_stops"] == 2


def test_grader_tracking_error_needs_full_window():
    def _days(n, diverge):
        out, px = [], 100.0
        for i in range(n):
            px *= 1.02  # 2%/day moves
            out.append({"date": f"2026-08-{i+1:02d}", "close": px,
                        "replica_position": True,
                        "actual_position": (not diverge)})
        return out
    cfg = _tsm_cfg()
    # divergent but only 5 days → window not full → no REVERT yet
    r = adj.grade_eth_tsm({}, {"days": _days(5, diverge=True)}, cfg)
    assert r["status"] == adj.WATCH and r["tracking_window_full"] is False
    # divergent over a full 15-day window → REVERT
    r2 = adj.grade_eth_tsm({}, {"days": _days(15, diverge=True)}, cfg)
    assert r2["status"] == adj.REVERT and "tracking error" in r2["note"]
    # perfectly tracking over the same window → WATCH
    r3 = adj.grade_eth_tsm({}, {"days": _days(15, diverge=False)}, cfg)
    assert r3["status"] == adj.WATCH and r3["divergence_days_window"] == 0


def test_digest_includes_tsm_line():
    line = adj._line_tsm(adj.grade_eth_tsm({}, {}, _tsm_cfg()))
    assert "[eth_tsm_28]" in line and "kill -10" in line
