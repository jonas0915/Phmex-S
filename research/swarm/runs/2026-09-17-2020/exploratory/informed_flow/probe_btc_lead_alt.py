"""EXPLORATORY probe, not a screen — numbers here are NOT evidence for a verdict.
Purpose: shape the informed_flow-btc-lead-alt thesis's expected_trades_per_week and
sanity-check that a BTC-lag continuation signal actually fires on long_1h TRAIN data.
Dataset: long_1h, era='train' only (train ends ~2026-04-24). No mr_edge data used here
(long_1h thesis must not touch mr_edge >= 2026-04-23 per STANDARDS #6 / DATA.md caveat).
"""
from research.swarm.lib import load_data as ld
import numpy as np
import pandas as pd

DATASET = "long_1h"
TF = "1h"
ALTS = ["1000PEPE", "1000SHIB", "ONDO", "TAO", "GIGGLE", "NEAR", "SUI", "DOGE", "XRP"]
BTC_LOOKBACK = 3       # bars of BTC trailing return
BTC_THRESH_BPS = 150   # BTC move over BTC_LOOKBACK bars must exceed this
ALT_LAG_CAP_BPS = 60   # alt itself must not have already moved this much in same direction

btc = ld.load_ohlcv("BTC", TF, era="train", dataset=DATASET)
btc_ret = (btc["close"] / btc["close"].shift(BTC_LOOKBACK) - 1.0) * 1e4  # bps

results = {}
for sym in ALTS:
    df = ld.load_ohlcv(sym, TF, era="train", dataset=DATASET)
    b = btc_ret.reindex(df.index)
    alt_ret = (df["close"] / df["close"].shift(BTC_LOOKBACK) - 1.0) * 1e4
    long_sig = (b > BTC_THRESH_BPS) & (alt_ret < ALT_LAG_CAP_BPS)
    short_sig = (b < -BTC_THRESH_BPS) & (alt_ret > -ALT_LAG_CAP_BPS)
    n_fire = int((long_sig | short_sig).sum())
    n_bars = len(df)
    weeks = n_bars / (24 * 7)
    results[sym] = {"n_fire": n_fire, "n_bars": n_bars, "weeks": round(weeks, 1),
                     "fires_per_week": round(n_fire / weeks, 2) if weeks else None}

total_fire = sum(v["n_fire"] for v in results.values())
weeks0 = list(results.values())[0]["weeks"]
print("per-symbol:", results)
print("TOTAL fires:", total_fire, "over", weeks0, "weeks ->", round(total_fire / weeks0, 2), "fires/week (all 9 symbols combined, pre-cooldown)")
