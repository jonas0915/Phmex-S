"""
Phmex2 Volatility Scanner
Continuously scans Phemex USDT perpetuals for high-volatility opportunities.

Scores each market on:
  - 24h price change %
  - Short-term momentum (last 10 candles % move)
  - Volume spike (current vs average)
  - ATR relative to price (volatility %)
  - Active trend alignment (EMA 9 > EMA 21 > EMA 50)
"""
import time
from config import Config
from logger import setup_logger

logger = setup_logger()


def scan_top_gainers(client, top_n: int = None, min_volume: float = None) -> list[str]:
    """Quick 24h gainer scan — used at startup."""
    top_n = top_n or Config.SCANNER_TOP_N
    min_volume = min_volume or Config.SCANNER_MIN_VOLUME

    try:
        tickers = client.fetch_tickers()
    except Exception as e:
        logger.error(f"Scanner failed to fetch tickers: {e}")
        return Config.TRADING_PAIRS

    candidates = []
    for symbol, t in tickers.items():
        if not symbol.endswith("/USDT:USDT"):
            continue
        info = t.get("info", {})
        try:
            close  = float(info.get("closeRp") or 0)
            open_  = float(info.get("openRp")  or 0)
            volume = float(info.get("turnoverRv") or 0)
            if close > 0 and open_ > 0 and volume >= min_volume:
                change = (close - open_) / open_ * 100
                candidates.append({"symbol": symbol, "change": change, "volume": volume, "price": close})
        except Exception:
            continue

    candidates.sort(key=lambda x: x["change"], reverse=True)
    top = candidates[:top_n]

    if top:
        logger.info(f"[SCANNER] Top {len(top)} gainers:")
        for c in top:
            logger.info(f"  {c['symbol']:<25} {c['change']:>+6.2f}%  vol: ${c['volume']:,.0f}")
    else:
        logger.warning("[SCANNER] No qualifying pairs found, keeping existing.")
        return Config.TRADING_PAIRS

    return [c["symbol"] for c in top]


def volatility_scan(client, top_n: int = None, min_volume: float = None) -> list[str]:
    """
    Deep real-time scan — fetches 5m candles for top candidates and scores on:
      - Short-term momentum (last 10 candles)
      - Volume spike
      - ATR %
      - Trend alignment
    Returns top_n symbols by composite volatility score.
    """
    top_n = top_n or Config.SCANNER_TOP_N
    min_volume = min_volume or Config.SCANNER_MIN_VOLUME

    # Step 1: Filter by 24h volume and change
    try:
        tickers = client.fetch_tickers()
    except Exception as e:
        logger.error(f"[VOLSCAN] Failed to fetch tickers: {e}")
        return Config.TRADING_PAIRS

    universe = []
    for symbol, t in tickers.items():
        if not symbol.endswith("/USDT:USDT"):
            continue
        info = t.get("info", {})
        try:
            close  = float(info.get("closeRp") or 0)
            open_  = float(info.get("openRp")  or 0)
            volume = float(info.get("turnoverRv") or 0)
            if close > 0 and open_ > 0 and volume >= min_volume:
                change_24h = (close - open_) / open_ * 100
                universe.append({"symbol": symbol, "price": close,
                                  "change_24h": change_24h, "volume": volume})
        except Exception:
            continue

    # Pre-filter: take top 30 by 24h change to limit API calls
    universe.sort(key=lambda x: abs(x["change_24h"]), reverse=True)
    universe = universe[:30]

    # Step 2: Score each on real-time 5m data
    scored = []
    for item in universe:
        symbol = item["symbol"]
        try:
            ohlcv = client.fetch_ohlcv(symbol, "5m", limit=50)
            if not ohlcv or len(ohlcv) < 20:
                continue

            closes  = [c[4] for c in ohlcv]
            volumes = [c[5] for c in ohlcv]
            highs   = [c[2] for c in ohlcv]
            lows    = [c[3] for c in ohlcv]

            # Short-term momentum: % move over last 10 candles
            momentum_10 = (closes[-1] - closes[-11]) / closes[-11] * 100

            # Volume spike: last candle vs 20-candle avg
            vol_avg = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1
            vol_spike = volumes[-1] / vol_avg if vol_avg > 0 else 0

            # ATR % (volatility relative to price)
            trs = []
            for i in range(1, len(closes)):
                tr = max(highs[i] - lows[i],
                         abs(highs[i] - closes[i-1]),
                         abs(lows[i]  - closes[i-1]))
                trs.append(tr)
            atr = sum(trs[-14:]) / 14 if len(trs) >= 14 else 0
            atr_pct = (atr / closes[-1]) * 100 if closes[-1] > 0 else 0

            # Trend alignment: EMA 9 > EMA 21
            def ema(data, period):
                k = 2 / (period + 1)
                e = data[0]
                for v in data[1:]:
                    e = v * k + e * (1 - k)
                return e

            ema9  = ema(closes, 9)
            ema21 = ema(closes, 21)
            trend_score = 1.0 if ema9 > ema21 else 0.0

            # Composite score (weighted)
            score = (
                abs(momentum_10) * 2.0 +   # short-term move
                vol_spike        * 1.5 +   # volume spike
                atr_pct          * 1.5 +   # volatility
                abs(item["change_24h"]) * 0.5 +  # 24h context
                trend_score      * 1.0     # trend aligned
            )

            scored.append({
                "symbol":      symbol,
                "score":       score,
                "momentum_10": momentum_10,
                "vol_spike":   vol_spike,
                "atr_pct":     atr_pct,
                "change_24h":  item["change_24h"],
                "price":       closes[-1],
                "trend":       "↑" if ema9 > ema21 else "↓",
            })
            time.sleep(0.15)  # rate limit friendly
        except Exception:
            continue

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]

    if top:
        logger.info(f"[VOLSCAN] Top {len(top)} opportunities:")
        for c in top:
            logger.info(
                f"  {c['symbol']:<25} score={c['score']:.1f} | "
                f"10c={c['momentum_10']:>+5.2f}% | vol={c['vol_spike']:.1f}x | "
                f"atr={c['atr_pct']:.2f}% | 24h={c['change_24h']:>+5.1f}% {c['trend']}"
            )
    else:
        logger.warning("[VOLSCAN] No results, keeping current pairs.")
        return Config.TRADING_PAIRS

    return [c["symbol"] for c in top]
