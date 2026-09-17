"""EXPLORATORY — NOT the screen, numbers are not evidence.
Probe A: fade the closed 1h bar that covers the BRRNY TWAP window (15:00-16:00 New York)
on weekdays; enter next open; symmetric TP/SL; controls at other UTC hours.
Dataset long_1h, era=train only. Lens: dealer_inventory (ETF issuer / AP fix execution).
"""
import json, sys
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm, bootstrap_ci as bc

OUT = "research/swarm/runs/2026-09-17-0732/exploratory/dealer_inventory/probe_a_etf_fix_fade.out.json"


def ny_hour(idx):
    return idx.tz_convert("America/New_York").hour


def make_sig(df, ny_h, thr_bps, weekday_only=True):
    idx = df.index
    ret = (df["close"] / df["open"] - 1.0).to_numpy() * 1e4
    h = ny_hour(idx)
    wk = idx.tz_convert("America/New_York").weekday
    evt = (h == ny_h)
    if weekday_only:
        evt = evt & (wk < 5)
    sig = pd.Series(0, index=idx, dtype=int)
    sig[evt & (ret <= -thr_bps)] = 1
    sig[evt & (ret >= thr_bps)] = -1
    return sig


def cell(syms, ny_h, thr, tp, hold):
    trades = []
    for s in syms:
        df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
        tr = sc.simulate(df, make_sig(df, ny_h, thr), tp, tp, hold)
        tr["sym"] = s
        trades.append(tr)
    t = pd.concat(trades) if trades else pd.DataFrame()
    if len(t) == 0:
        return {"n": 0}
    lo, hi = bc.mean_ci(t["net_bps"])
    return {"n": int(len(t)), "net_mean": float(t["net_bps"].mean()), "gross_mean": float(t["gross_bps"].mean()),
            "ci95": [float(lo), float(hi)], "wr_net": float((t["net_bps"] > 0).mean()), "p_star": fm.p_star(tp),
            "exit_mix": t["exit_reason"].value_counts().to_dict(),
            "per_sym": {k: round(float(v), 1) for k, v in t.groupby("sym")["net_bps"].mean().items()}}


res = {}
etf = ["BTC", "ETH"]
for ny_h in [15, 11, 13, 17, 19, 3]:          # 15 = fix window; others = controls
    for thr in [0, 20, 40]:
        for tp, hold in [(100, 3), (100, 6), (150, 6)]:
            key = f"nyh{ny_h}|thr{thr}|tp{tp}|hold{hold}"
            res[key] = cell(etf, ny_h, thr, tp, hold)
            print(key, json.dumps(res[key])[:200], flush=True)
# broader universe at the fix hour
for thr in [20, 40]:
    key = f"nyh15|thr{thr}|tp100|hold6|univ4"
    res[key] = cell(["BTC", "ETH", "SOL", "XRP"], 15, thr, 100, 6)
    print(key, json.dumps(res[key])[:200])
json.dump(res, open(OUT, "w"), indent=1)
