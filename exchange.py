import ccxt
import time
import pandas as pd
from typing import Optional
import concurrent.futures
from config import Config
from logger import setup_logger

logger = setup_logger()


class Exchange:
    def __init__(self):
        exchange_class = getattr(ccxt, Config.EXCHANGE)
        params = {"enableRateLimit": True, "timeout": 10000, "options": {"defaultType": "swap"}}

        if Config.is_live():
            params["apiKey"] = Config.API_KEY
            params["secret"] = Config.API_SECRET

        self.client = exchange_class(params)

        self.paper_balances: dict = {}
        self.paper_orders: list = []
        self._reduce_only_aborts: dict = {}  # symbol -> ts of last 11011/TE_REDUCE_ONLY_ABORT close failure
        self._last_balance: dict = {}   # value cache for failed fetches
        self._balance_fetch_ts: float = 0  # timestamp of last successful fetch
        self._BALANCE_TTL: float = 30.0    # only hit the API every 30 seconds

        if not Config.is_live():
            logger.info("Paper trading mode: using simulated balances")
            self.paper_balances = {Config.BASE_CURRENCY: 10000.0}
        else:
            # Load markets once so ccxt caches symbol mappings — prevents auto
            # load_markets() calls on every fetch_ticker() which would hammer the CDN.
            for attempt in range(3):
                try:
                    self.client.load_markets()
                    logger.info(f"Markets loaded ({len(self.client.markets)} symbols)")
                    break
                except Exception as e:
                    if attempt < 2:
                        logger.warning(f"Could not load markets (attempt {attempt+1}/3), retrying in 10s: {e}")
                        time.sleep(10)
                    else:
                        logger.warning(f"Could not load markets after 3 attempts — CDN may be blocked: {e}")

    def _call_with_timeout(self, fn, *args, timeout=15, **kwargs):
        """Run fn in a thread with hard timeout. Returns None on timeout."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                logger.warning(f"[TIMEOUT] {fn.__name__} timed out after {timeout}s — likely DNS hang")
                return None

    def get_balance(self, currency: str) -> float:
        if not Config.is_live():
            return self.paper_balances.get(currency, 0.0)
        try:
            balance = self._call_with_timeout(self.client.fetch_balance)
            if balance is None:
                return self._last_balance.get(currency, 0.0)
            free  = float(balance["free"].get(currency, 0.0))
            total = float(balance["total"].get(currency, 0.0))
            self._last_balance[currency] = free
            self._last_balance[f"equity_{currency}"] = total  # cache equity in the same call
            return free
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return self._last_balance.get(currency, 0.0)

    def get_equity(self, currency: str) -> float:
        """Total equity (free + margin in use). Reads from cache set by get_balance()."""
        if not Config.is_live():
            return self.paper_balances.get(currency, 0.0)
        return self._last_balance.get(f"equity_{currency}", 0.0)

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> Optional[pd.DataFrame]:
        try:
            ohlcv = self._call_with_timeout(self.client.fetch_ohlcv, symbol, timeframe, limit=limit)
            if ohlcv is None:
                return None
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return None

    def get_order_book(self, symbol: str, depth: int = 20) -> Optional[dict]:
        try:
            ob = self._call_with_timeout(self.client.fetch_order_book, symbol, limit=depth)
            if ob is None:
                return None
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if not bids or not asks:
                return None
            bid_vol = sum(b[1] for b in bids)
            ask_vol = sum(a[1] for a in asks)
            total   = bid_vol + ask_vol
            imbalance = (bid_vol - ask_vol) / total if total > 0 else 0

            # Detect walls: any single level > 15% of total side volume
            avg_bid = bid_vol / len(bids) if bids else 0
            avg_ask = ask_vol / len(asks) if asks else 0
            bid_walls = [b for b in bids if b[1] > avg_bid * 5]
            ask_walls = [a for a in asks if a[1] > avg_ask * 5]

            best_bid = bids[0][0] if bids else 0
            best_ask = asks[0][0] if asks else 0

            mid = (best_ask + best_bid) / 2 if (best_ask and best_bid) else 0
            spread_pct = ((best_ask - best_bid) / mid * 100) if mid else 0
            bid_depth_usdt = sum(b[0] * b[1] for b in bids)
            ask_depth_usdt = sum(a[0] * a[1] for a in asks)
            result = {
                "imbalance":  imbalance,
                "bid_vol":    bid_vol,
                "ask_vol":    ask_vol,
                "best_bid":   best_bid,
                "best_ask":   best_ask,
                "spread_pct": spread_pct,
                "bid_walls":  bid_walls,
                "ask_walls":  ask_walls,
                "bid_depth_usdt": bid_depth_usdt,
                "ask_depth_usdt": ask_depth_usdt,
            }
            if spread_pct > 0.3:
                result["illiquid"] = True
            return result
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return None

    def get_recent_trades(self, symbol: str, limit: int = 100) -> Optional[dict]:
        """Fetch recent trades (tape) and compute aggressor stats."""
        try:
            trades = self._call_with_timeout(self.client.fetch_trades, symbol, limit=limit)
            if trades is None:
                return None
            if not trades or len(trades) < 10:
                return None

            total_buy_vol = 0.0
            total_sell_vol = 0.0
            large_buy_vol = 0.0
            large_sell_vol = 0.0

            sizes = [t.get("amount", 0) * t.get("price", 0) for t in trades]
            avg_size = sum(sizes) / len(sizes) if sizes else 0
            large_threshold = avg_size * 3.0

            for t in trades:
                usd_size = t.get("amount", 0) * t.get("price", 0)
                side = t.get("side", "")
                if side == "buy":
                    total_buy_vol += usd_size
                    if usd_size > large_threshold:
                        large_buy_vol += usd_size
                else:
                    total_sell_vol += usd_size
                    if usd_size > large_threshold:
                        large_sell_vol += usd_size

            total_vol = total_buy_vol + total_sell_vol
            aggressor_ratio = total_buy_vol / total_vol if total_vol > 0 else 0.5
            net_delta = total_buy_vol - total_sell_vol

            # Large trade bias: +1 = large buys dominate, -1 = large sells dominate
            large_total = large_buy_vol + large_sell_vol
            large_trade_bias = (large_buy_vol - large_sell_vol) / large_total if large_total > 0 else 0.0

            # Velocity: trades per second (recent half vs older half)
            mid = len(trades) // 2
            if len(trades) >= 4:
                recent_trades = trades[mid:]
                older_trades = trades[:mid]
                recent_span = max(1, (recent_trades[-1]["timestamp"] - recent_trades[0]["timestamp"]) / 1000)
                older_span = max(1, (older_trades[-1]["timestamp"] - older_trades[0]["timestamp"]) / 1000)
                recent_rate = len(recent_trades) / recent_span
                older_rate = len(older_trades) / older_span
                velocity = recent_rate / older_rate if older_rate > 0 else 1.0
            else:
                velocity = 1.0

            return {
                "aggressor_ratio": aggressor_ratio,
                "net_delta": net_delta,
                "large_trade_bias": large_trade_bias,
                "velocity": velocity,
                "total_volume": total_vol,
                "trade_count": len(trades),
            }
        except Exception as e:
            logger.error(f"Failed to fetch recent trades for {symbol}: {e}")
            return None

    def get_cvd(self, symbol: str, limit: int = 200) -> Optional[dict]:
        """Compute Cumulative Volume Delta from recent trades.
        CVD divergence (price making new low but CVD rising) = high-conviction reversal signal."""
        try:
            trades = self._call_with_timeout(self.client.fetch_trades, symbol, limit=limit)
            if trades is None:
                return None
            if not trades or len(trades) < 20:
                return None

            cvd = 0.0
            cvd_values = []
            for t in trades:
                usd_size = t.get("amount", 0) * t.get("price", 0)
                if t.get("side") == "buy":
                    cvd += usd_size
                else:
                    cvd -= usd_size
                cvd_values.append(cvd)

            # CVD slope: compare first half vs second half
            mid = len(cvd_values) // 2
            first_half_avg = sum(cvd_values[:mid]) / mid if mid > 0 else 0
            second_half_avg = sum(cvd_values[mid:]) / (len(cvd_values) - mid) if len(cvd_values) > mid else 0
            total_volume = sum(
                abs(t.get("amount", 0) * t.get("price", 0)) for t in trades
            )
            cvd_slope = (second_half_avg - first_half_avg) / total_volume if total_volume > 0 else 0.0

            # Detect divergence: compare price direction vs CVD direction
            # Use first and last trade prices
            first_price = trades[0].get("price", 0)
            last_price = trades[-1].get("price", 0)
            price_direction = last_price - first_price  # positive = price rising

            divergence = None
            if price_direction < 0 and cvd_slope > 0:
                divergence = "bullish"  # price falling but buying pressure increasing
            elif price_direction > 0 and cvd_slope < 0:
                divergence = "bearish"  # price rising but selling pressure increasing

            return {
                "cvd": cvd,
                "cvd_slope": cvd_slope,
                "divergence": divergence,
            }
        except Exception as e:
            logger.error(f"Failed to compute CVD for {symbol}: {e}")
            return None

    def get_funding_rate(self, symbol: str) -> Optional[dict]:
        """Fetch current funding rate. Extreme rates signal contrarian opportunities."""
        try:
            funding = self._call_with_timeout(self.client.fetch_funding_rate, symbol)
            if funding is None:
                return None
            rate = float(funding.get("fundingRate", 0) or 0)
            return {
                "rate": rate,
                "signal": "short" if rate > 0.0005 else ("long" if rate < -0.0005 else None),
                "strength_mod": max(-0.03, min(0.03, -rate * 60)),  # scale rate to +/- 0.03
            }
        except Exception as e:
            logger.debug(f"Failed to fetch funding rate for {symbol}: {e}")
            return None

    def get_ticker(self, symbol: str) -> Optional[dict]:
        try:
            result = self._call_with_timeout(self.client.fetch_ticker, symbol)
            if result is None:
                return None
            return result
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return None

    def _coin_amount(self, symbol: str, margin_usdt: float, price: float) -> float:
        """Convert USDT margin to leveraged coin quantity."""
        return (margin_usdt * Config.LEVERAGE) / price

    # ── Long ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_rate_limit_error(e: Exception) -> bool:
        err = str(e).lower()
        return "429" in err or "rate" in err or "ratelimit" in err

    @staticmethod
    def _is_cloudfront_block(e: Exception) -> bool:
        err = str(e)
        return "403" in err or "cloudfront" in err.lower() or "request blocked" in err.lower()

    def _api_call_with_backoff(self, fn, *args, **kwargs):
        delays = [2, 4, 8, 16, 32]
        for attempt, delay in enumerate(delays):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if self._is_cloudfront_block(e) or self._is_rate_limit_error(e):
                    if attempt < len(delays) - 1:
                        logger.warning(f"API blocked (attempt {attempt+1}/{len(delays)}), retrying in {delay}s")
                        time.sleep(delay)
                    else:
                        logger.error(f"API blocked after {len(delays)} attempts: {e}")
                        raise
                else:
                    raise

    def _position_ground_truth(self, symbol: str, side: str, pre_amount: float = 0.0) -> Optional[dict]:
        """Final safety net: query exchange for any position on this symbol/side.

        Returns a synthetic order-like dict if a position exists on-exchange whose amount is
        GREATER than the pre-call snapshot. This delta check is critical — without it, we'd
        mis-adopt a user's pre-existing manual position as "our fill" and register it with
        wrong sizing. The callers MUST snapshot `pre_amount` BEFORE submitting any order,
        otherwise set pre_amount=0 and accept the risk of matching a pre-existing position.

        The returned `filled` and `amount` fields report only the DELTA (what our order added),
        so downstream sizing/margin calc reflects the actual order, not the full exchange position.
        """
        EPSILON = 1e-9
        try:
            positions = self.get_open_positions()
            if not positions:
                return None
            for p in positions:
                if p.get("symbol") != symbol:
                    continue
                if p.get("side") != side:
                    continue
                amount = float(p.get("amount") or 0)
                entry = float(p.get("entry_price") or 0)
                if amount <= 0 or entry <= 0:
                    continue
                # Only trust as "our fill" if the position grew beyond the pre-snapshot.
                if amount <= pre_amount + EPSILON:
                    logger.info(
                        f"[GROUND TRUTH] {symbol} {side.upper()} position exists (amount={amount}) "
                        f"but no growth vs pre-snapshot ({pre_amount}) — not attributing to our order"
                    )
                    continue
                delta = amount - pre_amount
                logger.warning(
                    f"[GROUND TRUTH] {symbol} {side.upper()} delta fill detected "
                    f"(pre={pre_amount}, now={amount}, delta={delta}, entry={entry}) "
                    f"— recovering from lost order tracking"
                )
                return {
                    "symbol": symbol,
                    "average": entry,
                    "price": entry,
                    "filled": delta,
                    "amount": delta,
                    "status": "closed",
                    "source": "ground_truth",
                    "exchange_total_amount": amount,
                }
        except Exception as e:
            logger.error(f"[GROUND TRUTH] fetch_positions failed for {symbol}: {e}")
        return None

    def _try_limit_entry(self, symbol: str, side: str, amount: float, limit_price: float,
                         patience_s: float = 20.0) -> Optional[dict]:
        """Place limit-only entry order. No market fallback — if unfilled, skip the trade.
        Maker fee = 0.01% vs taker 0.06%. Missing a fill is better than overpaying 6x fees.

        patience_s: how long the order rests before cancel (default 20s = the
        2026-04-13 calibration). Slots may extend it (5m_mean_revert 45s,
        2026-07-03 — mean-reversion fills on the way back; 9/11 of its missed
        winners returned through the limit within 60s).

        Every early-return path that says "no fill" MUST end by confirming with the exchange
        that no position materialized. Any races here create unmanaged orphan positions
        (real-money incident 2026-04-13)."""
        limit_price = self._round_price(symbol, limit_price)
        order_side = "buy" if side == "long" else "sell"

        # Pre-call snapshot — _position_ground_truth uses this to verify that any newly-found
        # position actually grew beyond what existed before. Prevents mis-adopting the user's
        # pre-existing manual position or a stale prior-instance position as "our fill".
        pre_amount = 0.0
        try:
            _pre = self.get_open_positions() or []
            for _p in _pre:
                if _p.get("symbol") == symbol and _p.get("side") == side:
                    pre_amount = float(_p.get("amount") or 0)
                    break
        except Exception as e:
            logger.warning(f"[PRE-SNAPSHOT] {symbol} {side} failed: {e} — ground-truth delta check may be unreliable")
        # Expose for the bot.py Layer-2 safety net after open_long/open_short returns None
        self._last_entry_pre_amount = {"symbol": symbol, "side": side, "pre_amount": pre_amount, "ts": time.time()}

        order_id = None
        try:
            order = self.client.create_order(symbol, "limit", order_side, amount, limit_price, params={"timeInForce": "PostOnly"})
            order_id = order.get("id")
            logger.info(f"[MAKER] Limit {order_side} {amount} {symbol} @ {limit_price} (id={order_id})")

            # Wait up to patience_s for fill (0.5s polls; default 20s).
            # Was 5s pre-2026-04-13 — produced 1.5% fill rate on Phemex; book moved
            # away from PostOnly price faster than 5s. Widened after forensic showed
            # 66 signals → 1 fill in 7 days. The ground-truth safety net below catches
            # any late-fill race beyond the cancel.
            for _ in range(int(patience_s / 0.5)):
                time.sleep(0.5)
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    status = fetched.get("status", "")
                    if status == "closed":
                        logger.info(f"[FILL] {symbol} {order_side} — MAKER @ {fetched.get('average', limit_price)}")
                        return fetched
                    if status in ("canceled", "cancelled"):
                        # PostOnly rejected — but check if it filled before cancel
                        _filled = float(fetched.get("filled", 0) or 0)
                        if _filled > 0:
                            logger.info(f"[FILL] {symbol} {order_side} — MAKER @ {fetched.get('average', limit_price)} (filled before cancel)")
                            return fetched
                        # Confirm with exchange that no position materialized before giving up
                        gt = self._position_ground_truth(symbol, side, pre_amount=pre_amount)
                        if gt:
                            return gt
                        logger.info(f"[FILL MISS] {symbol} — PostOnly rejected, skipping entry")
                        return None
                except Exception as e:
                    logger.debug(f"[POLL] fetch_order failed for {symbol} id={order_id}: {e}")

            # Not filled within patience_s — cancel and skip (no market fallback)
            try:
                self.client.cancel_order(order_id, symbol)
                # Check for race: filled between our last poll and cancel
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    if fetched.get("status") == "closed":
                        logger.info(f"[FILL] {symbol} {order_side} — MAKER @ {fetched.get('average', limit_price)} (raced cancel)")
                        return fetched
                    filled_amount = float(fetched.get("filled", 0) or 0)
                    if filled_amount > 0:
                        # Partial fill — keep it, don't chase remainder with market
                        logger.info(f"[FILL] {symbol} {order_side} — MAKER partial {filled_amount}/{amount}")
                        return fetched
                except Exception as e:
                    logger.warning(f"[POST-CANCEL] fetch_order failed for {symbol} id={order_id}: {e} — falling through to ground-truth check")
            except Exception as e:
                # Cancel failed — check if filled via fetch_order, then ground truth
                logger.warning(f"[CANCEL FAIL] {symbol} id={order_id}: {e}")
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    if fetched.get("status") == "closed":
                        return fetched
                    _filled_cf = float(fetched.get("filled", 0) or 0)
                    if _filled_cf > 0:
                        logger.info(f"[FILL] {symbol} {order_side} — MAKER partial {_filled_cf}/{amount} (cancel failed)")
                        return fetched
                except Exception as e2:
                    logger.warning(f"[CANCEL FAIL] fetch_order also failed for {symbol} id={order_id}: {e2} — falling through to ground-truth check")

            # Final safety net: before declaring "no fill", confirm with the exchange that
            # no position exists. Any exception path above may have lost track of a real fill.
            gt = self._position_ground_truth(symbol, side, pre_amount=pre_amount)
            if gt:
                return gt

            logger.info(f"[FILL MISS] {symbol} {order_side} — limit not filled in {patience_s:.0f}s, skipping entry")
            return None

        except Exception as e:
            logger.warning(f"[FILL MISS] {symbol} — limit order failed: {e}, skipping entry")
            # Even an exception on create_order can leave a live order if it timed out
            # after the exchange received it. Check ground truth.
            gt = self._position_ground_truth(symbol, side, pre_amount=pre_amount)
            if gt:
                return gt
            return None

    def open_long(self, symbol: str, margin_usdt: float, price: float = None,
                  patience_s: float = 20.0) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_open(symbol, margin_usdt, side="long")
        if price is None:
            ticker = self.get_ticker(symbol)
            price = ticker["last"] if ticker else None
        if not price:
            logger.error(f"Cannot open long for {symbol}: no valid price")
            return None
        amount = self._round_amount(symbol, self._coin_amount(symbol, margin_usdt, price))
        if amount <= 0:
            logger.error(f"Amount rounded to 0 for {symbol}, skipping open_long")
            return None
        # Use best bid for maker entry (buy at bid = maker)
        ob = self.get_order_book(symbol, depth=5)
        limit_price = ob["best_bid"] if ob and ob.get("best_bid") else price
        return self._try_limit_entry(symbol, "long", amount, limit_price,
                                     patience_s=patience_s)

    def close_long(self, symbol: str, coin_amount: float, urgent: bool = True) -> Optional[dict]:
        """urgent=True (default): straight to market reduceOnly — protective exits
        (SL/trail/watcher/emergency) must not burn seconds on a limit that has
        never filled. urgent=False: patient maker attempt first (sell at ask),
        then market fallback."""
        if not Config.is_live():
            return self._paper_close(symbol, coin_amount, side="long")
        coin_amount = self._round_amount(symbol, coin_amount)
        if coin_amount <= 0:
            logger.error(f"Amount rounded to 0 for close_long {symbol}")
            return None
        if not urgent:
            # Sell at best ask for maker exit
            ob = self.get_order_book(symbol, depth=5)
            limit_price = ob["best_ask"] if ob and ob.get("best_ask") else None
            if limit_price:
                result = self._try_limit_exit(symbol, "sell", coin_amount, limit_price,
                                              patience_s=self.PATIENT_EXIT_PATIENCE_S)
                if result:
                    return result
        # Fallback to market
        try:
            order = self.client.create_market_sell_order(symbol, coin_amount, params={"reduceOnly": True})
            logger.info(f"[TAKER] CLOSE LONG {coin_amount} {symbol}")
            return order
        except Exception as e:
            if self._note_reduce_only_abort(symbol, e):
                logger.info(f"[TAKER] close_long {symbol} reduceOnly abort — position is being closed elsewhere")
            else:
                logger.error(f"Failed to close long for {symbol}: {e}")
            return None

    # ── Short ────────────────────────────────────────────────────────────────

    def open_short(self, symbol: str, margin_usdt: float, price: float = None,
                   patience_s: float = 20.0) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_open(symbol, margin_usdt, side="short")
        if price is None:
            ticker = self.get_ticker(symbol)
            price = ticker["last"] if ticker else None
        if not price:
            logger.error(f"Cannot open short for {symbol}: no valid price")
            return None
        amount = self._round_amount(symbol, self._coin_amount(symbol, margin_usdt, price))
        if amount <= 0:
            logger.error(f"Amount rounded to 0 for {symbol}, skipping open_short")
            return None
        # Use best ask for maker entry (sell at ask = maker)
        ob = self.get_order_book(symbol, depth=5)
        limit_price = ob["best_ask"] if ob and ob.get("best_ask") else price
        return self._try_limit_entry(symbol, "short", amount, limit_price,
                                     patience_s=patience_s)

    def close_short(self, symbol: str, coin_amount: float, urgent: bool = True) -> Optional[dict]:
        """See close_long — same urgency contract, mirrored sides."""
        if not Config.is_live():
            return self._paper_close(symbol, coin_amount, side="short")
        coin_amount = self._round_amount(symbol, coin_amount)
        if coin_amount <= 0:
            logger.error(f"Amount rounded to 0 for close_short {symbol}")
            return None
        if not urgent:
            # Buy at best bid for maker exit
            ob = self.get_order_book(symbol, depth=5)
            limit_price = ob["best_bid"] if ob and ob.get("best_bid") else None
            if limit_price:
                result = self._try_limit_exit(symbol, "buy", coin_amount, limit_price,
                                              patience_s=self.PATIENT_EXIT_PATIENCE_S)
                if result:
                    return result
        # Fallback to market
        try:
            order = self.client.create_market_buy_order(symbol, coin_amount, params={"reduceOnly": True})
            logger.info(f"[TAKER] CLOSE SHORT {coin_amount} {symbol}")
            return order
        except Exception as e:
            if self._note_reduce_only_abort(symbol, e):
                logger.info(f"[TAKER] close_short {symbol} reduceOnly abort — position is being closed elsewhere")
            else:
                logger.error(f"Failed to close short for {symbol}: {e}")
            return None

    # Hard ceiling on the opt-in maker-exit patience window. close_long/close_short
    # block the main loop while the limit rests; the 180s cycle watchdog (bot.py:453)
    # raises TimeoutError mid-cycle, which would abandon the resting order AND skip
    # the market fallback — an unmanaged position. Worst case MAX_OPEN_TRADES=3
    # simultaneous exits: 3 x 45s = 135s, leaving ~45s for the rest of the cycle.
    MAKER_EXIT_PATIENCE_MAX_S = 45.0

    # Patience for urgent=False exits (flat/time/TP — no protective deadline).
    # 25s keeps worst case MAX_OPEN_TRADES=3 patient exits at 75s, well inside
    # the 180s cycle-watchdog budget — do not raise without re-checking that math.
    PATIENT_EXIT_PATIENCE_S = 25.0

    _REDUCE_ONLY_ABORT_MARKERS = ("11011", "TE_REDUCE_ONLY_ABORT")

    def _note_reduce_only_abort(self, symbol: str, exc: Exception) -> bool:
        """Record a Phemex 11011/TE_REDUCE_ONLY_ABORT close failure: the reduceOnly
        order found no position to reduce — it is being closed elsewhere (resting
        TP/SL fill or a racing close), not an execution failure."""
        if any(m in str(exc) for m in self._REDUCE_ONLY_ABORT_MARKERS):
            self._reduce_only_aborts[symbol] = time.time()
            return True
        return False

    def pop_reduce_only_abort(self, symbol: str, within_s: float = 10.0) -> bool:
        """True if the last close attempt for symbol failed with a reduceOnly
        abort within the last `within_s` seconds. Consumes the flag."""
        ts = self._reduce_only_aborts.pop(symbol, None)
        return ts is not None and (time.time() - ts) <= within_s

    def _market_close_remainder(self, symbol: str, side: str, amount: float, filled_amount: float) -> None:
        """Market-close (reduceOnly) the unfilled remainder of a partial limit exit."""
        remaining = self._round_amount(symbol, amount - float(filled_amount))
        if remaining <= 0:
            return
        try:
            self.client.create_order(symbol, "market", side, remaining, None, params={"reduceOnly": True})
            logger.info(f"[MAKER EXIT] Partial {filled_amount}, market remainder {remaining} {symbol}")
        except Exception as me:
            logger.error(f"[MAKER EXIT] Remainder market failed {symbol}: {me}")

    def _try_limit_exit(self, symbol: str, side: str, amount: float, limit_price: float,
                        patience_s: float = None) -> Optional[dict]:
        """Post-only limit exit at the touch for maker fees (0.01% vs 0.06% taker).

        Returns the filled order, or None — and EVERY None return means the caller
        (close_long/close_short) MUST market-close: the resting order is by then
        cancelled-by-id, confirmed dead, or at worst still resting as reduceOnly
        (which cannot double-close a flat position; bot.py also sweeps leftovers
        via cancel_open_orders after every close). The position is never left
        without a mandatory market fallback.

        Patience window:
          - Config.MAKER_EXIT_ENABLED=False (default): legacy 4s (8 x 0.5s polls).
            Known to yield 0% maker fills — kept so deploying this code changes
            nothing until .env opts in.
          - True: rests Config.MAKER_EXIT_PATIENCE_S (clamped to
            MAKER_EXIT_PATIENCE_MAX_S, 2s polls) before cancel + market fallback.
          - An explicit patience_s argument (urgency-gated patient exits) takes
            precedence over both, same clamp.

        Order-path house rule (lessons.md:290): direct client calls that complete
        or raise — never _call_with_timeout-wrapped.
        """
        limit_price = self._round_price(symbol, limit_price)
        if patience_s is not None or Config.MAKER_EXIT_ENABLED:
            poll_interval = 2.0
            requested_s = float(patience_s if patience_s is not None else Config.MAKER_EXIT_PATIENCE_S)
            if requested_s > self.MAKER_EXIT_PATIENCE_MAX_S:
                logger.warning(f"[MAKER EXIT] patience {requested_s} "
                               f"clamped to {self.MAKER_EXIT_PATIENCE_MAX_S}s (cycle-watchdog budget)")
            patience_s = min(requested_s, self.MAKER_EXIT_PATIENCE_MAX_S)
            polls = max(1, int(patience_s / poll_interval))
        else:
            poll_interval = 0.5
            polls = 8  # legacy 4s window — pre-fix behavior
        try:
            order = self.client.create_order(symbol, "limit", side, amount, limit_price,
                                             params={"reduceOnly": True, "timeInForce": "PostOnly"})
            order_id = order.get("id")
            logger.info(f"[MAKER EXIT] Limit {side} {amount} {symbol} @ {limit_price} "
                        f"(patience {polls * poll_interval:.0f}s, id={order_id})")

            for _ in range(polls):
                time.sleep(poll_interval)
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                except Exception as e:
                    logger.debug(f"[MAKER EXIT] poll fetch_order failed {symbol} id={order_id}: {e}")
                    continue
                status = fetched.get("status", "")
                if status == "closed":
                    logger.info(f"[MAKER EXIT] Filled for {symbol}")
                    return fetched
                if status in ("canceled", "cancelled", "rejected", "expired"):
                    # PostOnly rejected (would-cross) or externally cancelled — the
                    # order is dead; don't burn the remaining patience window.
                    filled_now = float(fetched.get("filled", 0) or 0)
                    if filled_now > 0:
                        self._market_close_remainder(symbol, side, amount, filled_now)
                        return fetched
                    logger.info(f"[MAKER EXIT] Order {status} unfilled for {symbol} — market fallback")
                    return None

            # Patience expired — cancel-by-id BEFORE the caller's market fallback
            # so the same position can never be closed twice.
            try:
                self.client.cancel_order(order_id, symbol)
            except Exception as ce:
                # Cancel can fail because the order just filled, or transient API
                # error. Either way fall through to the post-cancel fetch; if that
                # is inconclusive we still return None — the market fallback and
                # the resting order are both reduceOnly, so a double-close is
                # rejected by the exchange rather than flipping the position.
                logger.warning(f"[MAKER EXIT] cancel failed {symbol} id={order_id}: {ce}")
            try:
                fetched = self.client.fetch_order(order_id, symbol)
                if fetched.get("status") == "closed":
                    logger.info(f"[MAKER EXIT] Filled (raced cancel) for {symbol}")
                    return fetched
                filled_amount = float(fetched.get("filled", 0) or 0)
                if filled_amount > 0:
                    self._market_close_remainder(symbol, side, amount, filled_amount)
                    return fetched
            except Exception as fe:
                logger.warning(f"[MAKER EXIT] post-cancel fetch_order failed {symbol} id={order_id}: {fe}")
            logger.info(f"[MAKER EXIT] Not filled in {polls * poll_interval:.0f}s, market fallback {symbol}")
            return None
        except Exception as e:
            logger.warning(f"[MAKER EXIT] Limit failed for {symbol}: {e}")
            return None

    def extract_order_fee(self, order: Optional[dict], symbol: Optional[str] = None) -> float:
        """Pull total fee (USDT) paid for an order from a ccxt response.

        Tries in order:
          1. order['fee']['cost']
          2. sum(order['fees'][*]['cost'])
          3. fetch_order(id, symbol) and re-check
          4. fetch_my_trades(symbol, since=...) and sum fees for matching order id
        Returns 0.0 if nothing can be resolved (caller treats as unknown).
        """
        if not order:
            return 0.0
        if not Config.is_live():
            return 0.0

        def _read(o: dict) -> float:
            try:
                fee = o.get("fee") if isinstance(o, dict) else None
                if isinstance(fee, dict) and fee.get("cost") is not None:
                    return abs(float(fee.get("cost") or 0))
                fees = o.get("fees") if isinstance(o, dict) else None
                if isinstance(fees, list) and fees:
                    total = 0.0
                    for f in fees:
                        if isinstance(f, dict) and f.get("cost") is not None:
                            total += abs(float(f.get("cost") or 0))
                    if total > 0:
                        return total
            except Exception:
                pass
            return 0.0

        def _computed(o: dict) -> float:
            """Fee = notional x rate, for when the exchange omits fee['cost'].

            Phemex market fills frequently return fee={'cost': None, 'rate': ...},
            so an explicit cost is unavailable but the rate is not. Prefer the
            exchange's own rate (exact); fall back to takerOrMaker -> configured
            taker/maker rate (estimate). Returns 0.0 if no notional is resolvable.
            """
            if not isinstance(o, dict):
                return 0.0
            notional = o.get("cost")
            if not notional:
                try:
                    filled = float(o.get("filled") or o.get("amount") or 0)
                    price = float(o.get("average") or o.get("price") or 0)
                    notional = filled * price
                except (TypeError, ValueError):
                    notional = 0.0
            try:
                notional = abs(float(notional or 0))
            except (TypeError, ValueError):
                notional = 0.0
            if notional <= 0:
                return 0.0
            rate = None
            fee = o.get("fee")
            if isinstance(fee, dict) and fee.get("rate") is not None:
                rate = fee.get("rate")
            if rate is None:
                for f in (o.get("fees") or []):
                    if isinstance(f, dict) and f.get("rate") is not None:
                        rate = f.get("rate")
                        break
            if rate is None:
                # No exchange rate given -> estimate from taker/maker tier.
                # Default to taker: extract_order_fee runs on close orders, and
                # ~92% of live exits fill taker (fee-ground-truth 2026-06-11).
                if o.get("takerOrMaker") == "maker":
                    rate = Config.MAKER_FEE_PERCENT / 100.0
                else:
                    rate = Config.TAKER_FEE_PERCENT / 100.0
            try:
                rate = abs(float(rate or 0))
            except (TypeError, ValueError):
                rate = 0.0
            return notional * rate if rate > 0 else 0.0

        cost = _read(order)
        if cost > 0:
            return cost

        order_id = order.get("id") if isinstance(order, dict) else None
        sym = symbol or (order.get("symbol") if isinstance(order, dict) else None)

        # Follow-up fetch_order
        fetched = None
        if order_id and sym:
            try:
                fetched = self.client.fetch_order(order_id, sym)
                cost = _read(fetched)
                if cost > 0:
                    return cost
            except Exception as e:
                logger.debug(f"extract_order_fee fetch_order failed for {sym}: {e}")

        # Fallback: scan recent fills
        if order_id and sym:
            try:
                since = int((time.time() - 600) * 1000)
                trades = self.client.fetch_my_trades(sym, since=since, limit=20)
                total = 0.0
                for t in trades or []:
                    if t.get("order") == order_id:
                        fee = t.get("fee") or {}
                        if fee.get("cost") is not None:
                            total += abs(float(fee.get("cost") or 0))
                        else:
                            for f in t.get("fees") or []:
                                if f.get("cost") is not None:
                                    total += abs(float(f.get("cost") or 0))
                if total > 0:
                    return total
            except Exception as e:
                logger.debug(f"extract_order_fee fetch_my_trades failed for {sym}: {e}")

        # Last resort: compute from rate x notional (exchange omitted fee.cost).
        # Prefer a fetched order (may carry rate), else the original order.
        for src in (fetched, order):
            computed = _computed(src) if src else 0.0
            if computed > 0:
                logger.debug(
                    f"extract_order_fee: computed {computed:.5f} USDT from rate x notional "
                    f"for {sym} (exchange omitted fee.cost)"
                )
                return computed

        return 0.0

    def _round_price(self, symbol: str, price: float) -> float:
        """Round price to exchange tick size to avoid rejection."""
        try:
            return float(self.client.price_to_precision(symbol, price))
        except Exception:
            return price

    def _round_amount(self, symbol: str, amount: float) -> float:
        """Round amount to exchange step size to avoid rejection."""
        try:
            return float(self.client.amount_to_precision(symbol, amount))
        except Exception:
            return amount

    def place_sl_tp(self, symbol: str, side: str, amount: float, sl_price: float, tp_price: float) -> dict:
        """Place stop-loss and take-profit orders on exchange. Returns order IDs."""
        order_side = "sell" if side == "long" else "buy"
        results = {"sl_order_id": None, "tp_order_id": None}

        # Round to exchange precision — unrounded prices cause silent rejections
        sl_price = self._round_price(symbol, sl_price)
        tp_price = self._round_price(symbol, tp_price)
        amount = self._round_amount(symbol, amount)

        if amount <= 0:
            logger.error(f"SL/TP skip: amount rounded to 0 for {symbol}")
            return results

        # Stop Loss — conditional trigger order
        # Phemex/ccxt requires triggerDirection: "descending" for long SL (price falling),
        # "ascending" for short SL (price rising). Without this, ccxt raises ArgumentsRequired.
        sl_trigger_dir = "descending" if side == "long" else "ascending"
        for attempt in range(3):
            try:
                sl_params = {
                    "reduceOnly": True,
                    "triggerPrice": sl_price,
                    "triggerDirection": sl_trigger_dir,
                }
                sl_order = self.client.create_order(symbol, "market", order_side, amount, None, params=sl_params)
                results["sl_order_id"] = sl_order.get("id")
                logger.info(f"SL order placed: {symbol} {order_side} trigger@{sl_price} dir={sl_trigger_dir} (id={results['sl_order_id']})")
                break
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < 2:
                    time.sleep(1)
                else:
                    logger.error(f"Failed to place SL for {symbol} (attempt {attempt+1}): {e}")
                    break

        # Take Profit — limit order triggered at TP price (maker fee instead of taker)
        tp_trigger_dir = "ascending" if side == "long" else "descending"
        for attempt in range(3):
            try:
                tp_params = {
                    "reduceOnly": True,
                    "triggerPrice": tp_price,
                    "triggerDirection": tp_trigger_dir,
                }
                # Use limit order at TP price for maker fees (0.01% vs 0.06% taker)
                tp_order = self.client.create_order(symbol, "limit", order_side, amount, tp_price, params=tp_params)
                results["tp_order_id"] = tp_order.get("id")
                logger.info(f"TP order placed (LIMIT/MAKER): {symbol} {order_side} trigger@{tp_price} dir={tp_trigger_dir} (id={results['tp_order_id']})")
                break
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < 2:
                    time.sleep(1)
                else:
                    # Fallback to market TP if limit not supported
                    try:
                        tp_params_mkt = {"reduceOnly": True, "triggerPrice": tp_price, "triggerDirection": tp_trigger_dir}
                        tp_order = self.client.create_order(symbol, "market", order_side, amount, None, params=tp_params_mkt)
                        results["tp_order_id"] = tp_order.get("id")
                        logger.info(f"TP order placed (MARKET fallback): {symbol} trigger@{tp_price}")
                    except Exception as e2:
                        logger.error(f"Failed to place TP for {symbol}: {e2}")
                    break

        return results

    def move_stop_loss(self, symbol: str, side: str, amount: float, new_sl: float,
                       sl_order_id: str) -> str:
        """Move the resting exchange SL to new_sl with NO naked-position window.

        Primary: atomic edit_order amend — the stop never disappears (non-destructive
        on failure). Fallback: place new SL → verify → cancel old by id; the old SL
        is NEVER cancelled before the new one is confirmed live.

        Complete-or-raise (lessons.md:290 — deliberately not _call_with_timeout-
        wrapped): raises RuntimeError if the move cannot be guaranteed, in which
        case the OLD SL is still resting. Returns the resting SL order id.
        See docs/superpowers/specs/2026-06-08-part-b-trailing-protection-plan.md.
        """
        if not Config.is_live():
            return sl_order_id
        if not sl_order_id or sl_order_id == "software":
            raise ValueError(f"move_stop_loss requires a live exchange SL id (got {sl_order_id!r})")

        order_side = "sell" if side == "long" else "buy"
        sl_trigger_dir = "descending" if side == "long" else "ascending"
        new_sl = self._round_price(symbol, new_sl)
        amount = self._round_amount(symbol, amount)
        params = {"reduceOnly": True, "triggerPrice": new_sl, "triggerDirection": sl_trigger_dir}

        # Primary — atomic amend. First live amend doubles as the one-time
        # edit_order param validation (endpoint unused before 2026-06-11), so log
        # the full request shape.
        last_err = None
        for attempt in range(3):
            try:
                logger.info(f"[SL-MOVE] amend {symbol} id={sl_order_id} -> trigger@{new_sl} params={params}")
                result = self.client.edit_order(sl_order_id, symbol, "market", order_side,
                                                amount, None, params=params)
                new_id = (result or {}).get("id") or sl_order_id
                if self.verify_sl_order(symbol, new_id):
                    logger.info(f"[SL-MOVE] amended {symbol} SL -> {new_sl} (id={new_id})")
                    return new_id
                last_err = RuntimeError("amend verify failed — order not in open orders")
            except Exception as e:
                last_err = e
                # Log the exception CLASS + repr, not just str(): ccxt wraps the raw
                # Phemex code/JSON (e.g. ExchangeError vs InvalidOrder vs NotSupported)
                # which str() drops — that detail is what diagnoses a recurring reject.
                logger.warning(f"[SL-MOVE] amend attempt {attempt+1}/3 failed for {symbol}: "
                               f"{type(e).__name__}: {e!r}")
            if attempt < 2:
                time.sleep(1 + attempt)

        # Fallback — place-then-cancel. If the duplicate reduce-only SL is rejected
        # (Merged-mode acceptance unknown, Appendix A), we raise with the old SL intact.
        logger.warning(f"[SL-MOVE] amend exhausted for {symbol} "
                       f"({type(last_err).__name__}: {last_err}) — fallback place-then-cancel")
        new_id = None
        for attempt in range(3):
            try:
                order = self.client.create_order(symbol, "market", order_side, amount, None, params=params)
                new_id = order.get("id")
                if new_id and self.verify_sl_order(symbol, new_id):
                    break
                new_id = None
            except Exception as e:
                last_err = e
                logger.warning(f"[SL-MOVE] fallback place attempt {attempt+1}/3 failed for {symbol}: "
                               f"{type(e).__name__}: {e!r}")
            if attempt < 2:
                time.sleep(1 + attempt)
        if not new_id:
            raise RuntimeError(f"move_stop_loss failed for {symbol}: old SL {sl_order_id} "
                               f"left in place ({type(last_err).__name__}: {last_err})")
        try:
            self.client.cancel_order(sl_order_id, symbol)
        except Exception as e:
            logger.warning(f"[SL-MOVE] could not cancel old SL {sl_order_id} for {symbol}: {e} — orphan reduce-only, cleaned at close")
        logger.info(f"[SL-MOVE] fallback placed {symbol} SL -> {new_sl} (id={new_id}, old cancelled)")
        return new_id

    def verify_sl_order(self, symbol: str, sl_order_id: str) -> bool:
        """Check if a stop-loss order is still active on the exchange."""
        if not Config.is_live() or not sl_order_id:
            return True  # assume OK in paper mode
        try:
            open_orders = self.client.fetch_open_orders(symbol)
            return any(o.get("id") == sl_order_id for o in open_orders)
        except Exception as e:
            logger.warning(f"Could not verify SL order for {symbol}: {e}")
            return True  # assume OK if we can't check

    def cancel_order_by_id(self, symbol: str, order_id: str) -> bool:
        """Cancel a single resting order by id (e.g. move a runner's TP off its
        entry-time level without touching the SL). Returns True only on confirmed
        cancel — callers gate on this so a failed cancel degrades gracefully (the
        old order stays resting) instead of leaving two live TPs."""
        if not Config.is_live():
            return True  # paper: nothing resting
        if not order_id or order_id == "software":
            return False
        try:
            self.client.cancel_order(order_id, symbol)
            logger.info(f"Cancelled order {order_id} for {symbol}")
            return True
        except Exception as e:
            logger.warning(f"Could not cancel order {order_id} for {symbol}: {e}")
            return False

    def cancel_open_orders(self, symbol: str):
        """Cancel all open orders for a symbol — cleans up orphaned SL/TP after close."""
        if not Config.is_live():
            return
        try:
            open_orders = self.client.fetch_open_orders(symbol)
            for order in open_orders:
                try:
                    self.client.cancel_order(order["id"], symbol)
                    logger.info(f"Cancelled order {order['id']} for {symbol}")
                except Exception as e:
                    logger.warning(f"Could not cancel order {order['id']} for {symbol}: {e}")
        except Exception as e:
            logger.warning(f"Could not fetch open orders for {symbol}: {e}")

    def ensure_leverage(self, symbol: str):
        """Set leverage for a symbol if not already configured."""
        if not Config.is_live():
            return
        try:
            self.client.set_leverage(Config.LEVERAGE, symbol)
            logger.info(f"Leverage set to {Config.LEVERAGE}x for {symbol}")
        except Exception as e:
            logger.warning(f"Could not set leverage for {symbol}: {e}")

    def set_symbol_leverage(self, symbol: str, leverage: int) -> None:
        """Set ISOLATED leverage for one symbol (ETH-TSM-28, 2026-07-06).

        Phemex USDT perps: positive leverageRr = isolated, negative = cross
        (ccxt phemex.set_leverage → PUT /g-positions/leverage). Per-symbol —
        other symbols' leverage is untouched. Unlike ensure_leverage this
        RAISES on failure: the caller sizes orders for `leverage`, so placing
        an order after a silent failure would be mis-margined."""
        if not Config.is_live():
            return
        self.client.set_leverage(leverage, symbol)
        logger.info(f"Leverage set to {leverage}x (isolated) for {symbol}")

    def place_stop_loss(self, symbol: str, side: str, amount: float, sl_price: float):
        """Place ONLY a stop-loss conditional order (no TP) — the ETH-TSM-28 slot
        must not carry a take-profit (spec: signal exit or −8% stop, nothing else).
        Mirrors the SL block of place_sl_tp: triggerDirection 'descending' for a
        long SL / 'ascending' for a short SL (lessons.md), price_to_precision via
        _round_price. Returns the order id or None."""
        order_side = "sell" if side == "long" else "buy"
        sl_price = self._round_price(symbol, sl_price)
        amount = self._round_amount(symbol, amount)
        if amount <= 0:
            logger.error(f"place_stop_loss skip: amount rounded to 0 for {symbol}")
            return None
        sl_trigger_dir = "descending" if side == "long" else "ascending"
        for attempt in range(3):
            try:
                params = {
                    "reduceOnly": True,
                    "triggerPrice": sl_price,
                    "triggerDirection": sl_trigger_dir,
                }
                order = self.client.create_order(symbol, "market", order_side, amount, None, params=params)
                oid = order.get("id")
                logger.info(f"SL-only order placed: {symbol} {order_side} trigger@{sl_price} dir={sl_trigger_dir} (id={oid})")
                return oid
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < 2:
                    time.sleep(1)
                else:
                    logger.error(f"Failed to place SL-only for {symbol} (attempt {attempt+1}): {e}")
                    return None
        return None

    def open_long_market(self, symbol: str, coin_amount: float) -> Optional[dict]:
        """Market (taker) entry for the ETH-TSM-28 30-minute maker-window fallback
        (pre-registered spec §7.2). Fixed coin amount, NOT margin-based. On an
        exception the ground-truth check catches a fill that landed anyway
        (mirrors _try_limit_entry's safety net; pre_amount=0 is safe here — the
        slot only enters when no ETH position exists anywhere, enforced by the
        ownership rule)."""
        if not Config.is_live():
            logger.error("open_long_market called in paper mode — refusing")
            return None
        amount = self._round_amount(symbol, coin_amount)
        if amount <= 0:
            logger.error(f"open_long_market: amount rounded to 0 for {symbol}")
            return None
        try:
            order = self.client.create_market_buy_order(symbol, amount)
            logger.info(f"[TAKER] OPEN LONG {amount} {symbol} (TSM maker-window fallback)")
            return order
        except Exception as e:
            logger.error(f"open_long_market failed for {symbol}: {e} — checking ground truth")
            gt = self._position_ground_truth(symbol, "long", pre_amount=0.0)
            return gt or None

    def get_open_positions(self) -> list[dict]:
        """Fetch open positions from the exchange (live mode only)."""
        try:
            raw = self._call_with_timeout(self.client.fetch_positions)
            if raw is None:
                return None
            result = []
            for p in raw:
                contracts = abs(p.get("contracts") or 0)
                if contracts <= 0:
                    continue
                side_raw = p.get("side", "")
                side = "long" if side_raw == "long" else "short"
                result.append({
                    "symbol":      p.get("symbol"),
                    "side":        side,
                    "entry_price": float(p.get("entryPrice") or 0),
                    "amount":      float(contracts),
                    "margin":      float(p.get("initialMargin") or 0),
                })
            return result
        except Exception as e:
            logger.error(f"Failed to fetch open positions: {e}")
            return None

    # ── Paper trading ────────────────────────────────────────────────────────

    def _paper_open(self, symbol: str, margin_usdt: float, side: str) -> dict:
        ticker = self.get_ticker(symbol)
        if not ticker:
            return {}
        price = ticker["last"]
        amount = self._coin_amount(symbol, margin_usdt, price)

        self.paper_balances[Config.BASE_CURRENCY] = self.paper_balances.get(Config.BASE_CURRENCY, 0) - margin_usdt

        order = {"id": f"paper_{len(self.paper_orders)}", "symbol": symbol, "side": side,
                 "price": price, "amount": amount, "margin": margin_usdt, "status": "closed"}
        self.paper_orders.append(order)
        logger.info(f"[PAPER] OPEN {side.upper()} {amount:.6f} {symbol.split('/')[0]} @ {price:.4f} "
                    f"(margin: {margin_usdt:.2f} USDT, {Config.LEVERAGE}x)")
        return order

    def _paper_close(self, symbol: str, coin_amount: float, side: str) -> dict:
        ticker = self.get_ticker(symbol)
        if not ticker:
            return {}
        price = ticker["last"]

        order = {"id": f"paper_{len(self.paper_orders)}", "symbol": symbol, "side": side,
                 "price": price, "amount": coin_amount, "status": "closed"}
        self.paper_orders.append(order)
        logger.info(f"[PAPER] CLOSE {side.upper()} {coin_amount:.6f} {symbol.split('/')[0]} @ {price:.4f}")
        return order
