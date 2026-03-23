#!/usr/bin/env python3
"""
Monthly Recalibration Report for Phmex-S.
Generates per-slot performance analysis, kill switch evaluation,
and edge decay detection.

Usage:
    python recalibration.py                    # Full report
    python recalibration.py --slot 5m_scalp    # Specific slot
    python recalibration.py --days 7           # Last 7 days only
"""
import json
import os
import sys
import argparse
import time
from collections import defaultdict
from datetime import datetime, timedelta

def load_trades(state_file="trading_state.json", days=None):
    """Load closed trades, optionally filtered by recency."""
    path = os.path.join(os.path.dirname(__file__), state_file)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    trades = data.get("closed_trades", [])
    if days and trades:
        cutoff = time.time() - (days * 86400)
        trades = [t for t in trades if t.get("closed_at", 0) >= cutoff]
    return trades


def compute_metrics(trades):
    """Compute comprehensive trading metrics."""
    if not trades:
        return {"trades": 0, "wr": 0, "pnl": 0, "kelly": 0, "sharpe": 0,
                "avg_win": 0, "avg_loss": 0, "max_dd": 0, "profit_factor": 0}

    wins = [t for t in trades if t.get("pnl_usdt", 0) > 0]
    losses = [t for t in trades if t.get("pnl_usdt", 0) <= 0]
    pnl = sum(t.get("pnl_usdt", 0) for t in trades)
    wr = len(wins) / len(trades) * 100

    avg_win = sum(t["pnl_usdt"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["pnl_usdt"] for t in losses) / len(losses)) if losses else 0

    # Kelly
    kelly = 0
    if avg_win > 0 and wins and losses:
        kelly = (wr/100 * avg_win - (1-wr/100) * avg_loss) / avg_win

    # Sharpe (simplified: mean/std of per-trade returns)
    returns = [t.get("pnl_pct", 0) for t in trades]
    mean_r = sum(returns) / len(returns)
    std_r = (sum((r - mean_r)**2 for r in returns) / len(returns)) ** 0.5
    sharpe = mean_r / std_r if std_r > 0 else 0

    # Profit factor
    gross_profit = sum(t["pnl_usdt"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl_usdt"] for t in losses)) if losses else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Max drawdown
    cum = 0
    peak = 0
    max_dd = 0
    for t in trades:
        cum += t.get("pnl_usdt", 0)
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)

    # Exit breakdown
    exits = defaultdict(lambda: {"count": 0, "pnl": 0, "wr": 0, "wins": 0})
    for t in trades:
        reason = t.get("reason", "unknown")
        exits[reason]["count"] += 1
        exits[reason]["pnl"] += t.get("pnl_usdt", 0)
        if t.get("pnl_usdt", 0) > 0:
            exits[reason]["wins"] += 1
    for r in exits:
        exits[r]["wr"] = round(exits[r]["wins"] / exits[r]["count"] * 100, 1) if exits[r]["count"] > 0 else 0

    # Strategy breakdown
    strategies = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
    for t in trades:
        strat = t.get("strategy", "unknown")
        strategies[strat]["count"] += 1
        strategies[strat]["pnl"] += t.get("pnl_usdt", 0)
        if t.get("pnl_usdt", 0) > 0:
            strategies[strat]["wins"] += 1

    # Symbol breakdown
    symbols = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})
    for t in trades:
        sym = t.get("symbol", "unknown")
        symbols[sym]["count"] += 1
        symbols[sym]["pnl"] += t.get("pnl_usdt", 0)
        if t.get("pnl_usdt", 0) > 0:
            symbols[sym]["wins"] += 1

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "wr": round(wr, 1),
        "pnl": round(pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "kelly": round(kelly, 3),
        "sharpe": round(sharpe, 3),
        "profit_factor": round(pf, 2),
        "max_dd": round(max_dd, 2),
        "exits": dict(exits),
        "strategies": dict(strategies),
        "symbols": dict(symbols),
    }


def kill_switch_check(metrics):
    """Evaluate kill switch conditions."""
    issues = []

    if metrics["trades"] >= 50 and metrics["kelly"] < 0:
        issues.append(f"KILL: Negative Kelly ({metrics['kelly']:.3f}) after {metrics['trades']} trades")

    if metrics["trades"] >= 25 and metrics["wr"] < 30:
        issues.append(f"KILL: Win rate {metrics['wr']}% < 30% threshold after {metrics['trades']} trades")

    if metrics["max_dd"] > 0:
        # Check if DD exceeds 15% of total PnL magnitude
        if metrics["pnl"] < 0 and abs(metrics["pnl"]) > 10:
            issues.append(f"WARNING: Cumulative loss ${metrics['pnl']:.2f} with max DD ${metrics['max_dd']:.2f}")

    return issues


def edge_decay_check(trades, window_days=7):
    """Compare recent performance vs overall to detect edge decay."""
    if len(trades) < 20:
        return []

    cutoff = time.time() - (window_days * 86400)
    recent = [t for t in trades if t.get("closed_at", 0) >= cutoff]
    older = [t for t in trades if t.get("closed_at", 0) < cutoff]

    if len(recent) < 5 or len(older) < 10:
        return []

    recent_wr = sum(1 for t in recent if t.get("pnl_usdt", 0) > 0) / len(recent) * 100
    older_wr = sum(1 for t in older if t.get("pnl_usdt", 0) > 0) / len(older) * 100

    alerts = []
    if recent_wr < older_wr * 0.7:  # 30% drop
        alerts.append(f"DECAY: Recent WR {recent_wr:.0f}% vs historical {older_wr:.0f}% (>{30}% drop)")

    return alerts


def print_report(metrics, slot_name="ALL", days=None):
    """Print formatted report."""
    period = f"Last {days} days" if days else "All time"

    print(f"\n{'='*60}")
    print(f"  RECALIBRATION REPORT — {slot_name} ({period})")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    print(f"\n  Trades: {metrics['trades']} | Wins: {metrics['wins']} | Losses: {metrics['losses']}")
    print(f"  Win Rate: {metrics['wr']}%")
    print(f"  PnL: ${metrics['pnl']:+.2f}")
    print(f"  Avg Win: ${metrics['avg_win']:.2f} | Avg Loss: ${metrics['avg_loss']:.2f}")
    print(f"  Kelly: {metrics['kelly']:+.3f} {'POSITIVE' if metrics['kelly'] > 0 else 'NEGATIVE'}")
    print(f"  Sharpe: {metrics['sharpe']:.3f}")
    print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"  Max Drawdown: ${metrics['max_dd']:.2f}")

    # Exit breakdown
    if metrics.get("exits"):
        print(f"\n  Exit Breakdown:")
        for reason, data in sorted(metrics["exits"].items(), key=lambda x: x[1]["pnl"]):
            print(f"    {reason:20s}: {data['count']:3d} trades | ${data['pnl']:+7.2f} | WR {data['wr']:.0f}%")

    # Strategy breakdown
    if metrics.get("strategies"):
        print(f"\n  Strategy Breakdown:")
        for strat, data in sorted(metrics["strategies"].items(), key=lambda x: x[1]["pnl"]):
            wr = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
            print(f"    {strat:25s}: {data['count']:3d} trades | ${data['pnl']:+7.2f} | WR {wr:.0f}%")

    # Symbol breakdown
    if metrics.get("symbols"):
        print(f"\n  Symbol Breakdown:")
        for sym, data in sorted(metrics["symbols"].items(), key=lambda x: x[1]["pnl"]):
            wr = data['wins'] / data['count'] * 100 if data['count'] > 0 else 0
            print(f"    {sym:25s}: {data['count']:3d} trades | ${data['pnl']:+7.2f} | WR {wr:.0f}%")


def main():
    parser = argparse.ArgumentParser(description="Phmex-S Recalibration Report")
    parser.add_argument("--slot", default=None, help="Specific slot state file (e.g., trading_state_5m_scalp.json)")
    parser.add_argument("--days", type=int, default=None, help="Filter to last N days")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Find all state files
    base_dir = os.path.dirname(__file__) or "."
    if args.slot:
        state_files = [(args.slot, args.slot)]
    else:
        state_files = []
        for f in os.listdir(base_dir):
            if f.startswith("trading_state") and f.endswith(".json") and "v8" not in f and "pre_" not in f:
                slot_name = f.replace("trading_state_", "").replace("trading_state", "main").replace(".json", "")
                state_files.append((f, slot_name))

    if not state_files:
        print("No state files found.")
        return

    all_trades = []
    for state_file, slot_name in state_files:
        trades = load_trades(state_file, args.days)
        if not trades:
            print(f"\n  [{slot_name}] No trades found")
            continue

        metrics = compute_metrics(trades)

        if args.json:
            print(json.dumps({"slot": slot_name, **metrics}, indent=2))
        else:
            print_report(metrics, slot_name, args.days)

            # Kill switch
            issues = kill_switch_check(metrics)
            if issues:
                print(f"\n  ALERTS:")
                for issue in issues:
                    print(f"    {issue}")

            # Edge decay
            decay = edge_decay_check(trades)
            if decay:
                for alert in decay:
                    print(f"    {alert}")

        all_trades.extend(trades)

    # Combined report if multiple slots
    if len(state_files) > 1 and all_trades and not args.json:
        combined = compute_metrics(all_trades)
        print_report(combined, "COMBINED", args.days)
        issues = kill_switch_check(combined)
        if issues:
            print(f"\n  COMBINED ALERTS:")
            for issue in issues:
                print(f"    {issue}")


if __name__ == "__main__":
    main()
