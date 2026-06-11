"""Sprint checkpoint — fires on 2026-05-17 (day 7) and 2026-05-24 (day 14, end of 2-week sprint).

Compiles a decision packet and pings Telegram. Human decides next move in a fresh session.

Day 7 packet:
  - Flow capture rows/24h, NaN rate
  - Latest weekly_sweep ranking (if exists)
  - Status: should we wire flow replay yet?

Day 14 packet:
  - All of the above
  - Live bot net PnL since 2026-05-10 (sprint start)
  - Total trades, win rate
  - Suggested verdict: A (promote variant) / B (no edge, pivot) / C (not calibrated yet)
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import notifier  # noqa: E402

SPRINT_START = datetime.datetime(2026, 5, 10, tzinfo=datetime.timezone.utc).timestamp()
FLOW_LOG = REPO_ROOT / "logs" / "flow_capture.jsonl"
STATE_PATH = REPO_ROOT / "trading_state.json"
REPORTS_DIR = REPO_ROOT / "reports"


def flow_stats() -> dict:
    if not FLOW_LOG.exists():
        return {"days_captured": 0, "total_rows": 0}
    rows = 0
    earliest = float("inf")
    latest = 0
    with FLOW_LOG.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows += 1
            ts = rec.get("ts", 0)
            if ts < earliest:
                earliest = ts
            if ts > latest:
                latest = ts
    span_days = (latest - earliest) / 86400 if earliest != float("inf") else 0
    return {"days_captured": round(span_days, 1), "total_rows": rows}


def live_pnl_since_sprint() -> dict:
    if not STATE_PATH.exists():
        return {"trades": 0, "net_pnl": 0.0, "win_rate": 0.0}
    state = json.loads(STATE_PATH.read_text())
    trades = [
        t for t in state.get("closed_trades", [])
        if t.get("closed_at", 0) >= SPRINT_START
    ]
    if not trades:
        return {"trades": 0, "net_pnl": 0.0, "win_rate": 0.0}
    net = sum(t.get("net_pnl", t.get("pnl_usdt", 0.0)) for t in trades)
    wins = sum(1 for t in trades if t.get("net_pnl", t.get("pnl_usdt", 0)) > 0)
    return {"trades": len(trades), "net_pnl": net, "win_rate": wins / len(trades) * 100}


def latest_sweep() -> str | None:
    if not REPORTS_DIR.exists():
        return None
    files = sorted(REPORTS_DIR.glob("sweep_*.md"))
    return files[-1].name if files else None


def build_day7_packet() -> str:
    f = flow_stats()
    sweep = latest_sweep()
    lines = [
        "[SPRINT D7] 2026-05-17 checkpoint",
        f"Flow capture: {f['days_captured']}d, {f['total_rows']:,} rows",
        f"Latest sweep: {sweep or 'none yet'}",
        "",
        "Decision: ready to wire flow replay in backtest.py?",
        "  - If flow_days >= 7 AND no schema issues → YES, next session",
        "  - Else → extend capture window",
    ]
    return "\n".join(lines)


def build_day14_packet() -> str:
    f = flow_stats()
    p = live_pnl_since_sprint()
    sweep = latest_sweep()
    lines = [
        "[SPRINT D14] 2026-05-24 final checkpoint",
        f"Flow capture: {f['days_captured']}d, {f['total_rows']:,} rows",
        f"Live since sprint start: {p['trades']}t, net ${p['net_pnl']:+.2f}, WR {p['win_rate']:.0f}%",
        f"Latest sweep: {sweep or 'none'}",
        "",
        "Verdict options:",
        "  A) Calibrated + variant clears CI>0 → promote",
        "  B) Calibrated + no edge → pivot/pause",
        "  C) Not calibrated yet → diagnose + extend or pivot",
        "",
        "Next session: review reports/, decide A/B/C.",
    ]
    return "\n".join(lines)


def main() -> int:
    today = datetime.date.today()
    day7 = datetime.date(2026, 5, 17)
    day14 = datetime.date(2026, 5, 24)
    if today == day7:
        msg = build_day7_packet()
    elif today == day14:
        msg = build_day14_packet()
    else:
        print(f"Not a checkpoint date (today={today}). Skipping.")
        return 0
    print(msg)
    try:
        notifier.send(msg)
    except Exception as e:
        print(f"telegram send failed: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
