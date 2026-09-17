# Edge Swarm v2 — the desk

Spec: `docs/superpowers/specs/2026-09-16-edge-swarm-v2-design.md`. Plan: `docs/superpowers/plans/2026-09-16-edge-swarm-v2-desk.md`.

**Before any work on the bot's research:** `git pull` this repo, then read `kb/CONSTRAINTS.md`, `kb/STANDARDS.md`, `kb/DEAD_LIST.md`, `kb/LESSONS.md`. The knowledge base is the swarm's memory and lives in git, not on one laptop.

## Layout

- `lib/` — the tested library every seat must use for numbers: `fee_math` (c = 11.5 bps, `p_star`, `lot_check`), `bootstrap_ci` (`mean_ci`, `diff_ci`), `load_data` (train/holdout gate), `registrar` (freeze spec + signal with sha256), `screen` (causality check + closed-bar simulator → `out.json`), `kb_check`.
- `kb/` — the knowledge base (`CONSTRAINTS`, `STANDARDS`, `DATA`, `DEAD_LIST`, `LESSONS`, `SURVIVORS`, `owner_trades/`).
- `workflows/desk.js` — the Workflow script that IS the desk. Seats, in order: desk brief → 8 analysts in parallel (forced_flows, informed_flow, dealer_inventory, session_calendar, vol_structure, cross_asset, literature, owner-record) → gatekeeper (dedup, relabel check row-cited, source verification A/B/C/F) → per-thesis pipeline registrar → screener → auditor (no barrier between theses) → risk committee (economics seat + statistics seat, both must pass; the statistics seat applies Benjamini-Hochberg across the run's screens and runs the one registered tp_bps ±20% robustness read) → synthesis (`REPORT.md`) → critic (`CRITIC.md`) → reconciler (appends a `DEAD_LIST`/`SURVIVORS` row for every SCREENED thesis only — gate-rejected and errored theses live in REPORT.md/gate_rejections.json — plus `LESSONS` lines, and re-runs `kb_check` until `KB OK`).
- `runs/<run_id>/` — every artifact of a run: `mandate.md`, `theses/*.json`, `gate_rejections.json`, `specs/*.frozen.json`, `screens/<id>/{signal.py,out.json,trades.csv,audit.json,out.robust_plus.json,out.robust_minus.json,robust/}`, `committee/{economics,statistics,bh}.json`, `REPORT.md`, `CRITIC.md`, `exploratory/`.

## Running the desk

**Preconditions.** Launch real runs from a FRESH Claude Code session with an unused WebSearch budget — the analysts are internet-first, and if every analyst reports `web_budget_exhausted` the run aborts before the gate with `WEB_BUDGET_EXHAUSTED` (one LESSONS line, nothing else written). The controller checks `/workflows` for no live workflow before launching.

The script has no clock and no filesystem, so the launch invocation carries the timestamps AND the contents of the two governing documents (every prompt embeds them verbatim). Run it **alone** — never concurrently with another workflow (v1 died 4× on a shared rate ceiling). The controller verifies nothing else is live with `/workflows` before launching; `desk.js` logs "run alone — controller confirmed no other Workflow live" and does not shell out to `ps`.

From a Claude Code session in this repo, the controller reads the two files and passes them as strings:

```
constraints_md = Read("research/swarm/kb/CONSTRAINTS.md")
standards_md   = Read("research/swarm/kb/STANDARDS.md")

Workflow({ scriptPath: "research/swarm/workflows/desk.js",
           args: { run_id: "<YYYY-MM-DD-HHMM PT>",        // names runs/<run_id>/
                   now: "<ISO UTC, e.g. 2026-09-17T04:00:00Z>",  // registrar frozen_at
                   today: "<YYYY-MM-DD PT>",              // optional; DEAD_LIST/LESSONS date stamp (defaults to now[:10])
                   judge_model: null,                     // see JUDGE_MODEL below
                   max_analysts: 8, max_screens: 5,
                   dry_run: false,
                   constraints_md: <string>, standards_md: <string> } })
```

`args` reference:

| arg | required | meaning |
|---|---|---|
| `run_id` | yes | run directory name under `runs/` |
| `now` | yes (or `today`) | ISO UTC timestamp; becomes `frozen_at` on every frozen spec |
| `today` | no | `YYYY-MM-DD` used as the date cell of DEAD_LIST/LESSONS rows; defaults to `now[:10]` |
| `constraints_md`, `standards_md` | yes | file CONTENTS of `kb/CONSTRAINTS.md` / `kb/STANDARDS.md`; the script throws at startup without them |
| `max_analysts` | no (8) | first N lenses of the 8, in the order listed above |
| `max_screens` | no (5) | gate keeps at most N theses (truncation is logged, never silent) |
| `judge_model` | no (null) | model override for the five judging seats only |
| `dry_run` | no (false) | plumbing test, see below |

**JUDGE_MODEL.** `const JUDGE_MODEL = args.judge_model || null`. When set it is applied as `opts.model` to exactly five seats — gatekeeper, committee:economics, committee:statistics, synthesis, critic — and never to analysts, registrar, screens, audits or the reconciler. When null the `model` option is omitted and every seat inherits the session model. Run 1 uses `judge_model: null`.

**Dry run of the plumbing** (brief Step 4): `args: { run_id: "dryrun-<date>", now: "...", max_analysts: 1, max_screens: 1, dry_run: true, constraints_md, standards_md }`. With `max_analysts: 1` only the `forced_flows` lens runs; `dry_run: true` tells that analyst to produce ONE deliberately dead thesis (a relabel of a DEAD_LIST row, id prefixed `dryrun_`) with minimal web work, so the gatekeeper's row-cited rejection path and the reconciler are exercised end to end. Expected result: `ALL_REJECTED_AT_GATE`, a LESSONS entry and no DEAD_LIST row (rows are written only for screened theses — STANDARDS #15), `kb_check` prints `KB OK`. Verify with:

```
find research/swarm/runs/dryrun-<date> -type f | sort
python3 -m research.swarm.lib.kb_check
git diff --stat research/swarm/kb
```

If any phase returned `null` or an agent "fixed" a frozen spec, edit the prompt and resume with `resumeFromRunId`.

After a run: `python3 -m research.swarm.lib.kb_check && git add research/swarm && git commit && git push`.

## Rules the script enforces by construction

- Every prompt embeds `CONSTRAINTS.md` + `STANDARDS.md`, forbids hand-rolled statistics (lib only), forbids editing a frozen spec or `signal.py`, forbids holdout reads, and forbids any daily-ROI target.
- Every analyst prompt is internet-first (WebSearch/WebFetch, 8-12 searches, 5-8 pages) and states verbatim: `kb/DEAD_LIST.md is a FILTER for rejecting relabels, NEVER a source of ideas.` Theses require `source_urls` + `evidence`.
- The owner-record lens degrades gracefully: if `kb/owner_trades/api_closed_pnl.json` is absent it returns zero theses and the run logs it.
- Committee eligibility = audit `CONFIRMED` AND train CI95 excluding zero; BH is applied by the statistics seat, not the eligibility filter.
- The registrar is a mechanical low-effort seat that runs one CLI and may not edit the thesis; the screener may not "fix" a failing signal; the auditor re-runs the screen into a scratch dir and diffs.
- Budget target: ≤ 2.5M tokens and ≤ 35 min per full run (8 analysts, ≤ 5 screens, ≤ 5 audits, 2 committee seats, 3 closing seats).

Library tests: `python3 -m pytest tests/test_swarm_*.py -q`.

## Build stage (`workflows/build.js`)

`build.js` turns exactly ONE committee-PASS thesis into a pre-registered PAPER slot on the bot, following the bespoke Donchian recipe in `docs/2026-09-16-edge-swarm-v1/02_framework_audit.md` §3.6, on its own git branch — and stops. It never restarts the bot, never touches launchd, never places an order, never merges or pushes, and never edits the frozen spec or `signal.py`.

**Two owner gates, both human.**

- **Gate A — before launch.** A committee PASS from `desk.js` is not a go. The controller stops, reports the survivor (`runs/<run_id>/REPORT.md`, `kb/SURVIVORS.md`), and asks. `build.js` is invoked only after the owner says "go".
- **Gate B — after build.js finishes.** The script returns the branch name and the list of files changed. The owner reviews the branch, runs `/pre-restart-audit`, and says "go" again before any restart. Until that audited restart nothing the build wrote is live (editing a file ≠ the bot using it).

**Launch** (from a Claude Code session in this repo, alone — no other workflow live):

```
constraints_md = Read("research/swarm/kb/CONSTRAINTS.md")
standards_md   = Read("research/swarm/kb/STANDARDS.md")

Workflow({ scriptPath: "research/swarm/workflows/build.js",
           args: { run_id: "<the desk run that produced the PASS>",   // runs/<run_id>/
                   thesis_id: "<id>",                    // the survivor's id (^[a-z][a-z0-9_]{2,40}$)
                   now: "<ISO UTC, e.g. 2026-09-18T03:00:00Z>",  // registered_ts + prereg date
                   judge_model: null,                    // reviewer seat only (same convention as desk.js)
                   constraints_md: <string>, standards_md: <string> } })
```

| arg | required | meaning |
|---|---|---|
| `run_id` | yes | the desk run whose `committee/{economics,statistics}.json` both pass this id |
| `thesis_id` | yes | the survivor; becomes the slot_id, `<id>_slot.py`, `tests/test_<id>_slot.py`, `trading_state_<id>.json`, `.kill_<id>` |
| `now` | yes | ISO UTC; becomes `registered_ts` in the adjudicator and the prereg filename date |
| `constraints_md`, `standards_md` | yes | file CONTENTS of the two kb documents; every prompt embeds them |
| `judge_model` | no (null) | model override for the reviewer seat only |
| `today` | no | `YYYY-MM-DD` for the prereg filename / kb date cell; defaults to `now[:10]` |
| `suite_baseline` | no | text of the expected pytest baseline (default: the post-Task-7 baseline) |

**What it does, in order.** All work happens on branch `swarm/<id>-slot`, created from the current HEAD (the working tree is left checked out on that branch; nothing else on the tree is staged or touched).

1. **Prereg** — checks the frozen sha (`registrar.verify`), that both committee seats voted pass for this id, and that `screens/<id>/out.holdout.json` does not already exist. Writes `docs/superpowers/specs/<date>-<id>-prereg.md` with the frozen verdict line and anti-fishing clause, and COMMITS it before any holdout read:
   - verdict_n = 50; KILL if n ≥ 50 and net ≤ 0; KILL if net ≤ −$10 at any n; PASS if n ≥ 50 and the bootstrap CI95 lower bound of per-trade net USD (`bootstrap_ci.mean_ci`) > 0; n ≥ 50 with net > 0 but CI lower ≤ 0 = INCONCLUSIVE, hard stop at n = 100 (PASS if CI lower > 0 there, else KILL). `net_pnl` summed as-is (fee-inclusive at the source).
   - anti-fishing: no change to tp/sl/max_hold/universe/timeframe/signal during the paper era; no second holdout read; deviations are findings, not fixes; rollback = `touch .kill_<id>`.
   - Then the ONE registered holdout read, by a mechanical seat running exactly `python3 -m research.swarm.lib.screen runs/<run_id>/specs/<id>.frozen.json runs/<run_id> --era holdout --token COMMITTEE-HOLDOUT-READ` (the token is `load_data.COMMITTEE_TOKEN`). It writes `screens/<id>/out.holdout.json` and `trades.holdout.csv` (era-suffixed) and never touches the train `out.json`. The numbers are recorded in the prereg doc and committed. Decision rule (fixed in the doc before the read): CI95 upper < 0 → `DEAD_AT_HOLDOUT`; n < 10 or CI null → `HOLDOUT_INSUFFICIENT`; otherwise build. A non-build outcome stops here.
2. **Implement** — TDD: `tests/test_<id>_slot.py` first (signal parity against the frozen `signal.py` on synthetic AND train data, forming-bar exclusion, exit golden cases identical to `screen.simulate`, sidecar roundtrip, AST wiring, bare-bot orchestration, live-mode-places-no-orders) and adjudicator tests; then `<id>_slot.py` (pure; `signals()` transcribed verbatim from `screens/<id>/signal.py`, closed bars only), `bot.py` (one `StrategySlot` with the rails opt-out `loss_cap_usdt=-999.0`, `kelly_min_trades=10**9`, `paper_mode=True`, strategy_name not in `STRATEGIES`; `self._evaluate_<id>(prices)` in `_evaluate_all_slots`; the evaluator checks `slot.enabled` every cycle so `.kill_<id>` — processed by the bot's generic `.kill_*` loop — is honoured), `scripts/lab_adjudicator/adjudicate.py` (`EXPERIMENTS["<id>"]`, `grade_<id>`, digest line). Files touched are limited to those five plus the module. Full suite must be at baseline + the new tests. One commit.
3. **Review** — an independent reviewer (JUDGE_MODEL applies here only) verifies against the files: no forming-bar reads, verbatim signal transcription, exit rule = `simulate`, no live-order path, kill honoured, adjudicator numbers = prereg doc, tests exercise the signal, scope of the diff, full pytest. One fix round at most; a second BLOCK returns `REVIEW_BLOCKED`.
4. **Reconcile** — one kb row on the branch (`SURVIVORS` on `BUILT`, `DEAD_LIST` on `DEAD_AT_HOLDOUT`, a `LESSONS` line otherwise, plus a `LESSONS` line recording that the holdout was read), `kb_check` until `KB OK`, commit. Then the script returns `{result, branch, base_sha, files_changed, commits, holdout, review, next}` and stops.

Results: `BUILT` (→ Gate B), `DEAD_AT_HOLDOUT`, `HOLDOUT_INSUFFICIENT`, `HOLDOUT_ERROR`, `REVIEW_BLOCKED`, `IMPLEMENT_FAILED`, `PREREG_<reason>`.

**The branch holds the only record of the holdout read.** Never delete `swarm/<id>-slot` unmerged; never re-read holdout for the same thesis. If the owner declines the build, merge (or cherry-pick) the two prereg commits and the kb commit anyway so the read stays on the record.

Syntax check without running: the body uses top-level `return` inside the harness's async wrapper, so plain `node --check` reports "Illegal return statement" for both `desk.js` and `build.js`; wrap the body in an `async function` before `node --input-type=module --check` (see the Task 8 report for the one-liner).
