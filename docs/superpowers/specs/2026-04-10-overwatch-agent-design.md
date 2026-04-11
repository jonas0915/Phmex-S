# Overwatch Agent — Design Spec

**Date:** 2026-04-10
**Status:** Draft
**Triggered by:** Jonas wants a persistent agent that monitors bot health, code quality, and data accuracy — alerting via Telegram and generating AI-powered fix specs when issues are found.

---

## Overview

A Python script (`scripts/overwatch.py`) that runs every 1 hour via launchd. It performs 11 health checks across runtime, code, and data accuracy. When issues are found, it:
1. Sends a Telegram alert (CRITICAL = immediate, WARNING = batched)
2. Calls Claude Sonnet API to generate a structured fix spec
3. Saves the fix spec to `docs/fix-proposals/YYYY-MM-DD-HH-<issue>.md`

When all checks pass, it stays silent — no "all clear" spam.

**Cost:** ~$0.50-1.00/month (Sonnet API calls only when issues found, ~1-3/day estimated).

---

## Check Suite (11 checks, 3 categories)

### Category 1: Runtime Health (5 checks)

**Check 1 — Process Alive**
- Method: `ps aux | grep "Python.*main" | grep -v grep`
- CRITICAL if no process found
- **Auto-fix**: restart the bot using the start command from MEMORY.md:
  ```bash
  cd ~/Desktop/Phmex-S
  rm -rf __pycache__
  /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
  ```
- Wait 10s, re-check. If still dead → CRITICAL alert + fix spec. If restarted → WARNING alert ("bot was dead, auto-restarted").

**Check 2 — Log Errors**
- Method: Parse last 60 min of `logs/bot.log` for lines containing `ERROR` or `CRITICAL`
- Exclude known benign patterns: `[TIMEOUT]` warnings (handled by thread wrapper), `fetch_funding_rate` errors (non-critical)
- WARNING if >5 unique error patterns found
- Include the error lines in diagnostics for fix spec

**Check 3 — WebSocket Freshness**
- Method: Grep `bot.log` for `[STALE]` or `[WS] reconnect` messages in last 60 min. Count occurrences.
- WARNING if >3 stale/reconnect events in the last hour (occasional reconnects are normal; persistent staleness is not)
- Context: DNS failures happen daily during market hours (lessons.md). The thread timeout fix should handle this, but if WS is consistently stale it indicates a deeper issue.

**Check 4 — Position Desync**
- Method: Compare `trading_state.json` open positions (where `exit_time` is null/missing) against live exchange positions via `ccxt.fetch_positions()`
- CRITICAL if: exchange has a position not in trading_state (ghost position)
- WARNING if: trading_state has a position not on exchange (phantom — already closed but not recorded)
- Uses its own ccxt client instance (thread-safety per lessons.md META-RULE #11)

**Check 5 — Balance Anomaly**
- Method: Read current balance from exchange. Compare against last known balance in latest daily report or `trading_state.json` closed trades.
- Calculate expected balance: `last_known_balance + sum(recent_trade_pnl)`
- CRITICAL if actual balance is >$5 below expected (unexplained loss)
- WARNING if actual balance is >$2 below expected
- Accounts for open position unrealized PnL in the comparison

### Category 2: Code Quality (3 checks)

**Check 6 — Syntax Check**
- Method: `python3 -m py_compile <file>` on all core .py files:
  `main.py, bot.py, risk_manager.py, strategies.py, exchange.py, ws_feed.py, config.py, notifier.py, web_dashboard.py, war_room.py, strategy_slot.py`
- CRITICAL if any file fails compilation
- Include the compile error in diagnostics

**Check 7 — `__pycache__` Staleness**
- Method: For each .py file, check if corresponding `__pycache__/*.pyc` is older than the .py source file
- WARNING if stale bytecode found
- Context: stale __pycache__ already caused a full day of wrong behavior (lessons.md). This check catches it before it matters.
- **Auto-fix candidate** (future): could auto-clear `__pycache__` on detection, but for v1 just alert.

**Check 8 — Dirty Working Tree**
- Method: `git status --porcelain` filtered to core bot files (bot.py, risk_manager.py, strategies.py, exchange.py, config.py, main.py)
- WARNING if uncommitted changes exist on core files
- Context: uncommitted changes mean code running doesn't match git history — risky for a live trading bot

### Category 3: Data Accuracy (3 checks)

**Check 9 — Trade State vs Exchange Reconciliation**
- Method: Fetch last 10 closed trades from Phemex via `ccxt.fetch_my_trades()`. Compare against corresponding entries in `trading_state.json`:
  - Fill prices match (within 0.01% tolerance)
  - Fee amounts match
  - Timestamps are consistent (within 60s)
- WARNING if any mismatch found
- Include specific discrepancies in diagnostics

**Check 10 — Report Accuracy**
- Method: Read the latest `reports/YYYY-MM-DD.md`. Parse the reported metrics (trade count, win rate, PnL). Independently calculate the same metrics from `trading_state.json` for the same date.
- WARNING if any metric diverges:
  - Trade count: exact match required
  - Win rate: within 1% tolerance
  - PnL: within $0.05 tolerance
- Context: gross vs net PnL lies and fee capture errors caused real-money decisions on false data (Apr 7 session)

**Check 11 — Fee Capture**
- Method: Scan all closed trades in `trading_state.json` from the last 24 hours. Flag any trade where `fee` is 0.0, null, or missing.
- WARNING if any trade has fee == 0.0, fee is null/missing, or fee < $0.02 (suspiciously low — expected ~$0.06-0.07 per trade at taker rate on ~$100 notional)

---

## Alert System

### Severity Levels

| Level | Trigger | Delivery |
|-------|---------|----------|
| CRITICAL | Bot dead, position desync, balance >$5 off, syntax error | Immediate Telegram |
| WARNING | Log errors, stale WS, dirty code, data mismatches, stale cache, zero fees | Batched into single Telegram message |

### Telegram Format

Uses the same `requests.post` pattern as `notifier.py` and `monitor_daemon.py` — HTML parse mode, emoji prefixes.

**CRITICAL alert:**
```
🚨 <b>OVERWATCH — CRITICAL</b>

❌ Bot process NOT FOUND — auto-restarted (PID 12345)
❌ Position desync: BTC/USDT on exchange but not in state

📋 Fix spec: docs/fix-proposals/2026-04-10-14-position-desync.md
```

**WARNING alert:**
```
⚠️ <b>OVERWATCH — 3 warnings</b>

⚠️ 7 ERROR lines in bot.log (last hour)
⚠️ Stale __pycache__ for strategies.py
⚠️ 1 trade missing fee data (trade #412)

📋 Fix specs written to docs/fix-proposals/
```

**All clear:** No message sent.

---

## Fix Spec Generation

When any check fails, Overwatch collects diagnostics and calls Claude Sonnet to generate a fix spec.

### API Call

```python
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2000,
    system="You are a senior Python developer reviewing a live crypto trading bot. "
           "Write a concise fix spec for the issue below. Include: Problem, Root Cause, "
           "Proposed Fix (with file paths and code snippets), Risk Assessment.",
    messages=[{"role": "user", "content": diagnostics_prompt}]
)
```

### Diagnostics Prompt (sent to Sonnet)

```
Issue: {check_name} — {severity}
Description: {what_failed}

Evidence:
{raw_diagnostics — error logs, state diffs, file diffs, etc.}

Context:
- Bot: Phmex-S Sentinel v11, crypto scalper on Phemex
- Stack: Python 3.14, ccxt, WebSocket feeds
- Key files: bot.py, risk_manager.py, strategies.py, exchange.py

Write a fix spec with: Problem, Root Cause Analysis, Proposed Fix, Files to Change, Risk Assessment.
```

### Fix Spec Output

Saved to `docs/fix-proposals/YYYY-MM-DD-HH-<issue-slug>.md`:

```markdown
# Fix Proposal: <Issue Title>

**Generated:** 2026-04-10 2:30 PM PT
**Severity:** CRITICAL / WARNING
**Check:** <check_name>

## Problem
<what's wrong>

## Evidence
<raw diagnostics that triggered this>

## Root Cause Analysis
<Sonnet's analysis>

## Proposed Fix
<code changes with file paths>

## Files to Change
- file.py:line — description

## Risk Assessment
<impact analysis>
```

### Deduplication

- Before generating a fix spec, glob `docs/fix-proposals/` for files matching the same check slug (e.g., `*-log-errors.md`) modified within the last 24 hours (by file mtime)
- If a recent spec exists for the same check, append new evidence to that file instead of creating a new one
- Prevents duplicate specs for recurring issues (e.g., the same log error pattern firing every hour)

---

## File Structure

```
scripts/overwatch.py          # Main agent script
docs/fix-proposals/            # Generated fix specs (gitignored)
logs/overwatch.log             # Agent's own log file
```

### New .env Variables

```
ANTHROPIC_API_KEY=sk-ant-...   # For Sonnet fix spec calls
```

No other config needed — all check thresholds are hardcoded constants at the top of `overwatch.py` for simplicity.

---

## launchd Configuration

Plist: `~/Library/LaunchAgents/com.phmex.overwatch.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.phmex.overwatch</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Library/Frameworks/Python.framework/Versions/3.14/bin/python3</string>
        <string>/Users/jonaspenaso/Desktop/Phmex-S/scripts/overwatch.py</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>WorkingDirectory</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S</string>
    <key>StandardOutPath</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S/logs/overwatch.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/jonaspenaso/Desktop/Phmex-S/logs/overwatch.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Library/Frameworks/Python.framework/Versions/3.14/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

---

## Interaction with Existing Systems

| System | Relationship |
|--------|-------------|
| monitor_daemon.py | Overwatch is a superset — monitor_daemon can be retired once Overwatch is stable |
| auto_lifecycle.py | No overlap — lifecycle manages slots/promotions, Overwatch monitors health |
| telegram_commander.py | No overlap — commander handles user commands, Overwatch sends alerts |
| reconcile_phemex.py | Partial overlap on Check 9 — Overwatch checks data accuracy, reconcile auto-applies fixes. Both can coexist. |
| SIGALRM watchdog (bot.py) | Complementary — SIGALRM handles intra-cycle freezes, Overwatch handles inter-cycle health |

---

## What Overwatch Does NOT Do

- No parameter changes
- No code edits (except auto-restart if bot is dead)
- No trading decisions
- No modifications to trading_state.json
- No slot management (that's auto_lifecycle.py)
- Fix specs are proposals only — human or Claude Code session implements them

---

## Constraints Respected

- Own ccxt client instance (lessons.md #11 — thread safety)
- 12-hour PT time in all alerts and fix specs (lessons.md #8)
- No interaction with bot's main process — read-only except restart
- `docs/fix-proposals/` gitignored to avoid cluttering history
- Anthropic SDK used directly (not Claude Code CLI) — works on Pro plan

---

## Dependencies

- `anthropic` Python package (pip install anthropic)
- `ccxt` (already installed)
- `requests` (already installed)
- `python-dotenv` (already installed)
