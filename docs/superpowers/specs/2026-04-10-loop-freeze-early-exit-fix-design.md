# Loop Freeze + Early Exit Signal Lag Fix — Design Spec

**Date:** 2026-04-10
**Status:** Reviewed — audit-corrected v3 (gap scenario fixed)
**Triggered by:** SUI LONG on Apr 9 hit +10% unrealized ROI, loop froze for 35 min (DNS outage), trade reversed to -12% loss. Early exit never ran.

---

## Problem 1: Loop Freeze on DNS Outage

### Root Cause

At 8:28 AM PT on Apr 9, all 5 WebSocket feeds dropped (DNS: "Cannot connect to ws.phemex.com"). The main loop froze for 35 minutes — no cycles ran, no position checks, no exits.

The freeze path:
1. WS goes stale (>120s without update) -> REST fallback triggered
2. `exchange.get_ohlcv()` calls `ccxt.fetch_ohlcv()` which blocks at DNS resolution
3. ccxt `timeout: 10000` only covers HTTP read/write, NOT DNS resolution
4. `signal.alarm(120)` should interrupt, but on macOS SIGALRM may not interrupt blocking DNS syscalls
5. `time.sleep(Config.LOOP_INTERVAL)` at bot.py:419 is outside the try/except — completely unguarded

### Fix: Thread-Wrapped REST + Extended Watchdog

**Part A — Thread-wrapped REST calls with hard timeout**

Wrap `exchange.get_ohlcv()` in a thread with a 15-second hard timeout. If DNS hangs, the thread is abandoned and the loop continues.

Location: `exchange.py` — add a `_call_with_timeout(fn, *args, timeout=15)` helper.

Apply to all REST calls that could hang:
- `bot.py:585` — main OHLCV fetch fallback
- `bot.py:529` — ban-mode recovery check
- `bot.py:1253` — paper slot OHLCV fetch
- `bot.py:221` — HTF data fetch (`_fetch_htf_data`)

Implementation:
```python
import concurrent.futures

def _call_with_timeout(fn, *args, timeout=15, **kwargs):
    """Run fn in a thread with hard timeout. Returns None on timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning(f"[TIMEOUT] {fn.__name__} timed out after {timeout}s")
            return None
```

Add to `exchange.py` as a method and wrap ALL public REST methods internally. This protects every call site in bot.py automatically — not just `get_ohlcv` but also `get_order_book` (bot.py:926), `get_open_positions` (bot.py:1473), `get_balance` (bot.py:824), `get_cvd` (bot.py:966), and `get_funding_rate` (bot.py:237). Wrapping at the exchange layer means any new REST call added in the future is also protected.

**Part A.1 — Global socket timeout (prevents thread leak)**

Zombie thread prevention: when `_call_with_timeout` abandons a thread, the DNS call inside it can still block indefinitely. Add at bot startup (in `main.py` or top of `bot.py`):

```python
import socket
socket.setdefaulttimeout(10)  # 10s hard ceiling on all socket operations including DNS
```

This ensures abandoned threads terminate within 10s rather than accumulating.

**Part B — Move sleep inside watchdog scope**

Move `time.sleep(Config.LOOP_INTERVAL)` from bot.py:419 (outside try/except) to inside the try block so `signal.alarm(120)` covers it.

Before:
```python
try:
    signal.alarm(120)
    self._run_cycle()
    signal.alarm(0)
except TimeoutError:
    ...
time.sleep(Config.LOOP_INTERVAL)  # UNGUARDED
```

After:
```python
try:
    signal.alarm(180)  # 120s cycle + 60s sleep
    self._run_cycle()
    time.sleep(Config.LOOP_INTERVAL)
    signal.alarm(0)
except TimeoutError:
    signal.alarm(0)
    ...
```

Alarm value increased from 120 to 180 to account for the sleep duration.

---

## Problem 2: Early Exit Signal Lag

### Root Cause

`should_exit_early()` at risk_manager.py:112-149 checks 3 reversal signals:
1. RSI < 45 (for longs)
2. MACD fresh bearish crossover (edge-triggered, must happen on current candle)
3. Price below EMA-9 for 2 consecutive candles

At +10% ROI, all 3 signals read "bullish" because they confirm reversals AFTER they happen. At the peak, RSI is 60-80, MACD is above signal, price is above EMA-9.

At 8%+ ROI, only 1-of-3 signals needed — but all 3 are lagging, so 0-of-3 fire.

### Fix: Add Peak Drawdown Signal (#4)

Add a 4th signal to `should_exit_early()`: **drawdown from peak price**.

Logic: If the position previously reached a high ROI (tracked via `peak_price`) but has since pulled back significantly, that pullback IS the reversal signal — no need to wait for lagging indicators to confirm.

```python
# Signal 4: Peak drawdown — forward-looking reversal detection
peak_roi = 0.0
drawdown_from_peak = 0.0
if self.peak_price > 0:
    if self.side == "long":
        peak_roi = (self.peak_price - self.entry_price) / self.entry_price * 100 * Config.LEVERAGE
        drawdown_from_peak = (self.peak_price - current_price) / self.peak_price * 100 * Config.LEVERAGE
    else:
        peak_roi = (self.entry_price - self.peak_price) / self.entry_price * 100 * Config.LEVERAGE
        drawdown_from_peak = (current_price - self.peak_price) / self.peak_price * 100 * Config.LEVERAGE

    # At high peak ROI (>= 8%), this signal alone triggers immediate exit
    # (bypasses the normal signal count requirement).
    # This prevents the "gap scenario" where peak_roi was 10%, current drops to 7%,
    # signal #4 fires but 2-of-4 is required and no other signal has caught up.
    if peak_roi >= 8.0 and drawdown_from_peak >= 3.0:
        logger.info(f"[EARLY EXIT] {self.symbol} — peak drawdown trigger: "
                    f"peak_roi={peak_roi:.1f}%, drawdown={drawdown_from_peak:.1f}%")
        return True  # Immediate exit — no signal count needed

    # At moderate peak ROI (5-8%), count as one signal toward the 2-of-N requirement
    if peak_roi >= 5.0 and drawdown_from_peak >= 2.0:
        signals += 1
```

**Thresholds — two tiers:**
- **Peak ROI >= 8% + drawdown >= 3%: IMMEDIATE EXIT** — bypasses signal count entirely. If the position reached 8%+ and has since pulled back 3%, price action alone confirms the reversal. This is the critical fix for the SUI scenario.
- **Peak ROI 5-8% + drawdown >= 2%: counts as 1 signal** — contributes to the normal 2-of-N requirement at moderate profit levels.

**Why this works:**
- The SUI Apr 9 trade peaked at +10% ROI. When price pulled back 3% from peak (to ~+7% current ROI), the `peak_roi >= 8.0` branch fires `return True` immediately — no signal count needed.
- This eliminates the "gap scenario" where pnl drops below the 1-of-N tier before the drawdown threshold is reached.
- At lower peaks (5-8%), it still requires a confirming signal, avoiding false exits on modest pullbacks.
- The trailing stop (4% trail at 10% ROI, exits at ~6% ROI) remains as the hard backstop if this somehow doesn't fire.

**Critical: Execution order fix required.**

`update_trailing_stop()` currently runs at bot.py:782 — AFTER `should_exit_early()` at bot.py:622. This means `peak_price` is one cycle stale when signal #4 evaluates.

Fix: Update `peak_price` inline at the top of `should_exit_early()` before checking signals:

```python
# Update peak_price inline (trailing stop loop runs later in cycle)
if self.side == "long" and current_price > self.peak_price:
    self.peak_price = current_price
elif self.side == "short" and (current_price < self.peak_price or self.peak_price == 0.0):
    self.peak_price = current_price
```

This ensures signal #4 always evaluates against the current cycle's peak, not the previous cycle's.

**Restart resilience:** `peak_price` is persisted to `trading_state.json` and restored on restart. After a restart, if the market moved significantly while the bot was down, `peak_price` may be stale-low. Fix: in `bot.py` at the startup sync block (after `sync_positions()` returns, around line 365-370), fetch current prices and call `pos.update_trailing_stop(current_price)` for each restored position. This must happen in `bot.py` (not inside `sync_positions`) because `sync_positions` has no access to current market prices.

### Logging Addition

Currently there is ZERO logging when `should_exit_early` evaluates but returns False. Add debug logging:

```python
if pnl_pct >= 3.0:
    logger.debug(f"[EARLY EXIT CHECK] {self.symbol} — ROI: {pnl_pct:.1f}%, signals: {signals}/3, "
                 f"peak_roi: {peak_roi:.1f}%, drawdown: {drawdown_from_peak:.1f}%")
```

This makes future debugging possible without cluttering production logs.

---

## Files Changed

| File | Change |
|------|--------|
| `exchange.py` | Add `_call_with_timeout()` helper, wrap REST calls |
| `bot.py` | Move `time.sleep` inside watchdog scope, increase alarm to 180s, wrap HTF fetch at line 221 |
| `risk_manager.py` | Add peak drawdown signal #4, inline peak_price update, add debug logging |
| `main.py` or `bot.py` (top) | Add `socket.setdefaulttimeout(10)` at startup |

## Constraints Respected

- No profit-lock re-added (removed intentionally in v4.0)
- Trailing stop system untouched (already working)
- Paper slots: `should_exit_early()` is shared — paper slots get the fix too
- Exit reason stays `"early_exit"` — no new exit_reason tag needed
- No Telegram/dashboard changes needed (existing early_exit reporting covers it)

## Risk Assessment

- **Loop freeze fix:** Near-zero risk. Thread timeout is a safety net — if it fires, the bot just skips one REST call and retries next cycle. Moving sleep inside watchdog is a structural improvement.
- **Peak drawdown signal:** Low risk. It's additive (signal #4), doesn't change existing signal logic. Tiered drawdown thresholds (2% at 2-of-3, 3% at 1-of-3) prevent false triggers from candle noise while still catching real reversals.
- **Combined:** The SUI Apr 9 trade would have been caught by either fix independently — the loop freeze fix keeps the bot alive, and the peak drawdown `return True` bypasses signal counting entirely at 8%+ peak ROI.
- **Layered safety:** At 10% peak ROI — early exit fires at 3% drawdown (~7% ROI) via immediate `return True`. If that somehow fails, trailing stop catches it at 4% trail (~6% ROI). Two independent safety nets.
