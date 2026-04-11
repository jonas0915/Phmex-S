# Overwatch Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an hourly health-monitoring agent that checks bot runtime, code quality, and data accuracy — alerting via Telegram and generating Claude Sonnet fix specs when issues are found.

**Architecture:** A single Python script (`scripts/overwatch.py`) runs via launchd every hour. It performs 11 checks across 3 categories, sends Telegram alerts only when issues are found, and calls Claude Sonnet API to generate structured fix proposals saved to `docs/fix-proposals/`. The script uses its own ccxt client (thread-safe, per lessons.md) and follows the same patterns as `monitor_daemon.py` and `notifier.py`.

**Tech Stack:** Python 3.14, ccxt, anthropic SDK, requests, launchd

**Spec:** `docs/superpowers/specs/2026-04-10-overwatch-agent-design.md`

---

## Task 1: Project Setup + Script Skeleton

**Files:**
- Create: `scripts/overwatch.py`
- Create: `docs/fix-proposals/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Create fix-proposals directory**

```bash
mkdir -p docs/fix-proposals
touch docs/fix-proposals/.gitkeep
```

- [ ] **Step 2: Add fix-proposals contents to .gitignore**

Append to `.gitignore`:
```
docs/fix-proposals/*.md
```

This keeps the directory tracked but ignores generated specs.

- [ ] **Step 3: Install anthropic SDK**

```bash
pip3 install anthropic
```

Verify: `python3 -c "import anthropic; print(anthropic.__version__)"`

- [ ] **Step 4: Add ANTHROPIC_API_KEY to .env**

Append to `.env`:
```
ANTHROPIC_API_KEY=
```

Jonas will fill in the actual key. The script gracefully degrades if missing (skips fix spec generation, still sends Telegram alerts).

- [ ] **Step 5: Create overwatch.py skeleton**

Create `scripts/overwatch.py`:

```python
#!/usr/bin/env python3
"""Overwatch Agent — Hourly health monitor for Phmex-S trading bot.

Checks runtime health, code quality, and data accuracy.
Alerts via Telegram. Generates Claude Sonnet fix specs for issues found.
"""

import os
import sys
import json
import re
import subprocess
import time
import logging
import glob as glob_mod
from datetime import datetime, timedelta
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────
BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BOT_DIR, ".env"))

import requests

LOG_FILE = os.path.join(BOT_DIR, "logs", "bot.log")
STATE_FILE = os.path.join(BOT_DIR, "trading_state.json")
FIX_DIR = os.path.join(BOT_DIR, "docs", "fix-proposals")
REPORTS_DIR = os.path.join(BOT_DIR, "reports")

os.makedirs(FIX_DIR, exist_ok=True)

# ── logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [OVERWATCH] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BOT_DIR, "logs", "overwatch.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("overwatch")

# ── thresholds ─────────────────────────────────────────────────────────
BALANCE_CRITICAL_USD = 5.0     # unexplained balance drop → CRITICAL
BALANCE_WARNING_USD = 2.0      # unexplained balance drop → WARNING
MAX_LOG_ERRORS = 5             # unique error patterns in 1 hr → WARNING
MAX_WS_STALE_EVENTS = 3       # stale/reconnect events in 1 hr → WARNING
MIN_FEE_USD = 0.02             # trades with fee below this → WARNING
PNL_TOLERANCE = 0.05           # report vs state PnL mismatch tolerance
WR_TOLERANCE = 1.0             # report vs state WR mismatch tolerance (percentage points)

# ── Telegram ───────────────────────────────────────────────────────────
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def tg_send(message: str):
    """Send Telegram message. Silent failure if not configured."""
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.debug(f"Telegram send failed: {e}")


# ── check result ───────────────────────────────────────────────────────
class CheckResult:
    """Result from a single health check."""

    def __init__(self, name: str, severity: str, message: str, diagnostics: str = ""):
        self.name = name              # e.g. "process_alive"
        self.severity = severity      # "OK", "WARNING", "CRITICAL"
        self.message = message        # human-readable summary
        self.diagnostics = diagnostics  # raw evidence for fix spec

    def __repr__(self):
        return f"CheckResult({self.name}, {self.severity}, {self.message!r})"


# ── helpers ────────────────────────────────────────────────────────────
def get_recent_log_lines(minutes: int = 60) -> list[str]:
    """Read bot.log lines from the last N minutes."""
    if not os.path.exists(LOG_FILE):
        return []
    cutoff = datetime.now() - timedelta(minutes=minutes)
    lines = []
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        for line in f:
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", clean)
            if match:
                try:
                    ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff:
                        lines.append(clean)
                except ValueError:
                    pass
    return lines


def load_state() -> dict:
    """Load trading_state.json."""
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def utc_to_pt_12hr(utc_hour: int) -> str:
    """Convert UTC hour to 12-hour PT string (PDT = UTC-7)."""
    pt = (utc_hour - 7) % 24
    suffix = "AM" if pt < 12 else "PM"
    display = pt if pt <= 12 else pt - 12
    if display == 0:
        display = 12
    return f"{display} {suffix} PT"


def now_pt_12hr() -> str:
    """Current time in 12-hour PT format."""
    utc_now = datetime.utcnow()
    pt = utc_now - timedelta(hours=7)
    return pt.strftime("%-I:%M %p PT")


# ── check stubs (implemented in later tasks) ───────────────────────────
def check_process_alive() -> CheckResult:
    return CheckResult("process_alive", "OK", "Not implemented yet")


def check_log_errors() -> CheckResult:
    return CheckResult("log_errors", "OK", "Not implemented yet")


def check_ws_freshness() -> CheckResult:
    return CheckResult("ws_freshness", "OK", "Not implemented yet")


def check_position_desync() -> CheckResult:
    return CheckResult("position_desync", "OK", "Not implemented yet")


def check_balance_anomaly() -> CheckResult:
    return CheckResult("balance_anomaly", "OK", "Not implemented yet")


def check_syntax() -> CheckResult:
    return CheckResult("syntax", "OK", "Not implemented yet")


def check_pycache_stale() -> CheckResult:
    return CheckResult("pycache_stale", "OK", "Not implemented yet")


def check_dirty_tree() -> CheckResult:
    return CheckResult("dirty_tree", "OK", "Not implemented yet")


def check_trade_reconciliation() -> CheckResult:
    return CheckResult("trade_reconciliation", "OK", "Not implemented yet")


def check_report_accuracy() -> CheckResult:
    return CheckResult("report_accuracy", "OK", "Not implemented yet")


def check_fee_capture() -> CheckResult:
    return CheckResult("fee_capture", "OK", "Not implemented yet")


# ── orchestrator ───────────────────────────────────────────────────────
def run_all_checks() -> list[CheckResult]:
    """Run all 11 checks and return results."""
    checks = [
        check_process_alive,
        check_log_errors,
        check_ws_freshness,
        check_position_desync,
        check_balance_anomaly,
        check_syntax,
        check_pycache_stale,
        check_dirty_tree,
        check_trade_reconciliation,
        check_report_accuracy,
        check_fee_capture,
    ]
    results = []
    for check_fn in checks:
        try:
            result = check_fn()
            results.append(result)
            if result.severity != "OK":
                logger.info(f"{result.severity}: {result.name} — {result.message}")
            else:
                logger.debug(f"OK: {result.name}")
        except Exception as e:
            logger.exception(f"Check {check_fn.__name__} crashed: {e}")
            results.append(CheckResult(check_fn.__name__, "WARNING",
                                       f"Check crashed: {e}", str(e)))
    return results


def send_alert(failures: list[CheckResult]):
    """Send batched Telegram alert for all failures."""
    criticals = [r for r in failures if r.severity == "CRITICAL"]
    warnings = [r for r in failures if r.severity == "WARNING"]

    lines = []
    if criticals:
        lines.append(f"🚨 <b>OVERWATCH — {len(criticals)} CRITICAL</b>\n")
        for r in criticals:
            lines.append(f"❌ {r.message}")
    if warnings:
        lines.append(f"\n⚠️ <b>{len(warnings)} warnings</b>\n")
        for r in warnings:
            lines.append(f"⚠️ {r.message}")

    # Add fix spec pointer if any diagnostics generated
    if any(r.diagnostics for r in failures):
        lines.append(f"\n📋 Fix specs: docs/fix-proposals/")

    lines.append(f"\n🕐 {now_pt_12hr()}")
    tg_send("\n".join(lines))


def main():
    logger.info("=== Overwatch run started ===")
    results = run_all_checks()

    failures = [r for r in results if r.severity != "OK"]
    if failures:
        logger.info(f"{len(failures)} issue(s) found")
        send_alert(failures)
        generate_fix_specs(failures)  # implemented in Task 5
    else:
        logger.info("All checks passed — no alert sent")

    logger.info("=== Overwatch run complete ===")


def generate_fix_specs(failures: list[CheckResult]):
    """Stub — implemented in Task 5."""
    pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Syntax check**

Run: `python3 -m py_compile scripts/overwatch.py`
Expected: No output (clean compile)

- [ ] **Step 7: Dry run the skeleton**

Run: `cd ~/Desktop/Phmex-S && python3 scripts/overwatch.py`
Expected: Log output showing all checks as "OK" (stubs), "All checks passed — no alert sent", no Telegram message.

- [ ] **Step 8: Commit**

```bash
git add scripts/overwatch.py docs/fix-proposals/.gitkeep .gitignore
git commit -m "feat: overwatch agent skeleton — framework, helpers, telegram, check stubs"
```

---

## Task 2: Runtime Health Checks (Checks 1-5)

**Files:**
- Modify: `scripts/overwatch.py` (replace check stubs)

- [ ] **Step 1: Implement check_process_alive with auto-restart**

Replace the `check_process_alive` stub in `scripts/overwatch.py`:

```python
def check_process_alive() -> CheckResult:
    """Check 1: Is the bot process running? Auto-restart if dead."""
    try:
        result = subprocess.run(
            ["bash", "-c", "ps aux | grep 'Python.*main' | grep -v grep"],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            pid = result.stdout.strip().split()[1]
            return CheckResult("process_alive", "OK", f"Bot running (PID {pid})")

        # Bot is dead — attempt auto-restart
        logger.warning("Bot process not found — attempting auto-restart")
        restart_cmd = (
            f"cd {BOT_DIR} && rm -rf __pycache__ && "
            "/Library/Frameworks/Python.framework/Versions/3.14/Resources/"
            "Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &"
        )
        subprocess.run(["bash", "-c", restart_cmd], timeout=15)
        time.sleep(10)

        # Re-check
        result = subprocess.run(
            ["bash", "-c", "ps aux | grep 'Python.*main' | grep -v grep"],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            pid = result.stdout.strip().split()[1]
            return CheckResult("process_alive", "WARNING",
                               f"Bot was dead — auto-restarted (PID {pid})",
                               "Bot process was not found. Auto-restart succeeded.")
        else:
            return CheckResult("process_alive", "CRITICAL",
                               "Bot is DOWN — auto-restart FAILED",
                               "Bot process not found. Auto-restart attempted but process did not start. "
                               "Check logs/bot.log for crash reason.")
    except Exception as e:
        return CheckResult("process_alive", "WARNING",
                           f"Could not check process: {e}", str(e))
```

- [ ] **Step 2: Implement check_log_errors**

Replace the `check_log_errors` stub:

```python
def check_log_errors() -> CheckResult:
    """Check 2: Scan last 60 min of bot.log for ERROR/CRITICAL entries."""
    BENIGN_PATTERNS = ["[TIMEOUT]", "fetch_funding_rate", "Rate limit"]
    lines = get_recent_log_lines(minutes=60)
    error_lines = []
    for line in lines:
        if " ERROR " in line or " CRITICAL " in line:
            if not any(bp in line for bp in BENIGN_PATTERNS):
                error_lines.append(line)

    # Deduplicate by message pattern (strip timestamp + level)
    unique_patterns = set()
    for line in error_lines:
        # Extract message after timestamp and level
        match = re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+ (.+)", line)
        if match:
            unique_patterns.add(match.group(1)[:100])  # first 100 chars

    if len(unique_patterns) > MAX_LOG_ERRORS:
        sample = "\n".join(error_lines[:20])  # first 20 for diagnostics
        return CheckResult("log_errors", "WARNING",
                           f"{len(unique_patterns)} unique error patterns in last hour",
                           f"Found {len(error_lines)} total error lines, "
                           f"{len(unique_patterns)} unique patterns.\n\nSample:\n{sample}")
    return CheckResult("log_errors", "OK",
                        f"{len(unique_patterns)} error pattern(s) — within threshold")
```

- [ ] **Step 3: Implement check_ws_freshness**

Replace the `check_ws_freshness` stub:

```python
def check_ws_freshness() -> CheckResult:
    """Check 3: Grep bot.log for WS stale/reconnect events in last hour."""
    lines = get_recent_log_lines(minutes=60)
    stale_events = [l for l in lines if "[STALE]" in l or "[WS] reconnect" in l.lower()
                    or "ws reconnect" in l.lower() or "WebSocket" in l and "disconnect" in l.lower()]

    if len(stale_events) > MAX_WS_STALE_EVENTS:
        sample = "\n".join(stale_events[:10])
        return CheckResult("ws_freshness", "WARNING",
                           f"{len(stale_events)} WS stale/reconnect events in last hour",
                           f"WebSocket instability detected.\n\nEvents:\n{sample}")
    return CheckResult("ws_freshness", "OK",
                        f"{len(stale_events)} WS event(s) — within threshold")
```

- [ ] **Step 4: Implement check_position_desync**

Replace the `check_position_desync` stub:

```python
def check_position_desync() -> CheckResult:
    """Check 4: Compare trading_state.json positions vs exchange positions."""
    try:
        # Create dedicated ccxt client (thread-safety — lessons.md #11)
        import ccxt as ccxt_lib
        exchange_name = os.getenv("EXCHANGE", "phemex")
        client = getattr(ccxt_lib, exchange_name)({
            "apiKey": os.getenv("API_KEY", ""),
            "secret": os.getenv("API_SECRET", ""),
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "swap"},
        })
        client.load_markets()

        # Exchange positions
        raw_positions = client.fetch_positions()
        exchange_positions = {}
        for p in raw_positions:
            contracts = float(p.get("contracts", 0) or 0)
            if contracts > 0:
                exchange_positions[p["symbol"]] = {
                    "side": p.get("side", ""),
                    "contracts": contracts,
                    "entryPrice": p.get("entryPrice"),
                }

        # Local state positions
        state = load_state()
        local_positions = set()
        if "positions" in state and isinstance(state["positions"], dict):
            local_positions = set(state["positions"].keys())

        # Compare
        exchange_syms = set(exchange_positions.keys())
        ghost = exchange_syms - local_positions      # on exchange, not in state
        phantom = local_positions - exchange_syms    # in state, not on exchange

        issues = []
        if ghost:
            issues.append(f"Ghost position(s) on exchange not in state: {', '.join(ghost)}")
        if phantom:
            issues.append(f"Phantom position(s) in state not on exchange: {', '.join(phantom)}")

        if ghost:
            return CheckResult("position_desync", "CRITICAL",
                               f"Position desync: {'; '.join(issues)}",
                               json.dumps({"ghost": list(ghost), "phantom": list(phantom),
                                           "exchange": {k: v for k, v in exchange_positions.items()}}))
        if phantom:
            return CheckResult("position_desync", "WARNING",
                               f"Position desync: {'; '.join(issues)}",
                               json.dumps({"phantom": list(phantom)}))

        return CheckResult("position_desync", "OK",
                           f"Positions in sync ({len(exchange_syms)} open)")
    except Exception as e:
        return CheckResult("position_desync", "WARNING",
                           f"Could not check positions: {e}", str(e))
```

- [ ] **Step 5: Implement check_balance_anomaly**

Replace the `check_balance_anomaly` stub:

```python
def check_balance_anomaly() -> CheckResult:
    """Check 5: Verify balance hasn't dropped more than expected from trades."""
    try:
        # Fetch current balance
        import ccxt as ccxt_lib
        exchange_name = os.getenv("EXCHANGE", "phemex")
        client = getattr(ccxt_lib, exchange_name)({
            "apiKey": os.getenv("API_KEY", ""),
            "secret": os.getenv("API_SECRET", ""),
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "swap"},
        })
        balance = client.fetch_balance()
        current_balance = float(balance.get("USDT", {}).get("total", 0))

        # Get expected balance from state
        state = load_state()
        peak_balance = state.get("peak_balance", 0)
        closed_trades = state.get("closed_trades", [])

        # Sum PnL from last 24 hours of trades
        recent_pnl = 0.0
        for trade in closed_trades[-50:]:  # check last 50 trades
            pnl = trade.get("pnl_usdt", 0)
            if isinstance(pnl, (int, float)):
                recent_pnl += pnl

        # Use peak_balance as baseline if available
        if peak_balance > 0:
            expected_min = peak_balance - abs(recent_pnl) - BALANCE_CRITICAL_USD
            diff = peak_balance - current_balance

            if diff > BALANCE_CRITICAL_USD and diff > abs(recent_pnl) + BALANCE_CRITICAL_USD:
                return CheckResult("balance_anomaly", "CRITICAL",
                                   f"Balance ${current_balance:.2f} is ${diff:.2f} below peak "
                                   f"(${peak_balance:.2f}) — exceeds trade PnL explanation",
                                   f"Current: ${current_balance:.2f}, Peak: ${peak_balance:.2f}, "
                                   f"Recent PnL sum: ${recent_pnl:.2f}, Unexplained gap: "
                                   f"${diff - abs(recent_pnl):.2f}")
            if diff > BALANCE_WARNING_USD and diff > abs(recent_pnl) + BALANCE_WARNING_USD:
                return CheckResult("balance_anomaly", "WARNING",
                                   f"Balance ${current_balance:.2f} is ${diff:.2f} below peak",
                                   f"Current: ${current_balance:.2f}, Peak: ${peak_balance:.2f}")

        return CheckResult("balance_anomaly", "OK",
                           f"Balance ${current_balance:.2f} — within expected range")
    except Exception as e:
        return CheckResult("balance_anomaly", "WARNING",
                           f"Could not check balance: {e}", str(e))
```

- [ ] **Step 6: Syntax check**

Run: `python3 -m py_compile scripts/overwatch.py`
Expected: No output (clean compile)

- [ ] **Step 7: Test runtime checks**

Run: `cd ~/Desktop/Phmex-S && python3 scripts/overwatch.py`
Expected: All 5 runtime checks produce results (OK or actual findings). No crashes. Log output shows each check name and status.

- [ ] **Step 8: Commit**

```bash
git add scripts/overwatch.py
git commit -m "feat(overwatch): implement runtime health checks 1-5 — process, logs, WS, desync, balance"
```

---

## Task 3: Code Quality Checks (Checks 6-8)

**Files:**
- Modify: `scripts/overwatch.py` (replace check stubs)

- [ ] **Step 1: Implement check_syntax**

Replace the `check_syntax` stub in `scripts/overwatch.py`:

```python
CORE_PY_FILES = [
    "main.py", "bot.py", "risk_manager.py", "strategies.py",
    "exchange.py", "ws_feed.py", "config.py", "notifier.py",
    "web_dashboard.py", "war_room.py", "strategy_slot.py",
]


def check_syntax() -> CheckResult:
    """Check 6: py_compile all core .py files."""
    failures = []
    for filename in CORE_PY_FILES:
        filepath = os.path.join(BOT_DIR, filename)
        if not os.path.exists(filepath):
            continue
        result = subprocess.run(
            ["python3", "-m", "py_compile", filepath],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            failures.append(f"{filename}: {result.stderr.strip()}")

    if failures:
        return CheckResult("syntax", "CRITICAL",
                           f"Syntax errors in {len(failures)} file(s): "
                           f"{', '.join(f.split(':')[0] for f in failures)}",
                           "\n".join(failures))
    return CheckResult("syntax", "OK", f"All {len(CORE_PY_FILES)} files compile clean")
```

- [ ] **Step 2: Implement check_pycache_stale**

Replace the `check_pycache_stale` stub:

```python
def check_pycache_stale() -> CheckResult:
    """Check 7: Flag if any .pyc is older than its .py source."""
    cache_dir = os.path.join(BOT_DIR, "__pycache__")
    if not os.path.exists(cache_dir):
        return CheckResult("pycache_stale", "OK", "No __pycache__ directory")

    stale = []
    for pyc_file in glob_mod.glob(os.path.join(cache_dir, "*.pyc")):
        # Extract source filename from pyc name (e.g., bot.cpython-314.pyc → bot.py)
        basename = os.path.basename(pyc_file)
        source_name = basename.split(".")[0] + ".py"
        source_path = os.path.join(BOT_DIR, source_name)

        if os.path.exists(source_path):
            pyc_mtime = os.path.getmtime(pyc_file)
            src_mtime = os.path.getmtime(source_path)
            if pyc_mtime < src_mtime:
                stale.append(source_name)

    if stale:
        return CheckResult("pycache_stale", "WARNING",
                           f"Stale __pycache__ for: {', '.join(stale)}",
                           f"These .pyc files are older than their .py source. "
                           f"Bot may be running old bytecode. "
                           f"Fix: rm -rf __pycache__ && restart bot.\n"
                           f"Stale files: {', '.join(stale)}")
    return CheckResult("pycache_stale", "OK", "All bytecode up to date")
```

- [ ] **Step 3: Implement check_dirty_tree**

Replace the `check_dirty_tree` stub:

```python
CORE_BOT_FILES = {"bot.py", "risk_manager.py", "strategies.py", "exchange.py",
                  "config.py", "main.py", "ws_feed.py"}


def check_dirty_tree() -> CheckResult:
    """Check 8: Uncommitted changes on core bot files."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, cwd=BOT_DIR,
        )
        dirty_core = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            # git status --porcelain: first 2 chars are status, then space, then path
            filepath = line[3:].strip()
            filename = os.path.basename(filepath)
            if filename in CORE_BOT_FILES:
                dirty_core.append(f"{line[:2].strip()} {filename}")

        if dirty_core:
            return CheckResult("dirty_tree", "WARNING",
                               f"Uncommitted changes in: {', '.join(f.split()[-1] for f in dirty_core)}",
                               f"Core bot files have uncommitted changes. "
                               f"Running code may not match git history.\n"
                               f"Files: {'; '.join(dirty_core)}")
        return CheckResult("dirty_tree", "OK", "Working tree clean for core files")
    except Exception as e:
        return CheckResult("dirty_tree", "WARNING",
                           f"Could not check git status: {e}", str(e))
```

- [ ] **Step 4: Move CORE_PY_FILES and CORE_BOT_FILES to the thresholds section**

Move the two constants (`CORE_PY_FILES` and `CORE_BOT_FILES`) up to the thresholds section at the top of the file, after `WR_TOLERANCE`. This keeps all configuration in one place.

- [ ] **Step 5: Syntax check**

Run: `python3 -m py_compile scripts/overwatch.py`
Expected: No output (clean compile)

- [ ] **Step 6: Test code quality checks**

Run: `cd ~/Desktop/Phmex-S && python3 scripts/overwatch.py`
Expected: All 8 checks (5 runtime + 3 code quality) produce results. The dirty_tree check will likely show WARNING since there are uncommitted changes in .env and config.py (per git status). That's expected.

- [ ] **Step 7: Commit**

```bash
git add scripts/overwatch.py
git commit -m "feat(overwatch): implement code quality checks 6-8 — syntax, pycache, dirty tree"
```

---

## Task 4: Data Accuracy Checks (Checks 9-11)

**Files:**
- Modify: `scripts/overwatch.py` (replace check stubs)

- [ ] **Step 1: Implement check_trade_reconciliation**

Replace the `check_trade_reconciliation` stub in `scripts/overwatch.py`:

```python
def check_trade_reconciliation() -> CheckResult:
    """Check 9: Compare recent trading_state.json trades vs Phemex fills."""
    try:
        state = load_state()
        closed_trades = state.get("closed_trades", [])
        if not closed_trades:
            return CheckResult("trade_reconciliation", "OK", "No closed trades to reconcile")

        # Get last 10 trades from local state
        recent_local = closed_trades[-10:]

        # Fetch recent trades from exchange
        import ccxt as ccxt_lib
        exchange_name = os.getenv("EXCHANGE", "phemex")
        client = getattr(ccxt_lib, exchange_name)({
            "apiKey": os.getenv("API_KEY", ""),
            "secret": os.getenv("API_SECRET", ""),
            "enableRateLimit": True,
            "timeout": 10000,
            "options": {"defaultType": "swap"},
        })
        client.load_markets()

        mismatches = []
        for trade in recent_local:
            symbol = trade.get("symbol", "")
            local_entry = trade.get("entry", 0)
            local_exit = trade.get("exit", 0)
            local_fee = trade.get("fee", None)

            if not symbol or not local_entry:
                continue

            # Fetch exchange trades for this symbol (last 50)
            try:
                exchange_trades = client.fetch_my_trades(symbol, limit=50)
            except Exception:
                continue  # skip symbols we can't fetch

            if not exchange_trades:
                continue

            # Find matching fill by price proximity
            entry_matched = False
            for et in exchange_trades:
                ex_price = float(et.get("price", 0))
                if abs(ex_price - local_entry) / local_entry < 0.0001:  # 0.01% tolerance
                    entry_matched = True
                    # Check fee
                    ex_fee = float(et.get("fee", {}).get("cost", 0) or 0)
                    if local_fee is not None and abs(ex_fee - local_fee) > 0.01:
                        mismatches.append(
                            f"{symbol}: fee mismatch — local ${local_fee:.4f} vs exchange ${ex_fee:.4f}")
                    break

        if mismatches:
            return CheckResult("trade_reconciliation", "WARNING",
                               f"{len(mismatches)} trade reconciliation mismatch(es)",
                               "\n".join(mismatches))
        return CheckResult("trade_reconciliation", "OK",
                           f"Last {len(recent_local)} trades reconciled OK")
    except Exception as e:
        return CheckResult("trade_reconciliation", "WARNING",
                           f"Reconciliation check failed: {e}", str(e))
```

- [ ] **Step 2: Implement check_report_accuracy**

Replace the `check_report_accuracy` stub:

```python
def check_report_accuracy() -> CheckResult:
    """Check 10: Verify latest daily report matches trading_state.json."""
    try:
        # Find latest report
        report_files = sorted(glob_mod.glob(os.path.join(REPORTS_DIR, "*.md")))
        if not report_files:
            return CheckResult("report_accuracy", "OK", "No reports to verify")

        latest_report = report_files[-1]
        report_date = os.path.basename(latest_report).replace(".md", "")

        with open(latest_report, encoding="utf-8") as f:
            report_text = f.read()

        # Parse report metrics
        trade_count_match = re.search(r"Trades: (\d+)", report_text)
        wr_match = re.search(r"Win Rate: ([\d.]+)%", report_text)
        pnl_match = re.search(r"Net PnL: \$([+-]?[\d.]+)", report_text)

        if not trade_count_match:
            return CheckResult("report_accuracy", "OK",
                               "Could not parse report metrics — skipping")

        report_trades = int(trade_count_match.group(1))
        report_wr = float(wr_match.group(1)) if wr_match else None
        report_pnl = float(pnl_match.group(1)) if pnl_match else None

        # Calculate from trading_state.json
        state = load_state()
        closed_trades = state.get("closed_trades", [])

        # Filter to report date
        day_trades = []
        for t in closed_trades:
            exit_time = t.get("exit_time", "")
            if isinstance(exit_time, str) and exit_time.startswith(report_date):
                day_trades.append(t)

        state_trades = len(day_trades)
        state_wins = sum(1 for t in day_trades if t.get("pnl_usdt", 0) > 0)
        state_wr = (state_wins / state_trades * 100) if state_trades > 0 else 0
        state_pnl = sum(t.get("pnl_usdt", 0) for t in day_trades)

        mismatches = []
        if report_trades != state_trades:
            mismatches.append(f"Trade count: report={report_trades}, state={state_trades}")
        if report_wr is not None and abs(report_wr - state_wr) > WR_TOLERANCE:
            mismatches.append(f"Win rate: report={report_wr:.1f}%, state={state_wr:.1f}%")
        if report_pnl is not None and abs(report_pnl - state_pnl) > PNL_TOLERANCE:
            mismatches.append(f"Net PnL: report=${report_pnl:.2f}, state=${state_pnl:.2f}")

        if mismatches:
            return CheckResult("report_accuracy", "WARNING",
                               f"Report {report_date} has {len(mismatches)} mismatch(es)",
                               f"Report: {latest_report}\n" + "\n".join(mismatches))
        return CheckResult("report_accuracy", "OK",
                           f"Report {report_date} matches state data")
    except Exception as e:
        return CheckResult("report_accuracy", "WARNING",
                           f"Report accuracy check failed: {e}", str(e))
```

- [ ] **Step 3: Implement check_fee_capture**

Replace the `check_fee_capture` stub:

```python
def check_fee_capture() -> CheckResult:
    """Check 11: Flag closed trades with missing or suspiciously low fees."""
    try:
        state = load_state()
        closed_trades = state.get("closed_trades", [])
        if not closed_trades:
            return CheckResult("fee_capture", "OK", "No closed trades to check")

        # Check last 24 hours of trades
        cutoff = datetime.now() - timedelta(hours=24)
        recent_trades = []
        for t in closed_trades:
            exit_time = t.get("exit_time", "")
            if isinstance(exit_time, str) and exit_time:
                try:
                    ts = datetime.strptime(exit_time[:19], "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff:
                        recent_trades.append(t)
                except ValueError:
                    pass

        if not recent_trades:
            return CheckResult("fee_capture", "OK", "No trades in last 24h to check")

        bad_fees = []
        for t in recent_trades:
            fee = t.get("fee", None)
            symbol = t.get("symbol", "unknown")
            if fee is None:
                bad_fees.append(f"{symbol}: fee field missing")
            elif not isinstance(fee, (int, float)):
                bad_fees.append(f"{symbol}: fee not numeric ({fee!r})")
            elif fee < MIN_FEE_USD:
                bad_fees.append(f"{symbol}: fee=${fee:.4f} (below ${MIN_FEE_USD} threshold)")

        if bad_fees:
            return CheckResult("fee_capture", "WARNING",
                               f"{len(bad_fees)} trade(s) with missing/low fees in last 24h",
                               "\n".join(bad_fees))
        return CheckResult("fee_capture", "OK",
                           f"All {len(recent_trades)} recent trades have valid fees")
    except Exception as e:
        return CheckResult("fee_capture", "WARNING",
                           f"Fee capture check failed: {e}", str(e))
```

- [ ] **Step 4: Syntax check**

Run: `python3 -m py_compile scripts/overwatch.py`
Expected: No output (clean compile)

- [ ] **Step 5: Test all 11 checks**

Run: `cd ~/Desktop/Phmex-S && python3 scripts/overwatch.py`
Expected: All 11 checks produce results. Log shows each check name and status. Data accuracy checks may find real issues (that's the point).

- [ ] **Step 6: Commit**

```bash
git add scripts/overwatch.py
git commit -m "feat(overwatch): implement data accuracy checks 9-11 — reconciliation, report, fees"
```

---

## Task 5: Sonnet Fix Spec Generation

**Files:**
- Modify: `scripts/overwatch.py` (replace `generate_fix_specs` stub)

- [ ] **Step 1: Implement generate_fix_specs**

Replace the `generate_fix_specs` stub in `scripts/overwatch.py`:

```python
def generate_fix_specs(failures: list[CheckResult]):
    """Call Claude Sonnet to generate fix specs for each failure with diagnostics."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.info("No ANTHROPIC_API_KEY — skipping fix spec generation")
        return

    # Only generate specs for failures that have diagnostics
    actionable = [f for f in failures if f.diagnostics]
    if not actionable:
        logger.info("No actionable diagnostics — skipping fix specs")
        return

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping fix specs")
        return

    client = anthropic.Anthropic(api_key=api_key)

    for failure in actionable:
        slug = failure.name.replace("_", "-")
        spec_pattern = os.path.join(FIX_DIR, f"*-{slug}.md")
        existing = glob_mod.glob(spec_pattern)

        # Dedup: if a spec for this check exists from last 24h, append instead
        recent_existing = None
        for f in existing:
            if time.time() - os.path.getmtime(f) < 86400:  # 24 hours
                recent_existing = f
                break

        if recent_existing:
            _append_to_existing_spec(recent_existing, failure)
            continue

        # Generate new fix spec via Sonnet
        _generate_new_spec(client, failure, slug)


def _append_to_existing_spec(filepath: str, failure: CheckResult):
    """Append new evidence to an existing fix spec."""
    timestamp = now_pt_12hr()
    appendix = (
        f"\n\n---\n\n## Update — {timestamp}\n\n"
        f"**Status:** Issue persists\n\n"
        f"**New Evidence:**\n```\n{failure.diagnostics}\n```\n"
    )
    with open(filepath, "a") as f:
        f.write(appendix)
    logger.info(f"Appended new evidence to {os.path.basename(filepath)}")


def _generate_new_spec(client, failure: CheckResult, slug: str):
    """Generate a new fix spec via Claude Sonnet."""
    prompt = (
        f"Issue: {failure.name} — {failure.severity}\n"
        f"Description: {failure.message}\n\n"
        f"Evidence:\n{failure.diagnostics}\n\n"
        f"Context:\n"
        f"- Bot: Phmex-S Sentinel v11, crypto perpetual futures scalper on Phemex\n"
        f"- Stack: Python 3.14, ccxt, WebSocket feeds, 60s main loop\n"
        f"- Key files: bot.py (main loop), risk_manager.py (exits), "
        f"strategies.py (signals), exchange.py (API)\n"
        f"- The bot is LIVE with real money — safety is paramount\n\n"
        f"Write a fix spec with these sections:\n"
        f"1. Problem — what is wrong (1-2 sentences)\n"
        f"2. Root Cause Analysis — why it happened\n"
        f"3. Proposed Fix — specific code changes with file paths\n"
        f"4. Files to Change — list of file:line references\n"
        f"5. Risk Assessment — what could go wrong with the fix\n"
    )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=(
                "You are a senior Python developer reviewing a live crypto trading bot. "
                "Write concise, actionable fix specs. Include specific file paths and "
                "code snippets. Prioritize safety — this bot trades real money."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        spec_content = response.content[0].text
        timestamp = datetime.now().strftime("%Y-%m-%d-%H")
        filename = f"{timestamp}-{slug}.md"
        filepath = os.path.join(FIX_DIR, filename)

        header = (
            f"# Fix Proposal: {failure.message}\n\n"
            f"**Generated:** {now_pt_12hr()}\n"
            f"**Severity:** {failure.severity}\n"
            f"**Check:** {failure.name}\n\n"
            f"---\n\n"
        )

        with open(filepath, "w") as f:
            f.write(header + spec_content)

        logger.info(f"Fix spec written: {filename}")
    except Exception as e:
        logger.error(f"Failed to generate fix spec for {failure.name}: {e}")
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile scripts/overwatch.py`
Expected: No output (clean compile)

- [ ] **Step 3: Test fix spec generation (dry run)**

Run the script. If all checks pass (no failures), the fix spec generator won't fire — that's correct behavior. To verify the Sonnet integration works, you can temporarily force a failure:

```bash
cd ~/Desktop/Phmex-S && python3 -c "
import sys; sys.path.insert(0, '.')
from scripts.overwatch import CheckResult, generate_fix_specs
test_failure = CheckResult('test_check', 'WARNING', 'Test issue for verification',
                           'This is a test diagnostic — ignore this fix spec.')
generate_fix_specs([test_failure])
print('Check docs/fix-proposals/ for output')
"
```

Expected: A file `docs/fix-proposals/YYYY-MM-DD-HH-test-check.md` is created with Sonnet's analysis. If no ANTHROPIC_API_KEY is set, the log says "No ANTHROPIC_API_KEY — skipping fix spec generation" (graceful degradation).

- [ ] **Step 4: Clean up test spec if generated**

```bash
rm -f docs/fix-proposals/*test-check*.md
```

- [ ] **Step 5: Commit**

```bash
git add scripts/overwatch.py
git commit -m "feat(overwatch): add Claude Sonnet fix spec generation with deduplication"
```

---

## Task 6: launchd Service + Final Integration

**Files:**
- Create: `~/Library/LaunchAgents/com.phmex.overwatch.plist`

- [ ] **Step 1: Create launchd plist**

Create `~/Library/LaunchAgents/com.phmex.overwatch.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
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

- [ ] **Step 2: Load the service**

```bash
launchctl load ~/Library/LaunchAgents/com.phmex.overwatch.plist
```

Verify: `launchctl list | grep overwatch`
Expected: Shows `com.phmex.overwatch` with a PID or exit status.

- [ ] **Step 3: Trigger a manual run to verify end-to-end**

```bash
launchctl start com.phmex.overwatch
```

Wait 30 seconds, then check:
```bash
tail -20 ~/Desktop/Phmex-S/logs/overwatch.log
```

Expected: Log shows "=== Overwatch run started ===", all 11 check results, and "=== Overwatch run complete ===" (or alert details if issues found).

- [ ] **Step 4: Verify Telegram delivery (if issues found)**

If any checks flagged issues, verify the Telegram alert arrived on Jonas's phone. If all checks passed, no Telegram message is expected — that's correct behavior.

- [ ] **Step 5: Commit the overwatch script (final state)**

```bash
cd ~/Desktop/Phmex-S
git add scripts/overwatch.py
git commit -m "feat(overwatch): complete agent — 11 checks, Telegram alerts, Sonnet fix specs, launchd"
```
