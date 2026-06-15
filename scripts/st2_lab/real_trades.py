"""Ingest REAL ST2.0 live closed trades — the ground-truth data the sandbox can't make.

Each real live trade in trading_state_ST2.0.json carries an `entry_snapshot`
(ob.imbalance + flow.buy_ratio/cvd_slope/divergence/large_trade_bias/trade_count)
and a real `net_pnl`. We project those into the SAME record shape the evaluator /
diagnostics use ({feature..., net}), so the loop can find loss clusters in REAL
outcomes — not idealized 100%-fill replay. This is what closes the live→improve
loop: real fills + real PnL feed the improver.

Only `mode == "live"` trades count (real money). Paper sim trades are excluded.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

from . import config as C

ST2_STATE = os.path.join(C.BOT_DIR, "trading_state_ST2.0.json")
_PT = timezone(timedelta(hours=-7))


def _net(t: dict) -> float:
    v = t.get("net_pnl")
    return float(v) if v is not None else float(t.get("pnl_usdt", 0) or 0)


def _record(t: dict) -> dict | None:
    """Project a real closed trade into the diagnostics feature+net shape, or None
    if it lacks an entry_snapshot (can't be analyzed for entry-condition clusters)."""
    es = t.get("entry_snapshot")
    if not isinstance(es, dict):
        return None
    ob = es.get("ob") or {}
    flow = es.get("flow") or {}
    div = flow.get("divergence")
    ts = es.get("ts") or t.get("opened_at") or 0
    try:
        hour = datetime.fromtimestamp(int(ts), tz=_PT).hour if ts else 0
    except (ValueError, OverflowError, OSError):
        hour = 0
    return {
        "imbalance": float(ob.get("imbalance", 0.0) or 0.0),
        "spread_pct": float(ob.get("spread_pct", 0.0) or 0.0),
        "buy_ratio": float(flow.get("buy_ratio", 0.5) or 0.5),
        "trade_count": int(flow.get("trade_count", 0) or 0),
        "cvd_slope": float(flow.get("cvd_slope", 0.0) or 0.0),
        "large_trade_bias": float(flow.get("large_trade_bias", 0.0) or 0.0),
        "divergence_bullish": div == "bullish",
        "divergence_bearish": div == "bearish",
        "hour": hour,
        "net": _net(t),
    }


def load_real_trades(state_file: str = None) -> list[dict]:
    """Real LIVE ST2.0 trades as diagnostics records (entry features + real net).
    Trades without an entry_snapshot are skipped (and counted in load_summary)."""
    state_file = state_file or ST2_STATE
    if not os.path.exists(state_file):
        return []
    try:
        ct = json.load(open(state_file)).get("closed_trades", [])
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for t in ct:
        if t.get("mode") != "live":
            continue
        rec = _record(t)
        if rec is not None:
            out.append(rec)
    return out


def real_summary(records: list[dict]) -> dict:
    """Real-money performance summary (the honest scoreboard)."""
    n = len(records)
    if n == 0:
        return {"trades": 0, "net": 0.0, "expectancy": 0.0, "wr": 0.0, "wins": 0, "losses": 0}
    nets = [r["net"] for r in records]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    return {
        "trades": n,
        "net": round(sum(nets), 4),
        "expectancy": round(sum(nets) / n, 4),
        "wr": round(len(wins) / n, 4),
        "wins": len(wins),
        "losses": len(losses),
    }


def format_report(summary: dict) -> str:
    if summary["trades"] == 0:
        return "REAL trades: none live yet"
    return (f"REAL live trades: {summary['trades']} | "
            f"expectancy {summary['expectancy']:+.4f}/trade | "
            f"net {summary['net']:+.2f} | WR {summary['wr']*100:.0f}% "
            f"({summary['wins']}W/{summary['losses']}L)")
