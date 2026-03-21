#!/usr/bin/env python3
"""
Phmex-S Daily Performance Review — parses logs and trading_state.json.
Read-only, zero API calls, no bot module imports.
"""
import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "bot.log")
STATE_FILE = os.path.join(PROJECT_DIR, "trading_state.json")
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub('', text)


def read_state() -> dict:
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"peak_balance": 0, "closed_trades": []}


def read_log() -> list[str]:
    try:
        with open(LOG_FILE, "r") as f:
            return [strip_ansi(line.strip()) for line in f.readlines()]
    except FileNotFoundError:
        return []


def parse_trades_from_log(lines: list[str], date_str: str = None) -> list[dict]:
    """Parse closed trade entries from log lines, optionally filtered by date."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    trades = []
    entry_times = {}  # symbol -> entry timestamp

    for line in lines:
        if date_str and not line.startswith(date_str):
            # Also check previous day for entries that opened yesterday and closed today
            pass

        # Track entries
        m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Position opened: (\w+) ([\w/:.]+) \| Entry: ([\d.]+)', line)
        if m:
            ts, side, symbol, entry = m.group(1), m.group(2), m.group(3), m.group(4)
            entry_times[symbol] = ts

        # Track closes
        m = re.search(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Position closed: (\w+) ([\w/:.]+) \| '
            r'Exit: ([\d.]+) \| PnL: ([+-]?[\d.]+) USDT \(([+-]?[\d.]+)%\) \| Reason: (\w+)',
            line
        )
        if m:
            ts = m.group(1)
            if date_str and not ts.startswith(date_str):
                continue
            side = m.group(2)
            symbol = m.group(3)
            exit_price = float(m.group(4))
            pnl = float(m.group(5))
            pnl_pct = float(m.group(6))
            reason = m.group(7)

            entry_ts = entry_times.get(symbol, "?")
            hold_time = ""
            if entry_ts != "?":
                try:
                    t1 = datetime.strptime(entry_ts, "%Y-%m-%d %H:%M:%S")
                    t2 = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    delta = t2 - t1
                    hours = delta.seconds // 3600
                    mins = (delta.seconds % 3600) // 60
                    hold_time = f"{hours}h {mins}m"
                except ValueError:
                    hold_time = "?"

            trades.append({
                "symbol": symbol,
                "side": side,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "reason": reason,
                "entry_time": entry_ts,
                "exit_time": ts,
                "hold_time": hold_time,
            })

    return trades


def generate_review(trades: list[dict], date_str: str) -> str:
    """Generate a text performance review."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"  PHMEX-S DAILY PERFORMANCE REVIEW — {date_str}")
    lines.append("=" * 70)

    if not trades:
        lines.append("\n  No trades found for this date.\n")
        return "\n".join(lines)

    # Summary
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0

    lines.append(f"\n  SUMMARY")
    lines.append(f"  {'─' * 50}")
    lines.append(f"  Total Trades:    {len(trades)}")
    lines.append(f"  Wins / Losses:   {len(wins)} / {len(losses)}")
    lines.append(f"  Win Rate:        {win_rate:.1f}%")
    lines.append(f"  Total PnL:       ${total_pnl:+.2f}")
    lines.append(f"  Gross Profit:    ${gross_profit:.2f}")
    lines.append(f"  Gross Loss:      ${gross_loss:.2f}")
    lines.append(f"  Profit Factor:   {pf:.2f}")
    lines.append(f"  Avg Win:         ${avg_win:.2f}")
    lines.append(f"  Avg Loss:        ${avg_loss:.2f}")

    # Best / worst
    if trades:
        best = max(trades, key=lambda t: t["pnl"])
        worst = min(trades, key=lambda t: t["pnl"])
        lines.append(f"\n  Best Trade:      {best['side']} {best['symbol']} | ${best['pnl']:+.2f} ({best['pnl_pct']:+.1f}%)")
        lines.append(f"  Worst Trade:     {worst['side']} {worst['symbol']} | ${worst['pnl']:+.2f} ({worst['pnl_pct']:+.1f}%)")

    # By pair
    lines.append(f"\n  PNL BY PAIR")
    lines.append(f"  {'─' * 50}")
    pair_pnl = defaultdict(lambda: {"pnl": 0, "count": 0, "wins": 0})
    for t in trades:
        sym = t["symbol"].replace("/USDT:USDT", "")
        pair_pnl[sym]["pnl"] += t["pnl"]
        pair_pnl[sym]["count"] += 1
        if t["pnl"] > 0:
            pair_pnl[sym]["wins"] += 1

    for sym, data in sorted(pair_pnl.items(), key=lambda x: x[1]["pnl"], reverse=True):
        wr = data["wins"] / data["count"] * 100 if data["count"] > 0 else 0
        lines.append(f"  {sym:<10} {data['count']}t  ${data['pnl']:+.2f}  WR: {wr:.0f}%")

    # By exit reason
    lines.append(f"\n  PNL BY EXIT REASON")
    lines.append(f"  {'─' * 50}")
    reason_pnl = defaultdict(lambda: {"pnl": 0, "count": 0, "wins": 0})
    for t in trades:
        reason_pnl[t["reason"]]["pnl"] += t["pnl"]
        reason_pnl[t["reason"]]["count"] += 1
        if t["pnl"] > 0:
            reason_pnl[t["reason"]]["wins"] += 1

    for reason, data in sorted(reason_pnl.items(), key=lambda x: x[1]["pnl"], reverse=True):
        wr = data["wins"] / data["count"] * 100 if data["count"] > 0 else 0
        lines.append(f"  {reason:<20} {data['count']}t  ${data['pnl']:+.2f}  WR: {wr:.0f}%")

    # Trade log
    lines.append(f"\n  TRADE LOG")
    lines.append(f"  {'─' * 50}")
    lines.append(f"  {'#':<3} {'Side':<6} {'Pair':<12} {'PnL':>8} {'ROI':>8} {'Hold':>8} {'Exit Reason'}")
    lines.append(f"  {'─' * 70}")
    for i, t in enumerate(trades, 1):
        sign = "+" if t["pnl"] >= 0 else ""
        lines.append(
            f"  {i:<3} {t['side']:<6} {t['symbol'].replace('/USDT:USDT', ''):<12} "
            f"{sign}${t['pnl']:<7.2f} {sign}{t['pnl_pct']:<7.1f}% {t['hold_time']:>8} {t['reason']}"
        )

    # Drawdown
    lines.append(f"\n  CUMULATIVE PNL WALK")
    lines.append(f"  {'─' * 50}")
    cum = 0
    peak = 0
    max_dd = 0
    for t in trades:
        cum += t["pnl"]
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd

    lines.append(f"  Final PnL:       ${cum:+.2f}")
    lines.append(f"  Peak PnL:        ${peak:.2f}")
    lines.append(f"  Max Drawdown:    ${max_dd:.2f}")

    # Win/loss streaks
    max_win_streak = 0
    max_loss_streak = 0
    current_streak = 0
    for t in trades:
        if t["pnl"] > 0:
            current_streak = current_streak + 1 if current_streak > 0 else 1
            max_win_streak = max(max_win_streak, current_streak)
        else:
            current_streak = current_streak - 1 if current_streak < 0 else -1
            max_loss_streak = max(max_loss_streak, abs(current_streak))

    lines.append(f"  Max Win Streak:  {max_win_streak}")
    lines.append(f"  Max Loss Streak: {max_loss_streak}")

    lines.append(f"\n{'=' * 70}")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)

    return "\n".join(lines)


def main():
    import sys
    # Allow passing a date as argument: python daily_review.py 2026-03-12
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"Parsing trades for {date_str}...\n")

    log_lines = read_log()
    trades = parse_trades_from_log(log_lines, date_str)

    review = generate_review(trades, date_str)
    print(review)

    # Save to file
    output_dir = os.path.join(PROJECT_DIR, "reviews")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"review_{date_str}.txt")
    with open(output_file, "w") as f:
        f.write(review)
    print(f"\nSaved to: {output_file}")


if __name__ == "__main__":
    main()
