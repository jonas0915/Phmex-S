#!/usr/bin/env python3
"""
Phmex-S Performance Charts — generates PNG charts from trading_state.json.
Read-only, zero API calls, no bot module imports.
"""
import json
import os
from datetime import datetime
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PROJECT_DIR, "trading_state.json")
CHART_DIR = os.path.join(PROJECT_DIR, "charts")


def _net(t: dict) -> float:
    """Net PnL when present (post-fees), else fall back to gross pnl_usdt."""
    n = t.get("net_pnl")
    return n if n is not None else t.get("pnl_usdt", 0)


def read_state() -> dict:
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"peak_balance": 0, "closed_trades": []}


def ensure_chart_dir():
    os.makedirs(CHART_DIR, exist_ok=True)


def chart_cumulative_pnl(trades: list[dict], output: str):
    """Cumulative PnL over trade number (and time if timestamps available)."""
    if not trades:
        return

    pnls = [_net(t) for t in trades]
    cumulative = []
    running = 0
    for p in pnls:
        running += p
        cumulative.append(running)

    # Check if timestamps are available
    has_timestamps = trades[-1].get("closed_at", 0) > 0

    fig, ax = plt.subplots(figsize=(12, 5))

    if has_timestamps:
        times = []
        cum_with_time = []
        running = 0
        for t in trades:
            ts = t.get("closed_at", 0)
            if ts > 0:
                running += _net(t)
                times.append(datetime.fromtimestamp(ts))
                cum_with_time.append(running)
        if times:
            ax.plot(times, cum_with_time, 'b-o', markersize=4, linewidth=1.5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
            plt.xticks(rotation=45)
            ax.set_xlabel('Time')
    else:
        ax.plot(range(1, len(cumulative) + 1), cumulative, 'b-o', markersize=4, linewidth=1.5)
        ax.set_xlabel('Trade #')

    ax.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    if has_timestamps and times:
        x_axis = times
        fill_cum = cum_with_time
    else:
        x_axis = list(range(1, len(cumulative) + 1))
        fill_cum = cumulative
    ax.fill_between(
        x_axis, fill_cum, 0,
        where=[c >= 0 for c in fill_cum], color='green', alpha=0.15
    )
    ax.fill_between(
        x_axis, fill_cum, 0,
        where=[c < 0 for c in fill_cum], color='red', alpha=0.15
    )

    ax.set_ylabel('Cumulative PnL (USDT)')
    ax.set_title('Phmex-S — Cumulative PnL (net)')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()
    print(f"  Saved: {output}")


def chart_pnl_by_pair(trades: list[dict], output: str):
    """Bar chart of total PnL per trading pair."""
    if not trades:
        return

    pair_pnl = defaultdict(float)
    pair_count = defaultdict(int)
    for t in trades:
        sym = t.get("symbol", "?")
        pair_pnl[sym] += _net(t)
        pair_count[sym] += 1

    # Sort by PnL
    sorted_pairs = sorted(pair_pnl.items(), key=lambda x: x[1], reverse=True)
    symbols = [p[0].replace("/USDT:USDT", "") for p in sorted_pairs]
    pnls = [p[1] for p in sorted_pairs]
    counts = [pair_count[p[0]] for p in sorted_pairs]
    colors = ['green' if p >= 0 else 'red' for p in pnls]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(symbols, pnls, color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)

    # Add trade count labels
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f'{count}t', ha='center', va='bottom', fontsize=8, color='gray')

    ax.axhline(y=0, color='black', linewidth=0.8)
    ax.set_ylabel('Total PnL (USDT)')
    ax.set_title('Phmex-S — PnL by Pair')
    ax.grid(True, alpha=0.3, axis='y')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()
    print(f"  Saved: {output}")


def chart_pnl_by_exit_reason(trades: list[dict], output: str):
    """Bar chart of total PnL by exit reason."""
    if not trades:
        return

    reason_pnl = defaultdict(float)
    reason_count = defaultdict(int)
    for t in trades:
        reason = t.get("exit_reason") or t.get("reason") or "unknown"
        reason_pnl[reason] += _net(t)
        reason_count[reason] += 1

    reasons = list(reason_pnl.keys())
    pnls = [reason_pnl[r] for r in reasons]
    counts = [reason_count[r] for r in reasons]
    colors = ['green' if p >= 0 else 'red' for p in pnls]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(reasons, pnls, color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)

    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f'{count}t', ha='center', va='bottom', fontsize=9, color='gray')

    ax.axhline(y=0, color='black', linewidth=0.8)
    ax.set_ylabel('Total PnL (USDT)')
    ax.set_title('Phmex-S — PnL by Exit Reason')
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()
    print(f"  Saved: {output}")


def chart_win_loss_distribution(trades: list[dict], output: str):
    """Histogram of individual trade PnL distribution."""
    if not trades:
        return

    pnls = [_net(t) for t in trades]

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ['green' if p >= 0 else 'red' for p in pnls]
    ax.bar(range(len(pnls)), pnls, color=colors, alpha=0.8, edgecolor='black', linewidth=0.3)

    ax.axhline(y=0, color='black', linewidth=0.8)
    ax.set_xlabel('Trade #')
    ax.set_ylabel('PnL (USDT)')
    ax.set_title('Phmex-S — Individual Trade PnL')
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()
    print(f"  Saved: {output}")


def chart_rolling_win_rate(trades: list[dict], output: str, window: int = 10):
    """Rolling win rate over a window of trades."""
    if len(trades) < window:
        return

    rolling_wr = []
    for i in range(window, len(trades) + 1):
        batch = trades[i - window:i]
        wins = sum(1 for t in batch if _net(t) > 0)
        rolling_wr.append(wins / window * 100)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(range(window, len(trades) + 1), rolling_wr, 'b-', linewidth=1.5)
    ax.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50% breakeven')
    ax.axhline(y=60, color='orange', linestyle='--', alpha=0.5, label='60% target')

    ax.set_xlabel('Trade #')
    ax.set_ylabel('Win Rate (%)')
    ax.set_title(f'Phmex-S — Rolling {window}-Trade Win Rate')
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output, dpi=150)
    plt.close()
    print(f"  Saved: {output}")


def main():
    state = read_state()
    trades = state.get("closed_trades", [])

    if not trades:
        print("No closed trades found in trading_state.json")
        return

    ensure_chart_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"Generating charts from {len(trades)} trades...\n")

    chart_cumulative_pnl(trades, os.path.join(CHART_DIR, f"cumulative_pnl_{timestamp}.png"))
    chart_pnl_by_pair(trades, os.path.join(CHART_DIR, f"pnl_by_pair_{timestamp}.png"))
    chart_pnl_by_exit_reason(trades, os.path.join(CHART_DIR, f"pnl_by_exit_{timestamp}.png"))
    chart_win_loss_distribution(trades, os.path.join(CHART_DIR, f"trade_pnl_{timestamp}.png"))
    chart_rolling_win_rate(trades, os.path.join(CHART_DIR, f"rolling_winrate_{timestamp}.png"))

    print(f"\nAll charts saved to: {CHART_DIR}/")


if __name__ == "__main__":
    main()
