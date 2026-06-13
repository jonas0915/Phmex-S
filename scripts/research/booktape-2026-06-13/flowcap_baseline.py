"""Baseline: reproduce imbalance-alone reversion. corr + decile forward returns."""
import flowcap_lib as L
from collections import defaultdict

rbs = L.load()
samples = L.build_samples(rbs)

print("="*70)
print("BASELINE: imbalance-alone forward-return correlation (no fee)")
print("="*70)
for H in (300,900,1800):
    xs=[]; ys=[]
    for s in samples:
        fr=s.get(f"fwd_{H}")
        if fr is None: continue
        xs.append(s["imb"]); ys.append(fr)
    r=L.pearson(xs,ys)
    print(f"  H={H:5d}s  n={len(xs):6d}  corr(imbalance, fwd_ret) = {r:+.4f}")
print("  (negative corr = reversion: positive imbalance -> price falls)")

print()
print("Forward return by imbalance decile (H=900s), in bps:")
H=900
pairs=[(s["imb"], s[f"fwd_{H}"]) for s in samples if s.get(f"fwd_{H}") is not None]
pairs.sort()
n=len(pairs); nb=10
print(f"  {'decile':>6} {'imb_range':>20} {'mean_fwd_bps':>12} {'n':>7}")
for d in range(nb):
    lo=d*n//nb; hi=(d+1)*n//nb
    chunk=pairs[lo:hi]
    imbs=[p[0] for p in chunk]; frs=[p[1] for p in chunk]
    print(f"  {d:>6} [{min(imbs):+.3f},{max(imbs):+.3f}] {1e4*L.mean(frs):>12.2f} {len(chunk):>7}")

# Directional reversion signal: sign(-imb) * fwd_ret  -> expected positive if reversion
print()
print("Reversion alpha = mean( -sign(imb) * fwd_ret ) in bps (gross, no fee):")
for H in (300,900,1800):
    vals=[]
    for s in samples:
        fr=s.get(f"fwd_{H}")
        if fr is None: continue
        imb=s["imb"]
        if imb==0: continue
        vals.append((-1 if imb>0 else 1)*fr)
    print(f"  H={H:5d}s  n={len(vals):6d}  mean = {1e4*L.mean(vals):+.3f} bps")

# Strong-imbalance only
print()
print("Reversion alpha restricted to |imb|>=0.3 (bps gross):")
for H in (300,900,1800):
    vals=[]
    for s in samples:
        fr=s.get(f"fwd_{H}")
        if fr is None or abs(s["imb"])<0.3 or s["imb"]==0: continue
        vals.append((-1 if s["imb"]>0 else 1)*fr)
    print(f"  H={H:5d}s  n={len(vals):6d}  mean = {1e4*L.mean(vals):+.3f} bps")
