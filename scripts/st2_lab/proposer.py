"""Proposer — generate candidate mutations of the champion.

Deterministic (no RNG — Math.random/Date are unavailable in this runtime and
determinism keeps the loop reproducible/resumable). Each iteration rotates
through the mutation space so successive runs explore different candidates.

Two mutation kinds:
  * param neighbors  — perturb one numeric param by +/- one step within bounds
  * filter mutations — add one curated safe entry-filter, or drop an existing one

All proposed filters come from a curated library of expressions that are known
to compile under safe_exec (the AST-restricted interpreter). An optional LLM
proposer can be layered on later behind the same interface; the curated library
keeps the loop fully autonomous and safe without an external call in the
scheduled job.
"""
from __future__ import annotations

import copy
import hashlib

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


def _clamp(name: str, val):
    lo, hi, _ = C.PARAM_BOUNDS[name]
    return max(lo, min(hi, val))


def _with_change(champ: dict, change: str) -> dict:
    c = copy.deepcopy(champ)
    c.pop("_change", None)
    c["_change"] = change
    return c


def propose(champ: dict, k: int, iteration: int = 0) -> list[dict]:
    """Return up to k candidate configs (deep copies, each tagged ['_change'])."""
    cands: list[dict] = []

    # 1) param neighbors: +/- one step per param, within bounds
    for name, (lo, hi, step) in C.PARAM_BOUNDS.items():
        cur = champ["params"].get(name)
        if cur is None:
            continue
        for delta in (step, -step):
            nv = _clamp(name, round(cur + delta, 6))
            if nv == cur:
                continue
            c = _with_change(champ, f"{name} {cur} -> {nv}")
            c["params"][name] = nv
            cands.append(c)

    # 2) filter additions (curated library, not already present)
    present = {f.get("code") for f in champ.get("filters", []) if isinstance(f, dict)}
    for code in FILTER_LIBRARY:
        if code in present:
            continue
        try:
            compile_filter(code)  # safety: only propose compilable filters
        except Rejection:
            continue
        c = _with_change(champ, f"+filter: {code}")
        c["filters"] = list(champ.get("filters", [])) + [_filter_entry(code)]
        cands.append(c)

    # 3) filter removals (let the loop shed a filter that no longer helps)
    for i, f in enumerate(champ.get("filters", []) or []):
        code = f.get("code") if isinstance(f, dict) else f
        c = _with_change(champ, f"-filter: {code}")
        c["filters"] = [g for j, g in enumerate(champ["filters"]) if j != i]
        cands.append(c)

    if not cands:
        return []
    # rotate by iteration so each run explores a different slice, then take k
    off = iteration % len(cands)
    rotated = cands[off:] + cands[:off]
    return rotated[:k]
