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
from . import safe_exec
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
    """Guarantee a permanent id=='LIVE' registry entry (TRUTH = all real trades), and
    keep its config in sync with champ['live_config']. The sync matters because LIVE
    can be registered (in an early run) BEFORE a human sets live_config — leaving it
    with empty params that crash the SCREEN evaluator (KeyError sl_pct). Re-syncing
    self-heals that stale entry and tracks any later live_config change."""
    reg = champ.setdefault("confirm_registry", [])
    live_cfg = champ.get("live_config") or {"params": {}, "filters": [], "symbols": None}
    synced = {"params": dict(live_cfg.get("params", {})),
              "filters": list(live_cfg.get("filters", []) or []),
              "symbols": live_cfg.get("symbols")}
    existing = next((h for h in reg if h["id"] == "LIVE"), None)
    if existing is not None:
        if existing.get("config") != synced:
            existing["config"] = synced
        return
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


def _entry_ok(rec: dict, p: dict) -> bool:
    return (rec.get("imbalance", 0.0) >= p.get("imb_min", 0.0)
            and rec.get("buy_ratio", 0.0) >= p.get("br_min", 0.0)
            and rec.get("trade_count", 0) >= p.get("min_trades", 0))


def _passes_candidate(rec: dict, cfg: dict, filter_fns) -> bool:
    if not _entry_ok(rec, cfg.get("params", {})):
        return False
    for fn in filter_fns:
        if not fn(rec):
            return False
    return True


def truth_verdict(hyp: dict, real_records: list, live_config: dict | None,
                  loop_cfg: dict) -> dict:
    """Real-fill verdict. LIVE -> all real trades. Filter-kind -> the kept subset
    (entry + raw filters applied to each real trade's recorded conditions). Base /
    ineligible -> applicable False, stays accruing. Self-closes at >= confirm_sample
    kept: confirm (CI lower > 0) / reject (CI upper < 0) / else accruing."""
    t = hyp["truth"]
    need = loop_cfg.get("confirm_sample", C.DEFAULTS["confirm_sample"])
    t["considered"] = len(real_records)

    if hyp["id"] == "LIVE":
        kept = list(real_records)
    elif t.get("applicable") and truth_eligible(hyp["config"], live_config):
        try:
            fns = [safe_exec.compile_filter(f.get("code") if isinstance(f, dict) else f)
                   for f in hyp["config"].get("filters", []) or []]
        except safe_exec.Rejection:
            t["applicable"] = False
            t["status"] = "accruing"
            return t
        kept = [r for r in real_records if _passes_candidate(r, hyp["config"], fns)]
    else:
        t["applicable"] = False
        t["status"] = "accruing"
        return t

    t["applicable"] = True
    t["kept"] = len(kept)
    t["dropped"] = len(real_records) - len(kept)
    nets = [float(r.get("net", 0.0)) for r in kept]
    t["expectancy"] = sum(nets) / len(nets) if nets else 0.0
    if len(kept) < need or not nets:
        t["status"] = "accruing"
        t["ci"] = [0.0, 0.0]
        return t
    lo, hi = stats.bootstrap_diff_ci(nets, [0.0], seed=0)
    t["ci"] = [round(lo, 6), round(hi, 6)]
    t["status"] = "confirm" if lo > 0 else ("reject" if hi < 0 else "accruing")
    return t


def _verdict_for(hyp: dict) -> str:
    t, s = hyp["truth"], hyp["screen"]
    if t.get("applicable") and t["status"] in ("confirm", "reject"):
        return "truth_" + t["status"]
    if s["status"] in ("pass", "fail"):
        return "screen_" + s["status"]
    return "accruing"


def tick(champ: dict, by_symbol: dict, real_records: list) -> list:
    """Advance SCREEN + TRUTH for every registered hypothesis; set verdict; return
    NEW verdict transitions (deduped on change). TRUTH is authoritative over SCREEN."""
    loop_cfg = champ.get("loop", dict(C.DEFAULTS))
    live_config = champ.get("live_config")
    transitions = []
    for hyp in champ.setdefault("confirm_registry", []):
        screen_verdict(hyp, by_symbol, loop_cfg)
        truth_verdict(hyp, real_records, live_config, loop_cfg)
        new_v = _verdict_for(hyp)
        old_v = hyp.get("verdict", "accruing")
        hyp["verdict"] = new_v
        if new_v != old_v and new_v != "accruing":
            is_live_reject = (hyp["id"] == "LIVE" and new_v == "truth_reject")
            transitions.append({
                "id": hyp["id"], "from": old_v, "to": new_v, "kind": hyp["kind"],
                "alert": is_live_reject,
                "msg": (f"ST2.0 confirm: {hyp['id']} {old_v} -> {new_v} "
                        f"(truth kept={hyp['truth']['kept']} exp={hyp['truth']['expectancy']:+.4f} "
                        f"ci={hyp['truth']['ci']}; screen={hyp['screen']['status']})"),
            })
    return transitions
