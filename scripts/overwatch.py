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
