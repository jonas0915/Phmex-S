"""informed_flow_btc_alt_cascade signal (short-only laggard fade).

Mechanism: BTC carries the deepest book and the most informed leveraged flow; a sharp
BTC pump over the trailing K hours is priced into BTC first via short covering /
leveraged futures buying concentrated in BTC's own book. If a given alt has NOT
captured at least half of that same-direction move over the same window, its
apparent "lag" is not a catch-up waiting to happen — it signals the pump lacked
broad, genuine cross-market demand. The bet: informed desks and market makers fade
the unconfirmed laggard alt back down toward its pre-pump level over the next few
hours, squeezing late alt longs who bought the "BTC just pumped, alts will follow"
narrative. Short-only: the mirror-image long-the-laggard-on-a-BTC-dump case was
tested and found net-negative in-sample (see exploratory/informed_flow probe +
screen script), so it is not included here — a different mechanism, not tested here.

Only uses the alt's own OHLCV (`df`, passed by the screen) plus BTC's OHLCV loaded via
research.swarm.lib.load_data. Because BTC is loaded once per call and then intersected
with df's own (possibly truncated) index, passing a truncated prefix of df can never
pull in BTC bars beyond that prefix's own last timestamp -- no lookahead. Closed-bar
only: the K-bar returns at bar i use only close[i] and close[i-K], both already-closed
bars; no shift(-k), no forming-bar read.
"""
import pandas as pd

from research.swarm.lib import load_data as ld

K = 3               # trailing lookback, bars (hours on the 1h grid)
THRESH_BPS = 150.0  # BTC trailing K-bar move required to call it a "sharp pump"
LAG_RATIO = 0.5     # alt must have captured less than half of BTC's same-direction move


def signals(df: pd.DataFrame) -> pd.Series:
    btc = ld.load_reference("BTC", "1h", dataset="long_1h")
    idx = df.index.intersection(btc.index)
    btc_ret = (btc["close"].pct_change(K) * 1e4).reindex(idx)
    alt_ret = (df["close"].pct_change(K) * 1e4).reindex(idx)

    laggard_pump = (btc_ret > THRESH_BPS) & (alt_ret < btc_ret * LAG_RATIO)

    sig = pd.Series(0, index=idx, dtype=int)
    sig[laggard_pump] = -1
    return sig.reindex(df.index).fillna(0).astype(int)
