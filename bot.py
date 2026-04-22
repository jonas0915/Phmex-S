import signal
import time
import datetime
import subprocess
import os
import json
import threading
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
    if "l2 anticipation" in r:
        return "htf_l2_anticipation"
    if "confluence pullback" in r:
        return "htf_confluence_pullback"
    if "confluence vwap" in r:
        return "htf_confluence_vwap"
    if "liq_cascade" in r:
        return "liq_cascade"
    return ""


def _compute_today_net_pnl(closed_trades: list) -> float:
    """Sum today's net_pnl (or pnl_usdt fallback). Uses America/Los_Angeles day boundary."""
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    PT = ZoneInfo("America/Los_Angeles")
    today_str = _dt.now(PT).strftime("%Y-%m-%d")
    total = 0.0
    for t in closed_trades:
        closed_at = t.get("closed_at")
        if not closed_at:
            continue
        if _dt.fromtimestamp(closed_at, tz=PT).strftime("%Y-%m-%d") != today_str:
            continue
        net = t.get("net_pnl")
        if net is None:
            net = t.get("pnl_usdt", 0.0)
        total += float(net or 0.0)
    return total


def _should_halt_daily_loss(today_net: float, balance: float, threshold_pct: float = 3.0) -> bool:
    if balance <= 0:
        return False
    return today_net <= -(balance * threshold_pct / 100.0)


def _should_halt_consecutive_losses(loss_streak: int, threshold: int = 5) -> bool:
    return loss_streak >= threshold


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


def _rotate_vpn() -> bool:
    """Disconnect and reconnect ExpressVPN to a new server. Returns True if connected."""
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
        status_line = result.stdout.splitlines()[0] if result.stdout else "status unknown"
        logger.info(f"[VPN] {status_line}")
        connected = "Connected" in status_line or "connected" in status_line
        if not connected:
            logger.warning(f"[VPN] Rotation to {server} may have failed — status: {status_line}")
        return connected
    except Exception as e:
        logger.warning(f"[VPN] Rotation failed: {e}")
        return False


def _diagnose_connectivity() -> dict:
    """Quick connectivity diagnosis: network reachable? VPN connected?"""
    diag = {"network": "unknown", "vpn": "unknown"}
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "3", "8.8.8.8"],
            capture_output=True, timeout=5
        )
        diag["network"] = "ok" if result.returncode == 0 else "down"
    except Exception:
        diag["network"] = "down"
    try:
        result = subprocess.run(
            ["expressvpnctl", "status"],
            capture_output=True, text=True, timeout=5
        )
        status = result.stdout.strip() if result.stdout else ""
        if "Connected" in status or "connected" in status:
            diag["vpn"] = "connected"
        elif "Not connected" in status or "not connected" in status:
            diag["vpn"] = "disconnected"
        else:
            diag["vpn"] = status[:50] if status else "unknown"
    except Exception:
        diag["vpn"] = "unknown"
    return diag


def _check_htf_trend_flip_exit(side: str, htf_df) -> tuple[bool, str]:
    """Check if 1h EMA21/EMA50 has flipped against position direction.

    Returns (should_exit, reason). Used by htf_confluence_pullback positions only.
    """
    if htf_df is None or len(htf_df) == 0:
        return False, ""
    last = htf_df.iloc[-1]
    ema21 = last.get("ema_21")
    ema50 = last.get("ema_50")
    if ema21 is None or ema50 is None:
        return False, ""
    if side == "long" and ema21 < ema50:
        return True, "htf_trend_flip_exit"
    if side == "short" and ema21 > ema50:
        return True, "htf_trend_flip_exit"
    return False, ""


def _write_l2_snapshot(snapshot_dict: dict, path: str = "l2_snapshot.json") -> None:
    """Atomic write of L2 snapshot for dashboard. Silent on failure."""
    try:
        payload = {
            "updated_at": time.time(),
            "symbols": snapshot_dict,
        }
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp, path)
    except Exception as e:
        logger.debug(f"[L2_SNAPSHOT] write failed: {e}")


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
        self.ban_extensions = 0
        self._ws_feed: WSDataFeed | None = None
        self._empty_price_cycles = 0  # consecutive cycles with no ticker data (CDN ban detection)
        self._loss_streak = 0    # consecutive losses for streak-based sizing
        self._pair_cooldown: dict[str, float] = {}  # symbol -> timestamp when cooldown expires
        self._pair_loss_streak: dict[str, int] = {}  # symbol -> consecutive loss count
        self._last_entry_time: float = 0  # global cooldown between any new entry
        self._last_htf_entry_time: float = 0  # cluster throttle: 1 htf entry per 30 min
        self._trade_results: deque = deque(self.risk.trade_results, maxlen=5)  # rolling window of last 5 trade results (True=win, False=loss)
        self._regime_pause_until: float = 0  # timestamp when regime pause expires
        self._htf_cache: dict[str, tuple] = {}  # symbol -> (DataFrame, fetch_timestamp) for 1h candles
        self._funding_cache: dict[str, tuple] = {}  # symbol -> (data, fetch_timestamp) for funding rates
        self._divergence_cooldown: dict[str, dict] = {}  # symbol -> {"blocked_at": float, "clean_cycles": int}
        self._ob_depth_cache: dict[str, dict] = {}  # symbol -> depth data, populated by main loop, read by live writer thread

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
                slot_id="5m_mean_revert",
                strategy_name="bb_mean_reversion",
                timeframe="5m",
                max_positions=1,      # conservative — mean reversion is riskier
                capital_pct=0.3,      # 30% allocation (less than momentum/scalp)
                paper_mode=True,      # Paper mode first
            ),
            StrategySlot(
                slot_id="5m_liq_cascade",
                strategy_name="liq_cascade",
                timeframe="5m",
                max_positions=1,
                capital_pct=0.0,  # 0% for now — paper only
                paper_mode=True,
            ),
            # 5m_narrow — shadow slot that mirrors the live primary strategy but applies
            # three extra rejection filters (symbol blacklist, hour block, ensemble tightening).
            # Pure paper — never executes live orders. See strategy_slot.py:bump_blocked.
            StrategySlot(
                slot_id="5m_narrow",
                strategy_name="confluence",  # same primary strategy the live bot uses
                timeframe="5m",
                max_positions=2,
                capital_pct=0.0,
                paper_mode=True,
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
                            strategy: str = "", flow: dict | None = None) -> tuple[int, list[str]]:
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
        trend_strats = {"momentum_continuation", "trend_pullback", "keltner_squeeze", "htf_confluence_pullback", "htf_l2_anticipation"}
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

        # 7. Order flow — real-time buy/sell aggressor ratio
        if flow and flow.get("trade_count", 0) > 10:
            buy_ratio = flow.get("buy_ratio", 0.5)
            if (is_long and buy_ratio > 0.55) or (not is_long and buy_ratio < 0.45):
                confirmed.append("order_flow")

        logger.info(f"[ENSEMBLE] {direction} confidence={len(confirmed)}/{7} layers={','.join(confirmed) or 'none'}")
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
                self.ban_extensions = 0
            elif open_pos:
                # Sync ALL open positions — don't filter by active_pairs
                # (positions may exist on pairs not yet in the scanner/config list)
                if open_pos:
                    self.risk.sync_positions(open_pos, current_cycle=self.cycle_count)
                    logger.info(f"Synced {len(open_pos)} open position(s) from exchange")
                    # Refresh peak_price — may be stale if bot was down while price moved
                    for sym, pos in self.risk.positions.items():
                        try:
                            ticker = self.exchange.get_ticker(sym)
                            if ticker and "last" in ticker:
                                pos.update_trailing_stop(float(ticker["last"]))
                        except Exception as e:
                            logger.debug(f"Could not refresh peak_price for {sym}: {e}")
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

        def _cycle_timeout_handler(signum, frame):
            raise TimeoutError("Cycle exceeded 120s — likely hung API call")

        # Set running flag before starting thread so loop guard evaluates correctly
        self.running = True

        # Start L2 snapshot live writer thread (updates every 5s for real-time dashboard)
        threading.Thread(
            target=self._l2_live_writer_loop,
            daemon=True,
            name="l2-live-writer",
        ).start()
        logger.info("[L2_LIVE] Snapshot writer thread started (5s interval)")
        try:
            while self.running:
                try:
                    signal.signal(signal.SIGALRM, _cycle_timeout_handler)
                    signal.alarm(180)  # 120s cycle + 60s sleep
                    self._run_cycle()
                    self.consecutive_errors = 0
                    time.sleep(Config.LOOP_INTERVAL)
                    signal.alarm(0)  # cancel watchdog after sleep completes
                except TimeoutError as e:
                    signal.alarm(0)
                    self.consecutive_errors += 1
                    logger.error(f"[WATCHDOG] Cycle timed out ({self.consecutive_errors}): {e}")
                except Exception as e:
                    signal.alarm(0)
                    self.consecutive_errors += 1
                    logger.exception(f"Cycle error ({self.consecutive_errors})")
                if self.consecutive_errors >= 5:
                    self.ban_mode = True
                    self.ban_mode_until = time.time() + 600
                    self.ban_extensions = 0
                    logger.warning("[BAN MODE] Entering ban mode for 10 minutes after 5 consecutive errors")
                    self.consecutive_errors = 0
                    notifier.notify_ban_mode(10)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user.")
        finally:
            self._shutdown()

    def _set_pause_sentinel(self, reason: str) -> None:
        """Create the .pause_trading sentinel file with a reason note."""
        try:
            with open(".pause_trading", "w") as f:
                f.write(f"{int(time.time())}\n{reason}\n")
        except Exception as e:
            logger.warning(f"Failed to write pause sentinel: {e}")

    def _process_sentinels(self):
        """Check for sentinel files and act on them. One-shot: read, act, delete."""
        import glob as _glob

        # Global pause
        if os.path.exists(".pause_trading"):
            if not hasattr(self, '_pause_logged') or not self._pause_logged:
                logger.info("[SENTINEL] .pause_trading active — skipping all entries (exits still processed)")
                self._pause_logged = True
            self._trading_paused = True
        else:
            self._trading_paused = False
            self._pause_logged = False

        # Per-slot kills
        for path in _glob.glob(".kill_*"):
            slot_id = path.replace(".kill_", "")
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.enabled = False
                    for sym in list(slot.risk.positions.keys()):
                        pos = slot.risk.positions[sym]
                        if pos.side == "long":
                            self.exchange.close_long(sym, pos.amount)
                        else:
                            self.exchange.close_short(sym, pos.amount)
                        self.exchange.cancel_open_orders(sym)
                        logger.info(f"[SENTINEL] Closing {sym} for killed slot {slot_id}")
                    logger.warning(f"[SENTINEL] Slot '{slot_id}' KILLED")
                    notifier.send(f"🔪 Slot <b>{slot_id}</b> killed via sentinel")
                    break
            try:
                os.remove(path)
            except OSError:
                pass

        # Per-slot pauses (auto-expire after 24 hrs)
        for path in _glob.glob(".pause_*"):
            if path == ".pause_trading":
                continue
            slot_id = path.replace(".pause_", "")
            mtime = os.path.getmtime(path)
            if time.time() - mtime > 86400:
                os.remove(path)
                logger.info(f"[SENTINEL] Pause expired for slot '{slot_id}' (24 hrs)")
                continue
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.enabled = False

        # Promote: paper → live
        for path in _glob.glob(".promote_*"):
            slot_id = path.replace(".promote_", "")
            try:
                with open(path) as f:
                    data = json.load(f)
                capital_pct = data.get("capital_pct", 0.10)
            except Exception:
                capital_pct = 0.10
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.paper_mode = False
                    slot.capital_pct = capital_pct
                    logger.warning(f"[SENTINEL] Slot '{slot_id}' PROMOTED to live at {capital_pct*100:.0f}%")
                    notifier.send(f"🚀 Slot <b>{slot_id}</b> promoted to live ({capital_pct*100:.0f}% capital)")
                    break
            try:
                os.remove(path)
            except OSError:
                pass

        # Demote: live → paper
        for path in _glob.glob(".demote_*"):
            slot_id = path.replace(".demote_", "")
            for slot in self.slots:
                if slot.slot_id == slot_id:
                    slot.paper_mode = True
                    slot.capital_pct = 0.0
                    logger.warning(f"[SENTINEL] Slot '{slot_id}' DEMOTED to paper")
                    notifier.send(f"⬇️ Slot <b>{slot_id}</b> demoted to paper")
                    break
            try:
                os.remove(path)
            except OSError:
                pass

    def _run_cycle(self):
        import time as _time_module
        if self.ban_mode:
            if _time_module.time() < self.ban_mode_until:
                return
            # Use WS connectivity check instead of REST endpoint test
            if self._ws_feed and self._ws_feed.is_connected:
                recovery_failed = False
            else:
                sym = self.active_pairs[0] if self.active_pairs else None
                test = self.exchange.get_ohlcv(sym, Config.TIMEFRAME, limit=5) if sym else None
                recovery_failed = test is None or test.empty
            if recovery_failed:
                # Diagnose why recovery failed
                diag = _diagnose_connectivity()
                self.ban_extensions += 1
                logger.warning(
                    f"[BAN MODE] Still blocked (extension #{self.ban_extensions}) — "
                    f"network={diag['network']} vpn={diag['vpn']}"
                )
                # Re-rotate VPN every 2 failed recoveries
                if self.ban_extensions % 2 == 0:
                    logger.info(f"[BAN MODE] Re-rotating VPN after {self.ban_extensions} failed recoveries")
                    _rotate_vpn()
                # Telegram escalation after 60 min (6 extensions)
                if self.ban_extensions > 0 and self.ban_extensions % 6 == 0:
                    notifier.notify_ban_stuck(self.ban_extensions * 10, diag)
                self.ban_mode_until = _time_module.time() + 600
                return
            else:
                self.ban_mode = False
                self.consecutive_errors = 0
                self.ban_extensions = 0
                logger.info("[BAN MODE] Connection restored, resuming trading")
                notifier.notify_ban_lifted()

        self._process_sentinels()
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
                self.ban_extensions = 0
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
                    self.risk.close_position(symbol, fill_price, "early_exit", fees_usdt=self.exchange.extract_order_fee(order, symbol))
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
                self.risk.close_position(symbol, fill_price, "flat_exit", fees_usdt=self.exchange.extract_order_fee(order, symbol))
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "flat_exit")

        # Trend-flip exit — close htf_confluence_pullback positions when 1h EMA flips
        for symbol, pos in list(self.risk.positions.items()):
            if symbol not in self.risk.positions:
                continue
            if pos.strategy not in ("htf_confluence_pullback", "htf_l2_anticipation"):
                continue
            price = prices.get(symbol)
            if not price:
                continue
            htf_df_tuple = self._htf_cache.get(symbol)
            htf_df = htf_df_tuple[0] if htf_df_tuple else None
            should_flip, flip_reason = _check_htf_trend_flip_exit(pos.side, htf_df)
            if should_flip:
                logger.info(f"[TREND-FLIP EXIT] {symbol} {pos.side} — 1h EMA flipped, closing")
                if pos.side == "long":
                    order = self.exchange.close_long(symbol, pos.amount)
                else:
                    order = self.exchange.close_short(symbol, pos.amount)
                if not order:
                    logger.error(f"[TREND-FLIP EXIT] Close order failed for {symbol}")
                    continue
                fill_price = self._extract_fill_price(order, price, is_exit=True)
                self._set_cooldown_if_loss(symbol, pos.pnl_percent(fill_price))
                self.risk.close_position(symbol, fill_price, flip_reason, fees_usdt=self.exchange.extract_order_fee(order, symbol))
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), flip_reason)
                continue

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
                # Shadow log: would wider thresholds have held this trade?
                for alt in [-4.0, -5.0, -6.0]:
                    if roi > alt:
                        logger.info(f"[SHADOW ADVERSE] {symbol} — ROI {roi:.1f}% > {alt}% — would HOLD at threshold {alt}%")
                    else:
                        logger.info(f"[SHADOW ADVERSE] {symbol} — ROI {roi:.1f}% <= {alt}% — would STILL EXIT at threshold {alt}%")
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
                self.risk.close_position(symbol, fill_price, "adverse_exit", fees_usdt=self.exchange.extract_order_fee(order, symbol))
                self.exchange.cancel_open_orders(symbol)
                notifier.notify_exit(symbol, pos.side, pos.entry_price, fill_price, pos.pnl_usdt(fill_price), pos.pnl_percent(fill_price), "adverse_exit")
                continue

        # Bidirectional exchange sync — detect (A) closed-on-exchange positions AND
        # (B) untracked orphan positions. Must run even when self.risk.positions is empty,
        # because the orphan case by definition means bot thinks there are none.
        if Config.is_live():
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
                    self.risk.close_position(symbol, fill_price, exit_type, fees_usdt=self.exchange.extract_order_fee(order, symbol))
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
                    self.risk.close_position(symbol, fill_price, reason, fees_usdt=self.exchange.extract_order_fee(order, symbol))
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

        if getattr(self, '_trading_paused', False):
            return  # exits already processed above, skip entries

        # --- Extended kill switches (daily loss + consecutive loss) ---
        today_net = _compute_today_net_pnl(self.risk.closed_trades)
        if _should_halt_daily_loss(today_net, real_balance):
            reason = f"DAILY LOSS HALT: today net ${today_net:.2f} exceeds -3% of ${real_balance:.2f}"
            self._set_pause_sentinel(reason)
            logger.warning(f"[KILL SWITCH] {reason}")
            try:
                notifier.send(f"⛔ {reason}")
            except Exception:
                pass
            return

        if _should_halt_consecutive_losses(self._loss_streak):
            reason = f"CONSECUTIVE LOSS HALT: {self._loss_streak} losses in a row — 4h cooldown"
            self._set_pause_sentinel(reason)
            logger.warning(f"[KILL SWITCH] {reason}")
            try:
                notifier.send(f"⛔ {reason}")
            except Exception:
                pass
            return

        for symbol in self.active_pairs:
            if symbol in self.risk.positions:
                continue
            # Global cooldown: 2 min between any new entry (continue, not break)
            if time.time() - self._last_entry_time < 120:
                continue
            # Per-pair cooldown: skip pair after losses
            if symbol in self._pair_cooldown and time.time() < self._pair_cooldown[symbol]:
                continue
            # Daily trade counter — no hard cap, but log when a symbol trades frequently
            day_start = time.time() - (time.time() % 86400)  # midnight UTC
            daily_trades = sum(1 for t in self.risk.closed_trades
                               if t.get("symbol") == symbol and t.get("opened_at", 0) > day_start)
            daily_trades += 1 if symbol in self.risk.positions else 0  # count open positions too
            if daily_trades >= 4:
                logger.info(f"[RATE WATCH] {symbol} — {daily_trades + 1}th entry today (no cap, monitoring)")

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

            # Fetch orderbook, HTF data, and tape flow for strategy confirmation
            ob = self.exchange.get_order_book(symbol)
            # Cache depth for live L2 writer thread (no API cost — data is already fetched)
            if ob:
                self._ob_depth_cache[symbol] = {
                    "bid_depth_usdt": ob.get("bid_depth_usdt"),
                    "ask_depth_usdt": ob.get("ask_depth_usdt"),
                    "imbalance":      ob.get("imbalance", 0),
                    "updated_at":     time.time(),
                }
            htf_df = self._fetch_htf_data(symbol)
            flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
            try:
                signal = self.strategy_fn(df, ob, htf_df=htf_df, flow=flow)
            except TypeError:
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

                # Build cvd_data from order flow (backward compatible with ensemble layer 3)
                cvd_data = None
                if flow and flow.get("trade_count", 0) > 0:
                    cvd_data = {
                        "cvd": flow.get("cvd", 0),
                        "cvd_slope": flow.get("cvd_slope", 0),
                        "divergence": flow.get("divergence"),
                    }
                else:
                    # Fallback to REST CVD when WS trades unavailable
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
                    strategy=strat_name, flow=flow
                )
                # Strategy-aware confidence thresholds (raised to 4/7 on 2026-04-07)
                CONFIDENCE_THRESHOLDS = {
                    "htf_confluence_pullback": 4,
                    "htf_confluence_vwap": 4,
                    "vwap_reversion": 4,
                    "bb_mean_reversion": 4,
                    "momentum_continuation": 4,
                    "trend_pullback": 4,
                    "keltner_squeeze": 4,
                    "liq_cascade": 4,
                }
                min_confidence = CONFIDENCE_THRESHOLDS.get(strat_name, 4)

                if confidence < min_confidence:
                    logger.info(
                        f"[ENSEMBLE SKIP] {symbol} {direction} — BLOCKED: ensemble confidence {confidence}/7 "
                        f"< {min_confidence}/7 minimum (strat={strat_name})"
                    )
                    continue

                # Divergence cooldown — require 3 clean cycles OR 10 min after a divergence block
                if symbol in self._divergence_cooldown:
                    _dc = self._divergence_cooldown[symbol]
                    _dc_elapsed = time.time() - _dc["blocked_at"]
                    if _dc_elapsed >= 600 or _dc["clean_cycles"] >= 3:
                        del self._divergence_cooldown[symbol]  # cooldown expired, allow through
                    else:
                        # Count clean cycles (cycles where divergence is absent for this symbol)
                        if not (flow and flow.get("divergence")):
                            self._divergence_cooldown[symbol]["clean_cycles"] += 1
                        logger.info(
                            f"[DIVERGENCE COOLDOWN] {symbol} {direction} blocked — "
                            f"{_dc['clean_cycles']}/3 clean cycles, {_dc_elapsed:.0f}s elapsed")
                        continue

                # Order flow / tape veto — block entry if real money strongly disagrees
                if not (flow and flow.get("trade_count", 0) > 20):
                    logger.info(f"[TAPE GATE SKIP] {symbol} {direction} — low volume (trade_count={flow.get('trade_count', 0) if flow else 'no_flow'}) — tape gates inactive")
                    # Soft gate: even at low volume, block on extreme seller/buyer dominance
                    if flow and 5 <= flow.get("trade_count", 0) <= 20:
                        _soft_ratio = flow.get("buy_ratio", 0.5)
                        if direction == "long" and _soft_ratio < 0.40:
                            logger.info(
                                f"[TAPE GATE SOFT] {symbol} LONG blocked — buy_ratio {_soft_ratio:.0%} "
                                f"(thin tape, {flow.get('trade_count')} trades, sellers overwhelming)")
                            continue
                        if direction == "short" and _soft_ratio > 0.60:
                            logger.info(
                                f"[TAPE GATE SOFT] {symbol} SHORT blocked — buy_ratio {_soft_ratio:.0%} "
                                f"(thin tape, {flow.get('trade_count')} trades, buyers overwhelming)")
                            continue
                if flow and flow.get("trade_count", 0) > 20:
                    buy_ratio = flow.get("buy_ratio", 0.5)
                    cvd_slope = flow.get("cvd_slope", 0.0)
                    divergence = flow.get("divergence")
                    lt_bias = flow.get("large_trade_bias", 0.0)
                    if direction == "long" and buy_ratio < 0.45:
                        logger.info(
                            f"[TAPE GATE] {symbol} LONG blocked — buy_ratio {buy_ratio:.0%} "
                            f"({flow.get('trade_count', 0)} trades, sellers dominating)")
                        continue
                    if direction == "short" and buy_ratio > 0.55:
                        logger.info(
                            f"[TAPE GATE] {symbol} SHORT blocked — buy_ratio {buy_ratio:.0%} "
                            f"({flow.get('trade_count', 0)} trades, buyers dominating)")
                        continue
                    # cvd_slope absolute gate — skip for pullback/reversion strategies
                    # Pullbacks have negative CVD by definition (sellers pushing the dip),
                    # so this gate would systematically block legitimate pullback longs.
                    # The divergence gate below is the contextual version that handles this correctly.
                    if strat_name not in ("htf_confluence_pullback", "bb_mean_reversion"):
                        if direction == "long" and cvd_slope < -0.3:
                            logger.info(f"[TAPE GATE] {symbol} LONG blocked — CVD slope {cvd_slope:.2f} (selling accelerating)")
                            continue
                        if direction == "short" and cvd_slope > 0.3:
                            logger.info(f"[TAPE GATE] {symbol} SHORT blocked — CVD slope {cvd_slope:.2f} (buying accelerating)")
                            continue
                    if direction == "long" and divergence == "bearish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        logger.info(f"[TAPE GATE] {symbol} LONG blocked — bearish divergence (price up, sellers gaining)")
                        continue
                    if direction == "short" and divergence == "bullish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        logger.info(f"[TAPE GATE] {symbol} SHORT blocked — bullish divergence (price down, buyers gaining)")
                        continue
                    if direction == "long" and lt_bias < -0.3:
                        logger.info(f"[TAPE GATE] {symbol} LONG blocked — large trade bias {lt_bias:.2f} (whales selling)")
                        continue
                    if direction == "short" and lt_bias > 0.3:
                        logger.info(f"[TAPE GATE] {symbol} SHORT blocked — large trade bias {lt_bias:.2f} (whales buying)")
                        continue

                # Standalone divergence check — always active, even when tape gates skipped
                # Divergence = price direction vs CVD direction; valid at any volume
                # When trade_count > 20, the check inside the tape gate block (above) fires first.
                # This is the safety net for low-volume conditions where tape gates are skipped.
                if flow and flow.get("divergence"):
                    _div = flow["divergence"]
                    if direction == "long" and _div == "bearish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        self._log_gotaway("divergence_bearish", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[DIVERGENCE GATE] {symbol} LONG blocked — bearish divergence (always-on)")
                        continue
                    if direction == "short" and _div == "bullish":
                        self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
                        self._log_gotaway("divergence_bullish", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[DIVERGENCE GATE] {symbol} SHORT blocked — bullish divergence (always-on)")
                        continue

                # Apply funding rate strength modifier
                if funding_data and funding_data.get("strength_mod"):
                    signal = TradeSignal(signal.signal, signal.reason, signal.strength + funding_data["strength_mod"])

                # Candle-boundary entry bias: prefer entries near 5m candle opens
                # Research: +0.58bps at candle boundaries (t-stat > 9)
                now_min = datetime.datetime.now(datetime.timezone.utc).minute
                candle_offset = now_min % 5  # 0 = candle just opened, 4 = about to close
                if candle_offset >= 3:  # Last 2 minutes of candle — skip, wait for next open
                    logger.debug(f"[TIMING] {symbol} — skipping entry, {5-candle_offset}min to next candle open")
                    continue

                # Time-of-day filter: block entries during toxic PT hours (PDT = UTC-7)
                # Blocked PT hours → UTC (verified Apr 10–16, 417-trade analysis):
                #   2 AM PT   (26% WR/-$4.22 all-time)    → UTC 9
                #   10 AM-1 PM PT (28% WR/-$12.17)        → UTC 17,18,19,20
                #   5-7 PM PT (26% WR/-$16.11)            → UTC 0,1,2
                # Open: 12-2 AM, 3-10 AM, 2-5 PM, 8 PM-12 AM PT
                _BLOCKED_HOURS_UTC = {0, 1, 2, 9, 17, 18, 19, 20}
                _utc_hour = datetime.datetime.now(datetime.timezone.utc).hour
                _pt_hour = (_utc_hour - 7) % 24
                if _utc_hour in _BLOCKED_HOURS_UTC:
                    _pt_label = f"{_pt_hour % 12 or 12}:00 {'AM' if _pt_hour < 12 else 'PM'}"
                    logger.info(f"[TIME BLOCK] {symbol} {direction} skipped — {_pt_label} PT is blocked")
                    continue

                # Cluster throttle: max 1 htf_confluence_pullback entry per 30 min
                # Data: 27/57 htf cluster entries = -$14.10. Solo entries = -$0.37 (breakeven).
                if strat_name in ("htf_confluence_pullback", "htf_l2_anticipation") and time.time() - self._last_htf_entry_time < 1800:
                    logger.info(f"[HTF THROTTLE] {symbol} {direction} skipped — htf entry {(time.time() - self._last_htf_entry_time)/60:.0f}min ago, need 30min gap")
                    continue

                # Kelly-aware position sizing (uses $2 min margin during bootstrap)
                margin = self.risk.calculate_kelly_margin(available, confidence=confidence)

                # Weekend sizing boost: +85-92% weekend returns (p < 0.001)
                if datetime.datetime.now(datetime.timezone.utc).weekday() in (5, 6):  # Saturday=5, Sunday=6
                    margin = min(margin * 1.3, 10.0)  # cap at $10 (MAX_TRADE_MARGIN)

                if margin > available:
                    logger.warning(f"Insufficient balance for {symbol}: need {margin:.2f}, have {available:.2f}")
                    continue

                # Bump margin to exchange minimum if needed (ensures BTC/ETH can trade)
                try:
                    market = self.exchange.client.market(symbol)
                    min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
                    if min_amount and price > 0:
                        min_margin_needed = (min_amount * price) / Config.LEVERAGE
                        if margin < min_margin_needed:
                            old_margin = margin
                            margin = min(min_margin_needed * 1.1, available * 0.3)  # 10% buffer, cap at 30% of balance
                            if margin > available:
                                logger.debug(f"[SKIP] {symbol} — need ${min_margin_needed:.2f} but only ${available:.2f} available")
                                continue
                            logger.info(f"[MARGIN BUMP] {symbol} — ${old_margin:.2f} → ${margin:.2f} (exchange min qty)")
                except Exception:
                    pass

                # L2 Orderbook gate — block entry on adverse book conditions
                if ob is not None:
                    ob_imb = ob.get("imbalance", 0.0)
                    ob_bwalls = ob.get("bid_walls", [])
                    ob_awalls = ob.get("ask_walls", [])
                    ob_spread = ob.get("spread_pct", 0.0)
                    if direction == "long" and ob_imb < -0.25:
                        logger.info(f"[OB GATE] {symbol} LONG blocked — ask imbalance {ob_imb:.2f}")
                        continue
                    if direction == "short" and ob_imb > 0.25:
                        logger.info(f"[OB GATE] {symbol} SHORT blocked — bid imbalance {ob_imb:.2f}")
                        continue
                    if direction == "long" and ob_awalls and not ob_bwalls:
                        logger.info(f"[OB GATE] {symbol} LONG blocked — unmatched ask wall")
                        continue
                    if direction == "short" and ob_bwalls and not ob_awalls:
                        logger.info(f"[OB GATE] {symbol} SHORT blocked — unmatched bid wall")
                        continue
                    if ob_spread > 0.15:
                        logger.info(f"[OB GATE] {symbol} blocked — wide spread {ob_spread:.3f}%")
                        continue

                # QUIET regime gate — block low-momentum entries
                # QUIET = 5m ADX 20-25, no EMA stack alignment (0% WR in 48hr audit)
                # Allow through if flow CVD strongly confirms the trade direction
                _regime_snap = self._classify_regime(df.iloc[-1], df)
                if _regime_snap.get("label") == "QUIET":
                    _flow_confirms = False
                    if flow and flow.get("trade_count", 0) > 5:
                        if direction == "long" and flow.get("cvd_slope", 0) > 0.2:
                            _flow_confirms = True
                        if direction == "short" and flow.get("cvd_slope", 0) < -0.2:
                            _flow_confirms = True
                    if not _flow_confirms:
                        self._log_gotaway("quiet_regime", symbol, direction, strat_name,
                                          signal.strength, confidence, price, ob, flow, df)
                        logger.info(f"[REGIME GATE] {symbol} {direction.upper()} blocked — QUIET regime "
                                    f"(5m ADX={_regime_snap.get('adx', '?')}) with no flow confirmation")
                        continue

                order = self.exchange.open_long(symbol, margin, price) if direction == "long" else self.exchange.open_short(symbol, margin, price)
                if order:
                    fill_price = self._extract_fill_price(order, price)
                    self.risk.open_position(symbol, fill_price, margin, side=direction, atr=atr_val, regime=regime, cycle=self.cycle_count, strategy=strat_name)
                    pos = self.risk.positions[symbol]
                    fill_amount = self._extract_fill_amount(order, pos.amount)
                    actual_margin = (fill_amount * fill_price) / Config.LEVERAGE
                    _min_margin = float(os.getenv("MIN_TRADE_MARGIN", "10.0")) * 0.5
                    if actual_margin < _min_margin:
                        # Partial fill below minimum — close immediately to free the slot
                        logger.warning(f"[SKIP] {symbol} partial fill ${actual_margin:.4f} < ${_min_margin:.2f} min — closing to free slot")
                        self.exchange.cancel_open_orders(symbol)
                        close_ok = (
                            self.exchange.close_long(symbol, fill_amount)
                            if direction == "long"
                            else self.exchange.close_short(symbol, fill_amount)
                        )
                        if close_ok:
                            self.risk.close_position(symbol, fill_price, "min_margin_skip")
                        else:
                            logger.error(f"[SKIP] {symbol} emergency close failed — leaving in tracker for exit loop")
                        continue
                    pos.amount = fill_amount
                    pos.margin = actual_margin
                    pos.entry_strength = signal.strength
                    pos.confidence = confidence
                    pos.ensemble_layers = ",".join(layers)
                    sl_tp = self.exchange.place_sl_tp(symbol, direction, fill_amount, pos.stop_loss, pos.take_profit)
                    pos.sl_order_id = sl_tp.get("sl_order_id")
                    pos.tp_order_id = sl_tp.get("tp_order_id")
                    if not pos.sl_order_id:
                        pos.sl_order_id = "software"
                        logger.warning(f"[SL FALLBACK] Exchange SL failed for {direction.upper()} {symbol} — using software SL@{pos.stop_loss:.4f} TP@{pos.take_profit:.4f}")
                    available -= pos.margin
                    self._last_entry_time = time.time()
                    if strat_name in ("htf_confluence_pullback", "htf_l2_anticipation"):
                        self._last_htf_entry_time = time.time()
                    logger.info(f"[ENTRY] {direction.upper()} {symbol} | Fill: {fill_price:.4f} | Margin: ${pos.margin:.2f} | Conf: {confidence}/7 | {signal.reason} | Strength: {signal.strength:.2f}")
                    _htf_adx_val = float(htf_df.iloc[-1].get("adx", 0)) if htf_df is not None and len(htf_df) > 0 else None
                    pos.entry_snapshot = self._log_entry_snapshot(symbol, direction, "5m_scalp", strat_name, signal.strength, fill_price, confidence, ob, flow, ohlcv_last=df.iloc[-1], ohlcv_df=df, htf_adx=_htf_adx_val)
                    try:
                        self.risk._save_state()
                    except Exception as _e:
                        logger.debug(f"[SNAPSHOT] live save_state after entry failed: {_e}")
                    notifier.notify_entry(symbol, direction, fill_price, margin, pos.stop_loss, pos.take_profit, signal.strength, signal.reason)
                else:
                    # Before declaring "signal lost", verify no position materialized on-exchange.
                    # Race window: our order-tracking thinks nothing filled, but a late fill
                    # could have created an orphan (real-money incident 2026-04-13).
                    # CRITICAL: use the pre-snapshot amount captured by _try_limit_entry so we
                    # don't mis-adopt a pre-existing manual position as "our fill".
                    if Config.is_live():
                        pre_snap = getattr(self.exchange, "_last_entry_pre_amount", None) or {}
                        pre_amt = 0.0
                        if pre_snap.get("symbol") == symbol and pre_snap.get("side") == direction:
                            pre_amt = float(pre_snap.get("pre_amount") or 0.0)
                        try:
                            gt = self.exchange._position_ground_truth(symbol, direction, pre_amount=pre_amt)
                        except Exception as _e:
                            gt = None
                            logger.error(f"[ENTRY SAFETY] ground-truth check failed for {symbol}: {_e}")
                        if gt:
                            gt_entry = float(gt.get("average") or price)
                            gt_amount = float(gt.get("filled") or 0)
                            if gt_amount <= 0:
                                logger.error(f"[ENTRY SAFETY] {symbol} ground-truth returned zero amount — refusing to adopt, logging 'signal lost'")
                                logger.error(f"[ENTRY] Order FAILED for {direction.upper()} {symbol} — signal lost")
                                continue
                            logger.warning(
                                f"[ENTRY SAFETY] {symbol} {direction.upper()} orphan detected after 'signal lost' — "
                                f"adopting position @ {gt_entry} (amount={gt_amount})"
                            )
                            self.risk.open_position(symbol, gt_entry, margin, side=direction, atr=atr_val, regime=regime, cycle=self.cycle_count, strategy=strat_name)
                            pos = self.risk.positions[symbol]
                            pos.amount = gt_amount
                            pos.margin = (gt_amount * gt_entry) / Config.LEVERAGE
                            pos.entry_strength = signal.strength
                            pos.confidence = confidence
                            pos.ensemble_layers = ",".join(layers)
                            sl_tp = self.exchange.place_sl_tp(symbol, direction, pos.amount, pos.stop_loss, pos.take_profit)
                            pos.sl_order_id = sl_tp.get("sl_order_id")
                            pos.tp_order_id = sl_tp.get("tp_order_id")
                            if not pos.sl_order_id:
                                pos.sl_order_id = "software"
                            available -= pos.margin
                            self._last_entry_time = time.time()
                            if strat_name in ("htf_confluence_pullback", "htf_l2_anticipation"):
                                self._last_htf_entry_time = time.time()
                            try:
                                self.risk._save_state()
                            except Exception as _e:
                                logger.warning(f"[ENTRY SAFETY] _save_state after orphan-adopt failed for {symbol}: {_e}")
                            try:
                                notifier.send(
                                    f"⚠️ ORPHAN ADOPTED on entry\n"
                                    f"{symbol} {direction.upper()}\n"
                                    f"Entry: {gt_entry} | Amount: {pos.amount}\n"
                                    f"SL: {pos.stop_loss:.4f} | TP: {pos.take_profit:.4f}"
                                )
                            except Exception as _e:
                                logger.warning(f"[ENTRY SAFETY] Telegram alert for orphan-adopt failed: {_e}")
                            notifier.notify_entry(symbol, direction, gt_entry, pos.margin, pos.stop_loss, pos.take_profit, signal.strength, signal.reason + " (orphan-adopted)")
                            continue
                    logger.error(f"[ENTRY] Order FAILED for {direction.upper()} {symbol} — signal lost")

        if self.cycle_count % 10 == 0:
            self.risk.print_stats(real_balance)

        # Evaluate paper slots (completely isolated — no real orders)
        try:
            self._evaluate_paper_slots(self.active_pairs, prices)
        except Exception as e:
            logger.debug(f"[PAPER] Slot evaluation error: {e}")

        # Log slot status
        for slot in self.slots:
            s = slot.stats_summary()
            mode = "PAPER" if slot.paper_mode else "LIVE"
            status = "KILLED" if slot.is_killed else "ACTIVE" if slot.is_active else "DISABLED"
            logger.info(f"[SLOT] {slot.slot_id} ({mode}/{status}) | {s['trades']} trades | WR: {s['wr']}% | PnL: ${s['pnl']}")

    def _l2_live_writer_loop(self, interval_sec: float = 5.0) -> None:
        """Daemon thread: writes l2_snapshot.json every `interval_sec` from in-memory caches.
        No API calls — reads ws_feed (live) and _ob_depth_cache (populated by main loop)."""
        while self.running:
            try:
                pairs = list(self.active_pairs)
                accum: dict[str, dict] = {}
                for symbol in pairs:
                    flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
                    depth = self._ob_depth_cache.get(symbol, {})
                    accum[symbol] = {
                        "buy_ratio":         (flow or {}).get("buy_ratio"),
                        "cvd_slope":         (flow or {}).get("cvd_slope"),
                        "bid_depth_usdt":    depth.get("bid_depth_usdt"),
                        "ask_depth_usdt":    depth.get("ask_depth_usdt"),
                        "large_trade_bias":  (flow or {}).get("large_trade_bias"),
                        "trade_count":       (flow or {}).get("trade_count", 0),
                        "last_price":        None,
                        "updated_at":        time.time(),
                    }
                _write_l2_snapshot(accum)
            except Exception as e:
                logger.debug(f"[L2_LIVE] writer tick failed: {e}")
            time.sleep(interval_sec)

    def _evaluate_paper_slots(self, active_pairs: list, prices: dict):
        """Evaluate paper slots — simulate entries/exits without placing real orders."""
        for slot in self.slots:
            if not slot.paper_mode or not slot.is_active:
                continue

            strategy_fn = STRATEGIES.get(slot.strategy_name)
            if not strategy_fn:
                continue

            # --- Paper exits first (check existing paper positions) ---
            for symbol in list(slot.risk.positions.keys()):
                price = prices.get(symbol)
                if not price:
                    logger.debug(f"[PAPER] {slot.slot_id} no price for {symbol}, skipping exit check")
                    continue
                pos = slot.risk.positions[symbol]

                # Check SL
                if (pos.side == "long" and price <= pos.stop_loss) or \
                   (pos.side == "short" and price >= pos.stop_loss):
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    slot.risk.close_position(symbol, price, "stop_loss")
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, "stop_loss")
                    continue

                # Check TP
                if (pos.side == "long" and price >= pos.take_profit) or \
                   (pos.side == "short" and price <= pos.take_profit):
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    slot.risk.close_position(symbol, price, "take_profit")
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, "take_profit")
                    continue

                # Trend-flip exit for htf_confluence_pullback paper positions
                if slot.strategy_name in ("htf_confluence_pullback", "htf_l2_anticipation"):
                    htf_df_tuple = self._htf_cache.get(symbol)
                    htf_df = htf_df_tuple[0] if htf_df_tuple else None
                    should_flip, flip_reason = _check_htf_trend_flip_exit(pos.side, htf_df)
                    if should_flip:
                        pnl = pos.pnl_usdt(price)
                        pnl_pct = pos.pnl_percent(price)
                        logger.info(f"[PAPER TREND-FLIP EXIT] {slot.slot_id} {symbol} {pos.side} — 1h EMA flipped")
                        slot.risk.close_position(symbol, price, flip_reason)
                        notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, flip_reason)
                        continue

                # Check adverse exit
                if pos.should_adverse_exit(self.cycle_count, price):
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    slot.risk.close_position(symbol, price, "adverse_exit")
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, "adverse_exit")
                    continue

                # Check time exit
                should_exit, is_hard = pos.should_time_exit(self.cycle_count, price)
                if should_exit:
                    pnl = pos.pnl_usdt(price)
                    pnl_pct = pos.pnl_percent(price)
                    reason = "hard_time_exit" if is_hard else "time_exit"
                    slot.risk.close_position(symbol, price, reason)
                    notifier.notify_paper_exit(symbol, pos.side, pos.entry_price, price, pnl, pnl_pct, reason)
                    continue

            # --- Paper entries ---
            for symbol in active_pairs:
                if not slot.can_enter(symbol, self.slots):
                    continue

                price = prices.get(symbol)
                if not price:
                    continue

                try:
                    # Reuse WebSocket candle data (same as live bot — no extra REST calls)
                    if self._ws_feed and not self._ws_feed.is_stale(symbol):
                        df = self._ws_feed.get_ohlcv(symbol, limit=Config.CANDLE_LOOKBACK)
                    else:
                        df = self.exchange.get_ohlcv(symbol, slot.timeframe, limit=Config.CANDLE_LOOKBACK)
                    if df is None or len(df) < 50:
                        continue
                    df = add_all_indicators(df)
                    ob = self.exchange.get_order_book(symbol)
                    htf_df = self._fetch_htf_data(symbol)
                    _flow_for_strat = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None

                    # Build candidate signal list.
                    # For 5m_narrow ONLY: mirror every sub-strategy the live `confluence`
                    # router considers, so narrow filters can accept/reject each independently
                    # (instead of only seeing the single strongest signal confluence returns).
                    # Other slots keep their single-strategy behavior unchanged.
                    candidate_signals = []
                    if slot.slot_id == "5m_narrow":
                        try:
                            from strategies import (
                                htf_confluence_pullback,
                                htf_l2_anticipation,
                                htf_confluence_vwap,
                                bb_mean_reversion_strategy,
                                momentum_continuation_strategy,
                                liquidation_cascade_strategy,
                                htf_momentum_strategy,
                            )
                            _htf_adx = htf_df.iloc[-1].get("adx", 25) if htf_df is not None and len(htf_df) > 0 else 25
                            _hurst_v = df.iloc[-1].get("hurst", 0.5) if "hurst" in df.columns else 0.5
                            # Same gating confluence_strategy applies before routing
                            _chop_v = df.iloc[-1].get("chop", 50)
                            _confluence_ok = (htf_df is not None and len(htf_df) >= 30 and _chop_v <= 65 and len(df) >= 30)
                            if _confluence_ok:
                                if _htf_adx >= 20:
                                    candidate_signals.append(htf_confluence_pullback(df, ob, htf_df))
                                    candidate_signals.append(htf_l2_anticipation(df, ob, htf_df, _flow_for_strat))
                                if _htf_adx >= 25:
                                    candidate_signals.append(momentum_continuation_strategy(df, ob))
                                if _htf_adx < 25:
                                    candidate_signals.append(htf_confluence_vwap(df, ob, htf_df))
                                    if _hurst_v < 0.50:
                                        candidate_signals.append(bb_mean_reversion_strategy(df, ob))
                            # Top-level strategies the bot has registered but confluence doesn't call
                            try:
                                candidate_signals.append(htf_momentum_strategy(df, ob, htf_df=htf_df))
                            except TypeError:
                                candidate_signals.append(htf_momentum_strategy(df, ob))
                            candidate_signals.append(liquidation_cascade_strategy(df, ob))
                        except Exception as _narrow_build_err:
                            logger.debug(f"[PAPER] [NARROW] {symbol} candidate build failed: {_narrow_build_err}")
                            continue
                    else:
                        try:
                            _s = strategy_fn(df, ob, htf_df=htf_df)
                        except TypeError:
                            _s = strategy_fn(df, ob)
                        candidate_signals.append(_s)
                except Exception as e:
                    logger.debug(f"[PAPER] {slot.slot_id} error on {symbol}: {e}")
                    continue

                # Iterate each candidate signal (1 for standard slots, N for 5m_narrow)
                _entered_this_symbol = False
                for signal in candidate_signals:
                    if _entered_this_symbol:
                        break  # slot capacity respected — one entry per symbol per cycle
                    if signal is None or signal.signal == Signal.HOLD:
                        if signal is not None and "SMA+VWAP gate" in signal.reason:
                            logger.debug(f"[PAPER] {slot.slot_id} {symbol}: {signal.reason}")
                        continue
                    if signal.strength < 0.80:
                        logger.debug(f"[PAPER] {slot.slot_id} {symbol}: strength {signal.strength:.2f} < 0.80")
                        continue

                    direction = "long" if signal.signal == Signal.BUY else "short"

                    # --- 5m_narrow extra filters (shadow-only, never affects live) ---
                    if slot.slot_id == "5m_narrow":
                        try:
                            # Filter 1: symbol blacklist extension
                            if "SUI" in symbol or "LINK" in symbol:
                                slot.bump_blocked("blocked_symbol")
                                logger.debug(f"[PAPER] [NARROW FILTER] {symbol} blocked_symbol")
                                continue
                            # Filter 2: hour block extension (UTC hour 0 = PT 5 PM PDT, UTC hour 17 = PT 10 AM PDT)
                            _narrow_hr = datetime.datetime.now(datetime.timezone.utc).hour
                            if _narrow_hr in (0, 17):
                                slot.bump_blocked("blocked_hour")
                                logger.debug(f"[PAPER] [NARROW FILTER] {symbol} blocked_hour UTC{_narrow_hr}")
                                continue
                            # Filter 3: ensemble tightening for htf_confluence_pullback (>=5/7 vs live 4/7)
                            _narrow_strat = _extract_strategy_name(signal.reason)
                            if _narrow_strat == "htf_confluence_pullback":
                                _narrow_conf, _ = self._compute_confidence(
                                    direction, df, ob, htf_df=htf_df,
                                    cvd_data=self._ws_feed.get_order_flow(symbol) if self._ws_feed else None,
                                    hurst_val=None, funding_data=None,
                                    strategy=_narrow_strat,
                                    flow=self._ws_feed.get_order_flow(symbol) if self._ws_feed else None,
                                )
                                if _narrow_conf < 5:
                                    slot.bump_blocked("blocked_ensemble")
                                    logger.debug(f"[PAPER] [NARROW FILTER] {symbol} blocked_ensemble {_narrow_conf}/7<5")
                                    continue
                        except Exception as _ne:
                            logger.debug(f"[PAPER] [NARROW FILTER] {symbol} filter error (skipping signal): {_ne}")
                            continue
                    margin = Config.TRADE_AMOUNT_USDT
                    atr_val = df.iloc[-2].get("atr", 0) if len(df) > 1 else 0

                    # Apply OB + Tape gates to paper slots
                    # L2 Orderbook gate
                    if ob is not None:
                        ob_imb = ob.get("imbalance", 0.0)
                        ob_bwalls = ob.get("bid_walls", [])
                        ob_awalls = ob.get("ask_walls", [])
                        ob_spread = ob.get("spread_pct", 0.0)
                        if direction == "long" and ob_imb < -0.25:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} LONG blocked — ask imbalance {ob_imb:.2f}")
                            continue
                        if direction == "short" and ob_imb > 0.25:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} SHORT blocked — bid imbalance {ob_imb:.2f}")
                            continue
                        if direction == "long" and ob_awalls and not ob_bwalls:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} LONG blocked — unmatched ask wall")
                            continue
                        if direction == "short" and ob_bwalls and not ob_awalls:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} SHORT blocked — unmatched bid wall")
                            continue
                        if ob_spread > 0.15:
                            logger.debug(f"[PAPER] [OB GATE] {slot.slot_id} {symbol} blocked — wide spread {ob_spread:.3f}%")
                            continue
                    # Tape gate
                    flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
                    if flow and flow.get("trade_count", 0) > 20:
                        buy_ratio = flow.get("buy_ratio", 0.5)
                        cvd_slope = flow.get("cvd_slope", 0.0)
                        divergence = flow.get("divergence")
                        lt_bias = flow.get("large_trade_bias", 0.0)
                        if direction == "long" and buy_ratio < 0.45:
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — buy_ratio {buy_ratio:.0%}")
                            continue
                        if direction == "short" and buy_ratio > 0.55:
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — buy_ratio {buy_ratio:.0%}")
                            continue
                        # CVD slope gate — carve-out for pullback/reversion (matches live bot line 1037)
                        _paper_strat = _extract_strategy_name(signal.reason)
                        if _paper_strat not in ("htf_confluence_pullback", "bb_mean_reversion"):
                            if direction == "long" and cvd_slope < -0.3:
                                logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — CVD slope {cvd_slope:.2f}")
                                continue
                            if direction == "short" and cvd_slope > 0.3:
                                logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — CVD slope {cvd_slope:.2f}")
                                continue
                        if direction == "long" and divergence == "bearish":
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — bearish divergence")
                            continue
                        if direction == "short" and divergence == "bullish":
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — bullish divergence")
                            continue
                        if direction == "long" and lt_bias < -0.3:
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} LONG blocked — large trade bias {lt_bias:.2f}")
                            continue
                        if direction == "short" and lt_bias > 0.3:
                            logger.debug(f"[PAPER] [TAPE GATE] {slot.slot_id} {symbol} SHORT blocked — large trade bias {lt_bias:.2f}")
                            continue

                    # Shadow-tag: which LIVE gates would have blocked this trade?
                    _gate_tags = []
                    _strat_name = _extract_strategy_name(signal.reason)
                    _conf, _layers = self._compute_confidence(
                        direction, df, ob, htf_df=htf_df,
                        cvd_data=self._ws_feed.get_order_flow(symbol) if self._ws_feed else None,
                        hurst_val=None, funding_data=None,
                        strategy=_strat_name, flow=flow
                    )
                    if _conf < 4:
                        _gate_tags.append(f"confidence:{_conf}/7<4")
                    _utc_hr = datetime.datetime.now(datetime.timezone.utc).hour
                    if _utc_hr in {0, 1, 2, 17, 18, 19, 20}:
                        _gate_tags.append(f"time_block:UTC{_utc_hr}")
                    if time.time() - self._last_entry_time < 120:
                        _gate_tags.append("global_cooldown")
                    _regime_snap = self._classify_regime(df.iloc[-1], df)
                    if _regime_snap.get("label") == "QUIET":
                        _fc = False
                        if flow and flow.get("trade_count", 0) > 5:
                            if direction == "long" and flow.get("cvd_slope", 0) > 0.2:
                                _fc = True
                            if direction == "short" and flow.get("cvd_slope", 0) < -0.2:
                                _fc = True
                        if not _fc:
                            _gate_tags.append("quiet_regime")
                    if flow and flow.get("divergence"):
                        if direction == "long" and flow["divergence"] == "bearish":
                            _gate_tags.append("divergence_bearish")
                        if direction == "short" and flow["divergence"] == "bullish":
                            _gate_tags.append("divergence_bullish")
                    _would_block = len(_gate_tags) > 0
                    _tag_str = ",".join(_gate_tags) if _gate_tags else "none"

                    # For 5m_narrow, record the actual routed sub-strategy, not the slot's
                    # generic "confluence" label — preserves per-strategy attribution in logs.
                    _entry_strategy_name = _strat_name if (slot.slot_id == "5m_narrow" and _strat_name) else slot.strategy_name

                    slot.risk.open_position(
                        symbol, price, margin, side=direction,
                        atr=atr_val, regime="medium",
                        cycle=self.cycle_count,
                        strategy=_entry_strategy_name
                    )
                    notifier.notify_paper_entry(
                        symbol, direction, price, margin,
                        signal.strength, signal.reason
                    )
                    slot.total_entries += 1
                    _entered_this_symbol = True
                    _block_label = f" [WOULD BLOCK: {_tag_str}]" if _would_block else ""
                    logger.info(
                        f"[PAPER] {slot.slot_id} ENTRY {direction.upper()} {symbol} | "
                        f"Price: {price:.4f} | Strength: {signal.strength:.2f} | {signal.reason}{_block_label}"
                    )
                    snap = self._log_entry_snapshot(symbol, direction, slot.slot_id, _entry_strategy_name, signal.strength, price, 0, None, flow, ohlcv_last=df.iloc[-1] if len(df) > 0 else None, ohlcv_df=df if len(df) >= 20 else None)
                    if symbol in slot.risk.positions:
                        slot.risk.positions[symbol].entry_snapshot = snap
                        slot.risk.positions[symbol].gate_tags = _tag_str
                        try:
                            slot.risk._save_state()
                        except Exception as _e:
                            logger.debug(f"[SNAPSHOT] paper save_state after entry failed: {_e}")

    @staticmethod
    def _classify_regime(last, df=None) -> dict:
        """Classify market regime from OHLCV indicator row. Pure data, no gates."""
        try:
            close = float(last.get("close", 0))
            adx = float(last.get("adx", 0))
            atr = float(last.get("atr", 0))
            ema9 = float(last.get("ema_9", 0))
            ema21 = float(last.get("ema_21", 0))
            ema50 = float(last.get("ema_50", 0))
            ema200 = float(last.get("ema_200", 0))
            vol = float(last.get("volume", 0))
            vol_avg = float(df["volume"].iloc[-20:].mean()) if df is not None and len(df) >= 20 else 0
        except (TypeError, ValueError):
            return {"label": "UNKNOWN"}

        atr_pct = (atr / close) if close > 0 else 0
        vol_ratio = (vol / vol_avg) if vol_avg > 0 else 1.0
        above_ema200 = close > ema200 if ema200 > 0 else True
        stack_bull = ema9 > ema21 > ema50 > 0
        stack_bear = 0 < ema9 < ema21 < ema50

        if atr_pct > 0.015 or vol_ratio > 2.5:
            label = "VOLATILE"
        elif adx >= 25 and stack_bull and above_ema200:
            label = "TRENDING_UP"
        elif adx >= 25 and stack_bear and not above_ema200:
            label = "TRENDING_DOWN"
        elif adx < 20:
            label = "CHOPPY"
        else:
            label = "QUIET"

        return {
            "label": label,
            "adx": round(adx, 1),
            "atr_pct": round(atr_pct, 5),
            "above_ema200": above_ema200,
            "ema_stack_bull": stack_bull,
            "ema_stack_bear": stack_bear,
            "vol_ratio": round(vol_ratio, 2),
        }

    def _log_gotaway(self, reason: str, symbol: str, direction: str, strategy: str,
                     strength: float, confidence: int, price: float,
                     ob: dict | None, flow: dict | None, df=None):
        """Log a trade that was blocked by defensive gates for later analysis."""
        import json as _json
        entry = {
            "ts": int(time.time()),
            "reason": reason,
            "symbol": symbol,
            "direction": direction,
            "strategy": strategy,
            "strength": round(strength, 3),
            "confidence": confidence,
            "price": round(price, 6),
            "ob": {
                "imbalance": round(ob.get("imbalance", 0), 3),
                "spread_pct": round(ob.get("spread_pct", 0), 4),
            } if ob else None,
            "flow": {
                "buy_ratio": round(flow.get("buy_ratio", 0), 3),
                "cvd_slope": round(flow.get("cvd_slope", 0), 4),
                "divergence": flow.get("divergence"),
                "large_trade_bias": round(flow.get("large_trade_bias", 0), 3),
                "trade_count": flow.get("trade_count", 0),
            } if flow else None,
            "regime": self._classify_regime(df.iloc[-1], df) if df is not None and len(df) > 0 else None,
        }
        try:
            with open("logs/gotAway.jsonl", "a") as f:
                f.write(_json.dumps(entry) + "\n")
        except Exception:
            pass

    def _log_entry_snapshot(self, symbol: str, direction: str, slot_id: str,
                            strategy: str, strength: float, price: float,
                            confidence: int, ob: dict | None, flow: dict | None,
                            ohlcv_last=None, ohlcv_df=None, htf_adx: float = None) -> dict:
        """Append entry conditions snapshot to JSONL for post-hoc analysis.
        Returns the snapshot dict so it can be attached to the Position."""
        import json as _json
        snapshot = {
            "ts": int(time.time()),
            "symbol": symbol,
            "direction": direction,
            "slot": slot_id,
            "strategy": strategy,
            "strength": round(strength, 3),
            "confidence": confidence,
            "price": round(price, 6),
            "ob": {
                "imbalance": round(ob.get("imbalance", 0), 3),
                "bid_walls": len(ob.get("bid_walls", [])),
                "ask_walls": len(ob.get("ask_walls", [])),
                "spread_pct": round(ob.get("spread_pct", 0), 4),
            } if ob else None,
            "flow": {
                "buy_ratio": round(flow.get("buy_ratio", 0), 3),
                "cvd_slope": round(flow.get("cvd_slope", 0), 4),
                "divergence": flow.get("divergence"),
                "large_trade_bias": round(flow.get("large_trade_bias", 0), 3),
                "trade_count": flow.get("trade_count", 0),
            } if flow else None,
            "regime": self._classify_regime(ohlcv_last, ohlcv_df) if ohlcv_last is not None else None,
            "htf_adx": round(htf_adx, 1) if htf_adx is not None else None,
        }
        try:
            with open("logs/entry_snapshots.jsonl", "a") as f:
                f.write(_json.dumps(snapshot) + "\n")
        except Exception as e:
            logger.debug(f"[SNAPSHOT] Failed to write: {e}")
        return snapshot

    def _set_cooldown_if_loss(self, symbol: str, pnl_pct: float):
        """Set cooldown on a pair after loss: 10 min per loss, 4 hr after 3 consecutive.
        Also tracks global loss streak for regime filter."""
        if pnl_pct < 0:
            # Per-pair cooldown
            self._pair_loss_streak[symbol] = self._pair_loss_streak.get(symbol, 0) + 1
            streak = self._pair_loss_streak[symbol]
            if streak >= 3:
                self._pair_cooldown[symbol] = time.time() + 14400  # 4 hr after 3 consecutive losses
                self._pair_loss_streak[symbol] = 0
                logger.info(f"[BLACKLIST] {symbol} blocked for 4 hours after {streak} consecutive losses")
            else:
                self._pair_cooldown[symbol] = time.time() + 600  # 10 min after any loss
                logger.info(f"[RATE GATE] {symbol} blocked for 10 min (streak: {streak})")
            # Global regime filter: 3 of last 5 trades lost → 30 min pause
            self._trade_results.append(False)
            losses = sum(1 for r in self._trade_results if not r)
            if len(self._trade_results) >= 5 and losses >= 3:
                self._regime_pause_until = time.time() + 1800  # 30 min pause
                logger.warning(f"[REGIME] Rolling window: {losses}/5 losses — pausing 30 min")
                notifier.notify_ban_mode(30)  # reuse ban notification for regime pause
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
        """Bidirectional per-cycle position reconciliation against the exchange:

          (A) Exchange-closed positions that the bot still tracks (SL/TP fired) — close them locally.
          (B) Exchange-OPEN positions that the bot does NOT track (orphans) — auto-adopt with
              ATR/% SL + TP placed on the exchange, send Telegram alert.

          Case (B) added 2026-04-13 after a BTC short orphan ran to -45% unrealized because
          a race in _try_limit_entry let a late fill slip through without being recorded.
          Defense in depth: exchange.py adds a ground-truth check, bot.py adds entry-failure
          adoption, this function is the belt-and-suspenders catch-all.
        """
        try:
            exchange_positions = self.exchange.get_open_positions()
        except Exception as e:
            logger.warning(f"[SYNC] fetch_positions failed: {e} — skipping sync this cycle")
            return
        if exchange_positions is None:
            return  # API failed, skip sync this cycle (treat as unknown, not as "no positions")
        exchange_map = {p["symbol"]: p for p in exchange_positions}
        exchange_symbols = set(exchange_map.keys())

        # --- (A) Closes: tracked locally but gone from exchange ---
        try:
            for symbol in list(self.risk.positions.keys()):
                if symbol not in exchange_symbols:
                    pos = self.risk.positions[symbol]
                    # Try to get actual fill price from recent trades
                    exit_price = prices.get(symbol, pos.entry_price)
                    sync_fee = 0.0
                    try:
                        recent = self.exchange.client.fetch_my_trades(symbol, limit=10)
                        if recent:
                            # Filter to trades after position entry to avoid picking up the entry fill
                            entry_ts_ms = int(pos.opened_at * 1000)
                            close_trades = [tr for tr in recent if (tr.get("timestamp") or 0) > entry_ts_ms]
                            last_trade = close_trades[-1] if close_trades else None
                            if last_trade:
                                fill = float(last_trade.get("price", 0))
                                if fill > 0:
                                    exit_price = fill
                                    logger.info(f"[SYNC] {symbol} real exit fill: {exit_price}")
                                # Sum fees from the confirmed close trade
                                try:
                                    fee = last_trade.get("fee") or {}
                                    if fee.get("cost") is not None:
                                        sync_fee = abs(float(fee.get("cost") or 0))
                                    else:
                                        for f in last_trade.get("fees") or []:
                                            if f.get("cost") is not None:
                                                sync_fee += abs(float(f.get("cost") or 0))
                                except Exception:
                                    pass
                            else:
                                logger.debug(f"[SYNC] {symbol} no post-entry close trade found yet — using mark price")
                    except Exception:
                        pass
                    logger.info(f"[SYNC] {symbol} closed on exchange (SL/TP triggered) — removing from tracker")
                    self.exchange.cancel_open_orders(symbol)
                    self._set_cooldown_if_loss(symbol, pos.pnl_percent(exit_price))
                    notifier.notify_exit(symbol, pos.side, pos.entry_price, exit_price, pos.pnl_usdt(exit_price), pos.pnl_percent(exit_price), "exchange_close")
                    self.risk.close_position(symbol, exit_price, "exchange_close", fees_usdt=sync_fee)
        except Exception as e:
            logger.warning(f"[SYNC] (A) close-detection path failed: {e} — continuing to orphan scan")

        # --- (B) Orphans: open on exchange but not tracked locally ---
        # Snapshotted after (A) so any positions just closed locally are excluded.
        # Runs independently of (A) — a bug in close-detection must not block orphan discovery.
        try:
            tracked_symbols = set(self.risk.positions.keys())
            # NOTE: list comprehension is materialized before _adopt_orphan_position can mutate
            # self.risk.positions. Safe, but if refactored to a generator this becomes a bug.
            orphans = [p for p in exchange_positions if p["symbol"] not in tracked_symbols]
            for orphan in orphans:
                try:
                    self._adopt_orphan_position(orphan)
                except Exception as e:
                    logger.error(f"[ORPHAN] Failed to adopt {orphan.get('symbol')}: {e}")
        except Exception as e:
            logger.warning(f"[SYNC] (B) orphan-scan path failed: {e}")

    def _adopt_orphan_position(self, orphan: dict):
        """Adopt an exchange-visible position that the bot isn't tracking.

        - Calls risk.open_position to register it (with % SL fallback — ATR isn't available post-hoc)
        - Places SL/TP on exchange
        - Adds symbol to active_pairs so it's priced every cycle
        - Sends Telegram alert (real-money event — must not be silent)
        """
        symbol = orphan["symbol"]
        side = orphan["side"]
        entry_price = float(orphan["entry_price"])
        amount = float(orphan["amount"])
        margin = float(orphan.get("margin") or (amount * entry_price / max(Config.LEVERAGE, 1)))

        logger.warning(
            f"[ORPHAN] Adopting untracked position: {symbol} {side.upper()} "
            f"@ {entry_price} amount={amount} margin=${margin:.2f}"
        )

        # Register with risk manager (falls through to configured % SL since atr=0)
        self.risk.open_position(
            symbol, entry_price, margin,
            side=side, atr=0.0, regime="medium",
            cycle=self.cycle_count, strategy="orphan_adopted",
        )
        pos = self.risk.positions[symbol]
        pos.amount = amount
        pos.margin = margin

        # Place SL/TP on the exchange so the broker protects this position
        try:
            sl_tp = self.exchange.place_sl_tp(symbol, side, amount, pos.stop_loss, pos.take_profit)
            pos.sl_order_id = sl_tp.get("sl_order_id")
            pos.tp_order_id = sl_tp.get("tp_order_id")
            if not pos.sl_order_id:
                pos.sl_order_id = "software"
                logger.warning(f"[ORPHAN] Exchange SL placement failed for {symbol} — software SL@{pos.stop_loss:.4f}")
        except Exception as e:
            pos.sl_order_id = "software"
            logger.error(f"[ORPHAN] SL/TP placement failed for {symbol}: {e} — software SL@{pos.stop_loss:.4f}")

        # Make sure this symbol is priced on future cycles
        try:
            if symbol not in self.active_pairs:
                self.active_pairs.append(symbol)
        except Exception:
            pass

        # Persist immediately so a restart doesn't re-orphan it
        try:
            self.risk._save_state()
        except Exception as e:
            logger.debug(f"[ORPHAN] _save_state after adoption failed: {e}")

        # Telegram alert — this is a real-money event, must not be silent
        try:
            notifier.send(
                f"⚠️ ORPHAN POSITION ADOPTED (per-cycle scan)\n"
                f"{symbol} {side.upper()}\n"
                f"Entry: {entry_price} | Amount: {amount} | Margin: ${margin:.2f}\n"
                f"SL: {pos.stop_loss:.4f} | TP: {pos.take_profit:.4f}\n"
                f"Cycle: #{self.cycle_count}"
            )
        except Exception:
            pass

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
