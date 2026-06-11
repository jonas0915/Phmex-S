"""Daily sanity check on logs/flow_capture.jsonl.

Validates the in-bot flow capture deployed 2026-05-10. Telegrams ONLY when degraded
(low row rate, NaN incidents, schema breaks). Silent on healthy days.

Runs via com.phmex.flow-sanity launchd plist (6 AM PT daily).
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import notifier  # noqa: E402

FLOW_LOG = REPO_ROOT / "logs" / "flow_capture.jsonl"
WINDOW_HOURS = 24
MIN_ROWS_PER_HOUR = 100  # ~6/min × 18 pairs × 60min = lots; floor at 100 to alert on stalls
REQUIRED_FLOW_KEYS = {"buy_ratio", "cvd_slope", "trade_count"}
REQUIRED_OB_KEYS = {"imbalance", "spread_pct"}


def _has_nan(v) -> bool:
    if isinstance(v, float):
        return math.isnan(v) or math.isinf(v)
    return False


def audit() -> dict:
    if not FLOW_LOG.exists():
        return {"ok": False, "reason": "flow_capture.jsonl missing"}

    cutoff = time.time() - WINDOW_HOURS * 3600
    rows = 0
    rows_in_window = 0
    nan_rows = 0
    schema_breaks = 0
    pairs_seen: Counter = Counter()
    last_ts = 0
    first_ts_in_window = 0

    with FLOW_LOG.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                schema_breaks += 1
                continue
            ts = rec.get("ts", 0)
            if ts > last_ts:
                last_ts = ts
            if ts < cutoff:
                continue
            if first_ts_in_window == 0 or ts < first_ts_in_window:
                first_ts_in_window = ts
            rows_in_window += 1
            pairs_seen[rec.get("symbol", "?")] += 1
            flow = rec.get("flow") or {}
            ob = rec.get("ob") or {}
            if not REQUIRED_FLOW_KEYS.issubset(flow.keys()):
                schema_breaks += 1
            if ob and not REQUIRED_OB_KEYS.issubset(ob.keys()):
                schema_breaks += 1
            if any(_has_nan(v) for v in list(flow.values()) + list(ob.values())):
                nan_rows += 1

    # Scale expected_min by actual capture window — newly-started capture should not alert
    capture_hours = (time.time() - first_ts_in_window) / 3600 if first_ts_in_window else 0
    capture_hours = min(capture_hours, WINDOW_HOURS)
    expected_min = int(MIN_ROWS_PER_HOUR * capture_hours) if capture_hours >= 1 else 0
    healthy = (
        rows_in_window >= expected_min
        and nan_rows == 0
        and schema_breaks == 0
        and (time.time() - last_ts) < 600  # last write within 10 min
    )

    return {
        "ok": healthy,
        "rows_total": rows,
        "rows_24h": rows_in_window,
        "expected_min": expected_min,
        "nan_rows": nan_rows,
        "schema_breaks": schema_breaks,
        "pairs_seen": dict(pairs_seen.most_common(10)),
        "stale_seconds": int(time.time() - last_ts) if last_ts else None,
    }


def main() -> int:
    r = audit()
    print(json.dumps(r, indent=2))
    if r["ok"]:
        return 0
    msg_lines = ["[FLOW SANITY] degraded"]
    if "reason" in r:
        msg_lines.append(f"  reason: {r['reason']}")
    else:
        msg_lines.append(f"  24h rows: {r['rows_24h']} (min {r['expected_min']})")
        if r["nan_rows"]:
            msg_lines.append(f"  NaN rows: {r['nan_rows']}")
        if r["schema_breaks"]:
            msg_lines.append(f"  schema breaks: {r['schema_breaks']}")
        if r["stale_seconds"] and r["stale_seconds"] > 600:
            msg_lines.append(f"  stale: {r['stale_seconds']}s since last write")
    try:
        notifier.send("\n".join(msg_lines))
    except Exception as e:
        print(f"telegram send failed: {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
