"""U2 (2026-07-23 safety bundle): cross-book ownership + shared daily symbol
cap between the MAIN book and the HTF_L2 slot.

Evidence (7/23 loss audit): both books chase the same signals on ~$34 shared
margin; 7/22 ETH — the slot chased a signal at 10:12 AM that main was already
day-capped out of, lost −$1.48. Flag: Config.HTF_L2_CROSS_BOOK_LOCK.

  a) main holds S -> HTF_L2 slot must not enter S (counter "cross_book");
     HTF_L2 slot holds S live -> main must not enter S.
  b) The daily per-symbol cap counts BOTH main entries and HTF_L2 slot live
     entries; both entry paths enforce against the combined count.
"""
import inspect
import time
from types import SimpleNamespace

import pandas as pd
import pytest

import bot as botmod
import risk_manager
import strategy_slot
from config import Config
from strategy_slot import StrategySlot

SYM = "ETH/USDT:USDT"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    monkeypatch.setattr(risk_manager, "__file__", str(tmp_path / "risk_manager.py"))
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(botmod.notifier, "send", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_entry", lambda *a, **k: None)
    monkeypatch.setattr(botmod.notifier, "notify_paper_exit", lambda *a, **k: None)
    return tmp_path


def _df_5m(n=60):
    rows = {
        "close": [100.0] * n, "open": [100.0] * n,
        "high": [100.5] * n, "low": [99.5] * n,
        "volume": [1000.0] * n,
        "rsi": [50.0] * n, "vwap": [99.5] * n,
        "ema_9": [100.4] * n, "ema_21": [100.2] * n, "ema_50": [99.0] * n,
        "ema_200": [95.0] * n, "adx": [30.0] * n, "atr": [0.5] * n,
    }
    return pd.DataFrame(rows)


def _htf_df(adx=25.0, n=40):
    return pd.DataFrame({
        "close": [110.0] * n, "ema_21": [105.0] * n, "ema_50": [100.0] * n,
        "adx": [adx] * n,
    })


def _mk_slot(paper=True, slot_id="HTF_L2"):
    return StrategySlot(
        slot_id=slot_id, strategy_name="htf_l2_anticipation",
        timeframe="5m", max_positions=2, capital_pct=0.0, paper_mode=paper,
        trade_amount_usdt=None, loss_cap_usdt=-999.0, kelly_min_trades=10**9,
        sl_percent=Config.HTF_L2_SL_PCT, tp_percent=Config.HTF_L2_TP_PCT,
    )


def _bare_bot(slot, monkeypatch, main_positions=None, main_trades=None):
    df, htf = _df_5m(), _htf_df()
    flow = {"buy_ratio": 0.62, "cvd_slope": 0.5, "divergence": None,
            "large_trade_bias": 0.0, "trade_count": 80}
    ob = {"imbalance": 0.1, "bid_walls": [], "ask_walls": [],
          "spread_pct": 0.05, "bid_depth_usdt": 200000.0,
          "ask_depth_usdt": 100000.0, "illiquid": False}
    b = object.__new__(botmod.Phmex2Bot)
    b.slots = [slot] if slot is not None else []
    b.risk = SimpleNamespace(positions=main_positions or {},
                             closed_trades=main_trades or [],
                             _drawdown_pause_until=0.0)
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
    b._compute_confidence = lambda *a, **k: (5, ["l"] * 5)
    b._classify_regime = lambda last, df=None: {"label": "TREND", "adx": 30.0}
    monkeypatch.setattr(botmod, "add_all_indicators", lambda d: d)
    return b


def _trade(symbol=SYM, opened_at=None, mode=None, exit_reason="stop_loss"):
    t = {"symbol": symbol, "opened_at": opened_at if opened_at is not None else time.time(),
         "closed_at": time.time(), "net_pnl": -1.0, "pnl_usdt": -1.0,
         "exit_reason": exit_reason}
    if mode is not None:
        t["mode"] = mode
    return t


# ── (a) ownership lock ─────────────────────────────────────────────────────

def test_slot_skips_symbol_main_holds(sandbox, monkeypatch):
    slot = _mk_slot()
    b = _bare_bot(slot, monkeypatch,
                  main_positions={SYM: SimpleNamespace(side="long")})
    b._evaluate_slots([SYM], {SYM: 100.0})
    assert SYM not in slot.risk.positions
    assert slot.blocked_counts.get("cross_book", 0) == 1


def test_slot_enters_when_main_flat(sandbox, monkeypatch):
    slot = _mk_slot()
    b = _bare_bot(slot, monkeypatch)
    b._evaluate_slots([SYM], {SYM: 100.0})
    assert SYM in slot.risk.positions


def test_slot_flag_off_restores_old_behavior(sandbox, monkeypatch):
    monkeypatch.setattr(Config, "HTF_L2_CROSS_BOOK_LOCK", False)
    slot = _mk_slot()
    b = _bare_bot(slot, monkeypatch,
                  main_positions={SYM: SimpleNamespace(side="long")})
    b._evaluate_slots([SYM], {SYM: 100.0})
    assert SYM in slot.risk.positions
    assert slot.blocked_counts.get("cross_book", 0) == 0


def test_htf_l2_slot_holds_blocks_main(sandbox, monkeypatch):
    """Live HTF_L2 slot holding S -> main-path guard returns the lock."""
    slot = _mk_slot(paper=False)
    slot.risk.positions[SYM] = SimpleNamespace(side="long")
    b = _bare_bot(slot, monkeypatch)
    assert b._htf_l2_slot_holds(SYM) is True
    assert b._htf_l2_slot_holds("BTC/USDT:USDT") is False


def test_htf_l2_paper_slot_does_not_lock_main(sandbox, monkeypatch):
    slot = _mk_slot(paper=True)
    slot.risk.positions[SYM] = SimpleNamespace(side="long")
    b = _bare_bot(slot, monkeypatch)
    assert b._htf_l2_slot_holds(SYM) is False


def test_htf_l2_slot_holds_flag_off(sandbox, monkeypatch):
    monkeypatch.setattr(Config, "HTF_L2_CROSS_BOOK_LOCK", False)
    slot = _mk_slot(paper=False)
    slot.risk.positions[SYM] = SimpleNamespace(side="long")
    b = _bare_bot(slot, monkeypatch)
    assert b._htf_l2_slot_holds(SYM) is False


# ── (b) shared daily symbol cap ────────────────────────────────────────────

def test_combined_count_sums_main_and_slot_live_entries(sandbox, monkeypatch):
    slot = _mk_slot(paper=True)  # demoted slot: its LIVE-era records still count
    slot.risk.closed_trades = [
        _trade(mode="live"),                                # today, live -> counts
        _trade(mode="live", opened_at=time.time() - 86400 * 2),  # old -> no
        _trade(),                                           # paper record -> no
        _trade(mode="live", exit_reason="min_margin_skip"), # ghost -> no
    ]
    main_trades = [_trade(), _trade(),
                   _trade(symbol="BTC/USDT:USDT")]  # other symbol -> no
    b = _bare_bot(slot, monkeypatch, main_trades=main_trades)
    assert b._combined_daily_symbol_count(SYM) == 3  # 2 main + 1 slot live


def test_combined_count_includes_open_positions(sandbox, monkeypatch):
    slot = _mk_slot(paper=False)
    slot.risk.positions[SYM] = SimpleNamespace(side="long")
    b = _bare_bot(slot, monkeypatch,
                  main_positions={SYM: SimpleNamespace(side="long")})
    assert b._combined_daily_symbol_count(SYM) == 2  # 1 main open + 1 slot open


def test_combined_count_flag_off_is_main_only(sandbox, monkeypatch):
    monkeypatch.setattr(Config, "HTF_L2_CROSS_BOOK_LOCK", False)
    slot = _mk_slot(paper=True)
    slot.risk.closed_trades = [_trade(mode="live")]
    b = _bare_bot(slot, monkeypatch, main_trades=[_trade(), _trade()])
    assert b._combined_daily_symbol_count(SYM) == 2  # slot excluded


def test_slot_refuses_fourth_combined_entry(sandbox, monkeypatch):
    """2 main + 1 slot live ETH trades today -> combined 3 >= cap -> slot skips."""
    slot = _mk_slot()
    slot.risk.closed_trades = [_trade(mode="live")]
    b = _bare_bot(slot, monkeypatch, main_trades=[_trade(), _trade()])
    b._evaluate_slots([SYM], {SYM: 100.0})
    assert SYM not in slot.risk.positions
    assert slot.blocked_counts.get("daily_cap", 0) == 1


def test_main_entry_loop_wired_to_cross_book_guards():
    """The main entry section must consult both U2 helpers (the loop itself is
    not unit-runnable — mirror of the drift-gate wiring style)."""
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    assert "_htf_l2_slot_holds" in src
    assert "_combined_daily_symbol_count" in src
