#!/usr/bin/env python3
"""
Book+Tape interaction analysis.
Baseline: imbalance-alone reversion. Then test interactions a-d.
All correlations are Pearson r between signal and forward return.
NOTE: imbalance predicts REVERSION, so positive imb -> negative fwd ret => r<0.
"""
import numpy as np, pandas as pd
from scipy import stats
import glob, os

OUTDIR = "scripts/research/booktape-2026-06-13/out"
SYMS = ["BTC", "ETH", "INJ", "ARB"]
HZ = ["fwd30", "fwd60", "fwd300"]


def load_all():
    d = {}
    for s in SYMS:
        df = pd.read_csv(f"{OUTDIR}/{s}_features.csv")
        df["sym"] = s
        # normalize tape signed volume within symbol (z-score) so symbols comparable
        df["tape_sv_z"] = (df.tape_sv - df.tape_sv.mean()) / (df.tape_sv.std() + 1e-12)
        df["ofi_z"] = (df.ofi_w - df.ofi_w.mean()) / (df.ofi_w.std() + 1e-12)
        df["cnt_z"] = (df.tape_cnt - df.tape_cnt.mean()) / (df.tape_cnt.std() + 1e-12)
        d[s] = df
    allp = pd.concat(d.values(), ignore_index=True)
    return d, allp


def corr_line(name, x, y):
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < 30:
        return f"  {name:32s} n={len(x):5d} (too few)"
    r, p = stats.pearsonr(x, y)
    return f"  {name:32s} n={len(x):5d}  r={r:+.4f}  p={p:.2e}"


def baseline(allp):
    print("\n" + "="*70)
    print("BASELINE: imbalance-alone forward-return correlation (pooled, z'd per sym)")
    print("(reversion => negative r: positive imbalance -> price falls)")
    print("="*70)
    for h in HZ:
        print(f"[{h}]")
        print(corr_line("imb1", allp.imb1.values, allp[h].values))
        print(corr_line("imb5", allp.imb5.values, allp[h].values))
    print("\n  Tape-alone controls (expected ~0):")
    for h in HZ:
        print(f"[{h}]")
        print(corr_line("tape_sv (signed vol)", allp.tape_sv_z.values, allp[h].values))
        print(corr_line("tape_aggr (buy ratio)", (allp.tape_aggr-0.5).values, allp[h].values))
        print(corr_line("ofi_w", allp.ofi_z.values, allp[h].values))


def interaction_absorption(allp):
    print("\n" + "="*70)
    print("INTERACTION (a) ABSORPTION")
    print("Hypothesis: imbalance-reversion is STRONGER when tape opposes the book")
    print("(book bid-heavy [imb>0, predicts down] but tape aggressively BUYING into it")
    print(" => sellers absorbing buy aggression => stronger down reversion)")
    print("="*70)
    # Define 'tape opposes book' : sign(tape_sv) opposite to predicted reversion.
    # imb>0 predicts down (ret<0); reversion direction = -sign(imb).
    # tape agrees w/ reversion if sign(tape_sv) == -sign(imb).
    # tape OPPOSES reversion (pushes WITH the book) if sign(tape_sv)==sign(imb)...
    # Absorption framing: book imb>0 (bid heavy) AND tape selling-pressure??
    # Cleanest: condition imbalance signal on whether tape pushes same dir as imbalance-as-pressure.
    # imb>0 = bid pressure (buy-ish book). tape_sv>0 = buy aggression.
    # OPPOSING = imb>0 & tape_sv<0  (book bid-heavy, but tape selling) OR imb<0 & tape_sv>0.
    sv = allp.tape_sv_z.values
    imb = allp.imb1.values
    opposing = np.sign(imb) != np.sign(sv)
    agreeing = np.sign(imb) == np.sign(sv)
    for h in HZ:
        y = allp[h].values
        print(f"[{h}]")
        print("  -- tape OPPOSES book (book imb vs tape flow opposite sign):")
        print(corr_line("    imb1 | opposing", imb[opposing], y[opposing]))
        print("  -- tape AGREES with book (same sign):")
        print(corr_line("    imb1 | agreeing", imb[agreeing], y[agreeing]))


def interaction_confirmation(allp):
    print("\n" + "="*70)
    print("INTERACTION (b) CONFIRMATION")
    print("Split imbalance-reversion by whether tape AGREES with predicted reversion.")
    print("Predicted reversion dir = -sign(imb). Tape agrees if sign(tape_sv)==-sign(imb).")
    print("="*70)
    sv = allp.tape_sv_z.values
    imb = allp.imb1.values
    pred_rev = -np.sign(imb)
    tape_confirms = np.sign(sv) == pred_rev    # tape pushing toward the reversion
    tape_fights = np.sign(sv) == -pred_rev
    for h in HZ:
        y = allp[h].values
        print(f"[{h}]")
        print(corr_line("  imb1 | tape CONFIRMS reversion", imb[tape_confirms], y[tape_confirms]))
        print(corr_line("  imb1 | tape FIGHTS reversion", imb[tape_fights], y[tape_fights]))


def interaction_ofi(allp):
    print("\n" + "="*70)
    print("INTERACTION (c) OFI vs static imbalance")
    print("OFI = order-flow imbalance (book depth changes), trailing window.")
    print("="*70)
    for h in HZ:
        y = allp[h].values
        print(f"[{h}]")
        print(corr_line("  ofi_w (signed)", allp.ofi_z.values, y))
        # combined: residualize? simple sum of z-scores (imbalance reversion + ofi momentum)
        # Build a combined signal: predict reversion from imb, momentum from ofi.
        combo = -allp.imb1.values + 0.0  # placeholder, real combos in sim
        print(corr_line("  imb1 (ref)", allp.imb1.values, y))


def interaction_regime(allp):
    print("\n" + "="*70)
    print("INTERACTION (d) REGIME SPLIT by tape intensity (trade count terciles)")
    print("Does imbalance-reversion work only when tape quiet, or active?")
    print("="*70)
    for s in SYMS:
        df = allp[allp.sym == s]
        q1, q2 = df.tape_cnt.quantile([0.33, 0.66])
        lo = df[df.tape_cnt <= q1]
        mi = df[(df.tape_cnt > q1) & (df.tape_cnt <= q2)]
        hi = df[df.tape_cnt > q2]
        print(f"[{s}] cnt terciles cut at {q1:.0f}/{q2:.0f}")
        for h in ["fwd60"]:
            print(corr_line(f"  imb1 | LOW tape  ({len(lo)})", lo.imb1.values, lo[h].values))
            print(corr_line(f"  imb1 | MID tape  ({len(mi)})", mi.imb1.values, mi[h].values))
            print(corr_line(f"  imb1 | HIGH tape ({len(hi)})", hi.imb1.values, hi[h].values))
    print("\n  Pooled (z'd):")
    q1, q2 = allp.cnt_z.quantile([0.33, 0.66])
    for h in HZ:
        lo = allp[allp.cnt_z <= q1]; hi = allp[allp.cnt_z > q2]
        print(f"[{h}]")
        print(corr_line("  imb1 | LOW tape", lo.imb1.values, lo[h].values))
        print(corr_line("  imb1 | HIGH tape", hi.imb1.values, hi[h].values))


if __name__ == "__main__":
    d, allp = load_all()
    print(f"Loaded {len(allp)} pooled samples across {len(SYMS)} symbols.")
    print("Per-symbol counts:", {s: int((allp.sym==s).sum()) for s in SYMS})
    print("Median spread (bps):", {s: round(float(d[s].spread.median()*1e4),2) for s in SYMS})
    baseline(allp)
    interaction_absorption(allp)
    interaction_confirmation(allp)
    interaction_ofi(allp)
    interaction_regime(allp)
