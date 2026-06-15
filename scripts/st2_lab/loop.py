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
import hashlib
import json
import logging
import os

from . import config as C
from . import champion as champ_store
from . import dataset as ds
from .proposer import propose
from .evaluator import evaluate

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
    """A candidate improves if it's rankable and beats the champion's net by the
    margin (absolute floor so we don't churn on noise near zero)."""
    if not best.rankable:
        return False
    base = champ_metrics.net if champ_metrics.rankable else float("-inf")
    floor = max(0.02, abs(base) * margin) if base != float("-inf") else 0.0
    return best.net > base + floor


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

    champ_m = evaluate(champ, by_symbol, loop_cfg)
    logger.info("champion: net=%+.2f trades=%d wr=%.0f%% kelly=%.2f rankable=%s",
                champ_m.net, champ_m.trades, champ_m.wr * 100, champ_m.kelly, champ_m.rankable)

    cands = propose(champ, loop_cfg["candidates_per_iter"], iteration)
    scored = []
    for c in cands:
        m = evaluate(c, by_symbol, loop_cfg)
        scored.append((c, m))
        logger.info("  cand [%s] net=%+.2f trades=%d wr=%.0f%% kelly=%.2f%s",
                    c["_change"], m.net, m.trades, m.wr * 100, m.kelly,
                    "" if m.rankable else " (unrankable)")

    scored.sort(key=lambda cm: cm[1].score(), reverse=True)
    result = {"iteration": iteration, "champion_net": champ_m.net,
              "candidates": len(scored), "accepted": None}

    if scored and _improved(scored[0][1], champ_m, loop_cfg["improve_margin"]):
        best_cfg, best_m = scored[0]
        change = best_cfg.pop("_change")
        best_cfg["metrics"] = best_m.to_dict()
        best_cfg["lineage"] = champ.get("lineage", [])
        best_cfg["loop"] = loop_cfg
        best_cfg["last_proposed_hash"] = champ.get("last_proposed_hash")
        champ_store.append_lineage(best_cfg, change, best_m.to_dict(), iteration)
        if not dry_run:
            champ_store.save(best_cfg)
        logger.info("ACCEPTED new champion via [%s]: net %+.2f -> %+.2f",
                    change, champ_m.net, best_m.net)
        result["accepted"] = {"change": change, "net": best_m.net}
        proposal = maybe_emit_promotion(best_cfg, best_m, dry_run)
        if proposal:
            result["promotion_proposal"] = proposal
    else:
        logger.info("no improvement found this iteration — champion unchanged")

    return result


def maybe_emit_promotion(champ: dict, m, dry_run=False) -> str | None:
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
        f"**Sandbox metrics (OPTIMISTIC, relative-ranking only — NOT truth):** "
        f"net {m.net:+.2f}, {m.trades} trades, WR {m.wr*100:.0f}%, Kelly {m.kelly:.2f}.\n\n"
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
