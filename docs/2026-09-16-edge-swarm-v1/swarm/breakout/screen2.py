#!/usr/bin/env python3
"""1h-scale breakout screen. Same cost/fill model as screen.py (taker 0.12% RT + 0.05% slip, funding at 8h stamps).
Sets: A = mr_edge 35 syms 1h, 2026-06-01 -> 2026-08-03 (train only); B = mr-universe 400d parquet 19 syms 1h, 2025-06-27 -> 2026-05-31 (disjoint, no funding file -> funding approximated at +0.01%/8h paid by longs, received by shorts, the record's own convention in reference_sr_bounce_lever_lab).
Holdout 8/4->9/2 NOT read."""
import glob, json, os, numpy as np, pandas as pd
import importlib.util, sys
spec=importlib.util.spec_from_file_location("s1", os.path.join(os.path.dirname(__file__),"screen.py"))
# reuse functions without executing the module body: copy them here instead
FEE_RT=0.0012; SLIP_RT=0.0005; NOTIONAL=150.0
np.random.seed(7)
DA="/Users/jonaspenaso/Desktop/Phmex-S/reports/cache/mr_edge_20260601_20260903"
DB="/Users/jonaspenaso/Desktop/Phmex-S/scripts/research/mr-universe-scan-2026-08-01/cache"
A_END=pd.Timestamp("2026-08-03 23:59:59+00:00"); B_END=pd.Timestamp("2026-05-31 23:59:59+00:00")

def fund_cost(fr,t_in,t_out,side):
    if fr is None:  # flat 0.01%/8h convention
        n=int((t_out//(8*3600_000))-(t_in//(8*3600_000)))
        return 0.0001*n*(1 if side==1 else -1)
    return sum((r if side==1 else -r) for ts,r in fr if t_in<ts<=t_out)

def sim(df,fr,signals,tp_mult,sl_mult,max_bars,sym):
    o=df.open.values;h=df.high.values;l=df.low.values;c=df.close.values;idx=df.index;out=[];busy=-1
    for i,side,level,H in signals:
        if i+1>=len(df) or i<=busy: continue
        e=o[i+1]*(1+(SLIP_RT/2 if side==1 else -SLIP_RT/2)); tp=e+side*tp_mult*H; sl=e-side*sl_mult*H
        j=i+1;res=None;px=None;last=min(len(df)-1,i+1+max_bars)
        while j<=last:
            hs=(l[j]<=sl) if side==1 else (h[j]>=sl); ht=(h[j]>=tp) if side==1 else (l[j]<=tp)
            if hs: res="SL";px=sl;break
            if ht: res="TP";px=tp;break
            j+=1
        if res is None: j=last;res="TIME";px=c[j]
        px=px*(1-(SLIP_RT/2 if side==1 else -SLIP_RT/2)); gross=side*(px-e)/e
        f=fund_cost(fr,int(idx[i+1].value//1e6),int(idx[j].value//1e6),side); net=gross-FEE_RT-f
        out.append(dict(sym=sym,t=idx[i+1],side=side,res=res,gross=gross,net=net,fund=f,bars=j-(i+1),H=H)); busy=j
    return out
def boot(x,n=3000):
    x=np.asarray(x); 
    if len(x)<5: return (np.nan,np.nan)
    m=[x[np.random.randint(0,len(x),len(x))].mean() for _ in range(n)]; return (np.percentile(m,2.5),np.percentile(m,97.5))
def report(name,tr,geo,days):
    if not tr: print(f"{name} {geo}: 0 trades"); return
    net=np.array([t["net"] for t in tr]);g=np.array([t["gross"] for t in tr]);res=[t["res"] for t in tr];n=len(net)
    lo,hi=boot(net); tp=res.count("TP")/n; sl=res.count("SL")/n
    print(f"{name} {geo}: n={n} ({n/days*7:.1f}/wk) TP%={tp*100:.1f} SL%={sl*100:.1f} TIME%={(1-tp-sl)*100:.1f} gross={g.mean()*1e4:.1f}bps net={net.mean()*1e4:.1f}bps CI[{lo*1e4:.1f},{hi*1e4:.1f}] $/t@150={net.mean()*NOTIONAL:.3f} fund={np.mean([t['fund'] for t in tr])*1e4:.1f}bps medH={np.median([t['H'] for t in tr])*1e4:.0f}bps medbars={np.median([t['bars'] for t in tr]):.0f}")

def m2_signals(df1h,nr_frac=0.7,avg_days=20):
    df=df1h.copy(); day=df.index.floor("D"); df["day"]=day
    daily=df.groupby("day").agg(dh=("high","max"),dl=("low","min")); daily["rng"]=daily.dh-daily.dl
    daily["avg"]=daily.rng.rolling(avg_days).mean().shift(1)
    prev=daily.shift(1)  # prior day's stats
    sig=[];fired=set();c=df.close.values;dv=df.day.values
    ph=prev.dh.reindex(df.day).values; pl=prev.dl.reindex(df.day).values; pr=prev.rng.reindex(df.day).values; pa=prev.avg.reindex(df.day).values
    for i in range(len(df)):
        if not (pr[i]>0 and pa[i]>0 and pr[i]<=nr_frac*pa[i]): continue
        if dv[i] in fired: continue
        if c[i]>ph[i]: sig.append((i,1,ph[i],pr[i]));fired.add(dv[i])
        elif c[i]<pl[i]: sig.append((i,-1,pl[i],pr[i]));fired.add(dv[i])
    return sig
def m4_signals(df,N=24,lookback=720,comp=0.5,volx=1.5):
    h=df.high.values;l=df.low.values;c=df.close.values;v=df.volume.values;n=len(df);sig=[]
    hh=pd.Series(h).rolling(N).max().values; ll=pd.Series(l).rolling(N).min().values; box=hh-ll
    boxmed=pd.Series(box).rolling(lookback).median().values; vavg=pd.Series(v).rolling(20).mean().shift(1).values
    for i in range(lookback+N,n):
        bh=hh[i-1];bl=ll[i-1];H=box[i-1]
        if not (H>0 and boxmed[i-1]>0 and H<=comp*boxmed[i-1]): continue
        if vavg[i]>0 and v[i]<volx*vavg[i]: continue
        if c[i]>bh: sig.append((i,1,bh,H))
        elif c[i]<bl: sig.append((i,-1,bl,H))
    return sig

GEOS=[(1.0,0.5),(0.5,0.5),(0.5,1.0),(1.0,1.0)]
for label,D,pat,end,fund_avail in [("SET-A mr_edge 1h 6/1-8/3",DA,"*_1h.pkl",A_END,True),("SET-B 400d parquet 1h ->5/31",DB,"*_1h_400d.parquet",B_END,False)]:
    files=sorted(glob.glob(f"{D}/{pat}")); data={};fr={}
    for f in files:
        s=os.path.basename(f).split("_1h")[0]
        df=pd.read_pickle(f) if f.endswith(".pkl") else pd.read_parquet(f)
        if df.index.tz is None: df.index=df.index.tz_localize("UTC")
        df=df[df.index<=end]; data[s]=df
        fr[s]=sorted((int(r["ts"]),float(r["rate"])) for r in json.load(open(f"{D}/funding_{s}.json"))) if fund_avail else None
    any_df=next(iter(data.values())); days=(any_df.index[-1]-any_df.index[0]).days
    print(f"\n##### {label}: {len(data)} syms, {days} days, bars(first sym)={len(any_df)} {any_df.index[0]}..{any_df.index[-1]}")
    for name,fn,maxb in [("M2 1h prior-NR-day breakout",m2_signals,48),("M4 1h box-compression breakout",m4_signals,48)]:
        sigs={s:fn(data[s]) for s in data}
        print(f"== {name}: raw signals={sum(len(v) for v in sigs.values())}")
        for tp,sl in GEOS:
            tr=[]
            for s in data: tr+=sim(data[s],fr[s],sigs[s],tp,sl,maxb,s)
            report(name,tr,f"TP={tp}H SL={sl}H hold<={maxb}h",days)
        tr=[]
        for s in data: tr+=sim(data[s],fr[s],sigs[s],1.0,0.5,maxb,s)
        for side in (1,-1): report(name+(" LONG" if side==1 else " SHORT"),[t for t in tr if t["side"]==side],"TP=1.0H SL=0.5H",days)
