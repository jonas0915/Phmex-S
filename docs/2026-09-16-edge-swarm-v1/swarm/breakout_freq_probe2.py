import pandas as pd
import numpy as np
import os

DATA_DIR = "/Users/jonaspenaso/Desktop/Phmex-S/backtest_data"
symbols = ["BTC", "ETH"]

def load(sym):
    path = os.path.join(DATA_DIR, f"{sym}_USDT_USDT_5m.csv")
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)

for sym in symbols:
    df = load(sym)
    n_bars = len(df)
    span_days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).total_seconds() / 86400.0
    weeks = span_days / 7.0

    sma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    bw = (upper - lower) / sma20
    bw_p10 = bw.rolling(500, min_periods=200).apply(lambda x: np.nanpercentile(x, 10), raw=False)
    squeeze_bar = (bw <= bw_p10)
    # require squeeze persistence >=6 consecutive bars (30 min)
    persist = squeeze_bar.rolling(6).sum() >= 6
    vol_avg20 = df["volume"].rolling(20).mean()
    breakout_up = (df["close"] > upper) & (df["volume"] > 2.0 * vol_avg20)
    breakout_dn = (df["close"] < lower) & (df["volume"] > 2.0 * vol_avg20)
    breakout_any = (breakout_up | breakout_dn).values
    persist_idx = np.where(persist.fillna(False).values)[0]

    count = 0
    last = -100
    for i in persist_idx:
        if i - last <= 24:
            continue
        end = min(i + 4, n_bars)
        hit = np.where(breakout_any[i:end])[0]
        if len(hit) > 0:
            count += 1
            last = i + hit[0]

    print(sym, "tightened sig1 count:", count, "per_week:", round(count/weeks,3), "weeks:", round(weeks,2))
