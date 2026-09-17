import numpy as np
import pandas as pd
from research.swarm.lib import load_data as ld

BTC_THR_BPS = 100.0   # BTC 4-bar log return must exceed this (a BTC-led rally)
CAPTURE = 0.5         # alt captured less than this fraction of the BTC move -> failed catch-up
LAG = 4               # bars (1h dataset)


def _btc_close(df):
    bt = ld.load_ohlcv("BTC", "1h", era="train", dataset="mr_edge")["close"]
    if df.index.max() > bt.index.max():
        # df carries rows past the train boundary: only the build stage's single registered
        # holdout read can hand such a frame in; reuse the committee token there so the same
        # BTC bars exist for those rows. Never reached in a train-era screen.
        bt = ld.load_ohlcv("BTC", "1h", era="all", dataset="mr_edge", token=ld.COMMITTEE_TOKEN)["close"]
    return bt.reindex(df.index)


def signals(df: pd.DataFrame) -> pd.Series:
    b = _btc_close(df)
    c = df["close"]
    b_ret = np.log(b / b.shift(LAG)) * 1e4
    a_ret = np.log(c / c.shift(LAG)) * 1e4
    fire = (b_ret > BTC_THR_BPS) & (a_ret < CAPTURE * b_ret)
    fire = fire & b.notna() & b.shift(LAG).notna()
    out = pd.Series(0, index=df.index, dtype=int)
    out[fire.fillna(False)] = -1
    return out
