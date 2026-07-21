"""HTF_L2 slot (2026-07-18, action plan D1; born HTF_L2_PAPER, renamed
HTF_L2 at the 2026-07-20 go-live).

htf_l2_anticipation resurrected as a slot while the main path stays
HALTED (.halt_main_entries). The slot runs the full generic scalper path
(slot SL/TP, trend-flip, hard-240) with an ACTIVE thin-tape ∧ ADX>=35 gate
(F5 forward test) and an ensemble conf>=4 hard block. Kill criteria are
ADJUDICATOR-graded (report-only until the owner sets them); rails opted out.
"""
import inspect
import json
import os
import time
from types import SimpleNamespace

import pandas as pd
import pytest

import bot as botmod
import risk_manager
import strategy_slot
from config import Config
from risk_manager import RiskManager
from strategies import STRATEGIES
from strategy_slot import StrategySlot

SYM = "BTC/USDT:USDT"


# ── fixtures / builders ────────────────────────────────────────────────────

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Isolate every state/sidecar/log write into tmp_path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_entry", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_exit", lambda *a, **k: None)
    return tmp_path


def _df_5m(n=60):
    """5m frame that satisfies htf_l2_anticipation's LONG setup at close=100."""
    rows = {
        "close": [100.0] * n, "open": [100.0] * n,
        "high": [100.5] * n, "low": [99.5] * n,
        "volume": [1000.0] * n,
        "rsi": [50.0] * n, "vwap": [99.5] * n,
        "ema_9": [100.4] * n, "ema_21": [100.2] * n, "ema_50": [99.0] * n,
        "ema_200": [95.0] * n, "adx": [30.0] * n, "atr": [0.5] * n,
    }
    return pd.DataFrame(rows)


def _htf_df(adx=25.0, flipped=False, n=40):
    """1h frame: uptrend (ema21>ema50, close>ema50) unless flipped."""
    e21, e50 = (100.0, 105.0) if flipped else (105.0, 100.0)
    return pd.DataFrame({
        "close": [110.0] * n, "ema_21": [e21] * n, "ema_50": [e50] * n,
        "adx": [adx] * n,
    })


def _flow(tc=80):
    return {"buy_ratio": 0.62, "cvd_slope": 0.5, "divergence": None,
            "large_trade_bias": 0.0, "trade_count": tc}


def _ob():
    return {"imbalance": 0.1, "bid_walls": [], "ask_walls": [],
            "spread_pct": 0.05, "bid_depth_usdt": 200000.0,
            "ask_depth_usdt": 100000.0, "illiquid": False}


def _paper_slot():
    return StrategySlot(
        slot_id="HTF_L2", strategy_name="htf_l2_anticipation",
        timeframe="5m", max_positions=2, capital_pct=0.0, paper_mode=True,
        trade_amount_usdt=None, loss_cap_usdt=-999.0, kelly_min_trades=10**9,
        durable_trail_enabled=False,
        sl_percent=Config.HTF_L2_SL_PCT, tp_percent=Config.HTF_L2_TP_PCT,
    )


def _bare_bot(slot, htf_adx=25.0, tc=80, conf=5, monkeypatch=None):
    """Minimal bot able to run _evaluate_slots for one paper slot."""
    df, htf, flow, ob = _df_5m(), _htf_df(adx=htf_adx), _flow(tc=tc), _ob()
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = [slot]
    b.risk = SimpleNamespace(positions={}, _drawdown_pause_until=0.0)
    b.cycle_count = 5
    b._last_entry_time = 0.0
    b._htf_cache = {}
    b._ws_feed = SimpleNamespace(is_stale=lambda s: True,
                                 get_order_flow=lambda s: flow)
    b.exchange = SimpleNamespace(
        get_ohlcv=lambda s, tf, limit=None: df,
        get_order_book=lambda s, depth=None: ob,
    )
    b._fetch_htf_data = lambda s: htf
    b._compute_confidence = lambda *a, **k: (conf, ["l"] * conf)
    if monkeypatch is not None:
        # supply pre-baked indicator columns — the pipeline would recompute them
        monkeypatch.setattr(botmod, "add_all_indicators", lambda d: d)
    return b


def _run_entries(b):
    b._evaluate_slots([SYM], {SYM: 100.0})


def _reset_state(sandbox):
    """Drop the slot's persisted book so a fresh StrategySlot starts empty
    (state files are keyed by slot_id and reload on construction)."""
    for name in ("trading_state_HTF_L2.json",
                 "trading_state_HTF_L2_blocked.json"):
        p = sandbox / name
        if p.exists():
            p.unlink()


# ── 1-2: registration ──────────────────────────────────────────────────────

def test_slot_registered_paper(sandbox):
    slot = botmod.Phmex2Bot._build_htf_l2_slot()
    assert slot is not None
    assert slot.slot_id == "HTF_L2"
    assert slot.paper_mode is True
    assert slot.strategy_name == "htf_l2_anticipation"
    assert slot.strategy_name in STRATEGIES          # generic scalper path runs
    assert slot.loss_cap_usdt == -5.0                # hard rail: auto-demote at -$5 (owner go-live 7/20)
    assert slot.kelly_min_trades == 10**9
    assert slot.durable_trail_enabled is False
    assert slot.timeframe == "5m" and slot.max_positions == 2
    assert slot.risk.state_file.endswith("trading_state_HTF_L2.json")
    # wired into __init__ right after the slots literal
    src = inspect.getsource(botmod.Phmex2Bot.__init__)
    assert "_build_htf_l2_slot()" in src
    assert "self.slots.append" in src


def test_env_flag_removes_slot(sandbox, monkeypatch):
    monkeypatch.setattr(Config, "HTF_L2_ENABLED", False)
    assert botmod.Phmex2Bot._build_htf_l2_slot() is None
    monkeypatch.setattr(Config, "HTF_L2_ENABLED", True)
    assert botmod.Phmex2Bot._build_htf_l2_slot() is not None


# ── 3: flow plumbing ───────────────────────────────────────────────────────

def test_flow_reaches_signal(sandbox, monkeypatch):
    seen = {}

    def spy(df, ob=None, htf_df=None, flow=None):
        seen["flow"] = flow
        from strategies import Signal, TradeSignal
        return TradeSignal(Signal.HOLD, "spy", 0.0)

    monkeypatch.setitem(botmod.STRATEGIES, "htf_l2_anticipation", spy)
    b = _bare_bot(_paper_slot(), monkeypatch=monkeypatch)
    _run_entries(b)
    assert seen.get("flow") is not None
    assert seen["flow"]["trade_count"] == 80


# ── 4-6: ACTIVE thin∧ADX gate ─────────────────────────────────────────────

def test_thin_adx_blocks_paper_entry(sandbox, monkeypatch):
    slot = _paper_slot()
    b = _bare_bot(slot, htf_adx=40.0, tc=12, monkeypatch=monkeypatch)
    _run_entries(b)
    assert SYM not in slot.risk.positions
    assert slot.blocked_counts.get("thin_adx") == 1
    lines = [json.loads(l) for l in open(sandbox / "logs" / "gotAway.jsonl")]
    assert any(r["reason"] == "thin_adx_slot" for r in lines)


def test_thin_adx_allows_active_tape(sandbox, monkeypatch):
    slot = _paper_slot()
    b = _bare_bot(slot, htf_adx=40.0, tc=80, monkeypatch=monkeypatch)
    _run_entries(b)
    assert SYM in slot.risk.positions


def test_thin_adx_flag_off_allows(sandbox, monkeypatch):
    monkeypatch.setattr(Config, "HTF_THIN_ADX_BLOCK_ENABLED", False)
    slot = _paper_slot()
    b = _bare_bot(slot, htf_adx=40.0, tc=12, monkeypatch=monkeypatch)
    _run_entries(b)
    assert SYM in slot.risk.positions


# ── 7-8: halt/pause interaction ────────────────────────────────────────────

def test_paper_entry_during_main_halt(sandbox, monkeypatch):
    (sandbox / ".halt_main_entries").write_text("halted 2026-07-13")
    slot = _paper_slot()
    b = _bare_bot(slot, monkeypatch=monkeypatch)
    _run_entries(b)
    assert SYM in slot.risk.positions        # slot trades through the halt
    assert b.risk.positions == {}            # main book untouched


def test_paper_entry_blocked_during_pause(sandbox, monkeypatch):
    (sandbox / ".pause_trading").write_text("paused")
    slot = _paper_slot()
    b = _bare_bot(slot, monkeypatch=monkeypatch)
    _run_entries(b)
    assert slot.risk.positions == {}


# ── 9-10: telemetry parity ─────────────────────────────────────────────────

def test_snapshot_confidence_htf_adx(sandbox, monkeypatch):
    slot = _paper_slot()
    b = _bare_bot(slot, htf_adx=25.0, conf=5, monkeypatch=monkeypatch)
    _run_entries(b)
    snap = slot.risk.positions[SYM].entry_snapshot
    assert snap["confidence"] == 5           # was hardcoded 0 pre-fix
    assert snap["htf_adx"] == 25.0           # main-path parity (bot.py:2119)
    # ensemble hard block: conf < 4 must not enter this slot
    _reset_state(sandbox)
    slot2 = _paper_slot()
    b2 = _bare_bot(slot2, htf_adx=25.0, conf=3, monkeypatch=monkeypatch)
    _run_entries(b2)
    assert SYM not in slot2.risk.positions
    assert slot2.blocked_counts.get("ensemble_confidence") == 1


def test_gate_tags_cell_tagging(sandbox, monkeypatch):
    # thin tape (allowed: adx below the block line) → sg_thin_tape tag
    slot = _paper_slot()
    b = _bare_bot(slot, htf_adx=25.0, tc=12, monkeypatch=monkeypatch)
    _run_entries(b)
    assert "sg_thin_tape" in slot.risk.positions[SYM].gate_tags
    # high ADX on active tape → sg_htf_adx_hi tag
    _reset_state(sandbox)
    slot2 = _paper_slot()
    b2 = _bare_bot(slot2, htf_adx=40.0, tc=80, monkeypatch=monkeypatch)
    _run_entries(b2)
    assert "sg_htf_adx_hi" in slot2.risk.positions[SYM].gate_tags
    # clean cell → literal "none" (distinguishable from missing telemetry)
    _reset_state(sandbox)
    slot3 = _paper_slot()
    b3 = _bare_bot(slot3, htf_adx=25.0, tc=80, monkeypatch=monkeypatch)
    _run_entries(b3)
    assert slot3.risk.positions[SYM].gate_tags == "none"


# ── 11: paper fee model ────────────────────────────────────────────────────

def test_paper_fee_model(sandbox, monkeypatch):
    monkeypatch.setattr(Config, "MAKER_FEE_PERCENT", 0.01)
    monkeypatch.setattr(Config, "TAKER_FEE_PERCENT", 0.06)
    monkeypatch.setattr(Config, "SLIPPAGE_PERCENT", 0.05)
    slot = _paper_slot()
    pos = slot.risk.open_position(SYM, 100.0, 10.0, side="long")
    notional = pos.entry_price * pos.amount
    b = object.__new__(botmod.Phmex2Bot)
    b._close_slot_position(slot, SYM, pos, 100.0, "take_profit")  # gross = 0
    t = slot.risk.closed_trades[-1]
    assert t["net_pnl"] == pytest.approx(-notional * 0.12 / 100)


# ── 12-13: per-slot SL/TP override ─────────────────────────────────────────

def test_slot_sl_tp_override(sandbox):
    rm = RiskManager(state_file="override_state.json")
    # explicit overrides, fixed-% branch
    pos = rm.open_position(SYM, 100.0, 10.0, side="long", sl_pct=2.0, tp_pct=3.0)
    assert pos.stop_loss == pytest.approx(98.0)
    assert pos.take_profit == pytest.approx(103.0)
    rm.positions.clear()
    # None → identical to Config-driven defaults
    pos_none = rm.open_position(SYM, 100.0, 10.0, side="long",
                                sl_pct=None, tp_pct=None)
    assert pos_none.stop_loss == pytest.approx(
        100.0 * (1 - Config.STOP_LOSS_PERCENT / 100))
    assert pos_none.take_profit == pytest.approx(
        100.0 * (1 + Config.TAKE_PROFIT_PERCENT / 100))
    rm.positions.clear()
    # ATR branch: override drives the floor/cap and R:R geometry
    pos_atr = rm.open_position(SYM, 100.0, 10.0, side="long", atr=0.01,
                               sl_pct=2.0, tp_pct=3.0)
    # tiny ATR → SL floored at override 2.0%
    assert pos_atr.stop_loss == pytest.approx(98.0)
    # slot wiring: both slot entry call sites pass the overrides
    src = inspect.getsource(botmod.Phmex2Bot._evaluate_slots)
    assert src.count("sl_pct=slot.sl_percent") == 2
    assert src.count("tp_pct=slot.tp_percent") == 2
    # dataclass defaults keep every other slot on Config geometry
    plain = StrategySlot(slot_id="plain_t", strategy_name="bb_mean_reversion",
                         timeframe="5m", paper_mode=True)
    assert plain.sl_percent is None and plain.tp_percent is None


def test_open_position_default_unchanged(sandbox):
    rm = RiskManager(state_file="default_state.json")
    pos = rm.open_position(SYM, 100.0, 10.0, side="short")   # no new kwargs
    assert pos.stop_loss == pytest.approx(
        100.0 * (1 + Config.STOP_LOSS_PERCENT / 100))
    assert pos.take_profit == pytest.approx(
        100.0 * (1 - Config.TAKE_PROFIT_PERCENT / 100))
    rm.positions.clear()
    # ATR branch regression: same floor/cap math as before the kwargs existed
    atr = 1.0
    pos_atr = rm.open_position(SYM, 100.0, 10.0, side="long", atr=atr)
    min_sl = 100.0 * Config.STOP_LOSS_PERCENT / 100
    max_sl = min_sl * 3
    sl_dist = max(min_sl, min(1.5 * atr, max_sl))
    max_tp = 100.0 * Config.TAKE_PROFIT_PERCENT / 100
    sl_dist = min(sl_dist, max(min_sl, max_tp / 2.0))
    tp_dist = min(sl_dist * 2.0, max_tp)
    assert pos_atr.stop_loss == pytest.approx(100.0 - sl_dist)
    assert pos_atr.take_profit == pytest.approx(100.0 + tp_dist)


# ── 14: kill sentinel stays in the paper book ──────────────────────────────

def test_kill_sentinel_paper_close_in_book(sandbox, monkeypatch):
    slot = _paper_slot()
    slot.risk.open_position(SYM, 100.0, 10.0, side="long")
    calls = []
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = [slot]
    b.exchange = SimpleNamespace(
        close_long=lambda *a, **k: calls.append("close_long"),
        close_short=lambda *a, **k: calls.append("close_short"),
        cancel_open_orders=lambda *a, **k: calls.append("cancel"),
    )
    b.ws_feed = SimpleNamespace(last_price=lambda s: (101.0, 0.0))
    b.risk = SimpleNamespace(positions={}, _drawdown_pause_until=0.0)
    b._trading_paused = False
    b._pause_logged = False
    b._halt_main_logged = False
    open(".kill_HTF_L2", "w").close()

    b._process_sentinels()

    assert calls == []                                # zero exchange calls
    assert slot.risk.positions == {}                  # closed in the paper book
    assert slot.risk.closed_trades[-1]["reason"] == "killed"
    assert slot.enabled is False
    assert not os.path.exists(".kill_HTF_L2")


# ── 15: trend-flip exit ────────────────────────────────────────────────────

def test_trend_flip_exit_fires(sandbox, monkeypatch):
    slot = _paper_slot()
    slot.risk.open_position(SYM, 100.0, 10.0, side="long", cycle=5)
    b = _bare_bot(slot, monkeypatch=monkeypatch)
    b._htf_cache = {SYM: (_htf_df(flipped=True), time.time())}
    b._evaluate_slots([], {SYM: 100.0})               # price inside SL/TP band
    assert SYM not in slot.risk.positions
    t = slot.risk.closed_trades[-1]
    assert t["reason"] == "htf_trend_flip_exit"
