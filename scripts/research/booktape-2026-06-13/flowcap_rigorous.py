"""THE TEST. Chronological train/test, bootstrap CI, beats-random, net of fees.

Candidate (selected from grid/corners on FULL sample as hypothesis):
  ABSORPTION SHORT: imb >= 0.3 AND buy_ratio >= 0.6  -> SHORT, hold H seconds.
We harden it: select exact thresholds on TRAIN ONLY, report TEST only.

Fees (round-trip): maker 0.02% = 2 bps ; taker 0.12% = 12 bps.
Mean-return (signal) sim: net = gross_reversion_alpha - fee_rt.
"""
import flowcap_lib as L
import random
random.seed(42)

rbs = L.load()
samples = L.build_samples(rbs)
samples.sort(key=lambda s: s["ts"])  # chronological

# chronological split 70/30 by time
n=len(samples)
split_ts = samples[int(0.7*n)]["ts"]
train=[s for s in samples if s["ts"]<split_ts]
test =[s for s in samples if s["ts"]>=split_ts]
import datetime
print(f"split @ {datetime.datetime.utcfromtimestamp(split_ts)} UTC")
print(f"train n={len(train)}  test n={len(test)}")

FEE_MAKER=0.0002; FEE_TAKER=0.0012

def short_alpha(s, H):
    fr=s.get(f"fwd_{H}")
    if fr is None: return None
    return -fr  # short

def eval_rule(data, imb_thr, br_thr, H):
    vals=[short_alpha(s,H) for s in data
          if s["imb"]>=imb_thr and s.get("buy_ratio") is not None and s["buy_ratio"]>=br_thr
          and short_alpha(s,H) is not None]
    m,sd,nn=L.stats(vals); se=sd/(nn**0.5) if nn>1 else 0
    return m, nn, (m/se if se else 0), vals

print("\n"+"="*70)
print("STEP 1: SELECT thresholds on TRAIN only (grid search, H=300 & 900)")
print("="*70)
best=None
for H in (300,900):
    for it in (0.2,0.3,0.4):
        for bt in (0.5,0.6,0.7):
            m,nn,t,_=eval_rule(train,it,bt,H)
            if nn<300: continue
            net_maker=m-FEE_MAKER
            # objective: net maker alpha, require decent n
            score=net_maker
            if best is None or score>best[0]:
                best=(score,H,it,bt,m,nn,t)
print(f"  best on TRAIN: H={best[1]} imb>={best[2]} br>={best[3]}")
print(f"    train gross={1e4*best[4]:+.3f}bps net_maker={1e4*(best[4]-FEE_MAKER):+.3f}bps n={best[5]} t={best[6]:+.2f}")

_,H,IT,BT,_,_,_=best

print("\n"+"="*70)
print("STEP 2: APPLY frozen rule to TEST (out-of-sample)")
print(f"  RULE: imb>={IT} & buy_ratio>={BT} -> SHORT, hold {H}s")
print("="*70)
m,nn,t,vals=eval_rule(test,IT,BT,H)
print(f"  TEST gross reversion alpha: {1e4*m:+.3f} bps  (n={nn}, t={t:+.2f})")
print(f"  net @ maker 2bps RT:        {1e4*(m-FEE_MAKER):+.3f} bps")
print(f"  net @ taker 12bps RT:       {1e4*(m-FEE_TAKER):+.3f} bps")

# imbalance-alone baseline on TEST, same imb thr & H, for comparison
base=[short_alpha(s,H) for s in test if s["imb"]>=IT and short_alpha(s,H) is not None]
bm,bsd,bn=L.stats(base); bse=bsd/(bn**0.5) if bn>1 else 0
print(f"\n  IMBALANCE-ALONE baseline (imb>={IT}, no tape) on TEST:")
print(f"    gross {1e4*bm:+.3f} bps  net_maker {1e4*(bm-FEE_MAKER):+.3f} bps  (n={bn}, t={bm/bse if bse else 0:+.2f})")
print(f"    >>> tape lift over imbalance-alone (TEST): {1e4*(m-bm):+.3f} bps")

print("\n"+"="*70)
print("STEP 3: BOOTSTRAP 95% CI on TEST gross alpha (10000 resamples)")
print("="*70)
B=10000
boot=[]
nv=len(vals)
for _ in range(B):
    s=sum(vals[random.randrange(nv)] for _ in range(nv))/nv
    boot.append(s)
boot.sort()
lo=boot[int(0.025*B)]; hi=boot[int(0.975*B)]
print(f"  gross alpha 95% CI: [{1e4*lo:+.3f}, {1e4*hi:+.3f}] bps")
print(f"  net maker 95% CI:   [{1e4*(lo-FEE_MAKER):+.3f}, {1e4*(hi-FEE_MAKER):+.3f}] bps")
print(f"  net taker 95% CI:   [{1e4*(lo-FEE_TAKER):+.3f}, {1e4*(hi-FEE_TAKER):+.3f}] bps")

print("\n"+"="*70)
print("STEP 4: BEATS-RANDOM (permutation) on TEST")
print("  Null: assign the SAME number of signals to random rows; how often does")
print("  random selection match observed gross alpha?")
print("="*70)
allshort=[short_alpha(s,H) for s in test if short_alpha(s,H) is not None]
K=nn
P=10000
ge=0
obs=m
for _ in range(P):
    samp=sum(allshort[random.randrange(len(allshort))] for _ in range(K))/K
    if samp>=obs: ge+=1
print(f"  random pool mean (all rows, short): {1e4*L.mean(allshort):+.3f} bps")
print(f"  P(random K-draw >= observed {1e4*obs:+.3f}bps) = {ge/P:.4f}")

# Per-symbol robustness on TEST
print("\n"+"="*70)
print("STEP 5: per-symbol breakdown on TEST (is it one coin or broad?)")
print("="*70)
from collections import defaultdict
bysym=defaultdict(list)
for s in test:
    if s["imb"]>=IT and s.get("buy_ratio") is not None and s["buy_ratio"]>=BT:
        a=short_alpha(s,H)
        if a is not None: bysym[s["symbol"]].append(a)
rows=[(sym,1e4*L.mean(v),len(v)) for sym,v in bysym.items() if len(v)>=20]
rows.sort(key=lambda x:-x[1])
pos=sum(1 for _,a,_ in rows if a>0)
print(f"  symbols w/ >=20 test signals: {len(rows)}  positive: {pos}")
for sym,a,c in rows:
    print(f"    {sym:20} {a:+7.2f} bps  n={c}")
