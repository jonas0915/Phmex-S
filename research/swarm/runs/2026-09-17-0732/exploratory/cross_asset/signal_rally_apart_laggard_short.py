import numpy as np
import pandas as pd
from research.swarm.lib import load_data as ld

# BTC-led rally that the alt fails to follow -> short the alt (rally-apart, not a lag).
BTC_THR_BPS = 100.0   # BTC 4-bar (4h) log return must exceed this
CAPTURE = 0.5         # alt captured less than half of the BTC move
LAG = 4               # closed 1h bars

_BTC = None


def _btc_close():
    # Train-era BTC closes only; rows of df beyond the train boundary get NaN -> signal 0.
    global _BTC
    if _BTC is None:
        _BTC = ld.load_ohlcv("BTC", "1h", era="train", dataset="mr_edge")["close"]
    return _BTC


def signals(df: pd.DataFrame) -> pd.Series:
    b = _btc_close().reindex(df.index)
    c = df["close"]
    b_ret = np.log(b / b.shift(LAG)) * 1e4
    a_ret = np.log(c / c.shift(LAG)) * 1e4
    fire = (b_ret > BTC_THR_BPS) & (a_ret < CAPTURE * b_ret)
    fire = fire & b.notna() & b.shift(LAG).notna()
    out = pd.Series(0, index=df.index, dtype=int)
    out[fire.fillna(False)] = -1
    return out
