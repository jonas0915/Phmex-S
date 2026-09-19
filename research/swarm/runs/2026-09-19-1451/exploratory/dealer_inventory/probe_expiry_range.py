"""EXPLORATORY ONLY — not the screen, numbers here are not evidence.
Sanity-check: is realized range in the 8h after Friday 08:00 UTC (Deribit weekly
options expiry) larger than the 24h immediately before it, on long_1h TRAIN data
(BTC, ETH)? long_1h train ends ~2026-04-24, so this never touches the
long_1h-holdout / mr_edge-overlap window (2026-04-23+).
"""
from research.swarm.lib import load_data
import pandas as pd
import numpy as np

for sym in ["BTC", "ETH"]:
    df = load_data.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    idx = df.index
    is_expiry_close = (idx.dayofweek == 4) & (idx.hour == 8)
    expiry_bars = df[is_expiry_close]
    pre_ranges = []
    post_ranges = []
    for ts in expiry_bars.index:
        pre = df.loc[(df.index < ts) & (df.index >= ts - pd.Timedelta(hours=8))]
        post = df.loc[(df.index > ts) & (df.index <= ts + pd.Timedelta(hours=8))]
        if len(pre) < 6 or len(post) < 6:
            continue
        pre_range_bps = (pre["high"].max() - pre["low"].min()) / pre["close"].iloc[-1] * 1e4
        post_range_bps = (post["high"].max() - post["low"].min()) / post["close"].iloc[-1] * 1e4
        pre_ranges.append(pre_range_bps)
        post_ranges.append(post_range_bps)
    pre_ranges = np.array(pre_ranges)
    post_ranges = np.array(post_ranges)
    print(sym, "n_expiries=", len(pre_ranges),
          "mean_pre_range_bps=", round(pre_ranges.mean(), 1) if len(pre_ranges) else None,
          "mean_post_range_bps=", round(post_ranges.mean(), 1) if len(post_ranges) else None,
          "frac_post_gt_pre=", round((post_ranges > pre_ranges).mean(), 2) if len(pre_ranges) else None)
