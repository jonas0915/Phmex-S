#!/usr/bin/env python3
"""Audit post-restart closed trades for maker/taker inference from fees.
Restart: PID 69117 started 2026-06-12 22:06 ET (machine clock = Eastern).
Maker fee ~0.01%/side, taker ~0.06%/side. Read-only."""
import json, datetime as dt

STATE = "/Users/jonaspenaso/Desktop/Phmex-S/trading_state.json"
# Restart epoch: 2026-06-12 22:06:00 Eastern (machine local). Use naive local.
RESTART = dt.datetime(2026, 6, 12, 22, 6, 0)

with open(STATE) as f:
    s = json.load(f)

ct = s.get("closed_trades", [])
print(f"total closed_trades in state: {len(ct)}")

# find timestamp field name
sample = ct[-1] if ct else {}
print("sample keys:", sorted(sample.keys()))

def parse_ts(t):
    if t is None:
        return None
    if isinstance(t, (int, float)):
        # epoch seconds or ms
        v = float(t)
        if v > 1e12:
            v /= 1000.0
        return dt.datetime.fromtimestamp(v)
    if isinstance(t, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return dt.datetime.strptime(t[:26], fmt)
            except ValueError:
                continue
        try:
            return dt.datetime.fromisoformat(t.replace("Z", ""))
        except Exception:
            return None
    return None

# Detect close-time field
TS_FIELDS = ["exit_time", "close_time", "closed_at", "timestamp", "exit_ts", "time"]
ts_field = next((k for k in TS_FIELDS if k in sample), None)
print("using ts field:", ts_field)

post = []
for t in ct:
    ts = parse_ts(t.get(ts_field)) if ts_field else None
    if ts and ts >= RESTART:
        post.append((ts, t))

post.sort(key=lambda x: x[0])
print(f"\n=== {len(post)} trades closed AFTER restart {RESTART} ===\n")

for ts, t in post:
    sym = t.get("symbol")
    side = t.get("side")
    reason = t.get("exit_reason") or t.get("reason")
    fee = t.get("fees_usdt", t.get("fee", t.get("fees")))
    pnl = t.get("pnl_usdt", t.get("pnl"))
    notional = None
    ep = t.get("entry_price"); xp = t.get("exit_price"); amt = t.get("amount") or t.get("coin_amount")
    fee_rate_str = "?"
    if fee is not None and ep and xp and amt:
        try:
            notional = (float(ep) + float(xp)) * float(amt)  # both sides combined
            rate = float(fee) / notional if notional else None
            if rate is not None:
                fee_rate_str = f"{rate*100:.4f}% (2-side combined)"
        except Exception:
            pass
    print(f"{ts}  {sym:18} {side:5} {str(reason):16} fee={fee}  pnl={pnl}  rate={fee_rate_str}")
