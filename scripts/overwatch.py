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


def check_pycache_stale() -> CheckResult:
    """Check 7: Flag if any .pyc is older than its .py source."""
    cache_dir = os.path.join(BOT_DIR, "__pycache__")
    if not os.path.exists(cache_dir):
        return CheckResult("pycache_stale", "OK", "No __pycache__ directory")

    stale = []
    for pyc_file in glob_mod.glob(os.path.join(cache_dir, "*.pyc")):
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


def check_trade_reconciliation() -> CheckResult:
    """Check 9: Compare recent trading_state.json trades vs Phemex fills."""
    try:
        state = load_state()
        closed_trades = state.get("closed_trades", [])
        if not closed_trades:
            return CheckResult("trade_reconciliation", "OK", "No closed trades to reconcile")

        recent_local = closed_trades[-10:]

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
            local_fee = trade.get("fee", None)

            if not symbol or not local_entry:
                continue

            try:
                exchange_trades = client.fetch_my_trades(symbol, limit=50)
            except Exception:
                continue

            if not exchange_trades:
                continue

            entry_matched = False
            for et in exchange_trades:
                ex_price = float(et.get("price", 0))
                if abs(ex_price - local_entry) / local_entry < 0.0001:
                    entry_matched = True
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


def check_report_accuracy() -> CheckResult:
    """Check 10: Verify latest daily report matches trading_state.json."""
    try:
        report_files = sorted(glob_mod.glob(os.path.join(REPORTS_DIR, "*.md")))
        if not report_files:
            return CheckResult("report_accuracy", "OK", "No reports to verify")

        latest_report = report_files[-1]
        report_date = os.path.basename(latest_report).replace(".md", "")

        with open(latest_report, encoding="utf-8") as f:
            report_text = f.read()

        trade_count_match = re.search(r"Trades: (\d+)", report_text)
        wr_match = re.search(r"Win Rate: ([\d.]+)%", report_text)
        pnl_match = re.search(r"Net PnL: \$([+-]?[\d.]+)", report_text)

        if not trade_count_match:
            return CheckResult("report_accuracy", "OK",
                               "Could not parse report metrics — skipping")

        report_trades = int(trade_count_match.group(1))
        report_wr = float(wr_match.group(1)) if wr_match else None
        report_pnl = float(pnl_match.group(1)) if pnl_match else None

        state = load_state()
        closed_trades = state.get("closed_trades", [])

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


def check_fee_capture() -> CheckResult:
    """Check 11: Flag closed trades with missing or suspiciously low fees."""
    try:
        state = load_state()
        closed_trades = state.get("closed_trades", [])
        if not closed_trades:
            return CheckResult("fee_capture", "OK", "No closed trades to check")

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
