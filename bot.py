import time
import datetime
import subprocess
from collections import deque
from config import Config
from exchange import Exchange
from indicators import add_all_indicators
from risk_manager import RiskManager
from strategy_slot import StrategySlot
from strategies import STRATEGIES, Signal, TradeSignal
from scanner import scan_top_gainers, volatility_scan, start_background_scan, get_scan_result
from logger import setup_logger
from ws_feed import WSDataFeed
import notifier

logger = setup_logger()


def _extract_strategy_name(reason: str) -> str:
    """Derive strategy key from signal reason string for time exit lookup."""
    r = reason.lower()
    if "kc squeeze" in r or "keltner" in r:
        return "keltner_squeeze"
    if "bb" in r or "mean reversion" in r:
        return "bb_mean_reversion"
    if "trend pullback" in r:
        return "trend_pullback"
    if "trend scalp" in r or "trend_scalp" in r:
        return "trend_scalp"
    if "momentum cont" in r or "momentum_continuation" in r:
        return "momentum_continuation"
    if "vwap reversion" in r or "vwap_reversion" in r:
        return "vwap_reversion"
    if "confluence pullback" in r:
        return "htf_confluence_pullback"
    if "confluence vwap" in r:
        return "htf_confluence_vwap"
    return ""


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
        self.strategy_fn = STRATEGIES.get(Config.STRATEGY, STRATEGIES["adaptive"])
        self.running = False
        self.cycle_count = 0
        self.active_pairs = Config.TRADING_PAIRS[:]
        self._leverage_set: set = set()  # track symbols that already have leverage configured
        self.consecutive_errors = 0
        self.ban_mode = False
        self.ban_mode_until = 0
        self._ws_feed: WSDataFeed | None = None
        self._empty_price_cycles = 0  # consecutive cycles with no ticker data (CDN ban detection)
        self._loss_streak = 0    # consecutive losses for streak-based sizing
        self._pair_cooldown: dict[str, float] = {}  # symbol -> timestamp when cooldown expires
        self._pair_loss_streak: dict[str, int] = {}  # symbol -> consecutive loss count
        self._last_entry_time: float = 0  # global cooldown between any new entry
        self._trade_results: deque = deque(self.risk.trade_results, maxlen=6)  # rolling window of last 6 trade results (True=win, False=loss)
        self._regime_pause_until: float = 0  # timestamp when regime pause expires
        self._htf_cache: dict[str, tuple] = {}  # symbol -> (DataFrame, fetch_timestamp) for 1h candles
        self._funding_cache: dict[str, tuple] = {}  # symbol -> (data, fetch_timestamp) for funding rates

        # Strategy slots framework — independent trading units (additive, main loop still uses self.risk)
        self.slots = [
            StrategySlot(
                slot_id="5m_scalp",
                strategy_name="confluence",
                timeframe="5m",
                max_positions=2,
                capital_pct=0.4,  # 40% of balance
            ),
            StrategySlot(
                slot_id="1h_momentum",
                strategy_name="htf_momentum",
                timeframe="1h",
                max_positions=2,
                capital_pct=0.3,  # 30% of balance
                paper_mode=True,  # Paper mode first — validate before going live
            ),
            StrategySlot(
                slot_id="5m_mean_revert",
                strategy_name="bb_reversion",
                timeframe="5m",
                max_positions=1,      # conservative — mean reversion is riskier
                capital_pct=0.3,      # 30% allocation (less than momentum/scalp)
                paper_mode=True,      # Paper mode first
            ),
        ]

    def _fetch_htf_data(self, symbol: str):
        """Fetch 1h candle data with 5-minute cache. Returns indicator-enriched DataFrame or None."""
        cached = self._htf_cache.get(symbol)
        if cached:
            df, ts = cached
            if time.time() - ts < 300:  # 5 min cache
                return df
        try:
            df_raw = self.exchange.get_ohlcv(symbol, "1h", limit=100)
            if df_raw is not None and len(df_raw) >= 30:
                df = add_all_indicators(df_raw)
                self._htf_cache[symbol] = (df, time.time())
                return df
        except Exception as e:
            logger.debug(f"[HTF] Failed to fetch 1h data for {symbol}: {e}")
        return cached[0] if cached else None  # return stale cache over nothing

    def _fetch_funding_rate(self, symbol: str) -> dict | None:
        """Fetch funding rate with 4-hour cache. Returns stale cache on REST failure."""
        cached = self._funding_cache.get(symbol)
        if cached:
            data, ts = cached
            if time.time() - ts < 14400:  # 4 hr cache
                return data
        data = self.exchange.get_funding_rate(symbol)
        if data is not None:
            self._funding_cache[symbol] = (data, time.time())
            return data
        return cached[0] if cached else None

    def _compute_confidence(self, direction: str, df, ob: dict | None, htf_df=None,
                            cvd_data: dict | None = None, hurst_val: float = 0.5,
                            funding_data: dict | None = None,
                            strategy: str = "") -> tuple[int, list[str]]:
        """Count independent confirmation layers for the signal direction.
        Returns (count, list_of_confirmed_layers).
        Layers: HTF trend, VWAP position, CVD direction, Hurst regime, Funding rate, OB imbalance."""
        confirmed = []
        last = df.iloc[-1]
        is_long = direction == "long"

        # 1. HTF trend — 1h EMA slope confirms direction
        if htf_df is not None and len(htf_df) >= 2:
            htf_last = htf_df.iloc[-1]
            htf_ema50 = htf_last.get("ema_50", 0)
            htf_ema50_prev = htf_df.iloc[-2].get("ema_50", 0)
            if htf_ema50 and htf_ema50_prev:
                htf_slope = (htf_ema50 - htf_ema50_prev) / htf_ema50_prev if htf_ema50_prev else 0
                if (is_long and htf_slope > 0) or (not is_long and htf_slope < 0):
                    confirmed.append("htf_trend")

        # 2. VWAP position — price above VWAP for longs, below for shorts
        vwap_val = last.get("vwap", 0)
        close_val = last.get("close", 0)
        if vwap_val and close_val:
            if (is_long and close_val > vwap_val) or (not is_long and close_val < vwap_val):
                confirmed.append("vwap_pos")

        # 3. CVD direction — buying pressure for longs, selling for shorts
        #    Divergence upgrades the label but doesn't add a second count
        if cvd_data:
            cvd_slope = cvd_data.get("cvd_slope", 0)
            div = cvd_data.get("divergence")
            if (is_long and div == "bullish") or (not is_long and div == "bearish"):
                confirmed.append("cvd_divergence")  # strongest form
            elif (is_long and cvd_slope > 0) or (not is_long and cvd_slope < 0):
                confirmed.append("cvd")

        # 4. Hurst regime match — must align with strategy type
        reversion_strats = {"vwap_reversion", "htf_confluence_vwap", "bb_mean_reversion"}
        trend_strats = {"momentum_continuation", "trend_pullback", "keltner_squeeze", "htf_confluence_pullback"}
        if hurst_val and not (hurst_val != hurst_val):  # not NaN
            if hurst_val > 0.55 and (not strategy or strategy in trend_strats):
                confirmed.append("hurst_trend")
            elif hurst_val < 0.45 and (not strategy or strategy in reversion_strats):
                confirmed.append("hurst_revert")

        # 5. Funding rate — contrarian signal
        if funding_data:
            fsig = funding_data.get("signal")
            if (is_long and fsig == "long") or (not is_long and fsig == "short"):
                confirmed.append("funding")

        # 6. Order book imbalance — bid-heavy for longs, ask-heavy for shorts
        if ob:
            imb = ob.get("imbalance", 0)
            if (is_long and imb > 0.1) or (not is_long and imb < -0.1):
                confirmed.append("ob_imbalance")

        logger.info(f"[ENSEMBLE] {direction} confidence={len(confirmed)}/{6} layers={','.join(confirmed) or 'none'}")
        return len(confirmed), confirmed

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
            logger.info(f"Volume scanner ON — top {Config.SCANNER_TOP_N} pairs, min vol ${Config.SCANNER_MIN_VOLUME:,.0f}, refresh every {Config.SCANNER_REFRESH_CYCLES} cycles (~{Config.SCANNER_REFRESH_CYCLES * Config.LOOP_INTERVAL}s)")
            if not self.active_pairs:
                logger.info("[SCANNER] No static pairs configured — running initial scan synchronously...")
                for _scan_attempt in range(3):
                    initial_pairs = volatility_scan(self.exchange.client)
                    if initial_pairs:
                        self.active_pairs = initial_pairs
                        logger.info(f"[SCANNER] Initial pairs: {', '.join(self.active_pairs)}")
                        break
                    logger.warning(f"[SCANNER] Initial scan attempt {_scan_attempt+1}/3 failed, retrying in 15s...")
                    time.sleep(15)
                if not self.active_pairs:
                    logger.error("[SCANNER] All initial scan attempts failed — bot will retry via background scanner")
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
                # Sync ALL open positions — don't filter by active_pairs
                # (positions may exist on pairs not yet in the scanner/config list)
                if open_pos:
                    self.risk.sync_positions(open_pos, current_cycle=self.cycle_count)
                    logger.info(f"Synced {len(open_pos)} open position(s) from exchange")
                    # Place exchange SL/TP for synced positions (they have sl_order_id=None)
                    for sym, pos in self.risk.positions.items():
                        if pos.sl_order_id is None:
                            self.exchange.cancel_open_orders(sym)
                            sl_tp = self.exchange.place_sl_tp(sym, pos.side, pos.amount, pos.stop_loss, pos.take_profit)
                            pos.sl_order_id = sl_tp.get("sl_order_id")
                            pos.tp_order_id = sl_tp.get("tp_order_id")
                            if pos.sl_order_id:
                                logger.info(f"[SYNC] Placed exchange SL/TP for {sym} — SL@{pos.stop_loss:.4f} TP@{pos.take_profit:.4f}")
                            else:
                                pos.sl_order_id = "software"
                                logger.warning(f"[SYNC] Exchange SL failed for {sym} — using software SL@{pos.stop_loss:.4f}")
                    # Add synced symbols to active pairs so they get monitored
                    synced_symbols = {p["symbol"] for p in open_pos}
                    new_symbols = synced_symbols - set(self.active_pairs)
                    if new_symbols:
                        self.active_pairs = list(set(self.active_pairs) | synced_symbols)
                        logger.info(f"[SYNC] Added {len(new_symbols)} symbol(s) to active pairs: {', '.join(new_symbols)}")
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

        # Refresh volatility scan periodically (non-blocking background thread)
        if Config.SCANNER_ENABLED and self.cycle_count % Config.SCANNER_REFRESH_CYCLES == 0:
            logger.info("[SCANNER] Launching background volatility scan...")
            start_background_scan()  # uses its own dedicated ccxt client

        # Pick up background scan results when ready
        if Config.SCANNER_ENABLED:
            scan_result = get_scan_result()
            if scan_result:
                held = set(self.risk.positions.keys())
                self.active_pairs = list(held | set(scan_result))
                # Subscribe WS to any new pairs so they stream live candles
                if self._ws_feed:
                    self._ws_feed.subscribe(self.active_pairs)
                logger.info(f"[SCANNER] Updated pairs: {', '.join(self.active_pairs)}")

        # Fetch OHLCV for all pairs. WS feed is tried first; falls back to REST
        # for symbols not yet in the WS cache (e.g. freshly scanned pairs).
        ohlcv_cache = {}
        prices = {}
        all_symbols = list(set(self.active_pairs) | set(self.risk.positions.keys()))
        for symbol in all_symbols:
            df_raw = None
            if self._ws_feed and not self._ws_feed.is_stale(symbol):
                df_raw = self._ws_feed.get_ohlcv(symbol, limit=Config.CANDLE_LOOKBACK)
            if df_raw is None:
                df_raw = self.exchange.get_ohlcv(symbol, Config.TIMEFRAME, limit=Config.CANDLE_LOOKBACK)
                time.sleep(0.5)  # throttle REST fallback to avoid CDN ban
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
                    if not order:
                        logger.error(f"[EARLY EXIT] Close order failed for {symbol} — position still open on exchange")
                        continue
                    fill_price = self._extract_fill_price(order, price, is_exit=True)
                    self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                    self.risk.close_position(symbol, fill_price, "early_exit")
                    self.exchange.cancel_open_orders(symbol)
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "early_exit")
            except Exception as e:
                logger.debug(f"Early exit check failed for {symbol}: {e}")

        # Flat exit — cut indecisive positions after 20 min
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions:
                continue  # already closed by early_exit above
            price = prices.get(symbol)
            if not price:
                continue
            if pos.should_flat_exit(self.cycle_count, price):
                roi = pos.pnl_percent(price)
                cycles_held = self.cycle_count - pos.entry_cycle
                held_min = cycles_held * Config.LOOP_INTERVAL / 60
                logger.info(f"[FLAT EXIT] {symbol} — {roi:.1f}% ROI after {held_min:.0f}min (no momentum)")
                if pos.side == "long":
                    order = self.exchange.close_long(symbol, pos.amount)
                else:
                    order = self.exchange.close_short(symbol, pos.amount)
                if not order:
                    logger.error(f"[FLAT EXIT] Close order failed for {symbol}")
                    continue
                fill_price = self._extract_fill_price(order, price, is_exit=True)
                self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                self.risk.close_position(symbol, fill_price, "flat_exit")
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "flat_exit")

        # Adverse exit — bail out of wrong-direction trades early
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions:
                continue  # already closed by earlier exit this cycle
            price = prices.get(symbol)
            if not price:
                continue
            if pos.should_adverse_exit(self.cycle_count, price):
                cycles_held = self.cycle_count - pos.entry_cycle
                held_min = cycles_held * Config.LOOP_INTERVAL / 60
                roi = pos.pnl_percent(price)
                logger.info(f"[ADVERSE EXIT] {symbol} — {roi:.1f}% ROI after {held_min:.0f}min")
                if pos.side == "long":
                    order = self.exchange.close_long(symbol, pos.amount)
                else:
                    order = self.exchange.close_short(symbol, pos.amount)
                if not order:
                    logger.error(f"[ADVERSE EXIT] Close order failed for {symbol}")
                    continue
                fill_price = self._extract_fill_price(order, price, is_exit=True)
                self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                self.risk.close_position(symbol, fill_price, "adverse_exit")
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "adverse_exit")
                continue

        # Check if exchange already closed positions (exchange SL/TP triggered)
        if Config.is_live() and self.risk.positions:
            self._sync_exchange_closes(prices)

        # Verify SL orders still active — re-place if cancelled (skip software-managed)
        for symbol, pos in list(self.risk.positions.items()):
            if pos.sl_order_id == "software":
                continue  # managed by bot's check_positions loop
            if pos.sl_order_id and not self.exchange.verify_sl_order(symbol, pos.sl_order_id):
                logger.warning(f"[SL CHECK] SL order missing for {symbol} — re-placing")
                self.exchange.cancel_open_orders(symbol)
                sl_tp = self.exchange.place_sl_tp(symbol, pos.side, pos.amount, pos.stop_loss, pos.take_profit or pos.entry_price)
                pos.sl_order_id = sl_tp.get("sl_order_id")
                pos.tp_order_id = sl_tp.get("tp_order_id")
                if not pos.sl_order_id:
                    # Fall back to software SL/TP — preserve existing SL/TP values
                    # (may be ATR-based or breakeven-adjusted, don't overwrite with Config %)
                    pos.sl_order_id = "software"
                    logger.warning(f"[SL FALLBACK] Re-place failed for {symbol} — switching to software SL@{pos.stop_loss:.4f} TP@{pos.take_profit:.4f}")

        # Time-based exit — close stale positions (strategy-specific thresholds)
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions:
                continue  # already closed by early_exit/flat_exit this cycle
            price = prices.get(symbol)
            if not price:
                continue
            should_exit, is_hard = pos.should_time_exit(self.cycle_count, current_price=price)
            if should_exit:
                pnl_pct = pos.pnl_percent(price)
                # Soft exit: only if in the red. Hard exit: unconditional.
                if is_hard or pnl_pct < 0:
                    cycles_held = self.cycle_count - pos.entry_cycle
                    held_min = cycles_held * Config.LOOP_INTERVAL / 60
                    exit_type = "hard_time_exit" if is_hard else "time_exit"
                    logger.info(f"[{exit_type.upper()}] {symbol} — {pnl_pct:.1f}% PnL after {held_min:.0f}min (strat={pos.strategy or 'default'})")
                    if pos.side == "long":
                        order = self.exchange.close_long(symbol, pos.amount)
                    else:
                        order = self.exchange.close_short(symbol, pos.amount)
                    if not order:
                        logger.error(f"[{exit_type.upper()}] Close order failed for {symbol} — position still open on exchange")
                        continue
                    fill_price = self._extract_fill_price(order, price, is_exit=True)
                    self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                    self.risk.close_position(symbol, fill_price, exit_type)
                    self.exchange.cancel_open_orders(symbol)
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), exit_type)

        # Break-even and trailing stop updates
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions:
                continue  # already closed earlier this cycle
            price = prices.get(symbol)
            if not price:
                continue
            old_sl = pos.stop_loss
            pos.check_breakeven(price)
            pos.update_trailing_stop(price)
            # If SL ratcheted, update the exchange order
            if pos.stop_loss != old_sl and pos.sl_order_id and pos.sl_order_id != "software":
                self.exchange.cancel_open_orders(symbol)
                tp_price = pos.take_profit if pos.take_profit is not None else None
                if tp_price is not None:
                    sl_tp = self.exchange.place_sl_tp(symbol, pos.side, pos.amount, pos.stop_loss, tp_price)
                else:
                    # Partial-close mode: no TP, place SL only
                    sl_tp = self.exchange.place_sl_tp(symbol, pos.side, pos.amount, pos.stop_loss, pos.entry_price)
                    # We don't actually want a TP at entry, so cancel the TP if placed
                    if sl_tp.get("tp_order_id"):
                        try:
                            self.exchange.client.cancel_order(sl_tp["tp_order_id"], symbol)
                        except Exception:
                            pass
                        sl_tp["tp_order_id"] = None
                pos.sl_order_id = sl_tp.get("sl_order_id") or "software"
                pos.tp_order_id = sl_tp.get("tp_order_id")
                logger.info(f"[BREAKEVEN] {symbol} exchange SL updated to {pos.stop_loss:.4f}")

        # Check exit conditions for open positions
        to_close = self.risk.check_positions(prices)
        for symbol, reason in to_close:
            price = prices.get(symbol)
            if price:
                pos = self.risk.positions.get(symbol)
                if pos:
                    if pos.side == "long":
                        order = self.exchange.close_long(symbol, pos.amount)
                    else:
                        order = self.exchange.close_short(symbol, pos.amount)
                    if not order:
                        logger.error(f"[SOFTWARE SL/TP] Close order failed for {symbol} — position still open on exchange")
                        continue
                    fill_price = self._extract_fill_price(order, price, is_exit=True)
                    self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), reason)
                    self.risk.close_position(symbol, fill_price, reason)
                    self.exchange.cancel_open_orders(symbol)

        # Check for new entry signals
        available = self.exchange.get_balance(Config.BASE_CURRENCY)     # free balance for trade sizing
        margin_in_use = sum(pos.margin for pos in self.risk.positions.values())
        real_balance = available + margin_in_use                        # true equity for drawdown tracking
        self.risk.update_peak_balance(real_balance)

        # Regime filter — pause all entries after consecutive losses
        if time.time() < self._regime_pause_until:
            remaining = int(self._regime_pause_until - time.time())
            if self.cycle_count % 20 == 0:  # log every ~5 min
                logger.info(f"[REGIME] Entries paused — {remaining}s remaining")
            return  # skip entire entry section, but exits still processed above

        # Pre-compute indicators for entry signals
        indicator_cache = {}
        for sym in self.active_pairs:
            if sym in self.risk.positions:
                continue
            df_raw = ohlcv_cache.get(sym)
            if df_raw is None or len(df_raw) < 50:
                continue
            df_ind = add_all_indicators(df_raw)
            if len(df_ind) < 14:
                continue
            indicator_cache[sym] = df_ind

        for symbol in self.active_pairs:
            if symbol in self.risk.positions:
                continue
            # Global cooldown: 30s between any new entry (continue, not break)
            if time.time() - self._last_entry_time < 30:
                continue
            # Per-pair cooldown: skip pair after losses
            if symbol in self._pair_cooldown and time.time() < self._pair_cooldown[symbol]:
                continue

            if not self.risk.can_open_trade(real_balance):
                break

            if symbol not in self._leverage_set:
                self.exchange.ensure_leverage(symbol)
                self._leverage_set.add(symbol)

            df = indicator_cache.get(symbol)
            if df is None:
                df_raw = ohlcv_cache.get(symbol)
                if df_raw is None or len(df_raw) < 50:
                    logger.warning(f"Not enough data for {symbol}, skipping.")
                    continue
                df = add_all_indicators(df_raw)
                if len(df) < 14:
                    continue

            try:
                atr_val = float(df.iloc[-1]["atr"])
                if atr_val != atr_val:  # NaN check
                    atr_val = 0.0
            except (KeyError, ValueError, TypeError):
                atr_val = 0.0

            # Determine volatility regime (no extreme skip in v4.0)
            atr_pct_val = float(df.iloc[-1].get("atr_pct", 50))
            if atr_pct_val > 80:
                regime = "high"
            elif atr_pct_val > 25:
                regime = "medium"
            else:
                regime = "low"

            # Fetch orderbook and HTF data for strategy confirmation
            ob = self.exchange.get_order_book(symbol)
            htf_df = self._fetch_htf_data(symbol)
            try:
                signal = self.strategy_fn(df, ob, htf_df=htf_df)
            except TypeError:
                signal = self.strategy_fn(df, ob)

            if signal.signal == Signal.HOLD:
                logger.debug(f"[HOLD] {symbol} — {signal.reason}")

            if signal.signal != Signal.HOLD and ob is not None:
                logger.info(f"[OB] {symbol} imb={ob.get('imbalance', 0):+.2f} spread={ob.get('spread_pct', 0):.3f}% walls=B{len(ob.get('bid_walls', []))}A{len(ob.get('ask_walls', []))}")

            # Short penalty: -0.04 strength (reduced from -0.08 — was blocking market-open shorts)
            if signal.signal == Signal.SELL:
                signal = TradeSignal(signal.signal, signal.reason, signal.strength - 0.04)

            # Min strength check
            if signal.signal != Signal.HOLD and signal.strength < Config.SCALP_MIN_STRENGTH:
                logger.debug(f"Signal too weak for {symbol}: {signal.strength:.2f}, skipping")
                continue

            price = prices.get(symbol, df.iloc[-1]["close"])

            if signal.signal in (Signal.BUY, Signal.SELL):
                direction = "long" if signal.signal == Signal.BUY else "short"

                # Fetch CVD and funding rate for ensemble confidence
                cvd_data = self.exchange.get_cvd(symbol)
                funding_data = self._fetch_funding_rate(symbol)
                hurst_val = float(df.iloc[-1].get("hurst", 0.5))
                if hurst_val != hurst_val:  # NaN check
                    hurst_val = 0.5

                if cvd_data:
                    logger.info(f"[CVD] {symbol} cvd={cvd_data['cvd']:.0f} slope={cvd_data['cvd_slope']:.0f} div={cvd_data.get('divergence', 'none')}")
                if funding_data:
                    logger.info(f"[FUNDING] {symbol} rate={funding_data['rate']:.6f} signal={funding_data.get('signal', 'none')}")
                logger.info(f"[HURST] {symbol} H={hurst_val:.3f}")

                # Ensemble confidence gate
                strat_name = _extract_strategy_name(signal.reason)
                confidence, layers = self._compute_confidence(
                    direction, df, ob, htf_df=htf_df,
                    cvd_data=cvd_data, hurst_val=hurst_val, funding_data=funding_data,
                    strategy=strat_name
                )
                # Strategy-aware confidence thresholds
                # Start conservative: all at 3. Lower reversion to 2 after proving adverse_exit works.
                CONFIDENCE_THRESHOLDS = {
                    "htf_confluence_pullback": 3,
                    "htf_confluence_vwap": 3,
                    "vwap_reversion": 3,
                    "bb_mean_reversion": 3,
                    "momentum_continuation": 3,
                    "trend_pullback": 3,
                    "keltner_squeeze": 3,
                }
                min_confidence = CONFIDENCE_THRESHOLDS.get(strat_name, 3)

                if confidence < min_confidence:
                    logger.info(
                        f"[ENSEMBLE SKIP] {symbol} {direction} — confidence {confidence}/{min_confidence} "
                        f"too low for {strat_name}, need {min_confidence}+"
                    )
                    continue

                # Apply funding rate strength modifier
                if funding_data and funding_data.get("strength_mod"):
                    signal = TradeSignal(signal.signal, signal.reason, signal.strength + funding_data["strength_mod"])

                # Candle-boundary entry bias: prefer entries near 5m candle opens
                # Research: +0.58bps at candle boundaries (t-stat > 9)
                now_min = datetime.datetime.utcnow().minute
                candle_offset = now_min % 5  # 0 = candle just opened, 4 = about to close
                if candle_offset >= 3:  # Last 2 minutes of candle — skip, wait for next open
                    logger.debug(f"[TIMING] {symbol} — skipping entry, {5-candle_offset}min to next candle open")
                    continue

                # Kelly-aware position sizing (uses $2 min margin during bootstrap)
                margin = self.risk.calculate_kelly_margin(available, confidence=confidence)

                # Weekend sizing boost: +85-92% weekend returns (p < 0.001)
                if datetime.datetime.utcnow().weekday() in (5, 6):  # Saturday=5, Sunday=6
                    margin = min(margin * 1.3, 10.0)  # cap at $10 (MAX_TRADE_MARGIN)

                if margin > available:
                    logger.warning(f"Insufficient balance for {symbol}: need {margin:.2f}, have {available:.2f}")
                    continue

                # Check if margin meets exchange minimum for this symbol
                try:
                    market = self.exchange.client.market(symbol)
                    min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
                    if min_amount and price > 0:
                        min_notional = min_amount * price
                        min_margin_needed = min_notional / Config.LEVERAGE
                        if margin < min_margin_needed:
                            logger.debug(f"[SKIP] {symbol} — margin ${margin:.2f} < min ${min_margin_needed:.2f} for {min_amount} qty")
                            continue
                except Exception:
                    pass  # If check fails, let the order attempt proceed

                order = self.exchange.open_long(symbol, margin, price) if direction == "long" else self.exchange.open_short(symbol, margin, price)
                if order:
                    fill_price = self._extract_fill_price(order, price)
                    self.risk.open_position(symbol, fill_price, margin, side=direction, atr=atr_val, regime=regime, cycle=self.cycle_count, strategy=strat_name)
                    pos = self.risk.positions[symbol]
                    fill_amount = self._extract_fill_amount(order, pos.amount)
                    pos.amount = fill_amount
                    pos.entry_strength = signal.strength
                    pos.confidence = confidence
                    pos.ensemble_layers = ",".join(layers)
                    sl_tp = self.exchange.place_sl_tp(symbol, direction, fill_amount, pos.stop_loss, pos.take_profit)
                    pos.sl_order_id = sl_tp.get("sl_order_id")
                    pos.tp_order_id = sl_tp.get("tp_order_id")
                    if not pos.sl_order_id:
                        pos.sl_order_id = "software"
                        logger.warning(f"[SL FALLBACK] Exchange SL failed for {direction.upper()} {symbol} — using software SL@{pos.stop_loss:.4f} TP@{pos.take_profit:.4f}")
                    available -= margin
                    self._last_entry_time = time.time()
                    logger.info(f"[ENTRY] {direction.upper()} {symbol} | Fill: {fill_price:.4f} | Margin: ${margin:.2f} | Conf: {confidence}/6 | {signal.reason} | Strength: {signal.strength:.2f}")
                    notifier.notify_entry(symbol, direction, fill_price, margin, pos.stop_loss, pos.take_profit, signal.strength, signal.reason)
                else:
                    logger.error(f"[ENTRY] Order FAILED for {direction.upper()} {symbol} — signal lost")

        if self.cycle_count % 10 == 0:
            self.risk.print_stats(real_balance)

        # Log slot status
        for slot in self.slots:
            s = slot.stats_summary()
            mode = "PAPER" if slot.paper_mode else "LIVE"
            status = "KILLED" if slot.is_killed else "ACTIVE" if slot.is_active else "DISABLED"
            logger.info(f"[SLOT] {slot.slot_id} ({mode}/{status}) | {s['trades']} trades | WR: {s['wr']}% | PnL: ${s['pnl']}")

    def _set_cooldown_if_loss(self, symbol: str, pnl_pct: float):
        """Set cooldown on a pair after loss: 2 min per loss, 10 min after 3 consecutive.
        Also tracks global loss streak for regime filter."""
        if pnl_pct < 0:
            # Per-pair cooldown
            self._pair_loss_streak[symbol] = self._pair_loss_streak.get(symbol, 0) + 1
            streak = self._pair_loss_streak[symbol]
            if streak >= 3:
                self._pair_cooldown[symbol] = time.time() + 7200  # 2 hr after 3 consecutive losses
                self._pair_loss_streak[symbol] = 0
                logger.info(f"[BLACKLIST] {symbol} blocked for 2 hours after {streak} consecutive losses")
            else:
                self._pair_cooldown[symbol] = time.time() + 120  # 2 min after any loss
                logger.info(f"[COOLDOWN] {symbol} blocked for 2 min (streak: {streak})")
            # Global regime filter: 4 of last 6 trades lost → 15 min pause
            self._trade_results.append(False)
            losses = sum(1 for r in self._trade_results if not r)
            if len(self._trade_results) >= 6 and losses >= 4:
                self._regime_pause_until = time.time() + 900  # 15 min pause
                logger.warning(f"[REGIME] Rolling window: {losses}/6 losses — pausing 15 min")
                notifier.notify_ban_mode(15)  # reuse ban notification for regime pause
                self._trade_results.clear()  # reset window after pause
            self._persist_trade_results()
        else:
            self._pair_loss_streak[symbol] = 0  # reset on win
            self._trade_results.append(True)  # record win in rolling window
            self._persist_trade_results()

    def _persist_trade_results(self):
        """Sync rolling trade results to risk manager for persistence."""
        self.risk.trade_results = list(self._trade_results)
        self.risk._save_state()

    def _sync_exchange_closes(self, prices: dict):
        """Detect positions closed by exchange SL/TP orders so we don't double-close."""
        try:
            exchange_positions = self.exchange.get_open_positions()
            if exchange_positions is None:
                return  # API failed, skip sync this cycle
            exchange_symbols = {p["symbol"] for p in exchange_positions}
            for symbol in list(self.risk.positions.keys()):
                if symbol not in exchange_symbols:
                    pos = self.risk.positions[symbol]
                    # Try to get actual fill price from recent trades
                    exit_price = prices.get(symbol, pos.entry_price)
                    try:
                        recent = self.exchange.client.fetch_my_trades(symbol, limit=5)
                        if recent:
                            last_trade = recent[-1]
                            fill = float(last_trade.get("price", 0))
                            if fill > 0:
                                exit_price = fill
                                logger.info(f"[SYNC] {symbol} real exit fill: {exit_price}")
                    except Exception:
                        pass
                    logger.info(f"[SYNC] {symbol} closed on exchange (SL/TP triggered) — removing from tracker")
                    self.exchange.cancel_open_orders(symbol)
                    self._set_cooldown_if_loss(symbol, pos.pnl_percent(exit_price))
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, exit_price, pos.pnl_usdt(exit_price), pos.pnl_percent(exit_price), "exchange_close")
                    self.risk.close_position(symbol, exit_price, "exchange_close")
        except Exception as e:
            logger.debug(f"Exchange position sync failed: {e}")

    def _extract_fill_price(self, order: dict, fallback: float, is_exit: bool = False) -> float:
        """Get real fill price from exchange.

        For ENTRIES: fetch position entryPrice (source of truth).
        For EXITS: fetch order fill or last trade (position is already closed).
        """
        symbol = order.get("symbol") if order else None
        if not symbol:
            return fallback

        time.sleep(1.5)  # let the order settle on exchange

        if is_exit:
            # --- EXIT path: position is closed, fetch fill from order or trades ---
            order_id = order.get("id") if order else None

            # 1. Try fetch_order to get the actual average fill price
            if order_id:
                try:
                    fetched = self.exchange.client.fetch_order(order_id, symbol)
                    avg = fetched.get("average") if fetched else None
                    if avg is not None:
                        avg = float(avg)
                        if avg > 0:
                            logger.info(f"[FILL] {symbol} exit fill (fetch_order): {avg}")
                            return avg
                except Exception as e:
                    logger.debug(f"[FILL] fetch_order failed for {symbol}: {e}")

            # 2. Try fetch_my_trades to get the last trade's fill price
            try:
                trades = self.exchange.client.fetch_my_trades(symbol, limit=1)
                if trades:
                    trade_price = float(trades[-1].get("price", 0))
                    if trade_price > 0:
                        logger.info(f"[FILL] {symbol} exit fill (last trade): {trade_price}")
                        return trade_price
            except Exception as e:
                logger.debug(f"[FILL] fetch_my_trades failed for {symbol}: {e}")

            # 3. Try order response average field directly
            if order:
                fill = order.get("average")
                try:
                    fill = float(fill)
                    if fill > 0:
                        logger.info(f"[FILL] {symbol} exit fill (order response): {fill}")
                        return fill
                except (TypeError, ValueError):
                    pass

            logger.warning(f"[FILL] {symbol} exit using fallback price: {fallback}")
            return fallback

        # --- ENTRY path: fetch position entryPrice (source of truth) ---
        try:
            positions = self.exchange.client.fetch_positions([symbol])
            for p in positions:
                if p.get("symbol") == symbol and float(p.get("contracts", 0)) > 0:
                    entry = float(p.get("entryPrice", 0))
                    if entry > 0:
                        logger.info(f"[FILL] {symbol} real entry price: {entry}")
                        return entry
        except Exception as e:
            logger.warning(f"[FILL] Could not fetch position for {symbol}: {e}")

        # Fallback: try order average
        if order:
            fill = order.get("average")
            try:
                fill = float(fill)
                if fill > 0:
                    return fill
            except (TypeError, ValueError):
                pass

        logger.warning(f"[FILL] {symbol} entry using fallback price: {fallback}")
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
