"""Load recorded flow_capture.jsonl into per-symbol, time-ordered records.

Read-only. Each normalized record carries exactly what ST2.0 + filters need:
price, orderbook imbalance/spread, and tape flow (buy_ratio, trade_count, cvd,
large_trade_bias, divergence). This is the same recorded stream the live bot
sampled, so the replay is a faithful RELATIVE comparison surface (not an
absolute-PnL forecaster — see spec).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from . import config as C

_PT = timezone(timedelta(hours=-7))


def _normalize(raw: dict) -> dict | None:
    try:
        ob = raw.get("ob") or {}
        flow = raw.get("flow") or {}
        ts = int(raw["ts"])
        price = float(raw["price"])
    except (KeyError, TypeError, ValueError):
        return None
    if price <= 0:
        return None
    div = flow.get("divergence")
    return {
        "ts": ts,
        "symbol": raw.get("symbol", "?"),
        "price": price,
        "imbalance": float(ob.get("imbalance", 0.0) or 0.0),
        "spread_pct": float(ob.get("spread_pct", 0.0) or 0.0),
        "buy_ratio": float(flow.get("buy_ratio", 0.5) or 0.5),
        "trade_count": int(flow.get("trade_count", 0) or 0),
        "cvd_slope": float(flow.get("cvd_slope", 0.0) or 0.0),
        "large_trade_bias": float(flow.get("large_trade_bias", 0.0) or 0.0),
        "divergence_bullish": div == "bullish",
        "divergence_bearish": div == "bearish",
        "hour": datetime.fromtimestamp(ts, tz=_PT).hour,
    }


def load_dataset(path: str = None, limit: int | None = None) -> dict[str, list]:
    """Return {symbol: [record, ...]} sorted by ts ascending."""
    path = path or C.FLOW_CAPTURE
    by_symbol: dict[str, list] = {}
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec = _normalize(raw)
            if rec is None:
                continue
            by_symbol.setdefault(rec["symbol"], []).append(rec)
            n += 1
            if limit and n >= limit:
                break
    for sym in by_symbol:
        by_symbol[sym].sort(key=lambda r: r["ts"])
    return by_symbol


def chronological_split(by_symbol: dict[str, list], train_frac: float = 0.7):
    """Split CHRONOLOGICALLY by global timestamp (no lookahead): train = oldest
    train_frac of records, test = the rest. Returns (train, test) as the same
    {symbol: [records]} shape, dropping symbols with no records on a side."""
    all_ts = sorted(r["ts"] for recs in by_symbol.values() for r in recs)
    if not all_ts:
        return {}, {}
    cut = all_ts[min(len(all_ts) - 1, int(train_frac * len(all_ts)))]
    train, test = {}, {}
    for sym, recs in by_symbol.items():
        tr = [r for r in recs if r["ts"] <= cut]
        te = [r for r in recs if r["ts"] > cut]
        if tr:
            train[sym] = tr
        if te:
            test[sym] = te
    return train, test


def dataset_summary(by_symbol: dict[str, list]) -> str:
    parts = []
    for sym, recs in sorted(by_symbol.items(), key=lambda kv: -len(kv[1]))[:8]:
        parts.append(f"{sym.split('/')[0]}:{len(recs)}")
    total = sum(len(r) for r in by_symbol.values())
    return f"{total} recs / {len(by_symbol)} syms ({', '.join(parts)})"
