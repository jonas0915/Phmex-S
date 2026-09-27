import numpy as np
import pandas as pd


def signals(df: pd.DataFrame) -> pd.Series:
    """Weekend TradFi catch-up. Fires only on the CLOSED Monday 12:00-UTC 1h bar (closes
    13:00 UTC, before the US cash/ETF open). Weekend move = that close vs the close of the
    last Friday bar at or before 20:00 UTC (bar closing 21:00 UTC, after the 4 p.m. ET ETF
    close in both DST regimes). Scaled by trailing 1h return std (168 bars, ending at the
    Friday anchor) * sqrt(hours elapsed). |z| >= 0.5 -> trade in the weekend's direction."""
    idx = df.index
    close = df["close"].astype(float)
    r = np.log(close).diff()
    vol = r.rolling(168, min_periods=120).std()
    out = pd.Series(0, index=idx, dtype=int)
    is_fri_anchor = (idx.dayofweek == 4) & (idx.hour == 20)
    anchor_close = close.where(is_fri_anchor).ffill()
    anchor_vol = vol.where(is_fri_anchor).ffill()
    anchor_time = pd.Series(idx.where(is_fri_anchor), index=idx).ffill()
    is_fire = (idx.dayofweek == 0) & (idx.hour == 12)
    hours = (pd.Series(idx, index=idx) - anchor_time).dt.total_seconds() / 3600.0
    ok = is_fire & (hours > 60) & (hours < 72) & anchor_vol.gt(0)
    z = np.log(close / anchor_close) / (anchor_vol * np.sqrt(hours))
    out[ok & (z >= 0.5)] = 1
    out[ok & (z <= -0.5)] = -1
    return out
