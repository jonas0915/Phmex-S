from dataclasses import dataclass, field
from typing import Optional
from config import Config
from logger import setup_logger

logger = setup_logger()


@dataclass
class Position:
    symbol: str
    entry_price: float
    amount: float          # coin amount
    cost: float            # USDT cost
    stop_loss: float
    take_profit: float
    trailing_stop_price: Optional[float] = None
    peak_price: float = 0.0

    def update_trailing_stop(self, current_price: float):
        if not Config.TRAILING_STOP:
            return
        if current_price > self.peak_price:
            self.peak_price = current_price
            self.trailing_stop_price = current_price * (1 - Config.TRAILING_STOP_OFFSET / 100)

    def should_stop_loss(self, current_price: float) -> bool:
        if Config.TRAILING_STOP and self.trailing_stop_price:
            return current_price <= self.trailing_stop_price
        return current_price <= self.stop_loss

    def should_take_profit(self, current_price: float) -> bool:
        return current_price >= self.take_profit

    def pnl_percent(self, current_price: float) -> float:
        return (current_price - self.entry_price) / self.entry_price * 100

    def pnl_usdt(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.amount


class RiskManager:
    def __init__(self):
        self.positions: dict[str, Position] = {}
        self.initial_balance: float = 0.0
        self.peak_balance: float = 0.0
        self.closed_trades: list = []

    def set_initial_balance(self, balance: float):
        self.initial_balance = balance
        self.peak_balance = balance

    def can_open_trade(self, balance: float) -> bool:
        if len(self.positions) >= Config.MAX_OPEN_TRADES:
            logger.debug(f"Max open trades reached ({Config.MAX_OPEN_TRADES})")
            return False
        drawdown = self._drawdown_percent(balance)
        if drawdown >= Config.MAX_DRAWDOWN_PERCENT:
            logger.warning(f"Max drawdown reached ({drawdown:.1f}%). Trading halted.")
            return False
        return True

    def calculate_position_size(self, balance: float, price: float) -> float:
        usdt_amount = balance * (Config.TRADE_AMOUNT_PERCENT / 100)
        return usdt_amount

    def open_position(self, symbol: str, entry_price: float, usdt_amount: float) -> Position:
        coin_amount = usdt_amount / entry_price
        stop_loss = entry_price * (1 - Config.STOP_LOSS_PERCENT / 100)
        take_profit = entry_price * (1 + Config.TAKE_PROFIT_PERCENT / 100)

        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            amount=coin_amount,
            cost=usdt_amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
            peak_price=entry_price,
            trailing_stop_price=entry_price * (1 - Config.TRAILING_STOP_OFFSET / 100) if Config.TRAILING_STOP else None
        )
        self.positions[symbol] = position
        logger.info(
            f"Position opened: {symbol} | Entry: {entry_price:.4f} | "
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f} | Amount: {coin_amount:.6f}"
        )
        return position

    def close_position(self, symbol: str, exit_price: float, reason: str):
        if symbol not in self.positions:
            return
        pos = self.positions.pop(symbol)
        pnl = pos.pnl_usdt(exit_price)
        pnl_pct = pos.pnl_percent(exit_price)

        trade = {
            "symbol": symbol,
            "entry": pos.entry_price,
            "exit": exit_price,
            "amount": pos.amount,
            "pnl_usdt": pnl,
            "pnl_pct": pnl_pct,
            "reason": reason,
        }
        self.closed_trades.append(trade)

        emoji = "+" if pnl >= 0 else ""
        logger.info(
            f"Position closed: {symbol} | Exit: {exit_price:.4f} | "
            f"PnL: {emoji}{pnl:.2f} USDT ({emoji}{pnl_pct:.2f}%) | Reason: {reason}"
        )

    def check_positions(self, prices: dict[str, float]) -> list[tuple[str, str]]:
        """Check all positions for exit conditions. Returns list of (symbol, reason)."""
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

    def update_peak_balance(self, balance: float):
        if balance > self.peak_balance:
            self.peak_balance = balance

    def _drawdown_percent(self, current_balance: float) -> float:
        if self.peak_balance == 0:
            return 0.0
        return (self.peak_balance - current_balance) / self.peak_balance * 100

    def print_stats(self, current_balance: float):
        total_trades = len(self.closed_trades)
        if total_trades == 0:
            logger.info("No closed trades yet.")
            return

        wins = [t for t in self.closed_trades if t["pnl_usdt"] > 0]
        losses = [t for t in self.closed_trades if t["pnl_usdt"] <= 0]
        total_pnl = sum(t["pnl_usdt"] for t in self.closed_trades)
        win_rate = len(wins) / total_trades * 100

        logger.info(
            f"=== STATS === Trades: {total_trades} | Win Rate: {win_rate:.1f}% | "
            f"Total PnL: {total_pnl:+.2f} USDT | Balance: {current_balance:.2f} USDT | "
            f"Drawdown: {self._drawdown_percent(current_balance):.1f}%"
        )
