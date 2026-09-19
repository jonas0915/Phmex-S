"""EXPLORATORY ONLY — not the screen, not evidence for the pass bar. Shapes the
informed_flow BTC-leads-alts thesis. Uses long_1h TRAIN era only (era boundary ~2026-04-24),
which is entirely before the mr_edge/long_1h cross-dataset holdout caveat cutoff
(2026-04-23) — this probe never touches mr_edge, so the caveat does not bind here anyway,
but is respected on principle (long_1h only).
"""
from research.swarm.lib import load_data as ld
import numpy as np

BTC = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
K = 3          # trailing window, hours
THRESH = 150   # bps
LAG_RATIO = 0.5

btc_ret = BTC["close"].pct_change(K) * 1e4  # bps

alts = ["DOGE", "ADA", "XRP", "LTC", "LINK", "UNI", "NEAR", "SUI", "ONDO", "AAVE",
        "TAO", "XLM", "1000PEPE", "1000SHIB", "GIGGLE", "BNB"]

print(f"{'sym':10s} {'n_up_fire':>9s} {'n_dn_fire':>9s} {'fwd_ret_up_mean_bps':>20s} {'fwd_ret_dn_mean_bps':>20s}")
for sym in alts:
    try:
        df = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    except FileNotFoundError:
        print(f"{sym:10s} NO DATA")
        continue
    idx = df.index.intersection(BTC.index)
    d = df.loc[idx]
    b = btc_ret.reindex(idx)
    alt_ret = d["close"].pct_change(K) * 1e4
    up_fire = (b > THRESH) & (alt_ret < b * LAG_RATIO)
    dn_fire = (b < -THRESH) & (alt_ret > b * LAG_RATIO)
    # forward K-bar return of the alt AFTER the fire bar (exploratory shape-check only,
    # not the frozen screen's exit rule)
    fwd = d["close"].pct_change(K).shift(-K) * 1e4
    fwd_up = fwd[up_fire].mean()
    fwd_dn = fwd[dn_fire].mean()
    print(f"{sym:10s} {int(up_fire.sum()):9d} {int(dn_fire.sum()):9d} {fwd_up:20.2f} {fwd_dn:20.2f}")
