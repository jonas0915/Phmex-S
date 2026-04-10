import ccxt
import time
import pandas as pd
from typing import Optional
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

    def get_balance(self, currency: str) -> float:
        if not Config.is_live():
            return self.paper_balances.get(currency, 0.0)
        try:
            balance = self.client.fetch_balance()
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
            ohlcv = self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return None

    def get_order_book(self, symbol: str, depth: int = 20) -> Optional[dict]:
        try:
            ob = self.client.fetch_order_book(symbol, limit=depth)
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
            trades = self.client.fetch_trades(symbol, limit=limit)
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
            trades = self.client.fetch_trades(symbol, limit=limit)
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
            cvd_slope = second_half_avg - first_half_avg

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
            funding = self.client.fetch_funding_rate(symbol)
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
            return self.client.fetch_ticker(symbol)
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

    def _try_limit_then_market(self, symbol: str, side: str, amount: float, limit_price: float) -> Optional[dict]:
        """Place limit order at maker price, wait up to 3s for fill, fallback to market.
        Maker fee = 0.01% vs taker 0.06% — saves 83% on fees."""
        limit_price = self._round_price(symbol, limit_price)
        order_side = "buy" if side == "long" else "sell"

        # Try limit order first (maker)
        try:
            order = self.client.create_order(symbol, "limit", order_side, amount, limit_price, params={"timeInForce": "PostOnly"})
            order_id = order.get("id")
            logger.info(f"[MAKER] Limit {order_side} {amount} {symbol} @ {limit_price} (id={order_id})")

            # Wait up to 3s for fill
            for _ in range(6):
                time.sleep(0.5)
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    status = fetched.get("status", "")
                    if status == "closed":
                        logger.info(f"[MAKER] Limit filled for {symbol}")
                        return fetched
                    if status == "canceled" or status == "cancelled":
                        break
                except Exception:
                    pass

            # Not filled — cancel and fall through to market
            try:
                self.client.cancel_order(order_id, symbol)
                # Check for partial fill after cancel
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    filled_amount = fetched.get("filled", 0) or 0
                    if fetched.get("status") == "closed":
                        logger.info(f"[MAKER] Limit filled (raced cancel) for {symbol}")
                        return fetched
                    if filled_amount > 0:
                        remaining = amount - filled_amount
                        logger.info(f"[MAKER] Partial fill {filled_amount}/{amount} {symbol}, market for remaining {remaining}")
                        if remaining > 0:
                            remaining = self._round_amount(symbol, remaining)
                            if remaining > 0:
                                try:
                                    if side == "long":
                                        mkt = self.client.create_market_buy_order(symbol, remaining)
                                    else:
                                        mkt = self.client.create_market_sell_order(symbol, remaining)
                                    logger.info(f"[TAKER] Market {order_side} {remaining} {symbol} (partial fill remainder)")
                                    return mkt
                                except Exception as me:
                                    logger.error(f"Market remainder failed for {symbol}: {me}")
                                    return fetched  # Return partial fill info
                        return fetched  # Remaining rounded to 0, partial fill is enough
                    else:
                        logger.info(f"[MAKER] Limit not filled, cancelled — falling back to market for {symbol}")
                except Exception:
                    logger.info(f"[MAKER] Limit cancelled, falling back to market for {symbol}")
            except Exception:
                # May already be filled or cancelled
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    if fetched.get("status") == "closed":
                        return fetched
                    # Check for partial fill on cancel failure too
                    filled_amount = float(fetched.get("filled", 0) or 0)
                    if filled_amount > 0:
                        remaining = amount - filled_amount
                        remaining = self._round_amount(symbol, remaining)
                        if remaining > 0:
                            try:
                                if side == "long":
                                    rem_order = self.client.create_market_buy_order(symbol, remaining)
                                else:
                                    rem_order = self.client.create_market_sell_order(symbol, remaining)
                                logger.info(f"[MAKER] Cancel failed but partial fill {filled_amount} — market remainder {remaining} {symbol}")
                                return rem_order
                            except Exception as me:
                                logger.error(f"Market remainder failed for {symbol}: {me}")
                                return fetched
                        return fetched
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[MAKER] Limit order failed for {symbol}: {e} — using market")

        # Fallback: market order (taker)
        try:
            if side == "long":
                order = self.client.create_market_buy_order(symbol, amount)
            else:
                order = self.client.create_market_sell_order(symbol, amount)
            logger.info(f"[TAKER] Market {order_side} {amount} {symbol} (fallback)")
            return order
        except Exception as e:
            logger.error(f"Market order also failed for {symbol}: {e}")
            return None

    def open_long(self, symbol: str, margin_usdt: float, price: float = None) -> Optional[dict]:
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
        return self._try_limit_then_market(symbol, "long", amount, limit_price)

    def close_long(self, symbol: str, coin_amount: float) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_close(symbol, coin_amount, side="long")
        coin_amount = self._round_amount(symbol, coin_amount)
        if coin_amount <= 0:
            logger.error(f"Amount rounded to 0 for close_long {symbol}")
            return None
        # Sell at best ask for maker exit
        ob = self.get_order_book(symbol, depth=5)
        limit_price = ob["best_ask"] if ob and ob.get("best_ask") else None
        if limit_price:
            result = self._try_limit_exit(symbol, "sell", coin_amount, limit_price)
            if result:
                return result
        # Fallback to market
        try:
            order = self.client.create_market_sell_order(symbol, coin_amount, params={"reduceOnly": True})
            logger.info(f"[TAKER] CLOSE LONG {coin_amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Failed to close long for {symbol}: {e}")
            return None

    # ── Short ────────────────────────────────────────────────────────────────

    def open_short(self, symbol: str, margin_usdt: float, price: float = None) -> Optional[dict]:
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
        return self._try_limit_then_market(symbol, "short", amount, limit_price)

    def close_short(self, symbol: str, coin_amount: float) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_close(symbol, coin_amount, side="short")
        coin_amount = self._round_amount(symbol, coin_amount)
        if coin_amount <= 0:
            logger.error(f"Amount rounded to 0 for close_short {symbol}")
            return None
        # Buy at best bid for maker exit
        ob = self.get_order_book(symbol, depth=5)
        limit_price = ob["best_bid"] if ob and ob.get("best_bid") else None
        if limit_price:
            result = self._try_limit_exit(symbol, "buy", coin_amount, limit_price)
            if result:
                return result
        # Fallback to market
        try:
            order = self.client.create_market_buy_order(symbol, coin_amount, params={"reduceOnly": True})
            logger.info(f"[TAKER] CLOSE SHORT {coin_amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Failed to close short for {symbol}: {e}")
            return None

    def _try_limit_exit(self, symbol: str, side: str, amount: float, limit_price: float) -> Optional[dict]:
        """Try limit exit for maker fees. Shorter timeout than entry (2s) since exits are more urgent."""
        limit_price = self._round_price(symbol, limit_price)
        try:
            order = self.client.create_order(symbol, "limit", side, amount, limit_price,
                                             params={"reduceOnly": True, "timeInForce": "PostOnly"})
            order_id = order.get("id")
            logger.info(f"[MAKER EXIT] Limit {side} {amount} {symbol} @ {limit_price}")

            for _ in range(4):  # 2s total
                time.sleep(0.5)
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    if fetched.get("status") == "closed":
                        logger.info(f"[MAKER EXIT] Filled for {symbol}")
                        return fetched
                except Exception:
                    pass

            # Cancel unfilled limit
            try:
                self.client.cancel_order(order_id, symbol)
                # Check for partial fill after cancel
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    filled_amount = fetched.get("filled", 0) or 0
                    if fetched.get("status") == "closed":
                        logger.info(f"[MAKER EXIT] Filled (raced cancel) for {symbol}")
                        return fetched
                    if filled_amount > 0:
                        # Market-close the remainder to avoid orphan position
                        remaining = amount - float(filled_amount)
                        remaining = self._round_amount(symbol, remaining)
                        if remaining > 0:
                            try:
                                self.client.create_order(symbol, "market", side, remaining, None, params={"reduceOnly": True})
                                logger.info(f"[MAKER EXIT] Partial {filled_amount}, market remainder {remaining} {symbol}")
                            except Exception as me:
                                logger.error(f"[MAKER EXIT] Remainder market failed {symbol}: {me}")
                        return fetched
                    else:
                        logger.info(f"[MAKER EXIT] Not filled, cancelled {symbol}")
                except Exception:
                    logger.info(f"[MAKER EXIT] Cancelled {symbol}")
            except Exception:
                try:
                    fetched = self.client.fetch_order(order_id, symbol)
                    if fetched.get("status") == "closed":
                        return fetched
                    filled_amount = fetched.get("filled", 0) or 0
                    if filled_amount > 0:
                        # Market-close the remainder to avoid orphan position
                        remaining = amount - float(filled_amount)
                        remaining = self._round_amount(symbol, remaining)
                        if remaining > 0:
                            try:
                                self.client.create_order(symbol, "market", side, remaining, None, params={"reduceOnly": True})
                                logger.info(f"[MAKER EXIT] Partial {filled_amount}, market remainder {remaining} {symbol}")
                            except Exception as me:
                                logger.error(f"[MAKER EXIT] Remainder market failed {symbol}: {me}")
                        return fetched
                except Exception:
                    pass
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

        cost = _read(order)
        if cost > 0:
            return cost

        order_id = order.get("id") if isinstance(order, dict) else None
        sym = symbol or (order.get("symbol") if isinstance(order, dict) else None)

        # Follow-up fetch_order
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

    def get_open_positions(self) -> list[dict]:
        """Fetch open positions from the exchange (live mode only)."""
        try:
            raw = self.client.fetch_positions()
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
