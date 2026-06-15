"""Lab paths, constants, and shared types. No bot.py imports (isolation invariant)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict

# ── paths ──────────────────────────────────────────────────────────────
BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAB_DIR = os.path.join(BOT_DIR, "scripts", "st2_lab")
FLOW_CAPTURE = os.path.join(BOT_DIR, "logs", "flow_capture.jsonl")
CHAMPION_FILE = os.path.join(LAB_DIR, "champion.json")
DIGEST_LOG = os.path.join(BOT_DIR, "logs", "st2_lab.log")
HALT_FLAG = os.path.join(LAB_DIR, ".halt")
PROPOSALS_DIR = os.path.join(BOT_DIR, "docs", "fix-proposals")

# ── live ST2.0 economics (mirrors live for relative fidelity) ───────────
LEVERAGE = 10
MARGIN_USDT = 10.0
# Round-trip fee as % of notional. ST2.0 targets maker-maker (~0.02% each side).
# Used consistently across candidates — this is a RELATIVE-ranking sandbox, not
# an absolute-PnL forecaster (see spec; backtesting this data only makes artifacts).
FEE_RT_PCT = 0.04

# ── loop tuning (override in champion.json["loop"]) ─────────────────────
DEFAULTS = {
    "candidates_per_iter": 6,   # K mutations proposed each iteration
    "improve_margin": 0.10,     # winner must beat champion score by this fraction
    "min_trades_eval": 15,      # a config needs >= this many sim trades to be rankable
    "confirm_sample": 30,       # paper-confirm trades before a live proposal
}

# ── the ST2.0 config genome the loop evolves ────────────────────────────
DEFAULT_CHAMPION = {
    "params": {
        "imb_min": 0.30,      # bid-heavy book threshold
        "br_min": 0.60,       # heavy buying-into-it threshold
        "min_trades": 8,      # tape must be real
        "hold_secs": 900,     # ~15 min fixed maker hold
        "sl_pct": 1.2,        # stop (short: above entry)
        "tp_pct": 1.6,        # take-profit (short: below entry)
    },
    "filters": [],            # list of {id, code, hash} pure entry-veto fns (Phase 2)
    "metrics": {},            # last sandbox metrics
    "lineage": [],            # [{iter, parent, change, score}]
    "loop": dict(DEFAULTS),
}

# parameter search bounds the deterministic mutator stays within
PARAM_BOUNDS = {
    "imb_min":    (0.15, 0.50, 0.05),   # (lo, hi, step)
    "br_min":     (0.50, 0.80, 0.05),
    "min_trades": (4, 30, 2),
    "hold_secs":  (300, 1800, 300),
    "sl_pct":     (0.6, 3.0, 0.2),
    "tp_pct":     (0.8, 3.0, 0.2),
}


@dataclass
class Metrics:
    """Relative-ranking metrics for one config over the replay dataset."""
    trades: int = 0
    wins: int = 0
    losses: int = 0
    net: float = 0.0
    wr: float = 0.0
    kelly: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    rankable: bool = False   # met min_trades_eval

    def score(self) -> float:
        """Single comparable score for ranking. Net PnL is the primary objective;
        unrankable (too few trades) sorts to the bottom."""
        if not self.rankable:
            return float("-inf")
        return self.net

    def to_dict(self) -> dict:
        return asdict(self)
