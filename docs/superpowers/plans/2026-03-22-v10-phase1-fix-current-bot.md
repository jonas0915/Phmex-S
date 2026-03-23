# v10.0 Phase 1: Fix Current Bot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply 6 research-backed fixes to the current bot to move WR above 36.6% breakeven threshold and reduce time_exit losses.

**Architecture:** Modify exit logic, trailing stop, and entry filters in existing files. No architectural changes — Phase 2 handles the slot refactor.

**Tech Stack:** Python 3.14, ccxt, Phemex USDT perpetual futures

---

## Codebase API Reference

| Pattern | Correct |
|---------|---------|
| Risk manager attr | `self.risk` |
| Config access | `Config.X` (class attrs) |
| Cycle counter | `self.cycle_count` |
| Position PnL | `pos.pnl_percent(price)` |
| Strategy name | `_extract_strategy_name(signal.reason)` |
| Bot sync model | Synchronous (no async/await) |
| Inline exit pattern | close_long/short → _extract_fill_price → _set_cooldown_if_loss → self.risk.close_position → cancel_open_orders → notifier.notify_exit → continue |

---

## Task 1: Widen Adverse Exit -3% → -5% ROI

**Why:** -0.3% price is noise for ETH/SOL (1.2 sigma). Research says pros use 0.5-0.8% price = -5% to -8% ROI.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/.env` line 54
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/config.py` line 58

- [ ] **Step 1: Update .env**

Change `ADVERSE_EXIT_THRESHOLD=-3.0` to `ADVERSE_EXIT_THRESHOLD=-5.0`

- [ ] **Step 2: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile config.py && echo "OK"
```

- [ ] **Step 3: Commit**

```bash
git add .env && git commit -m "fix: widen adverse exit -3% → -5% ROI (research: -0.3% price is noise)"
```

- [ ] **Step 4: Update tracker**

```bash
python tracker_update.py check p1t1
```

---

## Task 2: Remove Soft Time Exits

**Why:** 567K backtests (KJ Trading): tight time exits destroy performance. Keep only 4h hard exit as safety net. Adverse exit at -5% handles the bad trades.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py` lines 152-182 (should_time_exit)

- [ ] **Step 1: Simplify should_time_exit to hard-only**

Replace the current `should_time_exit()` method (lines 152-182) with a simplified version that only checks the hard limit:

```python
    def should_time_exit(self, current_cycle: int, current_price: float = 0.0) -> tuple[bool, bool]:
        """Hard time exit only — 4h unconditional safety net.
        Soft time exits removed per 567K backtest study:
        tight time exits destroy performance.
        Adverse exit at -5% ROI handles wrong-direction trades."""
        hard_limit = 240  # 4 hours at 60s loop = 240 cycles
        cycles_held = current_cycle - self.entry_cycle
        roi = self.pnl_percent(current_price) if current_price > 0 else -99.0

        if cycles_held >= hard_limit:
            # Extend by 50% if trade is profitable (>= 5% ROI)
            if roi >= 5.0:
                extended = int(hard_limit * 1.5)
                if cycles_held < extended:
                    return False, False
            return True, True

        return False, False
```

- [ ] **Step 2: STRATEGY_TIME_EXITS and DEFAULT_TIME_EXIT are now unused — remove them**

Delete lines 14-23 (the STRATEGY_TIME_EXITS dict and DEFAULT_TIME_EXIT). They are no longer referenced.

- [ ] **Step 3: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile risk_manager.py && echo "OK"
```

- [ ] **Step 4: Verify no other code references STRATEGY_TIME_EXITS**

```bash
grep -r "STRATEGY_TIME_EXITS\|DEFAULT_TIME_EXIT" /Users/jonaspenaso/Desktop/Phmex-S/*.py
```
Expected: No matches (only risk_manager.py had them, now removed).

- [ ] **Step 5: Commit**

```bash
git add risk_manager.py && git commit -m "fix: remove soft time exits — 567K study says tight time exits destroy performance"
```

- [ ] **Step 6: Update tracker**

```bash
python tracker_update.py check p1t2
```

---

## Task 3: Add Tiered Trailing Stop

**Why:** Protect winning trades — never give back more than 1/3 of peak profit. Based on FMZ Quant tiered system and AdaptiveTrend study (removing trailing stop dropped Sharpe by 0.73).

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py` lines 46-69 (update_trailing_stop)

- [ ] **Step 1: Replace update_trailing_stop with tiered version**

Replace the current `update_trailing_stop()` method (lines 46-69) with:

```python
    def update_trailing_stop(self, current_price: float):
        """Tiered trailing stop — the bigger the winner, the tighter the trail.
        Never give back more than 1/3 of peak profit.

        | ROI Reached | Min Lock-In | Trail from Peak |
        |-------------|-------------|-----------------|
        | +5%         | +2%         | 3% from peak    |
        | +8%         | +4%         | 4% from peak    |
        | +10%        | +6%         | 4% from peak    |
        | +15%        | +10%        | 5% from peak    |
        | +20%        | +15%        | 5% from peak    |
        """
        if not Config.TRAILING_STOP:
            return

        roi = self.pnl_percent(current_price)
        if roi < 5.0:
            return  # Not yet in profit territory for trailing

        # Determine tier
        tiers = [
            (20.0, 15.0, 5.0),  # (roi_threshold, lock_in_pct, trail_pct)
            (15.0, 10.0, 5.0),
            (10.0,  6.0, 4.0),
            ( 8.0,  4.0, 4.0),
            ( 5.0,  2.0, 3.0),
        ]

        lock_in_pct = 2.0
        trail_pct = 3.0
        for threshold, lock, trail in tiers:
            if roi >= threshold:
                lock_in_pct = lock
                trail_pct = trail
                break

        # Compute trail price from current peak
        if self.side == "long":
            if current_price > self.peak_price or self.peak_price == 0.0:
                self.peak_price = current_price
            trail_price = self.peak_price * (1 - trail_pct / 100 / Config.LEVERAGE)
            # Compute lock-in floor price
            lock_price = self.entry_price * (1 + lock_in_pct / 100 / Config.LEVERAGE)
            # Use the higher of trail and lock-in
            new_trail = max(trail_price, lock_price)
            if self.trailing_stop_price is None or new_trail > self.trailing_stop_price:
                self.trailing_stop_price = new_trail
        elif self.side == "short":
            if current_price < self.peak_price or self.peak_price == 0.0:
                self.peak_price = current_price
            trail_price = self.peak_price * (1 + trail_pct / 100 / Config.LEVERAGE)
            lock_price = self.entry_price * (1 - lock_in_pct / 100 / Config.LEVERAGE)
            new_trail = min(trail_price, lock_price)
            if self.trailing_stop_price is None or new_trail < self.trailing_stop_price:
                self.trailing_stop_price = new_trail
```

- [ ] **Step 2: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile risk_manager.py && echo "OK"
```

- [ ] **Step 3: Commit**

```bash
git add risk_manager.py && git commit -m "feat: tiered trailing stop — progressive profit lock-in, never give back >1/3 of peak"
```

- [ ] **Step 4: Update tracker**

```bash
python tracker_update.py check p1t3
```

---

## Task 4: Add Weekend Kelly Multiplier

**Why:** Weekend returns are +85-92% higher than weekdays (p < 0.001, 1,672 trading days, 10 cryptos). Size up on weekends.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/bot.py` — where Kelly margin is computed (around line 682)

- [ ] **Step 1: Find the Kelly sizing code and add weekend multiplier**

In bot.py, find where the margin/position size is calculated (around line 682, where `calculate_kelly_margin` is called or where margin is set). Add a weekend check:

```python
import datetime

# After margin is calculated from Kelly:
if datetime.datetime.utcnow().weekday() in (5, 6):  # Saturday=5, Sunday=6
    margin = min(margin * 1.3, Config.MAX_TRADE_MARGIN)  # 1.3x weekend boost, respect cap
```

- [ ] **Step 2: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile bot.py && echo "OK"
```

- [ ] **Step 3: Commit**

```bash
git add bot.py && git commit -m "feat: 1.3x weekend Kelly multiplier (weekend returns +85-92%, p<0.001)"
```

- [ ] **Step 4: Update tracker**

```bash
python tracker_update.py check p1t4
```

---

## Task 5: Add Candle-Boundary Entry Bias

**Why:** +0.58 basis points at minutes 0, 15, 30, 45 (t-stat > 9). All other minutes have negative average returns. Bias entries toward candle opens.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/bot.py` — in the entry loop, before placing the order

- [ ] **Step 1: Add candle-boundary check before entry**

In bot.py, in the entry loop, BEFORE the order is placed (around line 687), add a timing check:

```python
# Candle-boundary entry bias: prefer entries near 5m candle opens
# Research: +0.58bps at min 0,5,10,15... (t-stat > 9)
import datetime
now_min = datetime.datetime.utcnow().minute
candle_offset = now_min % 5  # 0 = candle open, 4 = candle about to close
if candle_offset >= 3:  # Last 2 minutes of candle — skip, wait for next open
    logger.debug(f"[TIMING] {symbol} — skipping entry, {5-candle_offset}min to next candle open")
    continue
```

This skips entries in the last 2 minutes of each 5m candle (minutes x:03, x:04, x:08, x:09, etc.), biasing toward the first 3 minutes after candle open.

- [ ] **Step 2: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile bot.py && echo "OK"
```

- [ ] **Step 3: Commit**

```bash
git add bot.py && git commit -m "feat: candle-boundary entry bias — skip last 2min of each 5m candle (t-stat >9)"
```

- [ ] **Step 4: Update tracker**

```bash
python tracker_update.py check p1t5
```

---

## Task 6: Re-enable bb_mean_reversion with Strict Regime Gate

**Why:** Mean reversion works at 2-30 min horizons but ONLY in ranging conditions (Wen et al. 2022, arxiv). Currently disabled. Re-enable with strict gate: ADX < 25 AND Hurst < 0.50.

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/strategies.py` — adaptive_strategy (lines 651-720) or confluence_strategy (lines 951-984)

- [ ] **Step 1: Add bb_mean_reversion to the confluence strategy with regime gate**

In `confluence_strategy()` (strategies.py lines 951-984), add bb_mean_reversion as a third option when the market is ranging:

After the existing confluence_pullback and confluence_vwap calls, add:

```python
    # Mean reversion in confirmed ranging conditions
    # Research: works at 2-30 min horizons when ADX < 25 AND Hurst < 0.50
    if htf_adx < 25:
        hurst_val = df.iloc[-1].get("hurst", 0.5) if "hurst" in df.columns else 0.5
        if hurst_val < 0.50:
            bb_signal = bb_mean_reversion_strategy(df, ob)
            if bb_signal.signal != Signal.HOLD and bb_signal.strength > best_strength:
                best_signal = bb_signal
                best_strength = bb_signal.strength
```

- [ ] **Step 2: Add "bb_mean_reversion" to _extract_strategy_name if not already there**

Check bot.py lines 17-36. The mapping `"bb" in r or "mean reversion" in r` → `"bb_mean_reversion"` already exists. No change needed.

- [ ] **Step 3: Compile check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && rm -rf __pycache__ && python -m py_compile strategies.py && echo "OK"
```

- [ ] **Step 4: Commit**

```bash
git add strategies.py && git commit -m "feat: re-enable bb_mean_reversion with strict regime gate (ADX<25 + Hurst<0.50)"
```

- [ ] **Step 5: Update tracker**

```bash
python tracker_update.py check p1t6
```

---

## Task 7: Post-Fix Audit & Deploy

**Why:** MANDATORY per Jonas directive. Every change audited before restart.

- [ ] **Step 1: Git tag pre-phase1 state for rollback**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git tag v9.0-pre-phase1
```

- [ ] **Step 2: Deploy audit agents on all modified files**

Parallel audit: risk_manager.py, bot.py, strategies.py, .env/config.py

- [ ] **Step 3: Full compile check**

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

- [ ] **Step 4: Restart bot**

```bash
cd ~/Desktop/Phmex-S
kill -9 $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
```

- [ ] **Step 5: Verify startup**

```bash
sleep 5 && tail -30 logs/bot.log
```

- [ ] **Step 6: Monitor first 2-3 cycles**

Verify: no errors, strategy evaluation running, no crashes.
