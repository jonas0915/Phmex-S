"""
owner_record_liq_cascade_continuation signal.
Signals(df) -> pd.Series in {-1,0,1}, computed on CLOSED bars only.
Fires -1 (short) on a bar whose return is an abnormal negative outlier vs its own trailing
volatility AND whose volume is an abnormal positive outlier vs its own trailing volume
(liquidation-cascade-down proxy); fires +1 (long) on the mirrored abnormal-up case.
All rolling stats use only data up to and including the current closed bar (rolling(),
no shift(-k), no future index access) -> passes the whole-prefix causality check.
"""
import pandas as pd
import numpy as np

ROLL = 20
RET_Z_THRESH = 2.5
VOL_Z_THRESH = 2.0


def signals(df: pd.DataFrame) -> pd.Series:
    ret = df["close"].pct_change()
    roll_std = ret.rolling(ROLL, min_periods=ROLL).std()
    vol_mean = df["volume"].rolling(ROLL, min_periods=ROLL).mean()
    vol_std = df["volume"].rolling(ROLL, min_periods=ROLL).std()

    ret_z = ret / roll_std.replace(0, np.nan)
    vol_z = (df["volume"] - vol_mean) / vol_std.replace(0, np.nan)

    cascade_down = (ret_z < -RET_Z_THRESH) & (vol_z > VOL_Z_THRESH)
    cascade_up = (ret_z > RET_Z_THRESH) & (vol_z > VOL_Z_THRESH)

    sig = pd.Series(0, index=df.index, dtype=int)
    sig[cascade_down.fillna(False)] = -1
    sig[cascade_up.fillna(False)] = 1
    return sig
