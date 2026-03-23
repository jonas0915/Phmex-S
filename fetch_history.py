#!/usr/bin/env python3
"""Fetch historical OHLCV data from Phemex for backtesting."""
import ccxt
import pandas as pd
import os
import time
import sys

def fetch_ohlcv(symbol, timeframe="5m", days=30, exchange_id="phemex"):
    """Fetch N days of OHLCV data, paginating as needed."""
    exchange = ccxt.phemex({"enableRateLimit": True})
    exchange.load_markets()

    all_candles = []
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    since = exchange.milliseconds() - (days * 24 * 60 * 60 * 1000)

    print(f"Fetching {symbol} {timeframe} for {days} days...")
    while since < exchange.milliseconds():
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not candles:
                break
            all_candles.extend(candles)
            since = candles[-1][0] + tf_ms
            print(f"  {len(all_candles)} candles fetched...", end="\r")
            time.sleep(0.5)  # rate limit
        except Exception as e:
            print(f"  Error: {e}, retrying...")
            time.sleep(2)

    print(f"  {len(all_candles)} candles total for {symbol} {timeframe}")

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def main():
    pairs = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT"]
    timeframes = ["5m", "1h"]
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    os.makedirs("backtest_data", exist_ok=True)

    for pair in pairs:
        for tf in timeframes:
            df = fetch_ohlcv(pair, tf, days)
            safe_name = pair.replace("/", "_").replace(":", "_")
            path = f"backtest_data/{safe_name}_{tf}.csv"
            df.to_csv(path, index=False)
            print(f"Saved {path} ({len(df)} candles)")


if __name__ == "__main__":
    main()
