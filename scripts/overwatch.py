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
BALANCE_CRITICAL_USD = 5.0
BALANCE_WARNING_USD = 2.0
MAX_LOG_ERRORS = 5
MAX_WS_STALE_EVENTS = 3
MIN_FEE_USD = 0.02
PNL_TOLERANCE = 0.05
WR_TOLERANCE = 1.0

CORE_PY_FILES = [
    "main.py", "bot.py", "risk_manager.py", "strategies.py",
    "exchange.py", "ws_feed.py", "config.py", "notifier.py",
    "web_dashboard.py", "war_room.py", "strategy_slot.py",
]

CORE_BOT_FILES = {"bot.py", "risk_manager.py", "strategies.py", "exchange.py",
                  "config.py", "main.py", "ws_feed.py"}

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
        self.name = name
        self.severity = severity
        self.message = message
        self.diagnostics = diagnostics

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
        match = re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+ (.+)", line)
        if match:
            unique_patterns.add(match.group(1)[:100])

    if len(unique_patterns) > MAX_LOG_ERRORS:
        sample = "\n".join(error_lines[:20])
        return CheckResult("log_errors", "WARNING",
                           f"{len(unique_patterns)} unique error patterns in last hour",
                           f"Found {len(error_lines)} total error lines, "
                           f"{len(unique_patterns)} unique patterns.\n\nSample:\n{sample}")
    return CheckResult("log_errors", "OK",
                        f"{len(unique_patterns)} error pattern(s) — within threshold")


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


def check_position_desync() -> CheckResult:
    """Check 4: Compare trading_state.json positions vs exchange positions."""
    try:
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

        state = load_state()
        local_positions = set()
        if "positions" in state and isinstance(state["positions"], dict):
            local_positions = set(state["positions"].keys())

        exchange_syms = set(exchange_positions.keys())
        ghost = exchange_syms - local_positions
        phantom = local_positions - exchange_syms

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


def check_balance_anomaly() -> CheckResult:
    """Check 5: Verify balance hasn't dropped more than expected from trades."""
    try:
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

        state = load_state()
        peak_balance = state.get("peak_balance", 0)
        closed_trades = state.get("closed_trades", [])

        recent_pnl = 0.0
        for trade in closed_trades[-50:]:
            pnl = trade.get("pnl_usdt", 0)
            if isinstance(pnl, (int, float)):
                recent_pnl += pnl

        if peak_balance > 0:
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
        generate_fix_specs(failures)
    else:
        logger.info("All checks passed — no alert sent")

    logger.info("=== Overwatch run complete ===")


def generate_fix_specs(failures: list[CheckResult]):
    """Stub — implemented in Task 5."""
    pass


if __name__ == "__main__":
    main()
