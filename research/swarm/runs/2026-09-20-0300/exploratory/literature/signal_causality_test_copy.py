import pandas as pd
import numpy as np
from research.swarm.lib import load_data as ld

BTC_THRESHOLD = 0.00644  # 90th pct |BTC 1h log return|, train exploratory probe

def signals(df: pd.DataFrame) -> pd.Series:
    btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="mr_edge")
    btc_ret = np.log(btc["close"]).diff().rename("btc_ret")
    left = pd.DataFrame({"ts": df.index}).sort_values("ts")
    right = btc_ret.reset_index()
    right.columns = ["ts", "btc_ret"]
    right = right.sort_values("ts")
    merged = pd.merge_asof(left, right, on="ts", direction="backward")
    aligned = pd.Series(merged["btc_ret"].to_numpy(), index=df.index)
    sig = pd.Series(0, index=df.index, dtype=int)
    sig[aligned >= BTC_THRESHOLD] = 1
    sig[aligned <= -BTC_THRESHOLD] = -1
    return sig
