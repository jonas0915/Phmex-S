#!/usr/bin/env python3
"""
Backtest: SMA(9)+SMA(15)+VWAP filter on v10 trades ONLY (#247-266).

Scenarios:
  A — Current v10 (actual results, no filter)
  B — SMA+VWAP filter only
  C — ADX gate + SMA+VWAP filter (combined)

Uses ccxt to fetch historical 5m candles around each trade's entry time.
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# -- Setup -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

exchange = ccxt.phemex({
    "apiKey": os.getenv("API_KEY"),
    "secret": os.getenv("API_SECRET"),
    "enableRateLimit": True,
})
exchange.load_markets()

# -- Load trades (v10 only: indices 246-265, trade #247-266) -----------------
with open(ROOT / "trading_state.json") as f:
    state = json.load(f)

all_trades = state["closed_trades"]
# v10 htf_confluence trades starting Mar 22 — trade #247 onward (0-based idx 246)
v10_trades = all_trades[246:]

print(f"Total closed trades: {len(all_trades)}")
print(f"v10 trades (#247-{246+len(v10_trades)}): {len(v10_trades)}")
print()

# -- Indicator helpers -------------------------------------------------------

def compute_sma(series, period):
    return series.rolling(window=period).mean()


def compute_vwap(df):
    """Session-anchored VWAP, resets at midnight UTC each day."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    tpv = tp * df["volume"]
    dates = df.index.normalize()
    cum_tpv = tpv.groupby(dates).cumsum()
    cum_vol = df["volume"].groupby(dates).cumsum()
    return cum_tpv / cum_vol.replace(0, np.nan)


def compute_adx(df, period=14):
    """ADX, +DI, -DI — matches indicators.py logic."""
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm_raw = high.diff().clip(lower=0)
    minus_dm_raw = (-low.diff()).clip(lower=0)
    plus_dm = plus_dm_raw.copy()
    minus_dm = minus_dm_raw.copy()
    plus_dm[plus_dm_raw <= minus_dm_raw] = 0
    minus_dm[minus_dm_raw <= plus_dm_raw] = 0
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr_s = tr.ewm(com=period - 1, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(com=period - 1, adjust=False).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(com=period - 1, adjust=False).mean() / atr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(com=period - 1, adjust=False).mean()
    return adx_val, plus_di, minus_di


# -- Candle cache ------------------------------------------------------------
candle_cache = {}


def fetch_candles(symbol, entry_ts):
    """Fetch 5m candles covering the entry time. Returns DataFrame."""
    entry_dt = datetime.fromtimestamp(entry_ts, tz=timezone.utc)
    day_start = entry_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    cache_key = f"{symbol}_{day_start.strftime('%Y%m%d')}"
    if cache_key in candle_cache:
        return candle_cache[cache_key]

    fetch_start = day_start - timedelta(hours=2)  # SMA warmup buffer
    fetch_end = entry_dt + timedelta(minutes=10)

    since_ms = int(fetch_start.timestamp() * 1000)
    end_ms = int(fetch_end.timestamp() * 1000)

    all_candles = []
    cursor = since_ms
    while cursor < end_ms:
        try:
            candles = exchange.fetch_ohlcv(symbol, "5m", since=cursor, limit=500)
        except Exception as e:
            print(f"  API error for {symbol}: {e}")
            time.sleep(2)
            try:
                candles = exchange.fetch_ohlcv(symbol, "5m", since=cursor, limit=500)
            except Exception:
                return None

        if not candles:
            break
        all_candles.extend(candles)
        cursor = candles[-1][0] + 1
        if len(candles) < 500:
            break
        time.sleep(0.5)

    if not all_candles:
        return None

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    df = df[~df.index.duplicated(keep="last")]
    df.sort_index(inplace=True)

    candle_cache[cache_key] = df
    time.sleep(0.5)
    return df


def find_entry_candle_idx(df, entry_ts):
    """Find candle index closest to but not after the entry timestamp."""
    entry_dt = pd.Timestamp(entry_ts, unit="s", tz="UTC")
    mask = df.index <= entry_dt
    if not mask.any():
        return None
    return df.index.get_loc(df.index[mask][-1])


# -- Run backtest ------------------------------------------------------------
results = []
skipped = 0

print(f"Processing {len(v10_trades)} v10 trades...")
print("-" * 60)

for i, trade in enumerate(v10_trades):
    trade_num = 247 + i  # 1-based trade number
    symbol = trade["symbol"]
    side = trade["side"]
    pnl = trade["pnl_usdt"]
    entry_ts = trade.get("opened_at")
    entry_price = trade["entry"]
    strategy = trade.get("strategy", "unknown")

    if not entry_ts:
        print(f"  #{trade_num} {symbol} — no timestamp, skipping")
        skipped += 1
        continue

    print(f"  [{i+1}/{len(v10_trades)}] #{trade_num} {symbol} {side} ({strategy})...")

    df = fetch_candles(symbol, entry_ts)
    if df is None:
        print(f"    -> API error, skipped")
        skipped += 1
        continue

    idx = find_entry_candle_idx(df, entry_ts)
    if idx is None or idx < 20:
        print(f"    -> insufficient candles (idx={idx}), skipped")
        skipped += 1
        continue

    window = df.iloc[:idx + 1].copy()

    sma9 = compute_sma(window["close"], 9)
    sma15 = compute_sma(window["close"], 15)
    vwap_vals = compute_vwap(window)
    adx_vals, plus_di, minus_di = compute_adx(window, 14)

    entry_close = window["close"].iloc[-1]
    sma9_val = sma9.iloc[-1]
    sma15_val = sma15.iloc[-1]
    vwap_val = vwap_vals.iloc[-1]
    adx_val = adx_vals.iloc[-1]

    if pd.isna(sma9_val) or pd.isna(sma15_val) or pd.isna(vwap_val):
        print(f"    -> NaN indicators, skipped")
        skipped += 1
        continue

    # Scenario B: SMA+VWAP filter
    if side == "long":
        sma_vwap_pass = (entry_close > sma9_val) and (sma9_val > sma15_val) and (entry_close > vwap_val)
    else:
        sma_vwap_pass = (entry_close < sma9_val) and (sma9_val < sma15_val) and (entry_close < vwap_val)

    # Scenario C: ADX + SMA+VWAP
    adx_pass = not pd.isna(adx_val) and adx_val > 20
    combined_pass = adx_pass and sma_vwap_pass

    results.append({
        "trade_num": trade_num,
        "symbol": symbol,
        "side": side,
        "strategy": strategy,
        "pnl": pnl,
        "entry_price": entry_price,
        "entry_close": entry_close,
        "sma9": sma9_val,
        "sma15": sma15_val,
        "vwap": vwap_val,
        "adx": adx_val if not pd.isna(adx_val) else 0,
        "sma_vwap_pass": sma_vwap_pass,
        "adx_pass": adx_pass,
        "combined_pass": combined_pass,
        "is_win": pnl > 0,
        "opened_at": entry_ts,
    })

print()
print(f"Processed: {len(results)} | Skipped: {skipped}")
print("=" * 60)

# -- Compile statistics ------------------------------------------------------
df_r = pd.DataFrame(results)


def scenario_stats(mask, label):
    subset = df_r[mask]
    n = len(subset)
    if n == 0:
        return {"label": label, "trades": 0, "wins": 0, "losses": 0, "wr": 0,
                "total_pnl": 0, "avg_pnl": 0}
    wins = (subset["pnl"] > 0).sum()
    losses = (subset["pnl"] <= 0).sum()
    wr = wins / n * 100
    total_pnl = subset["pnl"].sum()
    avg_pnl = subset["pnl"].mean()
    return {"label": label, "trades": n, "wins": int(wins), "losses": int(losses),
            "wr": wr, "total_pnl": total_pnl, "avg_pnl": avg_pnl}


stats_a = scenario_stats(pd.Series([True] * len(df_r)), "A: Current v10")
stats_b = scenario_stats(df_r["sma_vwap_pass"], "B: SMA+VWAP only")
stats_c = scenario_stats(df_r["combined_pass"], "C: ADX + SMA+VWAP")

filtered_b = df_r[~df_r["sma_vwap_pass"]]
filtered_c = df_r[~df_r["combined_pass"]]

# -- Print results -----------------------------------------------------------
print()
print("=" * 70)
print("  v10 TRADES ONLY: SMA(9) + SMA(15) + VWAP FILTER BACKTEST")
print("=" * 70)
print()
print(f"  Trades analyzed: {len(df_r)}  (skipped {skipped})")
print()

header = f"{'Scenario':<25} {'Trades':>6} {'Wins':>5} {'Losses':>6} {'WR%':>7} {'PnL($)':>9} {'Avg PnL':>8}"
print(header)
print("-" * len(header))
for s in [stats_a, stats_b, stats_c]:
    print(f"{s['label']:<25} {s['trades']:>6} {s['wins']:>5} {s['losses']:>6} {s['wr']:>6.1f}% {s['total_pnl']:>+9.2f} {s['avg_pnl']:>+8.4f}")

print()
print("-" * 70)
print("  FILTERED TRADES ANALYSIS")
print("-" * 70)
print()
print(f"  B filter removed {len(filtered_b)} trades:")
if len(filtered_b) > 0:
    fb_wins = (filtered_b["pnl"] > 0).sum()
    fb_losses = (filtered_b["pnl"] <= 0).sum()
    fb_pnl = filtered_b["pnl"].sum()
    print(f"    Winners removed: {int(fb_wins)} | Losers removed: {int(fb_losses)}")
    print(f"    PnL of removed trades: ${fb_pnl:+.2f}")
    print(f"    Net PnL improvement: ${-fb_pnl:+.2f}" if fb_pnl < 0 else f"    Net PnL LOSS: ${-fb_pnl:+.2f}")
print()
print(f"  C filter removed {len(filtered_c)} trades:")
if len(filtered_c) > 0:
    fc_wins = (filtered_c["pnl"] > 0).sum()
    fc_losses = (filtered_c["pnl"] <= 0).sum()
    fc_pnl = filtered_c["pnl"].sum()
    print(f"    Winners removed: {int(fc_wins)} | Losers removed: {int(fc_losses)}")
    print(f"    PnL of removed trades: ${fc_pnl:+.2f}")
    print(f"    Net PnL improvement: ${-fc_pnl:+.2f}" if fc_pnl < 0 else f"    Net PnL LOSS: ${-fc_pnl:+.2f}")

# -- Per-trade detail --------------------------------------------------------
print()
print("-" * 70)
print("  TRADE-BY-TRADE DETAIL")
print("-" * 70)
print()
hdr = f"{'#':>4} {'Symbol':<20} {'Side':<6} {'Strategy':<28} {'PnL':>8} {'B?':>4} {'C?':>4}"
print(hdr)
print("-" * len(hdr))
for _, row in df_r.iterrows():
    b_flag = "YES" if row["sma_vwap_pass"] else "no"
    c_flag = "YES" if row["combined_pass"] else "no"
    print(f"{row['trade_num']:>4} {row['symbol']:<20} {row['side']:<6} {row['strategy']:<28} {row['pnl']:>+8.2f} {b_flag:>4} {c_flag:>4}")

# -- Per-side breakdown ------------------------------------------------------
print()
print("-" * 70)
print("  PER-SIDE BREAKDOWN")
print("-" * 70)
for side in ["long", "short"]:
    side_mask = df_r["side"] == side
    sa = scenario_stats(side_mask, f"A: {side.upper()}")
    sb = scenario_stats(side_mask & df_r["sma_vwap_pass"], f"B: {side.upper()} (SMA+VWAP)")
    sc = scenario_stats(side_mask & df_r["combined_pass"], f"C: {side.upper()} (ADX+SMA+VWAP)")
    print()
    for s in [sa, sb, sc]:
        print(f"  {s['label']:<30} {s['trades']:>3} trades | WR {s['wr']:.1f}% | PnL ${s['total_pnl']:+.2f} | Avg ${s['avg_pnl']:+.4f}")

# -- Save report to markdown ------------------------------------------------
report_path = ROOT / "reports" / "sma_vwap_v10_backtest.md"
with open(report_path, "w") as f:
    f.write("# v10 Trades: SMA(9) + SMA(15) + VWAP Filter Backtest\n\n")
    f.write(f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n")
    f.write(f"**Scope**: v10 trades only (#247-{246+len(v10_trades)}, Mar 22 onward)\n\n")
    f.write(f"**Trades analyzed**: {len(df_r)} (skipped {skipped})\n\n")

    f.write("## Filter Logic\n\n")
    f.write("- **LONG**: close > SMA(9), SMA(9) > SMA(15), close > VWAP\n")
    f.write("- **SHORT**: close < SMA(9), SMA(9) < SMA(15), close < VWAP\n")
    f.write("- **ADX gate**: 5m ADX > 20\n\n")

    f.write("## Results Summary\n\n")
    f.write("| Scenario | Trades | Wins | Losses | WR% | Total PnL | Avg PnL |\n")
    f.write("|----------|--------|------|--------|-----|-----------|----------|\n")
    for s in [stats_a, stats_b, stats_c]:
        f.write(f"| {s['label']} | {s['trades']} | {s['wins']} | {s['losses']} | {s['wr']:.1f}% | ${s['total_pnl']:+.2f} | ${s['avg_pnl']:+.4f} |\n")

    f.write("\n## Filter Impact\n\n")

    f.write("### Scenario B (SMA+VWAP only)\n\n")
    if len(filtered_b) > 0:
        fb_wins = (filtered_b["pnl"] > 0).sum()
        fb_losses = (filtered_b["pnl"] <= 0).sum()
        fb_pnl = filtered_b["pnl"].sum()
        f.write(f"- Trades removed: {len(filtered_b)}\n")
        f.write(f"- Winners removed: {int(fb_wins)} | Losers removed: {int(fb_losses)}\n")
        f.write(f"- PnL of removed trades: ${fb_pnl:+.2f}\n")
        f.write(f"- **Net improvement**: ${-fb_pnl:+.2f}\n\n")
    else:
        f.write("- No trades filtered.\n\n")

    f.write("### Scenario C (ADX + SMA+VWAP)\n\n")
    if len(filtered_c) > 0:
        fc_wins = (filtered_c["pnl"] > 0).sum()
        fc_losses = (filtered_c["pnl"] <= 0).sum()
        fc_pnl = filtered_c["pnl"].sum()
        f.write(f"- Trades removed: {len(filtered_c)}\n")
        f.write(f"- Winners removed: {int(fc_wins)} | Losers removed: {int(fc_losses)}\n")
        f.write(f"- PnL of removed trades: ${fc_pnl:+.2f}\n")
        f.write(f"- **Net improvement**: ${-fc_pnl:+.2f}\n\n")
    else:
        f.write("- No trades filtered.\n\n")

    f.write("## Trade-by-Trade Detail\n\n")
    f.write("| # | Symbol | Side | Strategy | PnL | Passed B? | Passed C? |\n")
    f.write("|---|--------|------|----------|-----|-----------|----------|\n")
    for _, row in df_r.iterrows():
        b_flag = "YES" if row["sma_vwap_pass"] else "no"
        c_flag = "YES" if row["combined_pass"] else "no"
        f.write(f"| {row['trade_num']:.0f} | {row['symbol']} | {row['side']} | {row['strategy']} | ${row['pnl']:+.2f} | {b_flag} | {c_flag} |\n")

    f.write("\n## Per-Side Breakdown\n\n")
    f.write("| Scenario | Trades | WR% | PnL | Avg PnL |\n")
    f.write("|----------|--------|-----|-----|----------|\n")
    for side in ["long", "short"]:
        side_mask = df_r["side"] == side
        for label, mask in [
            (f"A: {side.upper()}", side_mask),
            (f"B: {side.upper()} (SMA+VWAP)", side_mask & df_r["sma_vwap_pass"]),
            (f"C: {side.upper()} (ADX+SMA+VWAP)", side_mask & df_r["combined_pass"]),
        ]:
            s = scenario_stats(mask, label)
            f.write(f"| {s['label']} | {s['trades']} | {s['wr']:.1f}% | ${s['total_pnl']:+.2f} | ${s['avg_pnl']:+.4f} |\n")

    # Verdict
    f.write("\n## Verdict\n\n")
    b_better = stats_b["total_pnl"] > stats_a["total_pnl"]
    c_better = stats_c["total_pnl"] > stats_a["total_pnl"]
    if b_better:
        f.write(f"**Scenario B (SMA+VWAP) improves PnL by ${stats_b['total_pnl'] - stats_a['total_pnl']:+.2f}** ")
        f.write(f"while reducing trade count from {stats_a['trades']} to {stats_b['trades']}.\n\n")
    else:
        f.write(f"Scenario B (SMA+VWAP) would have **reduced** PnL by ${stats_b['total_pnl'] - stats_a['total_pnl']:+.2f}. ")
        f.write(f"The filter removes too many winners.\n\n")
    if c_better:
        f.write(f"**Scenario C (ADX+SMA+VWAP) improves PnL by ${stats_c['total_pnl'] - stats_a['total_pnl']:+.2f}** ")
        f.write(f"with {stats_c['trades']} trades.\n")
    else:
        f.write(f"Scenario C (ADX+SMA+VWAP) would have **reduced** PnL by ${stats_c['total_pnl'] - stats_a['total_pnl']:+.2f}. ")
        f.write(f"Not recommended as a blanket filter.\n")

print()
print(f"Report saved to: {report_path}")
print("Done.")
