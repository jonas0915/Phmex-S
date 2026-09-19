import pandas as pd
from research.swarm.lib import load_data as ld


def signals(df: pd.DataFrame) -> pd.Series:
    """Long-only: fires 1 when ETH/BTC crosses back above its trailing 48-bar (48h) moving
    average from below, on the theory that this follower alt keeps rising for up to 48h
    after the regime cross as rotation flow into alts continues. BTC/ETH data are loaded
    fully (train era) and only combined via reindex onto df's own index, so no bar beyond
    the current alt timestamp is ever used at any truncation point.
    """
    btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
    eth = ld.load_ohlcv("ETH", "1h", era="train", dataset="long_1h")
    idx = btc.index.intersection(eth.index)
    ratio = eth["close"].reindex(idx) / btc["close"].reindex(idx)
    ma = ratio.rolling(48).mean()
    cross_up = (ratio > ma) & (ratio.shift(1) <= ma.shift(1))
    cross_up = cross_up.reindex(df.index).fillna(False)

    sig = pd.Series(0, index=df.index, dtype=int)
    sig[cross_up] = 1
    return sig
