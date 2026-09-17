"""EXPLORATORY probe (not the screen, numbers are not evidence). vol_structure lens.
Post-shock continuation after compression->expansion at the daily horizon, long_1h train era only.
"""
import sys, json
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, bootstrap_ci as bc, fee_math as fm

COMP = float(sys.argv[1]) if len(sys.argv) > 1 else 0.75
SHOCK = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
TP = float(sys.argv[3]) if len(sys.argv) > 3 else 200
HOLD = int(sys.argv[4]) if len(sys.argv) > 4 else 48

def signals(df):
    h, l, c, v = df["high"], df["low"], df["close"], df["volume"]
    r24 = h.rolling(24).max() / l.rolling(24).min() - 1.0
    base = r24.rolling(480).mean().shift(24)          # 20-day mean of trailing-day range, excluding the shock day
    v24 = v.rolling(24).sum()
    vbase = v24.rolling(480).mean().shift(24)
    ret24 = c / c.shift(24) - 1.0
    calm = (r24.shift(24) / base) <= COMP              # prior day was compressed
    shock = (r24 / base) >= SHOCK
    vol_ok = (v24 / vbase) >= 2.0
    directional = ret24.abs() >= 0.5 * r24
    cond = calm & shock & vol_ok & directional
    first = cond & ~cond.shift(1, fill_value=False)
    s = pd.Series(0, index=df.index, dtype=int)
    s[first & (ret24 > 0)] = 1
    s[first & (ret24 < 0)] = -1
    return s

syms = ld.list_symbols("mr_edge")
rows = []
spans = {}
for sym in syms:
    df = ld.load_ohlcv(sym, "1h", era="train", dataset="mr_edge")
    spans[sym] = (str(df.index.min()), str(df.index.max()), len(df))
    sig = signals(df)
    tr = sc.simulate(df, sig, TP, TP, HOLD)
    tr.insert(0, "symbol", sym)
    rows.append(tr)
tr = pd.concat(rows, ignore_index=True)
n = len(tr)
out = {"params": {"COMP": COMP, "SHOCK": SHOCK, "TP": TP, "HOLD": HOLD}, "n": n,
       "net_bps_mean": float(tr.net_bps.mean()) if n else None,
       "ci95": list(bc.mean_ci(tr.net_bps.to_numpy())) if n >= 2 else None,
       "wr": float((tr.net_bps > 0).mean()) if n else None,
       "p_star": fm.p_star(TP),
       "per_symbol": tr.groupby("symbol").size().to_dict(),
       "by_side": tr.groupby("side").net_bps.agg(["count", "mean"]).to_dict(),
       "exit_reason": tr.exit_reason.value_counts().to_dict(),
       "spans": spans}
print(json.dumps(out, indent=1, default=str))
