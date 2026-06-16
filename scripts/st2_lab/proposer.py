"""Proposer — generate candidate mutations of the champion.

Deterministic (no RNG — Math.random/Date are unavailable in this runtime and
determinism keeps the loop reproducible/resumable). Each iteration rotates
through the mutation space so successive runs explore different candidates.

The loop passes the set of config fingerprints it has ALREADY tried; the proposer
skips those (don't re-test known dead-ends) and, when the shallow single-change
neighbourhood is exhausted, escalates to COMPOUND (two-change) candidates so the
search keeps finding genuinely new ground instead of going inert. This is what
lets the loop learn from its mistakes and keep improving past a local plateau.

Two mutation kinds:
  * param neighbors  — perturb one numeric param by +/- one step within bounds
  * filter mutations — add one curated safe entry-filter, or drop an existing one

All proposed filters come from a curated library of expressions known to compile
under safe_exec (the AST-restricted interpreter). An optional LLM proposer can be
layered behind the same interface later.
"""
from __future__ import annotations

import copy
import hashlib
import json

from . import config as C
from .safe_exec import compile_filter, Rejection

# Curated entry-filter vetoes (each returns True = ALLOW the short).
FILTER_LIBRARY = [
    "not divergence_bullish",      # don't short into a bullish divergence
    "cvd_slope <= 0.5",            # avoid shorting into strong buy momentum
    "large_trade_bias <= 0.0",     # whales not net buying
    "spread_pct <= 0.05",          # liquid books only
    "buy_ratio <= 0.85",           # skip blow-off extremes
    "imbalance <= 0.45",           # avoid the most lopsided (often breakout) books
]


def _hash(code: str) -> str:
    return hashlib.sha1(code.encode()).hexdigest()[:10]


def _filter_entry(code: str) -> dict:
    return {"id": _hash(code), "code": code, "hash": _hash(code)}


def config_hash(cfg: dict) -> str:
    """Canonical fingerprint of a config (params + filter SET, order-independent).
    Shared with the loop so 'tried' membership and history hashes always agree."""
    payload = json.dumps(
        {"params": cfg.get("params"),
         "filters": sorted(f.get("code") for f in cfg.get("filters", []) if isinstance(f, dict))},
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def _clamp(name: str, val):
    lo, hi, _ = C.PARAM_BOUNDS[name]
    return max(lo, min(hi, val))


def _moves(champ: dict) -> list:
    """Atomic moves available from this champion: (label, kind, payload)."""
    moves = []
    for name, (lo, hi, step) in C.PARAM_BOUNDS.items():
        cur = champ["params"].get(name)
        if cur is None:
            continue
        for delta in (step, -step):
            nv = _clamp(name, round(cur + delta, 6))
            if nv == cur:
                continue
            moves.append((f"{name} {cur} -> {nv}", "param", (name, nv)))
    present = {f.get("code") for f in champ.get("filters", []) if isinstance(f, dict)}
    for code in FILTER_LIBRARY:
        if code in present:
            continue
        try:
            compile_filter(code)  # safety: only propose compilable filters
        except Rejection:
            continue
        moves.append((f"+filter: {code}", "addfilter", code))
    for i, f in enumerate(champ.get("filters", []) or []):
        code = f.get("code") if isinstance(f, dict) else f
        moves.append((f"-filter: {code}", "rmfilter", i))
    return moves


def _apply_move(base: dict, move) -> dict:
    """Apply one move onto a base config; returns a new config. Composable: the
    _change label accumulates so compound candidates read 'A + B'."""
    label, kind, payload = move
    c = copy.deepcopy(base)
    prev = c.pop("_change", None)
    c["_change"] = f"{prev} + {label}" if prev else label
    if kind == "param":
        c["params"][payload[0]] = payload[1]
    elif kind == "addfilter":
        c["filters"] = list(base.get("filters", [])) + [_filter_entry(payload)]
    elif kind == "rmfilter":
        c["filters"] = [g for j, g in enumerate(base.get("filters", []) or []) if j != payload]
    return c


def _single_step_candidates(champ: dict) -> list:
    return [_apply_move(champ, m) for m in _moves(champ)]


def _compatible(a, b) -> bool:
    """Two moves combine only if they don't conflict. Removals stay single-step
    (more interpretable), and we never perturb the same param or add a filter twice."""
    (_, ka, pa), (_, kb, pb) = a, b
    if "rmfilter" in (ka, kb):
        return False
    if ka == "param" and kb == "param" and pa[0] == pb[0]:
        return False
    if ka == "addfilter" and kb == "addfilter" and pa == pb:
        return False
    return True


def _compound_candidates(champ: dict) -> list:
    """Two-change candidates — used when the single-change neighbourhood is
    exhausted, to escape a local plateau where no single step helps but a pair does."""
    moves = _moves(champ)
    out = []
    for i in range(len(moves)):
        for j in range(i + 1, len(moves)):
            if not _compatible(moves[i], moves[j]):
                continue
            out.append(_apply_move(_apply_move(champ, moves[i]), moves[j]))
    return out


def propose(champ: dict, k: int, iteration: int = 0, tried=None) -> list[dict]:
    """Up to k candidate configs (deep copies, each tagged ['_change']).

    Skips configs in `tried` (already-evaluated dead-ends — learn from mistakes).
    If the single-change pool is thinner than k after that, tops up with compound
    (two-change) candidates so each run keeps exploring NEW ground (keep improving)."""
    tried = tried or set()
    pool = [c for c in _single_step_candidates(champ) if config_hash(c) not in tried]
    if len(pool) < k:
        seen = {config_hash(c) for c in pool}
        for c in _compound_candidates(champ):
            h = config_hash(c)
            if h in tried or h in seen:
                continue
            pool.append(c)
            seen.add(h)
    if not pool:
        return []
    # rotate by iteration so each run explores a different slice, then take k
    off = iteration % len(pool)
    rotated = pool[off:] + pool[:off]
    return rotated[:k]
