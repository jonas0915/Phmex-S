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
from . import walkforward as wf
from . import stats
from .evaluator import evaluate_with_trades

_ADVERSE = dict(C.ADVERSE_FILL, enabled=True)

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


def _forward(by_symbol: dict, after_ts: int) -> dict:
    out = {}
    for sym, recs in by_symbol.items():
        kept = [r for r in recs if r.get("ts", 0) > after_ts]
        if kept:
            out[sym] = kept
    return out


def screen_verdict(hyp: dict, by_symbol: dict, loop_cfg: dict) -> dict:
    """Forward-OOS replay on snapshots with ts > registered_ts. Self-closes to
    'pass' (walk-forward majority-positive AND deflated-Sharpe >= dsr_min) or 'fail'
    once >= screen_min_trades forward trades exist; else 'accruing'. SCREEN is
    'screening, NOT truth' (modeled adverse fills)."""
    s = hyp["screen"]
    fwd = _forward(by_symbol, hyp["registered_ts"])
    cfg = hyp["config"]
    n_windows = loop_cfg.get("wf_windows", C.DEFAULTS["wf_windows"])
    embargo = loop_cfg.get("wf_embargo_secs", C.DEFAULTS["wf_embargo_secs"])
    min_tr = loop_cfg.get("wf_min_trades", C.DEFAULTS["wf_min_trades"])
    dsr_min = loop_cfg.get("dsr_min", C.DEFAULTS["dsr_min"])
    need = loop_cfg.get("screen_min_trades", C.DEFAULTS["screen_min_trades"])

    win_exps, total_trades, sharpes = [], 0, []
    try:
        splits = wf.walk_forward_splits(fwd, n_windows, embargo) if fwd else []
    except ValueError:
        splits = []
    for sp in splits:
        m, trades = evaluate_with_trades(cfg, sp["test"], loop_cfg, adverse=_ADVERSE)
        if m.trades >= min_tr:
            win_exps.append(m.expectancy)
            total_trades += m.trades
            nets = [t["net"] for t in trades]
            mean = sum(nets) / len(nets)
            sd = (sum((x - mean) ** 2 for x in nets) / len(nets)) ** 0.5
            sharpes.append(mean / sd if sd > 0 else 0.0)

    s["trades"] = total_trades
    s["expectancy"] = round(sum(win_exps) / len(win_exps), 6) if win_exps else 0.0
    s["updated_ts"] = max([hyp["registered_ts"]] +
                          [r["ts"] for recs in fwd.values() for r in recs])
    if total_trades < need or not win_exps:
        s["status"] = "accruing"
        return s
    majority_pos = sum(1 for e in win_exps if e > 0) > len(win_exps) / 2
    agg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0
    var_sh = (sum((x - agg_sharpe) ** 2 for x in sharpes) / len(sharpes)) if len(sharpes) > 1 else 1.0
    dsr = stats.deflated_sharpe_ratio(agg_sharpe, max(total_trades, 2),
                                      max(len(sharpes), 1), var_sh or 1.0)
    s["deflated_sharpe"] = round(dsr, 6)
    s["status"] = "pass" if (majority_pos and dsr >= dsr_min) else "fail"
    return s
