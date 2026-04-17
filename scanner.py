"""
Phmex2 Volume Scanner
Continuously scans Phemex USDT perpetuals for the highest-volume pairs.
Ranks by 24h turnover, applies spread filter, returns top N.
"""
import json
import math
import time
import threading
import ccxt
from config import Config
from logger import setup_logger

logger = setup_logger()


def _compute_history_scores(state_path: str = "trading_state.json",
                             min_trades: int = None) -> dict[str, float]:
    """
    Load trading_state.json and compute a history score per symbol.
    Returns {symbol: score} only for symbols with >= min_trades closed live trades.
    Score = sigmoid(avg_net_pnl_per_trade * 10), maps to [0,1] with 0.5 at breakeven.
    Symbols with < min_trades are absent — caller uses 0.5 (neutral) as default.
    """
    if min_trades is None:
        min_trades = Config.SCANNER_MIN_HISTORY_TRADES
    try:
        with open(state_path) as f:
            state = json.load(f)
    except Exception as e:
        logger.warning(f"[SCANNER] Could not load {state_path} for history scores: {e}")
        return {}

    # Accumulate per-symbol net PnL from closed live trades only
    symbol_pnl: dict[str, list[float]] = {}
    for t in state.get("closed_trades", []):
        if t.get("is_paper"):
            continue
        sym = t.get("symbol")
        if not sym:
            continue
        net = (t.get("pnl_usdt") or 0.0) - (t.get("fee_usdt") or 0.0)
        symbol_pnl.setdefault(sym, []).append(net)

    scores: dict[str, float] = {}
    for sym, pnl_list in symbol_pnl.items():
        if len(pnl_list) < min_trades:
            continue
        avg = sum(pnl_list) / len(pnl_list)
        scores[sym] = 1.0 / (1.0 + math.exp(-10.0 * avg))

    return scores


# Background scanner state
_scan_lock = threading.Lock()
_scan_result: list[str] | None = None
_scan_running = False
_scanner_client = None  # dedicated ccxt client for background thread


def _get_scanner_client():
    """Create a dedicated ccxt client for the scanner thread (ccxt is NOT thread-safe)."""
    global _scanner_client
    if _scanner_client is None:
        exchange_class = getattr(ccxt, Config.EXCHANGE)
        params = {"enableRateLimit": True, "timeout": 10000, "options": {"defaultType": "swap"}}
        if Config.is_live():
            params["apiKey"] = Config.API_KEY
            params["secret"] = Config.API_SECRET
        _scanner_client = exchange_class(params)
        try:
            _scanner_client.load_markets()
            logger.info("[SCANNER BG] Dedicated scanner client initialized")
        except Exception as e:
            logger.warning(f"[SCANNER BG] Could not load markets for scanner client: {e}")
    return _scanner_client


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

    # Remove blacklisted pairs
    candidates = [c for c in candidates if c["symbol"] not in Config.SCANNER_BLACKLIST]
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
    Volume-based scan — ranks all USDT perpetuals by 24h volume.
    Applies spread filter to reject illiquid pairs.
    Returns top_n symbols by highest 24h volume.
    """
    top_n = top_n or Config.SCANNER_TOP_N
    min_volume = min_volume or Config.SCANNER_MIN_VOLUME

    # Step 1: Filter by 24h volume and change
    try:
        tickers = client.fetch_tickers()
    except Exception as e:
        logger.error(f"[SCALPSCAN] Failed to fetch tickers: {e}")
        return None  # signal failure so caller keeps current pairs

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

    # Pre-filter: remove blacklisted pairs (keep both up and down movers for long/short)
    universe = [x for x in universe if x["symbol"] not in Config.SCANNER_BLACKLIST]

    # Rank by 24h volume — highest volume = most liquid, most volatile
    universe.sort(key=lambda x: x["volume"], reverse=True)
    # Take extra candidates for spread filtering
    candidates = universe[:top_n * 2]

    # Spread filter: reject illiquid pairs with wide bid-ask spread
    filtered = []
    for item in candidates:
        symbol = item["symbol"]
        try:
            ob = client.fetch_order_book(symbol, limit=5)
            if ob and ob.get("bids") and ob.get("asks"):
                best_bid = ob["bids"][0][0]
                best_ask = ob["asks"][0][0]
                spread_pct = (best_ask - best_bid) / best_bid * 100
                if spread_pct > 0.15:
                    logger.debug(f"[SCANNER] {symbol} spread too wide ({spread_pct:.3f}%), skipping")
                    continue
            filtered.append(item)
            time.sleep(1)  # rate limit friendly
        except Exception:
            filtered.append(item)  # if OB fetch fails, keep the pair
        if len(filtered) >= top_n:
            break

    top = filtered[:top_n]

    if top:
        logger.info(f"[SCALPSCAN] Top {len(top)} by volume:")
        for c in top:
            logger.info(
                f"  {c['symbol']:<25} vol=${c['volume']:,.0f} | "
                f"24h={c['change_24h']:>+5.1f}%"
            )
    else:
        logger.warning("[SCALPSCAN] No results, keeping current pairs.")
        return None  # signal failure so caller keeps current pairs

    return [c["symbol"] for c in top]


def start_background_scan(client=None, top_n: int = None, min_volume: float = None):
    """Launch volatility_scan in a background thread with its own ccxt client (thread-safe)."""
    global _scan_running
    with _scan_lock:
        if _scan_running:
            return  # already scanning
        _scan_running = True

    def _run():
        global _scan_result, _scan_running
        try:
            scanner_client = _get_scanner_client()
            result = volatility_scan(scanner_client, top_n, min_volume)
            with _scan_lock:
                _scan_result = result
        except Exception as e:
            logger.error(f"[SCANNER BG] Background scan failed: {e}")
        finally:
            with _scan_lock:
                _scan_running = False

    t = threading.Thread(target=_run, daemon=True, name="scanner-bg")
    t.start()
    logger.info("[SCANNER BG] Background scan started")


def get_scan_result() -> list[str] | None:
    """Retrieve the latest background scan result (or None if not ready)."""
    global _scan_result
    with _scan_lock:
        result = _scan_result
        _scan_result = None  # consume it
        return result


def is_scan_running() -> bool:
    with _scan_lock:
        return _scan_running
