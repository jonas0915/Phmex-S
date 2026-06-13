#!/usr/bin/env python3
"""Verification: (1) confirm no look-ahead by asserting anchor alignment <= alt ts,
(2) report TOP-5 TRAIN configs on TEST at MAKER fee (the only fee where ETH was positive),
(3) shuffle-control: scramble the divergence->side mapping; edge should vanish."""
import json,bisect,random,statistics
from collections import defaultdict
DATA="logs/flow_capture.jsonl"; ANCHOR_SYM="ETH/USDT:USDT"
MAKER=0.000663; ALIGN_TOL=150; random.seed(7)
series=defaultdict(list)
with open(DATA) as f:
    for line in f:
        line=line.strip()
        if not line: continue
        try: d=json.loads(line)
        except: continue
        p=d.get("price")
        if p is None or p<=0: continue
        series[d["symbol"]].append((d["ts"],p))
for s in series: series[s].sort(key=lambda x:x[0])
ats=[t for t,_ in series[ANCHOR_SYM]]; apx=[p for _,p in series[ANCHOR_SYM]]
def aob(tsl,pxl,target,tol):
    i=bisect.bisect_right(tsl,target)-1
    if i<0: return None,None
    if target-tsl[i]>tol: return None,None
    return pxl[i],tsl[i]
ALTS=[s for s in series if s!=ANCHOR_SYM and len(series[s])>=200]
allts=[]
for s in ALTS: allts.extend(t for t,_ in series[s])
allts.sort(); SPLIT=allts[len(allts)//2]

# LOOK-AHEAD ASSERTION: every anchor alignment must be at-or-before the alt ts
viol=0; checked=0
for s in ALTS[:5]:
    for t,_ in series[s][::50]:
        ap,att=aob(ats,apx,t,ALIGN_TOL)
        if att is not None:
            checked+=1
            if att>t: viol+=1
print(f"LOOK-AHEAD CHECK: checked={checked} anchor-after-alt violations={viol} (must be 0)")

W=600
def build(sym):
    s=series[sym]; ts=[t for t,_ in s]; px=[p for _,p in s]; out=[]
    for i in range(len(s)):
        t=ts[i]
        pp,_=aob(ts,px,t-W,ALIGN_TOL)
        if pp is None: continue
        anow,_=aob(ats,apx,t,ALIGN_TOL); apast,_=aob(ats,apx,t-W,ALIGN_TOL)
        if anow is None or apast is None: continue
        out.append((t,px[i],(px[i]/pp-1.0)-(anow/apast-1.0)))
    return out
sig={s:build(s) for s in ALTS}
def fexit(sym,et,ep,side,mh,tp,sl):
    s=series[sym]; ts=[t for t,_ in s]; px=[p for _,p in s]
    i=bisect.bisect_right(ts,et); end=et+mh; last=ep
    while i<len(s) and ts[i]<=end:
        p=px[i]; last=p; r=side*(p/ep-1.0)
        if r>=tp: return tp
        if r<=-sl: return -sl
        i+=1
    return side*(last/ep-1.0)
def run(pct,direction,mh,tp,sl,shuffle=False):
    rets=[]
    for sym,sigs in sig.items():
        td=sorted(abs(d) for (t,p,d) in sigs if t<SPLIT)
        if len(td)<30: continue
        thr=td[int(len(td)*pct/100.0)]
        if thr<=0: continue
        le=-1e18
        for (t,p,d) in sigs:
            if t<SPLIT: continue
            if abs(d)<thr: continue
            if t-le<W: continue
            if shuffle: side=random.choice([1,-1])
            elif direction=="reversion": side=-1 if d>0 else 1
            else: side=1 if d>0 else -1
            rets.append(fexit(sym,t,p,side,mh,tp,sl)); le=t
    return rets
def st(rets,fee):
    n=[r-fee for r in rets]
    return len(n),statistics.mean(n)*100,sum(1 for r in rets if r>0)/len(rets)*100,sum(n)*100

print("\nTOP TRAIN configs on TEST at MAKER fee 0.0663%:")
print(f"{'pct':>4}{'mh':>6}{'tp':>5}{'sl':>5} {'n':>5} {'maker_net%':>11} {'wr':>6} {'sum%':>8}")
for (pct,mh,tp,sl) in [(95,1800,0.006,0.005),(95,1800,0.010,0.005),(95,900,0.006,0.005),(90,1800,0.010,0.005),(90,1800,0.006,0.005)]:
    r=run(pct,"reversion",mh,tp,sl); n,mn,wr,sm=st(r,MAKER)
    print(f"{pct:>4}{mh:>6}{tp*100:>5.1f}{sl*100:>5.1f} {n:>5} {mn:>10.4f}% {wr:>5.1f}% {sm:>7.2f}%")

# shuffle control on best config: 200 shuffles, fraction with maker_net >= real
real=run(95,"reversion",1800,0.006,0.005); _,real_mn,_,_=st(real,MAKER)
shuf=[]
for _ in range(200):
    rr=run(95,"reversion",1800,0.006,0.005,shuffle=True); shuf.append(statistics.mean([x-MAKER for x in rr])*100)
fb=sum(1 for x in shuf if x>=real_mn)/len(shuf)
print(f"\nSHUFFLE CONTROL (best cfg, maker): real_net={real_mn:.4f}%  shuffle_mean={statistics.mean(shuf):.4f}%  frac_shuffle>=real={fb:.3f}")
