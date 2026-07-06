#!/usr/bin/env python3
"""Supplement: near-side x opposite-side depth 2x2 (web finding #1 replication,
20-level USDT depth from flow_capture, within-symbol median split). READ-ONLY."""
import bisect, json, statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

REPO = Path("/Users/jonaspenaso/Desktop/Phmex-S")
JUNE1 = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
RNG = np.random.default_rng(7)

flow_idx = defaultdict(lambda: ([], []))
with open(REPO / "logs" / "flow_capture.jsonl") as fh:
    for line in fh:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("ts", 0) < JUNE1 - 3600:
            continue
        ob = d.get("ob") or {}
        if ob.get("bid_depth_usdt") is None:
            continue
        ts_l, r_l = flow_idx[d["symbol"]]
        ts_l.append(d["ts"]); r_l.append(ob)

med = {}
for sym, (ts_l, r_l) in flow_idx.items():
    med[(sym, "bid")] = statistics.median([r["bid_depth_usdt"] for r in r_l])
    med[(sym, "ask")] = statistics.median([r["ask_depth_usdt"] for r in r_l])

def join(sym, ts, side, tol=90.0):
    ts_l, r_l = flow_idx.get(sym, ([], []))
    if not ts_l:
        return None
    i = bisect.bisect_left(ts_l, ts)
    best, gap = None, tol
    for j in (i - 1, i):
        if 0 <= j < len(ts_l) and abs(ts_l[j] - ts) < gap:
            best, gap = j, abs(ts_l[j] - ts)
    if best is None:
        return None
    r = r_l[best]
    nb, ob_ = ("bid", "ask") if side == "long" else ("ask", "bid")
    return {"near_big": r[f"{nb}_depth_usdt"] > med[(sym, nb)],
            "opp_big": r[f"{ob_}_depth_usdt"] > med[(sym, ob_)]}

state = json.load(open(REPO / "trading_state.json"))
cells = defaultdict(list)
for t in state["closed_trades"]:
    if t.get("strategy") != "htf_l2_anticipation" or (t.get("opened_at") or 0) < JUNE1:
        continue
    if t.get("exit_reason") == "min_margin_skip" or t.get("reason") == "min_margin_skip":
        continue
    if t.get("net_pnl") == 0 and (t.get("duration_s") or 0) < 60:
        continue
    q = join(t["symbol"], t["opened_at"], t["side"])
    if q:
        cells[("fill", q["near_big"], q["opp_big"])].append(t["net_pnl"])

mm = json.load(open(REPO / "reports" / "main_missed_fills.json"))
for m in mm["misses"]:
    if m.get("partial_skip"):
        continue
    q = join(m["sym"], m["ts"], m["side"])
    if q:
        cells[("miss", q["near_big"], q["opp_big"])].append(m.get("sim_net"))

print("cell (kind, near_big, opp_big): n, WR/simWR, sum$, avg$  [small_sample if n<20]")
out = {}
for k in sorted(cells, key=str):
    v = [x for x in cells[k] if x is not None]
    kind, nb, ob_ = k
    lab = f"{kind} near={'BIG' if nb else 'small'} opp={'BIG' if ob_ else 'small'}"
    wr = sum(1 for x in v if x > 0) / len(v) if v else None
    print(f"{lab:>34}: n={len(v):>3} WR={wr:.2f} sum={sum(v):+.2f} avg={statistics.mean(v):+.4f}"
          f"{'  [n<20]' if len(v) < 20 else ''}")
    out[lab] = {"n": len(v), "wr": round(wr, 3), "sum": round(sum(v), 2),
                "avg": round(statistics.mean(v), 4)}
# paper's clean cell: near BIG + opp small; worst: (their worst was small-near+large-opp)
a = cells.get(("fill", True, False), [])
rest = [x for k2, v2 in cells.items() if k2[0] == "fill" and k2 != ("fill", True, False) for x in v2]
if len(a) > 1 and len(rest) > 1:
    a, r = np.array(a, float), np.array(rest, float)
    diffs = [a[RNG.integers(0, len(a), len(a))].mean() - r[RNG.integers(0, len(r), len(r))].mean()
             for _ in range(10000)]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"\nfill 'clean cell' (nearBIG+oppSmall) minus other fills, avg$: "
          f"{a.mean()-r.mean():+.4f} 95% CI [{lo:+.4f}, {hi:+.4f}] (n={len(a)}/{len(r)})")
    out["clean_cell_minus_rest"] = {"diff": round(float(a.mean()-r.mean()), 4),
                                    "ci": [round(float(lo), 4), round(float(hi), 4)],
                                    "n": [len(a), len(r)]}
Path("near_opp_2x2_out.json").write_text(json.dumps(out, indent=1))
