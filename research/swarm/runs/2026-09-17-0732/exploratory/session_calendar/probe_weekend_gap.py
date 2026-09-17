"""EXPLORATORY (not the screen; numbers are not evidence). long_1h TRAIN only.
Weekend move = close(Sun 23:00 bar) / close(Fri 20:00 bar) - 1  (Fri 21:00 UTC = CME close, to Mon 00:00 UTC).
Forward = close(Tue 23:00 bar) / open(Mon 00:00 bar) - 1  (48h Mon-Tue).
Sign-adjusted forward return by |weekend move| bucket -> continuation (>0) or reversal (<0)."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld
from research.swarm.lib import bootstrap_ci as bc
syms = [s for s in ld.list_symbols('long_1h') if s != 'GIGGLE']
rows = []
for s in syms:
    df = ld.load_ohlcv(s, '1h', era='train', dataset='long_1h')
    c = df['close']; o = df['open']
    sun23 = df.index[(df.index.dayofweek == 6) & (df.index.hour == 23)]
    for t in sun23:
        fri20 = t - pd.Timedelta(hours=51)  # Sun 23:00 - 51h = Fri 20:00
        mon00 = t + pd.Timedelta(hours=1); tue23 = t + pd.Timedelta(hours=48)
        if fri20 not in df.index or mon00 not in df.index or tue23 not in df.index: continue
        wk = c[t] / c[fri20] - 1
        fwd = c[tue23] / o[mon00] - 1
        fwd24 = c[t + pd.Timedelta(hours=24)] / o[mon00] - 1 if (t + pd.Timedelta(hours=24)) in df.index else np.nan
        rows.append(dict(sym=s, t=t, wk=wk, fwd48=fwd, fwd24=fwd24))
d = pd.DataFrame(rows)
d['abs'] = d.wk.abs(); d['sgn'] = np.sign(d.wk)
d['sa48'] = d.sgn * d.fwd48 * 1e4; d['sa24'] = d.sgn * d.fwd24 * 1e4
print("weekends x symbols:", len(d), "symbols:", d.sym.nunique(), "weekends:", d.t.nunique())
for lo, hi in [(0, 0.01), (0.01, 0.02), (0.02, 0.03), (0.03, 0.05), (0.05, 1)]:
    sub = d[(d['abs'] >= lo) & (d['abs'] < hi)]
    if len(sub) < 5: print(f"|wk| in [{lo},{hi}): n={len(sub)}"); continue
    ci48 = bc.mean_ci(sub.sa48.to_numpy()); ci24 = bc.mean_ci(sub.sa24.dropna().to_numpy())
    print(f"|wk| in [{lo},{hi}): n={len(sub)} sign-adj fwd48 mean={sub.sa48.mean():.1f} bps CI95={ci48} | fwd24 mean={sub.sa24.mean():.1f} CI95={ci24} | frac>0 (48h)={ (sub.sa48>0).mean():.3f}")
for thr in (0.02, 0.03):
    sub = d[d['abs'] >= thr]
    print(f"thr>={thr}: n={len(sub)}, per-week={len(sub)/d.t.nunique():.2f}, sign-adj fwd48 mean={sub.sa48.mean():.1f} CI95={bc.mean_ci(sub.sa48.to_numpy())}, up n={(sub.sgn>0).sum()} mean={sub[sub.sgn>0].sa48.mean():.1f}, down n={(sub.sgn<0).sum()} mean={sub[sub.sgn<0].sa48.mean():.1f}")
d.to_csv('research/swarm/runs/2026-09-17-0732/exploratory/session_calendar/probe_weekend_gap_rows.csv', index=False)
