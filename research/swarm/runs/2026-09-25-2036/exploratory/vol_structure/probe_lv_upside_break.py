"""EXPLORATORY probe (NOT the screen, numbers are not evidence).
Low-vol-regime upside break, long-only; compares mirrored downside break.
long_1h TRAIN era only. No mr_edge data used."""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld, screen, fee_math as fm, bootstrap_ci as bc

UNI = ['1000PEPE','1000SHIB','AAVE','ADA','BNB','BTC','DOGE','ETH','LINK','LTC','NEAR','ONDO','SOL','SUI','TAO','UNI','XLM','XRP']

def raw(df, q=0.25, k=2.0, look=168, base=2160, cool=72):
    c = df['close'].astype(float); h = df['high'].astype(float); l = df['low'].astype(float)
    r = np.log(c).diff()
    rv = r.rolling(look, min_periods=look).std()
    rvq = rv.rolling(base, min_periods=base // 2).quantile(q)
    comp = rv.shift(1) <= rvq.shift(1)
    r24 = np.log(c / c.shift(24))
    thr = k * rv.shift(1) * np.sqrt(24)
    up = comp & (c > h.rolling(look, min_periods=look).max().shift(1)) & (r24 >= thr)
    dn = comp & (c < l.rolling(look, min_periods=look).min().shift(1)) & (r24 <= -thr)
    return up.fillna(False).to_numpy(), dn.fillna(False).to_numpy()

def cooled(mask, side, cool=72):
    out = np.zeros(len(mask), dtype=int); last = -10**9
    for i in np.flatnonzero(mask):
        if i - last >= cool:
            out[i] = side; last = i
    return out

def run(tp, sl, hold, which, **kw):
    allt = []
    weeks = None
    for s in UNI:
        df = ld.load_ohlcv(s, '1h', era='train', dataset='long_1h')
        if weeks is None: weeks = (df.index.max() - df.index.min()).days / 7
        up, dn = raw(df, **kw)
        sig = cooled(up, 1) if which == 'up' else cooled(dn, -1)
        t = screen.simulate(df, pd.Series(sig, index=df.index), tp, sl, hold)
        t['symbol'] = s; allt.append(t)
    t = pd.concat(allt)
    t = screen.admit_trades(t, fm.max_concurrent(sl), UNI)
    x = t['net_bps'].to_numpy()
    ci = bc.mean_ci(x) if len(x) > 1 else None
    return dict(which=which, tp=tp, sl=sl, hold=hold, kw=kw, n=len(x), mean=float(x.mean()) if len(x) else None,
                ci=ci, wr=float((t['gross_bps'] > 0).mean()) if len(x) else None, p_star=fm.p_star(tp),
                per_week=len(x) / weeks, max_conc=fm.max_concurrent(sl),
                months=t['entry_ts'].dt.strftime('%Y-%m').value_counts().sort_index().to_dict())

if __name__ == '__main__':
    res = []
    for which in ('up', 'dn'):
        res.append(run(300, 200, 72, which))
    for r in res: print(json.dumps(r, default=str))
