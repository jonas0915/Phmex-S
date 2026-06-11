---
name: 2026-05-10 session — calibration + flow capture + automation
description: Session that deployed in-bot flow capture, finished backtester Steps 3-4, ran first calibration (10x overfiring), and registered 4 launchd jobs for sprint automation
type: project
---

## What shipped

- **Backtester Steps 3+4**: AE flag-gated in `check_exits()`, `scripts/calibrate_compare.py` works end-to-end.
- **3 OHLCV-portable gates** added to `backtest.py`: time-of-day blocked hours, HTF cluster throttle (30 min between htf entries), per-pair loss cooldown (10 min after any loss). All mirror live constants — no new parameters.
- **In-bot flow capture** at `bot.py:986`: writes per-scan OB+flow snapshot to `logs/flow_capture.jsonl`. NaN-safe via `_safe()` helper. Reviewer caught NaN-silent-drop bug before deploy; fixed.
- **4 launchd jobs**: flow-sanity (daily 6 AM PT), weekly-sweep (Sunday 8 PM PT), sprint-checkpoint (May 17 + May 24 at 8 AM PT), proposals-digest (~every 3 days at 5 AM PT).
- **Bot restarted twice**: PID 13867 (after pre-restart audit, no code changes) and PID 59813 (after flow capture edit + re-audit). Both clean.

## Key calibration finding

Sim on ETH pullback 2026-04-02 → 2026-05-02 produces 326 trades vs live 22 — **15× overfire** before gates ported. After porting 3 OHLCV-portable gates, drops to **10× overfire** (221 trades, -$46.17 vs live -$2.40). The remaining gap is flow-attributable (ensemble layers 3/5/6/7, tape veto, divergence cooldown — all require flow data that doesn't exist for the historical window).

**Implication:** ~32% of the bot's protective gating is OHLCV-portable. ~68% is flow-dependent. The flow gates are doing real work even though the underlying strategies have no statistical edge.

## Automation lessons learned

- **`/schedule` remote agents don't work for local-file analysis** unless the repo is GitHub-pushed AND the data isn't sensitive. Phmex-S is a public repo, fix proposals contain log snippets / balance numbers — pushing them is a leak. Forced fallback to local launchd.
- **Gmail MCP can only `create_draft`, not `send`**. Don't promise email automation unless you mean drafts that need user-side opening.
- **AST-based hallucination check** is most of the protection you need. Pure grep misses function-vs-line mismatches (the April 23 hallucination class) — but a proper AST def-map check catches them. ~85-90% catch rate for the April 23 class.
- **Mac launchd uses local time, not UTC.** I initially wrote plists in UTC and had to fix. Existing plists use local PT.

## Plain-English feedback rule saved 2026-05-10

Jonas asked for normal-conversation English going forward. Saved as `feedback_plain_english.md` in global memory. Applies to all projects.

## What runs autonomously until May 17

- Bot trading at $5
- Flow capture appending JSONL
- Daily sanity check (silent on healthy days)
- Weekly sweep report Sunday May 16 8 PM PT
- Proposal digest on May 12, May 15 at 5 AM PT
- Sprint checkpoint May 17 8 AM PT — Telegram ping for "ready to wire flow replay?"

## Files touched

- `bot.py` — `_log_flow_snapshot()` method + call site at L986
- `backtest.py` — AE flag, 3 OHLCV-portable gates, htf throttle, per-pair loss cooldown
- `scripts/calibrate_compare.py` — new
- `scripts/flow_capture_sanity.py` — new
- `scripts/weekly_sweep.py` — new
- `scripts/sprint_checkpoint.py` — new
- `scripts/proposals_digest.py` — new
- 4 launchd plists at `~/Library/LaunchAgents/`
