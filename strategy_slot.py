"""Strategy Slot — independent trading unit with its own positions, P&L, and strategy."""
import os
import json
import time
from dataclasses import dataclass, field
from config import Config
from risk_manager import RiskManager
from logger import setup_logger

logger = setup_logger()

LIVE_LOSS_CAP_USDT = -5.0      # auto-demote when live net PnL breaches this
LIVE_KELLY_MIN_TRADES = 10     # negative-kelly demote needs at least this many live trades


def _trade_net(t: dict) -> float:
    """Net PnL of a closed trade — fees included when recorded (net_pnl), gross fallback."""
    v = t.get("net_pnl")
    return float(v) if v is not None else float(t.get("pnl_usdt", 0))


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
    trade_amount_usdt: float = None  # per-slot margin override; None = Config.TRADE_AMOUNT_USDT
    loss_cap_usdt: float = LIVE_LOSS_CAP_USDT  # per-slot auto-demote loss cap
    kelly_min_trades: int = LIVE_KELLY_MIN_TRADES  # per-slot: live trades before neg-Kelly demote arms
    adverse_exit_roi: float = None   # per-slot adverse-exit ROI threshold (e.g. ST2.0 -6.0 loss-cut);
                                     # None = global Config.ADVERSE_EXIT_THRESHOLD (-999 = disabled)
    adverse_exit_cycles: int = None  # cycles before the per-slot adverse-exit arms; None = Config default
    sl_percent: float = None         # per-slot SL % override passed to open_position (2026-07-18,
                                     # HTF_L2_PAPER); None = inherit Config.STOP_LOSS_PERCENT
    tp_percent: float = None         # per-slot TP % override; None = inherit Config.TAKE_PROFIT_PERCENT
    durable_trail_enabled: bool = False  # per-slot opt-in: ratchet the resting exchange SL up as the
                                         # trail arms (Config.TRAIL_ARM_ROI), mirroring the main-bot durable trail.
                                         # The amend rests on Phemex, so the profit-lock survives a host
                                         # sleep — unlike software exits. LIVE slots only. Off = no change.
    requote_attempts: int = 0  # per-slot opt-in (2026-07-01): on a PostOnly entry miss,
                               # re-place up to N maker orders at the fresh touch (never
                               # taker), drift-capped by Config.SLOT_REQUOTE_MAX_DRIFT_PCT.
                               # 0 = give up after the first miss (pre-existing behavior).
    entry_patience_s: float = None  # per-slot opt-in (2026-07-03): how long the PostOnly
                                    # entry rests before cancel. None = exchange default
                                    # (20s). 5m_mean_revert runs 45s — mean-reversion
                                    # fills on the way back (9/11 missed winners returned
                                    # through the limit within 60s); main bot stays 20s
                                    # (its patience buys back-of-queue toxic fills).

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
        # Shadow-only: extra rejection counters (used by narrow-filter slots like 5m_narrow).
        # Persisted to a sidecar file so it survives restarts without touching RiskManager schema.
        self._blocked_sidecar = os.path.join(
            os.path.dirname(__file__), f"trading_state_{self.slot_id}_blocked.json"
        )
        self.blocked_counts: dict = self._load_blocked_counts()
        self.promoted_at: float = 0.0
        self._mode_sidecar = os.path.join(
            os.path.dirname(__file__), f"trading_state_{self.slot_id}_mode.json"
        )
        self._load_mode()

    def _load_blocked_counts(self) -> dict:
        try:
            if os.path.exists(self._blocked_sidecar):
                with open(self._blocked_sidecar) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception as e:
            logger.debug(f"[SLOT] {self.slot_id} could not load blocked_counts: {e}")
        return {}

    def bump_blocked(self, tag: str) -> None:
        """Increment a rejection counter and persist. Never raises."""
        try:
            self.blocked_counts[tag] = int(self.blocked_counts.get(tag, 0)) + 1
            with open(self._blocked_sidecar, "w") as f:
                json.dump(self.blocked_counts, f)
        except Exception as e:
            logger.debug(f"[SLOT] {self.slot_id} bump_blocked({tag}) failed: {e}")

    def _load_mode(self) -> None:
        """Restore promotion state across restarts (constructor defaults are paper)."""
        try:
            if os.path.exists(self._mode_sidecar):
                with open(self._mode_sidecar) as f:
                    data = json.load(f)
                self.paper_mode = bool(data.get("paper_mode", self.paper_mode))
                self.capital_pct = float(data.get("capital_pct", self.capital_pct))
                self.promoted_at = float(data.get("promoted_at", 0.0))
        except Exception as e:
            logger.warning(f"[SLOT] {self.slot_id} mode sidecar load failed: {e}")
        self._sync_risk_semantics()

    def _sync_risk_semantics(self) -> None:
        """Keep the slot's RiskManager record/log semantics in step with slot mode.
        A promoted slot must record like live (gross pnl_usdt, real fees, no sim
        fee subtraction) and log without the [PAPER] prefix — mirrors the
        derivation at RiskManager.__init__ (risk_manager.py:269-270)."""
        self.risk.is_paper = self.paper_mode
        self.risk._log_prefix = "[PAPER] " if self.paper_mode else ""

    def _save_mode(self) -> None:
        try:
            tmp = self._mode_sidecar + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"paper_mode": self.paper_mode,
                           "capital_pct": self.capital_pct,
                           "promoted_at": self.promoted_at,
                           "loss_cap_usdt": self.loss_cap_usdt,
                           "trade_amount_usdt": self.trade_amount_usdt,
                           "kelly_min_trades": self.kelly_min_trades}, f)
            os.replace(tmp, self._mode_sidecar)
        except Exception as e:
            logger.warning(f"[SLOT] {self.slot_id} mode sidecar save failed: {e}")

    def set_live(self, capital_pct: float = None) -> None:
        self.paper_mode = False
        if capital_pct is not None:
            self.capital_pct = capital_pct
        self.promoted_at = time.time()
        self._sync_risk_semantics()
        self._save_mode()

    def set_paper(self) -> None:
        self.paper_mode = True
        self.capital_pct = 0.0
        self._sync_risk_semantics()
        self._save_mode()

    def live_trades(self) -> list:
        return [t for t in self.risk.closed_trades if t.get("mode") == "live"]

    def live_pnl(self) -> float:
        return sum(_trade_net(t) for t in self.live_trades())

    def should_auto_demote(self) -> tuple:
        """(demote: bool, reason: str). Checked after every live close."""
        trades = self.live_trades()
        pnl = sum(_trade_net(t) for t in trades)
        if pnl <= self.loss_cap_usdt:
            return True, f"live loss cap: ${pnl:.2f} <= ${self.loss_cap_usdt:.2f}"
        if len(trades) >= self.kelly_min_trades:
            wins = [_trade_net(t) for t in trades if _trade_net(t) > 0]
            losses = [abs(_trade_net(t)) for t in trades if _trade_net(t) < 0]
            if losses and wins:
                wr = len(wins) / len(trades)
                rr = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
                kelly = wr - (1 - wr) / rr
            elif not wins:
                kelly = -1.0
            else:
                kelly = 1.0
            if kelly < 0:
                return True, f"negative live Kelly ({kelly:.3f}) after {len(trades)} live trades"
        return False, ""

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
            # DEBUG not WARNING: this property is evaluated every cycle, so a killed
            # slot spammed ~1.6k WARNING lines/day (46% of all warnings, 2026-06-23 audit).
            # The actual auto-demote/disable is handled once at bot.py:_check_slot_demote.
            logger.debug(f"[KILL SWITCH] Slot '{self.slot_id}' disabled — negative Kelly ({kelly:.3f}) after {len(self.risk.closed_trades)} trades")
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
        wins = sum(1 for t in trades if _trade_net(t) > 0)
        pnl = sum(_trade_net(t) for t in trades)
        return {
            "slot": self.slot_id,
            "trades": len(trades),
            "wr": round(wins / len(trades) * 100, 1),
            "pnl": round(pnl, 2),
        }
