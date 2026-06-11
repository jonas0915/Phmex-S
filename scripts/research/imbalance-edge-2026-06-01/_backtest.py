import json, bisect, itertools, sys, time
from collections import defaultdict

def log(*a):
    print(*a)
    sys.stdout.flush()
_t0 = time.time()

PATH = "/Users/jonaspenaso/Desktop/Phmex-S/logs/flow_capture.jsonl"
FEE = 0.0012  # round-trip taker

# ---------- Load flow_capture, per-symbol time series ----------
series = defaultdict(lambda: {"ts": [], "px": [], "imb": []})
bad = 0
total = 0
with open(PATH) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        total += 1
        try:
            r = json.loads(line)
            sym = r["symbol"]
            ts = float(r["ts"])
            px = float(r["price"])
            imb = r["ob"]["imbalance"]
            if imb is None or px <= 0:
                bad += 1
                continue
            series[sym]["ts"].append(ts)
            series[sym]["px"].append(px)
            series[sym]["imb"].append(float(imb))
        except Exception:
            bad += 1

log(f"RECORDS total={total} bad/skipped={bad} symbols={len(series)}")

# ensure sorted by ts per symbol (data is interleaved but each symbol's records
# arrive in time order; sort defensively)
for sym, d in series.items():
    order = sorted(range(len(d["ts"])), key=lambda i: d["ts"][i])
    d["ts"] = [d["ts"][i] for i in order]
    d["px"] = [d["px"][i] for i in order]
    d["imb"] = [d["imb"][i] for i in order]

# global timeline split (chronological 50/50 by ts across ALL records)
all_ts = []
for d in series.values():
    all_ts.extend(d["ts"])
all_ts.sort()
t_min, t_max = all_ts[0], all_ts[-1]
mid_idx = len(all_ts) // 2
split_ts = all_ts[mid_idx]
span_hr = (t_max - t_min) / 3600.0
log(f"TIME span {span_hr:.1f}h  split_ts={split_ts}  ({(split_ts-t_min)/3600:.1f}h into data)")

for sym in sorted(series):
    d = series[sym]
    log(f"  {sym:20s} n={len(d['ts']):6d}")

# ---------- Helper: find price at-or-before a target ts within series ----------
def px_at_or_before(d, target_ts, start_hint=0):
    # returns (idx, price) of last record with ts <= target_ts, searching ts list
    ts = d["ts"]
    i = bisect.bisect_right(ts, target_ts) - 1
    if i < 0:
        return None
    return i, d["px"][i]

def px_step_forward(d, from_idx, entry_px, side, tp, sl, max_hold_s):
    # walk forward from from_idx+1 over records; entry at d at from_idx (ts0)
    ts = d["ts"]; px = d["px"]
    ts0 = ts[from_idx]
    deadline = ts0 + max_hold_s
    last_px = entry_px
    n = len(ts)
    j = from_idx + 1
    while j < n and ts[j] <= deadline:
        p = px[j]
        last_px = p
        if side == "long":
            ret = p / entry_px - 1.0
            if ret >= tp:
                return tp  # gross
            if ret <= -sl:
                return -sl
        else:  # short
            ret = entry_px / p - 1.0  # gain when price drops
            # equivalently -(p/entry-1)
            if ret >= tp:
                return tp
            if ret <= -sl:
                return -sl
        j += 1
    # neither hit -> exit at last price within hold (price at t+M, nearest stepping fwd)
    if side == "long":
        return last_px / entry_px - 1.0
    else:
        return entry_px / last_px - 1.0

# ---------- Precompute, for each symbol, the ret_prior series for each W ----------
Ws = [180, 300, 600]
PCTS = [90, 95]
THRS = [0.0, 0.1, 0.2]
TPS = [0.004, 0.006, 0.010]
SLS = [0.005, 0.008]
MS = [300, 900, 1800]

# For each (sym, W): compute ret_prior at each index i = px[i]/px(at ts[i]-W) - 1
# Then per-symbol percentile thresholds computed ON TRAIN ONLY.
def build_retprior(d, W):
    ts = d["ts"]; px = d["px"]
    out = []
    for i in range(len(ts)):
        target = ts[i] - W
        j = bisect.bisect_right(ts, target) - 1
        if j < 0:
            out.append(None)
            continue
        # require the prior point to be within reasonable window (W to 2*W back)
        if ts[i] - ts[j] > 2 * W:
            out.append(None)
            continue
        rp = px[i] / px[j] - 1.0
        out.append(rp)
    return out

retprior = {}  # (sym, W) -> list
for sym, d in series.items():
    for W in Ws:
        retprior[(sym, W)] = build_retprior(d, W)

def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac

# ---------- Trigger generation: for a given (W, pct), find setups per symbol/region ----------
# A trigger requires a cooldown so we don't fire every 2s during one dislocation.
# Use a per-symbol refractory period = W seconds between triggers of same direction.

def run_config(W, pct, thr, tp, sl, M, region):
    # region: 'train' or 'test' -> filter by entry ts
    trades = []  # list of (sym, side, net_ret)
    per_sym = defaultdict(lambda: [0, 0.0, 0])  # sym -> [n, sum_net, wins]
    for sym, d in series.items():
        ts = d["ts"]; px = d["px"]; imb = d["imb"]
        rp = retprior[(sym, W)]
        # train-only percentile thresholds
        train_vals = sorted(v for k, v in enumerate(rp)
                            if v is not None and ts[k] < split_ts)
        if len(train_vals) < 50:
            continue
        hi_thr = percentile(train_vals, pct)        # for SHORT (up spike)
        lo_thr = percentile(train_vals, 100 - pct)  # for LONG (down spike)
        last_trig_ts = -1e18
        for i in range(len(ts)):
            t = ts[i]
            in_region = (t < split_ts) if region == "train" else (t >= split_ts)
            if not in_region:
                continue
            v = rp[i]
            if v is None:
                continue
            side = None
            if v >= hi_thr:
                # up spike -> SHORT, require book leaning ask: imbalance <= -thr
                if imb[i] <= -thr:
                    side = "short"
            elif v <= lo_thr:
                # down spike -> LONG, require book leaning bid: imbalance >= +thr
                if imb[i] >= thr:
                    side = "long"
            if side is None:
                continue
            # refractory: at least W seconds since last trigger on this symbol
            if t - last_trig_ts < W:
                continue
            last_trig_ts = t
            entry_px = px[i]
            gross = px_step_forward(d, i, entry_px, side, tp, sl, M)
            net = gross - FEE
            trades.append((sym, side, net, gross))
            s = per_sym[sym]
            s[0] += 1
            s[1] += net
            if net > 0:
                s[2] += 1
    return trades, per_sym

# ---------- TRAIN sweep ----------
grid = list(itertools.product(Ws, PCTS, THRS, TPS, SLS, MS))
log(f"\nGRID size = {len(grid)} configs")

train_results = []
for (W, pct, thr, tp, sl, M) in grid:
    trades, per_sym = run_config(W, pct, thr, tp, sl, M, "train")
    n = len(trades)
    if n == 0:
        exp = 0.0
        wr = 0.0
        gross_exp = 0.0
    else:
        exp = sum(x[2] for x in trades) / n
        gross_exp = sum(x[3] for x in trades) / n
        wr = sum(1 for x in trades if x[2] > 0) / n
    train_results.append({
        "cfg": (W, pct, thr, tp, sl, M), "n": n, "exp": exp,
        "gross_exp": gross_exp, "wr": wr
    })

# eligible configs: n>=50 on train
eligible = [r for r in train_results if r["n"] >= 50]
log(f"Configs with n>=50 on TRAIN: {len(eligible)} / {len(grid)}")

# net-positive on train
train_pos = [r for r in eligible if r["exp"] > 0]
log(f"Configs net-positive on TRAIN (n>=50): {len(train_pos)}")

# pick best by net expectancy/trade
best = max(eligible, key=lambda r: r["exp"])
log(f"\nBEST TRAIN CONFIG (by net exp/trade, n>=50):")
W, pct, thr, tp, sl, M = best["cfg"]
log(f"  W={W}s pct={pct} thr={thr} TP={tp*100:.2f}% SL={sl*100:.2f}% M={M}s")
log(f"  TRAIN: n={best['n']} wr={best['wr']*100:.1f}% gross/trade={best['gross_exp']*100:.4f}% net/trade={best['exp']*100:.4f}%")

# ---------- TEST the exact best config ----------
trades, per_sym = run_config(W, pct, thr, tp, sl, M, "test")
n = len(trades)
if n > 0:
    exp = sum(x[2] for x in trades) / n
    gross_exp = sum(x[3] for x in trades) / n
    wr = sum(1 for x in trades if x[2] > 0) / n
    total_net = sum(x[2] for x in trades)
else:
    exp = gross_exp = wr = total_net = 0.0
log(f"\n=== HELD-OUT TEST (exact best config) ===")
log(f"  n={n} wr={wr*100:.1f}% gross/trade={gross_exp*100:.4f}% net/trade={exp*100:.4f}% total_net={total_net*100:.2f}%")
log(f"  per-symbol (n, net_total%, wr%):")
for sym in sorted(per_sym):
    s = per_sym[sym]
    if s[0] == 0:
        continue
    log(f"    {sym:20s} n={s[0]:4d} net_total={s[1]*100:8.2f}%  wr={s[2]/s[0]*100:5.1f}%")

# ---------- Overfit diagnostics: train-positive configs that stay positive on test ----------
# Compute test exp for each ELIGIBLE config (only those with train n>=50)
log(f"\n=== OVERFIT DIAGNOSTICS ===")
stay_pos = 0
checked = 0
test_exps_for_trainpos = []
for r in train_pos:
    cW, cpct, cthr, ctp, csl, cM = r["cfg"]
    tt, _ = run_config(cW, cpct, cthr, ctp, csl, cM, "test")
    if len(tt) == 0:
        te = 0.0
    else:
        te = sum(x[2] for x in tt) / len(tt)
    checked += 1
    test_exps_for_trainpos.append((r["cfg"], r["exp"], te, len(tt)))
    if te > 0:
        stay_pos += 1
log(f"  Train-positive configs (n>=50): {len(train_pos)}")
log(f"  ...of those, net-positive on TEST: {stay_pos}  ({stay_pos/max(1,len(train_pos))*100:.1f}%)")
log(f"  Overfit rate (train-pos but test<=0): {(len(train_pos)-stay_pos)/max(1,len(train_pos))*100:.1f}%")

# ---------- Gate vs no-gate: aggregate test expectancy across grid ----------
# For matched configs, compare thr=0 vs thr>0 on TEST
log(f"\n=== GATE MARGINAL VALUE (TEST set, all eligible configs) ===")
# Build test exp for every eligible config grouped by whether gated
gate_buckets = defaultdict(list)  # thr -> list of test exp (only configs eligible on train)
for r in eligible:
    cW, cpct, cthr, ctp, csl, cM = r["cfg"]
    tt, _ = run_config(cW, cpct, cthr, ctp, csl, cM, "test")
    if len(tt) == 0:
        continue
    te = sum(x[2] for x in tt) / len(tt)
    gate_buckets[cthr].append((te, len(tt)))
for thr_v in sorted(gate_buckets):
    rows = gate_buckets[thr_v]
    avg_exp = sum(e for e, _ in rows) / len(rows)
    tot_n = sum(nn for _, nn in rows)
    pos = sum(1 for e, _ in rows if e > 0)
    log(f"  thr={thr_v}: configs={len(rows):3d} avg_test_net/trade={avg_exp*100:8.4f}% total_test_trades={tot_n:6d} pct_pos={pos/len(rows)*100:.0f}%")

# Also a direct matched comparison: for each (W,pct,tp,sl,M), compare thr=0 vs thr=0.2 on TEST
log(f"\n  Matched pairs (same W,pct,TP,SL,M): thr=0 vs thr=0.2 on TEST net/trade:")
def test_exp(cfg):
    tt, _ = run_config(*cfg, "test")
    if len(tt) == 0:
        return None, 0
    return sum(x[2] for x in tt) / len(tt), len(tt)
diffs = []
for (cW, cpct, ctp, csl, cM) in itertools.product(Ws, PCTS, TPS, SLS, MS):
    e0, n0 = test_exp((cW, cpct, 0.0, ctp, csl, cM))
    e2, n2 = test_exp((cW, cpct, 0.2, ctp, csl, cM))
    if e0 is None or e2 is None or n0 < 20 or n2 < 20:
        continue
    diffs.append(e2 - e0)
if diffs:
    import statistics
    log(f"    pairs={len(diffs)} mean(gate0.2 - gate0)={statistics.mean(diffs)*100:.4f}%  median={statistics.median(diffs)*100:.4f}%  pct_gate_better={sum(1 for x in diffs if x>0)/len(diffs)*100:.0f}%")
