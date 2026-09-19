import numpy as np
import pandas as pd

# Deribit BTC/ETH options expiry calendar: last Friday of each calendar month,
# 08:00 UTC (monthly), with the March/June/September/December expiries also
# serving as the quarterly expiry (same date, same mechanism, larger notional).
# This is a public, fixed exchange calendar, not derived from any price data,
# so it is trivially closed-bar-safe and identical on any historical prefix.

def _last_friday_expiries(index):
    dates = pd.Series(index.normalize().unique())
    out = []
    for d in dates:
        # last Friday of d's month at 08:00 UTC
        month_end = (d + pd.offsets.MonthEnd(0))
        # walk back from month end to the last Friday (weekday()==4)
        offset = (month_end.weekday() - 4) % 7
        last_friday = month_end - pd.Timedelta(days=offset)
        out.append(last_friday.normalize() + pd.Timedelta(hours=8))
    return sorted(set(out))


def signals(df: pd.DataFrame) -> pd.Series:
    out = pd.Series(0, index=df.index, dtype=int)
    if len(df) < 40:
        return out

    expiries = _last_friday_expiries(df.index)
    close = df["close"]
    ret1h = close.pct_change()

    # pre-expiry realized-vol compression check: last 24h stdev of hourly
    # returns vs trailing 20-day (480h) average stdev, using only bars
    # strictly before the current bar (closed-bar safe).
    rv_short = ret1h.rolling(24).std()
    rv_long = ret1h.rolling(480, min_periods=120).std()

    for exp_ts in expiries:
        # find first bar at/after settlement (closed bar only)
        post = df.index[df.index >= exp_ts]
        if len(post) == 0:
            continue
        settle_bar = post[0]
        loc = df.index.get_loc(settle_bar)
        if loc < 30 or loc + 1 >= len(df):
            continue
        # compression check uses data strictly before settlement
        pre_rv_short = rv_short.iloc[loc - 1]
        pre_rv_long = rv_long.iloc[loc - 1]
        if pd.isna(pre_rv_short) or pd.isna(pre_rv_long) or pre_rv_long == 0:
            continue
        compressed = pre_rv_short < 0.7 * pre_rv_long
        if not compressed:
            continue
        # first large-range bar in the 0-8h post-settlement window sets direction
        window_end = min(loc + 8, len(df) - 1)
        window = df.iloc[loc:window_end + 1]
        bar_range = (window["close"] - window["open"]).abs() / window["open"]
        atr_proxy = ((df["high"] - df["low"]) / df["close"]).rolling(48).mean().iloc[loc - 1]
        if pd.isna(atr_proxy) or atr_proxy == 0:
            continue
        big = bar_range[bar_range > 1.5 * atr_proxy]
        if big.empty:
            continue
        trigger_ts = big.index[0]
        trigger_loc = df.index.get_loc(trigger_ts)
        direction = np.sign(df["close"].iloc[trigger_loc] - df["open"].iloc[trigger_loc])
        if direction == 0 or trigger_loc + 1 >= len(df):
            continue
        # enter at the bar after the triggering large-range bar (closed-bar entry)
        entry_loc = trigger_loc + 1
        out.iloc[entry_loc] = int(direction)

    return out.fillna(0).astype(int)
