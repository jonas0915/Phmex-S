#!/usr/bin/env python3
"""Daily bot performance report — runs via cron, saves to reports/"""
import glob
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
DEFAULT_LIVE_LOSS_CAP = -5.0  # per-slot cap comes from the mode sidecar; this default
                              # matches strategy_slot.py:12 (the old -10 hardcode was
                              # ST2.0-specific and overstated other slots' headroom 2x)

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


def live_slot_summaries(date_str):
    """Stats for strategy slots promoted to LIVE via trading_state_<slot>_mode.json
    sidecars (paper_mode false). Returns [] when nothing is promoted, so the
    report/Telegram sections simply don't render."""
    summaries = []
    for mode_path in sorted(glob.glob(os.path.join(BOT_DIR, "trading_state_*_mode.json"))):
        try:
            with open(mode_path) as f:
                mode = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        if mode.get("paper_mode", True):
            continue
        slot_id = os.path.basename(mode_path).replace("trading_state_", "").replace("_mode.json", "")
        try:
            with open(os.path.join(BOT_DIR, f"trading_state_{slot_id}.json")) as f:
                slot_state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, IOError):
            slot_state = {}
        live_trades = [t for t in slot_state.get("closed_trades", []) or [] if t.get("mode") == "live"]
        live_today = []
        for t in live_trades:
            closed_at = t.get("closed_at", 0)
            if closed_at and datetime.fromtimestamp(closed_at, tz=CA_TZ).strftime("%Y-%m-%d") == date_str:
                live_today.append(t)
        wins = sum(1 for t in live_today if _net(t) > 0)
        # Lifetime blocked-gate counters from the slot's _blocked.json sidecar
        # (generic: any bump_blocked tag surfaces, e.g. mr_rsi_floor).
        try:
            with open(os.path.join(BOT_DIR, f"trading_state_{slot_id}_blocked.json")) as bf:
                blocked = json.load(bf) or {}
        except (FileNotFoundError, json.JSONDecodeError, IOError):
            blocked = {}
        loss_cap = float(mode.get("loss_cap_usdt") or DEFAULT_LIVE_LOSS_CAP)
        summaries.append({
            "slot_id": slot_id,
            "loss_cap": loss_cap,
            "trades": len(live_today),
            "wins": wins,
            "losses": len(live_today) - wins,
            "wr": (wins / len(live_today) * 100) if live_today else 0,
            "pnl_today": sum(_net(t) for t in live_today),
            "live_pnl": sum(_net(t) for t in live_trades),
            "blocked": blocked,
        })
    return summaries


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
                hour = datetime.fromtimestamp(opened, tz=CA_TZ).strftime("%H")
                hours[hour]["count"] += 1
                hours[hour]["pnl"] += _net(t)
                if _net(t) > 0:
                    hours[hour]["wins"] += 1

        report += "\n## Today by Hour (PT)\n"
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
                h = datetime.fromtimestamp(opened, tz=CA_TZ).hour
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

    # Dead paper slots (5m_liq_cascade, 5m_narrow — KILLED) removed from the
    # report 2026-07-03: dead sims were headlining while the LIVE experiment
    # got 5 lines. Their state files remain on disk.

    # Live slot sections (promoted via mode sidecar) — absent when nothing is promoted
    for ls in live_slot_summaries(date_str):
        report += f"\n## Live Slot: {ls['slot_id']}\n"
        report += f"- Trades today: {ls['trades']} ({ls['wins']}W / {ls['losses']}L)\n"
        report += f"- Win Rate: {ls['wr']:.1f}%\n"
        report += f"- Net PnL today: ${ls['pnl_today']:.2f}\n"
        report += f"- Live PnL since promotion: ${ls['live_pnl']:.2f}\n"
        report += f"- Cap headroom: ${ls['live_pnl'] - ls['loss_cap']:.2f} until -${abs(ls['loss_cap']):.2f} auto-demote\n"
        if ls.get("blocked"):
            report += ("- Counters (lifetime): "
                       + " ".join(f"{k}={v}" for k, v in sorted(ls["blocked"].items()))
                       + "\n")

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
                hour = int(datetime.fromtimestamp(opened, tz=CA_TZ).strftime("%H"))
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

    # Promoted live slots (mode sidecar paper_mode false) — absent when none
    for ls in live_slot_summaries(date_str):
        t_sign = "+" if ls["pnl_today"] >= 0 else ""
        p_sign = "+" if ls["live_pnl"] >= 0 else ""
        msg += (
            f"\n🔴 <b>LIVE Slot: {ls['slot_id']}</b>\n"
            f"{ls['trades']} trades | {ls['wr']:.0f}% WR | {t_sign}${ls['pnl_today']:.2f}\n"
            f"Since promotion: {p_sign}${ls['live_pnl']:.2f} | "
            f"Headroom: ${ls['live_pnl'] - ls['loss_cap']:.2f} until -${abs(ls['loss_cap']):.2f} demote\n"
        )
        if ls.get("blocked"):
            msg += ("Counters: "
                    + " ".join(f"{k}={v}" for k, v in sorted(ls["blocked"].items()))
                    + "\n")

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
