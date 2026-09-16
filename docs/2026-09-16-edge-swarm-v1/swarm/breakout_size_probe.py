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
    sma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    bw = (upper - lower) / sma20
    bw_p10 = bw.rolling(500, min_periods=200).apply(lambda x: np.nanpercentile(x, 10), raw=False)
    squeeze_bar = (bw <= bw_p10)
    persist = squeeze_bar.rolling(6).sum() >= 6
    idx = np.where(persist.fillna(False).values)[0]
    bw_at_squeeze = bw.values[idx]
    print(sym, "n squeeze bars:", len(idx),
          "median bandwidth %:", round(np.nanmedian(bw_at_squeeze)*100,3),
          "p25:", round(np.nanpercentile(bw_at_squeeze,25)*100,3),
          "p75:", round(np.nanpercentile(bw_at_squeeze,75)*100,3))
