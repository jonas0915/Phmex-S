"""EXPLORATORY (not the screen; numbers are not evidence). long_1h TRAIN only; no mr_edge data read.
Question: can a weekend-conditioned (Fri 20:00 bar close -> Sun 23:00 bar close, 51h) long-only
'weekend dump absorbed Monday' trigger reach the CONSTRAINTS item-3 frequency under the
STANDARDS #17 concurrency cap? Counts only (no returns computed): per weekend, how many of the
18 active symbols have a weekend move <= -thr, and the cap-limited admitted count per week."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, fee_math as fm
syms = [s for s in ld.list_symbols('long_1h') if s != 'GIGGLE']
rows = []
for s in syms:
    df = ld.load_ohlcv(s, '1h', era='train', dataset='long_1h')
    c = df['close']
    for t in df.index[(df.index.dayofweek == 6) & (df.index.hour == 23)]:
        f = t - pd.Timedelta(hours=51)
        if f in df.index:
            rows.append(dict(sym=s, t=t, wk=c[t] / c[f] - 1))
d = pd.DataFrame(rows)
nwk = d.t.nunique()
print('train weekends:', nwk, 'symbols:', d.sym.nunique(), 'first', d.t.min(), 'last', d.t.max())
for sl in (100, 150, 200):
    cap = fm.max_concurrent(sl)
    for thr in (0.02, 0.03, 0.05):
        per = d[d.wk <= -thr].groupby('t').size().reindex(sorted(d.t.unique()), fill_value=0)
        adm = per.clip(upper=cap)
        tpw = adm.sum() / nwk
        print(f'sl={sl} cap={cap} thr={thr}: weekends firing={int((per>0).sum())}/{nwk}, raw sym-weekends={int(per.sum())}, '
              f'admitted(upper bound)={int(adm.sum())}, per-week={tpw:.2f}, ttv_weeks={fm.time_to_verdict_weeks(tpw) if tpw>0 else float("inf"):.1f}')
