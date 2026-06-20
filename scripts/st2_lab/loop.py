"""Orchestrator — one recursive iteration of the ST2.0 improvement lab.

  load champion -> propose K mutations -> sandbox-evaluate each -> rank ->
  if a candidate beats champion by the margin, it BECOMES the champion
  (autonomous, lab-only) -> if the champion qualifies, write a human-gated
  promotion proposal into docs/fix-proposals/ (the existing proposals-digest
  job verifies + Telegrams it; we never touch the live bot directly).

Run:  python -m scripts.st2_lab.loop --iterations 1
Test: python -m scripts.st2_lab.loop --iterations 3 --limit 40000 --dry-run
"""
from __future__ import annotations

import argparse
import copy
import logging
import os

from . import config as C
from . import champion as champ_store
from . import confirm
from . import notify
from . import dataset as ds
from . import fills as fills_mod
from . import diagnostics
from . import real_trades
from .proposer import propose, _filter_entry, config_hash
from .evaluator import evaluate, evaluate_with_trades
from . import walkforward as wf
from . import stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ST2-LAB] %(levelname)s %(message)s",
    handlers=[logging.FileHandler(C.DIGEST_LOG), logging.StreamHandler()],
)
logger = logging.getLogger("st2_lab")

# Live ST2.0 config we'd be proposing a change *from* (mirror of strategies.py).
LIVE_PARAMS = dict(C.DEFAULT_CHAMPION["params"])

# Phase 1 (2026-06-19): rank EVERY evaluation on the adverse-selection maker-fill
# model, not the 100%-fill fiction that made the sandbox read +0.31/trade while live
# was -0.14. The conservative default (window=1, no maker edge) is harsher than the
# measured ~43% live fill rate — the safe direction for an honest ranking.
_ADVERSE = dict(C.ADVERSE_FILL, enabled=True)


def _halted() -> bool:
    if os.path.exists(C.HALT_FLAG):
        logger.warning("halt flag present (%s) — skipping iteration", C.HALT_FLAG)
        return True
    return False


def _improved(best, champ_metrics, margin: float) -> bool:
    """A candidate improves if it's rankable and beats the champion's per-trade
    EXPECTANCY by the margin (absolute floor so we don't churn on noise). Expectancy
    (not total net) is the objective so 'fires more often' never wins on its own."""
    if not best.rankable:
        return False
    if not champ_metrics.rankable:
        return True
    base = champ_metrics.expectancy
    floor = max(0.005, abs(base) * margin)
    return best.expectancy > base + floor


def _wf_eval(cfg, by_symbol, loop_cfg, n_windows, embargo_secs):
    """Evaluate cfg across purged walk-forward windows on ADVERSE fills. Returns
    (per_window_expectancies, pooled_per_trade_sharpe, pooled_n_trades).
    A window with too few trades to rank contributes None to the expectancy vector
    (so it neither helps nor hurts the majority test)."""
    try:
        splits = wf.walk_forward_splits(by_symbol, n_windows, embargo_secs)
    except ValueError:
        return [None] * n_windows, 0.0, 0
    # Per-window rankability uses a lower trade bar than the single-split eval — ST2.0
    # fires too rarely to clear min_trades_eval inside a single window.
    wf_min = loop_cfg.get("wf_min_trades", loop_cfg.get("min_trades_eval", 15))
    win_cfg = dict(loop_cfg, min_trades_eval=wf_min)
    window_exps, pooled = [], []
    for s in splits:
        m, trades = evaluate_with_trades(cfg, s["test"], win_cfg, adverse=_ADVERSE)
        window_exps.append(m.expectancy if m.rankable else None)
        pooled.extend(t["net"] for t in trades)
    n_obs = len(pooled)
    if n_obs > 1:
        mean = sum(pooled) / n_obs
        var = sum((x - mean) ** 2 for x in pooled) / (n_obs - 1)
        sd = var ** 0.5
        sharpe = (mean / sd) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    return window_exps, sharpe, n_obs


def _robustness_ok(window_exps, champ_mean_oos, cand_sharpe, n_obs, n_trials,
                   var_trial_sharpes, margin=0.10, dsr_min=0.90):
    """Phase-1 walk-forward + deflated-Sharpe acceptance gate. A candidate is robust
    only if it (1) is rankable on at least one window, (2) wins on a MAJORITY of
    rankable windows (regime-luck guard), (3) beats the champion's mean out-of-sample
    expectancy by the margin, and (4) clears a deflated-Sharpe bar that rises with the
    number of candidates tried (multiple-testing / selection correction)."""
    rankable = [e for e in window_exps if e is not None]
    if not rankable:
        return False
    majority_positive = sum(1 for e in rankable if e > 0) > len(rankable) / 2.0
    mean_oos = sum(rankable) / len(rankable)
    beats_champ = mean_oos > champ_mean_oos + max(0.005, abs(champ_mean_oos) * margin)
    dsr = stats.deflated_sharpe_ratio(cand_sharpe, n_obs, n_trials, var_trial_sharpes)
    return bool(majority_positive and beats_champ and dsr >= dsr_min)


def run_iteration(by_symbol=None, iteration=None, dry_run=False) -> dict:
    if _halted():
        return {"halted": True}
    champ = champ_store.load()
    loop_cfg = champ.get("loop", C.DEFAULTS)
    run_count = champ.get("run_count", 0)
    if iteration is None:
        # Drive exploration by run_count, NOT lineage length. Tying it to lineage
        # froze the proposer at iteration 0 whenever nothing was accepted, so every
        # run re-offered the same candidates and the loop never explored new ground.
        iteration = run_count
    if by_symbol is None:
        by_symbol = ds.load_dataset()
    logger.info("iter %d | dataset: %s", iteration, ds.dataset_summary(by_symbol))

    # REAL fill truth — measured from live logs, leads every iteration. The sandbox
    # net below is now ADVERSE-fill-adjusted (not a 100%-fill upper bound); this fill
    # truth remains the ground reference the adverse model is calibrated against.
    fstats = fills_mod.measured_fill_stats()
    fr = fstats["rate"]
    logger.info("FILL TRUTH | %s", fills_mod.format_report(fstats).replace("\n", " | "))

    # Chronological train/test split. Diagnostics + selection happen on TRAIN; a
    # candidate is only accepted if it ALSO beats the champion OUT-OF-SAMPLE on TEST.
    # This is the overfit guard — in-sample-only "wins" (e.g. spread artifacts) die here.
    train, test = ds.chronological_split(by_symbol, loop_cfg.get("train_frac", 0.7))
    logger.info("split | train %s | test %s", ds.dataset_summary(train), ds.dataset_summary(test))

    champ_tr, champ_tr_trades = evaluate_with_trades(champ, train, loop_cfg, adverse=_ADVERSE)
    champ_te = evaluate(champ, test, loop_cfg, adverse=_ADVERSE)
    champ_full = evaluate(champ, by_symbol, loop_cfg, adverse=_ADVERSE)
    logger.info("champion: train exp=%+.4f | test(OOS) exp=%+.4f | full net(UB)=%+.2f fillAdj~%+.2f trades=%d kelly=%.2f",
                champ_tr.expectancy, champ_te.expectancy, champ_full.net,
                champ_full.fill_adjusted_net(fr), champ_full.trades, champ_full.kelly)

    # Phase 1 acceptance-gate inputs: the champion's mean out-of-sample expectancy
    # across purged walk-forward windows is the bar each candidate must clear (on top
    # of the single-split OOS check), plus the deflated-Sharpe selection correction.
    wf_n = loop_cfg.get("wf_windows", 5)
    wf_emb = loop_cfg.get("wf_embargo_secs", 900)
    dsr_min = loop_cfg.get("dsr_min", 0.90)
    champ_we, _csharpe, _cnobs = _wf_eval(champ, by_symbol, loop_cfg, wf_n, wf_emb)
    _crank = [e for e in champ_we if e is not None]
    champ_mean_oos = sum(_crank) / len(_crank) if _crank else 0.0
    logger.info("champion walk-forward | %d/%d windows positive | mean OOS exp=%+.4f",
                sum(1 for e in _crank if e > 0), len(_crank), champ_mean_oos)
    if not _crank:
        logger.warning("walk-forward INCONCLUSIVE — no window cleared wf_min_trades=%d "
                       "(ST2.0 fires too rarely to validate across %d windows yet). The "
                       "robustness gate will accept nothing until the signal fires more or "
                       "more data accrues — this is the honest 'insufficient data' outcome.",
                       loop_cfg.get("wf_min_trades", 8), wf_n)

    existing = {f.get("code") for f in champ.get("filters", []) if isinstance(f, dict)}

    # REAL-TRADE INGESTION — the honest scoreboard + loss clusters from LIVE outcomes
    # (not idealized replay). This is the live->improve loop closing: real fills +
    # real PnL feed the improver. Real-derived filters are higher-trust than sandbox.
    real_recs = real_trades.load_real_trades()
    logger.info("REAL TRADES | %s", real_trades.format_report(real_trades.real_summary(real_recs)))
    real_diag_cands = []
    need = diagnostics.MIN_SUPPORT + diagnostics.MIN_VETOED
    if len(real_recs) >= need:
        rd = diagnostics.propose_filter_codes(real_recs, existing, loop_cfg.get("diag_filters", 4))
        for d in rd:
            c = copy.deepcopy(champ)
            c.pop("_change", None)
            c["_change"] = f"+REAL-diag-filter: {d['code']} (LIVE loss cluster exp {d['vetoed_exp']:+.3f}, n={d['vetoed_n']})"
            c["filters"] = list(champ.get("filters", [])) + [_filter_entry(d["code"])]
            real_diag_cands.append(c)
        if rd:
            logger.info("REAL DIAGNOSTICS | %d loss-cluster filter(s) from LIVE trades: %s",
                        len(rd), "; ".join(d["code"] for d in rd))
    else:
        logger.info("REAL DIAGNOSTICS | %d live trades — need %d to mine real loss clusters (collecting)",
                    len(real_recs), need)

    # SIGNAL diagnostics on TRAIN ONLY (sandbox; no peeking at the test slice).
    diag = diagnostics.propose_filter_codes(champ_tr_trades, existing, loop_cfg.get("diag_filters", 4))
    diag_cands = []
    for d in diag:
        c = copy.deepcopy(champ)
        c.pop("_change", None)
        c["_change"] = f"+diag-filter: {d['code']} (train loss cluster exp {d['vetoed_exp']:+.3f}, n={d['vetoed_n']})"
        c["filters"] = list(champ.get("filters", [])) + [_filter_entry(d["code"])]
        diag_cands.append(c)
    if diag:
        logger.info("DIAGNOSTICS (train) | %d loss-cluster filter(s): %s", len(diag),
                    "; ".join(f"{d['code']} (Δexp {d['improvement']:+.3f})" for d in diag))

    # LEARN FROM MISTAKES: skip configs already evaluated. Reset that memory when the
    # dataset grows (new evidence) so a stale rejection never permanently blocks a config.
    tried = set(champ.get("tried", []))
    cur_epoch = max((r["ts"] for recs in by_symbol.values() for r in recs), default=0)
    if cur_epoch > champ.get("data_epoch", 0) and tried:
        logger.info("dataset grew (epoch %s -> %s) — clearing %d tried configs to re-explore",
                    champ.get("data_epoch", 0), cur_epoch, len(tried))
        tried = set()

    cands = propose(champ, loop_cfg["candidates_per_iter"], iteration, tried) + diag_cands + real_diag_cands
    # drop anything already tried (diag candidates can repeat across runs too)
    cands = [c for c in cands if config_hash(c) not in tried]
    margin = loop_cfg["improve_margin"]
    passed = []   # (cfg, train_metrics, test_metrics) — beat champion on BOTH
    history_entries = []   # memory of EVERY candidate tried this run (incl. failures)
    if not cands:
        logger.info("no NEW candidates — single + compound neighbourhood exhausted on "
                    "this data (%d already tried); will re-explore when the dataset grows",
                    len(tried))
    # Pass 1: evaluate each candidate on the single split AND across walk-forward
    # windows (adverse fills). Collect every candidate's per-trade Sharpe first so the
    # deflated-Sharpe bar can be deflated by the spread of all trials this run.
    evald = []
    for c in cands:
        tr = evaluate(c, train, loop_cfg, adverse=_ADVERSE)
        te = evaluate(c, test, loop_cfg, adverse=_ADVERSE)
        we, sharpe, nobs = _wf_eval(c, by_symbol, loop_cfg, wf_n, wf_emb)
        evald.append((c, tr, te, we, sharpe, nobs))
    n_trials = len(evald)
    sharpes = [s for (_, _, _, _, s, _) in evald]
    if len(sharpes) > 1:
        _sm = sum(sharpes) / len(sharpes)
        var_trial = sum((s - _sm) ** 2 for s in sharpes) / (len(sharpes) - 1)
    else:
        var_trial = 0.0

    # Pass 2: accept only candidates that pass the single-split OOS check AND the
    # walk-forward majority + deflated-Sharpe robustness gate (kills regime-luck +
    # selection-bias "wins" that a single lucky split would have let through).
    for c, tr, te, we, sharpe, nobs in evald:
        oos_holds = _improved(tr, champ_tr, margin) and _improved(te, champ_te, margin)
        robust = _robustness_ok(we, champ_mean_oos, sharpe, nobs, n_trials,
                                var_trial, margin, dsr_min)
        holds = oos_holds and robust
        wf_pos = sum(1 for e in we if e is not None and e > 0)
        wf_rank = sum(1 for e in we if e is not None)
        tag = ("  ✓ROBUST-HOLDS" if holds
               else ("  ·oos✓/wf✗" if oos_holds else ""))
        logger.info("  cand [%s] train exp=%+.4f test exp=%+.4f | wf %d/%d win sharpe=%.2f%s%s",
                    c["_change"], tr.expectancy, te.expectancy, wf_pos, wf_rank, sharpe,
                    "" if (tr.rankable and te.rankable) else " (unrankable)", tag)
        h = config_hash(c)
        tried.add(h)
        history_entries.append({
            "run": run_count, "change": c["_change"], "hash": h,
            "train_exp": round(tr.expectancy, 4), "test_exp": round(te.expectancy, 4),
            "wf_pos": wf_pos, "wf_rank": wf_rank, "wf_sharpe": round(sharpe, 4),
            "rankable": bool(tr.rankable and te.rankable), "accepted": bool(holds),
        })
        if holds:
            passed.append((c, tr, te))

    result = {"iteration": iteration, "champion_net": champ_full.net,
              "champion_trades": champ_full.trades,
              "candidates": len(cands), "oos_passed": len(passed), "accepted": None}

    if passed:
        # rank survivors by OUT-OF-SAMPLE (test) expectancy — the honest objective
        passed.sort(key=lambda x: x[2].score(), reverse=True)
        best_cfg, best_tr, best_te = passed[0]
        change = best_cfg.pop("_change")
        best_full = evaluate(best_cfg, by_symbol, loop_cfg, adverse=_ADVERSE)
        best_cfg["metrics"] = best_full.to_dict()
        best_cfg["test_metrics"] = best_te.to_dict()
        best_cfg["lineage"] = champ.get("lineage", [])
        best_cfg["loop"] = loop_cfg
        best_cfg["last_proposed_hash"] = champ.get("last_proposed_hash")
        champ_store.append_lineage(best_cfg, change, best_te.to_dict(), run_count)
        logger.info("ACCEPTED (OOS-validated) [%s]: test exp %+.4f -> %+.4f  (train %+.4f -> %+.4f)",
                    change, champ_te.expectancy, best_te.expectancy, champ_tr.expectancy, best_tr.expectancy)
        result["accepted"] = {"change": change, "test_expectancy": best_te.expectancy,
                              "train_expectancy": best_tr.expectancy}
        new_champ = best_cfg
        proposal = maybe_emit_promotion(best_cfg, best_te, dry_run, fr)  # promote on OOS metrics
        if proposal:
            result["promotion_proposal"] = proposal
    else:
        logger.info("no OUT-OF-SAMPLE improvement — champion unchanged (%d candidates, all failed test or overfit)",
                    len(cands))
        champ["metrics"] = champ_full.to_dict()   # refresh current champion metrics each run
        new_champ = champ

    # Persist EVERY run (the core fix): record this run's attempts + advance the
    # run counter so the loop accumulates durable learning — and explores new
    # candidates next run — even when nothing was accepted. Previously save() was
    # only reached inside the accept branch, so a no-accept run (the steady state)
    # persisted nothing: no history, no advancing counter, frozen exploration.
    champ_store.append_history(new_champ, history_entries)
    new_champ["run_count"] = run_count + 1
    new_champ["tried"] = sorted(tried)[:C.TRIED_CAP]   # memory of dead-ends (bounded)
    new_champ["data_epoch"] = cur_epoch
    result["run_count"] = new_champ["run_count"]
    result["history_size"] = len(new_champ.get("history", []))
    result["tried_size"] = len(new_champ["tried"])
    # Phase 2 — self-closing confirm: register Step-1 survivors + LIVE, advance verdicts.
    try:
        confirm.ensure_live_entry(new_champ, cur_epoch)
        for c, _tr, _te in passed:
            confirm.register_if_survivor(new_champ, c, cur_epoch, run_count)
        transitions = confirm.tick(new_champ, by_symbol, real_trades.load_real_trades())
        for tr in transitions:
            (logger.warning if tr["alert"] else logger.info)("[CONFIRM] %s", tr["msg"])
            champ_store.append_lineage(new_champ, f"confirm:{tr['id']}:{tr['to']}",
                                       {"verdict": tr["to"]}, run_count)
            # LIVE truth_reject (alert=True) is the load-bearing signal: the live
            # ST2.0 config is failing REAL-fill confirmation. Push it to Telegram
            # (best-effort; never raises). Other transitions stay log-only.
            if tr["alert"] and not dry_run:
                notify.telegram_alert(
                    f"🚨 ST2.0 LAB — LIVE config failing REAL confirmation\n{tr['msg']}")
        result["confirm_transitions"] = [t["msg"] for t in transitions]
    except Exception as e:                       # confirm must never break the search loop
        logger.error("[CONFIRM] tick failed (non-fatal): %s", e, exc_info=True)

    if not dry_run:
        champ_store.save(new_champ)

    return result


def maybe_emit_promotion(champ: dict, m, dry_run=False, fill_rate: float = 0.43) -> str | None:
    """If the champion clears the sandbox bar, write a human-gated PAPER-CONFIRM
    proposal into docs/fix-proposals/ (proposals-digest verifies + Telegrams it).

    IMPORTANT: this proposes the next step as PAPER-CONFIRM, never live. Sandbox
    metrics are an OPTIMISTIC UPPER BOUND — the replay fills every signal, but
    live ST2.0's real maker fill rate is ~43%, so positive sandbox PnL routinely
    contradicts live reality (the documented 'backtesting this data only makes
    artifacts' trap). Only real paper-confirm data can justify a later live
    proposal. We never change the live bot here."""
    loop_cfg = champ.get("loop", C.DEFAULTS)
    qualifies = (m.rankable and m.net > 0 and m.kelly > 0
                 and m.trades >= loop_cfg.get("confirm_sample", 30))
    if not qualifies:
        return None
    h = config_hash(champ)
    if champ.get("last_proposed_hash") == h:
        return None  # already proposed this exact config
    if champ["params"] == LIVE_PARAMS and not champ.get("filters"):
        return None  # champion is just the live default; nothing to propose
    champ["last_proposed_hash"] = h

    diffs = [f"{k}: {LIVE_PARAMS[k]} -> {v}"
             for k, v in champ["params"].items() if LIVE_PARAMS.get(k) != v]
    filt = [f.get("code") for f in champ.get("filters", [])]
    body = (
        f"# ST2.0 LAB — PAPER-CONFIRM CANDIDATE ({h})\n\n"
        f"**Out-of-sample (held-out TEST) metrics — beat the champion on BOTH train and "
        f"test, so not pure overfit. Still OPTIMISTIC (100%-fill) and relative-only, NOT truth:** "
        f"expectancy {m.expectancy:+.4f}/trade, net(UB) {m.net:+.2f}, {m.trades} trades, "
        f"WR {m.wr*100:.0f}%, Kelly {m.kelly:.2f}.\n\n"
        f"**Fill-adjusted at the measured {fill_rate*100:.0f}% live fill rate:** "
        f"net ~{m.fill_adjusted_net(fill_rate):+.2f} (crude — which signals fill is unknown).\n\n"
        "> ⚠️ The sandbox fills every signal; live ST2.0 fills ~43%. Positive sandbox "
        "PnL does NOT mean a live edge — it usually doesn't. This is a candidate to "
        "**forward-confirm in PAPER**, not a recommendation to go live.\n\n"
        f"## Proposed param changes vs live (`strategies.py` ST2_*)\n"
        + ("\n".join(f"- {d}" for d in diffs) or "- (none)") + "\n\n"
        f"## Proposed entry filters (must pass `safe_exec`)\n"
        + ("\n".join(f"- `{c}`" for c in filt) or "- (none)") + "\n\n"
        "## REQUIRED human steps (NOT automatic)\n"
        "1. Review this config. 2. For filters: implement + `/pre-restart-audit`.\n"
        "3. Run it as a PAPER variant and forward-confirm >= confirm_sample REAL trades.\n"
        "4. Only if paper-confirm is positive, consider a separate live promotion (your approval).\n\n"
        "_Generated by scripts/st2_lab — sandbox hypothesis, NOT validated truth._\n"
    )
    path = os.path.join(C.PROPOSALS_DIR, f"st2-lab-paper-confirm-{h}.md")
    if not dry_run:
        os.makedirs(C.PROPOSALS_DIR, exist_ok=True)
        with open(path, "w") as f:
            f.write(body)
        champ_store.save(champ)
        logger.info("PROMOTION PROPOSAL written: %s", path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None, help="cap dataset records (fast runs)")
    ap.add_argument("--dry-run", action="store_true", help="don't persist champion/proposals")
    args = ap.parse_args()

    by_symbol = ds.load_dataset(limit=args.limit)
    for i in range(args.iterations):
        if _halted():
            break
        run_iteration(by_symbol=by_symbol, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
