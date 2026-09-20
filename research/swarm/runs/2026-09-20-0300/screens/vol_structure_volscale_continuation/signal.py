import pandas as pd
import numpy as np


def signals(df: pd.DataFrame) -> pd.Series:
    """Vol-scaled-momentum continuation signal on closed 1h bars.

    Fires when trailing 24h realized volatility (rolling stdev of 1h
    returns over the last 24 fully closed bars) expands to >=1.5x its
    trailing 20-day (480-bar) median, in the direction of the prior
    closed 24h return. Uses only trailing, fixed-window rolling
    statistics on closed bars -- no shift(-k), no forming-bar lookups.
    """
    close = df["close"]
    ret_1h = close.pct_change()

    # trailing 24h realized-vol proxy, computed on closed bars only
    daily_vol = ret_1h.rolling(window=24, min_periods=24).std()
    baseline_vol = daily_vol.rolling(window=24 * 20, min_periods=24 * 20).median()

    # trailing 24h (closed) directional return
    day_ret = close.pct_change(periods=24)

    vol_ratio = daily_vol / baseline_vol
    expansion = vol_ratio >= 1.5

    sig = pd.Series(0, index=df.index, dtype=int)
    sig[expansion & (day_ret > 0)] = 1
    sig[expansion & (day_ret < 0)] = -1
    return sig.fillna(0).astype(int)
