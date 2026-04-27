#!/usr/bin/env python3
"""
Phmex-S Monitoring Daemon
Runs via system cron every hour. Analyzes bot health, trade performance,
and flags issues via Telegram + local report files.

No Claude session needed — fully autonomous.
"""
import json
import os
import re
import requests
from datetime import datetime, timedelta
from collections import defaultdict

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BOT_DIR, "trading_state.json")
LOG_FILE = os.path.join(BOT_DIR, "logs", "bot.log")
REPORT_DIR = os.path.join(BOT_DIR, "reports")
ALERT_LOG = os.path.join(REPORT_DIR, "alerts.log")

os.makedirs(REPORT_DIR, exist_ok=True)

# Load env for Telegram
from dotenv import load_dotenv
load_dotenv(os.path.join(BOT_DIR, ".env"))

TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def tg_send(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass


def check_bot_alive():
    """Check if bot process is running."""
    import subprocess
    result = subprocess.run(
        ["ps", "aux"], capture_output=True, text=True
    )
    return "Python main.py" in result.stdout


def get_recent_log_lines(minutes=60):
    """Get log lines from the last N minutes."""
    if not os.path.exists(LOG_FILE):
        return []
    cutoff = datetime.now() - timedelta(minutes=minutes)
    lines = []
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        for line in f:
            clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
            # Parse timestamp
            match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', clean)
            if match:
                try:
                    ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                    if ts >= cutoff:
                        lines.append(clean)
                except ValueError:
                    pass
    return lines


def analyze_recent_trades(lines):
    """Parse entries and exits from recent log lines (LIVE only, excludes paper)."""
    entries = []
    exits = []
    for line in lines:
        # Skip paper slot lines — only count live trades
        if "[PAPER]" in line or "PAPER" in line:
            continue
        if "[ENTRY]" in line:
            entries.append(line)
        if "Position closed" in line and "[PAPER]" not in line:
            exits.append(line)
    return entries, exits


def parse_pnl(exit_line):
    """Extract PnL from a Position closed line."""
    match = re.search(r'PnL: ([+-]?\d+\.\d+) USDT', exit_line)
    if match:
        return float(match.group(1))
    return 0.0


def parse_reason(exit_line):
    """Extract exit reason."""
    match = re.search(r'Reason: (\w+)', exit_line)
    if match:
        return match.group(1)
    return "unknown"


def load_state():
    """Load trading state."""
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE) as f:
        return json.load(f)


def check_consecutive_losses(lines):
    """Check for consecutive losses (LIVE only, excludes paper)."""
    recent_exits = [l for l in lines if "Position closed" in l and "[PAPER]" not in l and "PAPER" not in l]
    consecutive = 0
    for exit_line in reversed(recent_exits):
        pnl = parse_pnl(exit_line)
        if pnl < 0:
            consecutive += 1
        else:
            break
    return consecutive


def run_monitor():
    now = datetime.now()
    alerts = []

    # Check for restart sentinel (from auto_lifecycle rollback)
    restart_sentinel = os.path.join(BOT_DIR, ".restart_bot")
    if os.path.exists(restart_sentinel):
        import subprocess
        tg_send("🔄 <b>Restarting bot</b> — auto-rollback triggered restart")
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "Python main.py" in line and "grep" not in line:
                pid = int(line.split()[1])
                subprocess.run(["kill", "-9", str(pid)], check=False)
        import time as _time
        _time.sleep(3)
        _log_fh = open(os.path.join(BOT_DIR, "logs", "bot.log"), "a")
        subprocess.Popen(
            ["/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python", "main.py"],
            cwd=BOT_DIR,
            stdout=_log_fh,
            stderr=subprocess.STDOUT,
        )
        _log_fh.close()
        os.remove(restart_sentinel)
        tg_send("✅ <b>Bot restarted</b> successfully")
        print(f"[MONITOR] Restart sentinel processed — bot restarted")
        return  # Skip normal monitoring this cycle

    # 1. Bot alive check
    bot_alive = check_bot_alive()
    if not bot_alive:
        alerts.append("BOT IS DOWN — no Python main.py process found!")

    # 2. Get recent activity
    lines = get_recent_log_lines(60)
    entries, exits = analyze_recent_trades(lines)

    # 3. Check for no activity (bot might be frozen)
    cycle_lines = [l for l in lines if "Cycle #" in l]
    if bot_alive and len(cycle_lines) == 0:
        alerts.append("BOT FROZEN — running but no cycles in last 60 min")

    # 4. Analyze recent trade performance
    if exits:
        pnls = [parse_pnl(e) for e in exits]
        total_pnl = sum(pnls)
        wins = sum(1 for p in pnls if p > 0)
        wr = (wins / len(pnls) * 100) if pnls else 0

        if total_pnl < -2.0:
            alerts.append(f"HOURLY LOSS: ${total_pnl:.2f} on {len(exits)} trades ({wr:.0f}% WR)")
        if len(pnls) >= 3 and wr == 0:
            alerts.append(f"ALL LOSSES: 0% WR on {len(pnls)} trades this hour")

    # 5. Check consecutive losses
    all_recent = get_recent_log_lines(180)  # last 3 hours
    consec = check_consecutive_losses(all_recent)
    if consec >= 5:
        alerts.append(f"STREAK: {consec} consecutive losses")

    # 6. Check drawdown from log (balance not stored in state file)
    state = load_state()
    peak = state.get("peak_balance", 0)
    # Parse balance from most recent STATS line in logs
    balance = 0
    for line in reversed(all_recent):
        match = re.search(r'Balance: ([\d.]+) USDT', line)
        if match:
            balance = float(match.group(1))
            break
    if peak > 0 and balance > 0:
        dd = (peak - balance) / peak * 100
        if dd > 15:
            # Sanity check: bot logs `print_stats(real_balance)` where
            # `real_balance = free + locked_margin`. By construction,
            # parsed_balance must be >= sum of position margins. If the
            # parsed value is LESS THAN the locked margin, it means
            # get_balance() returned 0 (API failure) and the STATS line is
            # reporting margin-only — STALE. Skip the false alert.
            # 2026-04-26 incident: 87% false alarm during 401 IP-mismatch window.
            positions = state.get("positions", {})
            locked_margin = sum(
                (p.get("margin", 0) or 0) for p in positions.values()
                if isinstance(p, dict)
            )
            if locked_margin > 0 and balance <= locked_margin + 0.5:
                # Stale/bad STATS — skip alert
                pass
            else:
                alerts.append(f"DRAWDOWN: {dd:.1f}% (balance ${balance:.2f}, peak ${peak:.2f})")

    # 7. Check for errors in logs
    error_lines = [l for l in lines if "[ERROR]" in l]
    if len(error_lines) >= 15:
        alerts.append(f"ERRORS: {len(error_lines)} errors in last hour")

    # 8. Check for connectivity issues (only real network errors, require 5+ to alert)
    conn_issues = [l for l in lines if "DNSLookupError" in l or "ConnectTimeoutError" in l or "ConnectionError" in l or "NetworkError" in l]
    if len(conn_issues) >= 5:
        alerts.append(f"CONNECTIVITY: {len(conn_issues)} connection issues in last hour")

    # Build hourly summary
    summary_parts = []
    summary_parts.append(f"{'ONLINE' if bot_alive else 'OFFLINE'}")
    summary_parts.append(f"Cycles: {len(cycle_lines)}")
    summary_parts.append(f"Entries: {len(entries)}")
    summary_parts.append(f"Exits: {len(exits)}")
    if exits:
        total_pnl = sum(parse_pnl(e) for e in exits)
        summary_parts.append(f"PnL: ${total_pnl:+.2f}")

    summary = " | ".join(summary_parts)

    # Log to alerts file
    with open(ALERT_LOG, "a") as f:
        f.write(f"[{now.strftime('%Y-%m-%d %H:%M')}] {summary}\n")
        for a in alerts:
            f.write(f"  ALERT: {a}\n")

    # Send Telegram if there are alerts
    if alerts:
        msg = f"⚠️ <b>Phmex-S Monitor</b>\n"
        msg += f"Time: {now.strftime('%H:%M')}\n\n"
        for a in alerts:
            msg += f"• {a}\n"
        tg_send(msg)

    # Generate daily report (runs alongside hourly check)
    # Only generate full report at specific hours
    if now.hour in [0, 6, 12, 18]:
        try:
            from daily_report import generate_report
            generate_report()
        except Exception:
            pass

    print(f"[{now.strftime('%H:%M')}] Monitor complete. {len(alerts)} alerts. {summary}")


if __name__ == "__main__":
    run_monitor()
