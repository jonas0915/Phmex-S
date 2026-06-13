"""Robustness: drop top symbol, TP/SL path sim, H=300 OOS, and walk-forward folds."""
import flowcap_lib as L
import random
random.seed(7)

rbs = L.load()
samples = L.build_samples(rbs)
samples.sort(key=lambda s: s["ts"])
n=len(samples); split_ts=samples[int(0.7*n)]["ts"]
train=[s for s in samples if s["ts"]<split_ts]
test =[s for s in samples if s["ts"]>=split_ts]
FEE_MAKER=0.0002; FEE_TAKER=0.0012
IT,BT=0.3,0.6

def short_alpha(s,H):
    fr=s.get(f"fwd_{H}");
    return None if fr is None else -fr

def rule(s): return s["imb"]>=IT and s.get("buy_ratio") is not None and s["buy_ratio"]>=BT

print("="*70); print("ROBUSTNESS CHECKS  (rule: imb>=0.3 & buy_ratio>=0.6, SHORT)"); print("="*70)

# 1. Drop INJ (the outlier) from TEST
for H in (300,900):
    vals=[short_alpha(s,H) for s in test if rule(s) and short_alpha(s,H) is not None]
    vals_noinj=[short_alpha(s,H) for s in test if rule(s) and s["symbol"]!="INJ/USDT:USDT" and short_alpha(s,H) is not None]
    m,sd,nn=L.stats(vals); se=sd/nn**.5 if nn>1 else 0
    m2,sd2,nn2=L.stats(vals_noinj); se2=sd2/nn2**.5 if nn2>1 else 0
    print(f"\nH={H} TEST mean-return:")
    print(f"  all:      {1e4*m:+7.3f} bps gross | net_maker {1e4*(m-FEE_MAKER):+.3f} | net_taker {1e4*(m-FEE_TAKER):+.3f}  n={nn} t={m/se if se else 0:+.2f}")
    print(f"  ex-INJ:   {1e4*m2:+7.3f} bps gross | net_maker {1e4*(m2-FEE_MAKER):+.3f} | net_taker {1e4*(m2-FEE_TAKER):+.3f}  n={nn2} t={m2/se2 if se2 else 0:+.2f}")

# 2. TP/SL PATH sim on TEST. Walk forward snapshots per symbol; short entry.
# Use TP=SL band; exit at first snapshot where |move|>=band or at horizon.
print("\n" + "="*70)
print("TP/SL PATH SIM on TEST (short). Walk the actual snapshot path per symbol.")
print("="*70)
# rebuild per-symbol sorted rows for the TEST window only, with index map
from collections import defaultdict
import bisect
def pathsim(band, H, fee_rt, ex_inj=False):
    bysym=defaultdict(list)
    for s in samples:
        bysym[s["symbol"]].append(s)
    nets=[]
    for sym,rows in bysym.items():
        if ex_inj and sym=="INJ/USDT:USDT": continue
        ts=[r["ts"] for r in rows]
        for i,s in enumerate(rows):
            if s["ts"]<split_ts: continue  # test only
            if not rule(s): continue
            p0=s["px"]; deadline=s["ts"]+H
            outcome=None
            j=i+1
            while j<len(rows) and rows[j]["ts"]<=deadline:
                mv=(rows[j]["px"]-p0)/p0  # price move
                # short: profit if price DOWN. ret_short = -mv
                if -mv>=band: outcome=band; break   # TP hit
                if -mv<=-band: outcome=-band; break # SL hit
                j+=1
            if outcome is None:
                # exit at last snapshot <= deadline
                jj=bisect.bisect_right(ts,deadline)-1
                if jj<=i: continue
                outcome=-(rows[jj]["px"]-p0)/p0
            nets.append(outcome-fee_rt)
    m,sd,nn=L.stats(nets); se=sd/nn**.5 if nn>1 else 0
    wins=sum(1 for x in nets if x>0)
    return m,nn,(m/se if se else 0), wins/nn if nn else 0

for band in (0.003,0.005,0.008):
    for H in (900,1800):
        for fee,flab in ((FEE_MAKER,"maker"),(FEE_TAKER,"taker")):
            m,nn,t,wr=pathsim(band,H,fee)
            print(f"  band={band*100:.1f}% H={H} fee={flab}: net {1e4*m:+7.2f}bps/trade  n={nn} t={t:+.2f} WR={wr*100:.1f}%")
    print()

# 3. ex-INJ path sim at best band
print("ex-INJ path sim, band=0.5% H=900:")
for fee,flab in ((FEE_MAKER,"maker"),(FEE_TAKER,"taker")):
    m,nn,t,wr=pathsim(0.005,900,fee,ex_inj=True)
    print(f"  fee={flab}: net {1e4*m:+.2f}bps/trade n={nn} t={t:+.2f} WR={wr*100:.1f}%")

# 4. Walk-forward: 4 chronological folds, select on prior, test on next
print("\n" + "="*70)
print("WALK-FORWARD (mean-return, H=900, gross & net_maker)")
print("="*70)
ss=samples
edges=[ss[int(k*len(ss)/5)]["ts"] for k in range(6)]
for k in range(1,5):
    lo,hi=edges[k],edges[k+1]
    fold=[s for s in ss if lo<=s["ts"]<hi]
    vals=[short_alpha(s,900) for s in fold if rule(s) and short_alpha(s,900) is not None]
    m,sd,nn=L.stats(vals); se=sd/nn**.5 if nn>1 else 0
    if nn==0:
        print(f"  fold {k}: no signals"); continue
    print(f"  fold {k}: gross {1e4*m:+7.3f}bps net_maker {1e4*(m-FEE_MAKER):+.3f}  n={nn} t={m/se if se else 0:+.2f}")
