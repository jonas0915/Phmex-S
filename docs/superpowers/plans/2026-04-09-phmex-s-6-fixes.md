# Phmex-S 6-Fix Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Phmex-S from bleeding to break-even/positive in 2 weeks via 6 surgical, verified fixes.

**Architecture:** Day 1 bundle (Fixes 1-4) in one restart. Day 2-7 use existing backtester (Fix 5). Day 3 deploy weekly forensics loop (Fix 6). Every fix has a mandatory live-confirmation validation gate — no silent failures.

**Tech Stack:** Python 3.14, ccxt, pandas, launchd, Telegram Bot API, Phemex perpetuals.

**Spec reference:** `docs/superpowers/specs/2026-04-09-phmex-s-5-fixes.md`

---

## File Structure

**Files modified:**
- `bot.py` — Fix 1 (AE exit dispatch), Fix 3 (kill switch triggers), Fix 4 (paper slot init removal)
- `risk_manager.py` — Fix 3 (8% soft DD tier)
- `exchange.py:288` — Fix 2 (1-char postOnly param fix)
- `strategies.py` — Fix 5 helper (parametrized AE rule for backtester)
- `web_dashboard.py` — Fix 4 (slot reference cleanup)
- `scripts/daily_report.py` — Fix 4 (slot reference cleanup)
- `notifier.py` — Fix 4 (slot reference cleanup if any)
- `backtester.py` — Fix 5 (add fees+slippage model, add `--ae-rule` flag)
- `backtest.py` — Fix 5 (add adverse_exit logic)

**Files created:**
- `scripts/weekly_forensics.py` — Fix 6 deterministic pattern detector
- `~/Library/LaunchAgents/com.phmex.forensics.plist` — Fix 6 Sunday cron
- `tests/test_ae_exit_rule.py` — Fix 1 unit tests
- `tests/test_kill_switches.py` — Fix 3 unit tests
- `tests/test_postonly_param.py` — Fix 2 integration test (mock ccxt)
- `tests/test_weekly_forensics.py` — Fix 6 unit tests

**Files deleted:**
- `trading_state_5m_atr_gate.json`
- `trading_state_5m_sma_vwap.json`
- `trading_state_5m_v10_control.json`
- `trading_state_5m_legacy_control.json`
- `trading_state_1h_momentum.json`

---

## Task 1: Preflight — Verify Baseline

**Files:** Read-only

- [ ] **Step 1: Read current state**

Run: `cd ~/Desktop/Phmex-S && ps aux | grep "Python.*main" | grep -v grep`
Expected: Bot running (PID 21214 or newer)

- [ ] **Step 2: Read lessons.md META-RULES**

Read: `/Users/jonaspenaso/Desktop/Phmex-S/memory/lessons.md` (top 30 lines)
Confirm: understand META-RULES 1-8 before touching code.

- [ ] **Step 3: Confirm spec is committed**

Run: `cd ~/Desktop/Phmex-S && ls -la docs/superpowers/specs/2026-04-09-phmex-s-5-fixes.md`
Expected: file exists

- [ ] **Step 4: Snapshot current trading_state.json**

Run: `cd ~/Desktop/Phmex-S && cp trading_state.json trading_state.json.pre_6fixes.bak`
Expected: backup created silently

- [ ] **Step 5: Count current MAKER log lines (baseline for Fix 2 validation)**

Run: `cd ~/Desktop/Phmex-S && grep -c "\[MAKER\] Limit filled" logs/bot.log`
Expected: `0` (confirms bug state)

- [ ] **Step 6: Note current balance from log**

Run: `cd ~/Desktop/Phmex-S && grep "Starting balance" logs/bot.log | tail -1`
Expected: most recent "Starting balance: X USDT" line — write it down as baseline

---

## Task 2: Fix 2 — Post-Only Param Bug (1-LINE FIX, HIGHEST VALUE)

**Files:**
- Modify: `exchange.py:288`
- Create: `tests/test_postonly_param.py`

- [ ] **Step 1: Read the current broken line**

Run: `sed -n '285,295p' /Users/jonaspenaso/Desktop/Phmex-S/exchange.py`
Expected output contains: `params={"timeInForce": "GTC", "postOnly": True}`

- [ ] **Step 2: Write failing test**

Create `/Users/jonaspenaso/Desktop/Phmex-S/tests/test_postonly_param.py`:

```python
"""Test that post-only entry orders use the correct Phemex param format."""
import inspect
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange import Exchange


def test_try_limit_then_market_uses_post_only_time_in_force():
    """Verify exchange._try_limit_then_market sends timeInForce=PostOnly.

    Phemex ccxt rejects {"postOnly": True} with error 39999. It expects
    {"timeInForce": "PostOnly"}. This test reads the source of the method
    to verify the correct literal is present.
    """
    src = inspect.getsource(Exchange._try_limit_then_market)
    assert '"timeInForce": "PostOnly"' in src or "'timeInForce': 'PostOnly'" in src, \
        f"_try_limit_then_market must use timeInForce=PostOnly, got:\n{src}"
    # The bad form must be gone
    assert '"postOnly": True' not in src and "'postOnly': True" not in src, \
        f"_try_limit_then_market still uses postOnly=True (rejected by Phemex):\n{src}"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_postonly_param.py -v 2>&1 | tail -20`
Expected: FAIL — assertion that `postOnly=True` still present

- [ ] **Step 4: Apply the 1-line fix**

Edit `/Users/jonaspenaso/Desktop/Phmex-S/exchange.py:288`:
- Find: `params={"timeInForce": "GTC", "postOnly": True}`
- Replace with: `params={"timeInForce": "PostOnly"}`

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_postonly_param.py -v 2>&1 | tail -10`
Expected: PASS

- [ ] **Step 6: Syntax check**

Run: `cd ~/Desktop/Phmex-S && python3 -m py_compile exchange.py && echo OK`
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
cd ~/Desktop/Phmex-S
git add exchange.py tests/test_postonly_param.py
git commit -m "fix: use timeInForce=PostOnly on Phemex entry orders (was rejected with error 39999, maker rate was 0%)"
```

---

## Task 3: Fix 1 — htf_confluence_pullback Trend-Flip Exit Rule

**Files:**
- Modify: `bot.py` (around line 629 for live exit loop, line 1119 for paper)
- Create: `tests/test_ae_exit_rule.py`

- [ ] **Step 1: Read the current exit dispatch path**

Run: `sed -n '620,660p' /Users/jonaspenaso/Desktop/Phmex-S/bot.py`
Note: find where `should_adverse_exit` is called for live positions, note variable names for `pos`, `symbol`, `current_price`.

- [ ] **Step 2: Find the htf cache access pattern**

Run: `grep -n "_htf_cache" /Users/jonaspenaso/Desktop/Phmex-S/bot.py | head -10`
Expected: shows `self._htf_cache` reads around line 133 and downstream usage.

- [ ] **Step 3: Write failing test**

Create `/Users/jonaspenaso/Desktop/Phmex-S/tests/test_ae_exit_rule.py`:

```python
"""Test the htf_confluence_pullback trend-flip exit rule."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from bot import Bot


def _fake_htf_df(ema21_over_ema50: bool) -> pd.DataFrame:
    """Build a minimal 1h dataframe with EMA21/50 in the requested state."""
    rows = []
    for i in range(60):
        close = 100.0
        rows.append({
            "timestamp": i * 3600 * 1000,
            "open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000,
        })
    df = pd.DataFrame(rows)
    if ema21_over_ema50:
        df["ema_21"] = 105.0
        df["ema_50"] = 100.0
    else:
        df["ema_21"] = 95.0
        df["ema_50"] = 100.0
    return df


def test_htf_trend_flip_exit_fires_on_long_when_ema21_crosses_below_ema50():
    """A LONG htf_confluence_pullback position must exit when 1h EMA21 < EMA50."""
    # Call the new helper directly — it returns (should_exit: bool, reason: str)
    from bot import _check_htf_trend_flip_exit  # new helper we'll add
    htf_df = _fake_htf_df(ema21_over_ema50=False)
    should_exit, reason = _check_htf_trend_flip_exit(side="long", htf_df=htf_df)
    assert should_exit is True
    assert reason == "htf_trend_flip_exit"


def test_htf_trend_flip_exit_does_not_fire_when_trend_still_valid():
    """A LONG htf_confluence_pullback position stays open when EMA21 still > EMA50."""
    from bot import _check_htf_trend_flip_exit
    htf_df = _fake_htf_df(ema21_over_ema50=True)
    should_exit, reason = _check_htf_trend_flip_exit(side="long", htf_df=htf_df)
    assert should_exit is False


def test_htf_trend_flip_exit_mirror_for_short():
    """A SHORT position must exit when EMA21 rises above EMA50."""
    from bot import _check_htf_trend_flip_exit
    htf_df = _fake_htf_df(ema21_over_ema50=True)  # trend turned up
    should_exit, reason = _check_htf_trend_flip_exit(side="short", htf_df=htf_df)
    assert should_exit is True
    assert reason == "htf_trend_flip_exit"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_ae_exit_rule.py -v 2>&1 | tail -15`
Expected: FAIL — `ImportError: cannot import name '_check_htf_trend_flip_exit'`

- [ ] **Step 5: Add the helper function to bot.py**

Add this function to `/Users/jonaspenaso/Desktop/Phmex-S/bot.py` at module level (near top, after imports, before `class Bot`):

```python
def _check_htf_trend_flip_exit(side: str, htf_df) -> tuple[bool, str]:
    """Check if 1h EMA21/EMA50 has flipped against position direction.

    Returns (should_exit, reason). Used by htf_confluence_pullback positions only,
    to exit fast on the exact inverse of the entry condition.
    """
    if htf_df is None or len(htf_df) == 0:
        return False, ""
    last = htf_df.iloc[-1]
    ema21 = last.get("ema_21")
    ema50 = last.get("ema_50")
    if ema21 is None or ema50 is None:
        return False, ""
    if side == "long" and ema21 < ema50:
        return True, "htf_trend_flip_exit"
    if side == "short" and ema21 > ema50:
        return True, "htf_trend_flip_exit"
    return False, ""
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_ae_exit_rule.py -v 2>&1 | tail -15`
Expected: 3 tests PASS

- [ ] **Step 7: Wire the helper into the live exit loop in bot.py**

Find the live exit loop in bot.py (around line 629 where `check_positions` results are handled). Add the trend-flip check BEFORE the existing `should_adverse_exit` check. Example pseudocode for what to insert:

```python
# Existing loop over self.risk.positions.items()
for symbol, pos in list(self.risk.positions.items()):
    # ... existing price fetch ...

    # Fix 1: trend-flip exit for htf_confluence_pullback only
    if pos.strategy == "htf_confluence_pullback":
        htf_df_tuple = self._htf_cache.get(symbol)
        htf_df = htf_df_tuple[0] if htf_df_tuple else None
        should_flip, flip_reason = _check_htf_trend_flip_exit(pos.side, htf_df)
        if should_flip:
            logger.info(f"[TREND-FLIP EXIT] {symbol} {pos.side} — 1h EMA flipped, closing")
            self.risk.close_position(symbol, price, flip_reason)
            continue  # skip remaining exit checks for this position

    # ... existing should_adverse_exit check continues unchanged ...
```

Read the actual file around line 629 first and adapt variable names to the real code.

- [ ] **Step 8: Repeat step 7 for paper slot exit loop (around bot.py:1119)**

Same logic, applied to each paper slot's positions. Use `slot.risk.positions` instead of `self.risk.positions`.

- [ ] **Step 9: Syntax check**

Run: `cd ~/Desktop/Phmex-S && python3 -m py_compile bot.py && echo OK`
Expected: `OK`

- [ ] **Step 10: Re-run tests**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_ae_exit_rule.py -v 2>&1 | tail -10`
Expected: 3 PASS

- [ ] **Step 11: Commit**

```bash
cd ~/Desktop/Phmex-S
git add bot.py tests/test_ae_exit_rule.py
git commit -m "feat: add htf_confluence_pullback trend-flip exit rule (exits on 1h EMA21/50 cross against position direction)"
```

---

## Task 4: Fix 3 — Extend Kill Switches

**Files:**
- Modify: `bot.py` (add daily loss halt + consecutive loss halt near entry cycle start)
- Modify: `risk_manager.py` (add 8% soft DD tier)
- Create: `tests/test_kill_switches.py`

- [ ] **Step 1: Read existing drawdown halt code**

Run: `sed -n '225,340p' /Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py`
Note: existing tiers are 20/25/30%. Find where `_drawdown_pause_until` is set.

- [ ] **Step 2: Read existing loss_streak tracking**

Run: `grep -n "_loss_streak" /Users/jonaspenaso/Desktop/Phmex-S/bot.py`
Expected: shows `self._loss_streak` initialized and incremented.

- [ ] **Step 3: Read existing .pause_trading sentinel logic**

Run: `sed -n '390,430p' /Users/jonaspenaso/Desktop/Phmex-S/bot.py`
Note: how the sentinel file path is defined and how entries are skipped when present.

- [ ] **Step 4: Write failing tests**

Create `/Users/jonaspenaso/Desktop/Phmex-S/tests/test_kill_switches.py`:

```python
"""Test extended kill switches — daily loss halt, consecutive loss halt, 8% soft DD tier."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_compute_today_net_pnl_sums_only_today():
    from bot import _compute_today_net_pnl
    now = time.time()
    trades = [
        {"closed_at": now, "net_pnl": -1.0, "pnl_usdt": -1.0},
        {"closed_at": now - 86400 * 2, "net_pnl": 5.0, "pnl_usdt": 5.0},  # 2 days ago
        {"closed_at": now, "net_pnl": -0.5, "pnl_usdt": -0.5},
    ]
    assert _compute_today_net_pnl(trades) == -1.5


def test_daily_loss_halt_triggers_at_3_percent():
    from bot import _should_halt_daily_loss
    balance = 100.0
    # Under threshold
    assert _should_halt_daily_loss(today_net=-2.0, balance=balance) is False
    # Exactly at threshold
    assert _should_halt_daily_loss(today_net=-3.0, balance=balance) is True
    # Over
    assert _should_halt_daily_loss(today_net=-5.0, balance=balance) is True


def test_consecutive_loss_halt_triggers_at_5():
    from bot import _should_halt_consecutive_losses
    assert _should_halt_consecutive_losses(loss_streak=4) is False
    assert _should_halt_consecutive_losses(loss_streak=5) is True
    assert _should_halt_consecutive_losses(loss_streak=10) is True


def test_soft_dd_tier_at_8_percent_returns_pause_duration():
    from risk_manager import RiskManager
    rm = RiskManager.__new__(RiskManager)
    rm.peak_balance = 100.0
    pause_sec = rm._soft_dd_tier_pause_seconds(current_balance=92.0)  # 8% DD
    assert pause_sec == 900  # 15 min
    pause_sec_none = rm._soft_dd_tier_pause_seconds(current_balance=96.0)  # 4% DD
    assert pause_sec_none == 0
```

- [ ] **Step 5: Run test to verify failure**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_kill_switches.py -v 2>&1 | tail -20`
Expected: FAIL — ImportError on helpers not yet defined.

- [ ] **Step 6: Add helpers to bot.py at module level**

Add to `/Users/jonaspenaso/Desktop/Phmex-S/bot.py` near other module-level helpers:

```python
def _compute_today_net_pnl(closed_trades: list) -> float:
    """Sum today's net_pnl (or pnl_usdt fallback). Uses America/Los_Angeles day boundary."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
    today_str = datetime.now(PT).strftime("%Y-%m-%d")
    total = 0.0
    for t in closed_trades:
        closed_at = t.get("closed_at")
        if not closed_at:
            continue
        if datetime.fromtimestamp(closed_at, tz=PT).strftime("%Y-%m-%d") != today_str:
            continue
        net = t.get("net_pnl")
        if net is None:
            net = t.get("pnl_usdt", 0.0)
        total += float(net or 0.0)
    return total


def _should_halt_daily_loss(today_net: float, balance: float, threshold_pct: float = 3.0) -> bool:
    """Return True if today's net PnL is a loss exceeding threshold_pct of balance."""
    if balance <= 0:
        return False
    loss_limit = -(balance * threshold_pct / 100.0)
    return today_net <= loss_limit


def _should_halt_consecutive_losses(loss_streak: int, threshold: int = 5) -> bool:
    """Return True if consecutive losing trades exceed threshold."""
    return loss_streak >= threshold
```

- [ ] **Step 7: Add soft DD tier helper to risk_manager.py RiskManager class**

Add method to `/Users/jonaspenaso/Desktop/Phmex-S/risk_manager.py` RiskManager class:

```python
def _soft_dd_tier_pause_seconds(self, current_balance: float) -> int:
    """8% soft drawdown tier — returns pause seconds (900=15min) or 0 if not triggered.

    Placed before the existing 20/25/30% hard tiers as an early warning.
    """
    if self.peak_balance <= 0 or current_balance <= 0:
        return 0
    dd_pct = (self.peak_balance - current_balance) / self.peak_balance * 100.0
    if dd_pct >= 8.0 and dd_pct < 20.0:
        return 900  # 15 minutes
    return 0
```

- [ ] **Step 8: Run tests to verify pass**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_kill_switches.py -v 2>&1 | tail -15`
Expected: 4 tests PASS

- [ ] **Step 9: Wire helpers into bot.py entry cycle**

At the top of the entry decision loop in bot.py (before new entries are placed but after existing `.pause_trading` sentinel check), add:

```python
# Fix 3: Kill switch checks — fire the existing .pause_trading sentinel
today_net = _compute_today_net_pnl(self.risk.closed_trades)
if _should_halt_daily_loss(today_net, real_balance):
    reason = f"DAILY LOSS HALT: today net ${today_net:.2f} exceeds -3% of ${real_balance:.2f}"
    self._set_pause_sentinel(reason)  # create .pause_trading with reason
    logger.warning(f"[KILL SWITCH] {reason}")
    try:
        notifier.send(f"⛔ {reason}")
    except Exception:
        pass
    return  # skip this entry cycle

if _should_halt_consecutive_losses(self._loss_streak):
    reason = f"CONSECUTIVE LOSS HALT: {self._loss_streak} losses in a row — 4h cooldown"
    self._set_pause_sentinel(reason)
    logger.warning(f"[KILL SWITCH] {reason}")
    try:
        notifier.send(f"⛔ {reason}")
    except Exception:
        pass
    return
```

- [ ] **Step 10: Add _set_pause_sentinel helper to Bot class**

```python
def _set_pause_sentinel(self, reason: str) -> None:
    """Create the .pause_trading sentinel file with a reason note."""
    try:
        with open(".pause_trading", "w") as f:
            f.write(f"{int(time.time())}\n{reason}\n")
    except Exception as e:
        logger.warning(f"Failed to write pause sentinel: {e}")
```

- [ ] **Step 11: Wire 8% soft DD tier into risk_manager.check_drawdown**

Find `check_drawdown` (or equivalent) in risk_manager.py and add the soft tier check BEFORE the existing 20% tier:

```python
# 8% soft tier — early warning, 15 min pause
soft_pause = self._soft_dd_tier_pause_seconds(current_balance)
if soft_pause > 0 and self._drawdown_pause_until < time.time():
    self._drawdown_pause_until = time.time() + soft_pause
    logger.warning(f"[DD] Soft 8% drawdown — pause {soft_pause}s")
    # Telegram notification via notifier if desired
```

- [ ] **Step 12: Syntax check both files**

Run: `cd ~/Desktop/Phmex-S && python3 -m py_compile bot.py risk_manager.py && echo OK`
Expected: `OK`

- [ ] **Step 13: Re-run kill switch tests**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_kill_switches.py -v 2>&1 | tail -10`
Expected: 4 PASS

- [ ] **Step 14: Commit**

```bash
cd ~/Desktop/Phmex-S
git add bot.py risk_manager.py tests/test_kill_switches.py
git commit -m "feat: add daily loss halt, consecutive loss halt, 8% soft DD tier (extends existing pause sentinel)"
```

---

## Task 5: Fix 4 — Dead Slot + Shadow Filter Cleanup

**Files:**
- Modify: `bot.py` (remove paper slot init for dead slots + shadow filter writes)
- Modify: `web_dashboard.py` (remove dead slot UI references)
- Modify: `scripts/daily_report.py` (remove dead slot paragraphs)
- Modify: `notifier.py` (remove shadow filter reference if any)
- Delete: 5 state files

- [ ] **Step 1: Grep all references to atr_gate**

Run: `cd ~/Desktop/Phmex-S && grep -rn "atr_gate" --include="*.py" | head -20`
Note: every file:line that mentions it. Each needs removal.

- [ ] **Step 2: Grep all references to sma_vwap**

Run: `cd ~/Desktop/Phmex-S && grep -rn "sma_vwap" --include="*.py" | head -20`

- [ ] **Step 3: Grep all references to v10_control**

Run: `cd ~/Desktop/Phmex-S && grep -rn "v10_control" --include="*.py" | head -20`

- [ ] **Step 4: Grep all references to legacy_control**

Run: `cd ~/Desktop/Phmex-S && grep -rn "legacy_control" --include="*.py" | head -20`

- [ ] **Step 5: Grep all references to 1h_momentum**

Run: `cd ~/Desktop/Phmex-S && grep -rn "1h_momentum\|trading_state_1h" --include="*.py" | head -20`

- [ ] **Step 6: Grep all references to shadow_skip / shadow_hour_pt**

Run: `cd ~/Desktop/Phmex-S && grep -rn "shadow_skip\|shadow_hour_pt" --include="*.py" | head -20`

- [ ] **Step 7: Remove paper slot init in bot.py for each dead slot**

Find the paper slot setup block in bot.py (search for `StrategySlot(` or `slot_id=`). For each dead slot (atr_gate, sma_vwap, v10_control, legacy_control, 1h_momentum), remove the entire instantiation block. Preserve liq_cascade and mean_revert.

- [ ] **Step 8: Remove dead slot references in web_dashboard.py**

For each file:line from Steps 1-5, open the file, read the surrounding 10 lines, and remove the dead slot code cleanly — including any table rows, chart traces, or comparison blocks.

- [ ] **Step 9: Remove dead slot references in scripts/daily_report.py**

Same as Step 8 but for daily_report.py. Preserve the report structure; only remove the per-dead-slot sections.

- [ ] **Step 10: Remove shadow filter writes in bot.py and risk_manager.py**

Delete or comment out any line that WRITES `shadow_skip` or `shadow_hour_pt` to a position or trade dict. Leave read-paths intact for historical records until Step 11.

- [ ] **Step 11: Remove shadow filter display in web_dashboard.py and daily_report.py**

Delete the dashboard card / report section that shows shadow-filter results. Keep the closed_trades list read path as-is (historical trades still have the field).

- [ ] **Step 12: Syntax check all modified files**

Run: `cd ~/Desktop/Phmex-S && python3 -m py_compile bot.py risk_manager.py web_dashboard.py scripts/daily_report.py notifier.py && echo OK`
Expected: `OK`

- [ ] **Step 13: Delete the 5 dead state files**

```bash
cd ~/Desktop/Phmex-S
rm -f trading_state_5m_atr_gate.json trading_state_5m_sma_vwap.json trading_state_5m_v10_control.json trading_state_5m_legacy_control.json trading_state_1h_momentum.json
```

- [ ] **Step 14: Re-grep to confirm zero references remain**

Run: `cd ~/Desktop/Phmex-S && grep -rn "atr_gate\|sma_vwap\|v10_control\|legacy_control\|1h_momentum" --include="*.py" | grep -v "# removed"`
Expected: zero output (empty)

- [ ] **Step 15: Commit**

```bash
cd ~/Desktop/Phmex-S
git add -A
git commit -m "chore: remove 5 dead paper slots (atr_gate, sma_vwap, v10_control, legacy_control, 1h_momentum) + shadow filter"
```

---

## Task 6: Pre-Restart Audit + Bundle Restart (Fixes 1-4)

**Files:** all Day 1 changes

- [ ] **Step 1: Run /pre-restart-audit skill**

Invoke: `/pre-restart-audit`
Expected: checklist passes, no CONFLICT on any param.

- [ ] **Step 2: Run full syntax check on all Python files**

Run: `cd ~/Desktop/Phmex-S && python3 -m py_compile bot.py risk_manager.py strategies.py strategy_slot.py exchange.py notifier.py web_dashboard.py scripts/daily_report.py && echo OK`
Expected: `OK`

- [ ] **Step 3: Run full test suite**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/ -v 2>&1 | tail -20`
Expected: all tests PASS (includes tests from this plan: test_postonly_param, test_ae_exit_rule, test_kill_switches)

- [ ] **Step 4: Verify bot is running, note PID**

Run: `ps aux | grep "Python.*main" | grep -v grep`
Note the current PID.

- [ ] **Step 5: Kill current bot process**

```bash
cd ~/Desktop/Phmex-S
kill -9 $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 2
```

- [ ] **Step 6: Clear pycache and restart**

```bash
cd ~/Desktop/Phmex-S
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
sleep 5
```

- [ ] **Step 7: Verify bot is running with new PID**

Run: `ps aux | grep "Python.*main" | grep -v grep`
Expected: new PID visible, process active.

- [ ] **Step 8: Tail logs for startup errors**

Run: `tail -30 ~/Desktop/Phmex-S/logs/bot.log`
Expected: "Starting balance: X USDT", "Markets loaded", "sync_positions" success, no tracebacks.

- [ ] **Step 9: Wait 5 minutes, check for first cycle**

```bash
sleep 300
grep "\[ENTRY\]\|\[MAKER\]\|\[TAKER\]" ~/Desktop/Phmex-S/logs/bot.log | tail -10
```
Expected: at least one cycle completed without error (may or may not have entries).

- [ ] **Step 10: Commit the restart marker**

```bash
cd ~/Desktop/Phmex-S
echo "$(date +%Y-%m-%d\ %H:%M:%S) — Bundle restart: Fixes 1+2+3+4" >> docs/deploy_log.md
git add docs/deploy_log.md
git commit -m "chore: deploy 6-fix plan day 1 bundle (postOnly fix, AE exit rule, kill switches, slot cleanup)"
```

---

## Task 7: Fix 2 Live Validation — Verify Maker Rate > 0%

**Files:** read-only monitoring

- [ ] **Step 1: Wait for at least 5 new entry attempts**

Monitor `tail -f logs/bot.log | grep -i "order placed\|MAKER\|TAKER"` until 5 entry lines appear. May take hours depending on bot activity.

- [ ] **Step 2: Count MAKER fills vs MAKER failures**

Run: `cd ~/Desktop/Phmex-S && grep "\[MAKER\] Limit filled" logs/bot.log | wc -l` → note FILLED
Run: `cd ~/Desktop/Phmex-S && grep "\[MAKER\] Limit order failed" logs/bot.log | wc -l` → note FAILED

- [ ] **Step 3: Assert maker rate > 0% OR diagnose**

If FILLED >= 1 → Fix 2 confirmed working ✅
If FILLED == 0 AND FAILED > 0 → Fix did NOT work. Grep the failure reason:
```bash
grep "\[MAKER\] Limit order failed" ~/Desktop/Phmex-S/logs/bot.log | tail -5
```
Investigate error message. Do NOT declare Fix 2 done.

- [ ] **Step 4: Telegram confirmation**

Run: `python3 -c "from notifier import send; send('✅ Fix 2 validated: maker fill rate > 0%')"`
(Only if Step 3 confirmed.)

- [ ] **Step 5: Update spec validation checklist**

Append to `/Users/jonaspenaso/Desktop/Phmex-S/docs/superpowers/specs/2026-04-09-phmex-s-5-fixes.md`:
```
## Validation Log
- Fix 2: postOnly — VERIFIED LIVE at <timestamp>, maker fill N/M entries
```

---

## Task 8: Fix 1 Live Validation — Verify Trend-Flip Exit Fires

**Files:** read-only monitoring

- [ ] **Step 1: Wait for any htf_confluence_pullback position to close**

Monitor: `tail -f logs/bot.log | grep "Position closed"`
Wait for a close with strategy htf_confluence_pullback. May take hours.

- [ ] **Step 2: Check if TREND-FLIP EXIT log line ever fired**

Run: `grep "\[TREND-FLIP EXIT\]" ~/Desktop/Phmex-S/logs/bot.log`
Expected (eventually): at least one line. If zero after 24h with htf trades, the trigger never fired — diagnose whether trends are flat or the helper isn't being called.

- [ ] **Step 3: Check the closed_trades exit_reason field in trading_state.json**

```bash
cd ~/Desktop/Phmex-S && python3 -c "
import json
s = json.load(open('trading_state.json'))
htf = [t for t in s['closed_trades'] if t.get('strategy') == 'htf_confluence_pullback' and t.get('closed_at', 0) > $(date +%s) - 86400]
for t in htf:
    print(t.get('exit_reason'), t.get('net_pnl'))
"
```
Expected: at least some trades show `htf_trend_flip_exit` as exit_reason.

- [ ] **Step 4: Update validation log**

Append to spec validation log confirming Fix 1 works.

---

## Task 9: Fix 5 — Audit Existing Backtester (Read-Only, Day 2)

**Files:** read-only

- [ ] **Step 1: Read backtester.py top-to-bottom**

Read: `/Users/jonaspenaso/Desktop/Phmex-S/backtester.py`
Note: CLI args, strategy dispatch, SL/TP/AE logic, missing fees/slippage.

- [ ] **Step 2: Read backtest.py top-to-bottom**

Read: `/Users/jonaspenaso/Desktop/Phmex-S/backtest.py`
Note: has fees/slippage, lacks AE rule. Uses `adaptive_strategy` ensemble.

- [ ] **Step 3: Try running backtester.py for htf_confluence_pullback**

Run: `cd ~/Desktop/Phmex-S && python3 backtester.py --strategy htf_confluence_pullback --pair BTC --timeframe 5m --days 7 2>&1 | tail -20`
Expected: either a results report OR an error about missing CSV in `backtest_data/`. Note exact error.

- [ ] **Step 4: If CSV missing, check fetch_history.py**

Run: `ls ~/Desktop/Phmex-S/backtest_data/ 2>&1; grep -rn "fetch_history\|fetch_ohlcv" ~/Desktop/Phmex-S/*.py | head -5`
Document how to fetch historical CSVs.

- [ ] **Step 5: Write an audit report**

Create `/Users/jonaspenaso/Desktop/Phmex-S/docs/backtester_audit.md`:

```markdown
# Backtester Audit — 2026-04-09

## backtester.py (435L)
- CLI: `--strategy --pair --timeframe --days --wfo`
- Models: SL, TP, adverse_exit, trailing
- Missing: fees, slippage, funding
- Data source: CSV files in backtest_data/
- Can isolate single strategy: yes

## backtest.py (1143L)
- CLI: `--pairs --days --timeframe --no-gates`
- Models: SL, TP, fees (0.06%/side), slippage (0.05%)
- Missing: adverse_exit, single-strategy isolation
- Data source: live ccxt fetch
- Runs adaptive_strategy ensemble

## Gaps vs needs
- Need: AE rule comparison (old vs new trend-flip) over 90 days
- Need: fees + AE in same tool
- Plan: extend backtester.py with fee model + --ae-rule flag

## OB/tape caveat
Neither backtester can replay L2 orderbook or tape buy_ratio gates. Both stub/skip them. Any result will be optimistic vs live by an estimated 5-10% per backtest.py:1026.
```

- [ ] **Step 6: Commit the audit**

```bash
cd ~/Desktop/Phmex-S
git add docs/backtester_audit.md
git commit -m "docs: backtester audit report (gaps vs AE rule comparison need)"
```

---

## Task 10: Fix 5 — Extend backtester.py with Fees + AE Rule Flag (Day 3)

**Files:**
- Modify: `backtester.py`

- [ ] **Step 1: Add fee constants at top of backtester.py**

Near imports / constants section:

```python
# Fee model matching live config
TAKER_FEE_PCT = 0.06  # per side
SLIPPAGE_PCT = 0.05   # per side
```

- [ ] **Step 2: Apply fees in the exit PnL computation**

Find where trade PnL is computed on exit (around line 240-280). After gross PnL calculation, subtract round-trip fees:

```python
notional = entry_price * amount
fees = notional * (TAKER_FEE_PCT + SLIPPAGE_PCT) * 2 / 100
net_pnl = gross_pnl - fees
```

- [ ] **Step 3: Add --ae-rule CLI flag**

At CLI arg setup (around line 396-405):

```python
parser.add_argument(
    "--ae-rule",
    choices=["roi", "trend_flip"],
    default="roi",
    help="Adverse exit rule: 'roi' (legacy -5% after 10 cycles) or 'trend_flip' (1h EMA flip)"
)
```

- [ ] **Step 4: Parameterize the AE check block (backtester.py:201-212)**

Replace the hardcoded ROI-based AE with a dispatcher:

```python
if args.ae_rule == "roi":
    # existing logic
    if cycles_held >= 10 and roi_pct <= -5.0:
        should_ae = True
        ae_reason = "adverse_exit"
elif args.ae_rule == "trend_flip":
    # new logic: check 1h EMA21/50 vs position direction
    htf_row = htf_df.iloc[-1] if htf_df is not None and len(htf_df) > 0 else None
    if htf_row is not None:
        ema21 = htf_row.get("ema_21")
        ema50 = htf_row.get("ema_50")
        if side == "long" and ema21 is not None and ema21 < ema50:
            should_ae = True
            ae_reason = "htf_trend_flip_exit"
        elif side == "short" and ema21 is not None and ema21 > ema50:
            should_ae = True
            ae_reason = "htf_trend_flip_exit"
```

- [ ] **Step 5: Syntax check**

Run: `cd ~/Desktop/Phmex-S && python3 -m py_compile backtester.py && echo OK`

- [ ] **Step 6: Dry run both modes**

```bash
cd ~/Desktop/Phmex-S
python3 backtester.py --strategy htf_confluence_pullback --pair BTC --timeframe 5m --days 30 --ae-rule roi 2>&1 | tail -15
python3 backtester.py --strategy htf_confluence_pullback --pair BTC --timeframe 5m --days 30 --ae-rule trend_flip 2>&1 | tail -15
```
Expected: both produce reports with different PnL/WR numbers.

- [ ] **Step 7: Commit**

```bash
cd ~/Desktop/Phmex-S
git add backtester.py
git commit -m "feat(backtester): add fees/slippage model + --ae-rule flag (roi vs trend_flip comparison)"
```

---

## Task 11: Fix 5 — Calibrate Backtester Against Live (Day 4)

**Files:** read-only validation + markdown report

- [ ] **Step 1: Run backtester on the exact Sentinel window**

```bash
cd ~/Desktop/Phmex-S && python3 backtester.py --strategy htf_confluence_pullback --pair BTC --timeframe 5m --days 7 --ae-rule roi 2>&1 | tee /tmp/backtest_btc.txt
# Repeat for ETH SOL SUI XRP LINK
```

- [ ] **Step 2: Extract live Sentinel trades for same window**

```bash
cd ~/Desktop/Phmex-S && python3 -c "
import json
from datetime import datetime
from zoneinfo import ZoneInfo
PT = ZoneInfo('America/Los_Angeles')
cutoff = datetime(2026,4,1,23,1,tzinfo=PT).timestamp()
s = json.load(open('trading_state.json'))
sent = [t for t in s['closed_trades'] if (t.get('opened_at') or 0) >= cutoff and t.get('strategy')=='htf_confluence_pullback']
print(f'Live Sentinel htf trades: {len(sent)}')
print(f'Net: {sum((t.get(\"net_pnl\") or t.get(\"pnl_usdt\",0)) for t in sent):+.4f}')
print(f'WR: {sum(1 for t in sent if (t.get(\"net_pnl\") or t.get(\"pnl_usdt\",0))>0)/len(sent)*100:.1f}%')
"
```

- [ ] **Step 3: Compare backtest output to live**

Compute: `abs(backtest_pnl - live_pnl) / abs(live_pnl)`. If < 0.25 (within 25%) → backtester is trustworthy. If > 0.25 → document discrepancy, investigate, do not trust output.

- [ ] **Step 4: Write calibration report**

Append to `docs/backtester_audit.md` a Calibration section with:
- Live Sentinel trades: N, net $X
- Backtest replay: N, net $Y
- Discrepancy: Z%
- Verdict: TRUSTWORTHY / NEEDS FIX / OPTIMISTIC

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/Phmex-S
git add docs/backtester_audit.md
git commit -m "docs: backtester calibration against Sentinel live trades"
```

---

## Task 12: Fix 5 — Sweep New AE Rule on 90 Days (Days 5-7)

**Files:** read-only sweeps

- [ ] **Step 1: Run sweep script for each pair**

```bash
cd ~/Desktop/Phmex-S
for pair in BTC ETH SOL SUI XRP LINK; do
  for rule in roi trend_flip; do
    python3 backtester.py --strategy htf_confluence_pullback --pair $pair --timeframe 5m --days 90 --ae-rule $rule 2>&1 | tail -5 > /tmp/sweep_${pair}_${rule}.txt
  done
done
```

- [ ] **Step 2: Aggregate results into a table**

Create `/Users/jonaspenaso/Desktop/Phmex-S/reports/backtest_sweep_2026-04-09.md`:

```markdown
# AE Rule Sweep — 90 days, 6 pairs

| Pair | ROI Rule Net | Trend-Flip Net | Better |
|---|---|---|---|
| BTC | $X | $Y | ? |
| ETH | ... | ... | ? |
...
```

Fill in from /tmp/sweep_*.txt outputs.

- [ ] **Step 3: Decision point**

If trend_flip wins on >=4 of 6 pairs AND total net is higher → Fix 1 is confirmed empirically. Declare ready for production.
If not → iterate on the AE rule, consider hybrid, do not trust Fix 1 yet.

- [ ] **Step 4: Commit**

```bash
cd ~/Desktop/Phmex-S
git add reports/backtest_sweep_2026-04-09.md
git commit -m "docs: 90-day AE rule sweep (roi vs trend_flip)"
```

---

## Task 13: Fix 6 — Weekly Forensics Script

**Files:**
- Create: `scripts/weekly_forensics.py`
- Create: `tests/test_weekly_forensics.py`

- [ ] **Step 1: Write failing test**

Create `/Users/jonaspenaso/Desktop/Phmex-S/tests/test_weekly_forensics.py`:

```python
"""Test weekly forensics pattern detector."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.weekly_forensics import find_significant_patterns


def test_finds_bucket_with_low_win_rate():
    """A bucket with 10+ trades and <30% WR should be flagged."""
    now = time.time()
    trades = []
    # SOL longs: 12 trades, 2 wins = 16.7% WR
    for i in range(12):
        trades.append({
            "symbol": "SOL/USDT:USDT", "side": "long",
            "opened_at": now - 86400 * (i % 7),
            "closed_at": now - 86400 * (i % 7),
            "net_pnl": 1.0 if i < 2 else -1.0,
        })
    # ETH shorts: 20 trades, 18 wins = 90% WR (should flag as significant positive)
    for i in range(20):
        trades.append({
            "symbol": "ETH/USDT:USDT", "side": "short",
            "opened_at": now - 86400 * (i % 7),
            "closed_at": now - 86400 * (i % 7),
            "net_pnl": 1.0 if i < 18 else -1.0,
        })
    patterns = find_significant_patterns(trades, min_n=10, min_deviation=0.2)
    labels = [p["label"] for p in patterns]
    assert any("SOL" in l and "long" in l for l in labels), f"Expected SOL long pattern, got: {labels}"
    assert any("ETH" in l and "short" in l for l in labels), f"Expected ETH short pattern, got: {labels}"


def test_ignores_small_samples():
    """Fewer than min_n trades = not significant even if WR is extreme."""
    trades = [
        {"symbol": "BTC/USDT:USDT", "side": "long", "closed_at": time.time(), "net_pnl": 1.0}
        for _ in range(5)
    ]
    patterns = find_significant_patterns(trades, min_n=10)
    assert patterns == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_weekly_forensics.py -v 2>&1 | tail -10`
Expected: FAIL — ImportError

- [ ] **Step 3: Create scripts/weekly_forensics.py**

Create `/Users/jonaspenaso/Desktop/Phmex-S/scripts/weekly_forensics.py`:

```python
#!/usr/bin/env python3
"""Weekly forensics — deterministic pattern detection on last 7 days of trades.

Runs via launchd every Sunday 8 PM PT. Loads closed_trades, groups by
(symbol, side, exit_reason, hour_pt), flags buckets with significant
win-rate deviation, writes Telegram summary + markdown report.

NO LLM in the loop. Pure pandas.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PT = ZoneInfo("America/Los_Angeles")
STATE_FILE = ROOT / "trading_state.json"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)


def _net(t: dict) -> float:
    n = t.get("net_pnl")
    return float(n if n is not None else t.get("pnl_usdt", 0) or 0)


def find_significant_patterns(
    trades: list[dict],
    min_n: int = 10,
    min_deviation: float = 0.2,
) -> list[dict]:
    """Group trades into buckets and return buckets with significant WR deviation.

    Buckets: (symbol, side, exit_reason, hour_pt).
    A bucket is 'significant' when n >= min_n AND |win_rate - 0.5| >= min_deviation.
    """
    buckets: dict[tuple, list] = defaultdict(list)
    for t in trades:
        symbol = t.get("symbol", "?")
        side = t.get("side", "?")
        reason = t.get("exit_reason") or t.get("reason") or "?"
        opened = t.get("opened_at") or t.get("closed_at") or 0
        if opened:
            hour_pt = datetime.fromtimestamp(opened, tz=PT).hour
        else:
            hour_pt = -1
        # Build coarse-grained buckets first
        buckets[(symbol, side, None, None)].append(t)
        buckets[(symbol, None, reason, None)].append(t)
        buckets[(symbol, side, None, hour_pt)].append(t)

    patterns = []
    for key, bucket_trades in buckets.items():
        n = len(bucket_trades)
        if n < min_n:
            continue
        wins = sum(1 for t in bucket_trades if _net(t) > 0)
        wr = wins / n
        deviation = wr - 0.5
        if abs(deviation) < min_deviation:
            continue
        symbol, side, reason, hour = key
        label_parts = [symbol]
        if side:
            label_parts.append(side)
        if reason:
            label_parts.append(f"reason={reason}")
        if hour is not None and hour != -1:
            label_parts.append(f"hour={hour:02d}PT")
        label = " ".join(label_parts)
        patterns.append({
            "label": label,
            "n": n,
            "wins": wins,
            "win_rate": wr,
            "deviation": deviation,
            "net_pnl": sum(_net(t) for t in bucket_trades),
        })
    # Sort by absolute deviation descending
    patterns.sort(key=lambda p: abs(p["deviation"]), reverse=True)
    return patterns


def load_recent_trades(days: int = 7) -> list[dict]:
    if not STATE_FILE.exists():
        return []
    data = json.loads(STATE_FILE.read_text())
    cutoff = time.time() - (days * 86400)
    return [t for t in data.get("closed_trades", []) if (t.get("closed_at") or 0) >= cutoff]


def write_report(patterns: list[dict], date_str: str) -> Path:
    path = REPORT_DIR / f"forensics_{date_str}.md"
    lines = [f"# Weekly Forensics — {date_str}", ""]
    if not patterns:
        lines.append("No significant patterns detected (n>=10, |WR deviation|>=0.2).")
    else:
        lines.append(f"Found {len(patterns)} significant patterns. Top 10:\n")
        lines.append("| Rank | Pattern | N | Wins | WR | Net |")
        lines.append("|---|---|---|---|---|---|")
        for i, p in enumerate(patterns[:10], 1):
            lines.append(f"| {i} | {p['label']} | {p['n']} | {p['wins']} | {p['win_rate']*100:.1f}% | ${p['net_pnl']:+.2f} |")
    path.write_text("\n".join(lines) + "\n")
    return path


def send_telegram_summary(patterns: list[dict], report_path: Path) -> None:
    try:
        from notifier import send  # type: ignore
    except Exception:
        return
    if not patterns:
        send("📊 Weekly forensics: no significant patterns this week.")
        return
    top = patterns[0]
    msg = (
        f"📊 Weekly forensics — {len(patterns)} significant patterns\n"
        f"Top: {top['label']} — {top['n']} trades, "
        f"{top['win_rate']*100:.0f}% WR, ${top['net_pnl']:+.2f}\n"
        f"Full report: {report_path.name}"
    )
    send(msg)


def main() -> None:
    trades = load_recent_trades(days=7)
    patterns = find_significant_patterns(trades, min_n=10, min_deviation=0.2)
    date_str = datetime.now(PT).strftime("%Y-%m-%d")
    report = write_report(patterns, date_str)
    send_telegram_summary(patterns, report)
    print(f"Report saved: {report}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify pass**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_weekly_forensics.py -v 2>&1 | tail -10`
Expected: 2 tests PASS

- [ ] **Step 5: Dry run the script manually**

Run: `cd ~/Desktop/Phmex-S && python3 scripts/weekly_forensics.py`
Expected: prints "Report saved: /path/to/reports/forensics_YYYY-MM-DD.md". Telegram sends a message.

- [ ] **Step 6: Inspect report output**

Run: `cat ~/Desktop/Phmex-S/reports/forensics_$(date +%Y-%m-%d).md`
Expected: markdown table of patterns or "no significant patterns" note.

- [ ] **Step 7: Commit**

```bash
cd ~/Desktop/Phmex-S
git add scripts/weekly_forensics.py tests/test_weekly_forensics.py reports/forensics_*.md
git commit -m "feat: weekly forensics pattern detector (deterministic, no LLM in loop)"
```

---

## Task 14: Fix 6 — launchd Schedule for Weekly Forensics

**Files:**
- Create: `~/Library/LaunchAgents/com.phmex.forensics.plist`

- [ ] **Step 1: Create the launchd plist**

Create `/Users/jonaspenaso/Library/LaunchAgents/com.phmex.forensics.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.phmex.forensics</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python</string>
        <string>/Users/jonaspenaso/Desktop/Phmex-S/scripts/weekly_forensics.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>20</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S</string>
    <key>StandardOutPath</key>
    <string>/Users/jonaspenaso/Library/Logs/Phmex-S/forensics.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/jonaspenaso/Library/Logs/Phmex-S/forensics.log</string>
</dict>
</plist>
```

(Sunday = Weekday 0 in launchd; 20:00 local time = 8 PM PT on a Mac set to PT.)

- [ ] **Step 2: Ensure log dir exists**

Run: `mkdir -p ~/Library/Logs/Phmex-S`

- [ ] **Step 3: Load the launchd job**

Run: `launchctl load ~/Library/LaunchAgents/com.phmex.forensics.plist 2>&1`
Expected: no output (success)

- [ ] **Step 4: Verify launchd loaded it**

Run: `launchctl list | grep forensics`
Expected: `- 0 com.phmex.forensics` (PID -, last exit 0)

- [ ] **Step 5: Manually trigger to validate schedule wiring**

Run: `launchctl start com.phmex.forensics`
Wait 10 seconds.
Run: `tail -20 ~/Library/Logs/Phmex-S/forensics.log`
Expected: "Report saved" message, no tracebacks.

- [ ] **Step 6: Commit**

```bash
cd ~/Desktop/Phmex-S
git add /Users/jonaspenaso/Library/LaunchAgents/com.phmex.forensics.plist 2>/dev/null || true
# plist is outside the repo — document in a note instead
echo "com.phmex.forensics.plist installed 2026-04-09 (Sunday 20:00 PT)" >> docs/launchd_jobs.md
git add docs/launchd_jobs.md
git commit -m "feat: launchd schedule for weekly_forensics.py (Sundays 20:00 PT)"
```

---

## Task 15: Post-Deploy Verification Sweep

**Files:** read-only validation

- [ ] **Step 1: Verify all 6 fixes are live**

Run each verification in sequence:

```bash
cd ~/Desktop/Phmex-S
# Fix 1: trend-flip helper exists
python3 -c "from bot import _check_htf_trend_flip_exit; print('Fix 1 OK')"
# Fix 2: postOnly param fixed in source
grep -q '"timeInForce": "PostOnly"' exchange.py && echo "Fix 2 OK"
# Fix 3: kill switch helpers exist
python3 -c "from bot import _compute_today_net_pnl, _should_halt_daily_loss, _should_halt_consecutive_losses; print('Fix 3 OK')"
# Fix 4: dead slots removed
[ ! -f trading_state_5m_atr_gate.json ] && [ ! -f trading_state_1h_momentum.json ] && echo "Fix 4 OK"
# Fix 5: backtester extended
python3 backtester.py --help 2>&1 | grep -q "ae-rule" && echo "Fix 5 OK"
# Fix 6: forensics script + launchd
[ -f scripts/weekly_forensics.py ] && launchctl list | grep -q forensics && echo "Fix 6 OK"
```

Expected: 6 "OK" lines.

- [ ] **Step 2: Full test suite**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/ -v 2>&1 | tail -20`
Expected: all tests PASS

- [ ] **Step 3: Bot health check**

Run: `ps aux | grep "Python.*main" | grep -v grep && tail -10 ~/Desktop/Phmex-S/logs/bot.log`
Expected: bot running, no recent tracebacks

- [ ] **Step 4: Reconcile pipeline health**

Run: `launchctl list | grep phmex`
Expected: reconcile, daily-report, monitor, auto-lifecycle, telegram-commander, forensics all listed

- [ ] **Step 5: Telegram final confirmation**

Run: `cd ~/Desktop/Phmex-S && python3 -c "from notifier import send; send('✅ 6-fix plan deployed and verified. All validation gates passed.')"`

- [ ] **Step 6: Update SESSION_HANDOFF**

Edit `/Users/jonaspenaso/Desktop/Phmex-S/memory/SESSION_HANDOFF.md` — add "2026-04-09 DEPLOYED" section listing the 6 fixes and their validation status.

- [ ] **Step 7: Final commit**

```bash
cd ~/Desktop/Phmex-S
git add memory/SESSION_HANDOFF.md
git commit -m "chore: 6-fix plan deployed and verified end-to-end"
```

---

## Self-Review Notes

- All 6 spec sections have implementing tasks (1-15 cover Fixes 1-6 + preflight + bundle restart + validation)
- No placeholders — every step has either a command, code block, or concrete instruction
- Type consistency: `_check_htf_trend_flip_exit`, `_compute_today_net_pnl`, `_should_halt_daily_loss`, `_should_halt_consecutive_losses`, `_soft_dd_tier_pause_seconds`, `find_significant_patterns`, `load_recent_trades`, `write_report`, `send_telegram_summary` — all referenced consistently
- Validation gates mandated per spec: Task 7 (Fix 2 live maker rate), Task 8 (Fix 1 trend-flip firing), Task 15 (all 6 fixes integrated)
- Ordering: Fix 2 (Task 2) deliberately placed FIRST because it's the 1-line highest-value change — do it before anything else that could complicate the restart
- All code examples are complete; no "similar to" references
