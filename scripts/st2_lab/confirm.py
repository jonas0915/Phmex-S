"""Self-closing forward adjudication for ST2.0 lab hypotheses (Phase 2).

Registers Step-1 gate survivors (+ a permanent LIVE entry) and, each daily run,
advances a SCREEN (forward-OOS replay, "screening NOT truth") and an authoritative
TRUTH (real live-fill subset) verdict, auto-closing accruing -> confirm/reject.

ISOLATION: pure stdlib; never imports bot.py / main.py / loop.py. A CONFIRM is a
human-gated recommendation — this module never deploys anything.
"""
from __future__ import annotations

from . import config as C
from . import features as feat
from . import proposer

_EXIT_KEYS = ("sl_pct", "tp_pct", "hold_secs")
_ENTRY_KEYS = ("imb_min", "br_min", "min_trades")


def _raw_field_filters_only(cfg: dict) -> bool:
    """True if no filter code references an engineered features.py key (those are
    undefined on the single-snapshot real-trade records, so TRUTH can't judge them)."""
    eng = feat.feature_names()
    for f in cfg.get("filters", []) or []:
        code = f.get("code") if isinstance(f, dict) else f
        if any(name in (code or "") for name in eng):
            return False
    return True


def truth_eligible(cfg: dict, live_config: dict | None) -> bool:
    """TRUTH-judgeable on existing real trades iff: live baseline known, exits equal
    live, entry stricter-or-equal live, and filters use raw fields only."""
    if not live_config:
        return False
    lp, cp = live_config.get("params", {}), cfg.get("params", {})
    if any(cp.get(k) != lp.get(k) for k in _EXIT_KEYS):
        return False
    if any((cp.get(k, 0) or 0) < (lp.get(k, 0) or 0) for k in _ENTRY_KEYS):
        return False
    return _raw_field_filters_only(cfg)


def classify_kind(cfg: dict, live_config: dict | None) -> str:
    return "filter" if truth_eligible(cfg, live_config) else "base"


def _new_hypothesis(hid: str, cfg: dict, kind: str, registered_ts: int,
                    run_count: int, truth_applicable: bool) -> dict:
    return {
        "id": hid,
        "config": {"params": dict(cfg.get("params", {})),
                   "filters": list(cfg.get("filters", []) or []),
                   "symbols": cfg.get("symbols")},
        "kind": kind,
        "registered_ts": int(registered_ts),
        "registered_run": int(run_count),
        "screen": {"trades": 0, "expectancy": 0.0, "deflated_sharpe": 0.0,
                   "status": "accruing", "updated_ts": 0},
        "truth": {"applicable": bool(truth_applicable), "considered": 0, "kept": 0,
                  "dropped": 0, "expectancy": 0.0, "ci": [0.0, 0.0],
                  "status": "accruing", "updated_ts": 0},
        "verdict": "accruing",
    }


def ensure_live_entry(champ: dict, registered_ts: int) -> None:
    """Guarantee a permanent id=='LIVE' registry entry (TRUTH = all real trades)."""
    reg = champ.setdefault("confirm_registry", [])
    if any(h["id"] == "LIVE" for h in reg):
        return
    live_cfg = champ.get("live_config") or {"params": {}, "filters": [], "symbols": None}
    reg.append(_new_hypothesis("LIVE", live_cfg, "live", registered_ts,
                               champ.get("run_count", 0), truth_applicable=True))


def register_if_survivor(champ: dict, cfg: dict, registered_ts: int, run_count: int) -> bool:
    """Add cfg to confirm_registry (deduped by config_hash). Returns True if new."""
    reg = champ.setdefault("confirm_registry", [])
    hid = proposer.config_hash(cfg)
    if any(h["id"] == hid for h in reg):
        return False
    live_config = champ.get("live_config")
    kind = classify_kind(cfg, live_config)
    reg.append(_new_hypothesis(hid, cfg, kind, registered_ts, run_count,
                               truth_applicable=truth_eligible(cfg, live_config)))
    # bound non-LIVE entries (keep newest by registered_run)
    cap = champ.get("loop", {}).get("registry_cap", C.DEFAULTS["registry_cap"])
    non_live = [h for h in reg if h["id"] != "LIVE"]
    if len(non_live) > cap:
        non_live.sort(key=lambda h: h["registered_run"])
        drop = {id(h) for h in non_live[:len(non_live) - cap]}
        champ["confirm_registry"] = [h for h in reg if id(h) not in drop]
    return True
