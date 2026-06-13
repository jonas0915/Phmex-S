#!/usr/bin/env python3
"""BTC-anchor variant. BTC only covers ~9 days (2026-05-11..05-20), so we restrict
ALL alt snapshots to the BTC-covered window [btc_first, btc_last] and split THAT 50/50
chronologically. Otherwise identical method to xsymbol_divergence.py."""
import json, sys, bisect, random, statistics, datetime as _dt
from collections import defaultdict

DATA="logs/flow_capture.jsonl"; ANCHOR_SYM="BTC/USDT:USDT"
FEES={"gross":0.0,"maker_0.0663pct":0.000663,"taker_0.12pct":0.0012}
ALIGN_TOL=150; WINDOWS=[300,600,900]; MAX_HOLDS=[300,900,1800]
TPS=[0.004,0.006,0.010]; SLS=[0.005,0.008]; PCTS=[90,95]; MIN_TEST=15
random.seed(42)

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

anchor_ts=[t for t,_ in series[ANCHOR_SYM]]; anchor_px=[p for _,p in series[ANCHOR_SYM]]
BTC_FIRST=anchor_ts[0]; BTC_LAST=anchor_ts[-1]

def aob(tsl,pxl,target,tol):
    i=bisect.bisect_right(tsl,target)-1
    if i<0: return None
    if target-tsl[i]>tol: return None
    return pxl[i]
def anchor_ret(t,W):
    pn=aob(anchor_ts,anchor_px,t,ALIGN_TOL); pp=aob(anchor_ts,anchor_px,t-W,ALIGN_TOL)
    if pn is None or pp is None: return None
    return pn/pp-1.0

# restrict alts to BTC window
ALTS=[s for s in series if s!=ANCHOR_SYM and len(series[s])>=200]
all_ts=[]
for s in ALTS:
    all_ts.extend(t for t,_ in series[s] if BTC_FIRST<=t<=BTC_LAST)
all_ts.sort()
SPLIT_TS=all_ts[len(all_ts)//2]
def fmt(t): return _dt.datetime.fromtimestamp(t,tz=_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
print(f"# anchor=BTC window={fmt(BTC_FIRST)}..{fmt(BTC_LAST)} split={fmt(SPLIT_TS)} alts={len(ALTS)} rows_in_window={len(all_ts)}")
print(f"# fees RT: {FEES}")

def build_signals(sym,W,beta):
    s=series[sym]; ts=[t for t,_ in s]; px=[p for _,p in s]; out=[]
    for i in range(len(s)):
        t=ts[i]
        if t<BTC_FIRST or t>BTC_LAST: continue
        pp=aob(ts,px,t-W,ALIGN_TOL)
        if pp is None: continue
        ar=px[i]/pp-1.0; br=anchor_ret(t,W)
        if br is None: continue
        out.append((t,px[i],ar-beta*br))
    return out

def fexit(sym,et,ep,side,mh,tp,sl):
    s=series[sym]; ts=[t for t,_ in s]; px=[p for _,p in s]
    i=bisect.bisect_right(ts,et); end=et+mh; last=ep
    while i<len(s) and ts[i]<=end:
        p=px[i]; last=p; r=side*(p/ep-1.0)
        if r>=tp: return tp
        if r<=-sl: return -sl
        i+=1
    return side*(last/ep-1.0)

def run(ss,W,pct,direction,mh,tp,sl,period):
    rets=[]; contrib=defaultdict(list)
    for sym,sigs in ss.items():
        td=sorted(abs(d) for (t,p,d) in sigs if t<SPLIT_TS)
        if len(td)<30: continue
        thr=td[int(len(td)*pct/100.0)]
        if thr<=0: continue
        le=-1e18
        for (t,p,d) in sigs:
            if period=="train" and t>=SPLIT_TS: continue
            if period=="test" and t<SPLIT_TS: continue
            if abs(d)<thr: continue
            if t-le<W: continue
            if direction=="reversion": side=-1 if d>0 else 1
            else: side=1 if d>0 else -1
            r=fexit(sym,t,p,side,mh,tp,sl); rets.append(r); contrib[sym].append(r); le=t
    return rets,contrib

def ns(rets,fee):
    if not rets: return None
    nets=[r-fee for r in rets]
    return {"n":len(nets),"mean_net":statistics.mean(nets),"wr":sum(1 for r in rets if r>0)/len(rets),"sum_net":sum(nets)}

beta=1.0; results=[]
sigcache={}
for W in WINDOWS:
    ss={sym:build_signals(sym,W,beta) for sym in ALTS}; sigcache[W]=ss
    for pct in PCTS:
        for direction in ("reversion","momentum"):
            for mh in MAX_HOLDS:
                for tp in TPS:
                    for sl in SLS:
                        tr,_=run(ss,W,pct,direction,mh,tp,sl,"train")
                        if len(tr)<20: continue
                        st=ns(tr,FEES["taker_0.12pct"])
                        results.append({"W":W,"pct":pct,"dir":direction,"mh":mh,"tp":tp,"sl":sl,
                                        "train_n":st["n"],"train_mean_net":st["mean_net"],"train_wr":st["wr"]})
results.sort(key=lambda r:-r["train_mean_net"])
print("\n# ==== TOP 10 TRAIN configs (taker 0.12%) ====")
print(f"{'W':>4}{'pct':>4} {'dir':>9}{'mh':>5}{'tp':>5}{'sl':>5} {'tr_n':>5} {'tr_net%':>9} {'tr_wr':>6}")
for r in results[:10]:
    print(f"{r['W']:>4}{r['pct']:>4} {r['dir']:>9}{r['mh']:>5}{r['tp']*100:>5.1f}{r['sl']*100:>5.1f} {r['train_n']:>5} {r['train_mean_net']*100:>8.4f}% {r['train_wr']*100:>5.1f}%")

test_days=(BTC_LAST-SPLIT_TS)/86400.0
if results:
    b=results[0]; ss=sigcache[b["W"]]
    print(f"\n# ==== BEST TRAIN -> TEST ====\n# {b}")
    te,contrib=run(ss,b["W"],b["pct"],b["dir"],b["mh"],b["tp"],b["sl"],"test")
    print(f"# TEST n={len(te)} triggers/day={len(te)/test_days:.2f} test_days={test_days:.1f}")
    for fn,fee in FEES.items():
        st=ns(te,fee)
        if st: print(f"#   {fn:18s} mean_net={st['mean_net']*100:+.4f}% wr={st['wr']*100:.1f}% sum_net={st['sum_net']*100:+.2f}%")
    if te:
        pool=[(sym,t,p) for sym,sg in ss.items() for (t,p,d) in sg if t>=SPLIT_TS]
        draws=[]
        if len(pool)>=len(te):
            for _ in range(1000):
                picks=random.sample(pool,len(te))
                draws.append(statistics.mean(fexit(s,t,p,random.choice([1,-1]),b["mh"],b["tp"],b["sl"]) for s,t,p in picks))
        sg=statistics.mean(te)
        if draws:
            fb=sum(1 for d in draws if d>=sg)/len(draws)
            print(f"#   random gross mean={statistics.mean(draws)*100:+.4f}% strat gross={sg*100:+.4f}% p-value={fb:.3f}")
        cs=sorted(contrib.items(),key=lambda kv:-sum(kv[1]))
        print("#   top contributing symbols (TEST):")
        for sym,rr in cs[:8]: print(f"#     {sym:22s} n={len(rr):3d} sum_gross={sum(rr)*100:+.2f}% mean={statistics.mean(rr)*100:+.4f}%")

print("\n# ==== TOP-5 TRAIN evaluated on TEST (taker 0.12%) ====")
print(f"{'W':>4}{'pct':>4} {'dir':>9}{'mh':>5}{'tp':>5}{'sl':>5} {'te_n':>5} {'te_net%':>9} {'te_wr':>6} {'tr_net%':>9}")
shown=0
for r in results:
    ss=sigcache[r["W"]]
    te,_=run(ss,r["W"],r["pct"],r["dir"],r["mh"],r["tp"],r["sl"],"test")
    st=ns(te,FEES["taker_0.12pct"])
    if st and st["n"]>=MIN_TEST:
        print(f"{r['W']:>4}{r['pct']:>4} {r['dir']:>9}{r['mh']:>5}{r['tp']*100:>5.1f}{r['sl']*100:>5.1f} {st['n']:>5} {st['mean_net']*100:>8.4f}% {st['wr']*100:>5.1f}% {r['train_mean_net']*100:>8.4f}%")
        shown+=1
    if shown>=5: break
