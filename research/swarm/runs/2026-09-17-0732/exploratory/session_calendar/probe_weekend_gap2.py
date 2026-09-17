"""EXPLORATORY (not the screen). Concentration by weekend + simulate() with TP/SL for the reversal rule."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, bootstrap_ci as bc, screen
d = pd.read_csv('research/swarm/runs/2026-09-17-0732/exploratory/session_calendar/probe_weekend_gap_rows.csv', parse_dates=['t'])
d['sa48'] = np.sign(d.wk) * d.fwd48 * 1e4
for thr in (0.03, 0.05):
    sub = d[d.wk.abs() >= thr]
    g = sub.groupby('t').sa48.agg(['count', 'mean', 'sum']).sort_values('sum')
    print(f"thr {thr}: distinct weekends={len(g)}, weekends with sign-adj sum<0: {(g['sum']<0).sum()}, top-3 most negative weekends contribute {g['sum'].head(3).sum():.0f} of total {g['sum'].sum():.0f} bps-sum")
    print(g.head(5)); print(g.tail(3))

def make_sig(thr):
    def signals(df):
        c = df['close']
        sig = pd.Series(0, index=df.index, dtype='int64')
        is_sun23 = (df.index.dayofweek == 6) & (df.index.hour == 23)
        prev = c.shift(51)  # Fri 20:00 bar close
        ok = is_sun23 & (df.index.to_series().diff(51) == pd.Timedelta(hours=51)).to_numpy()
        wk = c / prev - 1
        sig[ok & (wk >= thr).to_numpy()] = -1
        sig[ok & (wk <= -thr).to_numpy()] = 1
        return sig
    return signals
syms = [s for s in ld.list_symbols('long_1h') if s != 'GIGGLE']
for thr in (0.03, 0.05):
    for tp, sl, hold in [(200, 200, 48), (150, 150, 48), (300, 300, 72)]:
        allt = []
        for s in syms:
            df = ld.load_ohlcv(s, '1h', era='train', dataset='long_1h')
            tr = screen.simulate(df, make_sig(thr)(df), tp, sl, hold); tr['sym'] = s; allt.append(tr)
        t = pd.concat(allt)
        print(f"thr={thr} tp/sl={tp}/{sl} hold={hold}: n={len(t)} net mean={t.net_bps.mean():.1f} CI95={bc.mean_ci(t.net_bps.to_numpy())} WR={(t.net_bps>0).mean():.3f} exits={t.exit_reason.value_counts().to_dict()}")
