import numpy as np
import pandas as pd


def signals(df: pd.DataFrame) -> pd.Series:
    """Post-liquidation-cascade continuation SHORT (closed 1h bars only).
    Cascade bar = 1h close-to-close return <= -3.0 x the trailing 168-bar std of 1h
    returns (std lagged one bar) AND bar volume >= 2.0 x the trailing 168-bar median
    volume (lagged one bar). Signal -1 on that closed bar; the screen enters short at
    the next bar's open. No long side: the crowded, collateral-impaired side is longs."""
    r = df["close"].pct_change()
    sd = r.rolling(168, min_periods=100).std().shift(1)
    vm = df["volume"].rolling(168, min_periods=100).median().shift(1)
    cascade = (r <= -3.0 * sd) & (df["volume"] >= 2.0 * vm)
    return pd.Series(np.where(cascade.fillna(False), -1, 0), index=df.index).astype(int)
