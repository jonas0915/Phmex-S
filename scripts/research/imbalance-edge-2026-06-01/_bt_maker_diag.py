"""Diagnostic: verify Scenario B fill mechanics. Report triggers vs fills for the
Scenario-A best config and a few representative configs, on BOTH train and test,
so we can confirm the 0-eligible result is real (fade limits rarely fill) not a bug.
Also test a MUCH longer fill-wait (300s) and an aggressive fade (limit placed
*beyond* the trigger price by 0 == at price; the realistic spec is at price).
"""
import json, bisect, time, sys
from collections import defaultdict
def log(*a): print(*a); sys.stdout.flush()

PATH = "/Users/jonaspenaso/Desktop/Phmex-S/logs/flow_capture.jsonl"
series = defaultdict(lambda: {"ts": [], "px": [], "imb": []})
with open(PATH) as f:
    for line in f:
        line=line.strip()
        if not line: continue
        try:
            r=json.loads(line); sym=r["symbol"]; ts=float(r["ts"]); px=float(r["price"])
            imb=r["ob"]["imbalance"]
            if imb is None or px<=0: continue
            series[sym]["ts"].append(ts); series[sym]["px"].append(px); series[sym]["imb"].append(float(imb))
        except: pass
for sym,d in series.items():
    o=sorted(range(len(d["ts"])),key=lambda i:d["ts"][i])
    d["ts"]=[d["ts"][i] for i in o]; d["px"]=[d["px"][i] for i in o]; d["imb"]=[d["imb"][i] for i in o]
all_ts=sorted(t for d in series.values() for t in d["ts"])
split_ts=all_ts[len(all_ts)//2]

def build_rp(d,W):
    ts=d["ts"]; px=d["px"]; out=[]
    for i in range(len(ts)):
        j=bisect.bisect_right(ts, ts[i]-W)-1
        if j<0 or ts[i]-ts[j]>2*W: out.append(None)
        else: out.append(px[i]/px[j]-1.0)
    return out
def pct(sv,p):
    if not sv: return None
    k=(len(sv)-1)*(p/100.0); lo=int(k); hi=min(lo+1,len(sv)-1); f=k-lo
    return sv[lo]*(1-f)+sv[hi]*f

# Median inter-record gap per symbol (to understand how many ticks are in a 30/60s window)
gaps=[]
for sym,d in series.items():
    ts=d["ts"]
    for i in range(1,len(ts)):
        gaps.append(ts[i]-ts[i-1])
gaps.sort()
log(f"Inter-record gap (per-symbol mixed): median={gaps[len(gaps)//2]:.1f}s "
    f"p25={gaps[len(gaps)//4]:.1f}s p75={gaps[3*len(gaps)//4]:.1f}s  "
    f"(records arrive interleaved; same-symbol cadence is the relevant one)")

# same-symbol cadence
sgaps=[]
for sym,d in series.items():
    ts=d["ts"]
    # this list IS per-symbol already
    for i in range(1,len(ts)):
        sgaps.append(ts[i]-ts[i-1])
# (identical to above because series is per-symbol) -> compute properly per symbol
log("\nPer-symbol record cadence (sample symbols):")
for sym in ["ADA/USDT:USDT","DOGE/USDT:USDT","ZEC/USDT:USDT","INJ/USDT:USDT","BTC/USDT:USDT"]:
    d=series.get(sym)
    if not d: continue
    ts=d["ts"]; g=sorted(ts[i]-ts[i-1] for i in range(1,len(ts)))
    if g:
        log(f"  {sym:18s} n={len(ts):6d} median_gap={g[len(g)//2]:.1f}s p90={g[int(0.9*len(g))]:.1f}s")

def fill_check(W,pct_,thr,fill_wait,region):
    """Return (triggers, fills) for the entry-fade fill model."""
    trig=0; fil=0
    for sym,d in series.items():
        ts=d["ts"]; px=d["px"]; imb=d["imb"]; rp=build_rp(d,W)
        tv=sorted(v for k,v in enumerate(rp) if v is not None and ts[k]<split_ts)
        if len(tv)<50: continue
        hi=pct(tv,pct_); lo=pct(tv,100-pct_); last=-1e18; n=len(ts)
        for i in range(n):
            t=ts[i]
            inr=(t<split_ts) if region=="train" else (t>=split_ts)
            if not inr: continue
            v=rp[i]
            if v is None: continue
            side=None
            if v>=hi and imb[i]<=-thr: side="short"
            elif v<=lo and imb[i]>=thr: side="long"
            if side is None: continue
            if t-last<W: continue
            last=t; trig+=1
            lim=px[i]; dl=t+fill_wait; j=i+1; got=False
            while j<n and ts[j]<=dl:
                p=px[j]
                if side=="long" and p<=lim: got=True; break
                if side=="short" and p>=lim: got=True; break
                j+=1
            if got: fil+=1
    return trig,fil

log("\n=== FILL RATE for Scenario-A best cfg (W=300,pct=95,thr=0.0) ===")
for fw in [30,60,120,300]:
    for region in ["train","test"]:
        trg,fl=fill_check(300,95,0.0,fw,region)
        fr=fl/trg*100 if trg else 0
        log(f"  fill_wait={fw:4d}s region={region:5s} triggers={trg:5d} fills={fl:5d} fill_rate={fr:5.1f}%")
