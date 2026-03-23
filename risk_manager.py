import json
import os
import time
from dataclasses import dataclass
from typing import Optional
from config import Config
from logger import setup_logger

logger = setup_logger()

PERSISTENCE_FILE = os.path.join(os.path.dirname(__file__), "trading_state.json")



@dataclass
class Position:
    symbol: str
    side: str              # "long" or "short"
    entry_price: float
    amount: float          # coin amount (leveraged)
    margin: float          # USDT margin used
    stop_loss: float
    take_profit: float
    trailing_stop_price: Optional[float] = None
    peak_price: float = 0.0
    sl_order_id: str = None
    tp_order_id: str = None
    entry_cycle: int = 0  # cycle count when position was opened
    opened_at: float = 0.0  # epoch timestamp when position was opened
    strategy: str = ""  # strategy name for strategy-specific time exits
    entry_strength: float = 0.0
    confidence: int = 0
    ensemble_layers: str = ""

    def update_trailing_stop(self, current_price: float):
        """Tiered trailing stop — the bigger the winner, the tighter the trail.
        Never give back more than 1/3 of peak profit.

        | ROI Reached | Min Lock-In | Trail from Peak |
        |-------------|-------------|-----------------|
        | +5%         | +2%         | 3% from peak    |
        | +8%         | +4%         | 4% from peak    |
        | +10%        | +6%         | 4% from peak    |
        | +15%        | +10%        | 5% from peak    |
        | +20%        | +15%        | 5% from peak    |
        """
        if not Config.TRAILING_STOP:
            return

        roi = self.pnl_percent(current_price)
        if roi < 5.0:
            return  # Not yet in profit territory for trailing

        # Determine tier
        tiers = [
            (20.0, 15.0, 5.0),  # (roi_threshold, lock_in_pct, trail_pct)
            (15.0, 10.0, 5.0),
            (10.0,  6.0, 4.0),
            ( 8.0,  4.0, 4.0),
            ( 5.0,  2.0, 3.0),
        ]

        lock_in_pct = 2.0
        trail_pct = 3.0
        for threshold, lock, trail in tiers:
            if roi >= threshold:
                lock_in_pct = lock
                trail_pct = trail
                break

        # Compute trail price from current peak
        if self.side == "long":
            if current_price > self.peak_price or self.peak_price == 0.0:
                self.peak_price = current_price
            trail_price = self.peak_price * (1 - trail_pct / 100 / Config.LEVERAGE)
            # Compute lock-in floor price
            lock_price = self.entry_price * (1 + lock_in_pct / 100 / Config.LEVERAGE)
            # Use the higher of trail and lock-in
            new_trail = max(trail_price, lock_price)
            if self.trailing_stop_price is None or new_trail > self.trailing_stop_price:
                self.trailing_stop_price = new_trail
        elif self.side == "short":
            if current_price < self.peak_price or self.peak_price == 0.0:
                self.peak_price = current_price
            trail_price = self.peak_price * (1 + trail_pct / 100 / Config.LEVERAGE)
            lock_price = self.entry_price * (1 - lock_in_pct / 100 / Config.LEVERAGE)
            new_trail = min(trail_price, lock_price)
            if self.trailing_stop_price is None or new_trail < self.trailing_stop_price:
                self.trailing_stop_price = new_trail

    def should_stop_loss(self, current_price: float) -> bool:
        if Config.TRAILING_STOP and self.trailing_stop_price:
            if self.side == "long":
                return current_price <= self.trailing_stop_price
            else:
                return current_price >= self.trailing_stop_price
        if self.side == "long":
            return current_price <= self.stop_loss
        else:
            return current_price >= self.stop_loss

    def should_take_profit(self, current_price: float) -> bool:
        if self.take_profit is None:
            return False
        if self.side == "long":
            return current_price >= self.take_profit
        else:
            return current_price <= self.take_profit

    def should_exit_early(self, current_price: float, df) -> bool:
        """Exit early if momentum has reversed and we're in profit.
        Lowered to 3% ROI — early_exit was 100% WR (+$16.24), fires more often at lower threshold."""
        try:
            pnl_pct = self.pnl_percent(current_price)
            if pnl_pct < 3.0:
                return False

            last = df.iloc[-1]
            prev = df.iloc[-2]
            signals = 0

            if self.side == "long":
                if last.get("rsi", 50) < 45:
                    signals += 1
                if "macd" in last and "macd_signal" in last:
                    if last["macd"] < last["macd_signal"] and prev["macd"] >= prev["macd_signal"]:
                        signals += 1
                if "ema_9" in last and "ema_9" in prev:
                    if last["close"] < last["ema_9"] and prev["close"] < prev["ema_9"]:
                        signals += 1
            else:
                if last.get("rsi", 50) > 55:
                    signals += 1
                if "macd" in last and "macd_signal" in last:
                    if last["macd"] > last["macd_signal"] and prev["macd"] <= prev["macd_signal"]:
                        signals += 1
                if "ema_9" in last and "ema_9" in prev:
                    if last["close"] > last["ema_9"] and prev["close"] > prev["ema_9"]:
                        signals += 1

            # At 8%+ ROI, relax to 1 signal — data shows 16 trades leaked at 8-22% ROI
            # because 2-of-3 signals weren't present. 1-of-3 captures them.
            if pnl_pct >= 8.0:
                return signals >= 1
            return signals >= 2
        except Exception:
            return False

    def pnl_usdt(self, current_price: float) -> float:
        if self.side == "long":
            return (current_price - self.entry_price) * self.amount
        else:
            return (self.entry_price - current_price) * self.amount

    def pnl_percent(self, current_price: float) -> float:
        """PnL as % of margin (reflects leverage)."""
        if self.margin <= 0:
            return 0.0
        return self.pnl_usdt(current_price) / self.margin * 100

    def should_adverse_exit(self, current_cycle: int, current_price: float) -> bool:
        """Exit early if trade is going wrong direction after N cycles.
        Catches bad entries before they bleed to time_exit."""
        cycles_held = current_cycle - self.entry_cycle
        if cycles_held < Config.ADVERSE_EXIT_CYCLES:
            return False
        roi = self.pnl_percent(current_price)
        if roi <= Config.ADVERSE_EXIT_THRESHOLD:
            return True
        return False

    def should_time_exit(self, current_cycle: int, current_price: float = 0.0) -> tuple[bool, bool]:
        """Hard time exit only — 4h unconditional safety net.
        Soft time exits removed per 567K backtest study:
        tight time exits destroy performance.
        Adverse exit at -5% ROI handles wrong-direction trades."""
        hard_limit = 240  # 4 hours at 60s loop = 240 cycles
        cycles_held = current_cycle - self.entry_cycle
        roi = self.pnl_percent(current_price) if current_price > 0 else -99.0

        if cycles_held >= hard_limit:
            # Extend by 50% if trade is profitable (>= 5% ROI)
            if roi >= 5.0:
                extended = int(hard_limit * 1.5)
                if cycles_held < extended:
                    return False, False
            return True, True

        return False, False

    def should_flat_exit(self, current_cycle: int, current_price: float) -> bool:
        """Exit stagnant trades after 10 min. Catches trades that would otherwise
        bleed to time_exit (89 trades, 2.2% WR, -$34.84).
        Widened from [2.5%, 4%) to [-4%, +4%) to catch near-zero losers too."""
        FLAT_EXIT_CYCLES = 240  # 240 × 60s = 4 hrs
        cycles_held = current_cycle - self.entry_cycle
        if cycles_held < FLAT_EXIT_CYCLES:
            return False
        roi = self.pnl_percent(current_price)
        return -4.0 <= roi < 4.0

    def check_breakeven(self, current_price: float):
        """Move SL to breakeven + fees once trade reaches 1R profit.
        Profit-lock removed in v4.0 — let early_exit manage high-ROI exits."""
        # Stage 1 only: At 1R profit, move SL to breakeven + fees
        r_distance = abs(self.entry_price - self.stop_loss)
        # 0.25% buffer covers round-trip fees (0.06% taker × 2 + 0.05% slippage × 2 = 0.22%) + margin
        if self.side == "long":
            if current_price >= self.entry_price + r_distance:
                new_sl = self.entry_price + (self.entry_price * 0.0025)
                if new_sl > self.stop_loss:
                    self.stop_loss = new_sl
        elif self.side == "short":
            if current_price <= self.entry_price - r_distance:
                new_sl = self.entry_price - (self.entry_price * 0.0025)
                if new_sl < self.stop_loss:
                    self.stop_loss = new_sl


class RiskManager:
    def __init__(self, state_file: str = None):
        self.state_file = os.path.join(os.path.dirname(__file__), state_file or "trading_state.json")
        self.positions: dict[str, Position] = {}
        self.initial_balance: float = 0.0
        self.peak_balance: float = 0.0
        self.closed_trades: list = []
        self._drawdown_pause_until: float = 0  # timestamp when drawdown pause expires
        self.trade_results: list = []  # rolling window of last 6 trade results (persisted for bot regime filter)
        self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    data = json.load(f)
                self.peak_balance = data.get("peak_balance", 0.0)
                self.closed_trades = data.get("closed_trades", [])
                self.trade_results = data.get("trade_results", [])
                logger.info(f"Loaded state: peak_balance={self.peak_balance:.2f}, trades={len(self.closed_trades)}")
            except Exception as e:
                logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump({"peak_balance": self.peak_balance, "closed_trades": self.closed_trades, "trade_results": self.trade_results}, f)
        except Exception as e:
            logger.warning(f"Could not save state: {e}")

    def set_initial_balance(self, balance: float):
        self.initial_balance = balance
        # Reset stale peak_balance if drawdown > 50% — prevents 1.5hr pause on every restart
        if self.peak_balance > 0 and balance < self.peak_balance * 0.5:
            logger.info(f"[DRAWDOWN] Resetting stale peak_balance {self.peak_balance:.2f} → {balance:.2f} (was >50% drawdown)")
            self.peak_balance = balance
        if balance > self.peak_balance:
            self.peak_balance = balance
        self._save_state()

    def can_open_trade(self, balance: float) -> bool:
        if len(self.positions) >= Config.MAX_OPEN_TRADES:
            logger.debug(f"Max open trades reached ({Config.MAX_OPEN_TRADES})")
            return False

        # Drawdown halt with auto-resume cooldown
        if self._drawdown_pause_until > 0:
            if time.time() < self._drawdown_pause_until:
                remaining = int(self._drawdown_pause_until - time.time())
                if remaining % 60 < 16:  # log roughly once per minute (within 15s loop window)
                    logger.info(f"[DRAWDOWN] Entries paused — {remaining // 60}m {remaining % 60}s remaining")
                return False
            else:
                # Cooldown expired — reset peak to current balance so drawdown = 0% (fresh start)
                logger.info(f"[DRAWDOWN] Cooldown expired. Resetting peak from {self.peak_balance:.2f} to {balance:.2f} — resuming trading.")
                self.peak_balance = balance
                self._drawdown_pause_until = 0
                self._save_state()

        drawdown = self._drawdown_percent(balance)
        if drawdown >= 30.0:
            self._drawdown_pause_until = time.time() + 5400  # 1.5 hours
            logger.warning(f"[DRAWDOWN] {drawdown:.1f}% — SEVERE. Halting entries for 1.5 hours.")
            return False
        elif drawdown >= 25.0:
            self._drawdown_pause_until = time.time() + 3600  # 1 hour
            logger.warning(f"[DRAWDOWN] {drawdown:.1f}% — HIGH. Halting entries for 1 hour.")
            return False
        elif drawdown >= 20.0:
            self._drawdown_pause_until = time.time() + 1800  # 30 min
            logger.warning(f"[DRAWDOWN] {drawdown:.1f}% — ELEVATED. Halting entries for 30 min.")
            return False

        min_margin = Config.TRADE_AMOUNT_USDT  # must have full margin available
        if balance < min_margin:
            logger.warning(f"Balance too low to trade safely: {balance:.2f} USDT (min {min_margin})")
            return False
        return True

    def calculate_margin(self, balance: float, atr: float = 0.0, price: float = 0.0) -> float:
        """Returns USDT margin to use per trade. If ATR provided, sizes so SL = 1% of balance."""
        if atr > 0 and price > 0:
            risk_per_trade = balance * 0.01  # risk 1% of balance
            sl_distance_pct = (1.5 * atr) / price  # approx SL distance as %
            if sl_distance_pct > 0:
                margin = risk_per_trade / (sl_distance_pct * Config.LEVERAGE)
                margin = min(margin, Config.TRADE_AMOUNT_USDT)  # cap at config max
                margin = max(margin, Config.TRADE_AMOUNT_USDT * 0.3)  # floor at 30% of config
                return margin
        return Config.TRADE_AMOUNT_USDT

    def calculate_kelly_margin(self, balance: float, confidence: int = 0) -> float:
        """Kelly-criterion position sizing scaled by ensemble confidence.

        Uses closed trade history to compute fractional Kelly.
        - 5+ confirmations → full size (1x fKelly)
        - 3-4 confirmations → half size (0.5x fKelly)
        - 0-2 confirmations → no trade (caller should skip)
        Bootstrap phase: first 50 trades use MIN_TRADE_MARGIN.
        Kill switch: if Kelly is negative after 50 trades, auto-size to MIN_TRADE_MARGIN.
        """
        kelly_fraction = float(os.getenv("KELLY_FRACTION", "0.25"))
        min_margin = float(os.getenv("MIN_TRADE_MARGIN", "2.0"))
        max_margin = float(os.getenv("MAX_TRADE_MARGIN", "10.0"))
        kelly_lookback = int(os.getenv("KELLY_LOOKBACK", "50"))

        # Bootstrap phase: not enough data yet
        if len(self.closed_trades) < kelly_lookback:
            logger.debug(f"[KELLY] Bootstrap phase ({len(self.closed_trades)}/{kelly_lookback} trades) — using min margin ${min_margin}")
            return min_margin

        # Compute Kelly from recent trades
        recent = self.closed_trades[-kelly_lookback:]
        wins = [t for t in recent if t["pnl_usdt"] > 0]
        losses = [t for t in recent if t["pnl_usdt"] <= 0]

        if not wins or not losses:
            return min_margin

        win_rate = len(wins) / len(recent)
        avg_win = sum(t["pnl_usdt"] for t in wins) / len(wins)
        avg_loss = abs(sum(t["pnl_usdt"] for t in losses) / len(losses))

        if avg_win <= 0:
            return min_margin

        # Kelly formula: f* = (WR * avg_win - (1-WR) * avg_loss) / avg_win
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win

        if kelly <= 0:
            # Negative edge — kill switch: size to minimum
            logger.warning(f"[KELLY] Negative edge ({kelly:.4f}) after {kelly_lookback} trades — kill switch, using ${min_margin}")
            return min_margin

        # Fractional Kelly (conservative)
        f_kelly = kelly * kelly_fraction

        # Scale by confidence tier
        if confidence >= 5:
            conf_mult = 1.0
        elif confidence >= 3:
            conf_mult = 0.5
        else:
            conf_mult = 0.0  # caller should have skipped, but safety net

        margin = balance * f_kelly * conf_mult

        # Clamp to bounds, never exceed 15% of balance
        margin = max(min_margin, min(margin, max_margin, balance * 0.15))

        logger.info(f"[KELLY] f*={kelly:.4f} fKelly={f_kelly:.4f} conf={confidence} mult={conf_mult} → ${margin:.2f}")
        return margin

    def calculate_kelly_raw(self) -> float:
        """Return raw Kelly criterion value. Negative = no edge."""
        trades = self.closed_trades
        if len(trades) < 20:
            return 0.0
        wins = [t for t in trades if t.get("pnl_usdt", 0) > 0]
        losses = [t for t in trades if t.get("pnl_usdt", 0) <= 0]
        if not wins or not losses:
            return 0.0
        wr = len(wins) / len(trades)
        avg_win = sum(t["pnl_usdt"] for t in wins) / len(wins)
        avg_loss = abs(sum(t["pnl_usdt"] for t in losses) / len(losses))
        if avg_win == 0:
            return 0.0
        return (wr * avg_win - (1 - wr) * avg_loss) / avg_win

    def open_position(self, symbol: str, entry_price: float, margin: float, side: str, atr: float = 0.0, regime: str = "medium", cycle: int = 0, strategy: str = "") -> Position:
        coin_amount = (margin * Config.LEVERAGE) / entry_price

        if atr > 0:
            # Regime-adaptive ATR multipliers
            REGIME_MULTS = {
                "low":     {"sl": 1.2, "tp_ratio": 2.0},
                "medium":  {"sl": 1.5, "tp_ratio": 2.0},
                "high":    {"sl": 2.0, "tp_ratio": 2.0},
                "extreme": {"sl": 2.5, "tp_ratio": 2.0},
            }
            mults = REGIME_MULTS.get(regime, REGIME_MULTS["medium"])
            sl_dist = mults["sl"] * atr
            tp_dist = sl_dist * mults["tp_ratio"]
            # Floor = configured SL%, Cap = 3× floor so ATR can breathe
            min_sl_dist = entry_price * (Config.STOP_LOSS_PERCENT / 100)
            max_sl_dist = entry_price * (Config.STOP_LOSS_PERCENT / 100) * 3
            sl_dist = max(min_sl_dist, min(sl_dist, max_sl_dist))
            # Cap SL so R:R never goes below 1:1
            max_tp_dist = entry_price * (Config.TAKE_PROFIT_PERCENT / 100)
            max_sl_for_rr = max_tp_dist / mults["tp_ratio"]
            sl_dist = min(sl_dist, max(min_sl_dist, max_sl_for_rr))
            tp_dist = sl_dist * mults["tp_ratio"]
            # Cap TP at .env value so it's actually reachable
            tp_dist = min(tp_dist, max_tp_dist)
            if side == "long":
                stop_loss   = entry_price - sl_dist
                take_profit = entry_price + tp_dist
            else:
                stop_loss   = entry_price + sl_dist
                take_profit = entry_price - tp_dist
        else:
            if side == "long":
                stop_loss   = entry_price * (1 - Config.STOP_LOSS_PERCENT / 100)
                take_profit = entry_price * (1 + Config.TAKE_PROFIT_PERCENT / 100)
            else:
                stop_loss   = entry_price * (1 + Config.STOP_LOSS_PERCENT / 100)
                take_profit = entry_price * (1 - Config.TAKE_PROFIT_PERCENT / 100)

        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            amount=coin_amount,
            margin=margin,
            stop_loss=stop_loss,
            take_profit=take_profit,
            peak_price=entry_price,
            trailing_stop_price=None,
            entry_cycle=cycle,
            opened_at=time.time(),
            strategy=strategy,
        )
        self.positions[symbol] = position
        sl_mode = f"ATR×{mults['sl'] if atr > 0 else 'fixed'}({atr:.5f})" if atr > 0 else "fixed%"
        logger.info(
            f"Position opened: {side.upper()} {symbol} | Entry: {entry_price:.4f} | "
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f} | "
            f"Margin: {margin:.2f} USDT | Size: {coin_amount:.6f} ({Config.LEVERAGE}x) | {sl_mode}"
            f" | strat={strategy or 'default'} time_exit=hard240"
        )
        return position

    def sync_positions(self, open_positions: list[dict], current_cycle: int = 0):
        """Load exchange positions into self.positions on startup."""
        for p in open_positions:
            symbol      = p["symbol"]
            side        = p["side"]
            entry_price = p["entry_price"]
            amount      = p["amount"]
            margin      = p["margin"]
            if margin <= 0:
                margin = Config.TRADE_AMOUNT_USDT
                logger.warning(f"[SYNC] {symbol} margin=0 from exchange — using default ${margin}")

            if side == "long":
                stop_loss   = entry_price * (1 - Config.STOP_LOSS_PERCENT / 100)
                take_profit = entry_price * (1 + Config.TAKE_PROFIT_PERCENT / 100)
            else:
                stop_loss   = entry_price * (1 + Config.STOP_LOSS_PERCENT / 100)
                take_profit = entry_price * (1 - Config.TAKE_PROFIT_PERCENT / 100)

            position = Position(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                amount=amount,
                margin=margin,
                stop_loss=stop_loss,
                take_profit=take_profit,
                peak_price=entry_price,
                trailing_stop_price=None,
                entry_cycle=current_cycle,
                opened_at=time.time(),
                strategy="synced",
            )
            self.positions[symbol] = position
            logger.info(
                f"[SYNC] Loaded {side.upper()} {symbol} | Entry: {entry_price:.4f} | "
                f"SL: {stop_loss:.4f} | TP: {take_profit:.4f} | "
                f"Amount: {amount:.6f} | Margin: {margin:.2f} USDT"
            )

    def close_position(self, symbol: str, exit_price: float, reason: str):
        if symbol not in self.positions:
            return
        pos = self.positions.pop(symbol)
        pnl      = pos.pnl_usdt(exit_price)
        pnl_pct  = pnl / pos.margin * 100 if pos.margin > 0 else 0.0

        trade = {
            "symbol":   symbol,
            "side":     pos.side,
            "entry":    pos.entry_price,
            "exit":     exit_price,
            "amount":   pos.amount,
            "margin":   pos.margin,
            "pnl_usdt": pnl,
            "pnl_pct":  pnl_pct,
            "reason":   reason,
            "strategy": pos.strategy,
            "opened_at": pos.opened_at,
            "closed_at": time.time(),
            "entry_strength": pos.entry_strength,
            "confidence": pos.confidence,
            "ensemble_layers": pos.ensemble_layers,
            "duration_s": time.time() - pos.opened_at,
        }
        self.closed_trades.append(trade)
        self._save_state()

        sign = "+" if pnl >= 0 else ""
        logger.info(
            f"Position closed: {pos.side.upper()} {symbol} | Exit: {exit_price:.4f} | "
            f"PnL: {sign}{pnl:.2f} USDT ({sign}{pnl_pct:.2f}%) | Reason: {reason}"
        )

    def check_positions(self, prices: dict[str, float]) -> list[tuple[str, str]]:
        to_close = []
        for symbol, pos in list(self.positions.items()):
            price = prices.get(symbol)
            if not price:
                continue
            pos.update_trailing_stop(price)
            if pos.should_take_profit(price):
                to_close.append((symbol, "take_profit"))
            elif pos.should_stop_loss(price):
                to_close.append((symbol, "stop_loss"))
        return to_close

    def partial_close_position(self, symbol: str, exit_price: float):
        """Close half the position, move SL to breakeven + fees, let remainder run."""
        if symbol not in self.positions:
            return None
        pos = self.positions[symbol]
        half_amount = pos.amount / 2
        pos.amount = half_amount
        pos.margin = pos.margin / 2
        # SL at entry + 0.15% fee buffer to avoid micro-losses on remainder
        if pos.side == "long":
            pos.stop_loss = pos.entry_price * 1.0015
        else:
            pos.stop_loss = pos.entry_price * 0.9985
        pos.take_profit = None
        pos.trailing_stop_price = None
        pos.peak_price = exit_price

        pnl = (exit_price - pos.entry_price) * half_amount if pos.side == "long" else (pos.entry_price - exit_price) * half_amount
        half_margin = pos.margin  # margin was already halved above (line 379)
        pnl_pct = pnl / half_margin * 100 if half_margin > 0 else 0.0
        sign = "+" if pnl >= 0 else ""
        logger.info(
            f"[PARTIAL TP] {pos.side.upper()} {symbol} | Closed half @ {exit_price:.4f} | "
            f"PnL on half: {sign}{pnl:.2f} USDT ({sign}{pnl_pct:.2f}%) | Remainder running with SL @ entry"
        )
        return half_amount

    def update_peak_balance(self, balance: float):
        if balance > self.peak_balance:
            self.peak_balance = balance
            self._save_state()

    def _drawdown_percent(self, current_balance: float) -> float:
        if self.peak_balance == 0:
            return 0.0
        return (self.peak_balance - current_balance) / self.peak_balance * 100

    def print_stats(self, current_balance: float):
        total_trades = len(self.closed_trades)
        if total_trades == 0:
            logger.info("No closed trades yet.")
            return

        wins     = [t for t in self.closed_trades if t["pnl_usdt"] > 0]
        losses   = [t for t in self.closed_trades if t["pnl_usdt"] <= 0]
        total_pnl = sum(t["pnl_usdt"] for t in self.closed_trades)
        win_rate  = len(wins) / total_trades * 100
        longs     = [t for t in self.closed_trades if t["side"] == "long"]
        shorts    = [t for t in self.closed_trades if t["side"] == "short"]

        logger.info(
            f"=== STATS === Trades: {total_trades} (L:{len(longs)} S:{len(shorts)}) | "
            f"Win Rate: {win_rate:.1f}% | Total PnL: {total_pnl:+.2f} USDT | "
            f"Balance: {current_balance:.2f} USDT | Drawdown: {self._drawdown_percent(current_balance):.1f}%"
        )
