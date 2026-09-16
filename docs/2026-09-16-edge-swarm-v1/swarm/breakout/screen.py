#!/usr/bin/env python3
"""Breakout-lens screen (read-only). Data: reports/cache/mr_edge_20260601_20260903 (Phemex, 35 syms).
TRAIN window only: 2026-06-01 -> 2026-08-03 23:59Z. Holdout 8/4->9/2 deliberately NOT read.
Costs: taker entry+exit 0.06%+0.06% = 0.12% of notional, + 0.05% slippage (bot SLIPPAGE_PERCENT) = 0.17% RT.
Funding: applied at each 8h stamp crossed while in position, sign per Phemex (rate>0: long pays).
Fill model: entry at next bar OPEN after the closed signal bar (closed-bar rule -> no forming-bar trap).
Exit: SL/TP intrabar; if both touched in the same bar -> SL (pessimistic). Time exit at bar close.
Notional $150 (= $15 margin x 10x, bot's live sizing)."""
import glob, json, os, sys, math, random
import numpy as np, pandas as pd
D="/Users/jonaspenaso/Desktop/Phmex-S/reports/cache/mr_edge_20260601_20260903"
TRAIN_END=pd.Timestamp("2026-08-03 23:59:59+00:00")
FEE_RT=0.0012; SLIP_RT=0.0005; NOTIONAL=150.0
random.seed(7); np.random.seed(7)

def load(sym,tf):
    df=pd.read_pickle(f"{D}/{sym}_{tf}.pkl")
    df=df[df.index<=TRAIN_END]
    return df
def funding(sym):
    j=json.load(open(f"{D}/funding_{sym}.json"))
    return sorted((int(r["ts"]),float(r["rate"])) for r in j)

def fund_cost(fr, t_in_ms, t_out_ms, side):
    c=0.0
    for ts,rate in fr:
        if t_in_ms < ts <= t_out_ms:
            c += rate if side==1 else -rate   # long pays positive rate
    return c

def sim(df, fr, signals, tp_mult, sl_mult, max_bars, sym):
    """signals: list of (i_signal_bar, side, level, H). enter at open of i+1."""
    o=df.open.values; h=df.high.values; l=df.low.values; c=df.close.values; idx=df.index
    out=[]; busy_until=-1
    for i,side,level,H in signals:
        if i+1>=len(df) or i<=busy_until: continue
        e=o[i+1]*(1+ (SLIP_RT/2 if side==1 else -SLIP_RT/2))
        tp = e + side*tp_mult*H; sl = e - side*sl_mult*H
        j=i+1; res=None; px=None
        last=min(len(df)-1, i+1+max_bars)
        while j<=last:
            hit_sl = (l[j]<=sl) if side==1 else (h[j]>=sl)
            hit_tp = (h[j]>=tp) if side==1 else (l[j]<=tp)
            if hit_sl: res="SL"; px=sl; break
            if hit_tp: res="TP"; px=tp; break
            j+=1
        if res is None: j=last; res="TIME"; px=c[j]
        px = px*(1-(SLIP_RT/2 if side==1 else -SLIP_RT/2))
        gross=side*(px-e)/e
        fnd=fund_cost(fr, int(idx[i+1].value//1e6), int(idx[j].value//1e6), side)
        net=gross-FEE_RT-fnd
        out.append(dict(sym=sym,t=idx[i+1],side=side,res=res,gross=gross,net=net,fund=fnd,bars=j-(i+1),H=H))
        busy_until=j
    return out

def boot_ci(x, n=3000):
    x=np.asarray(x); 
    if len(x)<5: return (float('nan'),float('nan'))
    m=[x[np.random.randint(0,len(x),len(x))].mean() for _ in range(n)]
    return (float(np.percentile(m,2.5)), float(np.percentile(m,97.5)))

def report(name, trades, geo):
    if not trades: print(f"{name} {geo}: 0 trades"); return
    net=np.array([t["net"] for t in trades]); gross=np.array([t["gross"] for t in trades])
    res=[t["res"] for t in trades]; n=len(net)
    tp=res.count("TP")/n; sl=res.count("SL")/n
    lo,hi=boot_ci(net)
    exbtc=np.array([t["net"] for t in trades if not t["sym"].startswith("BTC")])
    lo2,hi2=boot_ci(exbtc) if len(exbtc)>=5 else (float('nan'),float('nan'))
    days=(TRAIN_END-pd.Timestamp("2026-06-01",tz="UTC")).days
    print(f"{name} {geo}: n={n} ({n/days*7:.1f}/wk all syms) TP%={tp*100:.1f} SL%={sl*100:.1f} TIME%={(1-tp-sl)*100:.1f} "
          f"gross={gross.mean()*1e4:.1f}bps net={net.mean()*1e4:.1f}bps [{lo*1e4:.1f},{hi*1e4:.1f}] "
          f"$/t@150={net.mean()*NOTIONAL:.4f} exBTC net={exbtc.mean()*1e4 if len(exbtc) else float('nan'):.1f}bps [{lo2*1e4:.1f},{hi2*1e4:.1f}] "
          f"fund={np.mean([t['fund'] for t in trades])*1e4:.2f}bps medH={np.median([t['H'] for t in trades])*1e4:.0f}bps")

# ---- Mechanism 1: 5m box-compression breakout ----
def m1_signals(df, N=12, lookback=288, comp=0.5, volx=1.5):
    h=df.high.values; l=df.low.values; c=df.close.values; v=df.volume.values
    n=len(df); sig=[]
    hh=pd.Series(h).rolling(N).max().values; ll=pd.Series(l).rolling(N).min().values
    box=hh-ll
    boxmed=pd.Series(box).rolling(lookback).median().values
    vavg=pd.Series(v).rolling(20).mean().shift(1).values
    for i in range(lookback+N, n):
        # box = bars i-N .. i-1 (the N completed bars BEFORE the trigger bar)
        bh=hh[i-1]; bl=ll[i-1]; H=box[i-1]
        if not (H>0 and boxmed[i-1]>0 and H<=comp*boxmed[i-1]): continue
        if vavg[i]>0 and v[i]<volx*vavg[i]: continue
        if c[i]>bh: sig.append((i,1,bh,H))
        elif c[i]<bl: sig.append((i,-1,bl,H))
    return sig

# ---- Mechanism 3: wide-range-bar continuation on 5m ----
def m3_signals(df, k=3.0, closepos=0.8):
    h=df.high.values; l=df.low.values; c=df.close.values; o=df.open.values
    tr=np.maximum(h-l, np.maximum(abs(h-np.roll(c,1)), abs(l-np.roll(c,1))))
    atr=pd.Series(tr).rolling(20).mean().shift(1).values
    sig=[]
    for i in range(30,len(df)):
        rng=h[i]-l[i]
        if not (atr[i]>0 and rng>=k*atr[i]): continue
        pos=(c[i]-l[i])/rng
        if pos>=closepos and c[i]>o[i]: sig.append((i,1,h[i],rng))
        elif pos<=1-closepos and c[i]<o[i]: sig.append((i,-1,l[i],rng))
    return sig

# ---- Mechanism 2: prior-day narrow-range breakout on 1h ----
def m2_signals(df1h, nr_frac=0.7, avg_days=20):
    df=df1h.copy(); df["day"]=df.index.floor("D")
    daily=df.groupby("day").agg(dh=("high","max"),dl=("low","min"))
    daily["rng"]=daily.dh-daily.dl
    daily["avg"]=daily.rng.rolling(avg_days).mean().shift(1)
    daily["prev_h"]=daily.dh.shift(1); daily["prev_l"]=daily.dl.shift(1); daily["prev_rng"]=daily.rng.shift(1); daily["prev_avg"]=daily.avg.shift(1)
    sig=[]; days=df.day.values; c=df.close.values
    fired=set()
    for i in range(len(df)):
        d=days[i]; row=daily.loc[d]
        if not (row.prev_rng>0 and row.prev_avg>0 and row.prev_rng<=nr_frac*row.prev_avg): continue
        if d in fired: continue
        if c[i]>row.prev_h: sig.append((i,1,row.prev_h,row.prev_rng)); fired.add(d)
        elif c[i]<row.prev_l: sig.append((i,-1,row.prev_l,row.prev_rng)); fired.add(d)
    return sig

syms=sorted(set(os.path.basename(f).replace("_5m.pkl","") for f in glob.glob(D+"/*_5m.pkl")))
print("symbols:",len(syms))
GEOS=[(1.0,0.5),(0.5,0.5),(0.5,1.0),(1.0,1.0)]
d5={s:load(s,"5m") for s in syms}; d1={s:load(s,"1h") for s in syms}; fr={s:funding(s) for s in syms}
print("train bars 5m (BTC):",len(d5["BTC_USDT_USDT"]), d5["BTC_USDT_USDT"].index[0], d5["BTC_USDT_USDT"].index[-1])

for name,fn,tfd,maxb in [("M1 5m box-compression breakout",m1_signals,d5,24),("M3 5m wide-range-bar continuation",m3_signals,d5,24),("M2 1h prior-NR-day breakout",m2_signals,d1,48)]:
    sigs={s:fn(tfd[s]) for s in syms}
    print(f"\n== {name}: raw signals={sum(len(v) for v in sigs.values())}")
    for tp,sl in GEOS:
        tr=[]
        for s in syms: tr+=sim(tfd[s],fr[s],sigs[s],tp,sl,maxb,s)
        report(name,tr,f"TP={tp}H SL={sl}H hold<={maxb}bars")
    # side split for the (1.0,0.5) cell
    tr=[]
    for s in syms: tr+=sim(tfd[s],fr[s],sigs[s],1.0,0.5,maxb,s)
    for side in (1,-1):
        sub=[t for t in tr if t["side"]==side]
        report(name+(" LONG" if side==1 else " SHORT"),sub,"TP=1.0H SL=0.5H")
    # 1R-first rate: did +0.5H get touched before -0.5H? (partial-at-1R feasibility) via (0.5,0.5) cell
