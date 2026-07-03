#!/usr/bin/env python3
"""Queue-size-at-placement study (2026-07-03).

Research basis (deep-research, verified 3-0): front-of-queue maker fills mark
out ~13x better than back-of-queue fills (arxiv 2502.18625, live Binance perp
experiment). Question here: do OUR losing fills cluster on LARGE near-side
queue joins (back-of-queue) while winners/misses sit on small/fresh queues?

Part A (exact, tick symbols): reuses the fill/miss anchors from
reports/prefill_toxicity.json (12 fills / 11 misses, BTC/ETH/INJ/ARB). For each,
reads the l2_ticks book snapshot nearest the PLACEMENT estimate and extracts
the resting size at our limit price on our side, normalized by that symbol-day's
median touch size.

Part B (proxy, all symbols): every closed trade with an entry_snapshot
(signal-time ob.bid_depth_usdt / ask_depth_usdt = 5-level aggregate) — near-side
depth percentile WITHIN symbol vs win/loss. Coarser feature (5-level aggregate at
signal time, not touch queue at placement) but much larger n.

READ-ONLY vs bot. Screening-grade; n is small in Part A.
"""
import glob
import gzip
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOX = REPO / "reports" / "prefill_toxicity.json"
STATE = REPO / "trading_state.json"
TICKS = REPO / "logs" / "l2_ticks"
OUT = REPO / "reports" / "queue_at_placement.json"

PLACEMENT_BACKOFF_S = 20  # fills without a logged placement: assume worst-case
                          # full 20s rest (sensitivity: also computed at 10s)


def day_files(sym_dir, day):
    for ext in (".jsonl", ".jsonl.gz"):
        p = sym_dir / f"{day}{ext}"
        if p.exists():
            return p
    return None


def iter_books(path):
    op = gzip.open if str(path).endswith(".gz") else open
    with op(path, "rt") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if "b" in d and "a" in d:
                yield d


def load_day_books(symbol, ts):
    sym_dir = TICKS / symbol.replace("/", "_").replace(":", "_")
    day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    p = day_files(sym_dir, day)
    if not p:
        return []
    return [(d["ts"] / 1000.0, d) for d in iter_books(p)]


def size_at_px(book, side, px):
    """Resting size at our limit price (contracts). Falls back to the touch
    level if our exact price isn't a listed level (top-5 only)."""
    levels = book["b"] if side == "long" else book["a"]
    if not levels:
        return None, None
    for lpx, lsz in levels:
        if abs(float(lpx) - px) / px < 1e-6:
            return float(lsz), float(lpx)
    return float(levels[0][1]), float(levels[0][0])  # touch fallback


def nearest_book(books, target, tol=30.0):
    best, bd = None, tol
    for ts, d in books:
        dd = abs(ts - target)
        if dd < bd:
            best, bd = d, dd
    return best, bd


def part_a():
    tox = json.loads(TOX.read_text())
    rows = []
    day_medians = {}
    for kind in ("fills", "misses"):
        for r in tox[kind]:
            sym, side, px = r["symbol"], r["side"], r["limit_px"]
            placement = r.get("placement_ts")
            anchor = r["anchor_ts"]
            est = placement if placement else anchor - PLACEMENT_BACKOFF_S
            est10 = placement if placement else anchor - 10
            books = load_day_books(sym, est)
            if not books:
                rows.append({**_meta(r, kind), "covered": False})
                continue
            # symbol-day median touch size for normalization
            key = (sym, datetime.fromtimestamp(est, tz=timezone.utc).date())
            if key not in day_medians:
                sizes = [float((d["b"] if side == "long" else d["a"])[0][1])
                         for _, d in books[::max(1, len(books) // 500)]
                         if (d["b"] if side == "long" else d["a"])]
                day_medians[key] = statistics.median(sizes) if sizes else None
            med = day_medians[key]
            out = {**_meta(r, kind), "covered": True, "norm_med": med}
            for label, t in (("q20", est), ("q10", est10)):
                book, gap = nearest_book(books, t)
                if book is None:
                    out[label] = None
                    continue
                sz, lvl = size_at_px(book, side, px)
                out[label] = {
                    "size": sz, "size_usd": round(sz * px, 2) if sz else None,
                    "rel": round(sz / med, 3) if (sz and med) else None,
                    "snap_gap_s": round(gap, 2),
                    "at_exact_level": lvl is not None and abs(lvl - px) / px < 1e-6,
                }
            rows.append(out)
    return rows


def _meta(r, kind):
    return {"symbol": r["symbol"], "side": r["side"],
            "outcome": r.get("outcome") or kind[:-1],
            "net_pnl": r.get("net_pnl"), "limit_px": r["limit_px"],
            "log_matched_placement": bool(r.get("placement_ts"))}


def _flow_depth_index():
    """(ts, bid_depth, ask_depth) arrays per symbol from flow_capture.jsonl.
    Entry snapshots don't record depth; flow_capture (~80s cadence) does."""
    idx = defaultdict(lambda: ([], [], []))
    with open(REPO / "logs" / "flow_capture.jsonl") as fh:
        for line in fh:
            try:
                d = json.loads(line)
                ob = d.get("ob") or {}
                bd, ad = ob.get("bid_depth_usdt"), ob.get("ask_depth_usdt")
                if bd is None or ad is None:
                    continue
                ts_l, bd_l, ad_l = idx[d["symbol"]]
                ts_l.append(d["ts"]); bd_l.append(bd); ad_l.append(ad)
            except Exception:
                continue
    return idx


def part_b():
    import bisect
    state = json.loads(STATE.read_text())
    flow = _flow_depth_index()
    per_sym = defaultdict(list)
    trades = []
    for t in state.get("closed_trades", []):
        side = t.get("side")
        net = t.get("net_pnl")
        opened = t.get("opened_at")
        sym = t.get("symbol")
        if (net is None or not opened or sym not in flow
                or (t.get("exit_reason") or t.get("reason")) == "min_margin_skip"):
            continue
        ts_l, bd_l, ad_l = flow[sym]
        i = bisect.bisect_left(ts_l, opened)
        best, gap = None, 90.0
        for j in (i - 1, i):
            if 0 <= j < len(ts_l) and abs(ts_l[j] - opened) < gap:
                best, gap = j, abs(ts_l[j] - opened)
        if best is None:
            continue
        depth = bd_l[best] if side == "long" else ad_l[best]
        per_sym[sym].append(depth)
        trades.append({"symbol": sym, "side": side, "depth": depth,
                       "net": net, "opened_at": opened})
    # percentile within symbol (need >=8 obs for a meaningful rank)
    usable = []
    for tr in trades:
        pool = sorted(per_sym[tr["symbol"]])
        if len(pool) < 8:
            continue
        rank = sum(1 for x in pool if x <= tr["depth"]) / len(pool)
        usable.append({**tr, "depth_pctile": round(rank, 3)})
    return usable


def summarize(rows_a, rows_b):
    import numpy as np
    rng = np.random.default_rng(42)

    print("=== PART A: touch-queue size at placement (tick symbols, exact) ===")
    cov = [r for r in rows_a if r.get("covered")]
    print(f"covered {len(cov)}/{len(rows_a)} "
          f"(fills w/ logged placement: {sum(1 for r in cov if r['log_matched_placement'])})")
    groups = {"win": [], "loss": [], "miss": []}
    for r in cov:
        g = r["outcome"] if r["outcome"] in ("win", "loss", "miss") else (
            "win" if (r.get("net_pnl") or 0) > 0 else "loss")
        v = (r.get("q20") or {}).get("rel")
        if v is not None:
            groups[g].append(v)
    print(f"{'group':>6} {'n':>3} {'median rel-queue':>17} {'mean':>7}  (rel = size at our px / symbol-day median touch)")
    for g, vals in groups.items():
        if vals:
            print(f"{g:>6} {len(vals):>3} {statistics.median(vals):>17.2f} {sum(vals)/len(vals):>7.2f}")
    if groups["win"] and groups["loss"]:
        w, l = np.array(groups["win"]), np.array(groups["loss"])
        diffs = [l[rng.integers(0, len(l), len(l))].mean() -
                 w[rng.integers(0, len(w), len(w))].mean() for _ in range(5000)]
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        print(f"loss-minus-win mean rel-queue diff: {l.mean()-w.mean():+.2f}, 95% CI [{lo:+.2f}, {hi:+.2f}]")

    print("\n=== PART B: near-side 5-level depth percentile (all symbols, proxy) ===")
    wins = [r["depth_pctile"] for r in rows_b if r["net"] > 0]
    losses = [r["depth_pctile"] for r in rows_b if r["net"] < 0]
    print(f"n={len(rows_b)} usable ({len(wins)}W/{len(losses)}L)")
    if wins and losses:
        import numpy as np
        w, l = np.array(wins), np.array(losses)
        print(f"winners mean pctile {w.mean():.3f} | losers {l.mean():.3f}")
        diffs = [l[rng.integers(0, len(l), len(l))].mean() -
                 w[rng.integers(0, len(w), len(w))].mean() for _ in range(5000)]
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        print(f"loss-minus-win depth-pctile diff: {l.mean()-w.mean():+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}]")
        # quintile table
        print(f"{'depth quintile':>14} {'n':>4} {'WR%':>6} {'net$':>8}")
        allr = sorted(rows_b, key=lambda r: r["depth_pctile"])
        for i in range(5):
            seg = [r for r in rows_b if i / 5 <= r["depth_pctile"] < (i + 1) / 5 + (0.001 if i == 4 else 0)]
            if seg:
                sw = sum(1 for r in seg if r["net"] > 0)
                print(f"{f'{i*20}-{(i+1)*20}%':>14} {len(seg):>4} {sw/len(seg)*100:>5.1f} {sum(r['net'] for r in seg):>+8.2f}")


def main():
    rows_a = part_a()
    rows_b = part_b()
    summarize(rows_a, rows_b)
    OUT.write_text(json.dumps({"part_a": rows_a, "part_b": rows_b}, indent=1, default=str))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
