import numpy as np
import pandas as pd


def signals(df: pd.DataFrame) -> pd.Series:
    """Post-cascade deleveraging continuation SHORT on closed 1h bars.
    Cascade bar = 1h close-to-close return <= -3.0 x trailing-168-bar std of returns
    (std lagged one bar) AND bar volume >= 2.0 x trailing-168-bar median volume (lagged
    one bar). Signal -1 on that closed bar; the screen enters short at the next bar's
    open. Long side deliberately excluded (the crowded, collateral-impaired side is longs).
    Closed bars only: every rolling window ends at the current bar; no negative shifts."""
    r = df["close"].astype(float).pct_change()
    sd = r.rolling(168, min_periods=100).std().shift(1)
    vm = df["volume"].astype(float).rolling(168, min_periods=100).median().shift(1)
    cascade = (r <= -3.0 * sd) & (df["volume"].astype(float) >= 2.0 * vm)
    return pd.Series(np.where(cascade.fillna(False).to_numpy(), -1, 0), index=df.index).astype(int)
