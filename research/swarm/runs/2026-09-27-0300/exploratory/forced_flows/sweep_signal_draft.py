import numpy as np
import pandas as pd


def signals(df: pd.DataFrame) -> pd.Series:
    """Stop-sweep exhaustion fade (closed 1h bars only).
    Upside sweep: this closed bar's high trades ABOVE the highest high of the prior 72 closed bars
    (where buy-stops / short-liquidation orders rest) but the bar CLOSES back below that prior high
    -> -1 (short). Downside sweep mirror -> +1 (long). A bar that sweeps both sides -> 0."""
    n = 72
    prior_high = df["high"].rolling(n, min_periods=n).max().shift(1)
    prior_low = df["low"].rolling(n, min_periods=n).min().shift(1)
    up = (df["high"] > prior_high) & (df["close"] < prior_high)
    dn = (df["low"] < prior_low) & (df["close"] > prior_low)
    out = pd.Series(0, index=df.index, dtype=int)
    out[up & ~dn] = -1
    out[dn & ~up] = 1
    return out
