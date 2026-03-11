import time
import subprocess
from config import Config
from exchange import Exchange
from indicators import add_all_indicators
from risk_manager import RiskManager
from strategies import STRATEGIES, Signal
from scanner import scan_top_gainers, volatility_scan
from logger import setup_logger
from ws_feed import WSDataFeed
import notifier

logger = setup_logger()

# ExpressVPN server rotation list — cycled through on each CDN ban
_VPN_SERVERS = [
    "usa-new-york",
    "usa-chicago",
    "usa-los-angeles-1",
    "usa-dallas",
    "usa-seattle",
    "usa-miami",
    "usa-atlanta",
    "usa-denver",
]
_vpn_index = 1  # start at 1 — index 0 (usa-new-york) is the default connect server


def _rotate_vpn():
    """Disconnect and reconnect ExpressVPN to a new server to get a fresh IP."""
    global _vpn_index
    server = _VPN_SERVERS[_vpn_index % len(_VPN_SERVERS)]
    _vpn_index += 1
    logger.info(f"[VPN] Rotating to {server}...")
    try:
        subprocess.run(["expressvpnctl", "disconnect"], timeout=15, check=False)
        time.sleep(3)
        subprocess.run(["expressvpnctl", "connect", server], timeout=30, check=False)
        time.sleep(5)
        result = subprocess.run(["expressvpnctl", "status"], capture_output=True, text=True, timeout=10)
        logger.info(f"[VPN] {result.stdout.splitlines()[0] if result.stdout else 'status unknown'}")
    except Exception as e:
        logger.warning(f"[VPN] Rotation failed: {e}")


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
        self.consecutive_errors = 0
        self.ban_mode = False
        self.ban_mode_until = 0
        self._ws_feed: WSDataFeed | None = None
        self._empty_price_cycles = 0  # consecutive cycles with no ticker data (CDN ban detection)

    def start(self):
        logger.info(f"Phmex-S Scalp Bot starting | Mode: {Config.MODE.upper()} | Strategy: {Config.STRATEGY}")
        logger.info(f"Leverage: {Config.LEVERAGE}x | Margin/trade: ${Config.TRADE_AMOUNT_USDT} | Timeframe: {Config.TIMEFRAME}")

        # Warm balance/equity cache — retry up to 5x with 15s delay if rate-limited
        balance = 0.0
        for _attempt in range(5):
            balance = self.exchange.get_balance(Config.BASE_CURRENCY)
            if balance > 0:
                break
            logger.warning(f"Balance fetch returned 0 (attempt {_attempt+1}/5), retrying in 15s...")
            time.sleep(15)
        self.exchange.get_equity(Config.BASE_CURRENCY)  # prime the equity cache
        self.risk.set_initial_balance(balance)
        logger.info(f"Starting balance: {balance:.2f} {Config.BASE_CURRENCY}")

        if Config.SCANNER_ENABLED:
            logger.info(f"Volatility scanner ON — top {Config.SCANNER_TOP_N} pairs, min vol ${Config.SCANNER_MIN_VOLUME:,.0f}, refresh every {Config.SCANNER_REFRESH_CYCLES} cycles (~{Config.SCANNER_REFRESH_CYCLES * Config.LOOP_INTERVAL}s)")
            logger.info(f"[SCANNER] First scan runs at cycle {Config.SCANNER_REFRESH_CYCLES} (~{Config.SCANNER_REFRESH_CYCLES * Config.LOOP_INTERVAL}s from now).")
        logger.info(f"Trading pairs: {', '.join(self.active_pairs)}")
        notifier.notify_startup(balance, self.active_pairs, Config.MODE, Config.STRATEGY)

        if Config.is_live():
            logger.info("[WS] Starting WebSocket data feed...")
            self._ws_feed = WSDataFeed(self.active_pairs, Config.TIMEFRAME)
            self._ws_feed.start()
            logger.info("[WS] Seeding cache with REST history...")
            seeded = self._ws_feed.seed(self.exchange.client, limit=Config.CANDLE_LOOKBACK)
            logger.info(f"[WS] Seed complete — {seeded}/{len(self.active_pairs)} pairs ready")

        if Config.is_live():
            open_pos = None
            for _attempt in range(3):
                open_pos = self.exchange.get_open_positions()
                if open_pos is not None:
                    break
                logger.warning(f"Could not fetch open positions (attempt {_attempt+1}/3), retrying in 15s...")
                time.sleep(15)
            if open_pos is None:
                logger.warning("Could not sync open positions at startup — entering ban mode for 2 min to avoid duplicate entries.")
                self.ban_mode = True
                self.ban_mode_until = time.time() + 120
            elif open_pos:
                own_pos = [p for p in open_pos if p["symbol"] in self.active_pairs]
                if own_pos:
                    self.risk.sync_positions(own_pos)
                    logger.info(f"Synced {len(own_pos)} open position(s) from exchange")
                else:
                    logger.info("No open positions found on exchange.")

        self.running = True
        try:
            while self.running:
                try:
                    self._run_cycle()
                    self.consecutive_errors = 0
                except Exception as e:
                    self.consecutive_errors += 1
                    logger.error(f"Cycle error ({self.consecutive_errors}): {e}")
                    if self.consecutive_errors >= 5:
                        self.ban_mode = True
                        self.ban_mode_until = time.time() + 600
                        logger.warning("[BAN MODE] Entering ban mode for 10 minutes after 5 consecutive errors")
                        self.consecutive_errors = 0
                        notifier.notify_ban_mode(10)
                time.sleep(Config.LOOP_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
        finally:
            self._shutdown()

    def _run_cycle(self):
        import time as _time_module
        if self.ban_mode:
            if _time_module.time() < self.ban_mode_until:
                return
            # Use WS connectivity check instead of REST endpoint test
            if self._ws_feed and self._ws_feed.is_connected:
                test = True
            else:
                sym = self.active_pairs[0] if self.active_pairs else None
                test = self.exchange.get_ohlcv(sym, Config.TIMEFRAME, limit=3) if sym else None
            if not test or (hasattr(test, '__len__') and len(test) == 0):
                self.ban_mode_until = _time_module.time() + 600
                logger.warning("[BAN MODE] Still blocked, extending pause 10 minutes")
                return
            else:
                self.ban_mode = False
                self.consecutive_errors = 0
                logger.info("[BAN MODE] Connection restored, resuming trading")
                notifier.notify_ban_lifted()

        self.cycle_count += 1
        logger.info(f"Cycle #{self.cycle_count} | Positions: {len(self.risk.positions)}")

        # Refresh volatility scan periodically
        if Config.SCANNER_ENABLED and self.cycle_count % Config.SCANNER_REFRESH_CYCLES == 0:
            logger.info("[SCANNER] Running volatility scan...")
            new_pairs = volatility_scan(self.exchange.client)
            held = set(self.risk.positions.keys())
            self.active_pairs = list(held | set(new_pairs))
            # Subscribe WS to any new pairs so they stream live candles
            if self._ws_feed:
                self._ws_feed.subscribe(self.active_pairs)

        # Fetch OHLCV for all pairs. WS feed is tried first; falls back to REST
        # for symbols not yet in the WS cache (e.g. freshly scanned pairs).
        ohlcv_cache = {}
        prices = {}
        all_symbols = list(set(self.active_pairs) | set(self.risk.positions.keys()))
        for symbol in all_symbols:
            df_raw = None
            if self._ws_feed:
                df_raw = self._ws_feed.get_ohlcv(symbol, limit=Config.CANDLE_LOOKBACK)
            if df_raw is None:
                df_raw = self.exchange.get_ohlcv(symbol, Config.TIMEFRAME, limit=Config.CANDLE_LOOKBACK)
            if df_raw is not None and len(df_raw) >= 2:
                ohlcv_cache[symbol] = df_raw
                prices[symbol] = float(df_raw.iloc[-1]["close"])

        # CDN ban detection: if all OHLCV fetches failed, pause to let ban expire.
        # Skip during first 5 cycles — WebSocket cache may not have 2+ candles yet.
        # Also skip if WebSocket is connected — data shortage means candle history is
        # still accumulating, not a CDN ban.
        if all_symbols and not prices:
            if self.cycle_count <= 5:
                logger.info(f"[WARMUP] No OHLCV data yet (cycle {self.cycle_count}/5), waiting for WebSocket cache...")
                return
            if self._ws_feed and self._ws_feed.is_connected:
                logger.info("[WARMUP] WebSocket connected, waiting for candle history to accumulate...")
                return
            self._empty_price_cycles += 1
            if self._empty_price_cycles >= 3:
                self.ban_mode = True
                self.ban_mode_until = time.time() + 600
                self._empty_price_cycles = 0
                logger.warning("[BAN MODE] All OHLCV fetches failed 3 cycles — CDN ban detected, rotating VPN and pausing 10 min")
                _rotate_vpn()
                notifier.notify_ban_mode(10)
            return
        self._empty_price_cycles = 0

        # Early exit check — momentum reversal while in profit
        for symbol, pos in list(self.risk.positions.items()):
            price = prices.get(symbol)
            df_check = ohlcv_cache.get(symbol)
            if not price or df_check is None:
                continue
            try:
                df_check = add_all_indicators(df_check)
                if pos.should_exit_early(price, df_check):
                    logger.info(f"[EARLY EXIT] {symbol} — momentum reversal at {pos.pnl_percent(price):.1f}% profit")
                    if pos.side == "long":
                        order = self.exchange.close_long(symbol, pos.amount)
                    else:
                        order = self.exchange.close_short(symbol, pos.amount)
                    fill_price = self._extract_fill_price(order, price)
                    self.risk.close_position(symbol, fill_price, "early_exit")
                    self.exchange.cancel_open_orders(symbol)
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "early_exit")
            except Exception as e:
                logger.debug(f"Early exit check failed for {symbol}: {e}")

        # Check exit conditions for open positions
        to_close = self.risk.check_positions(prices)
        for symbol, reason in to_close:
            price = prices.get(symbol)
            if price:
                pos = self.risk.positions.get(symbol)
                if pos:
                    if reason == "partial_tp":
                        half = self.risk.partial_close_position(symbol, price)
                        if half:
                            if pos.side == "long":
                                order = self.exchange.close_long(symbol, half)
                            else:
                                order = self.exchange.close_short(symbol, half)
                            fill_price = self._extract_fill_price(order, price)
                            self.exchange.cancel_open_orders(symbol)
                            notifier.notify_partial_tp(symbol, pos.side, fill_price, pos.pnl_usdt(fill_price) / 2, pos.pnl_percent(fill_price))
                            remaining_pos = self.risk.positions.get(symbol)
                            if remaining_pos:
                                self.exchange.place_sl_tp(symbol, remaining_pos.side, remaining_pos.amount, remaining_pos.stop_loss, remaining_pos.stop_loss * (1.06 if remaining_pos.side == "long" else 0.94))
                    else:
                        if pos.side == "long":
                            order = self.exchange.close_long(symbol, pos.amount)
                        else:
                            order = self.exchange.close_short(symbol, pos.amount)
                        fill_price = self._extract_fill_price(order, price)
                        notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), reason)
                        self.risk.close_position(symbol, fill_price, reason)
                        self.exchange.cancel_open_orders(symbol)

        # Check for new entry signals
        available = self.exchange.get_balance(Config.BASE_CURRENCY)     # free balance for trade sizing
        margin_in_use = sum(pos.margin for pos in self.risk.positions.values())
        real_balance = available + margin_in_use                        # true equity for drawdown tracking
        self.risk.update_peak_balance(real_balance)

        for symbol in self.active_pairs:
            if symbol in self.risk.positions:
                continue

            if not self.risk.can_open_trade(real_balance):
                break

            if symbol not in self._leverage_set:
                self.exchange.ensure_leverage(symbol)
                self._leverage_set.add(symbol)

            df = ohlcv_cache.get(symbol)
            if df is None or len(df) < 50:
                logger.warning(f"Not enough data for {symbol}, skipping.")
                continue

            df = add_all_indicators(df)
            if len(df) < 14:
                continue

            try:
                atr_val = float(df.iloc[-1]["atr"])
                if atr_val != atr_val:  # NaN check
                    atr_val = 0.0
            except (KeyError, ValueError, TypeError):
                atr_val = 0.0

            # Two-pass signal: technicals first, order book only on live signal
            try:
                signal = self.strategy_fn(df, None)
            except TypeError:
                signal = self.strategy_fn(df)

            # If technicals fire, fetch order book for confirmation
            if signal.signal != Signal.HOLD:
                ob = self.exchange.get_order_book(symbol)
                if ob is not None:
                    try:
                        signal = self.strategy_fn(df, ob)
                    except TypeError:
                        pass  # strategy doesn't accept orderbook
                    logger.info(f"[OB] {symbol} imb={ob.get('imbalance', 0):+.2f} spread={ob.get('spread_pct', 0):.3f}% walls=B{len(ob.get('bid_walls', []))}A{len(ob.get('ask_walls', []))}")

            if signal.signal != Signal.HOLD and signal.strength < Config.SCALP_MIN_STRENGTH:
                logger.debug(f"Signal too weak for {symbol}: {signal.strength:.2f}, skipping")
                continue

            price = prices.get(symbol, df.iloc[-1]["close"])
            margin = self.risk.calculate_margin(available)

            if signal.signal == Signal.BUY:
                if margin > available:
                    logger.warning(f"Insufficient balance for {symbol}: need {margin:.2f}, have {available:.2f}")
                    continue
                order = self.exchange.open_long(symbol, margin, price)
                if order:
                    fill_price = self._extract_fill_price(order, price)
                    self.risk.open_position(symbol, fill_price, margin, side="long", atr=atr_val)
                    pos = self.risk.positions[symbol]
                    fill_amount = self._extract_fill_amount(order, pos.amount)
                    pos.amount = fill_amount
                    sl_tp = self.exchange.place_sl_tp(symbol, "long", fill_amount, pos.stop_loss, pos.take_profit)
                    pos.sl_order_id = sl_tp.get("sl_order_id")
                    pos.tp_order_id = sl_tp.get("tp_order_id")
                    if not pos.sl_order_id:
                        logger.error(f"[SAFETY] SL failed for LONG {symbol} — closing position immediately")
                        self.exchange.close_long(symbol, fill_amount)
                        self.exchange.cancel_open_orders(symbol)
                        self.risk.close_position(symbol, fill_price, "sl_failed")
                        continue
                    available -= margin
                    logger.info(f"LONG ENTRY: {symbol} | Fill: {fill_price:.4f} | {signal.reason} | Strength: {signal.strength:.2f}")
                    notifier.notify_entry(symbol, "long", fill_price, margin, pos.stop_loss, pos.take_profit, signal.strength, signal.reason)

            elif signal.signal == Signal.SELL:
                if margin > available:
                    logger.warning(f"Insufficient balance for {symbol}: need {margin:.2f}, have {available:.2f}")
                    continue
                order = self.exchange.open_short(symbol, margin, price)
                if order:
                    fill_price = self._extract_fill_price(order, price)
                    self.risk.open_position(symbol, fill_price, margin, side="short", atr=atr_val)
                    pos = self.risk.positions[symbol]
                    fill_amount = self._extract_fill_amount(order, pos.amount)
                    pos.amount = fill_amount
                    sl_tp = self.exchange.place_sl_tp(symbol, "short", fill_amount, pos.stop_loss, pos.take_profit)
                    pos.sl_order_id = sl_tp.get("sl_order_id")
                    pos.tp_order_id = sl_tp.get("tp_order_id")
                    if not pos.sl_order_id:
                        logger.error(f"[SAFETY] SL failed for SHORT {symbol} — closing position immediately")
                        self.exchange.close_short(symbol, fill_amount)
                        self.exchange.cancel_open_orders(symbol)
                        self.risk.close_position(symbol, fill_price, "sl_failed")
                        continue
                    available -= margin
                    logger.info(f"SHORT ENTRY: {symbol} | Fill: {fill_price:.4f} | {signal.reason} | Strength: {signal.strength:.2f}")
                    notifier.notify_entry(symbol, "short", fill_price, margin, pos.stop_loss, pos.take_profit, signal.strength, signal.reason)

        if self.cycle_count % 10 == 0:
            self.risk.print_stats(real_balance)

    def _extract_fill_price(self, order: dict, fallback: float) -> float:
        """Extract actual fill price from exchange order response. Falls back to ticker price."""
        if not order:
            return fallback
        fill = order.get("average") or order.get("price")
        try:
            fill = float(fill)
            if fill > 0:
                return fill
        except (TypeError, ValueError):
            pass
        return fallback

    def _extract_fill_amount(self, order: dict, fallback: float) -> float:
        """Extract actual filled amount from exchange order response. Falls back to calculated amount."""
        if not order:
            return fallback
        filled = order.get("filled") or order.get("amount")
        try:
            filled = float(filled)
            if filled > 0:
                return filled
        except (TypeError, ValueError):
            pass
        return fallback

    def _shutdown(self):
        if self._ws_feed:
            self._ws_feed.stop()
        balance = self.exchange.get_balance(Config.BASE_CURRENCY)
        logger.info(f"Shutting down. Open positions: {list(self.risk.positions.keys())}")
        self.risk.print_stats(balance)
        notifier.notify_shutdown(list(self.risk.positions.keys()), balance)
