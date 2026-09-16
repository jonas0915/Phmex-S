"""Screening-grade replay of three higher-timeframe LEVEL mechanisms (read-only on repo data).
Data: Phmex-S/scripts/research/mr-universe-scan-2026-08-01/cache/<SYM>_{5m,1h}_400d.parquet (Phemex, 2025-06-27 -> 2026-08-01)
      + reports/cache/mr_edge_20260601_20260903/<SYM>_{5m,1h}.pkl for the 2026-08-02 -> 2026-09-02 tail (OOS).
Costs: taker-taker 0.12% RT + 0.03% slippage per side (0.18% RT total), funding 0.01%/8h always charged (house convention).
Fills: signal on CLOSED 5m bar, entry = next 5m open; SL/TP by touch on later bars; both touched in one bar -> SL. One position per symbol.
Notional $60. Nothing here is a verdict; it is a screen."""
import sys, json, math, numpy as np, pandas as pd, os
ROOT="/Users/jonaspenaso/Desktop/Phmex-S"
PQ=ROOT+"/scripts/research/mr-universe-scan-2026-08-01/cache"
PK=ROOT+"/reports/cache/mr_edge_20260601_20260903"
SYMS=["ETH","SOL","XRP","DOGE","LINK","SUI","ADA","1000PEPE","1000SHIB"]
NOTIONAL=60.0; FEE_RT=0.0012; SLIP=0.0003; FUND8H=0.0001
OOS_START=pd.Timestamp("2026-08-02",tz="UTC")

def load(sym):
    a5=pd.read_parquet(f"{PQ}/{sym}_USDT_USDT_5m_400d.parquet"); a1=pd.read_parquet(f"{PQ}/{sym}_USDT_USDT_1h_400d.parquet")
    b5=pd.read_pickle(f"{PK}/{sym}_USDT_USDT_5m.pkl"); b1=pd.read_pickle(f"{PK}/{sym}_USDT_USDT_1h.pkl")
    d5=pd.concat([a5,b5[b5.index>a5.index[-1]]]); d1=pd.concat([a1,b1[b1.index>a1.index[-1]]])
    d5=d5[~d5.index.duplicated()].sort_index(); d1=d1[~d1.index.duplicated()].sort_index()
    return d5,d1

def atr1h(d1,n=14):
    h,l,c=d1.high,d1.low,d1.close; pc=c.shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def daily(d5):
    d=d5.resample("1D").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    return d

def simulate(d5, entries):
    """entries: list of dict(ts_signal_idx=i, side, sl, tp, hold_bars). Returns trades."""
    trades=[]; busy_until=-1
    o=d5.open.values; h=d5.high.values; l=d5.low.values; c=d5.close.values; idx=d5.index
    for e in entries:
        i=e["i"]
        if i<=busy_until or i+1>=len(d5): continue
        ep=o[i+1]; side=e["side"]; sl=e["sl"]; tp=e["tp"]
        if side=="long" and not (sl<ep<tp): continue
        if side=="short" and not (tp<ep<sl): continue
        ep_eff = ep*(1+SLIP) if side=="long" else ep*(1-SLIP)
        j_end=min(len(d5)-1, i+1+e["hold_bars"]); exit_px=None; reason=None; j=i+1
        for j in range(i+1, j_end+1):
            if side=="long":
                hit_sl = l[j]<=sl; hit_tp = h[j]>=tp
            else:
                hit_sl = h[j]>=sl; hit_tp = l[j]<=tp
            if j==i+1:  # entry bar: only allow SL (conservative), TP needs a later bar
                if hit_sl: exit_px=sl; reason="SL"; break
                continue
            if hit_sl and hit_tp: exit_px=sl; reason="SL"; break
            if hit_sl: exit_px=sl; reason="SL"; break
            if hit_tp: exit_px=tp; reason="TP"; break
        if exit_px is None: exit_px=c[j_end]; reason="TIME"; j=j_end
        xp_eff = exit_px*(1-SLIP) if side=="long" else exit_px*(1+SLIP)
        gross = (xp_eff/ep_eff-1) if side=="long" else (1-xp_eff/ep_eff)
        hold_h=(idx[j]-idx[i+1]).total_seconds()/3600
        net = gross*NOTIONAL - FEE_RT*NOTIONAL - FUND8H*NOTIONAL*hold_h/8
        trades.append(dict(ts=str(idx[i+1]),side=side,reason=reason,net=round(net,4),gross_bps=round(gross*1e4,1),hold_h=round(hold_h,2),
                           rr=round(abs(tp-ep)/abs(ep-sl),2)))
        busy_until=j
    return trades

# ---------- M1: prior-day extreme sweep-and-reclaim (taker at reclaim close) ----------
def m1(d5,d1,sweep_atr=0.10, reclaim_within=6, sl_atr=0.25, tp_frac=0.5, hold_bars=288):
    dd=daily(d5); atr=atr1h(d1).reindex(d5.index,method="ffill")
    pdh=dd.high.shift(1).reindex(d5.index,method="ffill"); pdl=dd.low.shift(1).reindex(d5.index,method="ffill")
    day=d5.index.floor("1D")
    ent=[]; c=d5.close.values; l=d5.low.values; h=d5.high.values
    n=len(d5); sweep_low=None; sweep_i=None; sweep_high=None; sweep_ih=None; last_day=None; done_long=False; done_short=False
    P=pdl.values; H=pdh.values; A=atr.values; D=day.values
    for i in range(n):
        if D[i]!=last_day: last_day=D[i]; sweep_low=None; sweep_high=None; done_long=False; done_short=False
        if np.isnan(P[i]) or np.isnan(A[i]): continue
        # sweep below PDL
        if l[i] < P[i]-sweep_atr*A[i]:
            sweep_low = l[i] if sweep_low is None else min(sweep_low,l[i]); sweep_i=i
        if sweep_low is not None and not done_long and c[i]>P[i] and i-sweep_i<=reclaim_within:
            sl=sweep_low - sl_atr*A[i]; tp=P[i]+tp_frac*(H[i]-P[i])
            ent.append(dict(i=i,side="long",sl=sl,tp=tp,hold_bars=hold_bars)); done_long=True; sweep_low=None
        if h[i] > H[i]+sweep_atr*A[i]:
            sweep_high = h[i] if sweep_high is None else max(sweep_high,h[i]); sweep_ih=i
        if sweep_high is not None and not done_short and c[i]<H[i] and i-sweep_ih<=reclaim_within:
            sl=sweep_high + sl_atr*A[i]; tp=H[i]-tp_frac*(H[i]-P[i])
            ent.append(dict(i=i,side="short",sl=sl,tp=tp,hold_bars=hold_bars)); done_short=True; sweep_high=None
    return simulate(d5,ent)

# ---------- M2: prior-day range breakout, measured-move TP ----------
def m2(d5,d1,vol_mult=1.5, sl_atr=0.5, tp_range=1.0, hold_bars=576):
    dd=daily(d5); atr=atr1h(d1)
    v20=d1.volume.rolling(20).mean()
    pdh=dd.high.shift(1); pdl=dd.low.shift(1)
    h1=d1.copy(); h1["atr"]=atr; h1["v20"]=v20
    h1["pdh"]=pdh.reindex(h1.index,method="ffill"); h1["pdl"]=pdl.reindex(h1.index,method="ffill")
    pos5=d5.index.get_indexer(h1.index+pd.Timedelta("55min"))  # the 5m bar closing the 1h bar
    ent=[]; last_day=None; dl=False; ds=False
    for k in range(len(h1)):
        r=h1.iloc[k]; i=pos5[k]
        if i<0 or np.isnan(r.pdh) or np.isnan(r.atr) or np.isnan(r.v20): continue
        dday=h1.index[k].floor("1D")
        if dday!=last_day: last_day=dday; dl=False; ds=False
        rng=r.pdh-r.pdl
        if not dl and r.close>r.pdh and r.volume>=vol_mult*r.v20:
            ent.append(dict(i=i,side="long",sl=r.pdh-sl_atr*r.atr,tp=r.close+tp_range*rng,hold_bars=hold_bars)); dl=True
        if not ds and r.close<r.pdl and r.volume>=vol_mult*r.v20:
            ent.append(dict(i=i,side="short",sl=r.pdl+sl_atr*r.atr,tp=r.close-tp_range*rng,hold_bars=hold_bars)); ds=True
    return simulate(d5,ent)

# ---------- M3: prior-week volume-profile value-area re-entry -> POC ----------
def vprofile(seg, nbins=50, va=0.70):
    lo=seg.low.min(); hi=seg.high.max()
    if hi<=lo: return None
    edges=np.linspace(lo,hi,nbins+1); vol=np.zeros(nbins)
    # spread each bar's volume evenly across bins it spans
    L=seg.low.values; H=seg.high.values; V=seg.volume.values
    for a,b,v in zip(L,H,V):
        i0=np.searchsorted(edges,a,side="right")-1; i1=np.searchsorted(edges,b,side="right")-1
        i0=max(0,min(nbins-1,i0)); i1=max(0,min(nbins-1,i1))
        vol[i0:i1+1]+=v/(i1-i0+1)
    poc=int(vol.argmax()); tot=vol.sum(); acc=vol[poc]; lo_i=hi_i=poc
    while acc<va*tot:
        up=vol[hi_i+1] if hi_i+1<nbins else -1; dn=vol[lo_i-1] if lo_i-1>=0 else -1
        if up>=dn: hi_i+=1; acc+=up
        else: lo_i-=1; acc+=dn
    mid=(edges[:-1]+edges[1:])/2
    return dict(poc=mid[poc], val=edges[lo_i], vah=edges[hi_i+1])

def m3(d5,d1,window_days=7, sl_atr=1.0, hold_bars=864, use_1h_close=True):
    atr=atr1h(d1).reindex(d5.index,method="ffill").values
    days=daily(d5).index
    ent=[]; c=d5.close.values; l=d5.low.values; h=d5.high.values; idx=d5.index
    day_of=d5.index.floor("1D")
    prof_by_day={}
    for k in range(window_days,len(days)):
        seg=d5[(d5.index>=days[k-window_days])&(d5.index<days[k])]
        if len(seg)<window_days*200: continue
        prof_by_day[days[k]]=vprofile(seg)
    outside_low=False; outside_high=False; last_day=None; dl=ds=False
    hour_close = (d5.index.minute==55)
    for i in range(len(d5)):
        d=day_of[i]
        if d!=last_day: last_day=d; dl=ds=False
        p=prof_by_day.get(d)
        if p is None or np.isnan(atr[i]): continue
        if c[i]<p["val"]: outside_low=True
        if c[i]>p["vah"]: outside_high=True
        if use_1h_close and not hour_close[i]: continue
        if outside_low and not dl and c[i]>p["val"] and c[i]<p["poc"]:
            ent.append(dict(i=i,side="long",sl=p["val"]-sl_atr*atr[i],tp=p["poc"],hold_bars=hold_bars)); dl=True; outside_low=False
        if outside_high and not ds and c[i]<p["vah"] and c[i]>p["poc"]:
            ent.append(dict(i=i,side="short",sl=p["vah"]+sl_atr*atr[i],tp=p["poc"],hold_bars=hold_bars)); ds=True; outside_high=False
    return simulate(d5,ent)

def boot_ci(x,B=4000,seed=1):
    x=np.asarray(x); rng=np.random.default_rng(seed)
    if len(x)<5: return (float("nan"),float("nan"))
    m=[rng.choice(x,len(x),replace=True).mean() for _ in range(B)]
    return (float(np.percentile(m,2.5)),float(np.percentile(m,97.5)))

def summarize(name, trades, split):
    for label,tt in [("TRAIN",[t for t in trades if pd.Timestamp(t["ts"])<split]),("OOS_tail",[t for t in trades if pd.Timestamp(t["ts"])>=split])]:
        if not tt: print(f"{name} {label}: n=0"); continue
        nets=[t["net"] for t in tt]; n=len(tt); wr=np.mean([x>0 for x in nets]); lo,hi=boot_ci(nets)
        reasons=pd.Series([t["reason"] for t in tt]).value_counts().to_dict()
        gross=np.mean([t["gross_bps"] for t in tt]); hold=np.median([t["hold_h"] for t in tt]); rr=np.median([t["rr"] for t in tt])
        print(f"{name} {label}: n={n} net/t=${np.mean(nets):.4f} CI95=[{lo:.4f},{hi:.4f}] total=${sum(nets):.2f} WR={wr:.3f} gross_bps={gross:.1f} exits={reasons} med_hold_h={hold:.1f} med_RR={rr:.2f}")

if __name__=="__main__":
    which=sys.argv[1] if len(sys.argv)>1 else "all"
    data={s:load(s) for s in SYMS}
    for s,(d5,d1) in data.items(): print(s, d5.index[0], d5.index[-1], len(d5))
    out={}
    cells={
      "M1_sweep_reclaim":      lambda d5,d1: m1(d5,d1),
      "M1_var_tp_full":        lambda d5,d1: m1(d5,d1,tp_frac=1.0),
      "M1_var_tp_quarter":     lambda d5,d1: m1(d5,d1,tp_frac=0.25),
      "M2_pdr_breakout":       lambda d5,d1: m2(d5,d1),
      "M2_var_novolfilter":    lambda d5,d1: m2(d5,d1,vol_mult=0.0),
      "M3_weekVA_reentry":     lambda d5,d1: m3(d5,d1),
      "M3_var_dayVA_reentry":  lambda d5,d1: m3(d5,d1,window_days=1,hold_bars=288),
    }
    for name,fn in cells.items():
        if which!="all" and not name.startswith(which): continue
        allt=[]; per={}
        for s,(d5,d1) in data.items():
            t=fn(d5,d1)
            for x in t: x["sym"]=s
            allt+=t; per[s]=(len(t), round(sum(x["net"] for x in t),2))
        summarize(name, allt, OOS_START)
        print("   per-symbol (n,total$):", per)
        out[name]=allt
    json.dump(out, open(os.path.dirname(os.path.abspath(__file__))+"/trades.json","w"))
