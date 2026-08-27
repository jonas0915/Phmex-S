"""Paper-trading mode for the MAIN book (.paper_main sentinel, owner order 2026-08-26).

Conventions under test (TASKS.md 8/26):
  - `.paper_main` in repo root => _main_paper() True (fresh check per call).
  - Paper MAIN positions are tagged pos.paper=True at open; every downstream
    branch (exits, reconciler, trail, watcher) keys on the POSITION tag, never
    the sentinel, so toggling the sentinel mid-position can't strand a position.
  - Paper closed rows carry mode="paper"; main's RiskManager is_paper stays
    False (no gross->net ledger flip mid-file).
  - Paper entry fill via _fresh_paper_entry_price; NO exchange call of any kind
    on the paper path (entry, exit, SL/TP, trail amend, reconciler).

Covers (spec a-e):
  a. paper entry places NO exchange order and records the position paper=True
  b. paper exit calls no exchange close and writes mode="paper"
  c. simulated SL/TP triggers close at the right prices
  d. reconciler (_sync_exchange_closes/_build_position_owners) skips paper
  e. a LIVE (untagged) position still follows the real-order path unchanged

No network, no live files. conftest.py routes logging to logs/test_run.log and
blanks Telegram credentials.
"""
import os
import sys
import threading
import time
import types
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot as bot_module
from bot import Phmex2Bot, _build_position_owners, _main_paper, _sim_paper_fee
from config import Config
from risk_manager import Position, RiskManager

SYMBOL = "BTC/USDT:USDT"
BOT_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot.py")


def _make_position(**overrides):
    base = dict(
        symbol=SYMBOL, side="long", entry_price=100.0, amount=1.0,
        margin=10.0, stop_loss=98.8, take_profit=101.6,
    )
    base.update(overrides)
    return Position(**base)


def _bare_rm(state_file=None):
    """RiskManager without __init__ side effects (mirrors test_live_exit_watcher).
    state_file=None disables _save_state persistence (patched to no-op)."""
    rm = RiskManager.__new__(RiskManager)
    rm.positions = {}
    rm.closed_trades = []
    rm.trade_results = []
    rm.peak_balance = 0.0
    rm.is_paper = False          # MAIN convention: stays False even in paper mode
    rm._log_prefix = ""
    if state_file is None:
        rm._save_state = lambda: None
    else:
        rm.state_file = state_file
    return rm


def _bare_bot(rm=None):
    """Phmex2Bot via object.__new__ with only what the paper paths touch."""
    b = object.__new__(Phmex2Bot)
    b.risk = rm if rm is not None else _bare_rm()
    b.exchange = MagicMock()
    b.slots = []
    b.cycle_count = 7
    b._pos_lock = threading.Lock()
    b._closing = set()
    b._tp_skip_since = {}
    b._pair_cooldown = {}
    b._pair_loss_streak = {}
    b._trade_results = __import__("collections").deque(maxlen=5)
    b._regime_pause_until = 0.0
    b._persist_trade_results = lambda: None
    return b


def _signal(strength=0.8, reason="RSI(7)=25.0 oversold"):
    return types.SimpleNamespace(strength=strength, reason=reason)


# ---------------------------------------------------------------------------
# Sentinel helper
# ---------------------------------------------------------------------------

def test_main_paper_sentinel_fresh_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert _main_paper() is False
    (tmp_path / ".paper_main").write_text("owner order 8/26\n")
    assert _main_paper() is True          # fresh os.path.exists per call
    (tmp_path / ".paper_main").unlink()
    assert _main_paper() is False


def test_main_paper_bot_dir_argument(tmp_path):
    assert _main_paper(str(tmp_path)) is False
    (tmp_path / ".paper_main").write_text("x")
    assert _main_paper(str(tmp_path)) is True


# ---------------------------------------------------------------------------
# a. Paper entry — no exchange order, position tagged paper=True
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("direction", ["long", "short"])
def test_paper_entry_places_no_exchange_order(monkeypatch, direction):
    b = _bare_bot()
    # Fresh WS price differs from the cycle-cached one — entry must use it.
    b._ws_feed = MagicMock()
    b._ws_feed.last_price.return_value = (100.5, 0.4)
    monkeypatch.setattr(bot_module.notifier, "notify_paper_entry", MagicMock())

    pos = b._open_paper_main_position(
        SYMBOL, direction, 15.0, 100.0, atr_val=0.0, regime="medium",
        strat_name="confluence", signal=_signal(), confidence=5,
        layers=["rsi", "macd"])

    # NO exchange call of any kind (entry, SL/TP, anything).
    b.exchange.open_long.assert_not_called()
    b.exchange.open_short.assert_not_called()
    b.exchange.place_sl_tp.assert_not_called()
    assert b.exchange.method_calls == []

    assert pos is b.risk.positions[SYMBOL]
    assert pos.paper is True
    assert pos.side == direction
    assert pos.entry_price == 100.5          # fresh paper price, not cached 100.0
    assert pos.margin == 15.0
    assert pos.confidence == 5
    assert pos.ensemble_layers == "rsi,macd"
    bot_module.notifier.notify_paper_entry.assert_called_once()
    assert bot_module.notifier.notify_paper_entry.call_args.kwargs.get("slot") == "main"


def test_entry_loop_gates_on_main_paper_before_open_long():
    """Source-level guard: the entry loop branches on _main_paper() BEFORE the
    real open_long/open_short call, and the paper branch uses the helper."""
    src = open(BOT_PY).read()
    assert "if _main_paper():" in src
    assert "self._open_paper_main_position(" in src
    assert src.index("if _main_paper():") < src.index(
        "order = self.exchange.open_long(symbol, margin, price)")


# ---------------------------------------------------------------------------
# b. Paper exit — no exchange close, mode="paper" row
# ---------------------------------------------------------------------------

def test_close_paper_main_no_exchange_and_mode_paper(monkeypatch):
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.paper = True
    rm.positions[SYMBOL] = pos
    monkeypatch.setattr(bot_module.notifier, "notify_paper_exit", MagicMock())

    b._close_paper_main(SYMBOL, pos, 101.0, "early_exit")

    assert b.exchange.method_calls == []      # zero exchange interaction
    assert SYMBOL not in rm.positions
    assert len(rm.closed_trades) == 1
    row = rm.closed_trades[0]
    assert row["mode"] == "paper"
    assert row["reason"] == "early_exit"
    assert row["exit_price"] == 101.0
    # Sim fee model passed explicitly (main is_paper stays False): fee > 0 and
    # not tagged fees_pending (that tag summons the live-fee reconciler).
    assert row["fees_usdt"] == pytest.approx(_sim_paper_fee(100.0 * 1.0))
    assert "fees_pending" not in row
    # is_paper=False semantics preserved: pnl_usdt gross, net_pnl fee-adjusted.
    assert row["pnl_usdt"] == pytest.approx(1.0)
    assert row["net_pnl"] == pytest.approx(1.0 - row["fees_usdt"])
    bot_module.notifier.notify_paper_exit.assert_called_once()
    assert bot_module.notifier.notify_paper_exit.call_args.kwargs.get("slot") == "main"


def test_close_paper_main_sets_loss_cooldown(monkeypatch):
    """Cooldown fidelity: a paper loss must gate future paper entries exactly
    as a live loss would (identical signal path requirement)."""
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.paper = True
    rm.positions[SYMBOL] = pos
    b._set_cooldown_if_loss = MagicMock()
    monkeypatch.setattr(bot_module.notifier, "notify_paper_exit", MagicMock())

    b._close_paper_main(SYMBOL, pos, 99.0, "stop_loss")
    b._set_cooldown_if_loss.assert_called_once()
    args = b._set_cooldown_if_loss.call_args.args
    assert args[0] == SYMBOL and args[1] < 0


def test_all_cycle_exit_sites_have_paper_branch():
    """Source-level guard: every MAIN exit site branches to _close_paper_main.
    7 sites: early_exit, flat_exit, trend-flip, adverse_exit, time_exit,
    software SL/TP to_close loop, live exit watcher."""
    src = open(BOT_PY).read()
    assert src.count("self._close_paper_main(") >= 7
    # Each block region must contain the paper branch before its exchange close.
    markers = [
        ("# Early exit check", "# Flat exit"),
        ("# Flat exit", "# Trend-flip exit"),
        ("# Trend-flip exit", "# Adverse exit"),
        ("# Adverse exit", "# Shadow adverse-exit logging"),
        ("# Time-based exit", "# Break-even and trailing stop"),
        ("to_close = self.risk.check_positions", "# Part B shadow-logger"),
        ("def _live_exit_watcher_loop", "def _log_shadow_trail"),
    ]
    for start, end in markers:
        block = src[src.index(start):src.index(end)]
        assert "_close_paper_main(" in block, f"no paper branch in block {start!r}"


# ---------------------------------------------------------------------------
# c. Simulated SL/TP — closes at the right prices via check_positions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("price,expected_reason", [
    (98.7, "stop_loss"),      # below SL 98.8
    (101.7, "take_profit"),   # above TP 101.6
], ids=["sim_sl", "sim_tp"])
def test_sim_sl_tp_close_at_levels(monkeypatch, price, expected_reason):
    """Paper MAIN positions have no resting exchange orders; the software
    check_positions loop is the simulator. Breach -> paper close with the
    classified reason, no exchange call."""
    monkeypatch.setattr(Config, "TRAILING_STOP", False)
    rm = _bare_rm()
    b = _bare_bot(rm)
    monkeypatch.setattr(bot_module.notifier, "notify_paper_exit", MagicMock())
    pos = _make_position(margin=10.0)
    pos.paper = True
    rm.positions[SYMBOL] = pos

    to_close = rm.check_positions({SYMBOL: price})
    assert to_close == [(SYMBOL, expected_reason)]

    # The cycle's to_close loop routes paper positions here:
    b._close_paper_main(SYMBOL, pos, price, expected_reason)
    assert b.exchange.method_calls == []
    row = rm.closed_trades[-1]
    assert row["reason"] == expected_reason
    assert row["mode"] == "paper"
    assert row["exit_price"] == price


def test_no_breach_keeps_paper_position_open(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", False)
    rm = _bare_rm()
    pos = _make_position()
    pos.paper = True
    rm.positions[SYMBOL] = pos
    assert rm.check_positions({SYMBOL: 100.2}) == []
    assert SYMBOL in rm.positions


# ---------------------------------------------------------------------------
# Live exit watcher — paper positions simulated, live unchanged (b + e)
# ---------------------------------------------------------------------------

@pytest.fixture
def watcher_bot(monkeypatch):
    monkeypatch.setattr(Config, "TRAILING_STOP", True)
    b = _bare_bot()
    b.running = True
    pos = _make_position(take_profit=None, trailing_stop_price=104.0,
                         peak_price=105.0, margin=100.0)
    b.risk.positions[SYMBOL] = pos
    b.risk.close_position = MagicMock()
    b.exchange.close_long.return_value = {"id": "close-1", "symbol": SYMBOL}
    b.exchange.pop_reduce_only_abort.return_value = False
    b._ws_feed = MagicMock()
    b._ws_feed.last_price.return_value = (103.9, 2.0)  # fresh trail breach
    b._extract_fill_price = MagicMock(return_value=103.85)
    b._set_cooldown_if_loss = MagicMock()
    monkeypatch.setattr(bot_module.notifier, "notify_exit", MagicMock())
    monkeypatch.setattr(bot_module.notifier, "notify_paper_exit", MagicMock())
    monkeypatch.setattr(bot_module.notifier, "send", MagicMock())

    def stop_after_first_sleep(_secs):
        b.running = False
    monkeypatch.setattr(bot_module.time, "sleep", stop_after_first_sleep)
    return b


def test_watcher_paper_position_simulated_close(watcher_bot):
    b = watcher_bot
    pos = b.risk.positions[SYMBOL]
    pos.paper = True

    b._live_exit_watcher_loop()

    b.exchange.close_long.assert_not_called()
    b.exchange.close_short.assert_not_called()
    b.exchange.cancel_open_orders.assert_not_called()
    # Simulated close at the WS price with mode="paper"
    b.risk.close_position.assert_called_once()
    call = b.risk.close_position.call_args
    assert call.args[0] == SYMBOL
    assert call.args[1] == 103.9              # WS price, no _extract_fill_price
    assert call.args[2] == "trailing_stop"
    assert call.kwargs.get("mode") == "paper"
    bot_module.notifier.notify_paper_exit.assert_called_once()
    bot_module.notifier.notify_exit.assert_not_called()
    assert b._closing == set()                # claim released


def test_watcher_live_position_real_path_unchanged(watcher_bot):
    """(e) An untagged position must follow the real-order path exactly."""
    b = watcher_bot
    pos = b.risk.positions[SYMBOL]
    assert getattr(pos, "paper", False) is False

    b._live_exit_watcher_loop()

    b.exchange.close_long.assert_called_once_with(SYMBOL, pos.amount)
    b.risk.close_position.assert_called_once_with(
        SYMBOL, 103.85, "trailing_stop", fees_usdt=b.exchange.extract_order_fee.return_value)
    b.exchange.cancel_open_orders.assert_called_once_with(SYMBOL)
    bot_module.notifier.notify_exit.assert_called_once()
    bot_module.notifier.notify_paper_exit.assert_not_called()


# ---------------------------------------------------------------------------
# d. Reconciler — paper positions excluded (highest-risk miss)
# ---------------------------------------------------------------------------

def test_build_position_owners_excludes_paper_main():
    rm = _bare_rm()
    paper_pos = _make_position()
    paper_pos.paper = True
    live_pos = _make_position(symbol="ETH/USDT:USDT")
    rm.positions = {SYMBOL: paper_pos, "ETH/USDT:USDT": live_pos}

    owners = _build_position_owners(rm, [])
    assert SYMBOL not in owners               # paper main excluded
    assert owners["ETH/USDT:USDT"] == (rm, None)


def test_sync_exchange_closes_skips_paper_position(monkeypatch):
    """Exchange shows NO position for the paper symbol (it never existed there).
    The reconciler must NOT 'close' it / fabricate a trade."""
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.paper = True
    rm.positions[SYMBOL] = pos
    rm.close_position = MagicMock()
    b.exchange.get_open_positions.return_value = []
    b._slot_pending_exit_reason = {}
    b._set_cooldown_if_loss = MagicMock()
    monkeypatch.setattr(bot_module.notifier, "notify_exit", MagicMock())

    b._sync_exchange_closes({SYMBOL: 99.0})

    rm.close_position.assert_not_called()
    assert SYMBOL in rm.positions             # survives reconciliation
    b.exchange.cancel_open_orders.assert_not_called()
    bot_module.notifier.notify_exit.assert_not_called()


def test_sync_exchange_closes_still_closes_live_position(monkeypatch):
    """(e) Untagged main position gone from the exchange still reconciles as
    exchange_close — behavior unchanged."""
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()                    # no paper tag
    rm.positions[SYMBOL] = pos
    rm.close_position = MagicMock()
    b.exchange.get_open_positions.return_value = []
    b.exchange.client.fetch_my_trades.return_value = []
    b._slot_pending_exit_reason = {}
    b._set_cooldown_if_loss = MagicMock()
    monkeypatch.setattr(bot_module.notifier, "notify_exit", MagicMock())

    b._sync_exchange_closes({SYMBOL: 99.0})

    rm.close_position.assert_called_once()
    assert rm.close_position.call_args.args[2] == "exchange_close"


# ---------------------------------------------------------------------------
# Durable trail / SL-verify / partial-TP / startup — no exchange for paper
# ---------------------------------------------------------------------------

def test_trail_slverify_partialtp_startup_have_paper_guards():
    """Source-level guard for the blocks that are impractical to drive whole:
    each must skip paper-tagged positions before touching the exchange."""
    src = open(BOT_PY).read()
    regions = [
        ("# Verify SL orders still active", "# Time-based exit"),
        ("# Break-even and trailing stop updates", "# Check exit conditions"),
        ("# Partial take-profit", "# Early exit check"),
        ("# Place exchange SL/TP for synced positions", "# Add synced symbols to active pairs"),
    ]
    for start, end in regions:
        i = src.index(start)
        block = src[i:src.index(end, i)] if end in src[i:] else src[i:i + 4000]
        assert 'getattr(pos, "paper", False)' in block, f"no paper guard in {start!r}"


def test_partial_close_position_stores_mode():
    rm = _bare_rm()
    rm._save_state = lambda: None
    pos = _make_position(amount=2.0, margin=20.0)
    pos.paper = True
    rm.positions[SYMBOL] = pos

    rm.partial_close_position(SYMBOL, 101.0, fees_usdt=0.01, mode="paper")
    assert rm.closed_trades[-1]["mode"] == "paper"
    assert rm.closed_trades[-1]["reason"] == "partial_tp"
    # Runner half remains, still tagged paper
    assert rm.positions[SYMBOL].amount == 1.0
    assert rm.positions[SYMBOL].paper is True


def test_partial_close_position_without_mode_unchanged():
    rm = _bare_rm()
    rm._save_state = lambda: None
    rm.positions[SYMBOL] = _make_position(amount=2.0, margin=20.0)
    rm.partial_close_position(SYMBOL, 101.0, fees_usdt=0.01)
    assert "mode" not in rm.closed_trades[-1]


# ---------------------------------------------------------------------------
# Persistence — paper tag must survive a restart (state-file round trip)
# ---------------------------------------------------------------------------

def test_paper_tag_survives_state_round_trip(tmp_path):
    state = str(tmp_path / "trading_state_test.json")
    rm = RiskManager(state_file=state)
    rm.open_position(SYMBOL, 100.0, 15.0, side="long", atr=0.0)
    rm.positions[SYMBOL].paper = True
    rm.open_position("ETH/USDT:USDT", 50.0, 15.0, side="short", atr=0.0)  # untagged
    rm._save_state()

    rm2 = RiskManager(state_file=state)
    assert rm2.positions[SYMBOL].paper is True
    assert rm2.positions["ETH/USDT:USDT"].paper is False


# ---------------------------------------------------------------------------
# Daily-loss halt — paper main rows must never count as real-money loss
# ---------------------------------------------------------------------------

def test_today_net_all_books_excludes_paper_main_rows():
    rm = _bare_rm()
    b = _bare_bot(rm)
    now = time.time()
    rm.closed_trades = [
        {"closed_at": now, "net_pnl": -5.0},                     # real (no mode)
        {"closed_at": now, "net_pnl": -7.0, "mode": "paper"},    # paper sim
    ]
    assert b._today_net_all_books() == pytest.approx(-5.0)


def test_paper_losses_do_not_trigger_daily_loss_halt():
    """Simulated main losses past the halt threshold must NOT trip the real
    fleet-wide daily-loss kill switch (paper->real coupling)."""
    rm = _bare_rm()
    b = _bare_bot(rm)
    now = time.time()
    rm.closed_trades = [{"closed_at": now, "net_pnl": -20.0, "mode": "paper"}]
    assert b._today_net_all_books() == pytest.approx(0.0)
    assert bot_module._should_halt_daily_loss(b._today_net_all_books(), 100.0) is False
    # Sanity: the SAME loss untagged WOULD halt — the mode filter is load-bearing.
    rm.closed_trades = [{"closed_at": now, "net_pnl": -20.0}]
    assert bot_module._should_halt_daily_loss(b._today_net_all_books(), 100.0) is True


def test_kelly_sizing_excludes_paper_rows(monkeypatch):
    """Paper sim rows must never steer real-money Kelly sizing. 5 real rows
    with a positive edge -> max-margin clamp; a flood of huge paper losses in
    the book must not flip Kelly to the negative-edge fixed path."""
    monkeypatch.setenv("KELLY_LOOKBACK", "5")
    monkeypatch.setenv("KELLY_FRACTION", "0.25")
    monkeypatch.setenv("MIN_TRADE_MARGIN", "2.0")
    monkeypatch.setenv("MAX_TRADE_MARGIN", "10.0")
    monkeypatch.setenv("TRADE_AMOUNT_USDT", "8.0")
    rm = _bare_rm()
    real = ([{"net_pnl": 2.0}] * 3 + [{"net_pnl": -1.0}] * 2)
    paper = [{"net_pnl": -50.0, "mode": "paper"}] * 20
    rm.closed_trades = paper + real          # paper flood must be invisible
    margin = rm.calculate_kelly_margin(100.0, confidence=5)
    # real-only edge: wr=0.6 avg_win=2 avg_loss=1 -> kelly=0.4, fKelly=0.1,
    # 100*0.1=10 -> clamps at MAX_TRADE_MARGIN 10. Paper included would have
    # forced the negative-edge fixed $8 path instead.
    assert margin == pytest.approx(10.0)
    # Paper-only book stays in bootstrap (no real rows yet)
    rm.closed_trades = paper
    assert rm.calculate_kelly_margin(100.0, confidence=5) == pytest.approx(2.0)
    # calculate_kelly_raw: paper flood invisible; needs >=20 real rows
    rm.closed_trades = paper + real * 4      # 20 real rows
    assert rm.calculate_kelly_raw() == pytest.approx(0.4)


def test_print_stats_excludes_paper_rows(monkeypatch):
    import risk_manager as rm_module
    rm = _bare_rm()
    rm.closed_trades = [
        {"side": "long", "net_pnl": 5.0},
        {"side": "short", "net_pnl": -9.0, "mode": "paper"},
    ]
    captured = []
    monkeypatch.setattr(rm_module.logger, "info", lambda msg, *a, **k: captured.append(str(msg)))
    rm.print_stats(100.0)
    line = captured[-1]
    assert "Trades: 1" in line
    assert "+5.00" in line
    assert "Paper rows excluded: 1" in line


# ---------------------------------------------------------------------------
# Row shape — downstream consumers key on exact mode=="paper" + normal fields
# ---------------------------------------------------------------------------

def test_paper_row_is_well_formed(monkeypatch):
    """reconcile_phemex / dashboard / adjudicator exclusions all key on the
    EXACT string mode=='paper'; the row must otherwise carry the normal
    schema (symbol/opened_at/closed_at/net_pnl/...)."""
    rm = _bare_rm()
    b = _bare_bot(rm)
    pos = _make_position()
    pos.opened_at = time.time() - 300
    pos.paper = True
    rm.positions[SYMBOL] = pos
    monkeypatch.setattr(bot_module.notifier, "notify_paper_exit", MagicMock())

    b._close_paper_main(SYMBOL, pos, 101.0, "take_profit")
    row = rm.closed_trades[-1]
    assert row["mode"] == "paper"            # exact downstream key
    for key in ("symbol", "side", "entry_price", "exit_price", "amount",
                "margin", "pnl_usdt", "pnl_pct", "fees_usdt", "net_pnl",
                "reason", "exit_reason", "strategy", "opened_at", "closed_at",
                "duration_s"):
        assert key in row, f"missing {key}"
    assert row["symbol"] == SYMBOL
    assert row["opened_at"] == pos.opened_at
    assert row["closed_at"] >= pos.opened_at
