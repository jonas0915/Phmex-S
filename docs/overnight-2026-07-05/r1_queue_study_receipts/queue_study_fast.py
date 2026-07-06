#!/usr/bin/env python3
"""Queue-state conditioning study on main-bot htf_l2 PostOnly fills (2026-07-05).

READ-ONLY. Joins:
 - trading_state.json June+ htf_l2 closed trades (entry_snapshot ob/flow)
 - logs/flow_capture.jsonl (20-level bid/ask_depth_usdt, ~cycle cadence) within 90s
 - reports/l2x_postentry_drift.json (post-entry drift bps per fill)
 - reports/main_missed_fills.json (100 PostOnly misses w/ replay sim_net)
 - logs/l2_ticks/{ARB,BTC,ETH,INJ} exact top-5 book (touch-queue at placement est.)
Bootstrap: independent resampling per group, diff per iteration (lessons.md rule).
"""
import bisect, glob, gzip, json, statistics, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

REPO = Path("/Users/jonaspenaso/Desktop/Phmex-S")
JUNE1 = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
RNG = np.random.default_rng(42)
OUT = {}

def boot_diff(a, b, n=10000):
    """mean(a) - mean(b), 95% CI via independent resampling."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2 or len(b) < 2:
        return None
    diffs = [a[RNG.integers(0, len(a), len(a))].mean()
             - b[RNG.integers(0, len(b), len(b))].mean() for _ in range(n)]
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"diff": round(float(a.mean() - b.mean()), 4),
            "ci_lo": round(float(lo), 4), "ci_hi": round(float(hi), 4),
            "n_a": len(a), "n_b": len(b)}

# ---------- 1. flow_capture index ----------
flow_idx = defaultdict(lambda: ([], []))  # symbol -> (ts_list, rec_list)
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

def flow_at(sym, ts, tol=90.0):
    ts_l, r_l = flow_idx.get(sym, ([], []))
    if not ts_l:
        return None, None
    i = bisect.bisect_left(ts_l, ts)
    best, gap = None, tol
    for j in (i - 1, i):
        if 0 <= j < len(ts_l) and abs(ts_l[j] - ts) < gap:
            best, gap = j, abs(ts_l[j] - ts)
    return (r_l[best], gap) if best is not None else (None, None)

# per-symbol-side depth pools for percentile normalization (June+)
depth_pool = {}
for sym, (ts_l, r_l) in flow_idx.items():
    depth_pool[(sym, "bid")] = np.sort([r["bid_depth_usdt"] for r in r_l])
    depth_pool[(sym, "ask")] = np.sort([r["ask_depth_usdt"] for r in r_l])

def depth_pctile(sym, side_book, v):
    pool = depth_pool.get((sym, side_book))
    if pool is None or len(pool) < 50:
        return None
    return float(np.searchsorted(pool, v) / len(pool))

# ---------- 2. drift join ----------
drift = json.load(open(REPO / "reports" / "l2x_postentry_drift.json"))
drift_by_key = {}
for t in drift["trades"]:
    drift_by_key[(t["symbol"], round(t["entry_ts"]))] = t

# ---------- 3. fills ----------
state = json.load(open(REPO / "trading_state.json"))
fills = []
for t in state["closed_trades"]:
    if t.get("strategy") != "htf_l2_anticipation":
        continue
    if (t.get("opened_at") or 0) < JUNE1:
        continue
    if t.get("exit_reason") == "min_margin_skip" or t.get("reason") == "min_margin_skip":
        continue
    if t.get("net_pnl") == 0 and (t.get("duration_s") or 0) < 60:
        continue  # phantom guard (drift-study convention)
    es = t.get("entry_snapshot") or {}
    ob = es.get("ob") or {}
    side = t["side"]
    imb = ob.get("imbalance")
    row = {
        "symbol": t["symbol"], "side": side,
        "opened_at": t["opened_at"], "net_pnl": t["net_pnl"],
        "win": t["net_pnl"] > 0,
        "spread_pct": ob.get("spread_pct"),
        "near_imb": (imb if side == "long" else -imb) if imb is not None else None,
        "near_walls": ob.get("bid_walls") if side == "long" else ob.get("ask_walls"),
        "entry_price": t.get("entry_price"),
    }
    # flow_capture depth join
    fc, gap = flow_at(t["symbol"], t["opened_at"])
    if fc:
        book_side = "bid" if side == "long" else "ask"
        nd = fc["bid_depth_usdt"] if side == "long" else fc["ask_depth_usdt"]
        row["near_depth"] = nd
        row["near_depth_pctile"] = depth_pctile(t["symbol"], book_side, nd)
        row["fc_gap_s"] = round(gap, 1)
    # drift join
    dt = drift_by_key.get((t["symbol"], round(t["opened_at"])))
    if dt is None:  # tolerance +/-2s
        for off in (-2, -1, 1, 2):
            dt = drift_by_key.get((t["symbol"], round(t["opened_at"]) + off))
            if dt:
                break
    if dt:
        row["drift5"] = dt["drift"].get("5")
        row["drift15"] = dt["drift"].get("15")
        row["drift30"] = dt["drift"].get("30")
        row["mae30"] = dt["mae"].get("30")
    fills.append(row)

print(f"June+ htf_l2 non-phantom fills: {len(fills)}")
print(f"  with entry_snapshot imbalance: {sum(1 for r in fills if r['near_imb'] is not None)}")
print(f"  with flow_capture depth join (<=90s): {sum(1 for r in fills if 'near_depth' in r)}")
print(f"  with drift join: {sum(1 for r in fills if 'drift15' in r)}")
gaps = [r["fc_gap_s"] for r in fills if "fc_gap_s" in r]
if gaps:
    print(f"  fc join gap median {statistics.median(gaps):.1f}s max {max(gaps):.1f}s")
OUT["fill_counts"] = {"n": len(fills),
                      "with_imb": sum(1 for r in fills if r["near_imb"] is not None),
                      "with_depth": sum(1 for r in fills if "near_depth" in r),
                      "with_drift": sum(1 for r in fills if "drift15" in r)}

# ---------- 4. bucket comparisons on fills ----------
def bucket_report(rows, feat, name, thresholds=None):
    vals = [r[feat] for r in rows if r.get(feat) is not None]
    if len(vals) < 10:
        print(f"\n[{name}] insufficient n={len(vals)}")
        return None
    med = statistics.median(vals)
    lo = [r for r in rows if r.get(feat) is not None and r[feat] <= med]
    hi = [r for r in rows if r.get(feat) is not None and r[feat] > med]
    res = {"feature": name, "median_split_at": round(med, 4), "buckets": {}}
    print(f"\n=== {name} (median split at {med:.4g}) ===")
    print(f"{'bucket':>18} {'n':>4} {'WR%':>6} {'sum$':>8} {'avg$':>8} {'d15bps':>8} {'n_d':>4}")
    for label, seg in (("low(front-ish)", lo), ("high(back-ish)", hi)):
        d15 = [r["drift15"] for r in seg if r.get("drift15") is not None]
        b = {"n": len(seg),
             "wr": round(sum(r["win"] for r in seg) / len(seg), 3) if seg else None,
             "sum_net": round(sum(r["net_pnl"] for r in seg), 2),
             "avg_net": round(statistics.mean([r["net_pnl"] for r in seg]), 4) if seg else None,
             "mean_drift15": round(statistics.mean(d15), 1) if d15 else None,
             "n_drift": len(d15),
             "small_sample": len(seg) < 20}
        res["buckets"][label] = b
        print(f"{label:>18} {b['n']:>4} {b['wr']*100 if b['wr'] is not None else 0:>6.1f} "
              f"{b['sum_net']:>8.2f} {b['avg_net']:>8.4f} "
              f"{b['mean_drift15'] if b['mean_drift15'] is not None else float('nan'):>8} {b['n_drift']:>4}")
    ci_pnl = boot_diff([r["net_pnl"] for r in hi], [r["net_pnl"] for r in lo])
    ci_d15 = boot_diff([r["drift15"] for r in hi if r.get("drift15") is not None],
                       [r["drift15"] for r in lo if r.get("drift15") is not None])
    res["hi_minus_lo_netpnl"] = ci_pnl
    res["hi_minus_lo_drift15"] = ci_d15
    if ci_pnl:
        print(f"  hi-lo avg net$: {ci_pnl['diff']:+.4f}  95% CI [{ci_pnl['ci_lo']:+.4f}, {ci_pnl['ci_hi']:+.4f}]")
    if ci_d15:
        print(f"  hi-lo drift15bps: {ci_d15['diff']:+.1f}  95% CI [{ci_d15['ci_lo']:+.1f}, {ci_d15['ci_hi']:+.1f}] (n={ci_d15['n_a']}/{ci_d15['n_b']})")
    return res

OUT["fill_buckets"] = {}
for feat, name in (("near_depth_pctile", "near-side 20L depth pctile (within-symbol)"),
                   ("near_imb", "side-relative book imbalance"),
                   ("spread_pct", "spread_pct"),
                   ("near_walls", "near-side walls")):
    r = bucket_report(fills, feat, name)
    if r:
        OUT["fill_buckets"][feat] = r

# quintiles on depth pctile
dp = [r for r in fills if r.get("near_depth_pctile") is not None]
print(f"\n=== depth-pctile quintiles (fills, n={len(dp)}) ===")
qrows = []
for i in range(5):
    seg = [r for r in dp if i/5 <= r["near_depth_pctile"] < (i+1)/5 + (0.001 if i == 4 else 0)]
    if seg:
        d15 = [r["drift15"] for r in seg if r.get("drift15") is not None]
        qrows.append({"q": f"{i*20}-{(i+1)*20}%", "n": len(seg),
                      "wr": round(sum(r['win'] for r in seg)/len(seg), 3),
                      "sum_net": round(sum(r['net_pnl'] for r in seg), 2),
                      "mean_d15": round(statistics.mean(d15), 1) if d15 else None,
                      "small_sample": len(seg) < 20})
        print(f"  {qrows[-1]}")
OUT["fill_depth_quintiles"] = qrows

# ---------- 5. misses ----------
mm = json.load(open(REPO / "reports" / "main_missed_fills.json"))
misses = []
for m in mm["misses"]:
    if m.get("partial_skip"):
        continue
    fc, gap = flow_at(m["sym"], m["ts"])
    row = {"symbol": m["sym"], "side": m["side"], "ts": m["ts"], "px": m["px"],
           "sim_net": m.get("sim_net"), "blocked": m.get("blocked_by_occupancy")}
    if fc:
        book_side = "bid" if m["side"] == "long" else "ask"
        nd = fc["bid_depth_usdt"] if m["side"] == "long" else fc["ask_depth_usdt"]
        imb = fc.get("imbalance")
        row["near_depth"] = nd
        row["near_depth_pctile"] = depth_pctile(m["sym"], book_side, nd)
        row["near_imb"] = imb if m["side"] == "long" else (-imb if imb is not None else None)
        row["spread_pct"] = fc.get("spread_pct")
        row["fc_gap_s"] = round(gap, 1)
    misses.append(row)

mj = [m for m in misses if m.get("near_depth_pctile") is not None]
print(f"\n=== MISSES: n={len(misses)} (flow-joined {len(mj)}) ===")
OUT["miss_counts"] = {"n": len(misses), "joined": len(mj)}
# same median threshold as fills for comparability
fill_med = statistics.median([r["near_depth_pctile"] for r in fills
                              if r.get("near_depth_pctile") is not None])
lo_m = [m for m in mj if m["near_depth_pctile"] <= fill_med]
hi_m = [m for m in mj if m["near_depth_pctile"] > fill_med]
print(f"split at fills' median depth-pctile {fill_med:.3f}")
OUT["miss_buckets"] = {"split_at": round(fill_med, 3), "buckets": {}}
for label, seg in (("low(front-ish)", lo_m), ("high(back-ish)", hi_m)):
    sn = [m["sim_net"] for m in seg if m["sim_net"] is not None]
    b = {"n": len(seg), "sim_wr": round(sum(1 for x in sn if x > 0)/len(sn), 3) if sn else None,
         "sim_sum": round(sum(sn), 2) if sn else None,
         "sim_avg": round(statistics.mean(sn), 4) if sn else None,
         "small_sample": len(seg) < 20}
    OUT["miss_buckets"]["buckets"][label] = b
    print(f"  {label}: {b}")
ci = boot_diff([m["sim_net"] for m in hi_m if m["sim_net"] is not None],
               [m["sim_net"] for m in lo_m if m["sim_net"] is not None])
OUT["miss_buckets"]["hi_minus_lo_simnet"] = ci
if ci:
    print(f"  hi-lo miss sim_net: {ci['diff']:+.4f} 95% CI [{ci['ci_lo']:+.4f}, {ci['ci_hi']:+.4f}]")

# where do misses sit relative to fills on the depth pctile axis?
fp = [r["near_depth_pctile"] for r in fills if r.get("near_depth_pctile") is not None]
mp = [m["near_depth_pctile"] for m in mj]
ci_fm = boot_diff(mp, fp)
OUT["miss_vs_fill_depth_pctile"] = {"miss_mean": round(statistics.mean(mp), 3),
                                    "fill_mean": round(statistics.mean(fp), 3),
                                    "ci": ci_fm}
print(f"  depth-pctile: misses mean {statistics.mean(mp):.3f} vs fills {statistics.mean(fp):.3f}; "
      f"miss-fill diff {ci_fm['diff']:+.3f} CI [{ci_fm['ci_lo']:+.3f},{ci_fm['ci_hi']:+.3f}]")

# ---------- 6. rule sweep: skip posts when near_depth_pctile > X ----------
print("\n=== RULE SWEEP: skip post when near-side depth pctile > X ===")
sweep = []
for X in (0.5, 0.6, 0.7, 0.8, 0.9):
    kept = [r for r in fills if r.get("near_depth_pctile") is not None and r["near_depth_pctile"] <= X]
    cut = [r for r in fills if r.get("near_depth_pctile") is not None and r["near_depth_pctile"] > X]
    cut_m = [m for m in mj if m["near_depth_pctile"] > X]
    row = {"X": X, "fills_kept": len(kept), "kept_net": round(sum(r['net_pnl'] for r in kept), 2),
           "fills_cut": len(cut), "cut_net": round(sum(r['net_pnl'] for r in cut), 2),
           "cut_wr": round(sum(r['win'] for r in cut)/len(cut), 3) if cut else None,
           "misses_also_skipped": len(cut_m)}
    sweep.append(row)
    print(f"  X={X}: keep {row['fills_kept']} fills (net {row['kept_net']:+.2f}) | "
          f"cut {row['fills_cut']} fills (net {row['cut_net']:+.2f}, WR {row['cut_wr']}) | "
          f"{row['misses_also_skipped']} misses also skipped")
OUT["rule_sweep"] = sweep


from pathlib import Path as _P
_P("queue_study_out.json").write_text(json.dumps(OUT, indent=1, default=str))
print("\nwrote queue_study_out.json")
