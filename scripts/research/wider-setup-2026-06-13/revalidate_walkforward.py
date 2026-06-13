#!/usr/bin/env python3
"""
Robustness re-test of the short-horizon MEAN REVERSION lead.

Re-uses logic from xsymbol_divergence.py (alt-vs-ETH cross-symbol reversion)
and volregime_highvol_focus.py (high-vol reversion) -- but instead of ONE
chronological 50/50 split, it slices the ~33-day span into K sequential folds
and asks: is the reversion edge TIME-STABLE or REGIME-LUCK?

Read-only on logs/flow_capture.jsonl. No live code touched. NEVER fabricate --
every number printed is computed here from the raw file.

Outputs:
 1. Per-fold gross + maker-net table for BOTH reversion families (K=4 and K=6).
 2. Walk-forward OOS: pick params on folds 1..n-1, test on fold n, rolling.
 3. Parameter sensitivity grid on a held-out fold.
 4. Per-fold direction-shuffle control (scramble long/short) -> p-value.
 5. Triggers/day per fold.

Fee conventions (round-trip, fraction of notional):
  taker     0.0012    (0.12% RT)
  maker_rt  0.000663  (0.0663% RT -- the spec's "maker" round-trip number)
  maker2    0.0002    (0.01%/side * 2 = 0.02% RT, true maker-maker round trip)
"""
import json, sys, os, bisect, random, statistics, datetime as dt
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))

DATA = "logs/flow_capture.jsonl"
ALIGN_TOL = 150          # seconds tolerance for at-or-before alignment
ANCHOR_SYM = "ETH/USDT:USDT"   # ETH-anchor (BTC anchor was null, only ~9d data)

FEE_TAKER = 0.0012
FEE_MAKER_RT = 0.000663
FEE_MAKER2 = 0.0002

random.seed(42)
N_SHUFFLE = 1000

# ---------------- load ----------------
def load():
    series = defaultdict(list)   # symbol -> [(ts, price)]
    with open(DATA) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            p = d.get("price")
            ts = d.get("ts")
            if p is None or ts is None or p <= 0:
                continue
            series[d["symbol"]].append((ts, float(p)))
    for s in series:
        series[s].sort(key=lambda x: x[0])
    return series

SERIES = load()
if ANCHOR_SYM not in SERIES:
    print("anchor not found"); sys.exit(1)
ANCHOR_TS = [t for t, _ in SERIES[ANCHOR_SYM]]
ANCHOR_PX = [p for _, p in SERIES[ANCHOR_SYM]]

ALTS = [s for s in SERIES if s != ANCHOR_SYM and len(SERIES[s]) >= 200]
all_alt_ts = []
for s in ALTS:
    all_alt_ts.extend(t for t, _ in SERIES[s])
all_alt_ts.sort()
T0, T1 = all_alt_ts[0], all_alt_ts[-1]
SPAN_DAYS = (T1 - T0) / 86400.0

def fmt(t): return dt.datetime.fromtimestamp(t, tz=dt.timezone.utc).strftime("%m-%d %H:%M")

# ---------------- shared primitives ----------------
def at_or_before(ts_list, px_list, target, tol=ALIGN_TOL):
    i = bisect.bisect_right(ts_list, target) - 1
    if i < 0:
        return None
    if target - ts_list[i] > tol:
        return None
    return px_list[i]

def anchor_ret(t_now, W):
    p_now = at_or_before(ANCHOR_TS, ANCHOR_PX, t_now)
    p_past = at_or_before(ANCHOR_TS, ANCHOR_PX, t_now - W)
    if p_now is None or p_past is None:
        return None
    return p_now / p_past - 1.0

def forward_exit(ts_list, px_list, entry_ts, entry_price, side, max_hold, tp, sl):
    """Walk forward from entry. side=+1 long,-1 short. Gross signed return."""
    i = bisect.bisect_right(ts_list, entry_ts)
    end = entry_ts + max_hold
    last_p = entry_price
    n = len(ts_list)
    while i < n and ts_list[i] <= end:
        p = px_list[i]; last_p = p
        ret = side * (p / entry_price - 1.0)
        if ret >= tp:
            return tp
        if ret <= -sl:
            return -sl
        i += 1
    return side * (last_p / entry_price - 1.0)

# ---------------- fold boundaries ----------------
def fold_bounds(K):
    """K equal-time sequential folds across [T0, T1]. Returns list of (lo, hi)."""
    step = (T1 - T0) / K
    bounds = []
    for k in range(K):
        lo = T0 + k * step
        hi = T1 + 1 if k == K - 1 else T0 + (k + 1) * step
        bounds.append((lo, hi))
    return bounds

def which_fold(ts, bounds):
    for k, (lo, hi) in enumerate(bounds):
        if lo <= ts < hi:
            return k
    return None

# ======================================================================
# FAMILY A: alt-vs-ETH cross-symbol divergence reversion
# ======================================================================
def buildA_signals(W, beta=1.0):
    """{sym: [(ts, price, divergence)]} -- alt trailing ret minus beta*anchor ret."""
    out = {}
    for sym in ALTS:
        s = SERIES[sym]
        ts = [t for t, _ in s]; px = [p for _, p in s]
        sigs = []
        for i in range(len(s)):
            t_now = ts[i]; p_now = px[i]
            p_past = at_or_before(ts, px, t_now - W)
            if p_past is None:
                continue
            ar = p_now / p_past - 1.0
            br = anchor_ret(t_now, W)
            if br is None:
                continue
            sigs.append((t_now, p_now, ar - beta * br))
        out[sym] = sigs
    return out

def runA_fold(sigsA, W, pct, max_hold, tp, sl, thr_lo, thr_hi, test_lo, test_hi,
              shuffle=False):
    """Reversion trades whose ENTRY ts is in [test_lo,test_hi).
    Threshold = per-symbol pct-ile of |div| computed on the THRESHOLD window
    [thr_lo,thr_hi) (the in-sample folds), strict no-look-ahead.
    shuffle=True scrambles long/short side (direction control)."""
    rets = []
    for sym, sigs in sigsA.items():
        thr_divs = [abs(d) for (t, p, d) in sigs if thr_lo <= t < thr_hi]
        if len(thr_divs) < 30:
            continue
        thr_divs.sort()
        thr = thr_divs[min(len(thr_divs) - 1, int(len(thr_divs) * pct / 100.0))]
        if thr <= 0:
            continue
        s = SERIES[sym]; ts = [t for t, _ in s]; px = [p for _, p in s]
        last_entry = -1e18
        for (t, p, d) in sigs:
            if not (test_lo <= t < test_hi):
                continue
            if abs(d) < thr:
                continue
            if t - last_entry < W:
                continue
            if shuffle:
                side = random.choice([+1, -1])
            else:
                side = -1 if d > 0 else +1   # reversion: fade the divergence
            rets.append(forward_exit(ts, px, t, p, side, max_hold, tp, sl))
            last_entry = t
    return rets

# ======================================================================
# FAMILY B: high-vol reversion (fade trailing return when vol is high)
# ======================================================================
def buildB_cands(vol_window, prior_window, max_horizon):
    """[ {ts, rv, rp, ep, ts_list, px_list, idx} ] per snapshot with valid features."""
    cands = []
    for sym in ALTS + [ANCHOR_SYM]:
        s = SERIES[sym]
        ts = [t for t, _ in s]; px = [p for _, p in s]
        n = len(s)
        for i in range(n):
            t_now = ts[i]
            # realized vol over trailing vol_window
            lo = t_now - vol_window
            k = bisect.bisect_left(ts, lo, 0, i + 1)
            seg = px[k:i + 1]
            if len(seg) < 4:
                continue
            rr = []
            for a in range(1, len(seg)):
                if seg[a - 1] > 0:
                    rr.append((seg[a] - seg[a - 1]) / seg[a - 1])
            if len(rr) < 3:
                continue
            m = sum(rr) / len(rr)
            rv = (sum((x - m) ** 2 for x in rr) / (len(rr) - 1)) ** 0.5
            # prior return over prior_window
            lo2 = t_now - prior_window
            k2 = bisect.bisect_left(ts, lo2, 0, i + 1)
            if k2 >= i:
                continue
            p0 = px[k2]
            if p0 <= 0:
                continue
            rp = px[i] / p0 - 1.0
            cands.append({"ts": t_now, "rv": rv, "rp": rp, "ep": px[i],
                          "ts_list": ts, "px_list": px, "idx": i})
    return cands

def quant(vals, qq):
    s = sorted(vals)
    return s[min(len(s) - 1, int(qq * len(s)))]

# ---- FAST shuffle support ----
# For each triggered trade, precompute BOTH the long return and the short return
# (TP/SL caps are NOT symmetric under a side flip, so we must run forward_exit
# for each side). Then a direction-shuffle just picks long_ret or short_ret per
# trade -- exact, no re-scan, no threshold recompute.
def triggersA(sigsA, W, pct, max_hold, tp, sl, thr_lo, thr_hi, test_lo, test_hi):
    """Returns (rev_rets, pairs) where rev_rets is the reversion-direction return
    list and pairs is [(long_ret, short_ret)] for shuffle control."""
    rev_rets = []; pairs = []
    for sym, sigs in sigsA.items():
        thr_divs = [abs(d) for (t, p, d) in sigs if thr_lo <= t < thr_hi]
        if len(thr_divs) < 30:
            continue
        thr_divs.sort()
        thr = thr_divs[min(len(thr_divs) - 1, int(len(thr_divs) * pct / 100.0))]
        if thr <= 0:
            continue
        s = SERIES[sym]; ts = [t for t, _ in s]; px = [p for _, p in s]
        last_entry = -1e18
        for (t, p, d) in sigs:
            if not (test_lo <= t < test_hi):
                continue
            if abs(d) < thr:
                continue
            if t - last_entry < W:
                continue
            lr = forward_exit(ts, px, t, p, +1, max_hold, tp, sl)
            sr = forward_exit(ts, px, t, p, -1, max_hold, tp, sl)
            rev = sr if d > 0 else lr   # reversion: fade
            rev_rets.append(rev); pairs.append((lr, sr))
            last_entry = t
    return rev_rets, pairs

def triggersB(candsB, rv_q, rp_q, max_hold, tp, sl, thr_lo, thr_hi, test_lo, test_hi):
    insample = [c for c in candsB if thr_lo <= c["ts"] < thr_hi]
    if len(insample) < 50:
        return [], []
    rv_thr = quant([c["rv"] for c in insample], rv_q)
    rp_thr = quant([abs(c["rp"]) for c in insample], rp_q)
    rev_rets = []; pairs = []
    for c in candsB:
        if not (test_lo <= c["ts"] < test_hi):
            continue
        if c["rv"] < rv_thr or abs(c["rp"]) < rp_thr:
            continue
        lr = forward_exit(c["ts_list"], c["px_list"], c["ts"], c["ep"], +1, max_hold, tp, sl)
        sr = forward_exit(c["ts_list"], c["px_list"], c["ts"], c["ep"], -1, max_hold, tp, sl)
        rev = sr if c["rp"] > 0 else lr
        rev_rets.append(rev); pairs.append((lr, sr))
    return rev_rets, pairs

def shuffle_p_from_pairs(real_gross, pairs):
    """Direction-shuffle control: for each trade randomly pick long or short
    return; p = frac of shuffles whose mean gross >= real reversion gross."""
    if not pairs:
        return float("nan")
    beats = 0
    n = len(pairs)
    for _ in range(N_SHUFFLE):
        tot = 0.0
        for lr, sr in pairs:
            tot += lr if random.random() < 0.5 else sr
        if tot / n >= real_gross:
            beats += 1
    return beats / N_SHUFFLE

def runB_fold(candsB, rv_q, rp_q, max_hold, tp, sl, thr_lo, thr_hi,
              test_lo, test_hi, shuffle=False):
    """High-vol reversion. Thresholds (rv pct, |rp| pct) computed on
    [thr_lo,thr_hi); trades whose ts in [test_lo,test_hi)."""
    insample = [c for c in candsB if thr_lo <= c["ts"] < thr_hi]
    if len(insample) < 50:
        return []
    rv_thr = quant([c["rv"] for c in insample], rv_q)
    rp_thr = quant([abs(c["rp"]) for c in insample], rp_q)
    rets = []
    for c in candsB:
        if not (test_lo <= c["ts"] < test_hi):
            continue
        if c["rv"] < rv_thr or abs(c["rp"]) < rp_thr:
            continue
        if shuffle:
            side = random.choice([+1, -1])
        else:
            side = -1 if c["rp"] > 0 else +1   # fade prior move
        rets.append(forward_exit(c["ts_list"], c["px_list"], c["ts"], c["ep"],
                                 side, max_hold, tp, sl))
    return rets

# ---------------- reporting helpers ----------------
def summarize(rets, days):
    if not rets:
        return None
    n = len(rets)
    gross = statistics.mean(rets)
    wr = sum(1 for r in rets if r > 0) / n
    return {
        "n": n, "gross": gross, "wr": wr,
        "net_taker": gross - FEE_TAKER,
        "net_makerrt": gross - FEE_MAKER_RT,
        "net_maker2": gross - FEE_MAKER2,
        "tpd": n / days if days > 0 else 0,
    }

def shuffle_pvalue(run_fn):
    """run_fn() -> list of rets with shuffle=True. Returns frac of shuffles whose
    mean gross >= real (real computed separately by caller)."""
    means = []
    for _ in range(N_SHUFFLE):
        r = run_fn()
        if r:
            means.append(statistics.mean(r))
    return means

# ======================================================================
# MAIN
# ======================================================================
# Config family A: the alt-vs-ETH reversion config from prior lead.
# Prior best-ish region: W=600, pct=95, max_hold=900, tp=0.006, sl=0.008
A_CFG = dict(W=600, pct=95, max_hold=900, tp=0.006, sl=0.008)
# Config family B: high-vol reversion baseline from volregime_highvol_focus.py
B_CFG = dict(vol_window=900, prior_window=900, max_horizon=1800,
             rv_q=2/3, rp_q=0.95, max_hold=1800, tp=0.006, sl=0.008)

print("=" * 78)
print("ROBUSTNESS RE-TEST: short-horizon MEAN REVERSION (walk-forward / K folds)")
print("=" * 78)
print(f"data span: {fmt(T0)} .. {fmt(T1)} UTC  ({SPAN_DAYS:.1f} days)")
print(f"anchor: {ANCHOR_SYM}  alts: {len(ALTS)}")
print(f"NOTE: BTC-anchor excluded -- BTC has only ~9 days of data (prior null).")
print(f"fees RT: taker={FEE_TAKER} maker_rt={FEE_MAKER_RT} maker2(0.02%)={FEE_MAKER2}")
print(f"Family A (alt-vs-ETH reversion) cfg: {A_CFG}")
print(f"Family B (high-vol reversion)   cfg: {B_CFG}")

# Pre-build signals/cands once (expensive)
print("\n[building Family A signals ...]", flush=True)
SIGS_A = buildA_signals(A_CFG["W"])
print("[building Family B candidates ...]", flush=True)
CANDS_B = buildB_cands(B_CFG["vol_window"], B_CFG["prior_window"], B_CFG["max_horizon"])
print(f"[Family B candidate snapshots: {len(CANDS_B)}]", flush=True)

def per_fold_report(K):
    bounds = fold_bounds(K)
    fold_days = SPAN_DAYS / K
    print("\n" + "#" * 78)
    print(f"### K={K} SEQUENTIAL FOLDS  (~{fold_days:.1f} days each)")
    print("#" * 78)
    for k, (lo, hi) in enumerate(bounds):
        print(f"  fold {k+1}: {fmt(lo)} .. {fmt(hi if hi <= T1 else T1)}")

    # ---- Per-fold in-sample-threshold from same fold (descriptive: is gross
    #      signal present in EACH window?). Threshold computed on the fold itself.
    for fam, label in (("A", "Family A: alt-vs-ETH reversion"),
                       ("B", "Family B: high-vol reversion")):
        print(f"\n--- {label} | per-fold (threshold from same fold) ---")
        print(f"{'fold':>4} {'n':>5} {'tpd':>6} {'gross%':>9} {'wr%':>6} "
              f"{'net_taker%':>11} {'net_makerRT%':>13} {'net_maker2%':>12} {'shuf_p':>7}")
        signs = []
        for k, (lo, hi) in enumerate(bounds):
            if fam == "A":
                rets, pairs = triggersA(SIGS_A, A_CFG["W"], A_CFG["pct"],
                                        A_CFG["max_hold"], A_CFG["tp"], A_CFG["sl"],
                                        lo, hi, lo, hi)
            else:
                rets, pairs = triggersB(CANDS_B, B_CFG["rv_q"], B_CFG["rp_q"],
                                        B_CFG["max_hold"], B_CFG["tp"], B_CFG["sl"],
                                        lo, hi, lo, hi)
            st = summarize(rets, fold_days)
            if not st:
                print(f"{k+1:>4} {'--':>5}  (no triggers)")
                continue
            p = shuffle_p_from_pairs(st["gross"], pairs)
            signs.append(1 if st["net_makerrt"] > 0 else (-1 if st["net_makerrt"] < 0 else 0))
            print(f"{k+1:>4} {st['n']:>5} {st['tpd']:>6.1f} {st['gross']*100:>8.4f}% "
                  f"{st['wr']*100:>5.1f}% {st['net_taker']*100:>10.4f}% "
                  f"{st['net_makerrt']*100:>12.4f}% {st['net_maker2']*100:>11.4f}% {p:>7.3f}")
        pos = sum(1 for s in signs if s > 0); neg = sum(1 for s in signs if s < 0)
        print(f"   -> maker_rt net sign: {pos} positive / {neg} negative folds (of {len(signs)})")

def walk_forward(K):
    """Pick best params on folds 1..n-1 (pooled in-sample), test on fold n.
    Search a small grid per family; selection metric = pooled gross mean
    (fee-agnostic edge) requiring >= 15 in-sample triggers."""
    bounds = fold_bounds(K)
    fold_days = SPAN_DAYS / K
    print("\n" + "#" * 78)
    print(f"### WALK-FORWARD OOS  (K={K}: train folds 1..n-1, test fold n)")
    print("#" * 78)

    # small selection grids
    A_GRID = [dict(W=600, pct=p, max_hold=mh, tp=tp, sl=sl)
              for p in (90, 95) for mh in (600, 900) for tp in (0.004, 0.006)
              for sl in (0.005, 0.008)]
    B_GRID = [dict(rv_q=rq, rp_q=pq, max_hold=mh, tp=tp, sl=sl)
              for rq in (0.5, 2/3) for pq in (0.90, 0.95) for mh in (900, 1800)
              for tp in (0.004, 0.006) for sl in (0.005, 0.008)]

    for fam, label in (("A", "Family A: alt-vs-ETH reversion"),
                       ("B", "Family B: high-vol reversion")):
        print(f"\n--- {label} | walk-forward OOS ---")
        print(f"{'test_fold':>9} {'picked_cfg':>34} {'is_gross%':>10} "
              f"{'oos_n':>6} {'oos_gross%':>11} {'oos_netRT%':>11} {'oos_net2%':>10} {'oos_wr%':>7}")
        oos_rt = []
        for n in range(1, K):   # test fold index n (0-based: folds[n]); train = folds[0..n-1]
            train_lo = bounds[0][0]; train_hi = bounds[n - 1][1]   # folds 1..n
            test_lo, test_hi = bounds[n]
            # select best cfg on train (in-sample = entries within train window,
            # threshold also from train window)
            best = None
            grid = A_GRID if fam == "A" else B_GRID
            for cfg in grid:
                if fam == "A":
                    isr = runA_fold(SIGS_A, cfg["W"], cfg["pct"], cfg["max_hold"],
                                    cfg["tp"], cfg["sl"], train_lo, train_hi,
                                    train_lo, train_hi)
                else:
                    isr = runB_fold(CANDS_B, cfg["rv_q"], cfg["rp_q"], cfg["max_hold"],
                                    cfg["tp"], cfg["sl"], train_lo, train_hi,
                                    train_lo, train_hi)
                if len(isr) < 15:
                    continue
                g = statistics.mean(isr)
                if best is None or g > best[1]:
                    best = (cfg, g)
            if best is None:
                print(f"{n+1:>9}   (no cfg with >=15 IS triggers)")
                continue
            cfg, isg = best
            # OOS: threshold from TRAIN window, entries in TEST fold (no look-ahead)
            if fam == "A":
                oos = runA_fold(SIGS_A, cfg["W"], cfg["pct"], cfg["max_hold"],
                                cfg["tp"], cfg["sl"], train_lo, train_hi,
                                test_lo, test_hi)
                cfgstr = f"W{cfg['W']} p{cfg['pct']} mh{cfg['max_hold']} tp{cfg['tp']} sl{cfg['sl']}"
            else:
                oos = runB_fold(CANDS_B, cfg["rv_q"], cfg["rp_q"], cfg["max_hold"],
                                cfg["tp"], cfg["sl"], train_lo, train_hi,
                                test_lo, test_hi)
                cfgstr = f"rvq{cfg['rv_q']:.2f} rpq{cfg['rp_q']} mh{cfg['max_hold']} tp{cfg['tp']} sl{cfg['sl']}"
            st = summarize(oos, fold_days)
            if not st:
                print(f"{n+1:>9} {cfgstr:>34} {isg*100:>9.4f}%   (no OOS triggers)")
                continue
            oos_rt.append(st["net_makerrt"])
            print(f"{n+1:>9} {cfgstr:>34} {isg*100:>9.4f}% {st['n']:>6} "
                  f"{st['gross']*100:>10.4f}% {st['net_makerrt']*100:>10.4f}% "
                  f"{st['net_maker2']*100:>9.4f}% {st['wr']*100:>6.1f}%")
        if oos_rt:
            pos = sum(1 for x in oos_rt if x > 0)
            print(f"   -> OOS maker_rt net: {pos}/{len(oos_rt)} steps positive; "
                  f"mean OOS net_makerRT = {statistics.mean(oos_rt)*100:+.4f}%")

def sensitivity(K):
    """Parameter sensitivity grid on a held-out fold (use the LAST fold of K=4).
    Threshold computed from all-prior folds; entries in held-out fold."""
    bounds = fold_bounds(K)
    fold_days = SPAN_DAYS / K
    train_lo = bounds[0][0]; train_hi = bounds[-2][1]
    test_lo, test_hi = bounds[-1]
    print("\n" + "#" * 78)
    print(f"### PARAMETER SENSITIVITY on held-out fold {K} "
          f"({fmt(test_lo)}..{fmt(T1)}); threshold from prior folds")
    print("#" * 78)

    # Family A grid (W, pct, tp, sl) at fixed max_hold=900
    print("\n--- Family A: alt-vs-ETH reversion (max_hold=900) ---")
    print(f"{'W':>4} {'pct':>4} {'tp':>5} {'sl':>5} {'n':>5} {'gross%':>9} "
          f"{'netRT%':>9} {'wr%':>6}")
    for W in (300, 600, 900):
        sigs = SIGS_A if W == A_CFG["W"] else buildA_signals(W)
        for pct in (90, 95):
            for tp in (0.004, 0.006, 0.010):
                for sl in (0.005, 0.008):
                    oos = runA_fold(sigs, W, pct, 900, tp, sl,
                                    train_lo, train_hi, test_lo, test_hi)
                    st = summarize(oos, fold_days)
                    if not st or st["n"] < 8:
                        continue
                    print(f"{W:>4} {pct:>4} {tp*100:>4.1f}% {sl*100:>4.1f}% {st['n']:>5} "
                          f"{st['gross']*100:>8.4f}% {st['net_makerrt']*100:>8.4f}% "
                          f"{st['wr']*100:>5.1f}%")

    # Family B grid (rv_q, rp_q, tp, sl) at fixed max_hold=1800
    print("\n--- Family B: high-vol reversion (max_hold=1800) ---")
    print(f"{'rv_q':>5} {'rp_q':>5} {'tp':>5} {'sl':>5} {'n':>5} {'gross%':>9} "
          f"{'netRT%':>9} {'wr%':>6}")
    for rq in (0.5, 2/3, 0.8):
        for pq in (0.90, 0.95):
            for tp in (0.004, 0.006, 0.010):
                for sl in (0.005, 0.008):
                    oos = runB_fold(CANDS_B, rq, pq, 1800, tp, sl,
                                    train_lo, train_hi, test_lo, test_hi)
                    st = summarize(oos, fold_days)
                    if not st or st["n"] < 8:
                        continue
                    print(f"{rq:>5.2f} {pq:>5.2f} {tp*100:>4.1f}% {sl*100:>4.1f}% {st['n']:>5} "
                          f"{st['gross']*100:>8.4f}% {st['net_makerrt']*100:>8.4f}% "
                          f"{st['wr']*100:>5.1f}%")

if __name__ == "__main__":
    per_fold_report(4)
    per_fold_report(6)
    walk_forward(4)
    walk_forward(6)
    sensitivity(4)
    print("\n[done]")
