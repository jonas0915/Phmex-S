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

# recursive-learning memory: how many attempt records to retain in champion.json.
# Each iteration records every candidate it evaluated (accepted AND rejected) so
# the loop has a durable memory of what it already tried — its mistakes included.
HISTORY_CAP = 500
# how many distinct config fingerprints to remember as already-tried (so the loop
# skips re-testing known dead-ends). Reset when the dataset grows (new evidence).
TRIED_CAP = 5000

# ── live ST2.0 economics (mirrors live for relative fidelity) ───────────
LEVERAGE = 10
MARGIN_USDT = 10.0
# Round-trip fee as % of notional. ST2.0 targets maker-maker (~0.02% each side).
# Used consistently across candidates — this is a RELATIVE-ranking sandbox, not
# an absolute-PnL forecaster (see spec; backtesting this data only makes artifacts).
FEE_RT_PCT = 0.04

# ── loop tuning (override in champion.json["loop"]) ─────────────────────
DEFAULTS = {
    "candidates_per_iter": 6,   # K param/curated mutations proposed each iteration
    "diag_filters": 4,          # max diagnostic (loss-cluster) filters proposed per iter
    "train_frac": 0.7,          # chronological train fraction; rest is out-of-sample test
    "improve_margin": 0.10,     # winner must beat champion score by this fraction
    "min_trades_eval": 15,      # a config needs >= this many sim trades to be rankable
    "confirm_sample": 30,       # paper-confirm trades before a live proposal
}

# ── the ST2.0 config genome the loop evolves ────────────────────────────
DEFAULT_CHAMPION = {
    "params": {
        "imb_min": 0.35,      # bid-heavy book threshold (mirrors LIVE ST2.0; recursion climbs from here)
        "br_min": 0.60,       # heavy buying-into-it threshold
        "min_trades": 8,      # tape must be real
        "hold_secs": 900,     # ~15 min fixed maker hold
        "sl_pct": 1.2,        # stop (short: above entry)
        "tp_pct": 1.6,        # take-profit (short: below entry)
    },
    "filters": [],            # list of {id, code, hash} pure entry-veto fns (Phase 2)
    "symbols": None,          # None = all symbols; or a list e.g. ["ETH/USDT:USDT"]
    "metrics": {},            # last sandbox metrics (refreshed EVERY run)
    "lineage": [],            # accepted transitions only [{iter, change, score, ...}]
    "history": [],            # EVERY candidate evaluated (incl. rejected) — learning memory
    "run_count": 0,           # iterations executed; advances exploration every run
    "tried": [],              # config fingerprints already evaluated (skip dead-ends)
    "data_epoch": 0,          # max ts of the dataset last explored; grows -> reset tried
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
    net: float = 0.0              # sandbox total, 100%-fill UPPER BOUND
    expectancy: float = 0.0       # net / trades — the ranking objective
    wr: float = 0.0
    kelly: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    rankable: bool = False        # met min_trades_eval

    def score(self) -> float:
        """Rank by PER-TRADE EXPECTANCY, not total net. Ranking by total net
        rewards configs that simply fire more often — which is meaningless (worse,
        actively misleading) for a maker strategy that only fills ~43% of signals.
        Expectancy is fill-robust: firing more does not inflate it. Unrankable
        (too few sim trades) sorts to the bottom."""
        if not self.rankable:
            return float("-inf")
        return self.expectancy

    def fill_adjusted_net(self, fill_rate: float) -> float:
        """Crude lower-ish estimate of real net if only fill_rate of signals filled.
        Approximate (which trades fill is unknown) — for honest framing, not truth."""
        return round(self.net * fill_rate, 4)

    def to_dict(self) -> dict:
        return asdict(self)
