# Live Slot Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build real-order execution for promoted strategy slots so 5m_mean_revert can trade live with hard guardrails (auto-demote at −$5 live PnL or negative live-only Kelly after 10 trades).

**Architecture:** Mode-aware slot evaluator — the existing paper evaluation path gains a live branch that places real PostOnly entries, real exchange SL/TP, and real adverse/time exits. Reconcile gains slot-ownership awareness. Promotion state persists across restarts via a sidecar file. Spec: `docs/superpowers/specs/2026-06-12-live-slot-execution-design.md`.

**Tech Stack:** Python 3.14, ccxt/Phemex, pytest. Run tests with:
`/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest tests/ -q`

**Constraints (non-negotiable):**
- Live money. NO restart without `/pre-restart-audit`. Deploy only on flat window after live-exit watcher has handled ≥2 real exits.
- `rm -rf __pycache__` before any restart.
- Every surfaced metric must propagate to Telegram + dashboard (CLAUDE.md rule).
- Mirror the paper path exactly — do NOT add ensemble/time-block/global-cooldown gates to slot entries.

---

### Task 1: Promotion persistence + live accounting on StrategySlot

**Files:**
- Modify: `strategy_slot.py` (dataclass fields + methods, after `_load_blocked_counts`)
- Test: `tests/test_live_slot.py` (create)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_live_slot.py
import os, json, time, tempfile, pytest
import strategy_slot
from strategy_slot import StrategySlot

@pytest.fixture
def slot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # state files land in tmp
    monkeypatch.setattr(strategy_slot, "__file__", str(tmp_path / "strategy_slot.py"))
    s = StrategySlot(slot_id="t_revert", strategy_name="bb_mean_reversion",
                     timeframe="5m", max_positions=1, capital_pct=0.2, paper_mode=True)
    return s

def _fake_trade(pnl, mode=None, ts=None):
    t = {"pnl_usdt": pnl, "closed_at": ts or time.time()}
    if mode:
        t["mode"] = mode
    return t

def test_promote_persists_and_reloads(slot, tmp_path, monkeypatch):
    slot.set_live(capital_pct=0.2)
    assert slot.paper_mode is False
    assert slot.promoted_at > 0
    # New instance must come back LIVE (restart survival)
    s2 = StrategySlot(slot_id="t_revert", strategy_name="bb_mean_reversion",
                      timeframe="5m", max_positions=1, capital_pct=0.5, paper_mode=True)
    assert s2.paper_mode is False
    assert s2.promoted_at == pytest.approx(slot.promoted_at)

def test_demote_persists(slot):
    slot.set_live(capital_pct=0.2)
    slot.set_paper()
    s2 = StrategySlot(slot_id="t_revert", strategy_name="bb_mean_reversion",
                      timeframe="5m", max_positions=1, capital_pct=0.2, paper_mode=False)
    assert s2.paper_mode is True

def test_live_pnl_excludes_paper_history(slot):
    slot.set_live()
    slot.risk.closed_trades = [
        _fake_trade(-20.0),                 # paper history — ignored
        _fake_trade(-2.0, mode="live"),
        _fake_trade(-1.5, mode="live"),
    ]
    assert slot.live_pnl() == pytest.approx(-3.5)

def test_auto_demote_on_loss_cap(slot):
    slot.set_live()
    slot.risk.closed_trades = [_fake_trade(-2.6, mode="live"), _fake_trade(-2.5, mode="live")]
    demote, reason = slot.should_auto_demote()
    assert demote and "loss cap" in reason

def test_auto_demote_on_negative_kelly_needs_10_trades(slot):
    slot.set_live()
    # 9 losing live trades — kelly negative but n<10 and pnl above cap → no demote
    slot.risk.closed_trades = [_fake_trade(-0.4, mode="live")] * 9
    demote, _ = slot.should_auto_demote()
    assert not demote
    # 10th trade: negative-kelly trigger arms (3 wins $0.1 / 7 losses $0.4 → kelly < 0)
    slot.risk.closed_trades = ([_fake_trade(0.1, mode="live")] * 3 +
                               [_fake_trade(-0.4, mode="live")] * 7)
    demote, reason = slot.should_auto_demote()
    assert demote and "kelly" in reason.lower()

def test_no_demote_when_healthy(slot):
    slot.set_live()
    slot.risk.closed_trades = ([_fake_trade(0.5, mode="live")] * 7 +
                               [_fake_trade(-0.4, mode="live")] * 5)
    demote, _ = slot.should_auto_demote()
    assert not demote
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest tests/test_live_slot.py -q`
Expected: FAIL — `AttributeError: 'StrategySlot' object has no attribute 'set_live'`

- [ ] **Step 3: Implement on StrategySlot**

In `strategy_slot.py`, add constants at module top and methods to the dataclass:

```python
LIVE_LOSS_CAP_USDT = -5.0      # auto-demote when live net PnL breaches this
LIVE_KELLY_MIN_TRADES = 10     # negative-kelly demote needs at least this many live trades
```

In `__post_init__`, after `self.blocked_counts = ...`:

```python
        self.promoted_at: float = 0.0
        self._mode_sidecar = os.path.join(
            os.path.dirname(__file__), f"trading_state_{self.slot_id}_mode.json"
        )
        self._load_mode()
```

New methods:

```python
    def _load_mode(self) -> None:
        """Restore promotion state across restarts (constructor defaults are paper)."""
        try:
            if os.path.exists(self._mode_sidecar):
                with open(self._mode_sidecar) as f:
                    data = json.load(f)
                self.paper_mode = bool(data.get("paper_mode", self.paper_mode))
                self.capital_pct = float(data.get("capital_pct", self.capital_pct))
                self.promoted_at = float(data.get("promoted_at", 0.0))
        except Exception as e:
            logger.warning(f"[SLOT] {self.slot_id} mode sidecar load failed: {e}")

    def _save_mode(self) -> None:
        try:
            with open(self._mode_sidecar, "w") as f:
                json.dump({"paper_mode": self.paper_mode,
                           "capital_pct": self.capital_pct,
                           "promoted_at": self.promoted_at}, f)
        except Exception as e:
            logger.warning(f"[SLOT] {self.slot_id} mode sidecar save failed: {e}")

    def set_live(self, capital_pct: float = None) -> None:
        self.paper_mode = False
        if capital_pct is not None:
            self.capital_pct = capital_pct
        self.promoted_at = time.time()
        self._save_mode()

    def set_paper(self) -> None:
        self.paper_mode = True
        self.capital_pct = 0.0
        self._save_mode()

    def live_trades(self) -> list:
        return [t for t in self.risk.closed_trades if t.get("mode") == "live"]

    def live_pnl(self) -> float:
        return sum(t.get("pnl_usdt", 0) for t in self.live_trades())

    def should_auto_demote(self) -> tuple:
        """(demote: bool, reason: str). Checked after every live close."""
        trades = self.live_trades()
        pnl = sum(t.get("pnl_usdt", 0) for t in trades)
        if pnl <= LIVE_LOSS_CAP_USDT:
            return True, f"live loss cap: ${pnl:.2f} <= ${LIVE_LOSS_CAP_USDT:.2f}"
        if len(trades) >= LIVE_KELLY_MIN_TRADES:
            wins = [t["pnl_usdt"] for t in trades if t.get("pnl_usdt", 0) > 0]
            losses = [abs(t["pnl_usdt"]) for t in trades if t.get("pnl_usdt", 0) < 0]
            if losses and wins:
                wr = len(wins) / len(trades)
                rr = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
                kelly = wr - (1 - wr) / rr
            elif not wins:
                kelly = -1.0
            else:
                kelly = 1.0
            if kelly < 0:
                return True, f"negative live Kelly ({kelly:.3f}) after {len(trades)} live trades"
        return False, ""
```

- [ ] **Step 4: Run tests, verify pass**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m pytest tests/test_live_slot.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add strategy_slot.py tests/test_live_slot.py
git commit -m "feat(slots): promotion persistence + live-only accounting + auto-demote triggers"
```

---

### Task 2: Mode tagging in RiskManager.close_position

**Files:**
- Modify: `risk_manager.py:601` (`close_position` signature + trade record)
- Test: `tests/test_live_slot.py` (append)

- [ ] **Step 1: Write failing test**

```python
def test_close_position_records_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from risk_manager import RiskManager
    rm = RiskManager(state_file=str(tmp_path / "state.json"))
    rm.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")
    rm.close_position("DOGE/USDT:USDT", 0.081, "take_profit", mode="live")
    assert rm.closed_trades[-1]["mode"] == "live"
    rm.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")
    rm.close_position("DOGE/USDT:USDT", 0.081, "take_profit")
    assert "mode" not in rm.closed_trades[-1]
```

- [ ] **Step 2: Run, verify fails** (`TypeError: close_position() got an unexpected keyword argument 'mode'`)

- [ ] **Step 3: Implement**

In `risk_manager.py:601` change the signature to
`def close_position(self, symbol, exit_price, reason, fees_usdt=None, mode=None):`
and where the trade-record dict is built (inside the same method, before append to
`self.closed_trades`), add:

```python
        if mode:
            trade_record["mode"] = mode
```

(use the actual local dict name in that method; do not change any other field).

- [ ] **Step 4: Run full suite** — all green, including pre-existing 65 tests.
- [ ] **Step 5: Commit** `git commit -am "feat(risk): optional mode tag on closed trades"`

---

### Task 3: Reconcile slot-ownership (the double-management fix)

**Files:**
- Modify: `bot.py` sync function (Path A bot.py:~2203, Path B bot.py:~2254)
- Test: `tests/test_live_slot.py` (append)

- [ ] **Step 1: Write failing tests** — pure-function tests against a new helper.

```python
def test_owner_map_includes_live_slots(slot):
    from bot import _build_position_owners
    class _MainRisk:  positions = {"BTC/USDT:USDT": object()}
    slot.set_live()
    slot.risk.positions = {"DOGE/USDT:USDT": object()}
    paper = StrategySlot(slot_id="t_paper", strategy_name="bb_mean_reversion",
                         timeframe="5m", paper_mode=True)
    paper.risk.positions = {"ETH/USDT:USDT": object()}
    owners = _build_position_owners(_MainRisk(), [slot, paper])
    assert "BTC/USDT:USDT" in owners and owners["BTC/USDT:USDT"][1] is None
    assert "DOGE/USDT:USDT" in owners and owners["DOGE/USDT:USDT"][1] is slot
    assert "ETH/USDT:USDT" not in owners   # paper positions are not exchange-backed
```

- [ ] **Step 2: Run, verify fails** (ImportError)

- [ ] **Step 3: Implement**

Module-level helper in `bot.py` (near the sync function):

```python
def _build_position_owners(main_risk, slots):
    """symbol -> (owner_risk_manager, slot_or_None) for every EXCHANGE-BACKED position.
    Main bot positions map to (self.risk, None); live-slot positions map to
    (slot.risk, slot). Paper slots are simulation-only and excluded."""
    owners = {s: (main_risk, None) for s in main_risk.positions}
    for slot in slots:
        if slot.paper_mode:
            continue
        for s in slot.risk.positions:
            if s not in owners:
                owners[s] = (slot.risk, slot)
    return owners
```

Then in the sync function:
- Replace Path A's `for symbol in list(self.risk.positions.keys()):` iteration to run over
  `owners = _build_position_owners(self.risk, self.slots)`. For slot-owned closes, record into
  the slot: `owner_risk.close_position(symbol, exit_price, close_reason, fees_usdt=sync_fee, mode="live")`,
  send `notifier.notify_exit(...)` with `f"{close_reason} [slot {slot.slot_id}]"` as the reason
  label, and after the close run the auto-demote check (Task 5 helper `self._maybe_auto_demote(slot)`).
  The durable-SL ratchet tag block applies only to main-owned positions (slots have no ratchet).
- Path B orphan scan: replace `tracked_symbols = set(self.risk.positions.keys())` with
  `tracked_symbols = set(_build_position_owners(self.risk, self.slots).keys())`.

- [ ] **Step 4: Run suite, all green.**
- [ ] **Step 5: Commit** `git commit -am "fix(sync): reconcile is slot-aware — live slot positions not mis-adopted"`

---

### Task 4: Live entry branch in the slot evaluator

**Files:**
- Modify: `bot.py:1530` `_evaluate_paper_slots` → rename `_evaluate_slots` (update the single call site — grep `_evaluate_paper_slots(`), and `bot.py:645` paper_pos_symbols comprehension to include ALL slots' positions (live slot symbols also need prices for exits): drop the `if slot.paper_mode` filter.

- [ ] **Step 1: Rename + price-coverage edit.** In bot.py:645 change to
`slot_pos_symbols = {s for slot in self.slots for s in slot.risk.positions.keys()}` (rename var, update usage at bot.py:647).

- [ ] **Step 2: Implement the live branch.** In `_evaluate_slots`, replace the unconditional
`slot.risk.open_position(...)` entry block (bot.py:1819-1843) with:

```python
                    if slot.paper_mode:
                        # --- existing paper entry block, unchanged ---
                        slot.risk.open_position(
                            symbol, price, margin, side=direction,
                            atr=atr_val, regime="medium",
                            cycle=self.cycle_count,
                            strategy=_entry_strategy_name
                        )
                        notifier.notify_paper_entry(symbol, direction, price, margin,
                                                    signal.strength, signal.reason)
                    else:
                        # --- LIVE slot entry (spec 2026-06-12) ---
                        # Account-level halts apply to slot entries too
                        # account halts: pause sentinel + main drawdown pause (risk_manager.py:351)
                        if os.path.exists(".pause_trading") or self.risk._drawdown_pause_until > time.time():
                            logger.info(f"[SLOT LIVE] {slot.slot_id} {symbol} entry blocked — account halt")
                            continue
                        order = (self.exchange.open_long(symbol, margin, price)
                                 if direction == "long"
                                 else self.exchange.open_short(symbol, margin, price))
                        if not order:
                            logger.info(f"[SLOT LIVE] {slot.slot_id} {symbol} {direction} — no fill (PostOnly miss), skipping")
                            continue
                        fill_price = self._extract_fill_price(order, price)
                        slot.risk.open_position(symbol, fill_price, margin, side=direction,
                                                atr=atr_val, regime="medium",
                                                cycle=self.cycle_count,
                                                strategy=_entry_strategy_name)
                        pos = slot.risk.positions[symbol]
                        fill_amount = self._extract_fill_amount(order, pos.amount)
                        actual_margin = (fill_amount * fill_price) / Config.LEVERAGE
                        _min_margin = float(os.getenv("MIN_TRADE_MARGIN", "10.0")) * 0.5
                        if actual_margin < _min_margin:
                            logger.warning(f"[SLOT LIVE] {slot.slot_id} {symbol} partial fill ${actual_margin:.4f} < ${_min_margin:.2f} — closing crumb")
                            self.exchange.cancel_open_orders(symbol)
                            closed = (self.exchange.close_long(symbol, fill_amount) if direction == "long"
                                      else self.exchange.close_short(symbol, fill_amount))
                            if closed:
                                slot.risk.close_position(symbol, fill_price, "min_margin_skip", mode="live")
                            continue
                        pos.amount = fill_amount
                        pos.margin = actual_margin
                        pos.entry_strength = signal.strength
                        sl_tp = self.exchange.place_sl_tp(symbol, direction, fill_amount,
                                                          pos.stop_loss, pos.take_profit)
                        pos.sl_order_id = sl_tp.get("sl_order_id") or "software"
                        pos.tp_order_id = sl_tp.get("tp_order_id")
                        if sl_tp.get("sl_order_id"):
                            pos.exchange_sl_price = pos.stop_loss
                        else:
                            logger.warning(f"[SLOT LIVE] [SL FALLBACK] {slot.slot_id} {symbol} exchange SL failed — software SL@{pos.stop_loss:.4f}")
                        notifier.notify_entry(symbol, direction, fill_price, pos.margin,
                                              pos.stop_loss, pos.take_profit,
                                              signal.strength, f"[slot {slot.slot_id}] {signal.reason}")
                        logger.info(f"[SLOT LIVE] {slot.slot_id} ENTRY {direction.upper()} {symbol} | Fill: {fill_price:.4f} | Margin: ${pos.margin:.2f} | {signal.reason}")
```

Keep the shared tail (snapshot logging, `gate_tags`, `_save_state`, `total_entries`,
`_entered_this_symbol`) running for BOTH branches — move it after the if/else. The
`[PAPER]`-prefixed entry log line stays in the paper branch only.

- [ ] **Step 3: Compile + suite.** `py_compile bot.py` then full pytest. Expected: green
(no unit test exercises live entry end-to-end — exchange calls aren't mockable cheaply
here; coverage comes from the audit + paper-parity review in Task 7).

- [ ] **Step 4: Commit** `git commit -am "feat(slots): live entry execution — PostOnly mirror of paper path"`

---

### Task 5: Live exit branch + auto-demote execution

**Files:**
- Modify: `bot.py` slot exit loop (bot.py:1543-1598) and a new `_demote_slot` helper; extend `_process_sentinels` demote handler (bot.py:567-580) to use it.
- Test: `tests/test_live_slot.py` (append demote-path test with mocked exchange)

- [ ] **Step 1: Write failing test for _demote_slot**

```python
def test_demote_slot_closes_position_and_flips_mode(slot, monkeypatch):
    from bot import TradingBot
    slot.set_live()
    slot.risk.open_position("DOGE/USDT:USDT", 0.08, 10.0, side="long")
    calls = {}
    class _FakeExchange:
        def close_long(self, s, a):  calls["closed"] = (s, a); return {"average": 0.079}
        def close_short(self, s, a): calls["closed"] = (s, a); return {"average": 0.079}
        def cancel_open_orders(self, s): calls["cancelled"] = s
        def extract_order_fee(self, o, s=None): return 0.0
    bot = TradingBot.__new__(TradingBot)   # no __init__ — unit-test the helper only
    bot.exchange = _FakeExchange()
    bot._demote_slot(slot, "test reason")
    assert slot.paper_mode is True
    assert calls.get("closed", (None,))[0] == "DOGE/USDT:USDT"
    assert calls.get("cancelled") == "DOGE/USDT:USDT"
    assert slot.risk.positions == {}
    assert slot.risk.closed_trades[-1]["mode"] == "live"
```

- [ ] **Step 2: Run, verify fails** (no `_demote_slot`)

- [ ] **Step 3: Implement `_demote_slot` on TradingBot**

```python
    def _demote_slot(self, slot, reason: str):
        """Demote a live slot to paper: close its real positions at market, cancel
        orders, flip mode. Never leaves a frozen position (DOGE-freeze lesson)."""
        logger.warning(f"[SLOT DEMOTE] {slot.slot_id} → paper ({reason})")
        for symbol in list(slot.risk.positions.keys()):
            pos = slot.risk.positions[symbol]
            try:
                self.exchange.cancel_open_orders(symbol)
                order = (self.exchange.close_long(symbol, pos.amount) if pos.side == "long"
                         else self.exchange.close_short(symbol, pos.amount))
                if order:
                    fill = self._extract_fill_price(order, pos.entry_price, is_exit=True)
                    slot.risk.close_position(symbol, fill, "slot_demote", mode="live",
                                             fees_usdt=self.exchange.extract_order_fee(order, symbol))
                else:
                    logger.error(f"[SLOT DEMOTE] {slot.slot_id} {symbol} close FAILED — reconcile will catch")
            except Exception as e:
                logger.error(f"[SLOT DEMOTE] {slot.slot_id} {symbol} error: {e}")
        slot.set_paper()
        try:
            notifier.send(f"⬇️ Slot <b>{slot.slot_id}</b> auto-demoted to paper — {reason}")
        except Exception:
            pass

    def _maybe_auto_demote(self, slot):
        demote, reason = slot.should_auto_demote()
        if demote:
            self._demote_slot(slot, reason)
```

Note: `_extract_fill_price` falls back to the passed price when the order response
lacks `average` — acceptable for the demote path; reconcile corrects via real fills.

- [ ] **Step 4: Wire the exit loop.** In the slot exit block (bot.py:1543-1598):
  - Wrap the SL-touch and TP-touch close blocks in `if slot.paper_mode:` (live SL/TP
    is enforced by exchange orders + reconcile; software touch-close would double-fire).
  - For adverse_exit / time_exit / trend-flip blocks, branch:

```python
                    if slot.paper_mode:
                        slot.risk.close_position(symbol, price, reason)
                        notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, reason)
                    else:
                        self.exchange.cancel_open_orders(symbol)
                        order = (self.exchange.close_long(symbol, pos.amount) if pos.side == "long"
                                 else self.exchange.close_short(symbol, pos.amount))
                        if not order:
                            logger.error(f"[SLOT LIVE] {slot.slot_id} {symbol} {reason} close FAILED — retry next cycle")
                            continue
                        fill = self._extract_fill_price(order, price, is_exit=True)
                        slot.risk.close_position(symbol, fill, reason, mode="live",
                                                 fees_usdt=self.exchange.extract_order_fee(order, symbol))
                        notifier.notify_exit(symbol, pos.side, pos.entry_price, fill,
                                             pos.pnl_usdt(fill), pos.pnl_percent(fill),
                                             f"{reason} [slot {slot.slot_id}]")
                        self._maybe_auto_demote(slot)
```

  - Update `_process_sentinels` demote handler (bot.py:567-580) to call
    `self._demote_slot(slot, "manual sentinel")` instead of inline `paper_mode = True`,
    and the promote handler (bot.py:555-561) to call `slot.set_live(capital_pct)`.

- [ ] **Step 5: Run suite + compile. Commit** `git commit -am "feat(slots): live exits, demote execution, sentinel wiring"`

---

### Task 6: Reporting propagation

**Files:**
- Modify: `web_dashboard.py:980` (`_LIVE_SLOTS`), `scripts/daily_report.py` (live-slot section)

- [ ] **Step 1:** `web_dashboard.py` — `_LIVE_SLOTS` is computed from state files, not hardcoded:

```python
def _live_slot_ids():
    ids = {"5m_scalp"}
    import glob as _g, json as _j
    for path in _g.glob(os.path.join(BASE_DIR, "trading_state_*_mode.json")):
        try:
            with open(path) as f:
                if not _j.load(f).get("paper_mode", True):
                    ids.add(os.path.basename(path).replace("trading_state_", "").replace("_mode.json", ""))
        except Exception:
            pass
    return ids
```

Replace reads of `_LIVE_SLOTS` with `_live_slot_ids()` (grep all usages; dashboard is
read-only and restart-independent — no pre-restart-audit needed for this file).

- [ ] **Step 2:** `scripts/daily_report.py` — after the existing paper-slot section, add a
"Live Slot" section for any slot whose `trading_state_<id>_mode.json` has `paper_mode: false`:
trades today (from `trading_state_<id>.json` closed_trades with `mode=="live"`), WR, net PnL,
live PnL since promotion, and remaining headroom to the −$5 cap. Follow the file's existing
markdown-section style.

- [ ] **Step 3: Run** `python3 scripts/daily_report.py` (dry run) — verify no exceptions and
the section renders only when a promoted slot exists.

- [ ] **Step 4: Commit** `git commit -am "feat(reporting): dashboard + daily report aware of live slots"`

---

### Task 7: Full verification + audit gate

- [ ] **Step 1:** Full suite: all tests green (expect 65 pre-existing + ~10 new).
- [ ] **Step 2:** `py_compile` every touched file.
- [ ] **Step 3:** Paper-parity review: diff the live branch against the paper branch and
  confirm gate-for-gate identity (strength 0.80, can_enter, conflict, OB gate, tape gate,
  carve-outs) — the live branch must not add or drop a single gate.
- [ ] **Step 4:** Run `/pre-restart-audit` (mandatory — live money).
- [ ] **Step 5:** Commit any audit fixes; push.

### Task 8: Deploy + promote (DO NOT run with Tasks 1-7; separate session/window)

- [ ] **Gate 1:** live-exit watcher has handled ≥2 real exits ([LIVE EXIT] lines in bot.log).
- [ ] **Gate 2:** flat window (`trading_state.json` positions == 0 AND all live-slot state files flat).
- [ ] `rm -rf __pycache__` → kill bot (PID from .bot.pid) → restart (append logs) → verify startup.
- [ ] `echo '{"capital_pct": 0.2}' > .promote_5m_mean_revert` — watch for the
  `[SENTINEL] Slot '5m_mean_revert' PROMOTED` log line + Telegram alert within 60s.
- [ ] Verify `trading_state_5m_mean_revert_mode.json` shows `paper_mode: false`.
- [ ] Watch first live slot entry end-to-end: PostOnly fill → SL/TP placed → snapshot logged.
  Confirm reconcile does NOT adopt it (no `[ENTRY SAFETY]`/orphan lines for the symbol).

**Rollback at any point:** `touch .demote_5m_mean_revert` (runtime, no restart).
