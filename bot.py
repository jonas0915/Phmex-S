import time
from config import Config
from exchange import Exchange
from indicators import add_all_indicators
from risk_manager import RiskManager
from strategies import STRATEGIES, Signal
from scanner import scan_top_gainers, volatility_scan
from logger import setup_logger

logger = setup_logger()


class Phmex2Bot:
    def __init__(self):
        Config.validate()
        self.exchange = Exchange()
        self.risk = RiskManager()
        self.strategy_fn = STRATEGIES.get(Config.STRATEGY, STRATEGIES["combined"])
        self.running = False
        self.cycle_count = 0
        self.active_pairs = Config.TRADING_PAIRS[:]
        self._leverage_set: set = set()  # track symbols that already have leverage configured

    def start(self):
        logger.info(f"Phmex2 Bot starting | Mode: {Config.MODE.upper()} | Strategy: {Config.STRATEGY}")
        logger.info(f"Leverage: {Config.LEVERAGE}x | Margin/trade: ${Config.TRADE_AMOUNT_USDT} | Timeframe: {Config.TIMEFRAME}")
        if Config.SCANNER_ENABLED:
            logger.info(f"Volatility scanner ON — top {Config.SCANNER_TOP_N} pairs, min vol ${Config.SCANNER_MIN_VOLUME:,.0f}, refresh every {Config.SCANNER_REFRESH_CYCLES} cycles (~{Config.SCANNER_REFRESH_CYCLES * Config.LOOP_INTERVAL}s)")
            self.active_pairs = volatility_scan(self.exchange.client)
        logger.info(f"Trading pairs: {', '.join(self.active_pairs)}")

        balance = self.exchange.get_balance(Config.BASE_CURRENCY)
        self.risk.set_initial_balance(balance)
        logger.info(f"Starting balance: {balance:.2f} {Config.BASE_CURRENCY}")

        if Config.is_live():
            open_pos = self.exchange.get_open_positions()
            if open_pos:
                self.risk.sync_positions(open_pos)
                logger.info(f"Synced {len(open_pos)} open position(s) from exchange")

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

        # Refresh volatility scan periodically
        if Config.SCANNER_ENABLED and self.cycle_count % Config.SCANNER_REFRESH_CYCLES == 0:
            logger.info("[SCANNER] Running volatility scan...")
            new_pairs = volatility_scan(self.exchange.client)
            held = set(self.risk.positions.keys())
            self.active_pairs = list(held | set(new_pairs))

        # Fetch current prices for all pairs
        prices = {}
        for symbol in self.active_pairs:
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
                    if pos.side == "long":
                        self.exchange.close_long(symbol, pos.amount)
                    else:
                        self.exchange.close_short(symbol, pos.amount)
                    self.risk.close_position(symbol, price, reason)
                    self.exchange.cancel_open_orders(symbol)

        # Check for new entry signals
        real_balance = self.exchange.get_balance(Config.BASE_CURRENCY)
        self.risk.update_peak_balance(real_balance)
        available = real_balance  # local decrement for multi-trade cap within one cycle

        for symbol in self.active_pairs:
            if symbol in self.risk.positions:
                continue

            if not self.risk.can_open_trade(available):
                break

            if symbol not in self._leverage_set:
                self.exchange.ensure_leverage(symbol)
                self._leverage_set.add(symbol)
            df = self.exchange.get_ohlcv(symbol, Config.TIMEFRAME, limit=Config.CANDLE_LOOKBACK)
            if df is None or len(df) < 50:
                logger.warning(f"Not enough data for {symbol}, skipping.")
                continue

            df = add_all_indicators(df)
            if len(df) < 2:
                continue

            orderbook = self.exchange.get_order_book(symbol)
            try:
                signal = self.strategy_fn(df, orderbook)
            except TypeError:
                signal = self.strategy_fn(df)

            if signal.signal != Signal.HOLD and signal.strength < 0.65:
                logger.debug(f"Signal too weak for {symbol}: {signal.strength:.2f}, skipping")
                continue

            price = prices.get(symbol, df.iloc[-1]["close"])
            margin = self.risk.calculate_margin(available)

            if signal.signal == Signal.BUY:
                if margin > available:
                    logger.warning(f"Insufficient balance for {symbol}: need {margin:.2f}, have {available:.2f}")
                    continue
                order = self.exchange.open_long(symbol, margin)
                if order:
                    self.risk.open_position(symbol, price, margin, side="long")
                    pos = self.risk.positions[symbol]
                    sl_tp = self.exchange.place_sl_tp(symbol, "long", pos.amount, pos.stop_loss, pos.take_profit)
                    pos.sl_order_id = sl_tp.get("sl_order_id")
                    pos.tp_order_id = sl_tp.get("tp_order_id")
                    available -= margin
                    logger.info(f"LONG ENTRY: {symbol} | {signal.reason} | Strength: {signal.strength:.2f}")

            elif signal.signal == Signal.SELL:
                if margin > available:
                    logger.warning(f"Insufficient balance for {symbol}: need {margin:.2f}, have {available:.2f}")
                    continue
                order = self.exchange.open_short(symbol, margin)
                if order:
                    self.risk.open_position(symbol, price, margin, side="short")
                    pos = self.risk.positions[symbol]
                    sl_tp = self.exchange.place_sl_tp(symbol, "short", pos.amount, pos.stop_loss, pos.take_profit)
                    pos.sl_order_id = sl_tp.get("sl_order_id")
                    pos.tp_order_id = sl_tp.get("tp_order_id")
                    available -= margin
                    logger.info(f"SHORT ENTRY: {symbol} | {signal.reason} | Strength: {signal.strength:.2f}")

        if self.cycle_count % 10 == 0:
            self.risk.print_stats(real_balance)

    def _shutdown(self):
        balance = self.exchange.get_balance(Config.BASE_CURRENCY)
        logger.info(f"Shutting down. Open positions: {list(self.risk.positions.keys())}")
        self.risk.print_stats(balance)
