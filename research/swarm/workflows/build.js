// build.js — Edge Swarm v2 BUILD stage.
//
// Turns exactly ONE committee-PASS thesis (from a desk.js run) into a pre-registered
// PAPER slot on the bot, following docs/2026-09-16-edge-swarm-v1/02_framework_audit.md
// §3.6 (the bespoke Donchian recipe), on its own git branch, and STOPS.
//
// TWO OWNER GATES, BOTH HUMAN — this script sits between them:
//   Gate A — the owner says "go" BEFORE this script is invoked. A committee PASS is not
//            a go: the controller stops after desk.js and asks. Never launch build.js
//            on the controller's own judgment.
//   Gate B — after this script finishes, the owner reviews the branch, runs
//            /pre-restart-audit, and says "go" AGAIN before any restart. Nothing this
//            script writes is live until that audited restart (CLAUDE.md: editing a
//            file ≠ the bot using it).
// build.js itself NEVER restarts anything, never touches launchd, never places an
// order, never merges or pushes, never writes under research/swarm/kb/, and never edits
// the frozen spec or signal.py. It ends after the reviewer seat with the branch name and
// the list of files changed (a reviewer BLOCK returns REVIEW_BLOCKED — no unsupervised
// fix seat edits bot code). It leaves the working tree checked out on the build branch.
// The prereg doc committed on the branch is the durable record of the holdout read.
//
// RESUME (args.resume_after_prereg, 2026-09-20): a build that stopped AFTER the prereg
// branch + the one holdout read (e.g. IMPLEMENT_FAILED because the frozen signal needs a
// data feed) is resumed on its existing branch: the Prereg phase is replaced by a
// deterministic precondition check (branch exists, prereg doc present with a BUILD
// decision, out.holdout.json recorded, frozen sha verifies) and NOTHING is re-read —
// the spent holdout read stays spent. Implement → Review run exactly as in a fresh build.
// REFERENCE FEED (args.reference_feed = "exchange_ohlcv" + args.owner_decision): the
// owner may authorise a cross-asset slot to fetch its reference symbol's CLOSED bars
// live via exchange.get_ohlcv (one extra request per cycle); the implementer then
// transcribes the frozen signal's load_reference(...) call as that fetch, exposes
// signals(df, ref_df), and appends the owner's decision verbatim to the prereg doc.
// Without that arg the IMPLEMENT seat still stops (IMPLEMENT_FAILED) instead of
// improvising a feed — an owner decision is never made by a seat.
//
// Harness rules (same as desk.js): no clock, no filesystem — timestamps and the two
// governing documents arrive through args; `meta` is a pure literal; every phase()
// title exists in meta.phases.

export const meta = {
  name: 'edge-desk-v2-build',
  description: 'Committee-passed thesis → pre-registered paper slot on a branch (prereg + ONE holdout read, TDD build, reviewer); stops before any restart; resumable after prereg',
  whenToUse: 'Only after a desk.js committee PASS AND the owner\'s explicit "go" (Gate A). Run alone from the Phmex-S repo root with args {run_id, thesis_id, now, judge_model, constraints_md, standards_md} (+ resume_after_prereg / reference_feed / owner_decision for a resume with an owner-authorised reference feed); see research/swarm/README.md "Build stage"',
  phases: [
    { title: 'Prereg', detail: 'branch from HEAD, prereg doc with frozen KILL/PASS lines committed, then the ONE holdout read, recorded (resume: precondition check only, nothing re-read)' },
    { title: 'Implement', detail: 'tests first, <id>_slot.py from the frozen signal.py (closed bars), bot.py wiring, adjudicator, reporting' },
    { title: 'Review', detail: 'independent reviewer (judge model) + full suite; BLOCK stops the run; stop before Gate B' },
  ],
}

// ---------------------------------------------------------------------------
// Args — see research/swarm/README.md "Build stage" for the launch invocation.
// ---------------------------------------------------------------------------
const A = args || {}
const RUN_ID = A.run_id
const THESIS_ID = A.thesis_id
const NOW = A.now || null                                               // ISO UTC; registered_ts source (required)
const TODAY = A.today || (NOW ? NOW.slice(0, 10) : null)                 // YYYY-MM-DD; prereg filename
const JUDGE_MODEL = A.judge_model || null                                // applied ONLY to the reviewer seat
const CONSTRAINTS_MD = A.constraints_md
const STANDARDS_MD = A.standards_md
const SUITE_BASELINE = A.suite_baseline || '1064 passed, 1 known ordering-only failure'  // repo suite after Task 7
const RESUME = A.resume_after_prereg === true                              // skip Prereg; precondition check on the existing branch
const RESUME_NOW = A.resume_now || NOW                                     // ISO UTC of the resume launch; dates the owner-decision section only
const REFERENCE_FEED = A.reference_feed ?? null                            // null | "exchange_ohlcv" (owner-authorised live reference series)
const OWNER_DECISION = A.owner_decision || null                            // verbatim owner text; required with reference_feed
if (!RUN_ID || !THESIS_ID || !NOW || !TODAY) throw new Error('build.js: args.run_id, args.thesis_id and args.now (ISO UTC) are required — the script has no clock')
if (!/^[a-z][a-z0-9_]{2,40}$/.test(THESIS_ID)) throw new Error(`build.js: thesis_id ${JSON.stringify(THESIS_ID)} must match the registrar id rule ^[a-z][a-z0-9_]{2,40}$ (it becomes a Python module, a slot_id and a kill-file name)`)
if (!CONSTRAINTS_MD || !STANDARDS_MD) throw new Error('build.js: args.constraints_md and args.standards_md (file CONTENTS of kb/CONSTRAINTS.md and kb/STANDARDS.md) are required — every prompt embeds them')
if (REFERENCE_FEED !== null && REFERENCE_FEED !== 'exchange_ohlcv') throw new Error(`build.js: args.reference_feed ${JSON.stringify(REFERENCE_FEED)} must be null or "exchange_ohlcv"`)
if (REFERENCE_FEED && (typeof OWNER_DECISION !== 'string' || OWNER_DECISION.trim().length < 20)) throw new Error('build.js: args.owner_decision (the owner\'s decision text, verbatim, dated) is required whenever args.reference_feed is set — a seat never authorises a data feed on its own')
if (A.resume_after_prereg !== undefined && typeof A.resume_after_prereg !== 'boolean') throw new Error('build.js: args.resume_after_prereg must be a boolean')

const REPO = '/Users/jonaspenaso/Desktop/Phmex-S'
const RUN_DIR = `research/swarm/runs/${RUN_ID}`
const KB = 'research/swarm/kb'
const ID = THESIS_ID
const BRANCH = `swarm/${ID}-slot`
const FROZEN = `${RUN_DIR}/specs/${ID}.frozen.json`
const SCREEN_DIR = `${RUN_DIR}/screens/${ID}`
const SIGNAL_PY = `${SCREEN_DIR}/signal.py`
const OUT_TRAIN = `${SCREEN_DIR}/out.json`
const OUT_HOLDOUT = `${SCREEN_DIR}/out.holdout.json`          // era-suffixed by screen.run_screen; train out.json is never touched
const TRADES_HOLDOUT = `${SCREEN_DIR}/trades.holdout.csv`
const PREREG = `docs/superpowers/specs/${TODAY}-${ID}-prereg.md`
const MODULE = `${ID}_slot.py`
const TEST = `tests/test_${ID}_slot.py`
const KILL_FILE = `.kill_${ID}`
const STATE_FILE = `trading_state_${ID}.json`               // written by StrategySlot's risk manager; dashboard auto-discovers it
const COMMITTEE_TOKEN = 'COMMITTEE-HOLDOUT-READ'             // research/swarm/lib/load_data.py: COMMITTEE_TOKEN
const HOLDOUT_CMD = `python3 -m research.swarm.lib.screen ${FROZEN} ${RUN_DIR} --era holdout --token ${COMMITTEE_TOKEN}`
const TRAILER = 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>'

// Frozen verdict line (brief + controller ruling 4). These are constants on purpose:
// there is no args override, so no launch can soften the line.
const VERDICT_N = 50
const KILL_NET_USD = -10.0
const INCONCLUSIVE_HARD_N = 2 * VERDICT_N

// The files the IMPLEMENT seat may touch, and nothing else (bot trading code is
// modified ONLY here, ONLY on the branch).
const ALLOWED_FILES = [MODULE, TEST, 'bot.py', 'scripts/lab_adjudicator/adjudicate.py', 'tests/test_lab_adjudicator.py']
// With an owner-authorised reference feed the IMPLEMENT seat may ALSO append (never edit)
// the owner-decision section to the prereg doc, in its own doc-only commit before the
// implement commit. That commit is the only prereg-doc change a non-prereg seat may make.
const OWNER_DECISION_HEADING = '## Owner decision (reference feed)'
const OWNER_DECISION_COMMIT_MSG = `prereg(${ID}): owner decision — reference feed via exchange OHLCV`
const IMPL_DOC_FILES = REFERENCE_FEED ? [PREREG] : []
// Reviewer scope arithmetic: prereg commits (doc + holdout artifacts) expected in
// base_sha..HEAD — 2 in a fresh build, 0 on resume (base_sha is then the branch tip);
// plus the owner-decision doc commit when a reference feed is authorised.
const PREREG_COMMITS_EXPECTED = RESUME ? 0 : 2
const DOC_COMMITS_EXPECTED = REFERENCE_FEED ? 1 : 0

// JUDGE_MODEL is applied to exactly one seat: the reviewer. Never the prereg writer, the
// holdout reader/recorder or the implementer.
const judge = (opts) => (JUDGE_MODEL ? { ...opts, model: JUDGE_MODEL } : opts)

// ---------------------------------------------------------------------------
// RULES — prepended to EVERY agent prompt; carries kb/CONSTRAINTS.md + kb/STANDARDS.md.
// ---------------------------------------------------------------------------
const HOLDOUT_RULE = RESUME
  ? `- Holdout data (era="holdout"/"all") was read EXACTLY ONCE in the ORIGINAL build of this thesis; the result is committed on ${BRANCH} as ${OUT_HOLDOUT} (+ ${TRADES_HOLDOUT}) and recorded in ${PREREG}. This is a RESUME: NO seat reads holdout again — nobody passes --era holdout/all or the committee token, nobody runs research.swarm.lib.screen, and no seat opens the cache files under reports/cache/ or scripts/research/ directly. Reading the committed ${OUT_HOLDOUT} artifact is allowed (it is the record, not the data); it is never used to change a parameter.`
  : `- Holdout data (era="holdout"/"all") is read EXACTLY ONCE in this build, by the HOLDOUT-READ seat, via the single CLI it is given. No other seat passes --era holdout/all or the committee token, and no seat opens the cache files under reports/cache/ or scripts/research/ directly. The result of that read lives in ${OUT_HOLDOUT} and is copied into ${PREREG}; it is never used to change a parameter.`
const REFERENCE_FEED_RULE = REFERENCE_FEED
  ? `- OWNER-AUTHORISED REFERENCE FEED (args.reference_feed = "${REFERENCE_FEED}"): the owner has decided that this slot MAY fetch its reference symbol's CLOSED bars live via self.exchange.get_ohlcv(<reference symbol>, <reference timeframe>, limit=OHLCV_LIMIT) — one extra request per cycle, closed bars only, intersected on the alt's closed-bar index exactly as the frozen signal does. The decision text, verbatim (args.owner_decision): <<<${OWNER_DECISION}>>>. This authorises ONLY the transcription of the frozen signal's load_reference(...) call(s) into that fetch; any other research.swarm.lib.load_data use in the signal is still a stop (IMPLEMENT_FAILED). The IMPLEMENT seat APPENDS the section "${OWNER_DECISION_HEADING}" to ${PREREG} (append-only; no existing line of the doc changes) in its own doc-only commit BEFORE the implement commit.`
  : ''
const RULES = `You are one seat on the BUILD stage of a quant research desk for the Phmex-S bot (repo ${REPO}). Work from the repo root. Run id: ${RUN_ID}; thesis: ${ID}. Clock: now = ${NOW} (UTC), today = ${TODAY}.${RESUME ? ` THIS IS A RESUME (args.resume_after_prereg): the prereg branch, doc and holdout read already exist from the original build; now/today are the ORIGINAL registration clock (registered_ts and the prereg filename derive from them); the resume itself was launched at ${RESUME_NOW} (UTC).` : ''}
Inputs (read-only, all of them): frozen spec ${FROZEN}; frozen signal ${SIGNAL_PY}; train screen ${OUT_TRAIN} (+ trades.csv, audit.json, out.robust_plus.json, out.robust_minus.json in ${SCREEN_DIR}/); committee votes ${RUN_DIR}/committee/{economics,statistics,bh}.json; the run report ${RUN_DIR}/REPORT.md. Knowledge base: ${KB}/. The two governing documents are embedded below verbatim — obey them; the files in ${KB}/ are canonical if they ever differ.
HARD RULES:
- The frozen spec ${FROZEN} and ${SIGNAL_PY} are NEVER edited by anyone, for any reason — not to fix an import, not to rename, not to "clean up". A change to the idea is a new thesis through desk.js. Nothing under research/swarm/lib/ is edited either.
${HOLDOUT_RULE}
- Bot trading code (bot.py, strategies.py, risk_manager.py, exchange.py, config.py, strategy_slot.py, any *_slot.py) is modified ONLY on git branch ${BRANCH}, ONLY in these files: ${ALLOWED_FILES.join(', ')}, ONLY by the IMPLEMENT seat. Every other seat is read-only on code. Nothing under ${KB}/ is written by any seat of this stage (kb rows are the desk's maintenance pass, not the build's).${REFERENCE_FEED_RULE ? `\n${REFERENCE_FEED_RULE}` : ''}
- NEVER start, stop, restart or signal the bot; never run launchctl, kill, pkill, main.py, or anything that places an order; never touch .env, any trading_state*.json, any sentinel file (.paper_main, .kill_*, .promote_*, .demote_*, .halt_*), any launchd plist, or logs/. Restart is a separate owner gate (/pre-restart-audit) that this stage never crosses.
- git: all work is on branch ${BRANCH}; never merge, rebase, push, reset --hard, stash, or switch to another branch; stage EXPLICIT paths only (never git add -A / -u / . — the working tree carries unrelated pre-existing modifications that are not yours and must stay untouched and unstaged); every commit message ends with the line: ${TRAILER}
- Never hand-roll statistics: every CI / bootstrap / p* / break-even number comes from research.swarm.lib (fee_math.p_star / net_bps / time_to_verdict_weeks / lot_check / position_notional, bootstrap_ci.mean_ci / diff_ci). Cite the file path for every number you report. "Not run" is a valid answer; a made-up number is not. No daily-ROI target anywhere.
Your final message is a return value read by a script, not prose for a human — return exactly what the task asks for.

=== ${KB}/CONSTRAINTS.md (embedded verbatim) ===
${CONSTRAINTS_MD}
=== ${KB}/STANDARDS.md (embedded verbatim) ===
${STANDARDS_MD}
=== end of embedded knowledge base ===
`

const VERDICT_LINE = `VERDICT LINE (frozen; the adjudicator implements it numerically, the prereg doc states it verbatim):
- Ledger: closed_trades of ${STATE_FILE} with closed_at >= registered_ts (the epoch of ${NOW}); net = sum of each row's net_pnl AS-IS (fee-inclusive at the source — risk_manager deducts sim fees at close; never re-subtract), via the adjudicator's existing _net(t).
- verdict_n = ${VERDICT_N}.
- KILL: n >= ${VERDICT_N} and net <= 0.
- KILL: net <= ${KILL_NET_USD.toFixed(2)} USD at ANY n (dollar loss cap).
- PASS: n >= ${VERDICT_N} and the lower bound of the bootstrap CI95 of per-trade net USD (research.swarm.lib.bootstrap_ci.mean_ci, defaults: 2000 reps, alpha 0.05, seed 0) > 0.
- INCONCLUSIVE: n >= ${VERDICT_N}, net > 0, CI95 lower bound <= 0 → keep accruing, re-grade at every n; hard stop at n = ${INCONCLUSIVE_HARD_N}: PASS if the CI95 lower bound > 0 there, else KILL.
- WATCH: n < ${VERDICT_N} and net > ${KILL_NET_USD.toFixed(2)}.
- ENFORCEMENT (spec §7 "kill line enforced automatically"): the adjudicator's grade_<id> TOUCHES ${KILL_FILE} when a KILL clause is hit — the two KILL lines above AND the INCONCLUSIVE hard stop at n = ${INCONCLUSIVE_HARD_N} — paper-only, zero market risk: the bot's existing .kill_* sentinel loop closes the paper book and persists the kill. The slot's own rails stay opted out (loss_cap_usdt −999.0, kelly_min_trades 10**9) because this line is the enforcement. PASS is never a promotion: it makes the thesis PASS-ELIGIBLE for an owner decision; the grader never writes .promote_* and promotes nothing.
ANTI-FISHING CLAUSE (frozen): no change to tp_bps, sl_bps, max_hold_bars, universe, timeframe or the signal during the paper era; no second holdout read; any deviation or data problem found during the run is REPORTED as a finding, never fixed-and-re-run; a parameter change is a new thesis through the desk with its own pre-registration. Rollback at any time = touch ${KILL_FILE} (paper-only, zero market risk).`

// ---------------------------------------------------------------------------
// Prompts
// ---------------------------------------------------------------------------
const preregPrompt = `${RULES}
PREREG seat (writes the pre-registration BEFORE the holdout read; this prompt contains no holdout token and you may not read holdout).
Step 0 — preconditions, all mechanical, IN THIS ORDER, stop with ok=false (and create nothing, check out nothing) on the first failure:
  a. Branch must not exist on any ref: "git rev-parse --verify --quiet refs/heads/${BRANCH}" must FAIL and "git branch -a --list '*${BRANCH}'" must print nothing (else status PREREG_BRANCH_EXISTS — a previous build of this thesis exists and may hold the spent holdout read; the owner deletes the branch by hand if a retry is really wanted; you never do).
  b. The holdout must never have been read on ANY ref, and no prereg doc may exist: "git log --all --oneline -- ${OUT_HOLDOUT} ${TRADES_HOLDOUT} ${PREREG}" must print nothing, "git cat-file -e ${BRANCH}:${OUT_HOLDOUT}" and "git cat-file -e ${BRANCH}:${PREREG}" must fail, and neither ${OUT_HOLDOUT} nor ${PREREG} may exist in the working tree (else status HOLDOUT_ALREADY_READ — the one read was already spent; do not read again, do not delete anything).
  c. python3 -c "from research.swarm.lib import registrar as r; print(r.verify('${FROZEN}'))" must print True (else status FROZEN_SHA_MISMATCH).
  d. ${RUN_DIR}/committee/economics.json AND ${RUN_DIR}/committee/statistics.json must each contain a vote for id "${ID}" with pass true (else status NOT_A_COMMITTEE_PASS — this stage runs only on a committee pass).
  e. Only now, git: record base_branch = output of "git rev-parse --abbrev-ref HEAD" and base_sha = output of "git rev-parse HEAD", then create the build branch FROM THIS HEAD: "git checkout -b ${BRANCH}". If the working tree has unstaged changes, leave them exactly as they are.
Step 1 — write ${PREREG} in the house format (tone and section shape of docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md and docs/superpowers/specs/2026-07-30-sr-bounce-v2-fixed-geometry-prereg.md). Sections, in this order:
  # PRE-REGISTRATION — ${ID} paper slot
  **Registered**: ${NOW} UTC (also give the PT wall time via python3 -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.fromisoformat('${NOW.replace('Z', '+00:00')}').astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d %-I:%M %p PT'))"), run ${RUN_ID}, Gate A (owner "go") passed before this script was invoked.
  **Thesis**: mechanism, counterparty, prediction — VERBATIM from the "thesis" object in ${FROZEN} (fields mechanism / counterparty / prediction), plus source_urls (from the same thesis object) and evidence_grade (from ${RUN_DIR}/gate_kept.json, the gatekeeper's kept entry for this id).
  ## Frozen data — dataset, universe, timeframe, tp_bps, sl_bps, max_hold_bars, expected_trades_per_week, doa_line (all from ${FROZEN}); frozen spec path + its sha256 field; signal sha256 from ${OUT_TRAIN}; train_span from ${OUT_TRAIN}; holdout = final 25% of the dataset range per load_data.holdout_start (state it as the rule, do not compute dates from holdout rows). If the frozen spec's dataset is "long_1h", this section also records the caveat verbatim: "holdout window overlaps mr_edge train; treat the holdout read as a sanity read only" (cross-dataset holdout caveat, STANDARDS #6).
  ## Economics — $200 basis; notional per trade = the printed output of python3 -c "from research.swarm.lib import fee_math as f; print(f.position_notional())"; c = fee_math.C_BPS (print it); p* = p_star from ${OUT_TRAIN}; lot_check per symbol from ${OUT_TRAIN}; if max_hold_bars × bar size > 8h, state the funding exposure per CONSTRAINTS. Paper convention: 1x paper book, margin recorded AS the notional (Donchian convention, donchian_slot.py / _donchian_open_paper), so USD PnL = notional × price move and ROI% = price move %.
  ## Slot design (paper only) — slot_id ${ID}; module ${MODULE}; tests ${TEST}; state file ${STATE_FILE} (auto-discovered by web_dashboard.read_all_slot_states); sidecars ${ID}_slot_state.json + ${ID}_signal_<SYM>.json (never prefixed trading_state_); signals computed on CLOSED bars only, transcribed from ${SIGNAL_PY} (signal on closed bar i → paper entry at the first price after bar i closes, ≈ open[i+1]); exit rule transcribed from research/swarm/lib/screen.py simulate(): each later closed bar checks SL then TP against low/high (SL wins ties), TIME exit at max_hold_bars at that bar's close; exit tags stop_loss / take_profit / time_exit; paper_mode True, loss_cap_usdt −999.0, kelly_min_trades 10**9, durable_trail_enabled False (rails opt-out: the verdict line below is the only kill); kill file ${KILL_FILE} touched automatically by the adjudicator on a KILL (see the verdict line) or by hand, honoured by the bot's generic .kill_* sentinel loop and by the evaluator's slot.enabled check every cycle; live path NOT implemented (a promoted slot logs an error once per UTC day and places nothing, identical to _donchian_adjust_position).
  ## Verdict line (frozen) — copy the following block verbatim:
${VERDICT_LINE}
  ## Prior (train, read before this registration) — from ${OUT_TRAIN}: n, net_bps_mean, ci95, wr vs p_star, trades_per_week, time_to_verdict_weeks; from ${SCREEN_DIR}/audit.json: verdict, numbers.p_boot; from ${RUN_DIR}/committee/bh.json: this id's BH row; from ${RUN_DIR}/committee/economics.json and statistics.json: the two votes' reasons; from ${SCREEN_DIR}/out.robust_plus.json and out.robust_minus.json: net_bps_mean of each. EVERY number followed by the path it came from. Missing file → "not run".
  ## Holdout (read once) — write exactly this, nothing more: "PENDING — the single registered holdout read happens AFTER this document is committed, by the command: ${HOLDOUT_CMD} (writes ${OUT_HOLDOUT} and ${TRADES_HOLDOUT}; the train out.json is never touched). Decision rule fixed now: ci95 upper bound < 0 → DEAD-AT-HOLDOUT (no build); ci95 null (n < 2) → HOLDOUT-INSUFFICIENT (no build; owner decision); otherwise → BUILD. The holdout numbers are recorded below and never used to change anything above."
Step 2 — commit exactly that one file on the branch: git add ${PREREG} && git commit -m "prereg(${ID}): pre-registration written before the holdout read" -m "${TRAILER}". Record commit_sha (git rev-parse HEAD).
Return {ok, status ("REGISTERED" on success, else one of PREREG_BRANCH_EXISTS / HOLDOUT_ALREADY_READ / FROZEN_SHA_MISMATCH / NOT_A_COMMITTEE_PASS / ERROR), base_branch, base_sha, prereg_path, commit_sha, error}.`

const holdoutReadPrompt = `${RULES}
HOLDOUT-READ seat (mechanical, low effort). This is the ONE registered holdout read of thesis ${ID}; the decision rule was committed in ${PREREG} before you ran. Run exactly this one command and nothing else that writes:
${HOLDOUT_CMD}
It writes ${OUT_HOLDOUT} and ${TRADES_HOLDOUT} (era-suffixed) and never touches ${OUT_TRAIN} or trades.csv — do NOT copy, move, rename or delete any file. Do NOT edit the frozen spec, signal.py, or anything under research/swarm/lib/. Do NOT retry with modifications and do NOT run it twice. If the command errors, return ok=false with the last 15 lines of the traceback in error. On success return ok=true, out_path = ${OUT_HOLDOUT}, and n, net_bps_mean, ci95, wr, p_star exactly as read from that file (null fields stay absent).`

const holdoutRecordPrompt = (h, decision) => `${RULES}
HOLDOUT-RECORD seat. The registered holdout read has run. Orchestrator-computed decision (from the rule already committed in ${PREREG}): ${decision}. Reader result: ${JSON.stringify(h)}.
Edit ${PREREG} ONLY under "## Holdout (read once)": replace the PENDING paragraph with: read at ${NOW}; the command (${HOLDOUT_CMD}); out path ${OUT_HOLDOUT}; n, net_bps_mean, ci95, wr, per_symbol, trades_per_week — each read from ${OUT_HOLDOUT} yourself (not from the reader's message) and each followed by that path; then "Decision: ${decision}" and one sentence restating which clause of the fixed rule produced it. If the decision is DEAD_AT_HOLDOUT / HOLDOUT_INSUFFICIENT / HOLDOUT_ERROR, also insert as the SECOND line of the document "STATUS: ${decision}" (for HOLDOUT_ERROR include the error text). Change nothing else in the document — not the verdict line, not the economics, not the prior.
Commit: git add ${PREREG} ${OUT_HOLDOUT} ${TRADES_HOLDOUT} (only those that exist) && git commit -m "prereg(${ID}): holdout read recorded — ${decision}" -m "${TRAILER}". Return the full document text.`

const resumeCheckPrompt = `${RULES}
RESUME-CHECK seat (mechanical, deterministic, low effort; replaces the Prereg phase on a resume). Nothing is created, nothing is read from holdout, nothing is committed. Run these checks IN THIS ORDER and stop with ok=false, status RESUME_PRECONDITION_FAILED and a one-line reason on the FIRST failure (checks a–b run before any checkout; a failed check leaves the tree wherever it is):
  a. Branch exists: "git rev-parse --verify --quiet refs/heads/${BRANCH}" must succeed (reason "branch ${BRANCH} missing — nothing to resume; a fresh build goes through the Prereg phase").
  b. Nothing staged: "git diff --cached --quiet" must succeed (reason "index not clean — staged changes would be swept into the implement commit"). Unstaged modifications to unrelated files are expected and stay untouched.
  c. Checkout: "git checkout ${BRANCH}" (if it fails, reason = git's message; never use -f, stash, or reset). Then "git rev-parse --abbrev-ref HEAD" must print ${BRANCH}.
  d. Prereg doc: "git cat-file -e ${BRANCH}:${PREREG}" must succeed AND the file must exist in the working tree (reason "prereg doc ${PREREG} not on the branch — check args.today: the prereg filename date is the ORIGINAL registration date, not the resume date"). Read it. Its second line must NOT start with "STATUS: DEAD_AT_HOLDOUT" / "STATUS: HOLDOUT_INSUFFICIENT" / "STATUS: HOLDOUT_ERROR" (reason = that status; a non-build outcome is never resumed). The "## Holdout (read once)" section must contain "Decision: BUILD" and must not contain "PENDING" (reason "holdout not recorded as BUILD"). The document must contain the exact substring "the epoch of ${NOW}" (reason "args.now must equal the ORIGINAL registration timestamp in the prereg doc's verdict line — the adjudicator's registered_ts and the reviewer's check derive from args.now"). Record prereg_status = the second line if it starts with "STATUS:", else "BUILD".
  e. Holdout artifact: ${OUT_HOLDOUT} must exist in the tree AND be committed on the branch ("git log --oneline ${BRANCH} -- ${OUT_HOLDOUT}" non-empty; reason "out.holdout.json missing/uncommitted"). Read n, net_bps_mean, ci95, wr, p_star from it with one python3 json one-liner (this is the committed record of the spent read; do NOT run research.swarm.lib.screen). ci95 must be a list of exactly 2 numbers and n >= 2 (reason "ci95 not a 2-array").
  f. Frozen sha: python3 -c "from research.swarm.lib import registrar as r; print(r.verify('${FROZEN}'))" must print True (reason "FROZEN_SHA_MISMATCH").
  g. Owner-decision section not already present${REFERENCE_FEED ? `: grep -c "${OWNER_DECISION_HEADING}" ${PREREG} must print 0 (reason "owner-decision section already appended — a previous resume got past the doc commit; owner inspects the branch by hand")` : ' — not applicable (no reference feed requested); skip'}.
  h. Only now record base_sha = "git rev-parse HEAD" (the branch tip; the reviewer diffs base_sha..HEAD, so it covers only what this resume commits) and head_subject = "git log -1 --format=%s".
Return {ok, status ("RESUMED" on success, else RESUME_PRECONDITION_FAILED / ERROR), base_sha, head_subject, prereg_status, n, net_bps_mean, ci95, wr, p_star, error}.`

// ---- IMPLEMENT prompt fragments that depend on the reference-feed decision ----
// Without an owner decision the seat STOPS on any load_data use (no improvised feed).
// With reference_feed="exchange_ohlcv" the ONLY authorised transcription is
// load_reference(<SYM>, <tf>, ...) → exchange.get_ohlcv(<SYM in exchange form>, <tf>,
// limit=OHLCV_LIMIT) → complete_bars → intersect, with the reference frame an explicit
// argument of the pure signal function so the parity tests can feed the research cache.
const IMPL_GUARD = REFERENCE_FEED
  ? `Guard before writing anything: read ${SIGNAL_PY}. Its ONLY permitted dependency outside pandas/numpy is research.swarm.lib.load_data.load_reference(<SYM>, <tf>, dataset=...) call(s) — the owner has authorised (HARD RULES, "OWNER-AUTHORISED REFERENCE FEED") transcribing exactly those into a live reference fetch. Record each such call (symbol, timeframe, dataset) in notes. If the file uses ANY other load_data function (load_ohlcv, load_funding, load_reference_funding, ...), reads the cache directly, or imports anything else outside pandas/numpy, STOP and return ok=false with error "signal needs a data feed the slot lacks: <what>" — the owner decision covers reference OHLCV only. TRANSCRIPTION (binding): the reference symbol in exchange form is the frozen base symbol mapped exactly as the universe symbols are (e.g. frozen "BTC" → "BTC/USDT:USDT", cf. tsm_slot.TSM_BTC_SYMBOL); REF_SYMBOL / REF_TIMEFRAME are module constants with the frozen call quoted in a comment; the reference frame is fetched via self.exchange.get_ohlcv(REF_SYMBOL, REF_TIMEFRAME, limit=OHLCV_LIMIT), reduced to CLOSED bars with the same complete_bars() as the alt, and intersected on the alt's closed-bar index exactly as the frozen file does (df.index.intersection(ref.index) — same line, same reindex/fillna); the pure module exposes signals(df, ref_df) with the reference frame as an explicit second argument (pure, testable, no I/O), and the bot orchestration fetches the reference ONCE per cycle (never per symbol) and hands the same closed frame to every symbol's evaluation. Both frames must share one index convention — the orchestration passes two exchange frames (naive-UTC DatetimeIndex, exchange.get_ohlcv shape) and the parity test passes two research-cache frames (tz-aware UTC); signals() must not convert either (verbatim body).`
  : `Guard before writing anything: if ${SIGNAL_PY} imports or calls research.swarm.lib.load_data (any loader — the bot has no such feed; load_funding is a research-cache reader) or anything outside pandas/numpy, STOP and return ok=false with error "signal needs a data feed the slot lacks: <what>" — do not improvise a live substitute; that is an owner decision (the owner authorises one with args.reference_feed + args.owner_decision on a resume).`
const PARITY_TESTS = REFERENCE_FEED
  ? `   (a) signal parity, SYNTHETIC: load signals() from ${SIGNAL_PY} (importlib from the path; read-only) and the slot module's signals(df, ref_df); build a synthetic alt frame and a synthetic reference frame on the same 1h grid (with rows the alt lacks and rows the reference lacks, so the intersection is exercised, and enough pump/laggard rows that the signal fires at least once and stays 0 elsewhere); monkeypatch the frozen module's loader (monkeypatch.setattr(<frozen module>.ld, "load_reference", lambda *a, **k: ref_df)) and assert exact equality (pandas.testing.assert_series_equal) of frozen signals(df) and module signals(df, ref_df) — index, values, dtype;
   (a2) signal parity, REAL TRAIN DATA (this proves the transcription): pytest.skip when the dataset's cache directory — research.swarm.lib.load_data.DATASETS[<spec.dataset>]["dir"] under the repo root — is absent; otherwise ref = load_data.load_ohlcv(<frozen reference symbol>, <frozen reference tf>, era="train", dataset=<spec.dataset>) and, for AT LEAST 3 universe symbols, df = load_data.load_ohlcv(sym, <tf>, era="train", dataset=<spec.dataset>); assert frozen signals(df) (real path, no monkeypatch — with no screen context load_reference IS the train load) equals module signals(df, ref) exactly (assert_series_equal; both are reindexed to df.index by the same verbatim lines, so equality on df.index is equality on the intersected index), and assert the series contains at least one non-zero value for at least one of the symbols (a trivially-all-zero parity proves nothing);`
  : `   (a) signal parity: load signals() from ${SIGNAL_PY} (importlib from the path; read-only) and the slot module's signal function; assert exact equality of the two series on a synthetic OHLCV frame AND on real TRAIN data of one universe symbol (research.swarm.lib.load_data.load_ohlcv(sym, tf, era="train", dataset=<spec.dataset>); pytest.skip when that dataset's cache directory — load_data.DATASETS[<dataset>]["dir"] under the repo root — is absent, so the suite stays green on a machine without the research cache) — this is the transcription check against the frozen file;`
const REF_ORCH_TESTS = REFERENCE_FEED
  ? `
   (f2) reference feed orchestration (same bare-bot fixture): with N universe symbols configured, one evaluation cycle makes EXACTLY ONE get_ohlcv call for REF_SYMBOL (count FakeExchange.calls by symbol) and one per alt — never one reference call per alt; the reference frame handed to the signal is CLOSED-bar only: a reference pump that exists only in the forming (last, not yet closed) reference bar must NOT fire an entry, while the same pump on a closed bar does; reference fetch returning None/empty → no alt is evaluated, no entry, no bar stamp (st["last_bar_ts"] unchanged) and a warning log (retry next cycle); reference lagging (last closed reference ts < last closed alt ts) → that alt is not evaluated/stamped this cycle (a fillna(0) at the newest bar would silently drop a signal), retried next cycle;`
  : ''
const SIGNALS_SPEC = REFERENCE_FEED
  ? `REF_SYMBOL / REF_TIMEFRAME (exchange form of the frozen load_reference(<SYM>, <tf>) call, quoted in a comment); signals(df, ref_df) transcribed from ${SIGNAL_PY} with EXACTLY ONE change: the line that calls ld.load_reference(...) becomes an assignment from the ref_df parameter (same variable name; every other line verbatim — same K/THRESH/LAG constants with the same values, same intersection, same reindex/fillna/astype; no import of research.swarm.lib.load_data in the module); last_signal(df_closed, ref_closed) → int in {-1,0,1} at the last CLOSED alt bar, returning 0 (and never raising) when ref_closed is None/empty or its last closed ts is older than df_closed's last ts — the orchestration checks that lag BEFORE calling it so the bar is retried, but the function itself must be safe`
  : `signals(df) transcribed VERBATIM from ${SIGNAL_PY} (same body; keep its name so the parity test is a direct comparison); last_signal(df_closed) → int in {-1,0,1} at the last CLOSED bar`
const REF_ORCH = REFERENCE_FEED
  ? ` REFERENCE FETCH (owner-authorised, once per cycle): because paper_mode is a SLOT attribute, hoist that same guard to the top of _evaluate_${ID} — order is: slot is None → return; not slot.enabled → return; not slot.paper_mode → logger.error once per UTC day, return (BEFORE any exchange call); ref_df = self.exchange.get_ohlcv(REF_SYMBOL, REF_TIMEFRAME, limit=OHLCV_LIMIT); ref_closed = complete_bars(ref_df); if ref_df is None/empty or ref_closed is empty → logger.warning "[${ID.toUpperCase()}] reference <REF_SYMBOL> fetch empty — retrying next cycle" and return (nothing stamped); ONLY THEN the per-symbol loop, which keeps its own paper_mode guard as the first line (redundant by construction, kept so the block shape matches the recipe) and, after computing closed for the alt, skips (no stamp, debug log) any symbol whose last closed ts is newer than ref_closed's last closed ts — the reference is fetched exactly once per cycle and never inside the per-symbol loop.`
  : ''
const DOC_STEP = REFERENCE_FEED
  ? `6b. OWNER-DECISION RECORD (doc-only commit, BEFORE step 7): APPEND to the END of ${PREREG} — never edit, reorder or delete an existing line; "git diff -U0 -- ${PREREG}" must show only added lines at the end of the file — this section (fill the angle brackets from the frozen call you recorded in the guard step):
${OWNER_DECISION_HEADING}
Appended ${RESUME_NOW} UTC on ${RESUME ? `resume of run ${RUN_ID} (args.resume_after_prereg)` : `run ${RUN_ID}`}, args.reference_feed = "${REFERENCE_FEED}". The original IMPLEMENT seat stopped because the frozen signal loads its reference series through research.swarm.lib.load_data and the slot framework hands a slot only its own symbol's OHLCV. Owner decision, verbatim (args.owner_decision), copied character-for-character — the text between the fence lines, nothing added, nothing escaped:
\`\`\`text
${OWNER_DECISION}
\`\`\`
Transcription: the frozen signal's \`ld.load_reference(<SYM>, <tf>, dataset=<dataset>)\` is transcribed as a live reference fetch — \`self.exchange.get_ohlcv(<SYM in exchange form>, <tf>, limit=OHLCV_LIMIT)\` → \`complete_bars(...)\` (closed bars only) → intersected on the alt's closed-bar index exactly as the frozen file does. The pure module exposes \`signals(df, ref_df)\` (reference frame as an explicit second argument; parity against the frozen file is tested on synthetic frames and on the research cache's train frames of ≥3 universe symbols). The bot fetches the reference ONCE per cycle, after the paper_mode guard, and passes the same closed frame to every symbol. Nothing above this section changes; the verdict line, anti-fishing clause and holdout record stand as committed.
   Then: git add ${PREREG} && git commit -m "${OWNER_DECISION_COMMIT_MSG}" -m "${TRAILER}" (this commit touches ONLY ${PREREG}). Record doc_commit_sha.
`
  : ''

const implementPrompt = `${RULES}
IMPLEMENT seat — TDD build of the ${ID} paper slot on branch ${BRANCH} (confirm with git rev-parse --abbrev-ref HEAD; if it is not ${BRANCH}, stop with ok=false). Read first, in this order: ${PREREG} (your spec — the verdict line there is binding), ${FROZEN}, ${SIGNAL_PY}, research/swarm/lib/screen.py (simulate: the exit rule you transcribe), donchian_slot.py, tests/test_donchian_slot.py, bot.py (grep for: "import donchian_slot"; the two DONCHIAN_ StrategySlot(...) entries in self.slots; "self._donchian_state = donchian_slot.load_state()"; def _evaluate_all_slots; def _donchian_slot; def _donchian_price; def _evaluate_donchian; def _donchian_daily_eval; def _donchian_adjust_position; def _donchian_open_paper; def _close_slot_position; def _slot_entries_blocked; the '.kill_*' sentinel loop 'for path in _glob.glob(".kill_*")'; _fresh_paper_entry_price), strategy_slot.py (StrategySlot fields; how the trading_state_<slot_id>.json path is derived; set_killed / is_active / enabled), scripts/lab_adjudicator/adjudicate.py (EXPERIMENTS; grade_sr_bounce_v2; _line_sr_bounce_v2; build_digest; _net; load_json), tests/test_lab_adjudicator.py, docs/2026-09-16-edge-swarm-v1/02_framework_audit.md §3.6.
${IMPL_GUARD} Do not touch any file outside this list: ${ALLOWED_FILES.join(', ')}${IMPL_DOC_FILES.length ? ` (plus the APPEND-ONLY owner-decision section of ${PREREG} in step 6b — its own commit, nothing else in that file changes)` : ''}. Never edit ${FROZEN} or ${SIGNAL_PY}.
1. TESTS FIRST — ${TEST}, mirroring tests/test_donchian_slot.py in structure (sandbox fixture, pure-module golden cases, AST wiring test, bare bot + FakeExchange). Cover:
${PARITY_TESTS}
   (b) forming-bar exclusion: complete_bars(df, now_utc) drops the last row when now_utc < that bar's close time and keeps it once the bar is closed;
   (c) exit rule golden cases identical to screen.simulate: SL and TP both touched on one bar → stop_loss (SL wins ties); TP-only → take_profit at the TP level; no touch through max_hold_bars → time_exit at the max_hold-th bar's close; both sides (long and short);
   (d) sidecar state save/load roundtrip (atomic tmp + os.replace) and missing/corrupt file → defaults; sidecar names not prefixed trading_state;
   (e) AST wiring (copy test_bot_slot_config_matches_rails_optout): exactly one StrategySlot(...) in bot.py with slot_id "${ID}", strategy_name "${ID}" (assert it is NOT in strategies.STRATEGIES — that absence is what keeps every scalper exit path away), timeframe = the frozen spec's timeframe, max_positions = len(universe), capital_pct 0.0, paper_mode True, trade_amount_usdt None, loss_cap_usdt -999.0, kelly_min_trades 10**9, durable_trail_enabled False; and "self._evaluate_${ID}(prices)" present in bot.py;
   (f) bare-bot orchestration (object.__new__(botmod.Phmex2Bot) + FakeExchange, no network): a closed-bar signal opens ONE paper position at the fresh price with notional = the module's NOTIONAL_USDT and margin == notional; the same closed bar is not evaluated twice (bar stamp); a later bar touching SL closes it with reason stop_loss at the SL level; slot.enabled False (killed) → no entry and the evaluator returns before fetching; _slot_entries_blocked() True → no NEW entry, exits still run; paper_mode False WITH an open paper position already in slot.risk.positions AND a bar that touches its SL → NO exchange call of any kind (FakeExchange.calls must stay empty — get_ohlcv included${REFERENCE_FEED ? ', the reference fetch included' : ''}), the position is untouched, no _close_slot_position, and one error log per UTC day (this is the test that proves the live guard sits BEFORE the exit path: _close_slot_position on a non-paper slot places a REAL market order);${REF_ORCH_TESTS}
   (g) adjudicator (in tests/test_lab_adjudicator.py, same style as the sr_bounce_v2 tests): grade_${ID} returns WATCH below n=${VERDICT_N}; KILL at n>=${VERDICT_N} with net<=0; KILL at net<=${KILL_NET_USD.toFixed(2)} with n<${VERDICT_N}; PASS at n>=${VERDICT_N} with a CI95 lower bound > 0 (use a clearly positive synthetic ledger); INCONCLUSIVE at n>=${VERDICT_N}, net>0, CI lower<=0 with n<${INCONCLUSIVE_HARD_N}; KILL at the hard stop n>=${INCONCLUSIVE_HARD_N} with CI lower<=0; rows with closed_at < registered_ts are ignored; on every KILL the grader touches <bot_dir>/${KILL_FILE} (pass bot_dir=tmp_path like grade_side_line's tests) and on WATCH / PASS / INCONCLUSIVE it writes NO file (assert tmp_path is empty).
   Run python3 -m pytest ${TEST} tests/test_lab_adjudicator.py -q and CONFIRM they fail (ImportError / AttributeError count) before step 2. Record that tail.
2. ${MODULE} — pure module: no bot imports, no network, imports limited to stdlib + pandas/numpy (+ research.swarm.lib.fee_math only for the derivation comment; write NOTIONAL_USDT as a literal equal to the printed fee_math.position_notional() with the derivation in a comment). Frozen constants copied from ${FROZEN} with the sha in a comment: SLOT_ID = "${ID}", SYMBOLS = spec.universe (list), TIMEFRAME, TP_BPS, SL_BPS, MAX_HOLD_BARS, OHLCV_LIMIT chosen from the Phemex whitelist {5,10,50,100,500,1000} so the signal's longest lookback is covered. STATE_FILE = <dir>/${ID}_slot_state.json, SIGNAL_FILES = {sym: <dir>/${ID}_signal_<BASE>.json} (never prefixed trading_state_). Functions: complete_bars(df, now_utc=None) → df without the forming bar (bar is closed when its open time + bar size <= now); ${SIGNALS_SPEC}; exit_check(side, entry, bar_high, bar_low, bar_close, bars_held) → (reason, price) or None, transcribed from screen.simulate (SL then TP on the same bar, SL wins ties, time_exit at bars_held >= MAX_HOLD_BARS at bar_close); default_symbol_state() ({"last_bar_ts": None, "bars_held": 0, ...}); load_state/save_state atomic and never raising; append_signal_bars(symbol, records) replica writer (bounded, idempotent per bar ts) for fidelity grading.
3. bot.py — orchestration only, modeled line-for-line on the Donchian methods: import next to "import donchian_slot" with the same comment style; ONE StrategySlot(...) in self.slots right after the DONCHIAN_ETH entry, keyword values exactly as the AST test in (e) asserts, with the same explanatory comment block (strategy_name deliberately NOT a STRATEGIES key so _evaluate_slots skips the slot entirely — no scalper exit can touch it); runtime state init right after "self._donchian_live_warned = {}": self._${ID}_state = ${ID}_slot.load_state() and self._${ID}_live_warned = {}; in _evaluate_all_slots add, after the Donchian block, in its own try/except with logger.error(..., exc_info=True): self._evaluate_${ID}(prices). Methods: _evaluate_${ID}(prices) — find the slot by id (reuse _donchian_slot(slot_id): it is generic); return immediately if slot is None or not slot.enabled (kill honoured EVERY cycle; ${KILL_FILE} is also processed by the generic .kill_* sentinel loop which closes paper positions and calls set_killed — do not duplicate that); per symbol, the block BEGINS with the live guard, BEFORE any data fetch, exit check or book write — exactly the recipe outline (02_framework_audit.md §3.6: 'if not slot.paper_mode: log "LIVE not implemented" once/day; return'): if not slot.paper_mode → logger.error once per UTC day via self._${ID}_live_warned and return without touching the exchange or the book (this matters: _close_slot_position on a non-paper slot places a REAL market order — the guard must sit above it, never below).${REF_ORCH} Then: df = self.exchange.get_ohlcv(symbol, TIMEFRAME, limit=OHLCV_LIMIT); closed = complete_bars(df); if the last closed bar ts equals st["last_bar_ts"] → continue; run exit_check on the open position (if any) against that bar's high/low/close and close via self._close_slot_position(slot, symbol, pos, level_price, reason); THEN, if no position, ${REFERENCE_FEED ? 'last_signal(closed, ref_closed)' : 'last_signal'} != 0, slot.is_active and not self._slot_entries_blocked(): open paper via _${ID}_open_paper (side long for +1, short for −1); stamp st["last_bar_ts"] only when the book matches the bar (a failed close/open retries next cycle, exactly the Donchian retry shape); save_state; append_signal_bars. _${ID}_open_paper(slot, symbol, price, side) — _fresh_paper_entry_price(...) as _donchian_open_paper does; slot.risk.open_position(symbol, price, NOTIONAL_USDT, side=side, atr=0.0, regime="medium", cycle=self.cycle_count, strategy="${ID}"); pos.amount = notional/price; pos.margin = notional (1x paper convention); pos.stop_loss / pos.take_profit set to the SL/TP price levels for display only (exits are evaluated by exit_check on closed bars); slot.risk._save_state(); slot.total_entries += 1; notifier.notify_paper_entry(..., slot=slot.slot_id); logger.info in the [PAPER] format. Nothing in this file may call any exchange method other than get_ohlcv / get_ticker for this slot, and only after the paper_mode guard.
4. scripts/lab_adjudicator/adjudicate.py — a state-file constant ${ID.toUpperCase()}_STATE_FILE = BOT_DIR / "${STATE_FILE}" next to SR_BOUNCE_STATE_FILE; EXPERIMENTS["${ID}"] = {"registered_ts": <epoch int of ${NOW}, computed with python3 -c "from datetime import datetime; print(int(datetime.fromisoformat('${NOW.replace('Z', '+00:00')}').timestamp()))" and written as the literal with a comment giving the ISO and PT time>, "verdict_n": ${VERDICT_N}, "kill_net_usd": ${KILL_NET_USD.toFixed(1)}, "inconclusive_hard_n": ${INCONCLUSIVE_HARD_N}, "prereg": "${PREREG}"} with a comment block quoting the prereg verdict line; grade_${ID}(slot_state, cfg, bot_dir=None) modeled on grade_sr_bounce_v2 for the ledger math and on grade_side_line for the sentinel write — trades = closed_trades with closed_at >= registered_ts; nets via _net; statuses exactly per the verdict line (KILL / PASS / INCONCLUSIVE / WATCH, note text naming the clause); the CI95 from research.swarm.lib.bootstrap_ci.mean_ci on the per-trade net USD list, imported lazily INSIDE the function after guarding sys.path with str(BOT_DIR) (ci = None when n < 2; never a hand-written resampler). AUTOMATIC KILL (spec §7, prereg verdict line): on ANY KILL clause — n>=verdict_n & net<=0, net<=kill_net_usd at any n, or the INCONCLUSIVE hard stop n>=inconclusive_hard_n with CI lower<=0 — touch os.path.join(str(bot_dir or BOT_DIR), "${KILL_FILE}") exactly as grade_side_line touches its sentinel (open(...,"w"), never overwrite an existing file, log a warning on OSError, say "touched ${KILL_FILE}" in the note); the bot's generic .kill_* loop then closes the paper book and persists the kill. On WATCH / PASS / INCONCLUSIVE the grader writes NOTHING and never writes .promote_*. Returns {"experiment": "${ID}", "status", "note", "n_trades", "wins", "wr", "net_usd", "ci95_lower", "verdict_n", "kill_touched"}. In build_digest append grade_${ID}(load_json(${ID.toUpperCase()}_STATE_FILE, {}), EXPERIMENTS["${ID}"]) at the END of the results list and a _line_${ID}(results[<last index>]) at the END of the lines — do not renumber the existing positional indexes.
5. Reporting propagation (CLAUDE.md rule): the dashboard auto-discovers ${STATE_FILE} (web_dashboard.read_all_slot_states) — confirm by reading how strategy_slot.py derives the state path and assert the derived filename in a test; Telegram paper entry/exit notifications go through notifier.notify_paper_entry (your open path) and _close_slot_position → notifier.notify_paper_exit; the adjudicator digest line from step 4 is the paper-verdict surface; scripts/daily_report.py covers slots only once promoted (live_slot_summaries) — state that in notes, do not edit it. Do NOT edit web_dashboard.py, notifier.py or daily_report.py; if you believe one needs a change, say so in notes and leave it.
6. Run python3 -m pytest -q (full suite). Acceptable: baseline "${SUITE_BASELINE}" plus your new tests passing; ANY other failure blocks — fix your code, never someone else's test. Paste the last 15 lines verbatim into pytest_tail.
${DOC_STEP}7. Commit on ${BRANCH} with explicit paths only: git add ${ALLOWED_FILES.join(' ')} (only those you changed) && git commit -m "feat(${ID}): pre-registered paper slot — closed-bar signal from the frozen spec${REFERENCE_FEED ? ', reference series via exchange OHLCV (owner-authorised)' : ''}, exits per screen.simulate, adjudicator line" -m "${TRAILER}". git status --short must show none of your files unstaged afterwards.${REFERENCE_FEED ? ` This commit must NOT include ${PREREG} (that is the step-6b commit).` : ''}
Return {ok, files_changed (paths), commit_sha, ${REFERENCE_FEED ? 'doc_commit_sha (step 6b), ' : ''}pytest_tail, failing_first_tail (the step-1 red run), notes, error}.`

const reviewModeNote = (baseSha) => `${RESUME ? `RESUME MODE: the Prereg phase did not run in this build — the branch, the prereg doc and the holdout artifacts pre-date base_sha (the branch tip at resume), so ${baseSha}..HEAD contains NO prereg commits; do not look for them there (verify instead that "git log --oneline ${BRANCH} -- ${PREREG} ${OUT_HOLDOUT}" shows the two original prereg commits BELOW base_sha). ` : ''}${REFERENCE_FEED ? `REFERENCE FEED MODE (owner-authorised, args.reference_feed = "${REFERENCE_FEED}"): the frozen signal's load_reference call is transcribed as a live exchange.get_ohlcv fetch of the reference symbol — that ONE difference from the frozen body is authorised; nothing else is. ` : ''}`
const reviewPrompt = (baseSha) => `${RULES}
INDEPENDENT REVIEWER of branch ${BRANCH} (single round: a BLOCK ends the build; nobody edits after you). You are read-only on code: you may run git, pytest and python one-liners, and you must not edit or commit anything. Diff = git diff ${baseSha}..HEAD (also --stat, and git log --format='%H %s' ${baseSha}..HEAD). ${reviewModeNote(baseSha)}Verify each item against the FILES, not the implementer's report; BLOCK on any failure and quote the file:line:
1. Forming-bar reads: any signal or exit evaluated on a bar that is not closed (df.iloc[-1] on a frame that still contains the forming bar, no complete_bars() before last_signal/exit_check${REFERENCE_FEED ? '; the reference frame handed to signals()/last_signal() not passed through complete_bars()' : ''}) → BLOCK.
2. Signal transcription: diff the body of signals() in ${MODULE} against ${SIGNAL_PY} — any semantic difference (renamed constants with different values, changed windows, added filters, changed sign convention) → BLOCK.${REFERENCE_FEED ? ` The ONLY permitted differences: the signature signals(df, ref_df) and the single line that called ld.load_reference(...) now assigning from ref_df (same variable name); every other line identical; ${MODULE} must not import research.swarm.lib.load_data; REF_SYMBOL / REF_TIMEFRAME must be the exchange-form / same-timeframe counterparts of the frozen call's arguments (e.g. "BTC" → "BTC/USDT:USDT", "1h" → "1h") — else BLOCK.` : ''} Confirm neither ${FROZEN} nor ${SIGNAL_PY} nor anything under research/swarm/lib/ appears in the diff, and python3 -c "from research.swarm.lib import registrar as r; print(r.verify('${FROZEN}'))" prints True — else BLOCK.
3. Exit rule vs research/swarm/lib/screen.py simulate(): SL checked before TP on the same bar (SL wins ties), levels at entry×(1 ± bps/1e4) with the correct sign per side, TIME exit at max_hold_bars at that bar's close — any divergence → BLOCK.
4. Live-order path: the per-symbol block in _evaluate_${ID} must BEGIN with the paper_mode guard (log once/day, return) BEFORE get_ohlcv, exit_check, _close_slot_position and the open path — _close_slot_position on a non-paper slot places a REAL market order (bot.py, the else-branch of _close_slot_position), so a guard placed after the exit check is a BLOCK; any code path for this slot that can call an exchange method other than get_ohlcv/get_ticker → BLOCK; the live-mode test must hold an open position and assert zero exchange calls${REFERENCE_FEED ? ' (the reference fetch included)' : ''} → else BLOCK. paper_mode=True, loss_cap_usdt=-999.0, kelly_min_trades=10**9, durable_trail_enabled=False in the StrategySlot call; strategy_name not in strategies.STRATEGIES.${REFERENCE_FEED ? `
4b. Reference fetch (owner-authorised): in _evaluate_${ID} the order must be slot None → enabled → paper_mode guard (once/day error, return) → ONE self.exchange.get_ohlcv(REF_SYMBOL, REF_TIMEFRAME, limit=OHLCV_LIMIT) → complete_bars → per-symbol loop; a reference fetch placed before the paper_mode guard, inside the per-symbol loop, or made more than once per cycle → BLOCK; an empty/None reference must return before any alt is evaluated or stamped → else BLOCK; an alt whose last closed ts is newer than the reference's last closed ts must be skipped without a bar stamp (else a signal at the newest bar is silently lost to fillna(0)) → else BLOCK; the tests must cover once-per-cycle (call count by symbol with ≥2 alts), forming-bar exclusion on the reference, empty reference, and the lag skip → else BLOCK.
4c. Owner-decision record: ${PREREG} must end with a section headed exactly "${OWNER_DECISION_HEADING}" that quotes args.owner_decision VERBATIM inside a \`\`\`text fence — compare character-for-character against the text between these markers (the markers are not part of it):
<<<OWNER_DECISION
${OWNER_DECISION}
OWNER_DECISION>>>
— and states the transcription (load_reference → exchange.get_ohlcv of the reference symbol, closed bars, intersected on the alt index, signals(df, ref_df), once per cycle after the paper_mode guard); "git diff -U0 ${baseSha}..HEAD -- ${PREREG}" must show ONLY added lines at the end of the file (no existing line of the verdict line, economics, prior or holdout record changed) → else BLOCK. That append must be its own commit touching only ${PREREG}, and it must precede the implement commit in git log → else BLOCK.` : ''}
5. Kill honoured every cycle: the evaluator checks slot.enabled before fetching data; killed/disabled → no entry; the bot side needs no code beyond that (the generic .kill_* loop already exists) → else BLOCK.
6. Adjudicator vs prereg: EXPERIMENTS["${ID}"] verdict_n == ${VERDICT_N}, kill_net_usd == ${KILL_NET_USD.toFixed(1)}, inconclusive_hard_n == ${INCONCLUSIVE_HARD_N}, registered_ts == the epoch of ${NOW}; grade_${ID} implements KILL / PASS / INCONCLUSIVE / WATCH exactly as the "## Verdict line (frozen)" section of ${PREREG} states, sums net_pnl as-is, uses bootstrap_ci.mean_ci (no hand-rolled resampler); AUTOMATIC KILL: on every KILL clause (including the INCONCLUSIVE hard stop at n = ${INCONCLUSIVE_HARD_N}) it touches ${KILL_FILE} in bot_dir (never overwriting an existing file), and on WATCH / PASS / INCONCLUSIVE it writes nothing and never writes .promote_*; the tests cover the touch and the no-write cases; the digest line is appended without renumbering existing results — else BLOCK.
7. Tests exercise the signal on data (parity against ${SIGNAL_PY} on synthetic AND train data, not just construction${REFERENCE_FEED ? ` — with the reference feed: the synthetic case monkeypatches the frozen module's ld.load_reference to return the same ref_df the module receives, and the real-data case (skipif the cache is absent) feeds the cache's reference train frame + the alt train frames of AT LEAST 3 universe symbols and requires exact series equality, with at least one non-zero signal somewhere` : ''}), the exit golden cases, the bare-bot orchestration including the no-orders-when-live case, and the adjudicator statuses — else BLOCK.
8. Scope: classify every commit in ${baseSha}..HEAD by the files it touches (git show --stat --format=%H <sha>): a PREREG commit touches only a subset of {${PREREG}, ${OUT_HOLDOUT}, ${TRADES_HOLDOUT}} — there must be exactly ${PREREG_COMMITS_EXPECTED + DOC_COMMITS_EXPECTED} such commit(s) in ${baseSha}..HEAD (${PREREG_COMMITS_EXPECTED} prereg${RESUME ? ' — none, this is a resume and the originals sit below base_sha' : ''}${DOC_COMMITS_EXPECTED ? ` + ${DOC_COMMITS_EXPECTED} owner-decision doc commit "${OWNER_DECISION_COMMIT_MSG}" touching ONLY ${PREREG}` : ''}); every other commit must touch only files in {${ALLOWED_FILES.join(', ')}} — a commit that mixes the two sets, or touches anything else, is a BLOCK; nothing under research/swarm/runs/ (beyond the two holdout artifacts), research/swarm/kb/, research/swarm/lib/ or docs/ (beyond ${PREREG}) is modified anywhere in ${baseSha}..HEAD; no .env, trading_state*.json, sentinel, launchd, logs/ or data files anywhere in ${baseSha}..HEAD; no launchctl/kill/pkill/main.py invocation anywhere in the diff → else BLOCK.
9. Run python3 -m pytest -q; compare with the baseline "${SUITE_BASELINE}" plus the new tests; any other failure → BLOCK. Paste the last 15 lines.
Return {verdict: "APPROVE" | "BLOCK", reasons: [one line each, file:line where applicable], pytest_tail}.`

// ---------------------------------------------------------------------------
// Schemas — object root, required ⊆ properties.
// ---------------------------------------------------------------------------
const PREREG_SCHEMA = { type: 'object', properties: {
  ok: { type: 'boolean' }, status: { type: 'string' }, base_branch: { type: 'string' }, base_sha: { type: 'string' },
  prereg_path: { type: 'string' }, commit_sha: { type: 'string' }, error: { type: 'string' } },
  required: ['ok', 'status'] }
const HOLDOUT_SCHEMA = { type: 'object', properties: { ok: { type: 'boolean' }, out_path: { type: 'string' }, n: { type: 'integer' }, net_bps_mean: { type: 'number' }, ci95: { type: 'array', items: { type: 'number' } }, wr: { type: 'number' }, p_star: { type: 'number' }, error: { type: 'string' } }, required: ['ok'] }
const RESUME_SCHEMA = { type: 'object', properties: {
  ok: { type: 'boolean' }, status: { type: 'string' }, base_sha: { type: 'string' }, head_subject: { type: 'string' },
  prereg_status: { type: 'string' }, n: { type: 'integer' }, net_bps_mean: { type: 'number' },
  ci95: { type: 'array', items: { type: 'number' } }, wr: { type: 'number' }, p_star: { type: 'number' }, error: { type: 'string' } },
  required: ['ok', 'status'] }
const IMPL_SCHEMA = { type: 'object', properties: {
  ok: { type: 'boolean' }, files_changed: { type: 'array', items: { type: 'string' } }, commit_sha: { type: 'string' },
  doc_commit_sha: { type: 'string' },
  pytest_tail: { type: 'string' }, failing_first_tail: { type: 'string' }, notes: { type: 'string' }, error: { type: 'string' } },
  required: ['ok'] }
const REVIEW_SCHEMA = { type: 'object', properties: {
  verdict: { type: 'string', enum: ['APPROVE', 'BLOCK'] }, reasons: { type: 'array', items: { type: 'string' } }, pytest_tail: { type: 'string' } },
  required: ['verdict', 'reasons'] }

// Decision rule for the holdout read — fixed here AND written into the prereg doc
// before the read; the recorder only transcribes it.
function holdoutDecision(h) {
  if (!h || !h.ok) return 'HOLDOUT_ERROR'
  if (!Array.isArray(h.ci95) || h.ci95.length !== 2) return 'HOLDOUT_INSUFFICIENT'   // ci95 is null when n < 2
  if (h.ci95[1] < 0) return 'DEAD_AT_HOLDOUT'
  return 'BUILD'
}

// `branch` is reported only once the prereg seat actually created it (a precondition
// failure stops before any checkout, so there is no branch to point the owner at). On a
// resume the branch pre-exists, so every stop names it and carries `resumed: true` plus
// the recorded holdout summary (from the committed artifact, never a re-read).
const holdoutSummary = (h) => (h ? { out_path: OUT_HOLDOUT, n: h.n, net_bps_mean: h.net_bps_mean, ci95: h.ci95, wr: h.wr } : null)
const modeFields = (h) => ({ ...(RESUME ? { resumed: true, holdout: holdoutSummary(h) } : {}), ...(REFERENCE_FEED ? { reference_feed: REFERENCE_FEED, owner_decision: OWNER_DECISION } : {}) })
const stop = (result, extra, branchCreated, h) => ({ run_id: RUN_ID, thesis_id: ID, result, ...(branchCreated ? { branch: BRANCH, prereg_doc: PREREG } : {}), ...modeFields(h), ...extra,
  next: `Stopped at ${result}. Nothing restarted, no launchd job touched, no order placed, nothing merged, nothing written under ${KB}/.${branchCreated ? ` Branch ${BRANCH} holds the prereg record — owner decides what happens to it.` : ''}` })

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
log('run alone — controller confirmed no other Workflow live; Gate A (owner "go" after the committee PASS) confirmed by the controller before launch')
log(`build ${ID} from run ${RUN_ID}: now=${NOW} branch=${BRANCH} verdict_n=${VERDICT_N} kill=${KILL_NET_USD} USD judge_model=${JUDGE_MODEL ?? 'inherit'} resume=${RESUME} reference_feed=${REFERENCE_FEED ?? 'none'}; this script never restarts the bot`)

// ---------- Phase 1: Prereg (write → commit → the ONE holdout read → record) ----------
// On a resume the phase is a deterministic precondition check on the existing branch;
// nothing is written and the spent holdout read is never repeated.
phase('Prereg')
let BASE_SHA
let holdout
let prereg = null
if (RESUME) {
  log(`resume: Prereg skipped — checking preconditions on the existing ${BRANCH} (branch, prereg doc with a BUILD decision, committed out.holdout.json, frozen sha); nothing is re-read`)
  const check = await agent(resumeCheckPrompt, { label: 'resume-check', phase: 'Prereg', schema: RESUME_SCHEMA, effort: 'low' })
  const recomputed = check?.ok ? holdoutDecision({ ok: true, ci95: check.ci95 }) : 'HOLDOUT_ERROR'   // script-side re-application of the fixed rule
  if (!check?.ok || !check.base_sha || recomputed !== 'BUILD' || (check.prereg_status && check.prereg_status !== 'BUILD')) {
    const reason = check?.error ?? (!check ? 'seat returned null' : !check.base_sha ? 'no base_sha returned' : `recorded holdout does not satisfy the fixed BUILD rule (${recomputed}; prereg_status=${check.prereg_status ?? '?'})`)
    log(`resume stopped: RESUME_PRECONDITION_FAILED — ${reason}`)
    return stop('RESUME_PRECONDITION_FAILED', { check, reason }, true, check?.ok ? check : null)   // the branch is the resume target (pre-existing), so it is named
  }
  BASE_SHA = check.base_sha
  holdout = { ok: true, out_path: OUT_HOLDOUT, n: check.n, net_bps_mean: check.net_bps_mean, ci95: check.ci95, wr: check.wr, p_star: check.p_star }
  log(`resume preconditions OK: ${BRANCH}@${BASE_SHA} ("${check.head_subject ?? '?'}"); recorded holdout n=${holdout.n} net_bps=${holdout.net_bps_mean} ci95=${JSON.stringify(holdout.ci95 ?? null)} (from ${OUT_HOLDOUT}, not re-read) → BUILD stands`)
} else {
  prereg = await agent(preregPrompt, { label: 'prereg-write', phase: 'Prereg', schema: PREREG_SCHEMA, effort: 'high' })
  if (!prereg?.ok) {
    const status = prereg?.status ?? 'NULL'
    const result = status.startsWith('PREREG_') ? status : `PREREG_${status}`
    log(`prereg stopped: ${result} — ${prereg?.error ?? 'seat returned null'}`)
    return stop(result, { prereg }, false)
  }
  BASE_SHA = prereg.base_sha
  log(`prereg committed ${prereg.commit_sha ?? '?'} on ${BRANCH} (base ${prereg.base_branch ?? '?'}@${BASE_SHA ?? '?'}); holdout read follows — the decision rule is already in the doc`)

  holdout = await agent(holdoutReadPrompt, { label: 'holdout-read', phase: 'Prereg', schema: HOLDOUT_SCHEMA, effort: 'low' })
  const decision = holdoutDecision(holdout)
  log(`holdout (read once): ${holdout?.ok ? `n=${holdout.n} net_bps=${holdout.net_bps_mean} ci95=${JSON.stringify(holdout.ci95 ?? null)}` : `error — ${holdout?.error ?? 'seat returned null'}`} → ${decision}`)
  const preregDoc = await agent(holdoutRecordPrompt(holdout, decision), { label: 'holdout-record', phase: 'Prereg', effort: 'medium' })
  if (!preregDoc) log('holdout-record returned null — check the prereg doc and the second prereg commit by hand before anything else')
  if (decision !== 'BUILD') return stop(decision, { base_sha: BASE_SHA, holdout, prereg_doc_text: preregDoc }, true)
}

// ---------- Phase 2: Implement (TDD, one commit on the branch) ----------
phase('Implement')
const impl = await agent(implementPrompt, { label: 'implement', phase: 'Implement', schema: IMPL_SCHEMA, effort: 'high' })
if (!impl?.ok) {
  log(`implement failed: ${impl?.error ?? 'seat returned null'}`)
  return stop('IMPLEMENT_FAILED', { base_sha: BASE_SHA, holdout, impl }, true, holdout)
}
log(`implemented ${impl.commit_sha ?? '?'}${impl.doc_commit_sha ? ` (owner-decision doc commit ${impl.doc_commit_sha})` : ''}: ${(impl.files_changed ?? []).join(', ') || 'files not reported'}`)

// ---------- Phase 3: Review (judge model; single round — BLOCK ends the build) and STOP before Gate B ----------
// The reviewer runs as the default workflow subagent (not agentType 'feature-dev:code-reviewer'):
// that agent type has no Bash tool, so it could not run pytest, git diff, or registrar.verify.
// Independence comes from the prompt (verify against files, not the implementer's report) and
// from JUDGE_MODEL, which applies to this seat only.
phase('Review')
let review = await agent(reviewPrompt(BASE_SHA), judge({ label: 'review', phase: 'Review', schema: REVIEW_SCHEMA, effort: 'high' }))
if (!review) review = { verdict: 'BLOCK', reasons: ['reviewer returned null — no approval exists'], pytest_tail: '' }
const result = review.verdict === 'APPROVE' ? 'BUILT' : 'REVIEW_BLOCKED'
log(`review: ${review.verdict}${review.verdict === 'BLOCK' ? ` — ${review.reasons.slice(0, 3).join(' | ')}` : ''}; stopping before Gate B`)
return {
  run_id: RUN_ID, thesis_id: ID, result, branch: BRANCH, base_sha: BASE_SHA, prereg_doc: PREREG,
  ...modeFields(holdout),
  holdout: holdoutSummary(holdout),
  files_changed: impl.files_changed ?? [], commits: [prereg?.commit_sha, impl.doc_commit_sha, impl.commit_sha].filter(Boolean),
  review,
  next: result === 'BUILT'
    ? `Gate B (human): owner reviews branch ${BRANCH} (git log ${BASE_SHA}..${BRANCH}), runs /pre-restart-audit, and says "go" before any restart. build.js restarted nothing, touched no launchd job, placed no order, merged nothing, wrote nothing under ${KB}/; the working tree is checked out on ${BRANCH}.`
    : `Reviewer BLOCKED — findings in review.reasons; branch ${BRANCH} stays unmerged for the owner to inspect; no fix seat ran; nothing restarted, nothing merged.`,
}
