#!/usr/bin/env python3
"""Daily bot performance report — runs via cron, saves to reports/"""
import json
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict
from zoneinfo import ZoneInfo

CA_TZ = ZoneInfo("America/Los_Angeles")

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BOT_DIR, "trading_state.json")
LOG_FILE = os.path.join(BOT_DIR, "logs", "bot.log")
REPORT_DIR = os.path.join(BOT_DIR, "reports")

os.makedirs(REPORT_DIR, exist_ok=True)


def load_state():
    with open(STATE_FILE) as f:
        return json.load(f)


def parse_log_entries(date_str):
    """Parse ENTRY and Position closed lines for a specific date."""
    entries = []
    if not os.path.exists(LOG_FILE):
        return entries
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        for line in f:
            clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
            if date_str not in clean:
                continue
            if "[ENTRY]" in clean or "Position closed" in clean or "Position opened" in clean:
                entries.append(clean)
    return entries


def _net(t):
    """Return net_pnl if present, else fall back to gross pnl_usdt."""
    n = t.get("net_pnl")
    return n if n is not None else t.get("pnl_usdt", 0)


def _fee(t):
    """Return real fees_usdt if present, else 0 (caller can decide to estimate)."""
    f = t.get("fees_usdt")
    return f if f is not None else 0


def analyze_trades(state, date_str):
    """Analyze trades for a specific date."""
    trades = state.get("closed_trades", [])
    today_trades = []
    for t in trades:
        # Trade records store closed_at as Unix timestamp (time.time())
        closed_at = t.get("closed_at", 0)
        if closed_at:
            trade_date = datetime.fromtimestamp(closed_at, tz=CA_TZ).strftime("%Y-%m-%d")
            if trade_date == date_str:
                today_trades.append(t)
                continue
        # Fallback: try legacy string fields
        ts = t.get("exit_time", "") or t.get("close_time", "")
        if date_str in str(ts):
            today_trades.append(t)
    return today_trades


def generate_report():
    today = datetime.now(CA_TZ)
    date_str = today.strftime("%Y-%m-%d")
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    # Reconcile fees against Phemex truth BEFORE reading state — prevents
    # reports from publishing stale/zero fees (known I7 regression).
    try:
        import subprocess
        subprocess.run(
            ["python3", os.path.join(BOT_DIR, "scripts", "reconcile_phemex.py"), "--apply"],
            cwd=BOT_DIR,
            timeout=120,
            capture_output=True,
        )
    except Exception as e:
        print(f"[WARN] pre-report reconcile failed: {e}")

    state = load_state()
    peak = state.get("peak_balance", 0)

    # Parse balance from bot log STATS line (trading_state.json stores None)
    balance = 0
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
            for line in f:
                clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
                m = re.search(r'Balance: ([\d.]+) USDT', clean)
                if m:
                    balance = float(m.group(1))
    if balance == 0:
        balance = state.get("balance") or 0

    closed = state.get("closed_trades", [])

    # Today's trades
    today_trades = analyze_trades(state, date_str)
    today_wins = sum(1 for t in today_trades if _net(t) > 0)
    today_losses = len(today_trades) - today_wins
    today_pnl = sum(_net(t) for t in today_trades)
    today_gross = sum(t.get("pnl_usdt", 0) for t in today_trades)
    today_fees = sum(_fee(t) for t in today_trades)
    today_wr = (today_wins / len(today_trades) * 100) if today_trades else 0

    # By exit reason
    exit_reasons = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
    for t in today_trades:
        reason = t.get("exit_reason") or t.get("reason") or "unknown"
        exit_reasons[reason]["count"] += 1
        exit_reasons[reason]["pnl"] += _net(t)
        if _net(t) > 0:
            exit_reasons[reason]["wins"] += 1

    # By symbol
    symbols = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
    for t in today_trades:
        sym = t.get("symbol", "unknown")
        symbols[sym]["count"] += 1
        symbols[sym]["pnl"] += _net(t)
        if _net(t) > 0:
            symbols[sym]["wins"] += 1

    # By strategy
    strategies = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
    for t in today_trades:
        strat = t.get("strategy", "unknown")
        strategies[strat]["count"] += 1
        strategies[strat]["pnl"] += _net(t)
        if _net(t) > 0:
            strategies[strat]["wins"] += 1

    # Build report
    report = f"""# Phmex-S Daily Report — {date_str}
Generated: {today.strftime("%Y-%m-%d %H:%M:%S")}

## Account Status
- Balance: ${balance:.2f} USDT
- Peak: ${peak:.2f} USDT
- Drawdown: {((peak - balance) / peak * 100) if peak > 0 else 0:.1f}%

## Today ({date_str})
- Trades: {len(today_trades)} ({today_wins}W / {today_losses}L)
- Win Rate: {today_wr:.1f}% (net)
- Gross PnL: ${today_gross:.2f}
- Fees: ${today_fees:.2f}
- Net PnL: ${today_pnl:.2f}
"""

    if exit_reasons:
        report += "\n## Today by Exit Reason\n"
        report += "| Reason | Count | Wins | PnL |\n|--------|-------|------|-----|\n"
        for reason, data in sorted(exit_reasons.items(), key=lambda x: x[1]["pnl"], reverse=True):
            report += f"| {reason} | {data['count']} | {data['wins']} | ${data['pnl']:.2f} |\n"

    if symbols:
        report += "\n## Today by Symbol\n"
        report += "| Symbol | Count | Wins | PnL |\n|--------|-------|------|-----|\n"
        for sym, data in sorted(symbols.items(), key=lambda x: x[1]["pnl"], reverse=True):
            report += f"| {sym} | {data['count']} | {data['wins']} | ${data['pnl']:.2f} |\n"

    if strategies:
        report += "\n## Today by Strategy\n"
        report += "| Strategy | Count | Wins | PnL |\n|----------|-------|------|-----|\n"
        for strat, data in sorted(strategies.items(), key=lambda x: x[1]["pnl"], reverse=True):
            report += f"| {strat} | {data['count']} | {data['wins']} | ${data['pnl']:.2f} |\n"

    if today_trades:
        # Time-of-day breakdown
        hours = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0})
        for t in today_trades:
            opened = t.get("opened_at", t.get("closed_at", 0))
            if opened:
                hour = datetime.fromtimestamp(opened).strftime("%H")
                hours[hour]["count"] += 1
                hours[hour]["pnl"] += _net(t)
                if _net(t) > 0:
                    hours[hour]["wins"] += 1

        report += "\n## Today by Hour (UTC)\n"
        report += "| Hour | Trades | Wins | WR | PnL |\n|------|--------|------|----|-----|\n"
        for hour in sorted(hours.keys()):
            h = hours[hour]
            h_wr = (h["wins"] / h["count"] * 100) if h["count"] > 0 else 0
            report += f"| {hour}:00 | {h['count']} | {h['wins']} | {h_wr:.0f}% | ${h['pnl']:.2f} |\n"

        # Session summary
        sessions = {"🌃 Early AM (12:01AM-5:59AM)": {"count": 0, "wins": 0, "pnl": 0},
                    "☀️ Morning (6AM-12PM)": {"count": 0, "wins": 0, "pnl": 0},
                    "🌤 Afternoon (12:01PM-8PM)": {"count": 0, "wins": 0, "pnl": 0},
                    "🌙 Night (8:01PM-12AM)": {"count": 0, "wins": 0, "pnl": 0}}
        for t in today_trades:
            opened = t.get("opened_at", t.get("closed_at", 0))
            if opened:
                h = datetime.fromtimestamp(opened).hour
                if 0 <= h < 6:
                    key = "🌃 Early AM (12:01AM-5:59AM)"
                elif 6 <= h < 12:
                    key = "☀️ Morning (6AM-12PM)"
                elif 12 <= h < 20:
                    key = "🌤 Afternoon (12:01PM-8PM)"
                else:
                    key = "🌙 Night (8:01PM-12AM)"
                sessions[key]["count"] += 1
                sessions[key]["pnl"] += _net(t)
                if _net(t) > 0:
                    sessions[key]["wins"] += 1

        report += "\n## Today by Session\n"
        report += "| Session | Trades | Wins | WR | PnL |\n|---------|--------|------|----|-----|\n"
        for s, d in sessions.items():
            s_wr = (d["wins"] / d["count"] * 100) if d["count"] > 0 else 0
            report += f"| {s} | {d['count']} | {d['wins']} | {s_wr:.0f}% | ${d['pnl']:.2f} |\n"

    report += f"""
## Alerts
"""
    alerts = []
    if today_wr < 30 and len(today_trades) >= 5:
        alerts.append(f"LOW WIN RATE: {today_wr:.0f}% today on {len(today_trades)} trades")
    if today_pnl < -3:
        alerts.append(f"SIGNIFICANT DAILY LOSS: ${today_pnl:.2f}")
    if peak > 0 and balance > 0 and (peak - balance) / peak * 100 > 10:
        alerts.append(f"HIGH DRAWDOWN: {((peak - balance) / peak * 100):.1f}%")
    if len(today_trades) == 0:
        alerts.append("NO TRADES TODAY — bot may be frozen or market very quiet")
    if not alerts:
        alerts.append("None — all metrics within normal range")
    for a in alerts:
        report += f"- {a}\n"

    # Paper slot comparison
    paper_state_file = os.path.join(BOT_DIR, "trading_state_5m_liq_cascade.json")
    if os.path.exists(paper_state_file):
        with open(paper_state_file) as f:
            paper_state = json.load(f)
        paper_closed = paper_state.get("closed_trades", [])
        paper_today = []
        for t in paper_closed:
            closed_at = t.get("closed_at", 0)
            if closed_at:
                trade_date = datetime.fromtimestamp(closed_at, tz=CA_TZ).strftime("%Y-%m-%d")
                if trade_date == date_str:
                    paper_today.append(t)
        paper_today_wins = sum(1 for t in paper_today if _net(t) > 0)
        paper_today_pnl = sum(_net(t) for t in paper_today)
        paper_today_wr = (paper_today_wins / len(paper_today) * 100) if paper_today else 0

        report += f"""
## Paper Slot: ADX+SMA+VWAP
| Metric | Live | Paper |
|--------|------|-------|
| Trades | {len(today_trades)} | {len(paper_today)} |
| Win Rate | {today_wr:.0f}% | {paper_today_wr:.0f}% |
| PnL | ${today_pnl:.2f} | ${paper_today_pnl:.2f} |
"""

    # Save
    report_path = os.path.join(REPORT_DIR, f"{date_str}.md")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved: {report_path}")

    # Send via Telegram
    send_telegram(report, date_str, balance, today_trades, today_pnl, today_wr)
    return report_path


def send_telegram(report, date_str, balance, today_trades, today_pnl, today_wr):
    """Send report summary via Telegram."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BOT_DIR, ".env"))

    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("Telegram not configured, skipping")
        return

    # Build concise Telegram message
    sign = "+" if today_pnl >= 0 else ""
    emoji = "📈" if today_pnl >= 0 else "📉"

    msg = (
        f"{emoji} <b>Phmex-S Daily Report — {date_str}</b>\n\n"
        f"💰 Balance: <b>${balance:.2f} USDT</b>\n\n"
        f"🟢 <b>Live Bot</b>\n"
        f"📊 Trades: {len(today_trades)} | WR: {today_wr:.0f}% (net)\n"
        f"💵 Net PnL: <b>{sign}${today_pnl:.2f}</b>\n"
        f"   Gross: ${sum(t.get('pnl_usdt', 0) for t in today_trades):.2f} | "
        f"Fees: ${sum(_fee(t) for t in today_trades):.2f}\n"
    )

    if today_trades:
        # Add by-symbol breakdown
        from collections import defaultdict
        syms = defaultdict(lambda: {"pnl": 0, "count": 0})
        for t in today_trades:
            s = t.get("symbol", "?").split("/")[0]
            syms[s]["pnl"] += _net(t)
            syms[s]["count"] += 1
        msg += "\n<b>By Symbol:</b>\n"
        for s, d in sorted(syms.items(), key=lambda x: x[1]["pnl"], reverse=True):
            sp = "+" if d["pnl"] >= 0 else ""
            msg += f"  {s}: {d['count']} trades, {sp}${d['pnl']:.2f}\n"

    if today_trades:
        # Time-of-day summary for Telegram
        from collections import defaultdict
        hours = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0})
        for t in today_trades:
            opened = t.get("opened_at", t.get("closed_at", 0))
            if opened:
                hour = int(datetime.fromtimestamp(opened).strftime("%H"))
                if 0 <= hour < 6:
                    period = "🌃 Early AM (12:01AM-5:59AM)"
                elif 6 <= hour < 12:
                    period = "☀️ Morning (6AM-12PM)"
                elif 12 <= hour < 20:
                    period = "🌤 Afternoon (12:01PM-8PM)"
                else:
                    period = "🌙 Night (8:01PM-12AM)"
                hours[period]["count"] += 1
                hours[period]["pnl"] += _net(t)
                if _net(t) > 0:
                    hours[period]["wins"] += 1
        if hours:
            msg += "\n<b>By Session:</b>\n"
            for period in ["🌃 Early AM (12:01AM-5:59AM)", "☀️ Morning (6AM-12PM)", "🌤 Afternoon (12:01PM-8PM)", "🌙 Night (8:01PM-12AM)"]:
                if period in hours:
                    h = hours[period]
                    h_wr = (h["wins"] / h["count"] * 100) if h["count"] > 0 else 0
                    h_sign = "+" if h["pnl"] >= 0 else ""
                    msg += f"  {period}: {h['count']} trades, {h_wr:.0f}% WR, {h_sign}${h['pnl']:.2f}\n"

    if len(today_trades) == 0:
        msg += "\n⚠️ No trades today — market quiet or filters blocking"

    # Add paper slot comparison if available
    paper_state_file = os.path.join(BOT_DIR, "trading_state_5m_liq_cascade.json")
    if os.path.exists(paper_state_file):
        with open(paper_state_file) as f:
            ps = json.load(f)
        pc = ps.get("closed_trades", [])
        pt = [t for t in pc if t.get("closed_at") and datetime.fromtimestamp(t["closed_at"]).strftime("%Y-%m-%d") == date_str]
        pt_wins = sum(1 for t in pt if _net(t) > 0)
        pt_pnl = sum(_net(t) for t in pt)
        pt_wr = (pt_wins / len(pt) * 100) if pt else 0
        pt_sign = "+" if pt_pnl >= 0 else ""
        msg += (
            f"\n🔵 <b>Paper Slot (ADX+SMA+VWAP)</b>\n"
            f"{len(pt)} trades | {pt_wr:.0f}% WR | {pt_sign}${pt_pnl:.2f}\n"
        )

    try:
        import requests
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        print("Telegram report sent")
    except Exception as e:
        print(f"Telegram send failed: {e}")


if __name__ == "__main__":
    generate_report()
