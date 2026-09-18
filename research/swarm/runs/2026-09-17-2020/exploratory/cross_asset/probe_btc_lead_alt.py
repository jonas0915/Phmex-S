"""EXPLORATORY ONLY — not the screen, not evidence. Shapes the cross_asset thesis
(BTC leads thin-liquidity altcoins). Train era, mr_edge dataset, 1h timeframe.
"""
from __future__ import annotations
import pandas as pd
from research.swarm.lib import load_data as ld

TF = "1h"
DATASET = "mr_edge"
LOOKBACK = 3          # BTC trailing return window, in closed bars
THRESH_BPS = 150.0    # BTC move required to fire
ALTS = ["DOGE", "XRP", "SOL", "ADA", "LINK", "AVAX", "BCH", "UNI", "XLM", "LTC"]

btc = ld.load_ohlcv("BTC", TF, era="train", dataset=DATASET)
btc_ret = (btc["close"] / btc["close"].shift(LOOKBACK) - 1) * 1e4  # bps, trailing K-bar return ending at this closed bar

rows = []
for sym in ALTS:
    df = ld.load_ohlcv(sym, TF, era="train", dataset=DATASET)
    b = btc_ret.reindex(df.index).ffill()
    fires_long = b > THRESH_BPS
    fires_short = b < -THRESH_BPS
    n_long, n_short = int(fires_long.sum()), int(fires_short.sum())
    span_days = (df.index.max() - df.index.min()).total_seconds() / 86400
    rows.append({"symbol": sym, "n_bars": len(df), "span_days": round(span_days, 1),
                 "fires_long": n_long, "fires_short": n_short,
                 "fires_per_week": round((n_long + n_short) / (span_days / 7), 2) if span_days > 0 else None})

out = pd.DataFrame(rows)
print(out.to_string(index=False))
print("\nTotal fires/week across universe:", round(out["fires_per_week"].sum(), 2))
