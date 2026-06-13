"""Dig into the joint corners. Compare imbalance-alone vs imbalance x buy_ratio
on the SHORT side specifically. Quantify whether tape adds over imbalance-alone."""
import flowcap_lib as L

rbs = L.load()
samples = L.build_samples(rbs)
H = 900

def report(name, vals):
    m,sd,n=L.stats(vals); se=sd/(n**0.5) if n>1 else 0
    print(f"  {name:<52} n={n:6d}  {1e4*m:+7.3f} bps  t={m/se if se else 0:+5.2f}")

# Reversion alpha for SHORT side. vals already sign-corrected: short => -fwd.
def short_rev(s):
    fr=s.get(f"fwd_{H}")
    if fr is None: return None
    return -fr  # short profits when price falls

print("="*70)
print("SHORT-SIDE focus: imbalance>0 reverts down. Does buy_ratio add edge?")
print("="*70)

# Baseline: imbalance alone, short side, various thresholds
print("\nImbalance-ALONE (short side):")
for thr in (0.2,0.3,0.4):
    vals=[short_rev(s) for s in samples if s["imb"]>=thr and short_rev(s) is not None]
    report(f"imb>={thr}", vals)

# Add buy_ratio HIGH filter (absorption: buyers into bid wall)
print("\nImbalance + buy_ratio HIGH (absorption: buying into bid-heavy book):")
for thr in (0.2,0.3,0.4):
    for brmin in (0.5,0.6,0.7):
        vals=[short_rev(s) for s in samples
              if s["imb"]>=thr and s.get("buy_ratio") is not None and s["buy_ratio"]>=brmin
              and short_rev(s) is not None]
        report(f"imb>={thr} & buy_ratio>={brmin}", vals)

# Compare: buy_ratio LOW (tape confirms down)
print("\nImbalance + buy_ratio LOW (tape confirms the down move):")
for thr in (0.2,0.3,0.4):
    vals=[short_rev(s) for s in samples
          if s["imb"]>=thr and s.get("buy_ratio") is not None and s["buy_ratio"]<0.5
          and short_rev(s) is not None]
    report(f"imb>={thr} & buy_ratio<0.5", vals)

# Add divergence filter on top of best absorption rule
print("\nAbsorption + divergence filter (exclude bearish-divergence dead bucket):")
for dvexcl in (("bearish",),("bullish",),()):
    vals=[short_rev(s) for s in samples
          if s["imb"]>=0.3 and s.get("buy_ratio") is not None and s["buy_ratio"]>=0.6
          and s["divergence"] not in dvexcl and short_rev(s) is not None]
    report(f"imb>=0.3 & buy_ratio>=0.6 & div not in {dvexcl}", vals)

# Best so far across both horizons
print("\nBest candidate across horizons (imb>=0.3 & buy_ratio>=0.6):")
for HH in (300,900,1800):
    vals=[]
    for s in samples:
        fr=s.get(f"fwd_{HH}")
        if fr is None: continue
        if s["imb"]>=0.3 and s.get("buy_ratio") is not None and s["buy_ratio"]>=0.6:
            vals.append(-fr)
    m,sd,n=L.stats(vals); se=sd/(n**0.5) if n>1 else 0
    print(f"  H={HH:5d}  n={n:6d}  {1e4*m:+7.3f} bps  t={m/se if se else 0:+5.2f}")
