"""DONCHIAN_ETH live execution (owner go-live 2026-09-28; TASKS.md).
Owner rules under test: notional = 2 x w x account equity floored to 0.01 ETH lots;
2x isolated leverage set BEFORE any order; resting SL -15% (ratchets up daily, never
down) + resting TP +25% from day one; state saved BEFORE the protective orders;
halts defer up-sizes; nothing enters while ETH is held elsewhere on the exchange;
loss cap -26 (~30% of $87) demotes to paper."""
import os
import time
from types import SimpleNamespace

import pytest

import donchian_slot
from tests.test_donchian_slot import sandbox, _make_donchian_slot, _bare_bot  # noqa: F401

ETH = "ETH/USDT:USDT"
BTC = "BTC/USDT:USDT"


# ── pure helpers ──────────────────────────────────────────────────────────
def test_live_target_lots_floors_two_x_w_times_equity_to_whole_lots():
    # 2 x 0.30 x 87 = $52.2 at $2,600 = 0.0201 ETH -> 2 lots of 0.01
    assert donchian_slot.live_target_lots(0.30, 87.0, 2600.0) == 2
    assert donchian_slot.live_target_lots(0.10, 87.0, 2600.0) == 0     # $17.4 < one lot
    assert donchian_slot.live_target_lots(0.0, 87.0, 2600.0) == 0
    assert donchian_slot.live_target_lots(0.5, 0.0, 2600.0) == 0
    assert donchian_slot.live_target_lots(0.5, 87.0, 0.0) == 0


def test_ratchet_stop_only_moves_up():
    assert donchian_slot.ratchet_stop(None, 2000.0) == pytest.approx(1700.0)
    assert donchian_slot.ratchet_stop(1700.0, 2100.0) == pytest.approx(1785.0)
    assert donchian_slot.ratchet_stop(1785.0, 1900.0) == pytest.approx(1785.0)   # never down


def test_live_constants_match_owner_decisions():
    assert donchian_slot.LIVE_EXPOSURE_MULT == 2.0
    assert donchian_slot.LIVE_EXCHANGE_LEVERAGE == 2
    assert donchian_slot.LIVE_LOT == {ETH: 0.01}
    assert donchian_slot.LIVE_STOP_PCT == 15.0
    assert donchian_slot.LIVE_TP_PCT == 25.0
    assert donchian_slot.LIVE_SYMBOLS == [ETH]


# ── fake exchange ─────────────────────────────────────────────────────────
class LiveExchange:
    def __init__(self, equity=87.0, open_positions=None, price=2600.0):
        self.equity = equity
        self.open_positions = [] if open_positions is None else open_positions
        self.price = price
        self.calls = []
        self.fail_sltp = False
        self.fail_tp = False

    def get_equity(self, cur):
        return self.equity

    def get_balance(self, cur):
        self.calls.append(("get_balance", cur))
        return self.equity

    def get_ticker(self, symbol):
        return {"last": self.price}

    def get_open_positions(self):
        self.calls.append(("get_open_positions",))
        return self.open_positions

    def set_symbol_leverage(self, symbol, lev):
        self.calls.append(("set_symbol_leverage", symbol, lev))

    def open_long_market(self, symbol, amount):
        self.calls.append(("open_long_market", symbol, amount))
        return {"symbol": symbol, "id": "o1", "average": self.price, "filled": amount}

    def place_sl_tp(self, symbol, side, amount, sl, tp):
        self.calls.append(("place_sl_tp", symbol, side, amount, sl, tp))
        if self.fail_sltp:
            return {"sl_order_id": None, "tp_order_id": None}
        return {"sl_order_id": "sl1", "tp_order_id": "tp1"}

    def place_stop_loss(self, symbol, side, amount, sl):
        self.calls.append(("place_stop_loss", symbol, side, amount, sl))
        return "sl9"

    def place_take_profit(self, symbol, side, amount, tp):
        self.calls.append(("place_take_profit", symbol, side, amount, tp))
        return None if self.fail_tp else "tp9"

    def move_stop_loss(self, symbol, side, amount, new_sl, sl_order_id):
        self.calls.append(("move_stop_loss", symbol, side, amount, new_sl, sl_order_id))
        return "sl2"

    def verify_sl_order(self, symbol, oid):
        self.calls.append(("verify", symbol, oid))
        return oid not in (None, "software", "gone")

    def cancel_open_orders(self, symbol):
        self.calls.append(("cancel_open_orders", symbol))

    def close_long(self, symbol, amount, urgent=True):
        self.calls.append(("close_long", symbol, amount, urgent))
        return {"symbol": symbol, "id": "c1", "average": self.price}

    def pop_reduce_only_abort(self, symbol):
        return False

    def extract_order_fee(self, order, symbol=None):
        return 0.01

    def names(self):
        return [c[0] for c in self.calls]


@pytest.fixture
def live(sandbox, monkeypatch):
    import bot as botmod
    sent = []
    monkeypatch.setattr(botmod.notifier, "send", lambda m: sent.append(m))
    monkeypatch.setattr(botmod.notifier, "notify_exit", lambda *a, **k: sent.append(("exit",) + a))
    monkeypatch.setattr(botmod.Phmex2Bot, "_extract_fill_price",
                        lambda self, order, fallback, is_exit=False: fallback)
    slot = _make_donchian_slot("DONCHIAN_ETH", paper=False)
    slot.set_live(capital_pct=0.0)
    b = _bare_bot([slot])
    b.exchange = LiveExchange()
    b.risk = SimpleNamespace(positions={}, _drawdown_pause_until=0.0)
    b._slot_pending_exit_reason = {}
    b._donchian_ownership_notified = {}
    return SimpleNamespace(bot=b, slot=slot, ex=b.exchange, sent=sent)


def _today():
    return donchian_slot.utc_date_str()


# ── entry ─────────────────────────────────────────────────────────────────
def test_live_entry_sets_leverage_first_saves_state_then_rests_sl_and_tp(live):
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2600.0, False, _today())
    assert note and "opened" in note
    n = live.ex.names()
    assert n.index("get_open_positions") < n.index("set_symbol_leverage") < n.index("open_long_market") \
        < n.index("place_sl_tp")
    assert ("set_symbol_leverage", ETH, 2) in live.ex.calls
    assert ("open_long_market", ETH, pytest.approx(0.02)) in [c[:2] + (pytest.approx(c[2]),) for c in live.ex.calls
                                                               if c[0] == "open_long_market"]
    sltp = next(c for c in live.ex.calls if c[0] == "place_sl_tp")
    assert sltp[4] == pytest.approx(2600.0 * 0.85) and sltp[5] == pytest.approx(2600.0 * 1.25)
    pos = live.slot.risk.positions[ETH]
    assert pos.amount == pytest.approx(0.02)
    assert pos.stop_loss == pytest.approx(2210.0) and pos.take_profit == pytest.approx(3250.0)
    assert pos.sl_order_id == "sl1" and pos.tp_order_id == "tp1"
    assert pos.margin == pytest.approx(0.02 * 2600.0 / 2)       # isolated 2x margin
    assert any("LIVE" in m for m in live.sent if isinstance(m, str))
    # state was persisted with the position (crash before SL/TP must not orphan it)
    assert os.path.exists(live.slot.risk.state_file)


def test_live_entry_below_one_lot_stays_flat_and_places_nothing(live):
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.05, 2600.0, False, _today())
    assert "flat" in note
    assert "open_long_market" not in live.ex.names()


def test_live_entry_refuses_when_eth_is_held_elsewhere_on_the_exchange(live):
    live.ex.open_positions = [{"symbol": ETH, "side": "long", "amount": 0.05}]
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2600.0, False, _today())
    assert note is None                                  # retry next cycle, day unstamped
    assert "open_long_market" not in live.ex.names()
    assert "set_symbol_leverage" not in live.ex.names()


def test_live_entry_retries_when_positions_cannot_be_read(live):
    live.ex.open_positions = None
    assert live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2600.0, False, _today()) is None
    assert "open_long_market" not in live.ex.names()


def test_live_entry_retries_when_equity_unknown(live):
    live.ex.equity = 0.0
    assert live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2600.0, False, _today()) is None
    assert "open_long_market" not in live.ex.names()


def test_live_upsize_deferred_during_account_halt(live, sandbox):
    open(".pause_trading", "w").close()
    assert live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2600.0, False, _today()) is None
    assert "open_long_market" not in live.ex.names()


def test_live_sltp_failure_marks_software_and_warns(live):
    live.ex.fail_sltp = True
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2600.0, False, _today())
    assert note and "opened" in note
    pos = live.slot.risk.positions[ETH]
    assert pos.sl_order_id == "software"
    assert any("NO resting" in m for m in live.sent if isinstance(m, str))


# ── holding / ratchet / exits / resize ────────────────────────────────────
def _open(live, w=0.30, price=2600.0):
    assert live.bot._donchian_adjust_position(live.slot, ETH, w, price, False, _today())
    live.ex.calls.clear()


def test_hold_same_lots_ratchets_stop_up_never_down(live):
    _open(live)
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2700.0, False, _today())
    assert "holding" in note
    mv = next(c for c in live.ex.calls if c[0] == "move_stop_loss")
    assert mv[4] == pytest.approx(2700.0 * 0.85)
    pos = live.slot.risk.positions[ETH]
    assert pos.stop_loss == pytest.approx(2295.0) and pos.sl_order_id == "sl2"
    live.ex.calls.clear()
    live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2650.0, False, _today())
    assert "move_stop_loss" not in live.ex.names()        # lower close never lowers the stop


def test_target_zero_closes_with_stop_reason(live):
    _open(live)
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.0, 2500.0, True, _today())
    assert "closed" in note and "donchian_stop" in note
    assert ETH not in live.slot.risk.positions
    assert ("close_long", ETH) in [c[:2] for c in live.ex.calls]


def test_lot_change_closes_then_reopens(live):
    _open(live, w=0.30)                                   # 2 lots
    live.ex.equity = 87.0
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.50, 2600.0, False, _today())   # 3 lots
    assert "rebalanced" in note
    n = live.ex.names()
    assert n.index("close_long") < n.index("open_long_market")
    assert live.slot.risk.positions[ETH].amount == pytest.approx(0.03)


# ── per-cycle protection heal ─────────────────────────────────────────────
def test_heal_is_quiet_when_both_orders_rest(live):
    _open(live)
    live.bot._donchian_heal_protection(live.slot, ETH)
    assert "place_sl_tp" not in live.ex.names() and "cancel_open_orders" not in live.ex.names()


# ── ownership lock / promotion / kill line / paper untouched ──────────────
def test_lock_blocks_other_books_on_eth_only_while_live(live):
    assert live.bot._donchian_locks_symbol(ETH)
    assert live.bot._donchian_locks_symbol(BTC) is None
    live.slot.set_paper()
    assert live.bot._donchian_locks_symbol(ETH) is None


def test_promotion_resets_the_eval_stamp_so_live_trades_next_cycle(sandbox):
    b = _bare_bot([_make_donchian_slot("DONCHIAN_ETH")])
    b._donchian_state.setdefault(ETH, donchian_slot.default_coin_state())["last_eval_utc_date"] = _today()
    b._donchian_on_promote("DONCHIAN_ETH")
    assert b._donchian_state[ETH]["last_eval_utc_date"] is None
    b._donchian_on_promote("SOME_OTHER_SLOT")                # no-op, no error


def test_eth_live_kill_line_demotes_at_minus_26(sandbox):
    slot = StrategySlotForCap()
    slot.set_live(capital_pct=0.0)
    slot.risk.closed_trades = [{"pnl_usdt": -13.5, "mode": "live", "closed_at": time.time()} for _ in range(2)]
    demote, _ = slot.should_auto_demote()
    assert demote is True


def StrategySlotForCap():
    from strategy_slot import StrategySlot
    return StrategySlot(slot_id="DONCHIAN_ETH", strategy_name="donchian_ensemble", timeframe="1d",
                        max_positions=1, capital_pct=0.0, paper_mode=True,
                        loss_cap_usdt=donchian_slot.LIVE_LOSS_CAP_USDT,
                        kelly_min_trades=10**9, durable_trail_enabled=False)


def test_btc_is_never_live_even_if_promoted(sandbox, monkeypatch):
    import bot as botmod
    monkeypatch.setattr(botmod.notifier, "send", lambda m: None)
    slot = _make_donchian_slot("DONCHIAN_BTC", paper=False)
    slot.set_live(capital_pct=0.0)
    b = _bare_bot([slot])
    b.exchange = LiveExchange()
    b._donchian_live_warned = {}
    note = b._donchian_adjust_position(slot, BTC, 0.5, 80000.0, False, _today())
    assert "not enabled for live" in note
    assert b.exchange.calls == []


def test_heal_never_rests_orders_when_the_exchange_shows_no_position(live):
    _open(live)
    live.slot.risk.positions[ETH].sl_order_id = "gone"
    live.ex.open_positions = []                              # SL/TP already filled; sync will book it
    live.bot._donchian_heal_protection(live.slot, ETH)
    assert "place_sl_tp" not in live.ex.names() and "cancel_open_orders" not in live.ex.names()


def test_price_drift_alone_never_resizes_while_w_is_unchanged(live):
    _open(live, w=0.30, price=2600.0)                         # 2 lots
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 3500.0, False, _today())
    assert "holding" in note                                 # would be 1 lot at 3500, but w didn't change
    assert "close_long" not in live.ex.names() and "open_long_market" not in live.ex.names()


# ── review fixes (9/28) ───────────────────────────────────────────────────
def test_hold_day_records_the_new_w_so_the_churn_gate_keeps_working(live):
    _open(live, w=0.30, price=2600.0)                                    # 2 lots
    live.bot._donchian_adjust_position(live.slot, ETH, 0.36, 2600.0, False, _today())  # still 2 lots
    assert live.bot._donchian_state[ETH]["live_w"] == pytest.approx(0.36)
    live.ex.calls.clear()
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.36, 3500.0, False, _today())
    assert "holding" in note and "close_long" not in live.ex.names()


def test_resize_never_moves_the_stop_down(live):
    _open(live, w=0.30, price=3000.0)                        # stop 2550
    live.ex.price = 2800.0
    live.bot._donchian_adjust_position(live.slot, ETH, 0.60, 2800.0, False, _today())
    pos = live.slot.risk.positions[ETH]
    assert pos.stop_loss == pytest.approx(2550.0)            # not 2800*0.85 = 2380
    sltp = [c for c in live.ex.calls if c[0] == "place_sl_tp"][-1]
    assert sltp[4] == pytest.approx(2550.0)


def test_halt_does_not_spin_when_w_is_unchanged(live, sandbox):
    _open(live, w=0.30, price=2600.0)
    open(".pause_trading", "w").close()
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2000.0, False, _today())
    assert note and "holding" in note                        # not None (would retry every cycle)


def test_leverage_flag_set_before_flip_and_restored_to_config_after_demote(live, monkeypatch):
    import bot as botmod
    live.bot._leverage_set = set()
    _open(live)
    assert live.bot._donchian_state[ETH]["leverage_2x_set"] is True
    # demoted + flat -> restore to Config.LEVERAGE, clear flag, lock released
    live.slot.risk.positions.pop(ETH)
    live.slot.set_paper()
    assert live.bot._donchian_locks_symbol(ETH)               # still locked: 2x not restored yet
    live.bot._donchian_restore_leverage(ETH)
    assert ("set_symbol_leverage", ETH, botmod.Config.LEVERAGE) in live.ex.calls
    assert live.bot._donchian_state[ETH]["leverage_2x_set"] is False
    assert ETH in live.bot._leverage_set
    assert live.bot._donchian_locks_symbol(ETH) is None


def test_leverage_not_restored_while_live(live):
    _open(live)
    live.ex.calls.clear()
    live.bot._donchian_restore_leverage(ETH)
    assert "set_symbol_leverage" not in live.ex.names()


def test_heal_rests_only_the_missing_leg_and_never_cancels_the_good_one(live):
    _open(live)
    pos = live.slot.risk.positions[ETH]
    pos.tp_order_id = "gone"
    live.ex.open_positions = [{"symbol": ETH, "side": "long", "amount": 0.02}]
    live.ex.calls.clear()
    live.bot._donchian_heal_protection(live.slot, ETH)
    n = live.ex.names()
    assert "cancel_open_orders" not in n and "place_sl_tp" not in n
    assert "place_take_profit" in n and "place_stop_loss" not in n
    assert pos.tp_order_id == "tp9" and pos.sl_order_id == "sl1"


def test_heal_missing_stop_retries_every_cycle_missing_tp_is_throttled(live):
    _open(live)
    pos = live.slot.risk.positions[ETH]
    live.ex.open_positions = [{"symbol": ETH, "side": "long", "amount": 0.02}]
    live.ex.fail_tp = True
    pos.tp_order_id = None
    live.bot._donchian_heal_protection(live.slot, ETH)
    live.ex.calls.clear()
    live.bot._donchian_heal_protection(live.slot, ETH)       # same minute: TP retry throttled
    assert "place_take_profit" not in live.ex.names()
    pos.sl_order_id = "software"
    live.bot._donchian_heal_protection(live.slot, ETH)       # missing STOP: never throttled
    assert "place_stop_loss" in live.ex.names()


def test_demote_with_failed_close_keeps_protection_stays_live_and_persists_the_retry(live):
    _open(live)
    live.ex.calls.clear()
    live.ex.close_long = lambda *a, **k: None                # exchange refuses the close
    ok = live.bot._demote_slot(live.slot, "loss cap")
    assert ok is False
    assert live.slot.paper_mode is False and ETH in live.slot.risk.positions
    assert "cancel_open_orders" not in live.ex.names()       # resting SL/TP stay in place
    assert os.path.exists(".demote_DONCHIAN_ETH")            # survives a restart; retried each cycle
    # the Telegram alert is deduped: a second failed attempt the same day sends nothing new
    n = len(live.sent)
    live.bot._demote_slot(live.slot, "loss cap")
    assert len(live.sent) == n


def test_demote_success_closes_first_then_cancels_and_flips_to_paper(live):
    _open(live)
    live.ex.calls.clear()
    assert live.bot._demote_slot(live.slot, "loss cap") is True
    n = live.ex.names()
    assert n.index("close_long") < n.index("cancel_open_orders")
    assert live.slot.paper_mode is True and ETH not in live.slot.risk.positions


def test_demote_sentinel_is_kept_until_the_close_succeeds(live):
    _open(live)
    open(".demote_DONCHIAN_ETH", "w").close()
    live.ex.close_long = lambda *a, **k: None
    live.bot._process_demote_sentinels()
    assert os.path.exists(".demote_DONCHIAN_ETH") and live.slot.paper_mode is False
    del live.ex.close_long                                   # exchange recovers
    live.bot._process_demote_sentinels()
    assert not os.path.exists(".demote_DONCHIAN_ETH") and live.slot.paper_mode is True


def test_no_live_entry_while_a_demote_is_pending(live):
    open(".demote_DONCHIAN_ETH", "w").close()
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 2600.0, False, _today())
    assert "demote pending" in note and "open_long_market" not in live.ex.names()


def test_split_resize_keeps_the_ratcheted_stop_across_a_failed_reopen(live):
    _open(live, w=0.30, price=3000.0)                        # stop 2550
    real_open = live.ex.open_long_market
    live.ex.open_long_market = lambda *a, **k: None          # reopen fails after the close
    assert live.bot._donchian_adjust_position(live.slot, ETH, 0.60, 2800.0, False, _today()) is None
    assert ETH not in live.slot.risk.positions
    live.ex.open_long_market = real_open
    live.ex.price = 2800.0
    assert live.bot._donchian_adjust_position(live.slot, ETH, 0.60, 2800.0, False, _today())
    assert live.slot.risk.positions[ETH].stop_loss == pytest.approx(2550.0)


def test_price_drift_to_below_one_lot_does_not_close_while_w_unchanged(live):
    _open(live, w=0.30, price=2600.0)                        # 2 lots
    note = live.bot._donchian_adjust_position(live.slot, ETH, 0.30, 9000.0, False, _today())
    assert "holding" in note and "close_long" not in live.ex.names()


def test_leverage_restore_not_blocked_by_a_paper_position(live):
    _open(live)
    live.slot.risk.positions.pop(ETH)
    live.slot.set_paper()
    live.slot.risk.positions[ETH] = SimpleNamespace(side="long", amount=0.01)   # paper book re-entered
    assert live.bot._donchian_restore_leverage(ETH) is True
