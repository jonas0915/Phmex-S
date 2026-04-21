# Loop Freeze + Early Exit Signal Lag Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent loop freezes on DNS outages and catch profit peaks before they reverse via a new peak-drawdown exit signal.

**Architecture:** (1) Add `_call_with_timeout()` to `exchange.py` wrapping all ccxt REST calls in a 15s thread timeout. (2) Move `time.sleep` inside the watchdog alarm scope. (3) Add `socket.setdefaulttimeout(10)` at startup. (4) Add peak-drawdown signal #4 to `should_exit_early()` with immediate `return True` at 8%+ peak ROI and 3%+ drawdown.

**Tech Stack:** Python 3.14, ccxt, concurrent.futures (stdlib), socket (stdlib)

**Spec:** `docs/superpowers/specs/2026-04-10-loop-freeze-early-exit-fix-design.md`

---

## Task 1: Socket Timeout at Startup

**Files:**
- Modify: `main.py:58-59`

- [ ] **Step 1: Add socket.setdefaulttimeout(10) to main.py**

At the top of `main()`, before `_check_pidfile()`, add the socket timeout:

```python
import socket
socket.setdefaulttimeout(10)  # 10s hard ceiling on all socket ops including DNS
```

The full function start becomes:

```python
def main():
    import socket
    socket.setdefaulttimeout(10)  # 10s hard ceiling on all socket ops including DNS
    _check_pidfile()
    args = parse_args()
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile main.py`
Expected: No output (clean compile)

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "fix: add socket.setdefaulttimeout(10) to prevent DNS hangs"
```

---

## Task 2: Thread-Wrapped REST Calls in exchange.py

**Files:**
- Modify: `exchange.py:1-8` (imports), `exchange.py:46-75` (get_balance, get_ohlcv)
- All `get_*` methods that hit ccxt REST

- [ ] **Step 1: Add _call_with_timeout helper and import**

At the top of `exchange.py`, after the existing imports (line 4), add:

```python
import concurrent.futures
```

Then add the helper method inside the `Exchange` class, right after `__init__` (after line 30):

```python
    def _call_with_timeout(self, fn, *args, timeout=15, **kwargs):
        """Run fn in a thread with hard timeout. Returns None on timeout."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.warning(f"[TIMEOUT] {fn.__name__} timed out after {timeout}s — likely DNS hang")
                return None
```

- [ ] **Step 2: Wrap get_ohlcv**

Replace the ccxt call inside `get_ohlcv` (line 68):

Before:
```python
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> Optional[pd.DataFrame]:
        try:
            ohlcv = self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
```

After:
```python
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> Optional[pd.DataFrame]:
        try:
            ohlcv = self._call_with_timeout(self.client.fetch_ohlcv, symbol, timeframe, limit=limit)
            if ohlcv is None:
                return None
```

- [ ] **Step 3: Wrap get_balance**

Replace the ccxt call inside `get_balance` (line 50):

Before:
```python
            balance = self.client.fetch_balance()
```

After:
```python
            balance = self._call_with_timeout(self.client.fetch_balance)
            if balance is None:
                return self._last_balance.get(currency, 0.0)
```

- [ ] **Step 4: Wrap get_order_book**

Replace the ccxt call inside `get_order_book` (line 79):

Before:
```python
            ob = self.client.fetch_order_book(symbol, limit=depth)
```

After:
```python
            ob = self._call_with_timeout(self.client.fetch_order_book, symbol, limit=depth)
            if ob is None:
                return None
```

- [ ] **Step 5: Wrap remaining REST methods**

Apply the same pattern to these methods — wrap the `self.client.fetch_*` or `self.client.create_*` call:

1. `get_recent_trades` (line 121): wrap `self.client.fetch_trades`
2. `get_cvd` (line 182): wrap `self.client.fetch_trades`
3. `get_funding_rate` (line 227): wrap `self.client.fetch_funding_rate`
4. `get_ticker` (line 241): wrap `self.client.fetch_ticker`
5. `get_open_positions` (line 716): wrap `self.client.fetch_positions`

For each: replace `self.client.fetch_X(...)` with `self._call_with_timeout(self.client.fetch_X, ...)` and add `if result is None: return None` (or the method's existing fallback).

**Do NOT wrap order placement methods** (`place_sl_tp`, `close_long`, `close_short`, `cancel_open_orders`) — those must complete or raise, not silently return None.

- [ ] **Step 6: Syntax check**

Run: `python3 -m py_compile exchange.py`
Expected: No output (clean compile)

- [ ] **Step 7: Commit**

```bash
git add exchange.py
git commit -m "fix: wrap all REST reads in 15s thread timeout to prevent DNS freeze"
```

---

## Task 3: Move time.sleep Inside Watchdog Scope

**Files:**
- Modify: `bot.py:397-419`

- [ ] **Step 1: Restructure the main loop**

Replace the loop structure at bot.py:397-419.

Before:
```python
            while self.running:
                try:
                    signal.signal(signal.SIGALRM, _cycle_timeout_handler)
                    signal.alarm(120)  # 120s watchdog per cycle
                    self._run_cycle()
                    signal.alarm(0)  # cancel watchdog on success
                    self.consecutive_errors = 0
                except TimeoutError as e:
                    signal.alarm(0)
                    self.consecutive_errors += 1
                    logger.error(f"[WATCHDOG] Cycle timed out ({self.consecutive_errors}): {e}")
                except Exception as e:
                    signal.alarm(0)
                    self.consecutive_errors += 1
                    logger.exception(f"Cycle error ({self.consecutive_errors})")
                if self.consecutive_errors >= 5:
                    self.ban_mode = True
                    self.ban_mode_until = time.time() + 600
                    self.ban_extensions = 0
                    logger.warning("[BAN MODE] Entering ban mode for 10 minutes after 5 consecutive errors")
                    self.consecutive_errors = 0
                    notifier.notify_ban_mode(10)
                time.sleep(Config.LOOP_INTERVAL)
```

After:
```python
            while self.running:
                try:
                    signal.signal(signal.SIGALRM, _cycle_timeout_handler)
                    signal.alarm(180)  # 120s cycle + 60s sleep
                    self._run_cycle()
                    self.consecutive_errors = 0
                except TimeoutError as e:
                    self.consecutive_errors += 1
                    logger.error(f"[WATCHDOG] Cycle timed out ({self.consecutive_errors}): {e}")
                except Exception as e:
                    self.consecutive_errors += 1
                    logger.exception(f"Cycle error ({self.consecutive_errors})")
                finally:
                    signal.alarm(0)  # always cancel watchdog
                if self.consecutive_errors >= 5:
                    self.ban_mode = True
                    self.ban_mode_until = time.time() + 600
                    self.ban_extensions = 0
                    logger.warning("[BAN MODE] Entering ban mode for 10 minutes after 5 consecutive errors")
                    self.consecutive_errors = 0
                    notifier.notify_ban_mode(10)
                time.sleep(Config.LOOP_INTERVAL)
```

Wait — the sleep must be INSIDE the try block. Corrected:

```python
            while self.running:
                try:
                    signal.signal(signal.SIGALRM, _cycle_timeout_handler)
                    signal.alarm(180)  # 120s cycle + 60s sleep
                    self._run_cycle()
                    self.consecutive_errors = 0
                    time.sleep(Config.LOOP_INTERVAL)
                    signal.alarm(0)  # cancel watchdog after sleep completes
                except TimeoutError as e:
                    signal.alarm(0)
                    self.consecutive_errors += 1
                    logger.error(f"[WATCHDOG] Cycle timed out ({self.consecutive_errors}): {e}")
                except Exception as e:
                    signal.alarm(0)
                    self.consecutive_errors += 1
                    logger.exception(f"Cycle error ({self.consecutive_errors})")
                if self.consecutive_errors >= 5:
                    self.ban_mode = True
                    self.ban_mode_until = time.time() + 600
                    self.ban_extensions = 0
                    logger.warning("[BAN MODE] Entering ban mode for 10 minutes after 5 consecutive errors")
                    self.consecutive_errors = 0
                    notifier.notify_ban_mode(10)
```

Key changes:
- `signal.alarm(180)` — increased from 120 to cover cycle + sleep
- `time.sleep(Config.LOOP_INTERVAL)` moved INSIDE the try block, after `_run_cycle()` success
- `signal.alarm(0)` now comes AFTER the sleep
- On timeout, the sleep is skipped and the next cycle starts immediately (desired behavior during DNS recovery)

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile bot.py`
Expected: No output (clean compile)

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "fix: move time.sleep inside watchdog alarm scope (was unguarded)"
```

---

## Task 4: Peak Drawdown Signal + Inline peak_price Update

**Files:**
- Modify: `risk_manager.py:112-149`

- [ ] **Step 1: Replace should_exit_early with updated version**

Replace the entire `should_exit_early` method (risk_manager.py lines 112-149):

Before:
```python
    def should_exit_early(self, current_price: float, df) -> bool:
        """Exit early if momentum has reversed and we're in profit.
        Lowered to 3% ROI — early_exit was 100% WR (+$16.24), fires more often at lower threshold."""
        try:
            pnl_pct = self.pnl_percent(current_price)
            if pnl_pct < 3.0:
                return False

            last = df.iloc[-1]
            prev = df.iloc[-2]
            signals = 0

            if self.side == "long":
                if last.get("rsi", 50) < 45:
                    signals += 1
                if "macd" in last and "macd_signal" in last:
                    if last["macd"] < last["macd_signal"] and prev["macd"] >= prev["macd_signal"]:
                        signals += 1
                if "ema_9" in last and "ema_9" in prev:
                    if last["close"] < last["ema_9"] and prev["close"] < prev["ema_9"]:
                        signals += 1
            else:
                if last.get("rsi", 50) > 55:
                    signals += 1
                if "macd" in last and "macd_signal" in last:
                    if last["macd"] > last["macd_signal"] and prev["macd"] <= prev["macd_signal"]:
                        signals += 1
                if "ema_9" in last and "ema_9" in prev:
                    if last["close"] > last["ema_9"] and prev["close"] > prev["ema_9"]:
                        signals += 1

            # At 8%+ ROI, relax to 1 signal — data shows 16 trades leaked at 8-22% ROI
            # because 2-of-3 signals weren't present. 1-of-3 captures them.
            if pnl_pct >= 8.0:
                return signals >= 1
            return signals >= 2
        except Exception:
            return False
```

After:
```python
    def should_exit_early(self, current_price: float, df) -> bool:
        """Exit early if momentum has reversed and we're in profit.
        Signal #4 (peak drawdown) added 2026-04-10: catches reversals at profit peaks
        where lagging indicators (RSI, MACD, EMA) still read bullish."""
        try:
            pnl_pct = self.pnl_percent(current_price)
            if pnl_pct < 3.0:
                return False

            # Update peak_price inline — trailing stop loop runs later in cycle
            if self.side == "long" and current_price > self.peak_price:
                self.peak_price = current_price
            elif self.side == "short" and (current_price < self.peak_price or self.peak_price == 0.0):
                self.peak_price = current_price

            last = df.iloc[-1]
            prev = df.iloc[-2]
            signals = 0

            # Signal 1: RSI reversal
            if self.side == "long":
                if last.get("rsi", 50) < 45:
                    signals += 1
            else:
                if last.get("rsi", 50) > 55:
                    signals += 1

            # Signal 2: MACD fresh bearish crossover
            if "macd" in last and "macd_signal" in last:
                if self.side == "long":
                    if last["macd"] < last["macd_signal"] and prev["macd"] >= prev["macd_signal"]:
                        signals += 1
                else:
                    if last["macd"] > last["macd_signal"] and prev["macd"] <= prev["macd_signal"]:
                        signals += 1

            # Signal 3: Price below EMA-9 for 2 consecutive candles
            if "ema_9" in last and "ema_9" in prev:
                if self.side == "long":
                    if last["close"] < last["ema_9"] and prev["close"] < prev["ema_9"]:
                        signals += 1
                else:
                    if last["close"] > last["ema_9"] and prev["close"] > prev["ema_9"]:
                        signals += 1

            # Signal 4: Peak drawdown — forward-looking reversal detection
            peak_roi = 0.0
            drawdown_from_peak = 0.0
            if self.peak_price > 0 and self.peak_price != self.entry_price:
                if self.side == "long":
                    peak_roi = (self.peak_price - self.entry_price) / self.entry_price * 100 * Config.LEVERAGE
                    drawdown_from_peak = (self.peak_price - current_price) / self.peak_price * 100 * Config.LEVERAGE
                else:
                    peak_roi = (self.entry_price - self.peak_price) / self.entry_price * 100 * Config.LEVERAGE
                    drawdown_from_peak = (current_price - self.peak_price) / self.peak_price * 100 * Config.LEVERAGE

                # Tier 1: peak >= 8% + drawdown >= 3% → immediate exit (no signal count)
                if peak_roi >= 8.0 and drawdown_from_peak >= 3.0:
                    logger.info(f"[EARLY EXIT] {self.symbol} — peak drawdown trigger: "
                                f"peak_roi={peak_roi:.1f}%, drawdown={drawdown_from_peak:.1f}%, pnl={pnl_pct:.1f}%")
                    return True

                # Tier 2: peak 5-8% + drawdown >= 2% → count as 1 signal
                if peak_roi >= 5.0 and drawdown_from_peak >= 2.0:
                    signals += 1

            logger.debug(f"[EARLY EXIT CHECK] {self.symbol} — ROI: {pnl_pct:.1f}%, signals: {signals}/4, "
                         f"peak_roi: {peak_roi:.1f}%, drawdown: {drawdown_from_peak:.1f}%")

            # At 8%+ ROI, relax to 1 signal. Below 8%, need 2 signals.
            if pnl_pct >= 8.0:
                return signals >= 1
            return signals >= 2
        except Exception:
            return False
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile risk_manager.py`
Expected: No output (clean compile)

- [ ] **Step 3: Commit**

```bash
git add risk_manager.py
git commit -m "feat: add peak drawdown signal #4 to early exit — catches profit peaks before reversal"
```

---

## Task 5: Restart Resilience — Update peak_price on Position Restore

**Files:**
- Modify: `bot.py:365-374` (startup sync block)

- [ ] **Step 1: Add peak_price refresh after sync_positions**

After `self.risk.sync_positions(open_pos, ...)` at bot.py:369-370, add peak_price refresh. Find the block:

```python
            elif open_pos:
                # Sync ALL open positions — don't filter by active_pairs
                # (positions may exist on pairs not yet in the scanner/config list)
                if open_pos:
                    self.risk.sync_positions(open_pos, current_cycle=self.cycle_count)
                    logger.info(f"Synced {len(open_pos)} open position(s) from exchange")
```

Add after the `logger.info` line:

```python
                    # Refresh peak_price — may be stale if bot was down while price moved
                    for sym, pos in self.risk.positions.items():
                        try:
                            ticker = self.exchange.get_ticker(sym)
                            if ticker and "last" in ticker:
                                pos.update_trailing_stop(float(ticker["last"]))
                        except Exception as e:
                            logger.debug(f"Could not refresh peak_price for {sym}: {e}")
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile bot.py`
Expected: No output (clean compile)

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "fix: refresh peak_price on position restore after restart"
```

---

## Task 6: Integration Verification

- [ ] **Step 1: Full syntax check on all changed files**

Run: `python3 -m py_compile main.py && python3 -m py_compile exchange.py && python3 -m py_compile bot.py && python3 -m py_compile risk_manager.py && echo "ALL OK"`
Expected: `ALL OK`

- [ ] **Step 2: Grep for stale references**

Run: `grep -n "signal.alarm(120)" bot.py`
Expected: No matches (should be 180 now)

Run: `grep -n ">= 3:" bot.py | grep -i "daily"`
Expected: No matches (should be Config.DAILY_SYMBOL_CAP from earlier fix)

Run: `grep -n "self.client.fetch_ohlcv" exchange.py`
Expected: Should show `_call_with_timeout(self.client.fetch_ohlcv` NOT bare `self.client.fetch_ohlcv`

- [ ] **Step 3: Verify early exit signal logging works**

Run: `grep -n "EARLY EXIT CHECK" risk_manager.py`
Expected: Shows the new debug log line

Run: `grep -n "peak drawdown trigger" risk_manager.py`
Expected: Shows the new info log line for immediate exit

- [ ] **Step 4: Run pre-restart audit**

Run the `/pre-restart-audit` skill before deploying.

- [ ] **Step 5: Commit all if any uncommitted changes remain**

```bash
git status
# If any unstaged changes:
git add main.py exchange.py bot.py risk_manager.py
git commit -m "chore: loop freeze + early exit signal lag fixes — integration verified"
```
