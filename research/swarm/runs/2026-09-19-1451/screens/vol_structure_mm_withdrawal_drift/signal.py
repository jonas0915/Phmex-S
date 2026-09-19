import numpy as np
import pandas as pd


def signals(df: pd.DataFrame) -> pd.Series:
    out = pd.Series(0, index=df.index, dtype=int)
    n = len(df)
    if n < 500:
        return out

    close = df["close"]
    ret1h = close.pct_change()

    # realized-vol shock: current 24h rolling stdev of hourly returns vs the
    # trailing 20-day (480h) rolling stdev, both computed on closed bars only
    # (rolling() at position i only uses bars up to and including i, and we
    # trigger off bar i-1's fully-closed window, entering at bar i).
    rv_24h = ret1h.rolling(24).std()
    rv_20d = ret1h.rolling(480, min_periods=200).std()

    shock_ratio = rv_24h / rv_20d

    in_position_until = -1
    for i in range(480, n - 1):
        if i <= in_position_until:
            continue
        prior_ratio = shock_ratio.iloc[i]
        if pd.isna(prior_ratio):
            continue
        if prior_ratio < 3.0:
            continue
        # direction = sign of the trailing 24h return that produced the shock
        trailing_ret = close.iloc[i] / close.iloc[i - 24] - 1.0
        direction = np.sign(trailing_ret)
        if direction == 0:
            continue
        entry_loc = i + 1
        if entry_loc >= n:
            continue
        out.iloc[entry_loc] = int(direction)
        in_position_until = entry_loc + 48  # respect max_hold_bars before re-arming

    return out.fillna(0).astype(int)
