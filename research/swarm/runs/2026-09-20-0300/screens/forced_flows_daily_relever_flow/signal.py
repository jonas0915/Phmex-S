"""Leveraged-token daily-rebalance continuation proxy. Closed-bar only, causal.

Trigger: the UTC hour==22 bar, if the day's cumulative return from that UTC
day's first (00:00) bar open through the current bar's close exceeds 3% in
absolute value. Signal = sign of that cumulative return (continuation bet,
entered at the next bar's open -- hour 23 -- per screen.simulate), betting
forced leveraged-token issuer rebalancing extends the move into and past the
00:00 UTC daily reset.
"""
import pandas as pd

HOUR_TRIGGER = 22
THRESH = 0.03


def signals(df: pd.DataFrame) -> pd.Series:
    day = df.index.normalize()
    day_open = df.groupby(day)["open"].transform("first")
    cum_ret = df["close"] / day_open - 1

    hour = df.index.hour
    fire = (hour == HOUR_TRIGGER) & (cum_ret.abs() > THRESH)

    sig = pd.Series(0, index=df.index, dtype=int)
    sig[fire & (cum_ret > 0)] = 1
    sig[fire & (cum_ret < 0)] = -1
    return sig
