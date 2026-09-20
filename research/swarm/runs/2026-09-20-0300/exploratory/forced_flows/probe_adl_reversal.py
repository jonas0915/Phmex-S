"""EXPLORATORY ONLY — not the screen, numbers are not evidence.

Estimate trigger frequency (bars/week) for forced_flows_adl_winner_reversal:
a 1h bar whose |return| exceeds the trailing 720-bar (30d) 99th percentile of
|return|, both computed causally (shift(1) before the trailing window), on
mr_edge TRAIN era (no cross-dataset holdout concern -- this thesis is mr_edge
native, not long_1h).
"""
import pandas as pd
from research.swarm.lib import load_data

SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
W = 720
Q = 0.97

for sym in SYMS:
    df = load_data.load_ohlcv(sym, "1h", era="train", dataset="mr_edge")
    ret = df["close"].pct_change()
    abs_ret = ret.abs()
    thresh = abs_ret.rolling(W, min_periods=W).quantile(Q).shift(1)
    fire = abs_ret > thresh
    n_bars = len(df)
    n_fire = int(fire.sum())
    weeks = n_bars / (24 * 7)
    print(f"{sym}: n_bars={n_bars} weeks={weeks:.1f} fires={n_fire} fires/week={n_fire/weeks:.3f} "
          f"date_range=[{df.index.min()}, {df.index.max()}]")
