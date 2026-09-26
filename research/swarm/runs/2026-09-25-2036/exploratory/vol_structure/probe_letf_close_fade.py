"""EXPLORATORY probe (NOT the screen, numbers are not evidence).
US-close leveraged-ETF rebalance fade: on the closed 1h bar ending at 16:00 America/New_York,
if the trailing 24-bar (US-close to US-close) log return exceeds k x trailing 30-day daily
stdev, fade it (enter next open), hold up to `hold` bars. long_1h TRAIN era only; no mr_edge."""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld, screen, fee_math as fm, bootstrap_ci as bc

def sig_fn(df, k=1.5, direction=-1):
    c = df['close'].astype(float)
    et = df.index.tz_convert('America/New_York')
    # bar labelled by open time; the bar opening 15:00 ET closes at 16:00 ET (US close)
    is_close_bar = (et.hour == 15) & (et.dayofweek < 5)
    r24 = np.log(c / c.shift(24))
    # stdev of the prior 30 close-to-close daily returns (close bars only, current included)
    dstd = r24[is_close_bar].rolling(30, min_periods=20).std().reindex(df.index)
    fire = is_close_bar & (r24.abs() >= k * dstd)
    out = pd.Series(0, index=df.index, dtype=int)
    out[fire & (r24 > 0)] = direction
    out[fire & (r24 < 0)] = -direction
    return out

def run(uni, tp, sl, hold, k, direction):
    allt = []; weeks = None
    for s in uni:
        df = ld.load_ohlcv(s, '1h', era='train', dataset='long_1h')
        if weeks is None: weeks = (df.index.max() - df.index.min()).days / 7
        t = screen.simulate(df, sig_fn(df, k, direction), tp, sl, hold); t['symbol'] = s; allt.append(t)
    t = screen.admit_trades(pd.concat(allt), fm.max_concurrent(sl), uni)
    x = t['net_bps'].to_numpy()
    return dict(uni=uni, tp=tp, sl=sl, hold=hold, k=k, dir=direction, n=len(x), mean=float(x.mean()) if len(x) else None,
                ci=bc.mean_ci(x) if len(x) > 1 else None, wr=float((t['gross_bps'] > 0).mean()) if len(x) else None,
                p_star=fm.p_star(tp), per_week=len(x) / weeks, max_conc=fm.max_concurrent(sl),
                months=pd.to_datetime(t['entry_ts']).dt.strftime('%Y-%m').value_counts().sort_index().to_dict())

if __name__ == '__main__':
    df = ld.load_ohlcv('ETH', '1h', era='train', dataset='long_1h')
    print('ETH train range', df.index.min(), df.index.max())
    for uni in (['BTC', 'ETH'], ['BTC', 'ETH', 'SOL', 'XRP']):
        for d in (-1, 1):
            print(json.dumps(run(uni, 250, 250, 24, 1.5, d), default=str))
