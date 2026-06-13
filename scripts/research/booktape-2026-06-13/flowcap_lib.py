"""Shared loader for book x tape interaction study on flow_capture.jsonl.

Builds per-symbol sorted time series and computes forward mid-returns via
at-or-before lookup at a target horizon (no look-ahead).
"""
import json, bisect, math
from collections import defaultdict

DATA = "logs/flow_capture.jsonl"

def load(path=DATA):
    rows_by_sym = defaultdict(list)
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            ob = r.get("ob"); fl = r.get("flow")
            if ob is None or fl is None:
                continue
            imb = ob.get("imbalance")
            px = r.get("price")
            if imb is None or px is None or px <= 0:
                continue
            rows_by_sym[r["symbol"]].append({
                "ts": r["ts"],
                "px": px,
                "imb": imb,
                "spread_pct": ob.get("spread_pct"),
                "bid_walls": ob.get("bid_walls"),
                "ask_walls": ob.get("ask_walls"),
                "bid_depth": ob.get("bid_depth_usdt"),
                "ask_depth": ob.get("ask_depth_usdt"),
                "buy_ratio": fl.get("buy_ratio"),
                "cvd_slope": fl.get("cvd_slope"),
                "divergence": fl.get("divergence"),
                "ltb": fl.get("large_trade_bias"),
                "trade_count": fl.get("trade_count"),
            })
    for s in rows_by_sym:
        rows_by_sym[s].sort(key=lambda x: x["ts"])
    return rows_by_sym

def build_samples(rows_by_sym, horizons=(300, 900, 1800), max_gap_factor=2.0):
    """For each row, find forward price at-or-before (ts+H) within tolerance.

    Tolerance: the matched forward ts must be within [ts+H-tol, ts+H+tol] where
    tol = H (i.e. we accept the nearest at-or-before snapshot only if it lands
    in a reasonable window). We use at-or-before lookup then validate the gap.
    Returns list of dicts with fwd_ret_{H} keys (decimal, signed mid return).
    """
    samples = []
    for sym, rows in rows_by_sym.items():
        ts_list = [r["ts"] for r in rows]
        n = len(rows)
        for i, r in enumerate(rows):
            t0 = r["ts"]; p0 = r["px"]
            rec = dict(r); rec["symbol"] = sym
            ok_any = False
            for H in horizons:
                target = t0 + H
                # at-or-before lookup: largest ts <= target, but strictly after t0
                j = bisect.bisect_right(ts_list, target) - 1
                fr = None
                if j > i:  # must be a later snapshot
                    tj = ts_list[j]
                    # require matched ts within H of target (accept at-or-before window of size H)
                    if abs(tj - target) <= H:
                        pj = rows[j]["px"]
                        if pj > 0:
                            fr = (pj - p0) / p0
                            ok_any = True
                rec[f"fwd_{H}"] = fr
            if ok_any:
                samples.append(rec)
    return samples

def pearson(xs, ys):
    n = len(xs)
    if n < 3: return None
    mx = sum(xs)/n; my = sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs)
    syy = sum((y-my)**2 for y in ys)
    sxy = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    if sxx <= 0 or syy <= 0: return None
    return sxy/math.sqrt(sxx*syy)

def mean(xs):
    return sum(xs)/len(xs) if xs else float("nan")

def stats(xs):
    n = len(xs)
    if n == 0: return (float("nan"), float("nan"), 0)
    m = sum(xs)/n
    if n < 2: return (m, float("nan"), n)
    var = sum((x-m)**2 for x in xs)/(n-1)
    return (m, math.sqrt(var), n)

if __name__ == "__main__":
    rbs = load()
    print("symbols:", len(rbs), "total rows:", sum(len(v) for v in rbs.values()))
    samples = build_samples(rbs)
    print("samples with >=1 horizon:", len(samples))
    for H in (300,900,1800):
        c = sum(1 for s in samples if s.get(f"fwd_{H}") is not None)
        print(f"  fwd_{H}: {c}")
