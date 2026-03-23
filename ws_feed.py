"""
WebSocket data feed for Phemex — streams OHLCV candles via ccxt.pro.
Replaces REST polling of /md/ CDN endpoints to avoid IP bans.
"""
import asyncio
import collections
import threading
import time as _time
import pandas as pd
import ccxt.pro as ccxtpro
from logger import setup_logger
from config import Config

logger = setup_logger()


class WSDataFeed:
    """Streams OHLCV candles from Phemex WebSocket in a background thread.

    Usage:
        feed = WSDataFeed(['OPN/USDT:USDT', 'MLN/USDT:USDT'], '5m')
        feed.start()          # blocks up to 30s waiting for first data
        df = feed.get_ohlcv('OPN/USDT:USDT', limit=100)
        feed.stop()
    """

    def __init__(self, symbols: list, timeframe: str):
        self.symbols = symbols
        self.timeframe = timeframe
        self._cache: dict = {}           # symbol -> list of [ts_ms, o, h, l, c, v]
        self._last_update: dict = {}     # symbol -> time.time() of last WS update
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._exchange = None
        self._running = False
        self._ready = threading.Event()  # set when ALL symbols have initial data
        self._trade_buffer: dict[str, list] = {}
        self._order_flow: dict[str, dict] = {}
        self._current_candle_start: dict[str, int] = {}
        self._candle_deltas: dict[str, collections.deque] = {}
        self._cvd_total: dict[str, float] = {}

    # ── Public interface ──────────────────────────────────────────────────────

    def start(self):
        """Start the background WS thread. Blocks up to 30s for initial data."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="WSFeed")
        self._thread.start()
        if self._ready.wait(timeout=30):
            logger.info(f"[WS] Feed ready — streaming {len(self.symbols)} pair(s) ({self.timeframe})")
        else:
            logger.warning("[WS] Feed not ready after 30s — will retry in background")

    def seed(self, rest_client, limit: int = 200):
        """Prime the OHLCV cache with REST history via paginated REST calls.
        Phemex caps at 100 candles per call, so we paginate backwards to get
        up to `limit` candles (default 200)."""
        # Map timeframe string to milliseconds for pagination offset
        tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
                 "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
        candle_ms = tf_ms.get(self.timeframe, 60_000)

        seeded = 0
        for symbol in self.symbols:
            all_candles = []
            pages = (limit // 100) + 1
            for page in range(pages):
                try:
                    if page == 0:
                        batch = rest_client.fetch_ohlcv(symbol, self.timeframe, limit=100)
                    else:
                        # Go back from the earliest candle we have
                        earliest_ts = all_candles[0][0]
                        since = earliest_ts - (100 * candle_ms)
                        batch = rest_client.fetch_ohlcv(symbol, self.timeframe, since=since, limit=100)
                    if not batch:
                        break
                    all_candles = batch + all_candles if page > 0 else batch
                    if len(batch) < 100:
                        break
                    _time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"[WS] Seed {symbol} page {page+1} failed: {str(e)[:80]}")
                    break
            # Deduplicate by timestamp and sort
            if all_candles:
                by_ts = {c[0]: c for c in all_candles}
                all_candles = sorted(by_ts.values(), key=lambda x: x[0])
            if all_candles and len(all_candles) >= 2:
                with self._lock:
                    self._cache[symbol] = all_candles[-300:]
                    if all(s in self._cache for s in self.symbols):
                        self._ready.set()
                logger.info(f"[WS] Seeded {symbol} with {len(all_candles)} candles ({pages} REST pages)")
                seeded += 1
            else:
                logger.warning(f"[WS] Could not seed {symbol} — WebSocket will populate in time")
        return seeded

    def subscribe(self, symbols: list):
        """Add new symbols to the WS feed (called when scanner updates pairs)."""
        new = [s for s in symbols if s not in self.symbols]
        if not new:
            return
        self.symbols = self.symbols + new
        if self._loop and not self._loop.is_closed():
            for sym in new:
                asyncio.run_coroutine_threadsafe(self._watch_symbol(sym), self._loop)
                asyncio.run_coroutine_threadsafe(self._watch_trades(sym), self._loop)
            logger.info(f"[WS] Subscribed to {len(new)} new symbol(s): {new}")

    def stop(self):
        """Signal the feed to shut down."""
        self._running = False
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self._close_exchange(), self._loop)

    def get_ohlcv(self, symbol: str, limit: int = 100) -> pd.DataFrame | None:
        """Return cached OHLCV as a DataFrame (same format as exchange.get_ohlcv)."""
        with self._lock:
            data = self._cache.get(symbol)
            if not data or len(data) < 2:
                return None
            rows = [list(row) for row in data[-limit:]] if limit else [list(row) for row in data]
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    @property
    def is_connected(self) -> bool:
        """True only if running AND at least one symbol has fresh data (<120s old)."""
        if not self._running or not self._cache:
            return False
        with self._lock:
            now = _time.time()
            return any(now - self._last_update.get(s, 0) < 120 for s in self._cache)

    def is_stale(self, symbol: str, max_age_s: float = 120) -> bool:
        """Return True if the symbol's WS data is older than max_age_s seconds."""
        with self._lock:
            last = self._last_update.get(symbol)
        if last is None:
            return True
        return (_time.time() - last) > max_age_s

    def get_order_flow(self, symbol: str) -> dict | None:
        """Get current candle's order flow stats for a symbol."""
        with self._lock:
            flow = self._order_flow.get(symbol)
            return dict(flow) if flow else None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_loop(self):
        while self._running:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._watch_all())
            except Exception as e:
                logger.error(f"[WS] Event loop crashed: {e}")
                if self._running:
                    logger.info("[WS] Restarting event loop in 5s...")
                    _time.sleep(5)
            finally:
                try:
                    self._loop.close()
                except Exception:
                    pass

    async def _watch_all(self):
        params = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
        if Config.is_live():
            params["apiKey"] = Config.API_KEY
            params["secret"] = Config.API_SECRET

        self._exchange = ccxtpro.phemex(params)
        try:
            tasks = []
            for sym in self.symbols:
                tasks.append(self._watch_symbol(sym))
                tasks.append(self._watch_trades(sym))
            await asyncio.gather(*tasks)
        finally:
            await self._close_exchange()

    async def _watch_symbol(self, symbol: str):
        backoff = 2
        while self._running:
            try:
                # watch_ohlcv returns the full candle list each time a candle updates
                ohlcv = await self._exchange.watch_ohlcv(symbol, self.timeframe)
                with self._lock:
                    new_candles = list(ohlcv)
                    existing = self._cache.get(symbol, [])
                    if existing and new_candles:
                        # Merge: preserve seeded history, update/append WS candles by timestamp
                        existing_dict = {row[0]: row for row in existing}
                        for row in new_candles:
                            existing_dict[row[0]] = row
                        merged = sorted(existing_dict.values(), key=lambda x: x[0])
                        self._cache[symbol] = merged[-300:]
                    else:
                        self._cache[symbol] = new_candles[-300:]
                    self._last_update[symbol] = _time.time()
                    if all(s in self._cache for s in self.symbols):
                        self._ready.set()
                backoff = 2  # reset on success
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning(f"[WS] {symbol} error, retrying in {backoff}s: {str(e)[:120]}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def _archive_candle(self, symbol: str):
        """Archive current candle's delta to CVD running total, reset for new candle.
        Must hold self._lock or be called from within a locked context."""
        with self._lock:
            flow = self._order_flow.get(symbol, {})
            delta = flow.get("delta", 0)
            self._cvd_total[symbol] = self._cvd_total.get(symbol, 0) + delta
            self._candle_deltas.setdefault(
                symbol, collections.deque(maxlen=10)
            ).append(delta)
            self._order_flow[symbol] = {
                "buy_volume": 0, "sell_volume": 0, "buy_ratio": 0.5,
                "delta": 0, "cvd": self._cvd_total[symbol],
                "cvd_slope": 0, "divergence": None,
                "large_trade_count": 0, "large_trade_bias": 0.5,
                "trade_count": 0, "updated_at": 0,
            }
            self._trade_buffer[symbol] = []

    async def _watch_trades(self, symbol: str):
        """Stream individual trades, aggregate into per-candle order flow stats."""
        backoff = 2
        while self._running:
            try:
                trades = await self._exchange.watch_trades(symbol)
                batch_buy = 0.0
                batch_sell = 0.0
                batch_count = 0

                for trade in trades:
                    cost = trade.get("cost", 0) or (
                        trade.get("amount", 0) * trade.get("price", 0))
                    ts = trade.get("timestamp", 0)

                    candle_start = (ts // 300_000) * 300_000
                    current = self._current_candle_start.get(symbol, 0)
                    if candle_start != current and current != 0:
                        self._archive_candle(symbol)
                    self._current_candle_start[symbol] = candle_start

                    if trade.get("side") == "buy":
                        batch_buy += cost
                    else:
                        batch_sell += cost
                    batch_count += 1

                with self._lock:
                    flow = self._order_flow.setdefault(symbol, {
                        "buy_volume": 0, "sell_volume": 0, "buy_ratio": 0.5,
                        "delta": 0, "cvd": 0, "cvd_slope": 0, "divergence": None,
                        "large_trade_count": 0, "large_trade_bias": 0.5,
                        "trade_count": 0, "updated_at": 0,
                    })
                    flow["buy_volume"] += batch_buy
                    flow["sell_volume"] += batch_sell
                    flow["trade_count"] += batch_count
                    total = flow["buy_volume"] + flow["sell_volume"]
                    flow["buy_ratio"] = flow["buy_volume"] / total if total > 0 else 0.5
                    flow["delta"] = flow["buy_volume"] - flow["sell_volume"]
                    flow["cvd"] = self._cvd_total.get(symbol, 0) + flow["delta"]
                    flow["updated_at"] = _time.time()

                    deltas = self._candle_deltas.get(symbol, collections.deque(maxlen=10))
                    if len(deltas) >= 2:
                        half = len(deltas) // 2
                        d_list = list(deltas)
                        flow["cvd_slope"] = sum(d_list[half:]) - sum(d_list[:half])
                    else:
                        flow["cvd_slope"] = flow["delta"]

                    candles = self._cache.get(symbol, [])
                    if len(candles) >= 2:
                        price_dir = candles[-1][4] - candles[-2][4]
                        cvd_dir = flow["cvd_slope"]
                        if price_dir < 0 and cvd_dir > 0:
                            flow["divergence"] = "bullish"
                        elif price_dir > 0 and cvd_dir < 0:
                            flow["divergence"] = "bearish"
                        else:
                            flow["divergence"] = None
                    else:
                        flow["divergence"] = None

                backoff = 2
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self._running:
                    break
                logger.warning(f"[WS] Trade stream error for {symbol}: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _close_exchange(self):
        if self._exchange:
            try:
                await self._exchange.close()
            except Exception:
                pass
            self._exchange = None
