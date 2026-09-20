# EXPLORATORY ONLY — sizes an expected_trades_per_week estimate for the
# literature_btc_alt_drift thesis. Train-era mr_edge only. Not the screen;
# not evidence of edge.
from research.swarm.lib import load_data as ld
import numpy as np

btc = ld.load_ohlcv('BTC', '1h', era='train', dataset='mr_edge')
print('BTC 1h train rows', len(btc), btc.index.min(), btc.index.max())
ret = np.log(btc['close']).diff()
thr = ret.abs().quantile(0.90)
print('90th pct abs 1h BTC return (bps):', round(thr * 1e4, 1))
n_fire = (ret.abs() >= thr).sum()
weeks = (btc.index.max() - btc.index.min()).days / 7
print('n_fire', n_fire, 'weeks', round(weeks, 1), 'fires/week', round(n_fire / weeks, 2))
