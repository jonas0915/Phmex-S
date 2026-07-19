#!/usr/bin/env python3
"""Reconstruct indicator-position features at entry for each htf_l2 position.

Fidelity contract (matches bot exactly):
- bot: exchange.get_ohlcv(symbol, '5m', limit=500) -> df INCLUDES forming bar;
  strategy reads last = df.iloc[-1] (the forming bar, close = live price).
- here: closed 5m bars (ts+300s <= opened_at) + synthetic forming bar
  (open = first closed 1m open in window else entry px; high/low = extremes of
  closed 1m bars in window unioned with entry px; close = entry px;
  volume = sum of closed 1m vols), then take last 500 rows.
- indicator math imported from the repo's indicators.py (ema/rsi/atr/vwap),
  NOT reimplemented.

Pre-registered feature family (8, all side-oriented so + = stretched in trade
direction; for shorts distances are sign-flipped and RSI -> 100-RSI,
range_pos -> 1-range_pos):
  rsi14_o, rsi7_o, d_ema21_o (%), d_ema50_o (%), d_vwap_o (%),
  stretch_ema21_atr_o, stretch_vwap_atr_o, range_pos20_o
"""
import json, os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
GEOM = os.path.join(HERE, "..", "htf_l2_geometry_2026-07-18")
sys.path.insert(0, ROOT)
from indicators import ema, rsi, atr, vwap  # bot's own math

positions = json.load(open(os.path.join(GEOM, "positions.json")))

rows, gaps = [], []
for i, p in enumerate(positions):
    f5 = os.path.join(HERE, "cache", f"{i}_5m.json")
    f1 = os.path.join(HERE, "cache", f"{i}_1m.json")
    if not (os.path.exists(f5) and os.path.exists(f1)):
        gaps.append((i, p["symbol"], "no cache"))
        continue
    entry_ts = int(p["opened_at"])
    entry_px = float(p["entry"])
    bar5_ms = (entry_ts // 300) * 300 * 1000
    c5 = json.load(open(f5))
    c1 = json.load(open(f1))
    closed = [c for c in c5 if c[0] + 300000 <= entry_ts * 1000]
    if len(closed) < 60:
        gaps.append((i, p["symbol"], f"only {len(closed)} closed 5m bars"))
        continue
    # forming bar
    ones = [c for c in c1 if c[0] >= bar5_ms and c[0] + 60000 <= entry_ts * 1000]
    if ones:
        o = ones[0][1]
        h = max(max(c[2] for c in ones), entry_px)
        l = min(min(c[3] for c in ones), entry_px)
        v = sum(c[5] for c in ones)
    else:
        o = h = l = entry_px
        v = 0.0
    forming = [bar5_ms, o, h, l, entry_px, v]
    bars = closed + [forming]
    bars = bars[-500:]
    df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)

    c = df["close"]
    e21 = ema(c, 21).iloc[-1]
    e50 = ema(c, 50).iloc[-1]
    r14 = rsi(c, 14).iloc[-1]
    r7 = rsi(c, 7).iloc[-1]
    a14 = atr(df["high"], df["low"], c, 14).iloc[-1]
    vw = vwap(df["high"], df["low"], c, df["volume"]).iloc[-1]
    hi20 = df["high"].iloc[-20:].max()
    lo20 = df["low"].iloc[-20:].min()
    px = c.iloc[-1]

    if pd.isna(vw) or a14 <= 0 or hi20 == lo20:
        gaps.append((i, p["symbol"], "nan indicator"))
        continue

    d = 1.0 if p["side"] == "long" else -1.0
    d21 = (px - e21) / e21 * 100
    d50 = (px - e50) / e50 * 100
    dvw = (px - vw) / vw * 100
    s21 = (px - e21) / a14
    svw = (px - vw) / a14
    rp = (px - lo20) / (hi20 - lo20)

    rows.append({
        "idx": i, "symbol": p["symbol"], "side": p["side"],
        "net": p["actual_net"], "toxic": p["toxic"],
        "exit_reason": p["exit_reason"], "opened_at": entry_ts,
        "n_closed_bars": len(closed), "n_form_1m": len(ones),
        "rsi14_o": r14 if d > 0 else 100 - r14,
        "rsi7_o": r7 if d > 0 else 100 - r7,
        "d_ema21_o": d * d21, "d_ema50_o": d * d50, "d_vwap_o": d * dvw,
        "stretch_ema21_atr_o": d * s21, "stretch_vwap_atr_o": d * svw,
        "range_pos20_o": rp if d > 0 else 1 - rp,
        # raw (unoriented) kept for sanity checks
        "rsi14_raw": r14, "d_vwap_raw": dvw,
    })

json.dump(rows, open(os.path.join(HERE, "features.json"), "w"), indent=1)
print(f"features built: {len(rows)}/{len(positions)}")
full = sum(1 for r in rows if r["n_closed_bars"] >= 499)
print(f"full 500-bar lookback: {full}; short-lookback (60-498 bars): {len(rows) - full}")
for g in gaps:
    print("GAP:", g)
