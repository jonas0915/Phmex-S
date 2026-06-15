"""Champion store — the recursive state. Pure JSON IO in the lab dir."""
from __future__ import annotations

import json
import os
import copy

from . import config as C


def load() -> dict:
    """Load the current champion, or seed from DEFAULT_CHAMPION on first run."""
    if not os.path.exists(C.CHAMPION_FILE):
        champ = copy.deepcopy(C.DEFAULT_CHAMPION)
        save(champ)
        return champ
    with open(C.CHAMPION_FILE) as f:
        champ = json.load(f)
    # forward-compat: backfill any missing top-level keys
    for k, v in C.DEFAULT_CHAMPION.items():
        champ.setdefault(k, copy.deepcopy(v))
    champ["loop"] = {**C.DEFAULTS, **champ.get("loop", {})}
    return champ


def save(champ: dict) -> None:
    os.makedirs(C.LAB_DIR, exist_ok=True)
    tmp = C.CHAMPION_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(champ, f, indent=2, sort_keys=True)
    os.replace(tmp, C.CHAMPION_FILE)


def append_lineage(champ: dict, change: str, metrics: dict, iteration: int) -> None:
    """Record one accepted champion transition for auditability."""
    champ.setdefault("lineage", []).append({
        "iter": iteration,
        "change": change,
        "score": metrics.get("net"),
        "trades": metrics.get("trades"),
        "wr": metrics.get("wr"),
    })
    # keep lineage bounded
    champ["lineage"] = champ["lineage"][-200:]
