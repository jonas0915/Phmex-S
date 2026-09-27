"""EXPLORATORY ONLY (dealer_inventory lens, run 2026-09-27-0300). Not the screen; numbers are not evidence.
Data: long_1h, era=train only (2025-06-27 -> 2026-04-23), via load_data.load_ohlcv. No mr_edge data used.
Variants tried (all listed, for multiplicity review):
  A1 weekend move (Fri 20:00 UTC close -> Sun 23:00 UTC close) |move| > 300 bps: mean signed fwd return (fade side) Mon 00:00 -> Mon 24:00
  A2 same, split by weekend volume ratio (weekend hourly vol / prior Mon-Fri hourly vol) < median vs >= median
  B1 24h move |r24| > 2 * trailing-30d std of 24h returns, fade, fwd 24h; split by vol ratio (24h vol / trailing 30d mean 24h vol) < 1 vs >= 1
Command: PYTHONPATH=. python3 research/swarm/runs/2026-09-27-0300/exploratory/dealer_inventory/probe_weekend_and_lowvol.py
"""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as L
SYMS = [s for s in L.list_symbols('long_1h') if s != 'GIGGLE']
A, B = [], []
for s in SYMS:
    d = L.load_ohlcv(s, '1h', era='train', dataset='long_1h')
    c, v = d['close'], d['volume']
    # A: weekends
    for ts in d.index[(d.index.dayofweek == 6) & (d.index.hour == 23)]:
        fri = ts - pd.Timedelta(hours=51)   # Fri 20:00
        mon_end = ts + pd.Timedelta(hours=24)
        wk0 = fri - pd.Timedelta(hours=100)
        if fri not in d.index or mon_end not in d.index: continue
        wmove = (c[ts] / c[fri] - 1) * 1e4
        fwd = (c[mon_end] / c[ts] - 1) * 1e4
        wv = v[fri:ts].iloc[1:].mean(); pv = v[wk0:fri].mean()
        A.append(dict(sym=s, ts=ts, wmove=wmove, fwd=fwd, vr=wv / pv if pv > 0 else np.nan))
    # B: low-volume 24h moves
    r24 = (c / c.shift(24) - 1) * 1e4
    sd = r24.rolling(720, min_periods=500).std()
    v24 = v.rolling(24).sum(); vbase = v24.rolling(720, min_periods=500).mean()
    vr = v24 / vbase
    fwd = (c.shift(-24) / c - 1) * 1e4   # exploratory forward return only; never in a signal
    z = r24 / sd
    last = None
    for ts in d.index[(z.abs() > 2).fillna(False)]:
        if last is not None and ts - last < pd.Timedelta(hours=24): continue
        if np.isnan(fwd[ts]): continue
        last = ts
        B.append(dict(sym=s, ts=ts, z=z[ts], vr=vr[ts], fwd_fade=-np.sign(z[ts]) * fwd[ts]))
A = pd.DataFrame(A); B = pd.DataFrame(B)
A['fade'] = -np.sign(A.wmove) * A.fwd
big = A[A.wmove.abs() > 300]
print('A1 weekends total rows', len(A), 'big(|move|>300) n', len(big), 'mean fade fwd bps', round(big.fade.mean(), 2), 'median', round(big.fade.median(), 2), 'share>0', round((big.fade > 0).mean(), 3))
med = A.vr.median()
for lab, g in [('lowvol', big[big.vr < med]), ('highvol', big[big.vr >= med])]:
    print('A2', lab, 'n', len(g), 'mean fade', round(g.fade.mean(), 2), 'share>0', round((g.fade > 0).mean(), 3))
print('A weekly counts: weeks', A.ts.nunique(), 'big per week', round(len(big) / A.ts.nunique(), 2))
for lab, g in [('B1 all', B), ('B1 vr<1', B[B.vr < 1]), ('B1 vr>=1', B[B.vr >= 1]), ('B1 vr<0.8', B[B.vr < 0.8])]:
    print(lab, 'n', len(g), 'mean fade fwd24 bps', round(g.fwd_fade.mean(), 2), 'share>0', round((g.fwd_fade > 0).mean(), 3))
