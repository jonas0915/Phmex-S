#!/usr/bin/env python3
"""Fetch fresh OHLCV (5m + 1h) for the flow-capture window so backtest.py can
replay flow against matching candles. Reuses fetch_ohlcv() from fetch_history.py.

Writes backtest_data/{SYMBOL}_{tf}.csv with a `timestamp` column, the exact format
load_candles() expects (pd.read_csv parse_dates=['timestamp'], index_col='timestamp').

Symbols = the pairs that actually traded live during the sprint window (from
trading_state.json), so the calibration compares sim vs live on the same universe.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fetch_history import fetch_ohlcv  # functional; only main() in that file is broken

# 16 symbols traded live 2026-05-12 -> 2026-05-30 (verified from trading_state.json,
# closed_trades since 5/10; counts: ETH8 INJ8 TON6 ONDO5 WLD5 DOGE4 XLM3 ENA2 ARB2
# XRP2 BTC2 RENDER2 TAO1 CFX1 ZEC1 BCH1)
SYMBOLS = [
    "ETH/USDT:USDT", "INJ/USDT:USDT", "TON/USDT:USDT", "ONDO/USDT:USDT",
    "WLD/USDT:USDT", "DOGE/USDT:USDT", "XLM/USDT:USDT", "ENA/USDT:USDT",
    "ARB/USDT:USDT", "XRP/USDT:USDT", "BTC/USDT:USDT", "RENDER/USDT:USDT",
    "TAO/USDT:USDT", "CFX/USDT:USDT", "ZEC/USDT:USDT", "BCH/USDT:USDT",
]
TIMEFRAMES = ["5m", "1h"]
DAYS = 22  # covers 2026-05-08 -> now, safely spanning the flow window (May 11-30)
# Separate dir so we never clobber the Jan-Apr baseline CSVs in backtest_data/.
OUT_DIR = "backtest_data_may"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    total = len(SYMBOLS) * len(TIMEFRAMES)
    done = 0
    for symbol in SYMBOLS:
        safe = symbol.replace("/", "_").replace(":", "_")
        for tf in TIMEFRAMES:
            done += 1
            out = os.path.join(OUT_DIR, f"{safe}_{tf}.csv")
            print(f"[{done}/{total}] {symbol} {tf} -> {out}")
            try:
                df = fetch_ohlcv(symbol, timeframe=tf, days=DAYS)
                if df is None or df.empty:
                    print(f"  !! EMPTY for {symbol} {tf}")
                    continue
                df.to_csv(out, index=False)
                print(f"  saved {len(df)} rows | {df['timestamp'].min()} -> {df['timestamp'].max()}")
            except Exception as e:
                print(f"  !! ERROR {symbol} {tf}: {e}")
    print("DONE")


if __name__ == "__main__":
    main()
