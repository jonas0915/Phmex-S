# v9.0 Assessment-Driven Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the bot's negative edge by addressing the root cause — bad entry quality producing 112 time_exit losses (-$35.50) that erase the only profitable mechanism (early_exit at +$16.68).

**Architecture:** Three-pronged fix: (1) Add aggressive early bail-out for trades going wrong instead of bleeding to time_exit, (2) Add momentum confirmation to confluence entries to filter falling knives, (3) Enrich trade logging so future analysis isn't blind.

**Tech Stack:** Python 3.14, ccxt, Phemex USDT perpetual futures

---

## Assessment Summary (245 trades)

| Metric | Value | Verdict |
|--------|-------|---------|
| Win rate | 35.9% | Below 40% minimum |
| Total PnL | -$23.47 | Losing money |
| Kelly | -0.21 | **No mathematical edge** |
| time_exit trades | 112 (46%) | 93.8% wrong direction |
| early_exit trades | 18 (7%) | 100% WR, only profit source |
| Balance | ~$20.61 | Down from $51 start |

## Root Cause Analysis

**The bot enters trades that go the wrong direction.** 93.8% of time_exit trades were losing at close — not "right direction, weak move" but genuinely bad entries. The confluence strategy gates are simultaneously too strict (blocking good setups in ranging markets where ADX < 30) and too permissive (letting through directionally wrong trades when gates are met).

**Three compounding problems:**

1. **Entry quality**: Confluence requires 5 simultaneous conditions — in trending markets these align but the trade is already late. In ranging markets (most of the time), nothing fires, so the fallback adaptive strategy takes weaker setups.

2. **No early bail-out**: Once entered, a bad trade bleeds for 20-90 minutes to soft time_exit. There's no mechanism to exit quickly when price moves against the position in the first 5-10 minutes.

3. **Blind diagnostics**: Closed trades log `strategy`, `opened_at`, `closed_at` (added in v8) but NOT entry strength, confidence score, or ensemble layers — making it impossible to analyze which confidence levels produce time_exits vs early_exits.

## Codebase API Reference

Key patterns to follow (verified from source):

| Pattern | Correct | Wrong |
|---------|---------|-------|
| Risk manager attribute | `self.risk` | `self.risk_manager` |
| Config access | `Config.LEVERAGE` (class attrs) | `self.config.X` |
| Cycle counter | `self.cycle_count` | `current_cycle` |
| Position PnL method | `pos.pnl_percent(price)` | `pos.get_roi(price)` |
| Cycles held | `self.cycle_count - pos.entry_cycle` | `pos.cycles_held` |
| Strategy name extraction | `_extract_strategy_name(signal.reason)` | `signal.strategy` |
| Signal enum values | `Signal.BUY`, `Signal.SELL` | `"long"`, `"short"` |
| Trade record creation | `risk_manager.py:close_position()` line 455 | bot.py |
| PnL field in closed trades | `pnl_pct` | `pnl_percent` |
| Bot sync model | Synchronous (no async/await) | Async |
| Position dataclass | `risk_manager.py:26-41` | — |

**Position dataclass fields** (risk_manager.py:26-41):
`symbol, side, entry_price, amount, margin, stop_loss, take_profit, trailing_stop_price, peak_price, sl_order_id, tp_order_id, entry_cycle, opened_at, strategy`

**Inline exit pattern** (from flat_exit, bot.py:396-413):
```python
held_min = cycles_held * Config.LOOP_INTERVAL / 60
logger.info(f"[EXIT_REASON] {symbol} — {roi:.1f}% ROI after {held_min:.0f}min (reason)")
if pos.side == "long":
    order = self.exchange.close_long(symbol, pos.amount)
else:
    order = self.exchange.close_short(symbol, pos.amount)
if not order:
    logger.error(f"[EXIT_REASON] Close order failed for {symbol}")
    continue
fill_price = self._extract_fill_price(order, price, is_exit=True)
self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
self.risk.close_position(symbol, fill_price, "exit_reason")
self.exchange.cancel_open_orders(symbol)
notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price,
                     pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "exit_reason")
```

## File Structure

| File | Changes | Purpose |
|------|---------|---------|
| `risk_manager.py` | Modify lines 26-41, 455-483, add method | Add Position fields, enrich close_position, add adverse exit |
| `bot.py` | Modify lines 631-633, add block after 413 | Store confidence at entry, wire adverse_exit, strategy-aware ensemble |
| `strategies.py` | Modify lines 773-825, 828+ | Add momentum confirmation to confluence entries |
| `config.py` | Modify | Add adverse exit config params as class attrs |
| `.env` | Modify | Add adverse exit env vars |

---

## Task 1: Enrich Trade Logging (Diagnostics First)

**Why first:** Every future change needs measurable impact. Without confidence/strength in closed trades, we're blind. Zero-risk (logging only). Note: `strategy`, `opened_at`, `closed_at` already exist in trade records — we're adding `entry_strength`, `confidence`, `ensemble_layers`, and `cycles_held`.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py` (lines 26-41 Position dataclass, lines 455-483 close_position)
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/bot.py` (around line 660 where Position is created after entry)

- [ ] **Step 1: Add fields to Position dataclass**

In `risk_manager.py`, add 3 new fields to the Position dataclass (lines 26-41), after the existing `strategy` field:

```python
    strategy: str = ""       # (existing) strategy name
    entry_strength: float = 0.0   # NEW: signal strength at entry (0.0-1.0)
    confidence: int = 0           # NEW: ensemble confidence (0-6)
    ensemble_layers: str = ""     # NEW: comma-separated confirmed layers
```

- [ ] **Step 2: Set enriched fields on Position after creation in bot.py**

Position is created inside `risk_manager.open_position()` (risk_manager.py:390-403), NOT directly in bot.py. Bot.py calls `self.risk.open_position(...)` at line 648 and then accesses the position at line 649. Following the existing mutation pattern at lines 650-651 (where `pos.amount` is set after creation), add the new fields AFTER the position is created:

```python
# After line 649: pos = self.risk.positions[symbol]
# (existing pattern: pos.amount and order IDs are set here)
pos.entry_strength = signal.strength
pos.confidence = confidence               # already computed at line 628
pos.ensemble_layers = ",".join(layers)     # already computed at line 628
```

Note: `confidence` and `layers` are already computed at line 628: `confidence, layers = self._compute_confidence(...)`. `signal.strength` is from the TradeSignal returned by the strategy. This matches the existing pattern where Position fields are mutated after creation.

- [ ] **Step 3: Add enriched fields to close_position() trade record**

In `risk_manager.py:close_position()` (lines 455-483), add the new fields to the `trade` dict after the existing `closed_at` field:

Add these 4 fields to the existing `trade` dict, after the `"closed_at"` line:

```python
        # NEW enriched fields for analysis
        "entry_strength": pos.entry_strength,
        "confidence": pos.confidence,
        "ensemble_layers": pos.ensemble_layers,
        "duration_s": time.time() - pos.opened_at,
```

Note: Uses `duration_s` (elapsed seconds) instead of `cycles_held` because `close_position()` doesn't receive `current_cycle`. Duration is more useful for analysis anyway.

- [ ] **Step 4: Syntax check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile risk_manager.py && python -m py_compile bot.py && echo "OK"
```
Expected: "OK"

- [ ] **Step 5: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
git add risk_manager.py bot.py
git commit -m "feat: enrich closed trade logging with entry_strength, confidence, ensemble_layers, duration"
```

---

## Task 2: Add Adverse Movement Exit (Quick Bail-Out)

**Why:** 93.8% of time_exit trades were wrong-direction. Instead of bleeding 20-90 min, exit within 10 min if price confirms the trade is wrong. This is the highest-impact change.

**Logic:** If after N cycles (default 10 = 10 min), the trade ROI is worse than -X% (default -3% ROI), exit immediately. A good scalp should be green or flat within 10 minutes. At 10x leverage, -3% ROI = -0.3% price move.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/config.py` — add class attrs
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/.env` — add env vars
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py` — add `should_adverse_exit()` on Position
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/bot.py` — wire adverse_exit in exit loop

- [ ] **Step 1: Add config params**

In `.env`, add:
```env
# Adverse exit — bail out of wrong-direction trades early
ADVERSE_EXIT_CYCLES=10        # Check after 10 cycles (10 min)
ADVERSE_EXIT_THRESHOLD=-3.0   # Exit if ROI worse than -3%
```

In `config.py`, add as class attributes (matching existing pattern like `STOP_LOSS_PERCENT`):
```python
    ADVERSE_EXIT_CYCLES = int(os.getenv("ADVERSE_EXIT_CYCLES", "10"))
    ADVERSE_EXIT_THRESHOLD = float(os.getenv("ADVERSE_EXIT_THRESHOLD", "-3.0"))
```

- [ ] **Step 2: Add `should_adverse_exit()` as a method on Position (risk_manager.py)**

Add this method to the Position class (after `pnl_percent`, around line 136):

```python
    def should_adverse_exit(self, current_cycle: int, current_price: float) -> bool:
        """Exit early if trade is going wrong direction after N cycles.
        Catches bad entries before they bleed to time_exit."""
        cycles_held = current_cycle - self.entry_cycle
        if cycles_held < Config.ADVERSE_EXIT_CYCLES:
            return False

        roi = self.pnl_percent(current_price)
        if roi <= Config.ADVERSE_EXIT_THRESHOLD:
            logger.info(
                f"[ADVERSE EXIT] {self.symbol} ROI={roi:.1f}% after "
                f"{cycles_held} cycles (threshold={Config.ADVERSE_EXIT_THRESHOLD}%)"
            )
            return True
        return False
```

- [ ] **Step 3: Wire adverse_exit into bot.py exit loop**

In `bot.py`, add adverse_exit check AFTER flat_exit (line 413) and BEFORE time_exit (line 435). Follow the exact inline exit pattern used by flat_exit:

```python
            # ── Adverse exit — bail out of wrong-direction trades early ──
            if pos.should_adverse_exit(self.cycle_count, price):
                cycles_held = self.cycle_count - pos.entry_cycle
                held_min = cycles_held * Config.LOOP_INTERVAL / 60
                roi = pos.pnl_percent(price)
                logger.info(f"[ADVERSE EXIT] {symbol} — {roi:.1f}% ROI after {held_min:.0f}min")
                if pos.side == "long":
                    order = self.exchange.close_long(symbol, pos.amount)
                else:
                    order = self.exchange.close_short(symbol, pos.amount)
                if not order:
                    logger.error(f"[ADVERSE EXIT] Close order failed for {symbol}")
                    continue
                fill_price = self._extract_fill_price(order, price, is_exit=True)
                self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                self.risk.close_position(symbol, fill_price, "adverse_exit")
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price,
                                     pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "adverse_exit")
                continue
```

- [ ] **Step 4: Simulate impact on historical trades**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && python3 -c "
import json
with open('trading_state.json') as f:
    state = json.load(f)
time_exits = [t for t in state['closed_trades'] if t['reason'] in ('time_exit', 'hard_time_exit')]
would_catch = [t for t in time_exits if t['pnl_pct'] <= -3.0]
print(f'Would catch {len(would_catch)}/{len(time_exits)} time_exits early')
print(f'Total loss from those trades: \${sum(t[\"pnl_usdt\"] for t in would_catch):.2f}')
remaining = [t for t in time_exits if t['pnl_pct'] > -3.0]
print(f'Remaining time_exits: {len(remaining)} (avg pnl: {sum(t[\"pnl_pct\"] for t in remaining)/max(len(remaining),1):.1f}%)')
"
```

- [ ] **Step 5: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile bot.py && python -m py_compile risk_manager.py && python -m py_compile config.py && echo "OK"
```

- [ ] **Step 6: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
git add risk_manager.py bot.py config.py .env
git commit -m "feat: add adverse_exit — bail out of wrong-direction trades within 10 min"
```

---

## Task 3: Tighten Soft Time Exits

**Why:** Current soft time exits are 15-45 min. With adverse_exit catching the worst -3% losers at 10 min, we can tighten soft exits to reduce the remaining bleed from trades that are losing but not yet at -3%.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py` (lines 14-23)

- [ ] **Step 1: Reduce soft time exit limits**

Update `STRATEGY_TIME_EXITS` dict (lines 14-22) and `DEFAULT_TIME_EXIT` (line 23). Keep `trend_scalp` in the dict. Hard limits unchanged:

```python
STRATEGY_TIME_EXITS = {
    "keltner_squeeze":          {"soft": 30, "hard": 120},   # was 45
    "trend_pullback":           {"soft": 20, "hard": 90},    # was 30
    "trend_scalp":              {"soft": 20, "hard": 90},    # was 30
    "momentum_continuation":    {"soft": 15, "hard": 60},    # was 20
    "vwap_reversion":           {"soft": 10, "hard": 45},    # was 15
    "htf_confluence_pullback":  {"soft": 20, "hard": 75},    # was 25
    "htf_confluence_vwap":      {"soft": 10, "hard": 45},    # was 15
}
DEFAULT_TIME_EXIT = {"soft": 30, "hard": 120}               # was soft: 45
```

Rationale: With adverse_exit catching -3%+ losers at 10 min, the remaining trades at soft limit are "weak" not "wrong" — cut them ~33% faster.

- [ ] **Step 2: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile risk_manager.py && echo "OK"
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
git add risk_manager.py
git commit -m "feat: tighten soft time exits — cut weak trades faster with adverse_exit backstop"
```

---

## Task 4: Add Momentum Confirmation to Confluence Entries

**Why:** Confluence entries check structure (VWAP, ADX, pullback) but not momentum direction. A pullback to EMA-21 in an uptrend is only valid if the pullback is ending (momentum turning back up). Without this, the bot enters falling knives.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/strategies.py` (lines 773-825 confluence_pullback, 828+ confluence_vwap)

- [ ] **Step 1: Add momentum confirmation to htf_confluence_pullback**

In `htf_confluence_pullback()`, insert AFTER `direction` is determined (after line 782 where `direction = Signal.SELL` is set) and BEFORE the `if direction is None` check (line 784):

```python
    # Momentum confirmation: last candle must show recovery in direction
    # For longs: close > open (green candle) OR RSI rising
    # For shorts: close < open (red candle) OR RSI falling
    if direction is not None:
        last_close = df["close"].iloc[-1]
        last_open = df["open"].iloc[-1]
        prev_rsi = df["rsi_14"].iloc[-3] if len(df) > 3 else rsi

        if direction == Signal.BUY:
            momentum_ok = (last_close > last_open) or (rsi > prev_rsi)
        else:  # Signal.SELL
            momentum_ok = (last_close < last_open) or (rsi < prev_rsi)

        if not momentum_ok:
            side_str = "long" if direction == Signal.BUY else "short"
            logger.debug(
                f"confluence_pullback: {side_str} rejected — no momentum confirmation "
                f"(candle={'green' if last_close > last_open else 'red'}, "
                f"RSI {prev_rsi:.1f}→{rsi:.1f})"
            )
            direction = None  # Reset direction so it falls through to HOLD return
```

- [ ] **Step 2: Add momentum confirmation to htf_confluence_vwap**

In `htf_confluence_vwap()`, same pattern after direction is determined. For VWAP reversion (mean-reversion strategy), the confirmation is a reversal candle — price bouncing off the extreme:

```python
    # Momentum confirmation for mean reversion: candle shows reversal
    if direction is not None:
        last_close = df["close"].iloc[-1]
        last_open = df["open"].iloc[-1]
        prev_rsi = df["rsi_14"].iloc[-3] if len(df) > 3 else rsi

        if direction == Signal.BUY:
            # Buying oversold: need green candle or RSI turning up
            momentum_ok = (last_close > last_open) or (rsi > prev_rsi)
        else:
            # Selling overbought: need red candle or RSI turning down
            momentum_ok = (last_close < last_open) or (rsi < prev_rsi)

        if not momentum_ok:
            side_str = "long" if direction == Signal.BUY else "short"
            logger.debug(
                f"confluence_vwap: {side_str} rejected — no reversal momentum "
                f"(candle={'green' if last_close > last_open else 'red'}, "
                f"RSI {prev_rsi:.1f}→{rsi:.1f})"
            )
            direction = None
```

- [ ] **Step 3: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile strategies.py && echo "OK"
```

- [ ] **Step 4: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
git add strategies.py
git commit -m "feat: add momentum confirmation to confluence entries — filter falling knives"
```

---

## Task 5: Strategy-Aware Ensemble Confidence Thresholds

**Why:** The flat 3/6 ensemble gate blocks entries when HTF is ranging (ADX < 20). In ranging markets, layers like "HTF trend" and "Hurst trending" will never confirm — but VWAP reversion trades don't need them. Strategy-aware thresholds let the right trades through.

**Risk note:** Start conservative — keep reversion at 3/6 initially. Only lower to 2/6 AFTER measuring adverse_exit effectiveness at the 25-trade milestone. This avoids compounding risk of more bad entries without the safety net proven.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/bot.py` (lines 631-633)

- [ ] **Step 1: Make confidence threshold strategy-aware**

Replace the flat `confidence < 3` check at bot.py line 631-633. The `strat_name` variable is already computed at line 625:

```python
        # Strategy-aware confidence thresholds
        # Start conservative: all at 3. Lower reversion to 2 after proving adverse_exit works.
        CONFIDENCE_THRESHOLDS = {
            "htf_confluence_pullback": 3,   # trend — needs HTF alignment
            "htf_confluence_vwap": 3,       # reversion — keep at 3 initially, lower later
            "vwap_reversion": 3,            # reversion — keep at 3 initially
            "bb_mean_reversion": 3,         # reversion — keep at 3 initially
            "momentum_continuation": 3,     # momentum — needs alignment
            "trend_pullback": 3,            # trend — needs alignment
            "keltner_squeeze": 3,           # breakout — needs alignment
        }
        min_confidence = CONFIDENCE_THRESHOLDS.get(strat_name, 3)

        if confidence < min_confidence:
            logger.info(
                f"[ENSEMBLE SKIP] {symbol} {direction} — confidence {confidence}/{min_confidence} "
                f"too low for {strat_name}, need {min_confidence}+"
            )
            continue
```

This replaces the current code:
```python
        if confidence < 3:
            logger.info(f"[ENSEMBLE SKIP] {symbol} {direction} — confidence {confidence}/6 too low, need 3+")
            continue
```

- [ ] **Step 2: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile bot.py && echo "OK"
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
git add bot.py
git commit -m "feat: strategy-aware ensemble thresholds — infrastructure for per-strategy confidence gates"
```

---

## Task 6: Reset Trading State for Clean Measurement

**Why:** The current 245 trades include pre-blacklist toxic symbols and pre-fix data. To measure v9.0 impact, we need a clean slate. Archive old state, reset counters, keep balance.

**Files:**
- Archive: `/Users/jonaspenaso/Desktop/Phmex-S/trading_state.json`

- [ ] **Step 1: Archive current state**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
cp trading_state.json trading_state_v8_245trades.json
```

- [ ] **Step 2: Reset trade counters (keep balance/config)**

Edit `trading_state.json`: set `closed_trades` to `[]`, `trade_results` to `[]`, `total_trades` to `0`. Keep `peak_balance` set to current balance (~$20.61). Keep `positions` as `{}`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
git add trading_state_v8_245trades.json trading_state.json
git commit -m "feat: archive v8 state (245 trades), reset counters for v9.0 clean measurement"
```

---

## Task 7: Post-Fix Audit & Deploy

**Why:** MANDATORY per Jonas directive (see memory/lessons.md → "Post-Fix Audit Rule"). Every change audited before restart.

- [ ] **Step 1: Deploy audit agents on ALL modified files**

Dispatch parallel agents to review:
- `bot.py` — verify adverse_exit wired correctly using inline exit pattern, confidence threshold logic correct, Position constructor updated with new fields
- `strategies.py` — verify momentum confirmation uses `Signal.BUY`/`Signal.SELL` (not strings), insertion point is after direction determination, no existing logic broken
- `risk_manager.py` — verify Position dataclass fields added correctly, `should_adverse_exit()` uses `Config.X` pattern, `close_position()` trade dict includes new fields, no side effects on existing exit paths
- `config.py` / `.env` — verify new params use class attribute pattern (`Config.ADVERSE_EXIT_CYCLES`), env var names match

- [ ] **Step 2: Full compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
rm -rf __pycache__
python -m py_compile bot.py
python -m py_compile strategies.py
python -m py_compile risk_manager.py
python -m py_compile config.py
python -m py_compile exchange.py
python -m py_compile scanner.py
echo "All compile checks passed"
```

- [ ] **Step 3: Restart bot**

```bash
cd ~/Desktop/Phmex-S
kill -9 $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
```

- [ ] **Step 4: Verify startup in logs**

```bash
tail -30 ~/Desktop/Phmex-S/logs/bot.log
```
Expect: Startup banner, 5 pairs loaded, WS feeds connected, no errors.

- [ ] **Step 5: Monitor first 2-3 cycles**

```bash
tail -f ~/Desktop/Phmex-S/logs/bot.log | head -100
```
Expect: Cycle runs, strategy evaluation logged with ensemble confidence, no crashes.

---

## Measurement Plan

| Milestone | When | Check |
|-----------|------|-------|
| 10 trades | ~1-2 days | Are adverse_exits firing? What % of trades? |
| 25 trades | ~3-4 days | Win rate vs v8 (target: >40%). If adverse_exit proven, lower reversion confidence to 2/6 |
| 50 trades | ~1 week | Kelly positive? early_exit still dominant profit? |
| 100 trades | ~2 weeks | Full assessment — continue, tune, or pivot? |

**Success criteria for v9.0:**
- time_exit drops from 46% to <25% of exits
- adverse_exit catches wrong-direction trades within 10 min
- Win rate improves from 35.9% to >42%
- Kelly turns positive (any positive value)
- early_exit remains 100% WR and primary profit source

**Failure triggers (revert to v8.0):**
- Win rate drops below 30% at 25 trades
- adverse_exit fires on >60% of trades (too aggressive)
- Balance drops below $15 (25% drawdown from current)

## Reversion Confidence Lowering (Deferred)

At 25-trade milestone, IF adverse_exit is working (catching 20-40% of would-be time_exits) AND win rate is stable, update `CONFIDENCE_THRESHOLDS` in bot.py:
```python
"htf_confluence_vwap": 2,   # reversion — proven safe with adverse_exit
"vwap_reversion": 2,
"bb_mean_reversion": 2,
```
This gives reversion strategies more entries in ranging markets while adverse_exit provides the safety net.
