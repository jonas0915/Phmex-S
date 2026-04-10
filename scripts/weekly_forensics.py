#!/usr/bin/env python3
"""Weekly forensics — deterministic pattern detection on last 7 days of trades.

Runs via launchd every Sunday 8 PM PT. Loads closed_trades, groups by
(symbol, side, exit_reason, hour_pt), flags buckets with significant
win-rate deviation, writes Telegram summary + markdown report.

NO LLM in the loop. Pure pandas.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PT = ZoneInfo("America/Los_Angeles")
STATE_FILE = ROOT / "trading_state.json"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(exist_ok=True)


def _net(t: dict) -> float:
    n = t.get("net_pnl")
    return float(n if n is not None else t.get("pnl_usdt", 0) or 0)


def find_significant_patterns(
    trades: list[dict],
    min_n: int = 10,
    min_deviation: float = 0.2,
) -> list[dict]:
    """Group trades into buckets and return buckets with significant WR deviation.

    Buckets: (symbol, side, exit_reason, hour_pt).
    A bucket is 'significant' when n >= min_n AND |win_rate - 0.5| >= min_deviation.
    """
    buckets: dict[tuple, list] = defaultdict(list)
    for t in trades:
        symbol = t.get("symbol", "?")
        side = t.get("side", "?")
        reason = t.get("exit_reason") or t.get("reason") or "?"
        opened = t.get("opened_at") or t.get("closed_at") or 0
        if opened:
            hour_pt = datetime.fromtimestamp(opened, tz=PT).hour
        else:
            hour_pt = -1
        # Build coarse-grained buckets first
        buckets[(symbol, side, None, None)].append(t)
        buckets[(symbol, None, reason, None)].append(t)
        buckets[(symbol, side, None, hour_pt)].append(t)

    patterns = []
    for key, bucket_trades in buckets.items():
        n = len(bucket_trades)
        if n < min_n:
            continue
        wins = sum(1 for t in bucket_trades if _net(t) > 0)
        wr = wins / n
        deviation = wr - 0.5
        if abs(deviation) < min_deviation:
            continue
        symbol, side, reason, hour = key
        label_parts = [symbol]
        if side:
            label_parts.append(side)
        if reason:
            label_parts.append(f"reason={reason}")
        if hour is not None and hour != -1:
            label_parts.append(f"hour={hour:02d}PT")
        label = " ".join(label_parts)
        patterns.append({
            "label": label,
            "n": n,
            "wins": wins,
            "win_rate": wr,
            "deviation": deviation,
            "net_pnl": sum(_net(t) for t in bucket_trades),
        })
    # Sort by absolute deviation descending
    patterns.sort(key=lambda p: abs(p["deviation"]), reverse=True)
    return patterns


def load_recent_trades(days: int = 7) -> list[dict]:
    if not STATE_FILE.exists():
        return []
    data = json.loads(STATE_FILE.read_text())
    cutoff = time.time() - (days * 86400)
    return [t for t in data.get("closed_trades", []) if (t.get("closed_at") or 0) >= cutoff]


def write_report(patterns: list[dict], date_str: str) -> Path:
    path = REPORT_DIR / f"forensics_{date_str}.md"
    lines = [f"# Weekly Forensics — {date_str}", ""]
    if not patterns:
        lines.append("No significant patterns detected (n>=10, |WR deviation|>=0.2).")
    else:
        lines.append(f"Found {len(patterns)} significant patterns. Top 10:\n")
        lines.append("| Rank | Pattern | N | Wins | WR | Net |")
        lines.append("|---|---|---|---|---|---|")
        for i, p in enumerate(patterns[:10], 1):
            lines.append(f"| {i} | {p['label']} | {p['n']} | {p['wins']} | {p['win_rate']*100:.1f}% | ${p['net_pnl']:+.2f} |")
    path.write_text("\n".join(lines) + "\n")
    return path


def send_telegram_summary(patterns: list[dict], report_path: Path) -> None:
    try:
        from notifier import send
    except Exception:
        return
    if not patterns:
        send("📊 Weekly forensics: no significant patterns this week.")
        return
    top = patterns[0]
    msg = (
        f"📊 Weekly forensics — {len(patterns)} significant patterns\n"
        f"Top: {top['label']} — {top['n']} trades, "
        f"{top['win_rate']*100:.0f}% WR, ${top['net_pnl']:+.2f}\n"
        f"Full report: {report_path.name}"
    )
    send(msg)


def main() -> None:
    trades = load_recent_trades(days=7)
    patterns = find_significant_patterns(trades, min_n=10, min_deviation=0.2)
    date_str = datetime.now(PT).strftime("%Y-%m-%d")
    report = write_report(patterns, date_str)
    send_telegram_summary(patterns, report)
    print(f"Report saved: {report}")


if __name__ == "__main__":
    main()
