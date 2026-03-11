import json
import os
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

    def update_trailing_stop(self, current_price: float):
        if not Config.TRAILING_STOP:
            return
        if self.side == "long" and current_price > self.peak_price:
            self.peak_price = current_price
            self.trailing_stop_price = current_price * (1 - Config.TRAILING_STOP_OFFSET / 100)
        elif self.side == "short" and current_price < self.peak_price:
            self.peak_price = current_price
            self.trailing_stop_price = current_price * (1 + Config.TRAILING_STOP_OFFSET / 100)

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
        """Exit early if momentum has reversed and we're in profit."""
        try:
            pnl_pct = self.pnl_percent(current_price)
            if pnl_pct < 0.8:
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
        return self.pnl_usdt(current_price) / self.margin * 100


class RiskManager:
    def __init__(self):
        self.positions: dict[str, Position] = {}
        self.initial_balance: float = 0.0
        self.peak_balance: float = 0.0
        self.closed_trades: list = []
        self._load_state()

    def _load_state(self):
        if os.path.exists(PERSISTENCE_FILE):
            try:
                with open(PERSISTENCE_FILE) as f:
                    data = json.load(f)
                self.peak_balance = data.get("peak_balance", 0.0)
                self.closed_trades = data.get("closed_trades", [])
                logger.info(f"Loaded state: peak_balance={self.peak_balance:.2f}, trades={len(self.closed_trades)}")
            except Exception as e:
                logger.warning(f"Could not load state: {e}")

    def _save_state(self):
        try:
            with open(PERSISTENCE_FILE, "w") as f:
                json.dump({"peak_balance": self.peak_balance, "closed_trades": self.closed_trades}, f)
        except Exception as e:
            logger.warning(f"Could not save state: {e}")

    def set_initial_balance(self, balance: float):
        self.initial_balance = balance
        if balance > self.peak_balance:
            self.peak_balance = balance
        self._save_state()

    def can_open_trade(self, balance: float) -> bool:
        if len(self.positions) >= Config.MAX_OPEN_TRADES:
            logger.debug(f"Max open trades reached ({Config.MAX_OPEN_TRADES})")
            return False
        drawdown = self._drawdown_percent(balance)
        if drawdown >= Config.MAX_DRAWDOWN_PERCENT:
            logger.warning(f"Max drawdown reached ({drawdown:.1f}%). Trading halted.")
            return False
        min_margin = Config.TRADE_AMOUNT_USDT  # must have full margin available
        if balance < min_margin:
            logger.warning(f"Balance too low to trade safely: {balance:.2f} USDT (min {min_margin})")
            return False
        return True

    def calculate_margin(self, balance: float) -> float:
        """Returns USDT margin to use per trade (fixed amount — always exact, never partial)."""
        return Config.TRADE_AMOUNT_USDT

    def open_position(self, symbol: str, entry_price: float, margin: float, side: str, atr: float = 0.0) -> Position:
        coin_amount = (margin * Config.LEVERAGE) / entry_price

        if atr > 0:
            sl_dist = 1.5 * atr
            tp_dist = 3.0 * atr
            # Cap SL at 2% of entry price — prevents absurd ATR-based stops on volatile alts
            max_sl_dist = entry_price * (Config.STOP_LOSS_PERCENT / 100)
            if sl_dist > max_sl_dist:
                sl_dist = max_sl_dist
                tp_dist = max_sl_dist * 2  # maintain 2:1 R:R
            if side == "long":
                stop_loss   = entry_price - sl_dist
                take_profit = entry_price + tp_dist
                trailing_start = entry_price * (1 - Config.TRAILING_STOP_OFFSET / 100) if Config.TRAILING_STOP else None
            else:
                stop_loss   = entry_price + sl_dist
                take_profit = entry_price - tp_dist
                trailing_start = entry_price * (1 + Config.TRAILING_STOP_OFFSET / 100) if Config.TRAILING_STOP else None
        else:
            if side == "long":
                stop_loss   = entry_price * (1 - Config.STOP_LOSS_PERCENT / 100)
                take_profit = entry_price * (1 + Config.TAKE_PROFIT_PERCENT / 100)
                trailing_start = entry_price * (1 - Config.TRAILING_STOP_OFFSET / 100) if Config.TRAILING_STOP else None
            else:
                stop_loss   = entry_price * (1 + Config.STOP_LOSS_PERCENT / 100)
                take_profit = entry_price * (1 - Config.TAKE_PROFIT_PERCENT / 100)
                trailing_start = entry_price * (1 + Config.TRAILING_STOP_OFFSET / 100) if Config.TRAILING_STOP else None

        position = Position(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            amount=coin_amount,
            margin=margin,
            stop_loss=stop_loss,
            take_profit=take_profit,
            peak_price=entry_price,
            trailing_stop_price=trailing_start,
        )
        self.positions[symbol] = position
        sl_mode = f"ATR×1.5({atr:.5f})" if atr > 0 else "fixed%"
        logger.info(
            f"Position opened: {side.upper()} {symbol} | Entry: {entry_price:.4f} | "
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f} | "
            f"Margin: {margin:.2f} USDT | Size: {coin_amount:.6f} ({Config.LEVERAGE}x) | {sl_mode}"
        )
        return position

    def sync_positions(self, open_positions: list[dict]):
        """Load exchange positions into self.positions on startup."""
        for p in open_positions:
            symbol      = p["symbol"]
            side        = p["side"]
            entry_price = p["entry_price"]
            amount      = p["amount"]
            margin      = p["margin"]

            if side == "long":
                stop_loss   = entry_price * (1 - Config.STOP_LOSS_PERCENT / 100)
                take_profit = entry_price * (1 + Config.TAKE_PROFIT_PERCENT / 100)
                trailing_start = entry_price * (1 - Config.TRAILING_STOP_OFFSET / 100) if Config.TRAILING_STOP else None
            else:
                stop_loss   = entry_price * (1 + Config.STOP_LOSS_PERCENT / 100)
                take_profit = entry_price * (1 - Config.TAKE_PROFIT_PERCENT / 100)
                trailing_start = entry_price * (1 + Config.TRAILING_STOP_OFFSET / 100) if Config.TRAILING_STOP else None

            position = Position(
                symbol=symbol,
                side=side,
                entry_price=entry_price,
                amount=amount,
                margin=margin,
                stop_loss=stop_loss,
                take_profit=take_profit,
                peak_price=entry_price,
                trailing_stop_price=trailing_start,
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
        notional = pos.amount * exit_price
        fee = notional * (Config.TAKER_FEE_PERCENT / 100) * 2  # entry + exit
        slippage_cost = notional * (Config.SLIPPAGE_PERCENT / 100)
        pnl = pnl - fee - slippage_cost
        pnl_pct  = pnl / pos.margin * 100

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
                to_close.append((symbol, "partial_tp"))
            elif pos.should_stop_loss(price):
                to_close.append((symbol, "stop_loss"))
        return to_close

    def partial_close_position(self, symbol: str, exit_price: float):
        """Close half the position, move SL to breakeven, let remainder run."""
        if symbol not in self.positions:
            return None
        pos = self.positions[symbol]
        half_amount = pos.amount / 2
        pos.amount = half_amount
        pos.margin = pos.margin / 2
        pos.stop_loss = pos.entry_price
        pos.take_profit = None
        pos.trailing_stop_price = None
        pos.peak_price = exit_price

        pnl = (exit_price - pos.entry_price) * half_amount if pos.side == "long" else (pos.entry_price - exit_price) * half_amount
        pnl_pct = pnl / (pos.margin / 2) * 100
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
