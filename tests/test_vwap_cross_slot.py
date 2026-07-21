"""VWAP_CROSS slot (2026-07-20) — owner-designed strategy, PAPER forward test.

Rule (owner's): LONG when the 9-period SMA crossed ABOVE the 15-period SMA
within the last K=3 bars AND price is above both the 5-minute-session VWAP
and the 15-minute VWAP (same session anchor, 3:1 resample of the 5m frame).
SHORT mirrored. Runs the full generic scalper slot path (slot SL/TP), NO
htf_l2-specific gates (thin∧ADX / ensemble hard block are htf_l2's). Kill
lines are OWNER-SET pending — adjudicator grades REPORT-ONLY.
"""
import inspect
import os
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

import bot as botmod
import risk_manager
import strategy_slot
from config import Config
from strategies import STRATEGIES, Signal, vwap_sma_cross
from strategy_slot import StrategySlot

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))
from lab_adjudicator import adjudicate as adj  # noqa: E402

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


def _sig_df(closes):
    """Bare OHLCV frame (DatetimeIndex, one UTC session) for direct signal
    calls — the strategy computes BOTH VWAPs itself (no baked columns)."""
    idx = pd.date_range("2026-07-20 00:00", periods=len(closes), freq="5min")
    c = pd.Series([float(x) for x in closes], index=idx)
    return pd.DataFrame({"open": c, "close": c, "high": c + 0.5, "low": c - 0.5,
                         "volume": pd.Series([1000.0] * len(c), index=idx)})


def _ramp(base=100.0, n=70, last=(100.5, 101.0)):
    """Flat session then a fresh 2-bar ramp: SMA9==SMA15 at bar -3 (flat),
    SMA9 beyond SMA15 now — a cross INSIDE the K=3 recency window."""
    return [base] * (n - len(last)) + list(last)


def _slot_df(closes, vwap_col):
    """Indicator-enriched frame for the slot path (add_all_indicators is
    identity-patched in _bare_bot, so columns are pre-baked). atr=0.0 keeps
    open_position on the fixed-% branch so the SL/TP override is assertable."""
    df = _sig_df(closes)
    n = len(df)
    for col, val in (("rsi", 50.0), ("vwap", vwap_col), ("ema_9", 100.0),
                     ("ema_21", 100.0), ("ema_50", 100.0), ("ema_200", 95.0),
                     ("adx", 30.0), ("atr", 0.0)):
        df[col] = [val] * n
    return df


def _flow(direction="long", tc=80):
    if direction == "long":
        return {"buy_ratio": 0.62, "cvd_slope": 0.5, "divergence": None,
                "large_trade_bias": 0.0, "trade_count": tc}
    return {"buy_ratio": 0.38, "cvd_slope": -0.5, "divergence": None,
            "large_trade_bias": 0.0, "trade_count": tc}


def _ob():
    return {"imbalance": 0.1, "bid_walls": [], "ask_walls": [],
            "spread_pct": 0.05, "bid_depth_usdt": 200000.0,
            "ask_depth_usdt": 100000.0, "illiquid": False}


def _paper_slot():
    return StrategySlot(
        slot_id="VWAP_CROSS", strategy_name="vwap_sma_cross",
        timeframe="5m", max_positions=2, capital_pct=0.0, paper_mode=True,
        trade_amount_usdt=None, loss_cap_usdt=-999.0, kelly_min_trades=10**9,
        durable_trail_enabled=False,
        sl_percent=Config.VWAP_CROSS_SL_PCT, tp_percent=Config.VWAP_CROSS_TP_PCT,
    )


def _bare_bot(slot, df, flow, monkeypatch):
    """Minimal bot able to run _evaluate_slots for one paper slot."""
    ob = _ob()
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
    b._fetch_htf_data = lambda s: None
    b._compute_confidence = lambda *a, **k: (5, ["l"] * 5)
    # supply pre-baked indicator columns — the pipeline would recompute them
    monkeypatch.setattr(botmod, "add_all_indicators", lambda d: d)
    return b


# ── 1-2: signal fires long / short ─────────────────────────────────────────

def test_signal_long_fires():
    sig = vwap_sma_cross(_sig_df(_ramp(last=(103.0, 106.0))), _ob())
    assert sig.signal == Signal.BUY
    assert sig.strength == pytest.approx(0.82)
    assert sig.reason.startswith("VWAP CROSS LONG")


def test_signal_short_fires():
    sig = vwap_sma_cross(_sig_df(_ramp(last=(97.0, 94.0))), _ob())
    assert sig.signal == Signal.SELL
    assert sig.strength == pytest.approx(0.82)
    assert sig.reason.startswith("VWAP CROSS SHORT")


# ── 3-6: HOLD paths ────────────────────────────────────────────────────────

def test_hold_no_recent_cross():
    sig = vwap_sma_cross(_sig_df([100.0] * 70), _ob())   # SMA9 == SMA15 flat
    assert sig.signal == Signal.HOLD


def test_hold_cross_but_below_vwap():
    # fresh cross-up (flat 100 then 100.5/101) but the session opened at 120
    # for 50 bars — session VWAP ≈ 114 sits far ABOVE the close → HOLD.
    closes = [120.0] * 50 + [100.0] * 18 + [100.5, 101.0]
    sig = vwap_sma_cross(_sig_df(closes), _ob())
    assert sig.signal == Signal.HOLD
    assert "VWAP" in sig.reason


def test_hold_cross_outside_k3_window():
    # cross fired 5 bars back (6-bar ramp): SMA9 > SMA15 at ALL of bars
    # -2/-3/-4 → recency window (K=3) missed → HOLD.
    closes = [100.0] * 64 + [101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    sig = vwap_sma_cross(_sig_df(closes), _ob())
    assert sig.signal == Signal.HOLD


def test_hold_insufficient_bars():
    sig = vwap_sma_cross(_sig_df(_ramp(n=40)), _ob())    # < 60-bar guard
    assert sig.signal == Signal.HOLD


# ── 7-8: registration ──────────────────────────────────────────────────────

def test_slot_registered_paper(sandbox):
    slot = botmod.Phmex2Bot._build_vwap_cross_slot()
    assert slot is not None
    assert slot.slot_id == "VWAP_CROSS"
    assert slot.paper_mode is True
    assert slot.strategy_name == "vwap_sma_cross"
    assert slot.strategy_name in STRATEGIES          # generic scalper path runs
    assert slot.loss_cap_usdt == -999.0              # paper — rails via adjudicator
    assert slot.kelly_min_trades == 10**9
    assert slot.durable_trail_enabled is False
    assert slot.timeframe == "5m" and slot.max_positions == 2
    assert slot.sl_percent == Config.VWAP_CROSS_SL_PCT
    assert slot.tp_percent == Config.VWAP_CROSS_TP_PCT
    assert slot.risk.state_file.endswith("trading_state_VWAP_CROSS.json")
    # wired into __init__ right after the HTF_L2 append
    src = inspect.getsource(botmod.Phmex2Bot.__init__)
    assert "_build_vwap_cross_slot()" in src


def test_env_flag_removes_slot(sandbox, monkeypatch):
    monkeypatch.setattr(Config, "VWAP_CROSS_ENABLED", False)
    assert botmod.Phmex2Bot._build_vwap_cross_slot() is None
    monkeypatch.setattr(Config, "VWAP_CROSS_ENABLED", True)
    assert botmod.Phmex2Bot._build_vwap_cross_slot() is not None


# ── 9-10: paper entries through the generic slot path ──────────────────────

def test_paper_entry_long(sandbox, monkeypatch):
    slot = _paper_slot()
    df = _slot_df(_ramp(last=(100.5, 101.0)), vwap_col=99.5)
    b = _bare_bot(slot, df, _flow("long"), monkeypatch)
    b._evaluate_slots([SYM], {SYM: 101.0})
    assert SYM in slot.risk.positions
    assert slot.risk.positions[SYM].side == "long"


def test_paper_entry_short(sandbox, monkeypatch):
    slot = _paper_slot()
    df = _slot_df(_ramp(last=(99.5, 99.0)), vwap_col=100.5)
    b = _bare_bot(slot, df, _flow("short"), monkeypatch)
    b._evaluate_slots([SYM], {SYM: 99.0})
    assert SYM in slot.risk.positions
    assert slot.risk.positions[SYM].side == "short"


# ── 11: halt interaction ───────────────────────────────────────────────────

def test_paper_entry_during_main_halt(sandbox, monkeypatch):
    (sandbox / ".halt_main_entries").write_text("halted 2026-07-13")
    slot = _paper_slot()
    df = _slot_df(_ramp(last=(100.5, 101.0)), vwap_col=99.5)
    b = _bare_bot(slot, df, _flow("long"), monkeypatch)
    b._evaluate_slots([SYM], {SYM: 101.0})
    assert SYM in slot.risk.positions        # slot trades through the halt
    assert b.risk.positions == {}            # main book untouched


# ── 12: slot SL/TP geometry flows to open_position ─────────────────────────

def test_sl_tp_overrides_flow_to_open_position(sandbox, monkeypatch):
    slot = _paper_slot()
    df = _slot_df(_ramp(last=(100.5, 101.0)), vwap_col=99.5)   # atr=0 → fixed-% branch
    b = _bare_bot(slot, df, _flow("long"), monkeypatch)
    b._evaluate_slots([SYM], {SYM: 101.0})
    pos = slot.risk.positions[SYM]
    assert pos.stop_loss == pytest.approx(
        101.0 * (1 - Config.VWAP_CROSS_SL_PCT / 100))
    assert pos.take_profit == pytest.approx(
        101.0 * (1 + Config.VWAP_CROSS_TP_PCT / 100))


# ── 13: kill sentinel stays in the paper book ──────────────────────────────

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
    open(".kill_VWAP_CROSS", "w").close()

    b._process_sentinels()

    assert calls == []                                # zero exchange calls
    assert slot.risk.positions == {}                  # closed in the paper book
    assert slot.risk.closed_trades[-1]["reason"] == "killed"
    assert slot.enabled is False
    assert not os.path.exists(".kill_VWAP_CROSS")


# ── 14-15: adjudicator grading (REPORT-ONLY) ───────────────────────────────

def test_grade_vwap_cross_zero_is_no_verdict():
    r = adj.grade_vwap_cross({}, {}, adj.EXPERIMENTS["vwap_cross"])
    assert r["experiment"] == "vwap_cross"
    assert r["status"] == adj.WATCH
    assert "n=0" in r["note"]


def test_grade_vwap_cross_reports_wr_net_and_breakeven():
    state = {"closed_trades": [{"net_pnl": 1.0}, {"net_pnl": -0.4},
                               {"net_pnl": 0.6}]}
    r = adj.grade_vwap_cross(state, {"tape_gate": 2},
                             adj.EXPERIMENTS["vwap_cross"])
    assert r["status"] == adj.WATCH          # report-only: kill lines OWNER-SET pending
    assert r["n_trades"] == 3
    assert abs(r["wr"] - 2 / 3) < 1e-4       # grader rounds to 4 dp
    assert abs(r["net_usd"] - 1.2) < 1e-9
    assert r["blocked_total"] == 2
    # breakeven WR from the slot's own geometry: win +2.4%−0.12% = +2.28% of
    # notional, loss −1.0%−0.12% = −1.12% → p = 1.12/3.40 = 0.3294 → 0.329
    assert abs(r["breakeven_wr"] - 0.329) < 1e-9
    assert "OWNER-SET" in r["note"]


# ── 16: dashboard box ──────────────────────────────────────────────────────

def test_dashboard_signal_box_present():
    import web_dashboard
    entries = {sid: (title, desc) for sid, title, desc in web_dashboard._SIGNAL_BOXES}
    assert "VWAP_CROSS" in entries
    title, desc = entries["VWAP_CROSS"]
    assert "PAPER" in title and "OWNER" in title
    assert "9/15 SMA" in desc and "VWAP" in desc
