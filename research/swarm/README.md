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

`build.js` turns exactly ONE committee-PASS thesis into a pre-registered PAPER slot on the bot, following the bespoke Donchian recipe in `docs/2026-09-16-edge-swarm-v1/02_framework_audit.md` §3.6, on its own git branch — and stops after the reviewer. It never restarts the bot, never touches launchd, never places an order, never merges or pushes, never writes under `kb/`, and never edits the frozen spec or `signal.py`.

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
| `now` | yes | ISO UTC; becomes `registered_ts` in the adjudicator and (by default) the prereg filename date |
| `constraints_md`, `standards_md` | yes | file CONTENTS of the two kb documents; every prompt embeds them |
| `judge_model` | no (null) | model override for the reviewer seat only |
| `today` | no | `YYYY-MM-DD` for the prereg filename; defaults to `now[:10]` |
| `suite_baseline` | no | text of the expected pytest baseline (default: the post-Task-7 baseline) |

**What it does, in order.** All work happens on branch `swarm/<id>-slot`, created from the current HEAD (the working tree is left checked out on that branch; nothing else on the tree is staged or touched).

1. **Prereg** — preconditions, in this order, each a hard stop before anything is created or checked out: the branch `swarm/<id>-slot` must not exist on any ref (`PREREG_BRANCH_EXISTS`); the holdout must never have been read for this thesis on any ref — `git log --all -- screens/<id>/out.holdout.json …` empty, `git cat-file -e` on the branch fails, no prereg doc anywhere (`HOLDOUT_ALREADY_READ`); frozen sha verifies; both committee seats voted pass. Then the branch is created, and `docs/superpowers/specs/<date>-<id>-prereg.md` is written with the frozen verdict line and anti-fishing clause and COMMITTED before any holdout read:
   - verdict_n = 50; KILL if n ≥ 50 and net ≤ 0; KILL if net ≤ −$10 at any n; PASS if n ≥ 50 and the bootstrap CI95 lower bound of per-trade net USD (`bootstrap_ci.mean_ci`) > 0; n ≥ 50 with net > 0 but CI lower ≤ 0 = INCONCLUSIVE, hard stop at n = 100 (PASS if CI lower > 0 there, else KILL). `net_pnl` summed as-is (fee-inclusive at the source).
   - **kill line enforced automatically** (spec §7): `grade_<id>` touches `.kill_<id>` on any KILL clause, including the INCONCLUSIVE hard stop; the bot's existing `.kill_*` loop closes the paper book (paper-only, zero market risk). The slot's own rails stay opted out (`loss_cap_usdt=-999.0`, `kelly_min_trades=10**9`) because the adjudicator line is the enforcement. PASS is never a promotion.
   - anti-fishing: no change to tp/sl/max_hold/universe/timeframe/signal during the paper era; no second holdout read; deviations are findings, not fixes; manual rollback = `touch .kill_<id>`.
   - Then the ONE registered holdout read, by a mechanical seat running exactly `python3 -m research.swarm.lib.screen runs/<run_id>/specs/<id>.frozen.json runs/<run_id> --era holdout --token COMMITTEE-HOLDOUT-READ` (the token is `load_data.COMMITTEE_TOKEN`). It writes `screens/<id>/out.holdout.json` and `trades.holdout.csv` (era-suffixed) and never touches the train `out.json`. The numbers are recorded in the prereg doc and committed. Decision rule (fixed in the doc before the read, applied by script code): CI95 upper < 0 → `DEAD_AT_HOLDOUT`; CI95 null (n < 2) → `HOLDOUT_INSUFFICIENT`; otherwise build. A non-build outcome stops here.
2. **Implement** — TDD: `tests/test_<id>_slot.py` first (signal parity against the frozen `signal.py` on synthetic AND train data — skipped when the research cache is absent — forming-bar exclusion, exit golden cases identical to `screen.simulate`, sidecar roundtrip, AST wiring, bare-bot orchestration, live mode with an open position places no orders) and adjudicator tests (statuses, the `.kill_<id>` touch, the no-write cases); then `<id>_slot.py` (pure; `signals()` transcribed verbatim from `screens/<id>/signal.py`, closed bars only), `bot.py` (one `StrategySlot` with the rails opt-out, `paper_mode=True`, strategy_name not in `STRATEGIES`; `self._evaluate_<id>(prices)` in `_evaluate_all_slots`; the per-symbol block begins with the `paper_mode` guard before any fetch/exit/open — `_close_slot_position` on a non-paper slot places a real order; the evaluator checks `slot.enabled` every cycle), `scripts/lab_adjudicator/adjudicate.py` (`EXPERIMENTS["<id>"]`, `grade_<id>` with the automatic kill, digest line). Files touched are limited to five: `<id>_slot.py`, `tests/test_<id>_slot.py`, `bot.py`, `scripts/lab_adjudicator/adjudicate.py`, `tests/test_lab_adjudicator.py`. Full suite must be at baseline + the new tests. One commit.
3. **Review** — an independent reviewer (JUDGE_MODEL applies here only) verifies against the files: no forming-bar reads, verbatim signal transcription, exit rule = `simulate`, live guard before the exit path, kill honoured, adjudicator numbers = prereg doc including the automatic kill, tests exercise the signal, scope of the diff (prereg commits identified by the files they touch), full pytest. A BLOCK returns `REVIEW_BLOCKED` with the findings and stops — no fix seat, no second review. Then the script returns `{result, branch, base_sha, files_changed, commits, holdout, review, next}` and stops.

Results: `BUILT` (→ Gate B), `DEAD_AT_HOLDOUT`, `HOLDOUT_INSUFFICIENT`, `HOLDOUT_ERROR`, `REVIEW_BLOCKED`, `IMPLEMENT_FAILED` (e.g. the frozen signal needs a `load_data` feed the bot lacks — an owner decision, never improvised), `PREREG_BRANCH_EXISTS`, `HOLDOUT_ALREADY_READ`, `PREREG_<other reason>`.

**The branch holds the only record of the holdout read** (the prereg doc + `out.holdout.json` in its commits). Never delete `swarm/<id>-slot` unmerged; never re-read holdout for the same thesis. `build.js` refuses to run while the branch exists on any ref, so a retry after `HOLDOUT_ERROR` (the read command itself failed, nothing was written) requires the owner to delete the branch by hand first — the script never does that. Build outcomes reach `kb/` through the desk's maintenance pass, not through `build.js`.

## Cadence (`scripts/swarm_desk.py` + two launchd jobs)

The desk runs on a schedule without the owner; nothing in this loop promotes a slot to live money, invokes `build.js`, or restarts the bot.

**What runs when.**

| job | schedule | command | what it does |
|---|---|---|---|
| `com.phmex.desk-weekly` | Sunday 3:00 AM PT (`Weekday 0 / Hour 3 / Minute 0`) | `swarm_desk.py --mode desk` | the maintenance pass, then ONE full desk run (`desk.js`, 8 analysts, ≤5 screens) through a headless `claude -p`; commits + pushes `kb/` and `runs/<run_id>/`; Telegram summary after every run |
| `com.phmex.desk-maint` | daily 6:30 AM PT (after the 6:00 AM adjudicator digest) | `swarm_desk.py --mode maint` | no LLM: rewrites `kb/PAPER_STATUS.md` from every registered paper slot's `trading_state_<id>.json` + the adjudicator's latest digest; Telegram only on an alert |

Weekly, not daily, by owner order (9/16): a full run is ~2.5M tokens and v1 died on rate ceilings. Both plists have `RunAtLoad false`, so loading a job never fires it. Every mode first checks the kill switch, then the run-alone guard, then the branch (`git rev-parse --abbrev-ref HEAD` must equal env `SWARM_BRANCH`, default `main`; both plists set `SWARM_BRANCH=main`; `desk`/`test` refuse with a Telegram "desk refused: on branch X, expected Y" + exit 1, `maint` only logs it), then `git pull --ff-only` (a failed pull is logged and the run continues on the local copy). The branch is logged in `swarm_desk.log` on every run. The versioned plist files live in `research/swarm/launchd/`; the installed copies live in `~/Library/LaunchAgents/`.

**The maintenance pass (`--mode maint`).** Reads the slot ids registered in `bot.py` (`slot_id="..."` inside `StrategySlot(...)`, minus the main-book label `5m_scalp`), each slot's `trading_state_<id>.json` + `_mode.json` sidecar, the `.kill_<id>` sentinel, and the last `digest:` block of `~/Library/Logs/Phmex-S/lab_adjudicator.log` (the adjudicator writes its grades only there, to stdout and to Telegram — there is no grades file). Kill lines come from `scripts/lab_adjudicator/adjudicate.py` `EXPERIMENTS` (build.js slots: `verdict_n` / `kill_net_usd` / `inconclusive_hard_n` / `registered_ts`; legacy `sr_bounce_v2` → SR_BOUNCE, `eth_tsm_28`) plus the Donchian spec's paper −$15 line; slots with no registered line say so. `PAPER_STATUS.md` shows per slot: mode, n, net USD (era `net_pnl` as-is), WR, days running, last close, kill line + distance to it, verdict_n progress, and the adjudicator's latest grade; killed slots (sentinel, sidecar `killed_at`, or the bot's own negative-Kelly switch at n ≥ 50) are listed separately; the file ends with `no paper slots running` when no active slot exists. The header states whether the bot process is alive and how old the adjudicator digest is. Crossing / verdict flags are kept in `kb/.maint_state.json` (gitignored); the first run is a baseline. When a slot newly crosses its kill line or newly reaches `verdict_n`, maint appends ONE dated line to `kb/LESSONS.md` and sends one Telegram; otherwise it is silent. Maint commits what it wrote (pathspec commit of `kb/PAPER_STATUS.md` when it changed, plus `kb/LESSONS.md` on an alert; NO push) so the next day's `pull --ff-only` never conflicts on a dirty file — the weekly desk run pushes. `PAPER_STATUS.md` is regenerated on every pass — never edit it by hand. Read it before proposing any slot work.

**The desk run (`--mode desk`).** After maint, the runner writes the exact `desk.js` args to `runs/<run_id>/launch_args.json` (`run_id` = launch time `YYYY-MM-DD-HHMM` PT, `now` = ISO UTC, `today` = PT date, `judge_model` from env `SWARM_JUDGE_MODEL` or null, `max_analysts 8`, `max_screens 5`, `dry_run false`, `constraints_md` / `standards_md` = the two kb files' contents) and launches `claude -p` with `--allowedTools Workflow WebSearch WebFetch Read Write Bash Glob Grep --permission-mode acceptEdits` (model from env `SWARM_DESK_MODEL`; unset = account default), 75-minute timeout. The prompt tells that session to invoke the Workflow tool on `desk.js` with the file's args verbatim and to reply with the result JSON. Then: `git add research/swarm/kb research/swarm/runs/<run_id>` (return code checked) and a PATHSPEC commit `git commit -m "swarm: desk run <run_id> — <result>" -- research/swarm/kb research/swarm/runs/<run_id>` (never `.env`, never data, never whatever else was staged), then `git push`. A desk.js result other than `WEB_BUDGET_EXHAUSTED` must leave `REPORT.md` AND `CRITIC.md` in the run dir (the closing seats write them); if either is missing the result becomes `NO_ARTIFACTS` (exit 1, Telegram with the one-liner). the headless session is launched with `--disallowedTools` denying launchctl / main.py / git push / kill / pkill / rm -rf; interactive sessions are unaffected; the push happens in swarm_desk.py outside the session.

**Known limit — pass-through fidelity.** `constraints_md` / `standards_md` reach `desk.js` by the headless session re-emitting the `launch_args.json` fields verbatim inside its Workflow call, which cannot be verified from outside the session. The prompt asks the session to add `constraints_len` / `standards_len` (the lengths of the strings it actually passed) to the `DESK_RESULT_JSON:` line; the runner compares them to the file contents and logs `pass-through fidelity OK` or a WARNING (`MISMATCH` / `not reported`) in `swarm_desk.log`. The controller reads that line once after `--mode test`.

**What Telegram sends.** Every desk run: the first 3 lines of `runs/<run_id>/REPORT.md` (or "REPORT.md missing"), the result code (`SURVIVORS`, `NO_SURVIVORS`, `ALL_REJECTED_AT_GATE`, `GATE_FAILED`, `NO_THESES`, `WEB_BUDGET_EXHAUSTED`), counts (theses · gate rejected · screened · passed), any maint alerts, and the git outcome. On `WEB_BUDGET_EXHAUSTED` (the analysts could not search), a timeout, a claude failure, or a missing result, the message says so and carries the manual launch one-liner below. Maint alone sends only on an alert (crossed kill line / reached verdict_n).

**The two owner gates still apply.** A committee PASS in a scheduled run (`SURVIVORS`) → Telegram names the survivor and says "Gate A: owner decision required — STOP". build.js is never invoked by the scheduler (the runner's prompt and argv never name it); the owner launches it by hand after saying "go" (see Build stage). Gate B (audited restart) is likewise human. Gate B checklist item: the automatic kill lines (`grade_<id>` touching `.kill_<id>`) only work while `com.phmex.lab-adjudicator` is loaded — it is re-enabled together with the bot at the restart (unloaded since the 9/9 wind-down; its plist is in `~/Library/LaunchAgents/disabled/phmex-winddown-2026-09-09/`). Until then `PAPER_STATUS.md` says "kill lines are not being graded automatically", and the maintenance pass reports crossings but kills nothing.

**Headless Workflow — which path is live.** `--mode test` runs the desk with the dry-run args (`max_analysts 1`, `max_screens 1`, `dry_run true`, run_id `dryrun-<stamp>`), then prints `HEADLESS WORKFLOW: OK` (a desk.js result code AND `REPORT.md` + `CRITIC.md` in the run dir — artifacts only the workflow writes), `UNAVAILABLE` (`claude -p` has no Workflow tool), or `FAILED`. Like a real run, `--mode test` commits and pushes the `dryrun-<stamp>` run dir together with the LESSONS line its reconciler appends, and sends a Telegram tagged `[TEST — dry-run args]`. If the Workflow tool is unavailable under `claude -p`, `--mode desk` cannot run the desk itself: it sends "desk run due — paste this into a fresh Claude Code session:" plus the one-liner, and the owner runs it interactively. Status: **HEADLESS WORKFLOW: OK** — verified 2026-09-17 2:41 AM PT (`--mode test`, run `dryrun-2026-09-17-0230`, result `ALL_REJECTED_AT_GATE`, REPORT.md + CRITIC.md present, pass-through fidelity OK: constraints_len=1995 standards_len=4678, committed 3c35a93 and pushed). The scheduled path is live; the Telegram-paste fallback remains in code for the UNAVAILABLE case.

Manual launch one-liner (also what Telegram sends on `WEB_BUDGET_EXHAUSTED` / timeout / fallback):

```
cd ~/Desktop/Phmex-S && claude — then paste: "Run the desk alone per research/swarm/README.md (Running the desk): confirm /workflows shows nothing live, Read kb/CONSTRAINTS.md + kb/STANDARDS.md, and invoke Workflow research/swarm/workflows/desk.js with run_id <YYYY-MM-DD-HHMM PT>, now <ISO UTC>, judge_model null, max_analysts 8, max_screens 5, dry_run false, constraints_md/standards_md = those file contents; then python3 -m research.swarm.lib.kb_check && git add research/swarm && git commit && git push."
```

**Kill switch.** `touch scripts/.halt_swarm_desk` (gitignored) — every mode logs "halt sentinel present" and exits 0 without pulling, launching or writing anything. `rm` it to resume. `--mode desk|test` also refuses (exit 3) while another `swarm_desk.py --mode desk|test` process is alive (pgrep on argv — the desk never runs concurrently with another workflow); maint never blocks anything.

**Logs.** `~/Library/Logs/Phmex-S/swarm_desk.log` (the runner's own log, every mode), `desk-weekly.out.log` / `desk-weekly.err.log` and `desk-maint.out.log` / `desk-maint.err.log` (launchd stdout/stderr). Never under `~/Desktop` (launchd + TCC → exit 78; `memory/feedback_launchd_tcc.md`). Judge the jobs by `launchctl print gui/$(id -u)/com.phmex.desk-weekly` counters (`runs`, `last exit code`), not by log mtimes.

**Install (controller, after this task).**

```
cp research/swarm/launchd/com.phmex.desk-weekly.plist research/swarm/launchd/com.phmex.desk-maint.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.phmex.desk-weekly.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.phmex.desk-maint.plist
launchctl print gui/$(id -u)/com.phmex.desk-weekly | grep -E "state|runs|last exit"
python3 scripts/swarm_desk.py --mode maint     # by hand once; read kb/PAPER_STATUS.md
python3 scripts/swarm_desk.py --mode test      # headless-Workflow feasibility; record the answer above
```

**Flip weekly ↔ daily.** Edit the installed `~/Library/LaunchAgents/com.phmex.desk-weekly.plist` (and the versioned copy so git matches): daily = delete the `Weekday` key from `StartCalendarInterval` (keeping `Hour 3 / Minute 0`); weekly = put `<key>Weekday</key><integer>0</integer>` back. launchd only reads a plist at load, so reload it:

```
launchctl bootout gui/$(id -u)/com.phmex.desk-weekly
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.phmex.desk-weekly.plist
launchctl print gui/$(id -u)/com.phmex.desk-weekly | grep -E "state|runs|last exit"
```

Daily full runs are NOT the owner's standing order — flip only on an explicit instruction (token cost ~2.5M/run). To stop a job for good: `launchctl bootout gui/$(id -u)/<label>` and move the plist to `~/Library/LaunchAgents/disabled/`.

Syntax check without running: the body uses top-level `return` inside the harness's async wrapper, so plain `node --check` reports "Illegal return statement" for both `desk.js` and `build.js`; wrap the body in an `async function` before `node --input-type=module --check` (see the Task 8 report for the one-liner).
