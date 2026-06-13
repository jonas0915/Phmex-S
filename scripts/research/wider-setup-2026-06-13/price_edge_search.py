#!/usr/bin/env python3
"""
Pure PRICE reversion/momentum OOS edge search.
Isolates the price-move trigger from order-book imbalance.

Discipline:
- Per-symbol percentile thresholds computed on TRAIN ONLY.
- Forward exit model with NO look-ahead (only ts <= target).
- Chronological 50/50 split by global ts.
- Select best config on TRAIN net expectancy, report that single config on TEST.
- Random baseline: 1000 draws, fraction beating the strategy = p-value.
"""
import json, collections, bisect, random
import numpy as np

DATA = 'logs/flow_capture.jsonl'

LOOKBACKS = [180, 300, 600, 900]      # W seconds
PCTILES   = [90.0, 95.0, 97.5]
MAX_HOLDS = [300, 900, 1800]          # seconds
TPS       = [0.004, 0.006, 0.010]     # 0.4 / 0.6 / 1.0 %
SLS       = [0.005, 0.008]            # 0.5 / 0.8 %
DIRS      = ['revert', 'momentum']

FEE_MEASURED = 0.000663   # 0.0663% RT
FEE_TAKER    = 0.0012     # 0.12% RT conservative

random.seed(42)
np.random.seed(42)

# ---------------------------------------------------------------
# Load
# ---------------------------------------------------------------
def load():
    by_sym = collections.defaultdict(list)  # symbol -> list of (ts, price)
    with open(DATA) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            p = r.get('price')
            if p is None or p <= 0:
                continue
            by_sym[r['symbol']].append((r['ts'], float(p)))
    # sort + dedup by ts (keep last for identical ts)
    clean = {}
    for s, rows in by_sym.items():
        rows.sort(key=lambda x: x[0])
        ts = [rows[0][0]]; px = [rows[0][1]]
        for t, p in rows[1:]:
            if t == ts[-1]:
                px[-1] = p
            else:
                ts.append(t); px.append(p)
        clean[s] = (np.array(ts, dtype=np.int64), np.array(px, dtype=np.float64))
    return clean

# ---------------------------------------------------------------
# ret_prior at index i for lookback W: price[i]/price(at-or-before ts[i]-W) - 1
# ---------------------------------------------------------------
def compute_ret_prior(ts, px, W):
    n = len(ts)
    ret = np.full(n, np.nan)
    for i in range(n):
        target = ts[i] - W
        # rightmost index j with ts[j] <= target
        j = bisect.bisect_right(ts, target) - 1
        if j < 0:
            continue
        # require the prior point be within a reasonable window (not too stale)
        # allow up to 2*W staleness so sparse symbols still trigger, but be honest
        if ts[i] - ts[j] > 2 * W + 120:
            continue
        ret[i] = px[i] / px[j] - 1.0
    return ret

# ---------------------------------------------------------------
# Exit model: from trigger index, walk forward up to max_hold.
# side = +1 long, -1 short. Returns gross return fraction (signed for the position).
# ---------------------------------------------------------------
def simulate_exit(ts, px, i, side, max_hold, tp, sl):
    entry = px[i]
    deadline = ts[i] + max_hold
    last = entry
    n = len(ts)
    j = i + 1
    while j < n and ts[j] <= deadline:
        p = px[j]
        last = p
        move = side * (p / entry - 1.0)   # signed PnL fraction in position direction
        if move >= tp:
            return tp
        if move <= -sl:
            return -sl
        j += 1
    # else exit at last price within window
    return side * (last / entry - 1.0)

# ---------------------------------------------------------------
# Generate triggers for a symbol given config, using threshold thr (abs ret_prior).
# Returns list of (entry_index, side). Refractory = W.
# ---------------------------------------------------------------
def gen_triggers(ts, ret, W, thr, direction, idx_lo, idx_hi):
    trigs = []
    last_trig_ts = -10**18
    n = len(ts)
    for i in range(idx_lo, idx_hi):
        r = ret[i]
        if np.isnan(r):
            continue
        if abs(r) < thr:
            continue
        if ts[i] - last_trig_ts < W:
            continue
        # direction of the move
        move_up = r > 0
        if direction == 'revert':
            side = -1 if move_up else +1   # fade the move
        else:  # momentum
            side = +1 if move_up else -1   # follow the move
        trigs.append((i, side))
        last_trig_ts = ts[i]
    return trigs

# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
def main():
    clean = load()
    syms = sorted(clean.keys())
    # global ts midpoint for chronological 50/50 split
    all_ts = np.concatenate([clean[s][0] for s in syms])
    split_ts = int(np.median(all_ts))
    tmin, tmax = int(all_ts.min()), int(all_ts.max())
    train_days = (split_ts - tmin) / 86400.0
    test_days  = (tmax - split_ts) / 86400.0
    print(f"# rows total: {len(all_ts)}  symbols: {len(syms)}")
    print(f"# split_ts={split_ts}  TRAIN days={train_days:.2f}  TEST days={test_days:.2f}")
    print()

    # Precompute ret_prior per (symbol, W). Also per-symbol index boundaries for train/test.
    ret_cache = {}   # (sym, W) -> ret array
    bound = {}       # sym -> (n, split_index)  where rows [0:split_index) train, [split_index:n) test
    for s in syms:
        ts, px = clean[s]
        n = len(ts)
        si = bisect.bisect_left(ts, split_ts)  # first test index
        bound[s] = (n, si)
        for W in LOOKBACKS:
            ret_cache[(s, W)] = compute_ret_prior(ts, px, W)

    # Per-symbol TRAIN threshold for (W, pctile): percentile of |ret_prior| over TRAIN rows
    def thr_for(s, W, pct):
        n, si = bound[s]
        ret = ret_cache[(s, W)]
        train_ret = ret[:si]
        vals = np.abs(train_ret[~np.isnan(train_ret)])
        if len(vals) < 20:
            return None
        return np.percentile(vals, pct)

    # Evaluate a full config across all symbols on a given segment ('train' or 'test')
    def eval_config(W, pct, direction, max_hold, tp, sl, segment):
        rets = []
        for s in syms:
            ts, px = clean[s]
            n, si = bound[s]
            thr = thr_for(s, W, pct)
            if thr is None:
                continue
            ret = ret_cache[(s, W)]
            if segment == 'train':
                lo, hi = 0, si
            else:
                lo, hi = si, n
            trigs = gen_triggers(ts, ret, W, thr, direction, lo, hi)
            for i, side in trigs:
                g = simulate_exit(ts, px, i, side, max_hold, tp, sl)
                rets.append(g)
        return np.array(rets)

    # ---- TRAIN: grid search, select best per direction by net expectancy (measured fee)
    print("# ===== TRAIN grid search (net @ measured fee 0.0663%) =====")
    best = {'revert': None, 'momentum': None}
    for direction in DIRS:
        results = []
        for W in LOOKBACKS:
            for pct in PCTILES:
                for max_hold in MAX_HOLDS:
                    for tp in TPS:
                        for sl in SLS:
                            g = eval_config(W, pct, direction, max_hold, tp, sl, 'train')
                            if len(g) < 30:   # need a minimum sample
                                continue
                            gross = g.mean()
                            net_m = gross - FEE_MEASURED
                            cfg = dict(W=W, pct=pct, dir=direction, max_hold=max_hold,
                                       tp=tp, sl=sl, n=len(g), gross=gross,
                                       net_m=net_m, wr=float((g > 0).mean()))
                            results.append(cfg)
        results.sort(key=lambda c: c['net_m'], reverse=True)
        if results:
            best[direction] = results[0]
            print(f"\n## {direction}: top 5 TRAIN configs by net/trade (measured fee)")
            for c in results[:5]:
                print(f"   W={c['W']} pct={c['pct']} hold={c['max_hold']} "
                      f"tp={c['tp']*100:.1f}% sl={c['sl']*100:.1f}% | n={c['n']} "
                      f"gross={c['gross']*100:+.4f}% net={c['net_m']*100:+.4f}% wr={c['wr']*100:.1f}%")
        else:
            print(f"\n## {direction}: NO config met min sample on TRAIN")

    # ---- TEST: evaluate the single selected config, full fee accounting + random baseline
    print("\n\n# ===== TEST (held-out) for selected configs =====")
    for direction in DIRS:
        c = best[direction]
        if c is None:
            print(f"\n## {direction}: no selected config")
            continue
        g = eval_config(c['W'], c['pct'], direction, c['max_hold'], c['tp'], c['sl'], 'test')
        n = len(g)
        print(f"\n## {direction} SELECTED config: "
              f"W={c['W']} pct={c['pct']} hold={c['max_hold']} "
              f"tp={c['tp']*100:.1f}% sl={c['sl']*100:.1f}%")
        print(f"   TRAIN: n={c['n']}  net/trade(meas)={c['net_m']*100:+.4f}%  wr={c['wr']*100:.1f}%")
        if n < 10:
            print(f"   TEST: only n={n} triggers -- too few, NO RELIABLE EDGE")
            continue
        gross = g.mean()
        net_m = gross - FEE_MEASURED
        net_t = gross - FEE_TAKER
        wr = float((g > 0).mean())
        trig_per_day = n / test_days
        print(f"   TEST:  n={n}  triggers/day={trig_per_day:.2f}")
        print(f"          GROSS net/trade = {gross*100:+.4f}%")
        print(f"          NET @ measured 0.0663% = {net_m*100:+.4f}%/trade  (total {net_m*n*100:+.2f}%)")
        print(f"          NET @ taker    0.12%   = {net_t*100:+.4f}%/trade  (total {net_t*n*100:+.2f}%)")
        print(f"          WR = {wr*100:.1f}%")

        # ---- Random baseline: same n entries drawn from TEST snapshots, same exit model
        # Build pool of (sym, index, ts) for all TEST snapshots that have a forward window.
        pool = []
        for s in syms:
            ts, px = clean[s]
            nn, si = bound[s]
            for i in range(si, nn):
                pool.append((s, i))
        beats = 0
        rand_means = []
        for _ in range(1000):
            picks = random.sample(pool, min(n, len(pool)))
            rr = []
            for s, i in picks:
                ts, px = clean[s]
                side = random.choice([+1, -1])
                rr.append(simulate_exit(ts, px, i, side, c['max_hold'], c['tp'], c['sl']))
            rm = np.mean(rr) - FEE_MEASURED
            rand_means.append(rm)
            if rm >= net_m:
                beats += 1
        rand_means = np.array(rand_means)
        pval = beats / 1000.0
        print(f"          RANDOM baseline (1000 draws, n={n}, same exit, measured fee):")
        print(f"            random net/trade mean={rand_means.mean()*100:+.4f}%  "
              f"p5={np.percentile(rand_means,5)*100:+.4f}%  p95={np.percentile(rand_means,95)*100:+.4f}%")
        print(f"            fraction of random draws beating strategy (p-value) = {pval:.3f}")
        verdict = "EDGE candidate" if (net_m > 0 and pval < 0.05) else "NO EDGE"
        print(f"          VERDICT: {verdict}")

    # ---- current cadence reference
    print("\n# (current live setup triggers ~2-4/day per the brief)")

if __name__ == '__main__':
    main()
