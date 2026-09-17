import pandas as pd
import numpy as np


def signals(df: pd.DataFrame) -> pd.Series:
    """Post-expiry vol-release breakout (closed 1h bars only).

    Anchor = the closed 1h bar that opens at 08:00 UTC on a Friday (Deribit weekly /
    monthly option expiry settles 08:00 UTC). Pre-expiry window = the 72 closed bars
    before the anchor (3 days). Compression = the 72-bar realised vol at the anchor is
    at or below the 33rd percentile of its own trailing 720-bar (30-day) history.
    After a compressed expiry, the first closed bar within the next 48 bars that closes
    above the pre-expiry 72-bar high fires +1; below the 72-bar low fires -1. One fire
    per expiry window. Everything uses only current-and-prior bars.
    """
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    r = np.log(c).diff()
    rv72 = r.rolling(72, min_periods=72).std()
    rv_q = rv72.rolling(720, min_periods=360).quantile(0.33)
    hi72 = h.rolling(72, min_periods=72).max()
    lo72 = l.rolling(72, min_periods=72).min()
    idx = df.index
    is_anchor = (idx.dayofweek == 4) & (idx.hour == 8)
    compressed = (rv72 <= rv_q).to_numpy()
    cv = c.to_numpy()
    hi_prev = hi72.shift(1).to_numpy()   # range of the 72 bars ending at the bar BEFORE the anchor
    lo_prev = lo72.shift(1).to_numpy()
    out = np.zeros(len(df), dtype=np.int64)
    armed = False
    box_hi = box_lo = np.nan
    expires_at = -1
    for i in range(len(df)):
        if is_anchor[i] and compressed[i] and np.isfinite(hi_prev[i]) and np.isfinite(lo_prev[i]):
            armed, box_hi, box_lo, expires_at = True, hi_prev[i], lo_prev[i], i + 48
            continue
        if armed:
            if i > expires_at:
                armed = False
                continue
            if cv[i] > box_hi:
                out[i] = 1
                armed = False
            elif cv[i] < box_lo:
                out[i] = -1
                armed = False
    return pd.Series(out, index=idx)
