"""EXPLORATORY probe #3 (NOT the screen; numbers are not evidence). Second proxy of the
Concretum 'Monday Asia open' finding: trend-following INSIDE the window Sun 19:00 -> Mon 19:00
America/New_York. At each closed bar inside the window, side = sign(trailing 6-bar close move)
if |move| >= 100 bps; TP/SL 150/150, max 12 bars. One run only, no sweep. long_1h TRAIN only.
"""
import json, sys
import pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, bootstrap_ci as bc, fee_math as fm

def signals(df):
    ny = df.index.tz_convert("America/New_York")
    in_win = ((ny.dayofweek == 6) & (ny.hour >= 19)) | ((ny.dayofweek == 0) & (ny.hour < 19))
    mv = (df["close"] / df["close"].shift(6) - 1) * 1e4
    s = pd.Series(0, index=df.index, dtype=int)
    w = pd.Series(in_win, index=df.index)
    s[w & (mv >= 100)] = 1; s[w & (mv <= -100)] = -1
    return s

rows = []; lo = hi = None
for sym in ld.list_symbols("long_1h"):
    df = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    lo = df.index.min() if lo is None else min(lo, df.index.min()); hi = df.index.max() if hi is None else max(hi, df.index.max())
    tr = sc.simulate(df, signals(df), 150, 150, 12); tr.insert(0, "symbol", sym); rows.append(tr)
t = pd.concat(rows, ignore_index=True); weeks = (hi - lo).total_seconds()/(7*86400)
out = {"label": "EXPLORATORY probe, not evidence", "n": int(len(t)), "net_bps_mean": float(t.net_bps.mean()),
       "ci95": list(bc.mean_ci(t.net_bps.to_numpy())), "wr": float((t.net_bps > 0).mean()), "p_star_150": fm.p_star(150),
       "trades_per_week": len(t)/weeks, "by_side": {int(k): {"n": int(len(g)), "net": float(g.net_bps.mean())} for k, g in t.groupby("side")},
       "exit_reasons": t.exit_reason.value_counts().to_dict()}
print(json.dumps(out, indent=1)); json.dump(out, open(sys.argv[1], "w"), indent=1)
