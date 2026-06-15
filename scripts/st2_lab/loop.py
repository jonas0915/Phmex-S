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
import hashlib
import json
import logging
import os

from . import config as C
from . import champion as champ_store
from . import dataset as ds
from . import fills as fills_mod
from . import diagnostics
from . import real_trades
from .proposer import propose, _filter_entry
from .evaluator import evaluate, evaluate_with_trades

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ST2-LAB] %(levelname)s %(message)s",
    handlers=[logging.FileHandler(C.DIGEST_LOG), logging.StreamHandler()],
)
logger = logging.getLogger("st2_lab")

# Live ST2.0 config we'd be proposing a change *from* (mirror of strategies.py).
LIVE_PARAMS = dict(C.DEFAULT_CHAMPION["params"])


def _halted() -> bool:
    if os.path.exists(C.HALT_FLAG):
        logger.warning("halt flag present (%s) — skipping iteration", C.HALT_FLAG)
        return True
    return False


def _config_hash(cfg: dict) -> str:
    payload = json.dumps(
        {"params": cfg.get("params"), "filters": [f.get("code") for f in cfg.get("filters", [])]},
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


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


def run_iteration(by_symbol=None, iteration=None, dry_run=False) -> dict:
    if _halted():
        return {"halted": True}
    champ = champ_store.load()
    loop_cfg = champ.get("loop", C.DEFAULTS)
    if iteration is None:
        iteration = len(champ.get("lineage", []))
    if by_symbol is None:
        by_symbol = ds.load_dataset()
    logger.info("iter %d | dataset: %s", iteration, ds.dataset_summary(by_symbol))

    # REAL fill truth — measured from live logs, leads every iteration. The sandbox
    # net below is a 100%-fill UPPER BOUND; this is what actually happens.
    fstats = fills_mod.measured_fill_stats()
    fr = fstats["rate"]
    logger.info("FILL TRUTH | %s", fills_mod.format_report(fstats).replace("\n", " | "))

    # Chronological train/test split. Diagnostics + selection happen on TRAIN; a
    # candidate is only accepted if it ALSO beats the champion OUT-OF-SAMPLE on TEST.
    # This is the overfit guard — in-sample-only "wins" (e.g. spread artifacts) die here.
    train, test = ds.chronological_split(by_symbol, loop_cfg.get("train_frac", 0.7))
    logger.info("split | train %s | test %s", ds.dataset_summary(train), ds.dataset_summary(test))

    champ_tr, champ_tr_trades = evaluate_with_trades(champ, train, loop_cfg)
    champ_te = evaluate(champ, test, loop_cfg)
    champ_full = evaluate(champ, by_symbol, loop_cfg)
    logger.info("champion: train exp=%+.4f | test(OOS) exp=%+.4f | full net(UB)=%+.2f fillAdj~%+.2f trades=%d kelly=%.2f",
                champ_tr.expectancy, champ_te.expectancy, champ_full.net,
                champ_full.fill_adjusted_net(fr), champ_full.trades, champ_full.kelly)

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

    cands = propose(champ, loop_cfg["candidates_per_iter"], iteration) + diag_cands + real_diag_cands
    margin = loop_cfg["improve_margin"]
    passed = []   # (cfg, train_metrics, test_metrics) — beat champion on BOTH
    for c in cands:
        tr = evaluate(c, train, loop_cfg)
        te = evaluate(c, test, loop_cfg)
        holds = _improved(tr, champ_tr, margin) and _improved(te, champ_te, margin)
        logger.info("  cand [%s] train exp=%+.4f test exp=%+.4f%s%s",
                    c["_change"], tr.expectancy, te.expectancy,
                    "" if (tr.rankable and te.rankable) else " (unrankable)",
                    "  ✓OOS-HOLDS" if holds else "")
        if holds:
            passed.append((c, tr, te))

    result = {"iteration": iteration, "champion_net": champ_full.net,
              "candidates": len(cands), "oos_passed": len(passed), "accepted": None}

    if passed:
        # rank survivors by OUT-OF-SAMPLE (test) expectancy — the honest objective
        passed.sort(key=lambda x: x[2].score(), reverse=True)
        best_cfg, best_tr, best_te = passed[0]
        change = best_cfg.pop("_change")
        best_full = evaluate(best_cfg, by_symbol, loop_cfg)
        best_cfg["metrics"] = best_full.to_dict()
        best_cfg["test_metrics"] = best_te.to_dict()
        best_cfg["lineage"] = champ.get("lineage", [])
        best_cfg["loop"] = loop_cfg
        best_cfg["last_proposed_hash"] = champ.get("last_proposed_hash")
        champ_store.append_lineage(best_cfg, change, best_te.to_dict(), iteration)
        if not dry_run:
            champ_store.save(best_cfg)
        logger.info("ACCEPTED (OOS-validated) [%s]: test exp %+.4f -> %+.4f  (train %+.4f -> %+.4f)",
                    change, champ_te.expectancy, best_te.expectancy, champ_tr.expectancy, best_tr.expectancy)
        result["accepted"] = {"change": change, "test_expectancy": best_te.expectancy,
                              "train_expectancy": best_tr.expectancy}
        proposal = maybe_emit_promotion(best_cfg, best_te, dry_run, fr)  # promote on OOS metrics
        if proposal:
            result["promotion_proposal"] = proposal
    else:
        logger.info("no OUT-OF-SAMPLE improvement — champion unchanged (%d candidates, all failed test or overfit)",
                    len(cands))

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
    h = _config_hash(champ)
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
