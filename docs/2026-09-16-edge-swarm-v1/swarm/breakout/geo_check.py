import glob, json, os, numpy as np, pandas as pd, importlib.util, sys, io, contextlib
# import screen2 functions silently (its body runs; suppress prints)
buf=io.StringIO()
with contextlib.redirect_stdout(buf):
    spec=importlib.util.spec_from_file_location("s2","screen2.py"); s2=importlib.util.module_from_spec(spec); spec.loader.exec_module(s2)
np.random.seed(7)
def run(label,D,pat,end,fund_avail,fn,tp,sl,maxb):
    data={};fr={}
    for f in sorted(glob.glob(f"{D}/{pat}")):
        s=os.path.basename(f).split("_1h")[0] if "_1h" in f else os.path.basename(f).split("_5m")[0]
        df=pd.read_pickle(f) if f.endswith(".pkl") else pd.read_parquet(f)
        if df.index.tz is None: df.index=df.index.tz_localize("UTC")
        data[s]=df[df.index<=end]
        fr[s]=sorted((int(r["ts"]),float(r["rate"])) for r in json.load(open(f"{D}/funding_{s}.json"))) if fund_avail else None
    tr=[]
    for s in data: tr+=s2.sim(data[s],fr[s],fn(data[s]),tp,sl,maxb,s)
    Hpct=[t["H"]/ (data[t["sym"]].loc[t["t"],"open"]) for t in tr]
    per={}
    for t in tr: per.setdefault(t["sym"],[]).append(t["net"])
    pos=sum(1 for s,v in per.items() if np.mean(v)>0)
    net=np.array([t["net"] for t in tr])
    print(f"{label} TP={tp}H SL={sl}H: n={len(tr)} medH/price={np.median(Hpct)*100:.2f}% (TP dist={tp*np.median(Hpct)*100:.2f}%, SL dist={sl*np.median(Hpct)*100:.2f}%) net={net.mean()*1e4:.1f}bps symbols net>0: {pos}/{len(per)} median bars held={np.median([t['bars'] for t in tr]):.0f}")
A=(s2.DA,"*_1h.pkl",s2.A_END,True); B=(s2.DB,"*_1h_400d.parquet",s2.B_END,False)
for tp,sl in [(0.5,1.0),(1.0,0.5),(1.0,1.0)]:
    run("SET-A M2 prior-NR-day",*A,s2.m2_signals,tp,sl,48)
    run("SET-B M2 prior-NR-day",*B,s2.m2_signals,tp,sl,48)
for tp,sl in [(1.0,0.5),(0.5,1.0)]:
    run("SET-A M4 1h box-comp",*A,s2.m4_signals,tp,sl,48)
    run("SET-B M4 1h box-comp",*B,s2.m4_signals,tp,sl,48)
# 5m M1 geometry size
spec=importlib.util.spec_from_file_location("s1","screen.py")
src=open("screen.py").read().split("syms=sorted")[0]
ns={}; exec(src,ns)
D5=ns["D"]; tr=[]; Hp=[]
for f in sorted(glob.glob(D5+"/*_5m.pkl")):
    s=os.path.basename(f).replace("_5m.pkl",""); df=ns["load"](s,"5m"); sig=ns["m1_signals"](df)
    t=ns["sim"](df,ns["funding"](s),sig,1.0,0.5,24,s); tr+=t
    Hp+=[x["H"]/df.loc[x["t"],"open"] for x in t]
per={}
for t in tr: per.setdefault(t["sym"],[]).append(t["net"])
print(f"5m M1 box-comp TP=1.0H SL=0.5H: n={len(tr)} medH/price={np.median(Hp)*100:.3f}% symbols net>0: {sum(1 for v in per.values() if np.mean(v)>0)}/{len(per)}")
