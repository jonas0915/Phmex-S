# Edge Swarm v2 — the desk

Spec: `docs/superpowers/specs/2026-09-16-edge-swarm-v2-design.md`. Plan: `docs/superpowers/plans/2026-09-16-edge-swarm-v2-desk.md`.

**Before any work on the bot's research:** `git pull` this repo, then read `kb/CONSTRAINTS.md`, `kb/STANDARDS.md`, `kb/DEAD_LIST.md`, `kb/LESSONS.md`. The knowledge base is the swarm's memory and lives in git, not on one laptop.

## Layout

- `lib/` — the tested library every seat must use for numbers: `fee_math` (c = 11.5 bps, `p_star`, `lot_check`), `bootstrap_ci` (`mean_ci`, `diff_ci`), `load_data` (train/holdout gate), `registrar` (freeze spec + signal with sha256), `screen` (causality check + closed-bar simulator → `out.json`), `kb_check`.
- `kb/` — the knowledge base (`CONSTRAINTS`, `STANDARDS`, `DATA`, `DEAD_LIST`, `LESSONS`, `SURVIVORS`, `owner_trades/`).
- `workflows/desk.js` — the Workflow script that IS the desk. Seats, in order: desk brief → 8 analysts in parallel (forced_flows, informed_flow, dealer_inventory, session_calendar, vol_structure, cross_asset, literature, owner-record) → gatekeeper (dedup, relabel check row-cited, source verification A/B/C/F) → per-thesis pipeline registrar → screener → auditor (no barrier between theses) → risk committee (economics seat + statistics seat, both must pass; the statistics seat applies Benjamini-Hochberg across the run's screens and runs the one registered tp_bps ±20% robustness read) → synthesis (`REPORT.md`) → critic (`CRITIC.md`) → reconciler (appends a `DEAD_LIST`/`SURVIVORS` row for every SCREENED thesis only — gate-rejected and errored theses live in REPORT.md/gate_rejections.json — plus `LESSONS` lines, and re-runs `kb_check` until `KB OK`).
- `runs/<run_id>/` — every artifact of a run: `mandate.md`, `theses/*.json`, `gate_rejections.json`, `specs/*.frozen.json`, `screens/<id>/{signal.py,out.json,trades.csv,audit.json,out.robust_plus.json,out.robust_minus.json,robust/}`, `committee/{economics,statistics,bh}.json`, `REPORT.md`, `CRITIC.md`, `exploratory/`.

## Running the desk

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
Build stage (`workflows/build.js`) runs only on a committee pass AND the owner's "go"; it stops before any bot restart (`/pre-restart-audit`).
