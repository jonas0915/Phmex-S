import pandas as pd
import numpy as np


def signals(df: pd.DataFrame) -> pd.Series:
    """Shock-out-of-compression drift (closed 1h bars only).

    Compression: the 72-bar realised vol measured on the bar BEFORE the shock bar is at
    or below the 33rd percentile of its trailing 720-bar history. Shock: the closed bar's
    absolute log return is >= 4x that pre-shock 72-bar vol AND the bar's close also
    breaks the pre-shock 72-bar high/low (so the move leaves the pinned range). Fire in
    the direction of the shock. Re-arm only after 48 bars have passed since the last
    fire. Only current-and-prior bars are used.
    """
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    r = np.log(c).diff()
    rv72 = r.rolling(72, min_periods=72).std()
    rv_q = rv72.rolling(720, min_periods=360).quantile(0.33)
    rv_prev = rv72.shift(1)
    compressed = (rv_prev <= rv_q.shift(1))
    hi_prev = h.rolling(72, min_periods=72).max().shift(1)
    lo_prev = l.rolling(72, min_periods=72).min().shift(1)
    shock_up = compressed & (r >= 4.0 * rv_prev) & (c > hi_prev)
    shock_dn = compressed & (r <= -4.0 * rv_prev) & (c < lo_prev)
    raw = np.where(shock_up.fillna(False), 1, np.where(shock_dn.fillna(False), -1, 0))
    out = np.zeros(len(df), dtype=np.int64)
    last = -10**9
    for i in range(len(df)):
        if raw[i] != 0 and i - last >= 48:
            out[i] = raw[i]
            last = i
    return pd.Series(out, index=df.index)
