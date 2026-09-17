"""EXPLORATORY probe (NOT the screen; numbers are not evidence).
Sunday-reopen weekend-move continuation on long_1h TRAIN era only.
Signal bar = 1h bar stamped Sunday 19:00 America/New_York (Concretum 'Monday Asia open' start);
weekend move = close(signal bar) / close(Friday bar stamped 16:00 America/New_York) - 1.
Side = sign(move) if |move| >= 100 bps. Sim via research.swarm.lib.screen.simulate (200/200, 24 bars).
"""
import json, sys
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, bootstrap_ci as bc, fee_math as fm

THRESH_BPS = 100.0
def signals(df):
    idx = df.index
    ny = idx.tz_convert("America/New_York")
    is_sig = (ny.dayofweek == 6) & (ny.hour == 19)
    is_ref = (ny.dayofweek == 4) & (ny.hour == 16)
    close = df["close"]
    ref = close.where(pd.Series(is_ref, index=idx)).ffill()
    move = (close / ref - 1.0) * 1e4
    s = pd.Series(0, index=idx, dtype=int)
    hit = pd.Series(is_sig, index=idx) & move.notna()
    s[hit & (move >= THRESH_BPS)] = 1
    s[hit & (move <= -THRESH_BPS)] = -1
    return s

rows = []
syms = ld.list_symbols("long_1h")
for sym in syms:
    df = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    sig = signals(df)
    tr = sc.simulate(df, sig, 200, 200, 24)
    tr.insert(0, "symbol", sym)
    rows.append(tr)
t = pd.concat(rows, ignore_index=True)
weeks = (max(ld.load_ohlcv(s,'1h',era='train',dataset='long_1h').index.max() for s in syms) - min(ld.load_ohlcv(s,'1h',era='train',dataset='long_1h').index.min() for s in syms)).total_seconds()/(7*86400)
out = {"label": "EXPLORATORY probe, not evidence", "n": int(len(t)),
       "net_bps_mean": float(t.net_bps.mean()), "ci95": list(bc.mean_ci(t.net_bps.to_numpy())),
       "wr": float((t.net_bps > 0).mean()), "p_star_200": fm.p_star(200),
       "trades_per_week": len(t)/weeks, "ttv_weeks": fm.time_to_verdict_weeks(len(t)/weeks),
       "by_side": {int(k): {"n": int(len(g)), "net": float(g.net_bps.mean())} for k, g in t.groupby("side")},
       "exit_reasons": t.exit_reason.value_counts().to_dict()}
print(json.dumps(out, indent=1))
json.dump(out, open(sys.argv[1], "w"), indent=1)
