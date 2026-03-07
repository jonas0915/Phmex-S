import ccxt
import pandas as pd
from typing import Optional
from config import Config
from logger import setup_logger

logger = setup_logger()


class Exchange:
    def __init__(self):
        exchange_class = getattr(ccxt, Config.EXCHANGE)
        params = {"enableRateLimit": True}

        if Config.is_live():
            params["apiKey"] = Config.API_KEY
            params["secret"] = Config.API_SECRET

        self.client = exchange_class(params)
        self.paper_balances: dict = {}
        self.paper_orders: list = []

        if not Config.is_live():
            logger.info("Paper trading mode: using simulated balances")
            self.paper_balances = {Config.BASE_CURRENCY: 10000.0}

    def get_balance(self, currency: str) -> float:
        if not Config.is_live():
            return self.paper_balances.get(currency, 0.0)
        try:
            balance = self.client.fetch_balance()
            return float(balance["free"].get(currency, 0.0))
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return 0.0

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 250) -> Optional[pd.DataFrame]:
        try:
            ohlcv = self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return None

    def get_ticker(self, symbol: str) -> Optional[dict]:
        try:
            return self.client.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol}: {e}")
            return None

    def place_market_buy(self, symbol: str, amount: float) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_buy(symbol, amount)
        try:
            order = self.client.create_market_buy_order(symbol, amount)
            logger.info(f"[LIVE] BUY {amount:.6f} {symbol} @ market")
            return order
        except Exception as e:
            logger.error(f"Failed to place buy order for {symbol}: {e}")
            return None

    def place_market_sell(self, symbol: str, amount: float) -> Optional[dict]:
        if not Config.is_live():
            return self._paper_sell(symbol, amount)
        try:
            order = self.client.create_market_sell_order(symbol, amount)
            logger.info(f"[LIVE] SELL {amount:.6f} {symbol} @ market")
            return order
        except Exception as e:
            logger.error(f"Failed to place sell order for {symbol}: {e}")
            return None

    def _paper_buy(self, symbol: str, usdt_amount: float) -> dict:
        ticker = self.get_ticker(symbol)
        if not ticker:
            return {}
        price = ticker["last"]
        base = symbol.split("/")[0]
        coin_amount = usdt_amount / price

        self.paper_balances[Config.BASE_CURRENCY] = self.paper_balances.get(Config.BASE_CURRENCY, 0) - usdt_amount
        self.paper_balances[base] = self.paper_balances.get(base, 0) + coin_amount

        order = {"id": f"paper_{len(self.paper_orders)}", "symbol": symbol, "side": "buy",
                 "price": price, "amount": coin_amount, "cost": usdt_amount, "status": "closed"}
        self.paper_orders.append(order)
        logger.info(f"[PAPER] BUY {coin_amount:.6f} {base} @ {price:.4f} (cost: {usdt_amount:.2f} USDT)")
        return order

    def _paper_sell(self, symbol: str, coin_amount: float) -> dict:
        ticker = self.get_ticker(symbol)
        if not ticker:
            return {}
        price = ticker["last"]
        base = symbol.split("/")[0]
        usdt_received = coin_amount * price

        self.paper_balances[base] = self.paper_balances.get(base, 0) - coin_amount
        self.paper_balances[Config.BASE_CURRENCY] = self.paper_balances.get(Config.BASE_CURRENCY, 0) + usdt_received

        order = {"id": f"paper_{len(self.paper_orders)}", "symbol": symbol, "side": "sell",
                 "price": price, "amount": coin_amount, "cost": usdt_received, "status": "closed"}
        self.paper_orders.append(order)
        logger.info(f"[PAPER] SELL {coin_amount:.6f} {base} @ {price:.4f} (received: {usdt_received:.2f} USDT)")
        return order
