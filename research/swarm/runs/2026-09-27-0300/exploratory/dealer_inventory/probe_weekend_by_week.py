"""EXPLORATORY ONLY. Per-weekend breakdown of variant A1 (weekend |move|>300 bps fade Monday) from probe_weekend_and_lowvol.py
to see how many independent weekends drive the pooled mean. long_1h train only. Also variant A3: BTC-only and ETH-only.
Command: PYTHONPATH=. python3 research/swarm/runs/2026-09-27-0300/exploratory/dealer_inventory/probe_weekend_by_week.py
"""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as L
SYMS = [s for s in L.list_symbols('long_1h') if s != 'GIGGLE']
A = []
for s in SYMS:
    d = L.load_ohlcv(s, '1h', era='train', dataset='long_1h'); c = d['close']
    for ts in d.index[(d.index.dayofweek == 6) & (d.index.hour == 23)]:
        fri = ts - pd.Timedelta(hours=51); me = ts + pd.Timedelta(hours=24)
        if fri not in d.index or me not in d.index: continue
        A.append(dict(sym=s, ts=ts, wmove=(c[ts]/c[fri]-1)*1e4, fwd=(c[me]/c[ts]-1)*1e4))
A = pd.DataFrame(A); A['fade'] = -np.sign(A.wmove)*A.fwd
big = A[A.wmove.abs() > 300]
w = big.groupby('ts').agg(n=('fade','size'), mean_fade=('fade','mean'), mean_wmove=('wmove','mean')).round(1)
pd.set_option('display.width', 200); print(w.to_string())
print('weekends with >=1 big', len(w), 'weekends mean_fade>0', int((w.mean_fade > 0).sum()))
print('mean of weekend means', round(w.mean_fade.mean(), 2), 'median of weekend means', round(w.mean_fade.median(), 2))
for s in ['BTC', 'ETH']:
    g = A[(A.sym == s) & (A.wmove.abs() > 150)]
    print(s, '|move|>150 n', len(g), 'mean fade', round(g.fade.mean(), 2), 'share>0', round((g.fade > 0).mean(), 3))
# first half vs second half of train
mid = big.ts.min() + (big.ts.max() - big.ts.min()) / 2
for lab, g in [('H1', big[big.ts < mid]), ('H2', big[big.ts >= mid])]:
    print(lab, 'n', len(g), 'mean fade', round(g.fade.mean(), 2), 'share>0', round((g.fade > 0).mean(), 3))
