import time
from config import Config
from exchange import Exchange
from indicators import add_all_indicators
from risk_manager import RiskManager
from strategies import STRATEGIES, Signal
from logger import setup_logger

logger = setup_logger()


class DegenCrytBot:
    def __init__(self):
        Config.validate()
        self.exchange = Exchange()
        self.risk = RiskManager()
        self.strategy_fn = STRATEGIES.get(Config.STRATEGY, STRATEGIES["combined"])
        self.running = False
        self.cycle_count = 0

    def start(self):
        logger.info(f"DegenCryt Bot starting | Mode: {Config.MODE.upper()} | Strategy: {Config.STRATEGY}")
        logger.info(f"Pairs: {', '.join(Config.TRADING_PAIRS)} | Timeframe: {Config.TIMEFRAME}")

        balance = self.exchange.get_balance(Config.BASE_CURRENCY)
        self.risk.set_initial_balance(balance)
        logger.info(f"Starting balance: {balance:.2f} {Config.BASE_CURRENCY}")

        self.running = True
        try:
            while self.running:
                self._run_cycle()
                time.sleep(Config.LOOP_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
        finally:
            self._shutdown()

    def _run_cycle(self):
        self.cycle_count += 1
        logger.debug(f"Cycle #{self.cycle_count}")

        # Fetch current prices for all pairs
        prices = {}
        for symbol in Config.TRADING_PAIRS:
            ticker = self.exchange.get_ticker(symbol)
            if ticker:
                prices[symbol] = ticker["last"]

        # Check exit conditions for open positions
        to_close = self.risk.check_positions(prices)
        for symbol, reason in to_close:
            price = prices.get(symbol)
            if price:
                pos = self.risk.positions.get(symbol)
                if pos:
                    self.exchange.place_market_sell(symbol, pos.amount)
                    self.risk.close_position(symbol, price, reason)

        # Check for new entry signals
        balance = self.exchange.get_balance(Config.BASE_CURRENCY)
        self.risk.update_peak_balance(balance)

        for symbol in Config.TRADING_PAIRS:
            if symbol in self.risk.positions:
                continue  # Already in a position for this pair

            if not self.risk.can_open_trade(balance):
                break

            df = self.exchange.get_ohlcv(symbol, Config.TIMEFRAME, limit=Config.CANDLE_LOOKBACK)
            if df is None or len(df) < 50:
                logger.warning(f"Not enough data for {symbol}, skipping.")
                continue

            df = add_all_indicators(df)
            if len(df) < 2:
                continue

            signal = self.strategy_fn(df)

            if signal.signal == Signal.BUY:
                price = prices.get(symbol, df.iloc[-1]["close"])
                usdt_amount = self.risk.calculate_position_size(balance, price)

                if usdt_amount > balance:
                    logger.warning(f"Insufficient balance for {symbol}: need {usdt_amount:.2f}, have {balance:.2f}")
                    continue

                order = self.exchange.place_market_buy(symbol, usdt_amount)
                if order:
                    self.risk.open_position(symbol, price, usdt_amount)
                    balance -= usdt_amount
                    logger.info(f"ENTRY: {symbol} | Signal: {signal.reason} | Strength: {signal.strength:.2f}")

            elif signal.signal == Signal.SELL:
                if symbol in self.risk.positions:
                    pos = self.risk.positions[symbol]
                    price = prices.get(symbol, df.iloc[-1]["close"])
                    self.exchange.place_market_sell(symbol, pos.amount)
                    self.risk.close_position(symbol, price, f"strategy_signal: {signal.reason}")

        # Print stats every 10 cycles
        if self.cycle_count % 10 == 0:
            self.risk.print_stats(balance)

    def _shutdown(self):
        balance = self.exchange.get_balance(Config.BASE_CURRENCY)
        logger.info(f"Shutting down. Open positions: {list(self.risk.positions.keys())}")
        self.risk.print_stats(balance)
