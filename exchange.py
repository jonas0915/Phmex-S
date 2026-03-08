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
        params = {"enableRateLimit": True, "options": {"defaultType": "swap"}}

        if Config.is_live():
            params["apiKey"] = Config.API_KEY
            params["secret"] = Config.API_SECRET

        self.client = exchange_class(params)
        self.client.load_markets()

        self.paper_balances: dict = {}
        self.paper_orders: list = []

        if not Config.is_live():
            logger.info("Paper trading mode: using simulated balances")
            self.paper_balances = {Config.BASE_CURRENCY: 10000.0}
        else:
            # Set leverage and margin mode for each pair on the exchange
            for symbol in Config.TRADING_PAIRS:
                try:
                    self.client.set_leverage(Config.LEVERAGE, symbol)
                    logger.info(f"Leverage set to {Config.LEVERAGE}x for {symbol}")
                except Exception as e:
                    logger.warning(f"Could not set leverage for {symbol}: {e}")
                try:
                    self.client.set_margin_mode("isolated", symbol)
                    logger.info(f"Margin mode set to isolated for {symbol}")
                except Exception as e:
                    logger.warning(f"Could not set margin mode for {symbol}: {e}")

    def get_balance(self, currency: str) -> float:
        if not Config.is_live():
            return self.paper_balances.get(currency, 0.0)
        try:
            balance = self.client.fetch_balance()
            return float(balance["free"].get(currency, 0.0))
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return 0.0

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

            return {
                "imbalance":  imbalance,
                "bid_vol":    bid_vol,
                "ask_vol":    ask_vol,
                "best_bid":   best_bid,
                "best_ask":   best_ask,
                "spread_pct": (best_ask - best_bid) / best_bid * 100 if best_bid else 0,
                "bid_walls":  bid_walls,
                "ask_walls":  ask_walls,
            }
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
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

    def open_long(self, symbol: str, margin_usdt: float) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_open(symbol, margin_usdt, side="long")
        ticker = self.get_ticker(symbol)
        price = ticker["last"] if ticker else 1
        amount = self._coin_amount(symbol, margin_usdt, price)
        for attempt in range(3):
            try:
                order = self.client.create_market_buy_order(symbol, amount, params={"marginMode": "isolated"})
                logger.info(f"[LIVE] LONG {amount:.6f} {symbol} @ market (margin: {margin_usdt:.2f} USDT, {Config.LEVERAGE}x)")
                return order
            except Exception as e:
                if self._is_rate_limit_error(e):
                    logger.warning(f"Rate limited on open_long {symbol} (attempt {attempt+1}/3): {e}")
                    time.sleep(1)
                else:
                    logger.error(f"Failed to open long for {symbol}: {e}")
                    return None
        logger.error(f"open_long {symbol} failed after 3 rate-limit retries")
        return None

    def close_long(self, symbol: str, coin_amount: float) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_close(symbol, coin_amount, side="long")
        for attempt in range(3):
            try:
                order = self.client.create_market_sell_order(symbol, coin_amount, params={"reduceOnly": True})
                logger.info(f"[LIVE] CLOSE LONG {coin_amount:.6f} {symbol}")
                return order
            except Exception as e:
                if self._is_rate_limit_error(e):
                    logger.warning(f"Rate limited on close_long {symbol} (attempt {attempt+1}/3): {e}")
                    time.sleep(1)
                else:
                    logger.error(f"Failed to close long for {symbol}: {e}")
                    return None
        logger.error(f"close_long {symbol} failed after 3 rate-limit retries")
        return None

    # ── Short ────────────────────────────────────────────────────────────────

    def open_short(self, symbol: str, margin_usdt: float) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_open(symbol, margin_usdt, side="short")
        ticker = self.get_ticker(symbol)
        price = ticker["last"] if ticker else 1
        amount = self._coin_amount(symbol, margin_usdt, price)
        for attempt in range(3):
            try:
                order = self.client.create_market_sell_order(symbol, amount, params={"marginMode": "isolated"})
                logger.info(f"[LIVE] SHORT {amount:.6f} {symbol} @ market (margin: {margin_usdt:.2f} USDT, {Config.LEVERAGE}x)")
                return order
            except Exception as e:
                if self._is_rate_limit_error(e):
                    logger.warning(f"Rate limited on open_short {symbol} (attempt {attempt+1}/3): {e}")
                    time.sleep(1)
                else:
                    logger.error(f"Failed to open short for {symbol}: {e}")
                    return None
        logger.error(f"open_short {symbol} failed after 3 rate-limit retries")
        return None

    def close_short(self, symbol: str, coin_amount: float) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_close(symbol, coin_amount, side="short")
        for attempt in range(3):
            try:
                order = self.client.create_market_buy_order(symbol, coin_amount, params={"reduceOnly": True})
                logger.info(f"[LIVE] CLOSE SHORT {coin_amount:.6f} {symbol}")
                return order
            except Exception as e:
                if self._is_rate_limit_error(e):
                    logger.warning(f"Rate limited on close_short {symbol} (attempt {attempt+1}/3): {e}")
                    time.sleep(1)
                else:
                    logger.error(f"Failed to close short for {symbol}: {e}")
                    return None
        logger.error(f"close_short {symbol} failed after 3 rate-limit retries")
        return None

    def place_sl_tp(self, symbol: str, side: str, amount: float, sl_price: float, tp_price: float) -> dict:
        """Place stop-loss and take-profit orders on exchange. Returns order IDs."""
        order_side = "sell" if side == "long" else "buy"
        results = {"sl_order_id": None, "tp_order_id": None}

        # Stop Loss — market stop order
        for attempt in range(3):
            try:
                sl_params = {"reduceOnly": True, "triggerPrice": sl_price, "triggerType": "ByLastPrice"}
                sl_order = self.client.create_order(symbol, "stop_market", order_side, amount, None, params=sl_params)
                results["sl_order_id"] = sl_order.get("id")
                logger.info(f"SL order placed: {symbol} {order_side} @ {sl_price:.4f} (id={results['sl_order_id']})")
                break
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < 2:
                    time.sleep(1)
                else:
                    logger.error(f"Failed to place SL for {symbol}: {e}")
                    break

        # Take Profit — limit order
        for attempt in range(3):
            try:
                tp_params = {"reduceOnly": True}
                tp_order = self.client.create_order(symbol, "limit", order_side, amount, tp_price, params=tp_params)
                results["tp_order_id"] = tp_order.get("id")
                logger.info(f"TP order placed: {symbol} {order_side} @ {tp_price:.4f} (id={results['tp_order_id']})")
                break
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < 2:
                    time.sleep(1)
                else:
                    logger.error(f"Failed to place TP for {symbol}: {e}")
                    break

        return results

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
            return []

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
