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
    ts = df["timestamp"]
    hour = ts.dt.hour; minute = ts.dt.minute
    anchor_mask = hour.isin([0, 8, 16]) & (minute == 0)
    anchor_idx = np.where(anchor_mask.values)[0]
    highs = df["high"].values; lows = df["low"].values; closes = df["close"].values
    vols = df["volume"].values

    count = 0
    for i in anchor_idx:
        if i + 15 >= n_bars or i < 20:
            continue
        or_high = highs[i:i+3].max()
        or_low = lows[i:i+3].min()
        or_height = or_high - or_low
        if or_height <= 0:
            continue
        vol_ref = vols[i-12:i].mean() if i >= 12 else vols[:i].mean()
        window_c = closes[i+3:i+15]
        window_v = vols[i+3:i+15]
        up_hits = np.where((window_c > or_high + 0.3*or_height) & (window_v > 1.5*vol_ref))[0]
        dn_hits = np.where((window_c < or_low - 0.3*or_height) & (window_v > 1.5*vol_ref))[0]
        if len(up_hits) > 0 or len(dn_hits) > 0:
            count += 1

    print(sym, "tightened sig2 (OR breakout, mag>0.3xOR + vol>1.5x) count:", count,
          "per_week:", round(count/weeks,3), "n_anchors:", len(anchor_idx))
