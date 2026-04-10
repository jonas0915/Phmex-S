"""Strategy Slot — independent trading unit with its own positions, P&L, and strategy."""
import os
import json
import time
from dataclasses import dataclass, field
from config import Config
from risk_manager import RiskManager
from logger import setup_logger

logger = setup_logger()


@dataclass
class StrategySlot:
    """An independent trading unit. Each slot has its own strategy, timeframe,
    positions, P&L tracking, and kill switch. Multiple slots run sequentially
    in the main bot loop — never threaded."""

    slot_id: str              # e.g., "5m_scalp", "5m_mean_revert"
    strategy_name: str        # key in STRATEGIES dict
    timeframe: str            # "5m", "1h", "4h"
    max_positions: int = 2
    capital_pct: float = 0.5  # fraction of total balance allocated to this slot
    enabled: bool = True
    paper_mode: bool = False  # if True, track signals but don't place real orders

    def __post_init__(self):
        # Each slot gets its own RiskManager (separate positions, P&L, Kelly)
        state_file = f"trading_state_{self.slot_id}.json"
        self.risk = RiskManager(state_file=state_file)
        self.htf_cache: dict = {}
        self.pair_cooldown: dict = {}
        self.pair_loss_streak: dict = {}
        self.last_entry_time: float = 0.0
        self.regime_pause_until: float = 0.0
        self.total_signals: int = 0
        self.total_entries: int = 0

    @property
    def is_active(self) -> bool:
        return self.enabled and not self.is_killed

    @property
    def is_killed(self) -> bool:
        """Kill switch: negative Kelly after 50+ trades → auto-disable."""
        if len(self.risk.closed_trades) < 50:
            return False
        kelly = self.risk.calculate_kelly_raw()
        if kelly < 0:
            logger.warning(f"[KILL SWITCH] Slot '{self.slot_id}' disabled — negative Kelly ({kelly:.3f}) after {len(self.risk.closed_trades)} trades")
            return True
        return False

    def get_available_margin(self, total_balance: float) -> float:
        """How much margin this slot can use, based on its capital allocation."""
        allocated = total_balance * self.capital_pct
        used = sum(p.margin for p in self.risk.positions.values())
        return max(0, allocated - used)

    def has_position(self, symbol: str) -> bool:
        return symbol in self.risk.positions

    def can_enter(self, symbol: str, all_slots: list) -> bool:
        """Check if this slot can enter a position on the given symbol.
        Prevents opposing positions across slots on the same symbol."""
        if symbol in self.risk.positions:
            return False  # already have a position in this slot
        if len(self.risk.positions) >= self.max_positions:
            return False  # slot full
        return True

    def check_position_conflict(self, symbol: str, side: str, all_slots: list) -> bool:
        """Return True if another slot holds an OPPOSING position on this symbol.
        Same-direction is allowed; opposing is blocked."""
        for slot in all_slots:
            if slot.slot_id == self.slot_id:
                continue
            if symbol in slot.risk.positions:
                other_side = slot.risk.positions[symbol].side
                if other_side != side:
                    logger.info(f"[CONFLICT] Slot '{self.slot_id}' wants {side} {symbol} but slot '{slot.slot_id}' holds {other_side} — BLOCKED")
                    return True
        return False

    def stats_summary(self) -> dict:
        """Quick stats for dashboard/logging."""
        trades = self.risk.closed_trades
        if not trades:
            return {"slot": self.slot_id, "trades": 0, "wr": 0, "pnl": 0, "kelly": 0}
        wins = sum(1 for t in trades if t.get("pnl_usdt", 0) > 0)
        pnl = sum(t.get("pnl_usdt", 0) for t in trades)
        return {
            "slot": self.slot_id,
            "trades": len(trades),
            "wr": round(wins / len(trades) * 100, 1),
            "pnl": round(pnl, 2),
        }
