"""EXPLORATORY ONLY — not the screen, numbers here are NOT evidence (STANDARDS #2/#12).
Shapes cross_asset_btc_shock_lag thesis. Dataset: long_1h, train era only (no mr_edge
data used, so the cross-dataset holdout caveat does not apply here).
"""
import pandas as pd
from research.swarm.lib import load_data as ld

btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
btc_ret_prior = btc["close"].pct_change().shift(1)
thresh = 0.006
weeks = (btc.index.max() - btc.index.min()).total_seconds() / (7 * 86400)

for sym in ["ETH", "ADA", "XRP", "SOL"]:
    alt = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    close = alt["close"]
    b = btc_ret_prior.reindex(alt.index)
    sig = (b > thresh).astype(int)
    transitions = int(((sig == 1) & (sig.shift(1).fillna(0) == 0)).sum())
    for h in (1, 3, 6, 8):
        fwd = close.shift(-h) / close - 1
        up = b > thresh
        print(sym, "h", h, "n_up", int(up.sum()), "mean_fwd_up_bps", round(fwd[up].mean() * 1e4, 2),
              "unconditional_bps", round(fwd.mean() * 1e4, 2))
    print(sym, "raw_signal_bars", int(sig.sum()), "transitions(proxy trades)", transitions,
          "transitions_per_week", round(transitions / weeks, 2))
