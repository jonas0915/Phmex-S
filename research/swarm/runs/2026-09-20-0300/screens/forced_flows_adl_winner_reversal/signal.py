"""ADL-tier extreme-magnitude reversal proxy. Closed-bar only, causal.

Trigger: a 1h bar whose |return| exceeds the trailing 720-bar (30d) 97th
percentile of |return| for that symbol, both the rolling window and its
quantile computed from STRICTLY PRIOR bars (shift(1)) so the current bar
cannot inform its own threshold. Signal = -sign(triggering bar's return)
(reversal bet, entered at the next bar's open per screen.simulate), betting
forced ADL closure of profitable opposite-side positions at this magnitude
tier dampens/reverses the move rather than extending it.
"""
import pandas as pd

W = 720   # 30d trailing window at 1h bars
Q = 0.97  # percentile defining the ADL-plausible magnitude tail


def signals(df: pd.DataFrame) -> pd.Series:
    ret = df["close"].pct_change()
    abs_ret = ret.abs()

    thresh = abs_ret.rolling(W, min_periods=W).quantile(Q).shift(1)
    fire = abs_ret > thresh

    sig = pd.Series(0, index=df.index, dtype=int)
    sig[fire & (ret > 0)] = -1
    sig[fire & (ret < 0)] = 1
    return sig
