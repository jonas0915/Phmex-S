"""Candle cache/fetch for the scan. Cache-first; network only on miss."""
import os
import time
import pandas as pd

FALLBACK_PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
                  "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT",
                  "LTC/USDT:USDT", "1000PEPE/USDT:USDT", "1000SHIB/USDT:USDT",
                  "ENA/USDT:USDT"]
COLS = ["ts", "open", "high", "low", "close", "volume"]


def _slug(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def scan_pairs() -> list[str]:
    return list(FALLBACK_PAIRS)


def load_candles(symbol: str, timeframe: str, days: int = 90,
                 data_dir: str = "data") -> pd.DataFrame:
    path = os.path.join(data_dir, f"{_slug(symbol)}_{timeframe}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path)[COLS]
    else:
        import ccxt
        ex = ccxt.phemex()
        since = ex.milliseconds() - days * 86_400_000
        rows = []
        while True:
            page = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not page:
                break
            rows.extend(page)
            if len(page) < 1000:
                break
            since = page[-1][0] + 1
            time.sleep(0.5)
        df = pd.DataFrame(rows, columns=COLS)
        os.makedirs(data_dir, exist_ok=True)
        df.to_csv(path, index=False)
    return (df.sort_values("ts").drop_duplicates("ts", keep="first")
              .reset_index(drop=True))
