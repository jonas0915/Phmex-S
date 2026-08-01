#!/usr/bin/env python3
"""Permutation / exact tests: hard_time_exit vs priced (TP/SL/exchange_close) exits.

Small-n hypothesis-generating analysis. Primary: live era (timeout n=5 vs
priced n=13). Secondary: pooled eras (labeled, caveated). adverse_exit trades
(paper era, n=4) are excluded from both groups and reported separately.
Two-sided permutation p on |mean diff| (20,000 shuffles, seeded); Fisher exact
for binaries. All tests reported for multiple-comparison accounting.
"""
import json, os, random, math
from math import comb

HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "trades_features.json")))

NUMERIC = [
    "ob_imbalance", "ob_imbalance_aligned", "spread_pct",
    "buy_ratio", "buy_ratio_aligned", "cvd_slope_aligned",
    "large_trade_bias_aligned", "trade_count",
    "adx", "atr_pct", "vol_ratio", "htf_adx", "hour_pt",
]
BINARY = [
    ("side_long", lambda r: 1 if r["side"] == "long" else 0),
    ("regime_choppy", lambda r: None if r["regime_label"] is None else (1 if r["regime_label"] == "CHOPPY" else 0)),
    ("above_ema200", lambda r: None if r["above_ema200"] is None else int(r["above_ema200"])),
    ("any_bid_wall", lambda r: None if r["bid_walls"] is None else int(r["bid_walls"] > 0)),
    ("any_ask_wall", lambda r: None if r["ask_walls"] is None else int(r["ask_walls"] > 0)),
    ("ema_stack_aligned", lambda r: None if r["ema_stack_bull"] is None else int(
        (r["side"] == "long" and r["ema_stack_bull"]) or (r["side"] == "short" and r["ema_stack_bear"]))),
]

def perm_test(a, b, n=20000, seed=42):
    """Two-sided permutation test on |mean(a)-mean(b)|."""
    obs = abs(sum(a)/len(a) - sum(b)/len(b))
    pool = a + b
    na = len(a)
    rng = random.Random(seed)
    hits = 0
    for _ in range(n):
        rng.shuffle(pool)
        d = abs(sum(pool[:na])/na - sum(pool[na:])/(len(pool)-na))
        if d >= obs - 1e-12:
            hits += 1
    return hits / n

def fisher_2sided(a1, a0, b1, b0):
    """Exact two-sided Fisher (sum of tables with prob <= observed)."""
    n = a1 + a0 + b1 + b0
    r1 = a1 + b1          # total successes
    ca = a1 + a0          # group-a size
    def p_tab(x):
        return comb(r1, x) * comb(n - r1, ca - x) / comb(n, ca)
    p_obs = p_tab(a1)
    lo, hi = max(0, r1 - (n - ca)), min(r1, ca)
    return sum(p_tab(x) for x in range(lo, hi + 1) if p_tab(x) <= p_obs + 1e-12)

def run(tag, subset):
    T = [r for r in subset if r["group"] == "timeout"]
    P = [r for r in subset if r["group"] == "priced"]
    print(f"\n=== {tag}: timeout n={len(T)} vs priced n={len(P)} ===")
    results = []
    for f in NUMERIC:
        a = [r[f] for r in T if r[f] is not None]
        b = [r[f] for r in P if r[f] is not None]
        if len(a) < 3 or len(b) < 3:
            print(f"  {f:26s} SKIP (n={len(a)} vs {len(b)} non-null)")
            continue
        ma, mb = sum(a)/len(a), sum(b)/len(b)
        sa = sorted(a); sb = sorted(b)
        meda = sa[len(sa)//2] if len(sa) % 2 else (sa[len(sa)//2-1]+sa[len(sa)//2])/2
        medb = sb[len(sb)//2] if len(sb) % 2 else (sb[len(sb)//2-1]+sb[len(sb)//2])/2
        p = perm_test(list(a), list(b))
        # pooled-SD effect size (hypothesis-generating only)
        va = sum((x-ma)**2 for x in a)/max(len(a)-1,1)
        vb = sum((x-mb)**2 for x in b)/max(len(b)-1,1)
        psd = math.sqrt(((len(a)-1)*va + (len(b)-1)*vb) / max(len(a)+len(b)-2, 1))
        dz = (ma-mb)/psd if psd > 0 else float("nan")
        results.append((f, p))
        print(f"  {f:26s} T mean={ma:+.4f} med={meda:+.4f} (n={len(a)}) | "
              f"P mean={mb:+.4f} med={medb:+.4f} (n={len(b)}) | d={dz:+.2f} p={p:.4f}")
    for name, fn in BINARY:
        a = [fn(r) for r in T]; a = [x for x in a if x is not None]
        b = [fn(r) for r in P]; b = [x for x in b if x is not None]
        if len(a) < 3 or len(b) < 3:
            print(f"  {name:26s} SKIP (n={len(a)} vs {len(b)})")
            continue
        a1 = sum(a); b1 = sum(b)
        p = fisher_2sided(a1, len(a)-a1, b1, len(b)-b1)
        results.append((name, p))
        print(f"  {name:26s} T {a1}/{len(a)} | P {b1}/{len(b)} | Fisher p={p:.4f}")
    return results

live = [r for r in rows if r["era"] == "live" and r["has_snapshot"]]
allr = [r for r in rows if r["has_snapshot"]]

res_live = run("LIVE era only (primary)", live)
res_pool = run("POOLED eras (secondary, era-labeled caveat)", allr)

n_tests = len(res_live) + len(res_pool)
print(f"\nTotal tests run: {n_tests}  -> Bonferroni alpha for p<0.05: {0.05/n_tests:.4f}")
print("Nominal p<0.05 hits:")
for tag, res in (("live", res_live), ("pooled", res_pool)):
    for f, p in res:
        if p < 0.05:
            print(f"  [{tag}] {f}: p={p:.4f}")

# adverse group note + capacity cost
adv = [r for r in rows if r["group"] == "adverse"]
print(f"\nadverse_exit trades (excluded from comparison): idx {[r['idx'] for r in adv]}, all paper era")
for era in ("paper", "live"):
    tt = [r for r in rows if r["era"] == era and r["group"] == "timeout"]
    hrs = sum(r["duration_h"] for r in tt)
    net = sum(r["net_pnl"] for r in tt if r["net_pnl"] is not None)
    gross = sum(r["pnl_usdt"] for r in tt)
    print(f"{era} timeouts: idx {[r['idx'] for r in tt]}, {hrs:.1f}h held, gross {gross:+.2f}, net(where recorded) {net:+.2f}")
