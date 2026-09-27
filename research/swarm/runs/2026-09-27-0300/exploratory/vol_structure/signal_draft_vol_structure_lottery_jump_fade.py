import numpy as np
import pandas as pd
from research.swarm.lib import load_data


def signals(df: pd.DataFrame) -> pd.Series:
    """Short an alt perp at the 00:00 UTC closed bar ONE day after an idiosyncratic
    (BTC-relative) upside 24h jump: excess 24h log return (alt minus BTC, measured at the
    00:00 UTC bar) >= 2.0 x its trailing 60-day std (prior days only, min 30 obs) AND >= 4%.
    Closed bars only; BTC reference via load_reference (STANDARDS #16)."""
    out = pd.Series(0, index=df.index, dtype=int)
    if len(df) < 50:
        return out
    ref = load_data.load_reference("BTC", "1h", "long_1h")["close"]
    ref = ref.reindex(df.index).ffill()
    c = df["close"]
    ex = np.log(c / c.shift(24)) - np.log(ref / ref.shift(24))
    daily = ex[df.index.hour == 0]
    sd = daily.rolling(60, min_periods=30).std().shift(1)
    jump = ((daily >= 2.0 * sd) & (daily >= 0.04)).fillna(False)
    fire = jump.shift(1, fill_value=False).astype(bool)
    out.loc[fire[fire].index] = -1
    return out
