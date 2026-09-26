"""cross_asset_brrny_window_continuation — signal (closed 1h bars only).
Fires on the 1h bar whose New-York-local open hour is 15:00 (the CME CF BRRNY 3:00-4:00 p.m. ET
benchmark observation window) on NY weekdays, when that bar's open->close log return is a
|z| > 1.5 outlier versus the trailing 40 prior NY-15:00 bars of the same symbol (std excludes
the current bar). Direction = continuation (sign of the window move). All inputs are the bar
itself and earlier bars; no reference symbol, no funding."""
import numpy as np
import pandas as pd


def signals(df: pd.DataFrame) -> pd.Series:
    idx = df.index
    idx_utc = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    ny = idx_utc.tz_convert("America/New_York")
    r = np.log(df["close"].astype(float) / df["open"].astype(float))
    mask = np.asarray((ny.hour == 15) & (ny.dayofweek < 5))
    rr = r[mask]
    sd = rr.rolling(40, min_periods=20).std().shift(1)
    z = rr / sd
    out = pd.Series(0, index=df.index, dtype=int)
    out.loc[z.index[(z > 1.5).to_numpy()]] = 1
    out.loc[z.index[(z < -1.5).to_numpy()]] = -1
    return out
