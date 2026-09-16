import pandas as pd, numpy as np, os
DATA_DIR = "/Users/jonaspenaso/Desktop/Phmex-S/backtest_data"
for sym in ["BTC","ETH"]:
    df = pd.read_csv(os.path.join(DATA_DIR, f"{sym}_USDT_USDT_5m.csv"), parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    hour = df["timestamp"].dt.hour; minute = df["timestamp"].dt.minute
    anchor_idx = np.where((hour.isin([0,8,16]) & (minute==0)).values)[0]
    heights = []
    for i in anchor_idx:
        if i+3 >= len(df): continue
        h = df["high"].values[i:i+3].max(); l = df["low"].values[i:i+3].min()
        c = df["close"].values[i]
        heights.append((h-l)/c*100)
    heights = np.array(heights)
    print(sym, "median OR height %:", round(np.median(heights),3), "p75:", round(np.percentile(heights,75),3))
