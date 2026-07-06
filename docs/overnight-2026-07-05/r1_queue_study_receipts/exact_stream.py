#!/usr/bin/env python3
"""Exact touch-queue at placement (streaming, one pass per symbol-day file).

For each June+ htf_l2 fill/miss on a tick-recorded symbol (ARB/BTC/ETH/INJ),
find the book snapshot nearest (anchor_ts - 20s) [placement estimate; misses'
ts is the outcome log line, fills' ts is opened_at≈fill], read resting size at
our limit price on our side (top-5; touch fallback), normalize by symbol-day
median touch size (every-200th-line sample). O(1) memory. READ-ONLY.
"""
import gzip, json, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/Users/jonaspenaso/Desktop/Phmex-S")
TICKS = REPO / "logs" / "l2_ticks"
JUNE1 = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
TICK_SYMS = {"ARB/USDT:USDT", "BTC/USDT:USDT", "ETH/USDT:USDT", "INJ/USDT:USDT"}
BACKOFF = 20.0

anchors = defaultdict(list)  # (sym, day) -> list of anchor dicts
state = json.load(open(REPO / "trading_state.json"))
for t in state["closed_trades"]:
    if (t.get("strategy") != "htf_l2_anticipation" or (t.get("opened_at") or 0) < JUNE1
            or t["symbol"] not in TICK_SYMS
            or t.get("exit_reason") == "min_margin_skip" or t.get("reason") == "min_margin_skip"
            or (t.get("net_pnl") == 0 and (t.get("duration_s") or 0) < 60)
            or not t.get("entry_price")):
        continue
    est = t["opened_at"] - BACKOFF
    day = datetime.fromtimestamp(est, tz=timezone.utc).strftime("%Y-%m-%d")
    anchors[(t["symbol"], day)].append(
        {"kind": "fill", "side": t["side"], "px": t["entry_price"], "est": est,
         "net": t["net_pnl"], "best_gap": 30.0, "best": None})
mm = json.load(open(REPO / "reports" / "main_missed_fills.json"))
for m in mm["misses"]:
    if m.get("partial_skip") or m["sym"] not in TICK_SYMS:
        continue
    est = m["ts"] - BACKOFF
    day = datetime.fromtimestamp(est, tz=timezone.utc).strftime("%Y-%m-%d")
    anchors[(m["sym"], day)].append(
        {"kind": "miss", "side": m["side"], "px": m["px"], "est": est,
         "net": m.get("sim_net"), "best_gap": 30.0, "best": None})

print(f"{sum(len(v) for v in anchors.values())} anchors over {len(anchors)} symbol-days", flush=True)

rows = []
for (sym, day), alist in sorted(anchors.items()):
    sym_dir = TICKS / sym.replace("/", "_").replace(":", "_")
    path = None
    for ext in (".jsonl", ".jsonl.gz"):
        p = sym_dir / f"{day}{ext}"
        if p.exists():
            path = p
            break
    if path is None:
        for a in alist:
            rows.append({**a, "covered": False, "symbol": sym, "day": day})
        print(f"{sym} {day}: NO FILE", flush=True)
        continue
    touch_bid, touch_ask = [], []
    i = 0
    lo_t = min(a["est"] for a in alist) - 35
    hi_t = max(a["est"] for a in alist) + 35
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as fh:
        for line in fh:
            i += 1
            if i % 200 == 0 or True:
                pass
            # cheap prefilter: only parse sampled lines or lines possibly in window
            parse_for_median = (i % 200 == 0)
            # we can't know ts without parsing; parse every line but keep it lean
            try:
                d = json.loads(line)
            except Exception:
                continue
            b, a_ = d.get("b"), d.get("a")
            if not b or not a_:
                continue
            if parse_for_median:
                touch_bid.append(float(b[0][1]))
                touch_ask.append(float(a_[0][1]))
            ts = d["ts"] / 1000.0
            if ts < lo_t or ts > hi_t:
                continue
            for an in alist:
                gap = abs(ts - an["est"])
                if gap < an["best_gap"]:
                    an["best_gap"] = gap
                    levels = b if an["side"] == "long" else a_
                    sz, exact = None, False
                    for lpx, lsz in levels:
                        if abs(float(lpx) - an["px"]) / an["px"] < 1e-6:
                            sz, exact = float(lsz), True
                            break
                    if sz is None:
                        sz = float(levels[0][1])
                    an["best"] = {"size": sz, "at_exact_level": exact,
                                  "snap_gap_s": round(gap, 2)}
    med_b = statistics.median(touch_bid) if touch_bid else None
    med_a = statistics.median(touch_ask) if touch_ask else None
    for an in alist:
        med = med_b if an["side"] == "long" else med_a
        r = {"symbol": sym, "day": day, "kind": an["kind"], "side": an["side"],
             "net": an["net"], "covered": an["best"] is not None}
        if an["best"] and med:
            r.update(an["best"])
            r["rel_queue"] = round(an["best"]["size"] / med, 3)
        rows.append(r)
    print(f"{sym} {day}: {len(alist)} anchors, "
          f"{sum(1 for an in alist if an['best'])} covered ({i} lines)", flush=True)

cov = [r for r in rows if r.get("covered") and r.get("rel_queue") is not None]
fw = [r["rel_queue"] for r in cov if r["kind"] == "fill" and r["net"] > 0]
fl = [r["rel_queue"] for r in cov if r["kind"] == "fill" and r["net"] < 0]
ms = [r["rel_queue"] for r in cov if r["kind"] == "miss"]
print(f"\ncovered {len(cov)}/{len(rows)}; exact-level {sum(1 for r in cov if r['at_exact_level'])}")
for name, v in (("fill-win", fw), ("fill-loss", fl), ("miss", ms)):
    if v:
        print(f"{name}: n={len(v)} median rel-queue {statistics.median(v):.2f} mean {sum(v)/len(v):.2f}")

import numpy as np
rng = np.random.default_rng(42)
res = {"rows": rows}
if len(fw) > 1 and len(fl) > 1:
    a, b = np.array(fl, float), np.array(fw, float)
    diffs = [a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean()
             for _ in range(10000)]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"loss-minus-win rel-queue diff {a.mean()-b.mean():+.2f} 95% CI [{lo:+.2f},{hi:+.2f}]")
    res["loss_minus_win"] = {"diff": round(float(a.mean()-b.mean()), 3),
                             "ci": [round(float(lo), 3), round(float(hi), 3)],
                             "n": [len(fl), len(fw)]}
fills_all = fw + fl
if len(ms) > 1 and len(fills_all) > 1:
    a, b = np.array(ms, float), np.array(fills_all, float)
    diffs = [a[rng.integers(0, len(a), len(a))].mean() - b[rng.integers(0, len(b), len(b))].mean()
             for _ in range(10000)]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"miss-minus-fill rel-queue diff {a.mean()-b.mean():+.2f} 95% CI [{lo:+.2f},{hi:+.2f}]")
    res["miss_minus_fill"] = {"diff": round(float(a.mean()-b.mean()), 3),
                              "ci": [round(float(lo), 3), round(float(hi), 3)],
                              "n": [len(ms), len(fills_all)]}
Path("exact_stream_out.json").write_text(json.dumps(res, indent=1))
print("wrote exact_stream_out.json", flush=True)
