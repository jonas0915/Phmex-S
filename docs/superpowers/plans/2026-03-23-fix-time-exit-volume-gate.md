# Fix Time Exit Bug + Volume Gate Optimization

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the flat_exit timing bug that causes 105 trades to bleed for 4 hours instead of exiting at 10 min, and optimize the volume gate based on 258-trade data analysis.

**Architecture:** Two targeted fixes in risk_manager.py and strategies.py. No new strategies or structural changes. Both changes are data-backed with clear before/after metrics.

**Tech Stack:** Python, existing Phmex-S codebase

**Expected Impact:**
- flat_exit bug fix: recovers estimated $12-15 from 68 trades that would have been flat_exit (58.8% WR) instead of time_exit (1.9% WR)
- Volume gate: eliminates ~58 losing trades (vol < 0.8x bucket: -$3.53 total)

---

### Task 1: Fix FLAT_EXIT_CYCLES Bug

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py:195`

**Context:** `FLAT_EXIT_CYCLES = 240` is set to 4 hours (240 cycles x 60s). The comment says "after 10 min" but the value is 24x too large. This causes trades to sit for 4 hours bleeding value instead of being exited at ~10 min when still near breakeven. 105 time_exit trades lost $37.88 at 1.9% WR. flat_exit has 58.8% WR when it fires correctly.

Research (Mar 21 deep session + Mar 23 web research) confirms: 5m scalp trades should exit within 15-25 min if flat. Jonathan Kinlay's HFT research shows optimal hold time of ~15 min on 3-min bars.

- [ ] **Step 1: Read current flat_exit code**

Read `/Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py` lines 191-200 to verify current state.

- [ ] **Step 2: Fix FLAT_EXIT_CYCLES from 240 to 15**

Change line 195 in `risk_manager.py`:
```python
# Before:
FLAT_EXIT_CYCLES = 240  # 240 × 60s = 4 hrs

# After:
FLAT_EXIT_CYCLES = 15   # 15 × 60s = 15 min
```

Why 15 not 10: Research says 15-25 min is optimal. 10 cycles (10 min) may be slightly too aggressive — adverse_exit already handles -3% ROI at 10 min. 15 min gives the trade one more chance to move before cutting.

- [ ] **Step 3: Update the comment**

Ensure the comment accurately reflects the new value:
```python
FLAT_EXIT_CYCLES = 15   # 15 min at 60s/cycle — exit stagnant trades near breakeven
```

- [ ] **Step 4: Compile check**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -c "import risk_manager; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Verify no other references to the old value**

Search for any hardcoded 240 related to flat_exit in bot.py or other files.
Run: `grep -n "240\|FLAT_EXIT" /Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py /Users/jonaspenaso/Desktop/Phmex-S/bot.py`

---

### Task 2: Raise Volume Gate from 0.5x to 0.8x

**Files:**
- Modify: `/Users/jonaspenaso/Desktop/Phmex-S/strategies.py:755`

**Context:** We lowered the volume gate from 0.8x to 0.5x earlier today. 258-trade data analysis shows:
- vol < 0.6x: 47.6% WR, -$1.67 (losing)
- vol 0.6-0.8x: 48.6% WR, -$1.86 (losing)
- vol 0.8-1.0x: **72.7% WR, +$2.97** (sweet spot)
- vol 1.0-1.5x: 39.5% WR, +$1.41 (profitable)

The data is unambiguous: 0.8x is the optimal threshold. Below that, entries lose money.

- [ ] **Step 1: Read current volume gate**

Read `/Users/jonaspenaso/Desktop/Phmex-S/strategies.py` lines 754-756 to verify current state.

- [ ] **Step 2: Change volume gate from 0.5x to 0.8x**

```python
# Before:
if vol_avg <= 0 or volume < vol_avg * 0.5:
    return TradeSignal(Signal.HOLD, f"confluence_pullback: vol {volume/max(vol_avg,1e-10):.2f}x < 0.5x", 0.0)

# After:
if vol_avg <= 0 or volume < vol_avg * 0.8:
    return TradeSignal(Signal.HOLD, f"confluence_pullback: vol {volume/max(vol_avg,1e-10):.2f}x < 0.8x", 0.0)
```

- [ ] **Step 3: Compile check**

Run: `/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -c "import strategies; print('OK')"`
Expected: `OK`

---

### Task 3: Audit and Restart

**Files:**
- All modified files from Tasks 1-2

- [ ] **Step 1: Deploy audit agent**

Run a code review agent on the two changed files to verify no regressions.

- [ ] **Step 2: Clear cache and restart bot**

```bash
kill -9 $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
cd ~/Desktop/Phmex-S && rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
```

- [ ] **Step 3: Verify bot is running and new code is active**

```bash
ps aux | grep "Python.*main" | grep -v grep
```

- [ ] **Step 4: Monitor first 3 cycles for correct behavior**

Check logs for:
- Volume gate rejections should say `< 0.8x` (not 0.5x)
- No errors or crashes
- flat_exit should fire at ~15 cycles if a position goes stagnant

---

### Task 4: Update Memory and Spec

- [ ] **Step 1: Update the momentum router design spec**

Add a note to `/Users/jonaspenaso/Desktop/Phmex-S/docs/superpowers/specs/2026-03-23-momentum-router-design.md` documenting:
- Volume gate reverted to 0.8x based on 258-trade data analysis
- flat_exit bug found and fixed (240 → 15 cycles)

- [ ] **Step 2: Update memory with today's findings**

Save to memory:
- flat_exit bug and fix
- Volume gate data (0.8-1.0x is sweet spot)
- Today's momentum_cont results (first trade was a win)

---

## Monitoring Plan (Post-Deploy)

**First 10 trades:**
- Are flat_exits firing at ~15 min? (should see "flat_exit" reason in logs)
- Are time_exits decreasing? (should be rare now)
- Volume gate: are pullback entries only at 0.8x+?

**At 25 trades:**
- WR check: target > 45% (up from 36.4%)
- flat_exit WR: should stay ~58%+
- time_exit count: should be < 10% of trades (was 42%)

**At 50 trades:**
- Full Kelly recalculation
- If Kelly is still negative, reassess strategy
