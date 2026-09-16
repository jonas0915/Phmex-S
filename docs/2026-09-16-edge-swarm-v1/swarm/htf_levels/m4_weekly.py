"""M4: prior-7-day extreme sweep-and-reclaim on 1h CLOSED bars, TP = weekly midpoint, SL = sweep extreme -/+ 1.0*ATR(1h), hold <= 5 days.
Same costs/fill model as screen.py. Pre-declared single cell + one hold variant, reported regardless."""
import numpy as np, pandas as pd, json
from screen import load, atr1h, daily, simulate, summarize, SYMS, OOS_START
def m4(d5,d1, sweep_atr=0.10, reclaim_within_h=24, sl_atr=1.0, tp_frac=0.5, hold_bars=1440, lookback=7):
    dd=daily(d5); atr=atr1h(d1)
    wh=dd.high.rolling(lookback).max().shift(1); wl=dd.low.rolling(lookback).min().shift(1)
    h1=d1.copy(); h1["atr"]=atr; h1["wh"]=wh.reindex(h1.index,method="ffill"); h1["wl"]=wl.reindex(h1.index,method="ffill")
    pos5=d5.index.get_indexer(h1.index+pd.Timedelta("55min"))
    ent=[]; sweep_low=None; sl_k=None; sweep_high=None; sh_k=None; cool_long=-999; cool_short=-999
    for k in range(len(h1)):
        r=h1.iloc[k]; i=pos5[k]
        if i<0 or np.isnan(r.wh) or np.isnan(r.atr): continue
        if r.low < r.wl - sweep_atr*r.atr:
            sweep_low = r.low if sweep_low is None else min(sweep_low,r.low); sl_k=k
        if sweep_low is not None and r.close>r.wl and k-sl_k<=reclaim_within_h and k-cool_long>24:
            ent.append(dict(i=i,side="long",sl=sweep_low-sl_atr*r.atr,tp=r.wl+tp_frac*(r.wh-r.wl),hold_bars=hold_bars)); sweep_low=None; cool_long=k
        if r.high > r.wh + sweep_atr*r.atr:
            sweep_high = r.high if sweep_high is None else max(sweep_high,r.high); sh_k=k
        if sweep_high is not None and r.close<r.wh and k-sh_k<=reclaim_within_h and k-cool_short>24:
            ent.append(dict(i=i,side="short",sl=sweep_high+sl_atr*r.atr,tp=r.wh-tp_frac*(r.wh-r.wl),hold_bars=hold_bars)); sweep_high=None; cool_short=k
    return simulate(d5,ent)
if __name__=="__main__":
    data={s:load(s) for s in SYMS}; out={}
    cells={"M4_week_sweep_reclaim": lambda d5,d1: m4(d5,d1),
           "M4_var_tp_quarter":     lambda d5,d1: m4(d5,d1,tp_frac=0.25),
           "M4_var_lookback14":     lambda d5,d1: m4(d5,d1,lookback=14)}
    for name,fn in cells.items():
        allt=[]; per={}
        for s,(d5,d1) in data.items():
            t=fn(d5,d1)
            for x in t: x["sym"]=s
            allt+=t; per[s]=(len(t), round(sum(x["net"] for x in t),2))
        summarize(name, allt, OOS_START); print("   per-symbol (n,total$):", per)
        # side split
        for side in ("long","short"):
            tt=[t for t in allt if t["side"]==side and pd.Timestamp(t["ts"])<OOS_START]
            if tt: print(f"   TRAIN {side}: n={len(tt)} net/t=${np.mean([t['net'] for t in tt]):.4f} WR={np.mean([t['net']>0 for t in tt]):.3f}")
        out[name]=allt
    json.dump(out, open("trades_m4.json","w"))
