"""EXPLORATORY ONLY. Variant A2-lowvol (weekend |move|>300 bps AND weekend hourly volume / prior Mon-Fri hourly volume
below the pooled median from probe_weekend_and_lowvol.py) broken down per weekend, and the same with a fixed ratio < 0.6.
long_1h train only. Command: PYTHONPATH=. python3 research/swarm/runs/2026-09-27-0300/exploratory/dealer_inventory/probe_weekend_lowvol_by_week.py
"""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as L
SYMS = [s for s in L.list_symbols('long_1h') if s != 'GIGGLE']
A = []
for s in SYMS:
    d = L.load_ohlcv(s, '1h', era='train', dataset='long_1h'); c, v = d['close'], d['volume']
    for ts in d.index[(d.index.dayofweek == 6) & (d.index.hour == 23)]:
        fri = ts - pd.Timedelta(hours=51); me = ts + pd.Timedelta(hours=24); wk0 = fri - pd.Timedelta(hours=100)
        if fri not in d.index or me not in d.index: continue
        pv = v[wk0:fri].mean()
        A.append(dict(sym=s, ts=ts, wmove=(c[ts]/c[fri]-1)*1e4, fwd=(c[me]/c[ts]-1)*1e4, vr=v[fri:ts].iloc[1:].mean()/pv if pv > 0 else np.nan))
A = pd.DataFrame(A); A['fade'] = -np.sign(A.wmove)*A.fwd
print('pooled vr median', round(A.vr.median(), 3))
for lab, g in [('lowvol<median', A[(A.wmove.abs() > 300) & (A.vr < A.vr.median())]), ('vr<0.6', A[(A.wmove.abs() > 300) & (A.vr < 0.6)])]:
    w = g.groupby('ts').fade.mean()
    print(lab, 'rows', len(g), 'weekends', len(w), 'weekends>0', int((w > 0).sum()), 'median weekend mean', round(w.median(), 1), 'pooled mean', round(g.fade.mean(), 1))
