"""Shared loader + helpers for vol-regime / divergence OOS edge search.

NEVER fabricate: all numbers come from running this against logs/flow_capture.jsonl.
Read-only on the data. No live code touched.
"""
import json
import bisect
from collections import defaultdict

DATA = "logs/flow_capture.jsonl"

# Fee assumptions (round-trip), from task spec.
FEE_LOW = 0.000663   # 0.0663% RT (maker-ish)
FEE_HIGH = 0.0012    # 0.12% RT (taker)


def load_by_symbol(path=DATA):
    """Return {symbol: [ {ts, price, div, tc} ... sorted by ts ]}."""
    by = defaultdict(list)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            flow = r.get("flow", {}) or {}
            price = r.get("price")
            ts = r.get("ts")
            if price is None or ts is None or price <= 0:
                continue
            by[r["symbol"]].append({
                "ts": ts,
                "price": float(price),
                "div": flow.get("divergence"),
                "tc": flow.get("trade_count"),
                "buy_ratio": flow.get("buy_ratio"),
            })
    for s in by:
        by[s].sort(key=lambda x: x["ts"])
    return by


def fwd_price(rows, ts_list, i, horizon, max_slack=None):
    """Price at the first snapshot with ts >= rows[i].ts + horizon.

    Gap-aware: uses timestamps, not index offsets. Returns None if the
    nearest forward snapshot is too far past the target (slack guard).
    max_slack default = horizon (i.e. don't accept a fill more than one
    horizon beyond target).
    """
    if max_slack is None:
        max_slack = horizon
    target = rows[i]["ts"] + horizon
    j = bisect.bisect_left(ts_list, target, i + 1)
    if j >= len(rows):
        return None
    if rows[j]["ts"] - target > max_slack:
        return None
    return rows[j]["price"]


def realized_vol(rows, ts_list, i, window=900):
    """Stdev of snapshot-to-snapshot log-ish returns over trailing `window` secs
    ending at i. Returns None if too few points."""
    lo_ts = rows[i]["ts"] - window
    k = bisect.bisect_left(ts_list, lo_ts, 0, i + 1)
    seg = rows[k:i + 1]
    if len(seg) < 4:
        return None
    rets = []
    for a in range(1, len(seg)):
        p0 = seg[a - 1]["price"]
        p1 = seg[a]["price"]
        if p0 > 0:
            rets.append((p1 - p0) / p0)
    if len(rets) < 3:
        return None
    m = sum(rets) / len(rets)
    var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
    return var ** 0.5


def ret_prior(rows, ts_list, i, window=900):
    """Return over trailing window: (price_i / price_at_window_start - 1)."""
    lo_ts = rows[i]["ts"] - window
    k = bisect.bisect_left(ts_list, lo_ts, 0, i + 1)
    if k >= i:
        return None
    p0 = rows[k]["price"]
    if p0 <= 0:
        return None
    return rows[i]["price"] / p0 - 1


def simulate_exit(entry_price, fwd_prices, direction, tp, sl):
    """Given a list of forward prices (chronological), simulate TP/SL.
    direction: +1 long, -1 short. tp/sl are fractions (e.g. 0.006).
    Returns gross return fraction (signed for the trade's direction).
    If neither hit, exit at last fwd price.
    """
    for p in fwd_prices:
        chg = (p - entry_price) / entry_price * direction
        if chg >= tp:
            return tp
        if chg <= -sl:
            return -sl
    if fwd_prices:
        return (fwd_prices[-1] - entry_price) / entry_price * direction
    return 0.0


def fwd_path(rows, ts_list, i, max_horizon):
    """List of forward prices from i+1 up to ts+max_horizon (for TP/SL sim)."""
    target = rows[i]["ts"] + max_horizon
    out = []
    for j in range(i + 1, len(rows)):
        if rows[j]["ts"] > target:
            break
        out.append(rows[j]["price"])
    return out
