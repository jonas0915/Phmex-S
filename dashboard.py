#!/usr/bin/env python3
"""
Phmex-S Live Dashboard — read-only terminal monitor.
Reads bot.log and trading_state.json only. Zero API calls.
"""
import json
import os
import re
import time
import subprocess
from datetime import datetime

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


def tail_log(n: int = 200) -> list[str]:
    try:
        result = subprocess.run(
            ["tail", "-n", str(n), LOG_FILE],
            capture_output=True, text=True, timeout=5
        )
        return [strip_ansi(line) for line in result.stdout.splitlines()]
    except Exception:
        return []


def parse_open_positions(lines: list[str]) -> list[dict]:
    """Find currently open positions from recent log entries."""
    positions = {}
    for line in lines:
        m = re.search(r'Position opened: (\w+) ([\w/:.]+) \| Entry: ([\d.]+)', line)
        if m:
            side, symbol, entry = m.group(1), m.group(2), float(m.group(3))
            positions[symbol] = {"side": side, "symbol": symbol, "entry": entry}

        m = re.search(r'Position closed: \w+ ([\w/:.]+)', line)
        if m:
            positions.pop(m.group(1), None)

        m = re.search(r'\[SYNC\] Loaded (\w+) ([\w/:.]+) \| Entry: ([\d.]+)', line)
        if m:
            side, symbol, entry = m.group(1), m.group(2), float(m.group(3))
            positions[symbol] = {"side": side, "symbol": symbol, "entry": entry}

    return list(positions.values())


def parse_latest_cycle(lines: list[str]) -> str:
    for line in reversed(lines):
        m = re.search(r'Cycle #(\d+) \| Positions: (\d+)', line)
        if m:
            return f"Cycle #{m.group(1)} | Positions: {m.group(2)}"
    return "Unknown"


def parse_regime_status(lines: list[str]) -> str:
    for line in reversed(lines):
        if "[REGIME]" in line:
            m = re.search(r'\[REGIME\] (.+)', line)
            if m:
                return m.group(1)
        if "[DRAWDOWN]" in line:
            m = re.search(r'\[DRAWDOWN\] (.+)', line)
            if m:
                return m.group(1)
    return "Normal"


def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "total_pnl": 0, "avg_win": 0, "avg_loss": 0, "profit_factor": 0}

    wins = [t for t in trades if t.get("pnl_usdt", 0) > 0]
    losses = [t for t in trades if t.get("pnl_usdt", 0) <= 0]
    total_pnl = sum(t.get("pnl_usdt", 0) for t in trades)
    gross_profit = sum(t["pnl_usdt"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl_usdt"] for t in losses)) if losses else 0

    return {
        "total": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "total_pnl": total_pnl,
        "avg_win": gross_profit / len(wins) if wins else 0,
        "avg_loss": gross_loss / len(losses) if losses else 0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float('inf'),
    }


def get_recent_activity(lines: list[str], n: int = 8) -> list[str]:
    activity = []
    for line in reversed(lines):
        if any(kw in line for kw in ["ENTRY:", "Position closed:", "EARLY EXIT", "TIME EXIT",
                                       "HARD_TIME_EXIT", "REGIME", "DRAWDOWN", "SCANNER"]):
            activity.append(line.strip())
            if len(activity) >= n:
                break
    return list(reversed(activity))


def render(state: dict, lines: list[str]):
    os.system("clear")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trades = state.get("closed_trades", [])
    stats = compute_stats(trades)
    positions = parse_open_positions(lines)
    cycle = parse_latest_cycle(lines)
    regime = parse_regime_status(lines)

    print("=" * 70)
    print(f"  PHMEX-S LIVE DASHBOARD | {now}")
    print("=" * 70)

    # Stats
    print(f"\n  Cycle: {cycle}")
    print(f"  Peak Balance: ${state.get('peak_balance', 0):.2f}")
    print(f"  Status: {regime}")

    print(f"\n  {'─' * 50}")
    print(f"  PERFORMANCE (all time)")
    print(f"  {'─' * 50}")
    print(f"  Trades: {stats['total']} | Wins: {stats['wins']} | Losses: {stats['losses']}")
    print(f"  Win Rate: {stats['win_rate']:.1f}%")
    print(f"  Total PnL: ${stats['total_pnl']:+.2f}")
    print(f"  Avg Win: ${stats['avg_win']:.2f} | Avg Loss: ${stats['avg_loss']:.2f}")
    print(f"  Profit Factor: {stats['profit_factor']:.2f}")

    # Open positions
    print(f"\n  {'─' * 50}")
    print(f"  OPEN POSITIONS ({len(positions)})")
    print(f"  {'─' * 50}")
    if positions:
        for p in positions:
            print(f"  {p['side']:<6} {p['symbol']:<25} Entry: {p['entry']:.4f}")
    else:
        print("  No open positions")

    # Last 5 closed trades
    print(f"\n  {'─' * 50}")
    print(f"  RECENT TRADES (last 5)")
    print(f"  {'─' * 50}")
    recent = trades[-5:] if trades else []
    for t in reversed(recent):
        pnl = t.get("pnl_usdt", 0)
        pnl_pct = t.get("pnl_pct", 0)
        sign = "+" if pnl >= 0 else ""
        marker = "W" if pnl > 0 else "L"
        print(f"  [{marker}] {t.get('side', '?').upper():<6} {t.get('symbol', '?'):<25} {sign}${pnl:.2f} ({sign}{pnl_pct:.1f}%) | {t.get('reason', '?')}")

    # Activity feed
    print(f"\n  {'─' * 50}")
    print(f"  ACTIVITY FEED")
    print(f"  {'─' * 50}")
    activity = get_recent_activity(lines)
    for line in activity:
        # Trim timestamp for display
        if len(line) > 80:
            print(f"  {line[:78]}...")
        else:
            print(f"  {line}")

    print(f"\n  {'─' * 50}")
    print(f"  Refresh: 15s | Press Ctrl+C to exit")
    print("=" * 70)


def main():
    print("Starting Phmex-S Dashboard (read-only, zero API calls)...")
    try:
        while True:
            state = read_state()
            lines = tail_log(500)
            render(state, lines)
            time.sleep(15)
    except KeyboardInterrupt:
        print("\nDashboard stopped.")


if __name__ == "__main__":
    main()
