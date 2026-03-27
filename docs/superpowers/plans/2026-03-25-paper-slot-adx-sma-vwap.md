# ADX+SMA+VWAP Paper Slot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a paper trading slot that runs the current confluence strategy with an additional SMA(9)+SMA(15)+VWAP gate, tracking simulated results alongside the live slot for comparison.

**Architecture:** The existing slot system (`StrategySlot`) provides isolated `RiskManager` instances per slot but is not wired into the main loop. We add a single paper slot with a new strategy function, wire paper slot evaluation into `_run_cycle()` after the main entry block, and add paper-specific Telegram notifications and daily report sections.

**Tech Stack:** Python 3.14, ccxt, Telegram Bot API, existing indicator pipeline (SMA 9/15 and VWAP already computed)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `strategies.py` | Modify (~1010) | Add `confluence_sma_vwap_strategy` — wraps `confluence_strategy` with SMA+VWAP gate |
| `bot.py` | Modify (~101, ~820) | Add paper slot definition + wire paper slot evaluation into cycle |
| `notifier.py` | Modify (append) | Add `notify_paper_entry()` and `notify_paper_exit()` with blue emoji |
| `scripts/daily_report.py` | Modify (append) | Add paper slot comparison section to report + Telegram message |

No new files. No indicator changes (SMA 9, SMA 15, VWAP already in pipeline).

---

### Task 1: Add Paper Notification Functions to notifier.py

**Files:**
- Modify: `notifier.py` (append after line 98)

- [ ] **Step 1: Add notify_paper_entry()**

```python
def notify_paper_entry(symbol: str, side: str, price: float, margin: float, strength: float, reason: str):
    emoji = "🔵" if side == "long" else "🟣"
    direction = "LONG" if side == "long" else "SHORT"
    send(
        f"{emoji} <b>[PAPER] {direction} ENTRY — {symbol}</b>  [{BOT_NAME}]\n"
        f"Price:    ${price:.4f}\n"
        f"Margin:   ${margin:.2f} USDT (simulated)\n"
        f"Strength: {strength:.2f}\n"
        f"Reason:   {reason}"
    )
```

- [ ] **Step 2: Add notify_paper_exit()**

```python
def notify_paper_exit(symbol: str, side: str, entry: float, exit_price: float, pnl: float, pnl_pct: float, reason: str):
    emoji = "🔷" if pnl >= 0 else "🔶"
    sign = "+" if pnl >= 0 else ""
    send(
        f"{emoji} <b>[PAPER] EXIT — {symbol}</b>  [{BOT_NAME}]\n"
        f"Entry: ${entry:.4f}  →  Exit: ${exit_price:.4f}\n"
        f"PnL:   <b>{sign}${pnl:.2f} USDT ({sign}{pnl_pct:.1f}%)</b>\n"
        f"Reason: {reason}"
    )
```

- [ ] **Step 3: Syntax check**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile notifier.py`

---

### Task 2: Add confluence_sma_vwap_strategy to strategies.py

**Files:**
- Modify: `strategies.py` (add function before STRATEGIES dict ~line 1274, add to STRATEGIES dict)

- [ ] **Step 1: Add the strategy function**

Insert before the `STRATEGIES` dict. This wraps `confluence_strategy` with an additional SMA+VWAP alignment gate:

```python
def confluence_sma_vwap_strategy(df, orderbook=None, htf_df=None) -> TradeSignal:
    """Confluence strategy + SMA(9)/SMA(15)/VWAP directional gate.
    Requires price aligned with SMA structure AND VWAP before allowing entry."""
    # Run base confluence strategy first
    signal = confluence_strategy(df, orderbook, htf_df)
    if signal.signal == Signal.HOLD:
        return signal

    # Get current values from the completed candle
    last = df.iloc[-2]
    close = last["close"]
    sma9 = last.get("sma_9", 0)
    sma15 = last.get("sma_15", 0)
    vwap_val = last.get("vwap", 0)

    if sma9 == 0 or sma15 == 0 or vwap_val == 0:
        return signal  # indicators not ready, pass through

    # SMA+VWAP directional gate
    if signal.signal == Signal.BUY:
        if not (close > sma9 and sma9 > sma15 and close > vwap_val):
            return TradeSignal(Signal.HOLD, "SMA+VWAP gate: long alignment failed", 0.0)
    elif signal.signal == Signal.SELL:
        if not (close < sma9 and sma9 < sma15 and close < vwap_val):
            return TradeSignal(Signal.HOLD, "SMA+VWAP gate: short alignment failed", 0.0)

    # Passed both confluence AND SMA+VWAP — boost strength slightly
    return TradeSignal(signal.signal, signal.reason + " +SMA/VWAP", min(signal.strength + 0.03, 1.0))
```

- [ ] **Step 2: Register in STRATEGIES dict**

Add to the STRATEGIES dict at line ~1274:

```python
    "confluence_sma_vwap":      confluence_sma_vwap_strategy,
```

- [ ] **Step 3: Syntax check**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile strategies.py`

---

### Task 3: Add Paper Slot Definition to bot.py

**Files:**
- Modify: `bot.py` (after line 141, inside `self.slots` list)

- [ ] **Step 1: Add the paper slot to the slots list**

Add before the closing `]` of `self.slots` (after the `8h_funding` slot):

```python
            StrategySlot(
                slot_id="5m_sma_vwap",
                strategy_name="confluence_sma_vwap",
                timeframe="5m",
                max_positions=2,
                capital_pct=0.0,  # Paper only — no real capital
                paper_mode=True,
            ),
```

- [ ] **Step 2: Syntax check**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py`

---

### Task 4: Wire Paper Slot Evaluation into _run_cycle()

**Files:**
- Modify: `bot.py` (after slot logging block ~line 828, add paper evaluation loop)

This is the core change. After the main live trading loop completes and slot stats are logged, evaluate paper slots against the same market data.

- [ ] **Step 1: Add import for STRATEGIES at top of bot.py**

Verify `from strategies import STRATEGIES` already exists. If not, add it alongside existing strategy imports.

- [ ] **Step 2: Add paper slot evaluation method to TradingBot class**

Add this method to the `TradingBot` class (after `_run_cycle` or at end of class):

```python
    def _evaluate_paper_slots(self, active_pairs: list, prices: dict):
        """Evaluate paper slots — simulate entries/exits without placing real orders."""
        for slot in self.slots:
            if not slot.paper_mode or not slot.is_active:
                continue

            strategy_fn = STRATEGIES.get(slot.strategy_name)
            if not strategy_fn:
                continue

            # --- Paper exits first (check existing paper positions) ---
            for symbol in list(slot.risk.positions.keys()):
                price = prices.get(symbol)
                if not price:
                    continue
                pos = slot.risk.positions[symbol]

                # Check SL
                if pos.side == "long" and price <= pos.stop_loss:
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    slot.risk.close_position(symbol, price, "stop_loss")
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, "stop_loss")
                    continue
                if pos.side == "short" and price >= pos.stop_loss:
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    slot.risk.close_position(symbol, price, "stop_loss")
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, "stop_loss")
                    continue

                # Check TP
                if pos.side == "long" and price >= pos.take_profit:
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    slot.risk.close_position(symbol, price, "take_profit")
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, "take_profit")
                    continue
                if pos.side == "short" and price <= pos.take_profit:
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    slot.risk.close_position(symbol, price, "take_profit")
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, "take_profit")
                    continue

                # Check adverse exit
                if pos.should_adverse_exit(self.cycle_count, price):
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    slot.risk.close_position(symbol, price, "adverse_exit")
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, "adverse_exit")
                    continue

                # Check time exit
                should_exit, is_hard = pos.should_time_exit(self.cycle_count, price)
                if should_exit:
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    reason = "hard_time_exit" if is_hard else "time_exit"
                    slot.risk.close_position(symbol, price, reason)
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, reason)
                    continue

            # --- Paper entries ---
            for symbol in active_pairs:
                if not slot.can_enter(symbol, self.slots):
                    continue
                # Also skip if live bot already has position (avoid double-counting)
                if symbol in self.risk.positions:
                    continue

                price = prices.get(symbol)
                if not price:
                    continue

                try:
                    df = self.exchange.get_candles(symbol, slot.timeframe, limit=200)
                    if df is None or len(df) < 50:
                        continue
                    from indicators import add_indicators
                    df = add_indicators(df)
                    ob = self.exchange.get_orderbook(symbol)
                    htf_df = self._get_htf_data(symbol)
                    signal = strategy_fn(df, ob, htf_df=htf_df)
                except Exception as e:
                    logger.debug(f"[PAPER] {slot.slot_id} error on {symbol}: {e}")
                    continue

                if signal.signal == Signal.HOLD:
                    continue
                if signal.strength < 0.80:
                    continue

                # Simulate entry with $10 margin
                direction = "long" if signal.signal == Signal.BUY else "short"
                margin = 10.0
                atr_val = df.iloc[-2].get("atr", 0) if len(df) > 1 else 0

                slot.risk.open_position(
                    symbol, price, margin, side=direction,
                    atr=atr_val, regime="medium",
                    cycle=self.cycle_count,
                    strategy=slot.strategy_name
                )
                pos = slot.risk.positions[symbol]
                notifier.notify_paper_entry(
                    symbol, direction, price, margin,
                    signal.strength, signal.reason
                )
                slot.total_entries += 1
                logger.info(
                    f"[PAPER] {slot.slot_id} ENTRY {direction.upper()} {symbol} | "
                    f"Price: {price:.4f} | Strength: {signal.strength:.2f} | {signal.reason}"
                )
```

- [ ] **Step 3: Call _evaluate_paper_slots at end of _run_cycle**

Add this call right before the slot logging block (before line 823):

```python
        # Evaluate paper slots
        try:
            self._evaluate_paper_slots(self.active_pairs, prices)
        except Exception as e:
            logger.debug(f"[PAPER] Slot evaluation error: {e}")
```

Where `prices` is the dict of current prices already available in `_run_cycle`. If `prices` isn't in scope at that point, build it from `self.exchange.get_price(symbol)` for each active pair.

- [ ] **Step 4: Verify the Signal import**

Ensure `from strategies import Signal` is imported in bot.py (it likely already is via `from strategies import STRATEGIES, Signal`).

- [ ] **Step 5: Syntax check**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py`

---

### Task 5: Add Paper Slot Section to Daily Report

**Files:**
- Modify: `scripts/daily_report.py` (add paper slot comparison after the main report)

- [ ] **Step 1: Add paper slot stats to the report**

After the alerts section in `generate_report()`, add:

```python
    # Paper slot comparison
    paper_state_file = os.path.join(BOT_DIR, "trading_state_5m_sma_vwap.json")
    if os.path.exists(paper_state_file):
        with open(paper_state_file) as f:
            paper_state = json.load(f)
        paper_closed = paper_state.get("closed_trades", [])
        paper_today = []
        for t in paper_closed:
            closed_at = t.get("closed_at", 0)
            if closed_at:
                trade_date = datetime.fromtimestamp(closed_at).strftime("%Y-%m-%d")
                if trade_date == date_str:
                    paper_today.append(t)
        paper_all_wins = sum(1 for t in paper_closed if t.get("pnl_usdt", 0) > 0)
        paper_all_pnl = sum(t.get("pnl_usdt", 0) for t in paper_closed)
        paper_all_wr = (paper_all_wins / len(paper_closed) * 100) if paper_closed else 0
        paper_today_wins = sum(1 for t in paper_today if t.get("pnl_usdt", 0) > 0)
        paper_today_pnl = sum(t.get("pnl_usdt", 0) for t in paper_today)
        paper_today_wr = (paper_today_wins / len(paper_today) * 100) if paper_today else 0

        report += f"""
## Paper Slot: ADX+SMA+VWAP
### Today
| Metric | Live | Paper |
|--------|------|-------|
| Trades | {len(today_trades)} | {len(paper_today)} |
| Win Rate | {today_wr:.0f}% | {paper_today_wr:.0f}% |
| PnL | ${today_pnl:.2f} | ${paper_today_pnl:.2f} |

### All Time
| Metric | Live | Paper |
|--------|------|-------|
| Trades | {len(closed)} | {len(paper_closed)} |
| Win Rate | {wr:.0f}% | {paper_all_wr:.0f}% |
| PnL | ${total_pnl:.2f} | ${paper_all_pnl:.2f} |
"""
```

- [ ] **Step 2: Add paper comparison to Telegram message**

In the `send_telegram()` function, add after the main message:

```python
    # Add paper slot comparison if available
    paper_state_file = os.path.join(BOT_DIR, "trading_state_5m_sma_vwap.json")
    if os.path.exists(paper_state_file):
        with open(paper_state_file) as f:
            ps = json.load(f)
        pc = ps.get("closed_trades", [])
        pt = [t for t in pc if t.get("closed_at") and datetime.fromtimestamp(t["closed_at"]).strftime("%Y-%m-%d") == date_str]
        pt_wins = sum(1 for t in pt if t.get("pnl_usdt", 0) > 0)
        pt_pnl = sum(t.get("pnl_usdt", 0) for t in pt)
        pt_wr = (pt_wins / len(pt) * 100) if pt else 0
        pc_wins = sum(1 for t in pc if t.get("pnl_usdt", 0) > 0)
        pc_pnl = sum(t.get("pnl_usdt", 0) for t in pc)
        pc_wr = (pc_wins / len(pc) * 100) if pc else 0
        pt_sign = "+" if pt_pnl >= 0 else ""
        pc_sign = "+" if pc_pnl >= 0 else ""
        msg += (
            f"\n🔵 <b>Paper Slot (ADX+SMA+VWAP)</b>\n"
            f"Today: {len(pt)} trades | {pt_wr:.0f}% WR | {pt_sign}${pt_pnl:.2f}\n"
            f"Total: {len(pc)} trades | {pc_wr:.0f}% WR | {pc_sign}${pc_pnl:.2f}\n"
        )
```

- [ ] **Step 3: Syntax check**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile scripts/daily_report.py`

---

### Task 6: Pre-Restart Audit

- [ ] **Step 1: Clear __pycache__**

```bash
rm -rf __pycache__
```

- [ ] **Step 2: Syntax check all modified files**

```bash
python -m py_compile strategies.py
python -m py_compile bot.py
python -m py_compile notifier.py
python -m py_compile scripts/daily_report.py
```

- [ ] **Step 3: Run /pre-restart-audit**

Deploy audit agents on all 4 modified files. Verify:
- Paper slot cannot affect live trading (no real orders from paper path)
- Paper slot uses its own RiskManager state file
- No regressions to live entry/exit logic
- Telegram messages clearly distinguish paper from live
- Daily report handles missing paper state file gracefully

- [ ] **Step 4: Restart bot**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
kill -9 $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
```

- [ ] **Step 5: Verify bot started and paper slot is logging**

```bash
tail -50 logs/bot.log | grep -E "SLOT|PAPER"
```

Expected: See `[SLOT] 5m_sma_vwap (PAPER/ACTIVE)` in the cycle output.
