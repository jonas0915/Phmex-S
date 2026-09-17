"""EXPLORATORY (not the screen). Per-symbol and per-side breakdown at thr=5%, tp/sl 200, hold 48; per-weekend cluster view."""
import numpy as np, pandas as pd, sys
sys.path.insert(0, 'research/swarm/runs/2026-09-17-0732/exploratory/session_calendar')
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, screen
from probe_weekend_gap2 import make_sig  # noqa (re-runs that probe's prints; harmless)
syms = [s for s in ld.list_symbols('long_1h') if s != 'GIGGLE']
allt = []
for s in syms:
    df = ld.load_ohlcv(s, '1h', era='train', dataset='long_1h')
    tr = screen.simulate(df, make_sig(0.05)(df), 200, 200, 48); tr['sym'] = s; allt.append(tr)
t = pd.concat(allt)
print("\n=== thr=0.05 tp/sl 200 hold 48 ===")
print(t.groupby('sym').net_bps.agg(['count', 'mean']).round(1).to_string())
print(t.groupby('side').net_bps.agg(['count', 'mean']).round(1))
t['wk'] = pd.to_datetime(t.entry_ts).dt.to_period('W')
g = t.groupby('wk').net_bps.agg(['count', 'mean'])
print("distinct entry weeks:", len(g), "weeks with mean>0:", (g['mean'] > 0).sum()); print(g.round(1).to_string())
ex = t[~t.sym.isin(['BTC', 'ETH'])]
print("ex-BTC/ETH: n=", len(ex), "mean=", round(ex.net_bps.mean(), 1), "CI=", bc.mean_ci(ex.net_bps.to_numpy()), "WR=", round((ex.net_bps > 0).mean(), 3))
