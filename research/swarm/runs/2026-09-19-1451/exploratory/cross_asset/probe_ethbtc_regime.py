"""EXPLORATORY ONLY — not the screen, numbers here are NOT evidence (STANDARDS #2/#12).
Shapes cross_asset_ethbtc_regime_rotation thesis. Dataset: long_1h, train era only
(no mr_edge data used, so the cross-dataset holdout caveat does not apply here).
"""
import pandas as pd
from research.swarm.lib import load_data as ld

btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
eth = ld.load_ohlcv("ETH", "1h", era="train", dataset="long_1h")
idx = btc.index.intersection(eth.index)
ratio = eth["close"].reindex(idx) / btc["close"].reindex(idx)
ma = ratio.rolling(48).mean()
cross_up = (ratio > ma) & (ratio.shift(1) <= ma.shift(1))
print("n cross_up events", int(cross_up.sum()), "over", len(idx), "bars")

weeks = (idx.max() - idx.min()).total_seconds() / (7 * 86400)
for sym in ["SOL", "ADA", "XRP", "LINK"]:
    alt = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    close = alt["close"].reindex(idx)
    for h in (12, 24, 48):
        fwd = close.shift(-h) / close - 1
        cond = fwd[cross_up.reindex(idx).fillna(False)]
        print(sym, "h", h, "n_events", int(cross_up.sum()), "mean_fwd_bps", round(cond.mean() * 1e4, 2),
              "unconditional_bps", round(fwd.mean() * 1e4, 2))
print("events_per_week", round(cross_up.sum() / weeks, 2))
