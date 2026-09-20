"""EXPLORATORY ONLY — not the screen, numbers are not evidence.

Estimate trigger frequency (bars/week) for the forced_flows_daily_relever_flow
thesis: bar at UTC hour==22 whose |cum intraday return from day-open| exceeds
3%, on long_1h TRAIN era only (dataset train ends ~2026-04-24, well before the
2026-04-23 cross-dataset holdout caveat boundary, and we touch no mr_edge data
here at all, so the cross-dataset holdout rule does not apply).
"""
import pandas as pd
from research.swarm.lib import load_data

SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
THRESH = 0.03

for sym in SYMS:
    df = load_data.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    day = df.index.normalize()
    day_open = df.groupby(day)["open"].transform("first")
    cum_ret = df["close"] / day_open - 1
    hour = df.index.hour
    fire = (hour == 22) & (cum_ret.abs() > THRESH)
    n_bars = len(df)
    n_fire = int(fire.sum())
    weeks = n_bars / (24 * 7)
    print(f"{sym}: n_bars={n_bars} weeks={weeks:.1f} fires={n_fire} fires/week={n_fire/weeks:.3f} "
          f"date_range=[{df.index.min()}, {df.index.max()}]")
