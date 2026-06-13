#!/usr/bin/env python3
import os, json, math
import numpy as np, pandas as pd
from backtest import load, gen_signals, realize, stats, SYMBOLS

DIR = os.path.dirname(os.path.abspath(__file__))
FEE = 0.00066

def build_all(k, hold, atr_period=14, fee=FEE, slip=0.0, stop=None, tp=None):
    frames=[]
    for s in SYMBOLS:
        df = load(s)
        tr, dff = gen_signals(df, k, atr_period)
        pnl = realize(tr, dff, hold, fee_oneway=fee, slip=slip, stop=stop, tp=tp)
        if len(pnl): pnl["sym"]=s
        frames.append(pnl)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

print("="*70)
print("STEP 0: pooled time-span (all symbols share 2025-06-13 -> 2026-06-13)")
btc = load("BTC")
print("span:", btc.dt.iloc[0], "->", btc.dt.iloc[-1], " bars:", len(btc))

# ---- STEP 1: reproduce headline. Chronological 50/50 split. Tune k,hold on train, report test.
print("\n"+"="*70)
print("STEP 1: PARAM SELECTION ON TRAIN (first 50%), REPORT ON TEST (last 50%)")
# split point by calendar: use BTC midpoint timestamp
mid_ts = btc.ts.iloc[len(btc)//2]
mid_dt = pd.to_datetime(mid_ts, unit="ms")
print("split at:", mid_dt)

def split_pnl(pnl):
    tr = pnl[pd.to_datetime(pnl.dt) < mid_dt]
    te = pnl[pd.to_datetime(pnl.dt) >= mid_dt]
    return tr, te

grid_k = [2.5, 3.0, 3.5, 4.0]
grid_h = [6, 12, 18, 24]
best=None
train_table=[]
for k in grid_k:
    for h in grid_h:
        pnl = build_all(k, h)
        tr,_ = split_pnl(pnl)
        st = stats(tr)
        train_table.append((k,h,st["n"],round(st["mean_pct"],4),round(st["sharpe"],3)))
        if st["n"]>=30:
            score = st["mean_pct"]  # select on per-trade net mean (train)
            if best is None or score>best[0]:
                best=(score,k,h,st)
print("train grid (k,h,n,mean%,sharpe):")
for row in train_table: print("  ",row)
_, bk, bh, btr = best
print(f"\nBEST ON TRAIN: k={bk} hold={bh}  train mean={btr['mean_pct']:.4f}% n={btr['n']} sharpe={btr['sharpe']:.2f}")

pnl_best = build_all(bk, bh)
_, te = split_pnl(pnl_best)
ste = stats(te)
print(f"\n>>> OOS (TEST) with k={bk} hold={bh}: n={ste['n']} mean={ste['mean_pct']:.4f}%/trade "
      f"total={ste['total_pct']:.2f}% WR={ste['wr']:.1f}% sharpe={ste['sharpe']:.2f}")

# also report the claim's exact-ish params k=3.0-3.5 hold=12
for k in [3.0,3.5]:
    pnl=build_all(k,12); _,te2=split_pnl(pnl); s=stats(te2)
    print(f"    [claim params k={k} hold=12] OOS: n={s['n']} mean={s['mean_pct']:.4f}% sharpe={s['sharpe']:.2f} WR={s['wr']:.1f}%")

# ---- STEP 2: LEG DECOMPOSITION (use best params, FULL sample for power, also OOS)
print("\n"+"="*70)
print("STEP 2: LONG-LEG (fade down-bars) vs SHORT-LEG (fade up-bars)")
pnl=build_all(bk,bh)
for label, sub in [("FULL", pnl), ("OOS", pnl[pd.to_datetime(pnl.dt)>=mid_dt])]:
    longs = sub[sub.side==1]   # fading down-bars
    shorts= sub[sub.side==-1]  # fading up-bars
    sl=stats(longs); ss=stats(shorts)
    print(f"\n  [{label}]")
    print(f"    LONG  leg (fade DOWN bars): n={sl['n']} mean={sl['mean_pct']:.4f}% total={sl.get('total_pct',0):.2f}% WR={sl['wr']:.1f}% sharpe={sl['sharpe']:.2f}")
    print(f"    SHORT leg (fade UP   bars): n={ss['n']} mean={ss['mean_pct']:.4f}% total={ss.get('total_pct',0):.2f}% WR={ss['wr']:.1f}% sharpe={ss['sharpe']:.2f}")

# per-symbol leg breakdown (full)
print("\n  PER-SYMBOL (FULL sample) mean%/trade:  sym | longN longMean | shortN shortMean | allMean")
for s in SYMBOLS:
    sub=pnl[pnl.sym==s]
    L=sub[sub.side==1]; S=sub[sub.side==-1]
    print(f"    {s:5s} | {len(L):3d} {L.net.mean()*100 if len(L) else 0:+.3f}% | {len(S):3d} {S.net.mean()*100 if len(S) else 0:+.3f}% | {sub.net.mean()*100 if len(sub) else 0:+.3f}%")

pnl_best.to_csv(os.path.join(DIR,"trades_best.csv"), index=False)
with open(os.path.join(DIR,"best_params.json"),"w") as f:
    json.dump({"k":bk,"hold":bh,"oos":ste}, f, indent=2, default=str)
print("\nsaved trades_best.csv")
