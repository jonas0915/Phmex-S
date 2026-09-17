export const meta = {
  name: 'edge-desk-v2',
  description: 'Mechanism-first edge research desk: brief → analysts → gatekeeper → registrar → screen → audit → committee → report',
  whenToUse: 'Run alone from the Phmex-S repo root with args {run_id, now, constraints_md, standards_md, ...}; see research/swarm/README.md',
  phases: [
    { title: 'Brief', detail: 'read kb, write mandate' },
    { title: 'Analysts', detail: 'one market-participant lens each, internet-first, ≤2 theses' },
    { title: 'Gate', detail: 'dedup + relabel check + source verification, row-cited' },
    { title: 'Register', detail: 'freeze spec+signal sha before data' },
    { title: 'Screen', detail: 'pre-registered train-era screen → out.json' },
    { title: 'Audit', detail: 're-run, lookahead/fee/era checks, per-screen p_boot' },
    { title: 'Committee', detail: 'economics + statistics (BH + tp±20% read), both must pass' },
    { title: 'Close', detail: 'synthesis report, critic, reconcile kb' },
  ],
}

// ---------------------------------------------------------------------------
// Args (the script has no clock and no filesystem: everything time- or file-shaped
// comes in through `args`). See research/swarm/README.md for the launch invocation.
// ---------------------------------------------------------------------------
const A = args || {}
const RUN_ID = A.run_id
const NOW = A.now || (A.today ? `${A.today}T00:00:00Z` : null)          // ISO UTC; registrar frozen_at
const TODAY = A.today || (NOW ? NOW.slice(0, 10) : null)                 // YYYY-MM-DD; DEAD_LIST/LESSONS date stamp
const MAX_ANALYSTS = A.max_analysts ?? 8
const MAX_SCREENS = Math.min(A.max_screens ?? 5, 5)                      // hard cap 5 (addendum D)
const DRY = !!A.dry_run
const JUDGE_MODEL = A.judge_model || null                                // addendum C8
const CONSTRAINTS_MD = A.constraints_md
const STANDARDS_MD = A.standards_md
if (!RUN_ID || !NOW || !TODAY) throw new Error('desk.js: args.run_id and args.now (ISO UTC) are required — the script has no clock')
if (!CONSTRAINTS_MD || !STANDARDS_MD) throw new Error('desk.js: args.constraints_md and args.standards_md (file CONTENTS of kb/CONSTRAINTS.md and kb/STANDARDS.md) are required — every prompt embeds them')

const REPO = '/Users/jonaspenaso/Desktop/Phmex-S'
const RUN_DIR = `research/swarm/runs/${RUN_ID}`
const KB = 'research/swarm/kb'
const SWEEP = 'docs/2026-09-16-edge-swarm-v1/sweep'

// JUDGE_MODEL is applied to exactly five seats: gatekeeper, committee:economics,
// committee:statistics, synthesis, critic. Never analysts, screens, audits, registrar, reconciler.
const judge = (opts) => (JUDGE_MODEL ? { ...opts, model: JUDGE_MODEL } : opts)

// ---------------------------------------------------------------------------
// Prompts — one constant per role. RULES is prepended to EVERY agent prompt and
// carries the full text of kb/CONSTRAINTS.md and kb/STANDARDS.md.
// ---------------------------------------------------------------------------
const RULES = `You are one seat on a quant research desk for the Phmex-S bot (repo ${REPO}). Work from the repo root. Run id: ${RUN_ID}. Clock: now = ${NOW} (UTC), today = ${TODAY}${DRY ? ' — THIS IS A DRY RUN (plumbing test)' : ''}.
Run dir for all outputs: ${RUN_DIR} (create sub-dirs as needed). Knowledge base: ${KB}/.
MANDATORY before anything: read ${KB}/DATA.md and ${RUN_DIR}/mandate.md in full (the mandate may not exist yet if you are writing it); grep ${KB}/DEAD_LIST.md for anything you touch. The two governing documents are embedded below verbatim — obey them; the files in ${KB}/ are canonical if they ever differ.
HARD RULES: never modify bot trading code (bot.py, strategies.py, risk_manager.py, exchange.py, config.py, .env, any slot file). Never read holdout data (era="holdout"/"all", the committee token, or the cache files directly). A frozen spec (${RUN_DIR}/specs/*.frozen.json) and its screens/<id>/signal.py are NEVER edited by anyone — a new idea is a new thesis. Never hand-roll statistics: every win-rate, break-even, p*, time-to-verdict, CI or bootstrap number comes from research.swarm.lib (fee_math.p_star / net_bps / time_to_verdict_weeks / lot_check / position_notional, bootstrap_ci.mean_ci / diff_ci) — hand arithmetic in prose is a defect. Cite the file path for every number you report. "Not run" is a valid answer; a made-up number is not. Do not write any daily-ROI target anywhere.
Your final message is a return value read by a script, not prose for a human — return exactly what the task asks for.

=== ${KB}/CONSTRAINTS.md (embedded verbatim) ===
${CONSTRAINTS_MD}
=== ${KB}/STANDARDS.md (embedded verbatim) ===
${STANDARDS_MD}
=== end of embedded knowledge base ===
`

const BRIEF_PROMPT = `${RULES}
You are the DESK BRIEF seat. Write ${RUN_DIR}/mandate.md (create the directory). Contents, in this order:
1. Purpose: the owner's goal of growing a small account is the desk's PURPOSE and is stated as such — it is NOT a screening threshold. The pass bar is, and stays: per-trade net expectancy > 0 after c, with the 95% bootstrap CI excluding zero (CONSTRAINTS "viable" 1-5). No daily-ROI target anywhere in this run.
2. Capital $200 and sizing (fee_math.position_notional; lot minimums via fee_math.lot_check).
3. Minimum net edge in bps after c = 11.5 bps, justified from the embedded CONSTRAINTS — compute p* for the target ladder with fee_math.p_star (python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})") and quote the output. Targets: 100-300 bps moves, where p* is roughly 52-56%.
4. Horizons in scope: intraday-to-multi-day, explicitly NOT scalping; event-driven explicitly IN scope; at least two analyst lenses must target holds > 8h (funding at every 8h settlement must be accounted for on such holds).
5. The bot's execution reality (5-min poller, maker entries ~27% fill, taker exits, Mac may sleep) — from CONSTRAINTS.
6. Datasets and their train/holdout boundaries, from ${KB}/DATA.md (paths, symbols, timeframes, train-end dates), and the rule that holdout is never read in this run.
7. The 15 DEAD_LIST rows most likely to be relabeled this run, by row number with a 5-word gist each (read ${KB}/DEAD_LIST.md; these are the gatekeeper's watch list, NOT ideas).
8. Then run exactly: python3 -m research.swarm.lib.kb_check — and paste its output verbatim under a "kb_check" heading. If it does not print KB OK, say so at the top of the mandate; do not fix the kb.
Return the full mandate text.`

const INTERNET_FIRST = `INTERNET-FIRST SOURCING (owner order 2026-09-16 9:22 PM PT): source mechanisms from OUTSIDE this account's record. Use WebSearch and WebFetch — aim for 8-12 searches and 5-8 fetched pages; stop early when the lens is dry. Look for papers dated 2024-2026, practitioner write-ups with live or paper records, exchange and on-chain data feeds. kb/DEAD_LIST.md is a FILTER for rejecting relabels, NEVER a source of ideas. Every thesis must carry source_urls (at least one URL you actually opened) and evidence (what the source reports — the actual number and the URL it came from). Never pair a real paper title with a statistic you did not read on the page; if you could not open a source, do not cite it.`

const THESIS_RULES = `Produce at most 2 theses. Each MUST: name the counterparty and why they are forced to pay; state a falsifiable prediction; list the nearest DEAD_LIST.md rows by number (nearest_dead_rows, never empty — read the file) and say precisely why the MECHANISM differs (not the parameters, not the indicator name); carry source_urls and evidence per the sourcing rule above; and give a full spec: dataset mr_edge or long_1h (only these two are screenable — long_1h for multi-day/event-driven), universe = symbols present in that dataset per ${KB}/DATA.md, timeframe 5m or 1h (must exist in the dataset), tp_bps and sl_bps (targets of 100-300 bps; scalping-size targets are fee-trapped), max_hold_bars (consistent with the horizon and the bar size), expected_trades_per_week, doa_line (the pre-registered kill condition in one sentence). id must match ^[a-z][a-z0-9_]{2,40}$ (snake_case, 3-41 chars, the registrar rejects anything else), unique across the desk — prefix it with your lens key with hyphens replaced by underscores (owner-record → owner_record).
signal_py: Python source defining signals(df) -> pd.Series indexed like df with values exactly in {-1, 0, 1}, computed on CLOSED bars only — no .shift(-k), no future index use, no iloc[-1] forming-bar tricks; the screen runs a whole-prefix causality check on every symbol and any lookahead kills the thesis; a signal that returns any other value (NaN is fine, it is filled to 0) also kills it. df has columns open/high/low/close/volume with a UTC DatetimeIndex. Funding is available via research.swarm.lib.load_data.load_funding(symbol) (train era only, rate rows {ts, rate}) if the signal needs it — merge_asof on ts and use only rates settled BEFORE the bar. Import only pandas/numpy and research.swarm.lib inside signal_py.
You MAY run exploratory probes on TRAIN data (load_data.load_ohlcv(sym, tf, era="train", dataset=...)) to shape the thesis; save probe scripts and outputs under ${RUN_DIR}/exploratory/<lens>/ and label them exploratory — they are NOT the screen and their numbers are not evidence. Do not touch holdout.
web_budget_exhausted: set it true if WebSearch refuses for budget/limit reasons before you completed your sourcing, and say so in exploratory_notes; do not fabricate sourcing and do not substitute the dead list for the web. Otherwise set it false.
Write each thesis as JSON (all schema fields, exactly the field names below) to ${RUN_DIR}/theses/<id>.json and return them in the schema with thesis_path set to that path. If your lens yields no thesis with a genuine counterparty and a real source, return an empty theses list and say why in exploratory_notes — that is a valid outcome.`

const DRY_RUN_ANALYST = `DRY RUN (plumbing test, owner-sanctioned): produce exactly ONE thesis and make it a DELIBERATE relabel of a DEAD_LIST.md row (same mechanism, renamed indicator) so the gatekeeper's row-cited rejection path is exercised end to end; set its id prefix to dryrun_, put "DRY RUN — deliberate relabel of row <n>" in evidence, and in nearest_dead_rows say honestly that the mechanism is NOT different. Keep web work to at most 2 searches and 1 fetched page (still cite one real URL you opened) — this overrides the 8-12 search target above. Skip exploratory probes.`

const ALL_LENSES = [
  { key: 'forced_flows', brief: 'Forced flows: liquidations, funding settlement at 00/08/16 UTC, listings/delistings, index or perp-basis rebalances. Who is FORCED to trade and when?' },
  { key: 'informed_flow', brief: 'Informed vs uninformed flow: cross-venue lead-lag (Binance/Bybit/Coinbase → Phemex), spot→perp, large-cap→alt propagation at hourly+ horizons. Who knows first, and how long until Phemex prices it?' },
  { key: 'dealer_inventory', brief: 'Dealer / market-maker inventory: end-of-session unwind, weekend inventory, post-spike mean reversion of the *basis* not price. Who must flatten, and when?' },
  { key: 'session_calendar', brief: 'Session and calendar structure at ≥ 8h horizons: Asia/EU/US opens, weekend→Monday, monthly/quarterly expiries, US macro release days. Multi-day holds only — intraday calendar effects are dead rows.' },
  { key: 'vol_structure', brief: 'Volatility structure: realized-vol regime shifts, vol-of-vol, compression→expansion at DAILY horizon, post-shock drift. Who is short gamma / forced to re-hedge?' },
  { key: 'cross_asset', brief: 'Cross-asset spillover: equities (SPX/NDX futures), DXY, rates moves → BTC/ETH at 1h–1d lags; ETH/BTC ratio regimes → alt beta. Who reprices late?' },
  { key: 'literature', brief: `Literature. In addition to the web work, open and disposition the five already-fetched papers under ${SWEEP}/: emoji_paper.txt, garcia_schweitzer.txt, hansen_periodicity.txt, petukhina_hft.txt, academic/ssrn_6932998.html (one line each: mechanism, counterparty or none, usable or not). If ${SWEEP}/leadlag/local_check.py exists, run it READ-ONLY (fix only import/path errors in a COPY under ${RUN_DIR}/exploratory/literature/, never edit the original) and record its output there. Only a mechanism with a stated counterparty becomes a thesis.` },
  { key: 'owner-record', brief: `OWNER'S RECORD — the owner's own 2022 trade history. Read ${KB}/owner_trades/SOURCES.md first, then ${KB}/owner_trades/api_closed_pnl.json: 819 closed positions on Phemex COIN-MARGINED inverse contracts, 2022-03-25 → 2023-02-15 PT, leverage up to 100x; fields include symbol, side, closedSize, cumEntryValueEv, closedPnlEv, exchangeFeeEv, fundingFeeEv, realizedPnlEv (÷1e4 = USD), openedTimeNs. Also, IF PRESENT (they are gitignored and may be absent), ${KB}/owner_trades/api_deposit_list_full.json and api_withdraw_list_full.json.
IF api_closed_pnl.json IS ABSENT: return an empty theses list with exploratory_notes = "owner-record: api_closed_pnl.json absent — lens skipped" and stop. Do not fail.
FIRST run an exploratory probe (a Python script under ${RUN_DIR}/exploratory/owner-record/, labeled exploratory) and write its results to ${RUN_DIR}/theses/owner_record_probe.json (this file is a PROBE, not a thesis): true equity path if deposit/withdrawal files exist, otherwise cumulative realized PnL; concentration = share of total positive PnL from the single largest trade and from the top-5 trades; win rate; payoff ratio; median hold; symbols; side split; time-of-day; behaviour after a loss (size/side/hold of the next trade). Every number with the field it came from.
THEN propose at most 2 theses on the MECHANISM behind the profitable subset (who was the counterparty in those trades and why they paid), same schema as every other lens. source_urls may cite the local files by path (e.g. ${KB}/owner_trades/api_closed_pnl.json) in addition to web sources for the mechanism. Prefer to express the spec on the USDT-perp equivalents present in the screenable datasets so it can be screened; if the mechanism is inherently an inverse-contract one, say so in spec.universe (e.g. "BTCUSD-inverse") and add the note "bot has no inverse path yet" to the prediction — the gate will record it as not screenable rather than dead.` },
]
const LENSES = ALL_LENSES.slice(0, MAX_ANALYSTS)

const analystPrompt = (lens, i) => `${RULES}
You are analyst #${i + 1} of ${LENSES.length}, lens key = ${lens.key}. ${lens.brief}
${INTERNET_FIRST}
${THESIS_RULES}
${DRY ? DRY_RUN_ANALYST : ''}`

const gatePrompt = (thesisPaths) => `${RULES}
You are the GATEKEEPER. Thesis files (JSON): ${thesisPaths.join(', ')}. (${RUN_DIR}/theses/owner_record_probe.json, if present, is an exploratory probe, not a thesis — ignore it.)
Step 1 — for each thesis: (a) dedup against the others (same mechanism = keep the better-specified one, reject the other with dead_row null and reason "duplicate of <id>"); (b) relabel check against ${KB}/DEAD_LIST.md — if the MECHANISM matches a dead row (ignore renamed indicators, changed parameters, changed universe, changed timeframe), reject and cite the row number in dead_row; also confirm the thesis's own nearest_dead_rows are real rows (reject a thesis whose nearest_dead_rows is empty or whose why_different is generic boilerplate — dead_row null, say so); (c) sanity: id matches ^[a-z][a-z0-9_]{2,40}$ (the registrar's _ID_RE — reject a bad id here with dead_row null and reason "invalid id: ...", not at the registrar); every universe symbol exists in the named dataset per ${KB}/DATA.md (python3 -c "from research.swarm.lib import load_data as l; print(l.list_symbols('<dataset>'))"), timeframe exists in that dataset, tp/sl/hold are consistent with the horizon and the bar size, signal_py defines signals(df) and imports nothing outside pandas/numpy/research.swarm.lib, source_urls non-empty. A thesis whose universe is not screenable (e.g. inverse contracts) is rejected with dead_row null and reason starting "not screenable: ". Owner directives in STANDARDS #14 apply (demoted books, BTC blacklist, gate loosening, funding/XS/OI hunt → reject, cite the row).
Step 2 — SOURCE VERIFICATION on every thesis that survived step 1: WebFetch EVERY entry in its source_urls (try https://web.archive.org/web/<url> on a 403 or timeout; local file paths are read with Read). Does the page actually contain the claim and the number in the thesis's evidence field? Grade: A = primary source(s) confirm the mechanism and the numbers; B = confirmed mechanism, numbers partially confirmed; C = only secondary/anecdotal support; F = key claims unsupported or fabricated (the known failure mode is a real paper title paired with a made-up statistic). Reject grade F with dead_row null and reason "source verification F: <which URL, which claim>". Kept theses carry evidence_grade A, B or C.
Step 3 — keep at most ${MAX_SCREENS}, ranked by novelty of mechanism then specificity; anything beyond the cap is rejected with dead_row null and reason "over cap: ranked <k>". Do NOT edit any thesis file.
Write ${RUN_DIR}/gate_rejections.json as a JSON list of every rejection {id, dead_row, reason} and ${RUN_DIR}/gate_kept.json as the kept list. Return kept (id, thesis_path, evidence_grade, reason = one line on why it passed) and rejected, and rejections_path.`

const registrarPrompt = (k) => `${RULES}
REGISTRAR (mechanical, low effort). Run exactly this one command and nothing else that writes:
python3 -m research.swarm.lib.registrar ${k.thesis_path} ${RUN_DIR} ${NOW}
Do NOT edit the thesis, do NOT retry with modifications, do NOT "fix" validation errors. If the command fails, return ok=false with the error text verbatim in error. If it succeeds it prints the frozen path: return ok=true, frozen_path = that printed path, and sha256 = the "sha256" field read from that frozen file (python3 -c "import json; print(json.load(open('<frozen_path>'))['sha256'])").`

const screenPrompt = (k, reg) => `${RULES}
SCREENER for thesis ${k.id}. Frozen spec: ${reg.frozen_path} (sha ${reg.sha256}). Run exactly:
python3 -m research.swarm.lib.screen ${reg.frozen_path} ${RUN_DIR} --era train
You may NOT edit the frozen spec, ${RUN_DIR}/screens/${k.id}/signal.py, or any file under research/swarm/lib/. Never pass --era holdout/all or any token. If the command errors (ImportError, KeyError, LookaheadError/causality failure, signal-value error, ValueError, data missing), return ok=false with the last 15 lines of the traceback in error — do not "fix" anything and do not re-run with changes. On success return ok=true, out_path = ${RUN_DIR}/screens/${k.id}/out.json, and n, net_bps_mean, ci95, wr, p_star exactly as read from that file (null fields stay absent).`

const auditPrompt = (k) => `${RULES}
AUDITOR for thesis ${k.id}. Inputs: ${RUN_DIR}/specs/${k.id}.frozen.json and ${RUN_DIR}/screens/${k.id}/{signal.py,out.json,trades.csv}. You may not edit any of them.
1. Verify the frozen sha: python3 -c "from research.swarm.lib import registrar as r; print(r.verify('${RUN_DIR}/specs/${k.id}.frozen.json'))" — must print True, else verdict RERUN_MISMATCH with finding "frozen spec tampered".
2. Re-run the screen into a scratch run dir: mkdir -p /tmp/audit_${RUN_ID}_${k.id}/screens/${k.id} && cp ${RUN_DIR}/screens/${k.id}/signal.py /tmp/audit_${RUN_ID}_${k.id}/screens/${k.id}/signal.py && python3 -m research.swarm.lib.screen ${RUN_DIR}/specs/${k.id}.frozen.json /tmp/audit_${RUN_ID}_${k.id} --era train. Diff n / net_bps_mean / ci95 / wr against the run's out.json — any difference = RERUN_MISMATCH.
3. Read signal.py: any .shift(-k) with k>0, negative-index or future-timestamp use, rolling with center=True, iloc[-1]-style forming-bar logic, or use of data outside df/load_funding = REFUTED (lookahead). Confirm out.json causality == "PASS".
4. Check trades.csv: entry price equals the next bar's open after the signal (spot-check ≥5 rows by recomputing signals(df) on train data via load_data.load_ohlcv and comparing df['open'] at the bar after each signal — trades.csv has no signal timestamp column); no exit_ts after train_span end from out.json; cost applied (net_bps = gross_bps − 11.5 on every row, check with fee_math.C_BPS).
5. Recompute p_star (fee_math.p_star(tp_bps)) and time_to_verdict_weeks (fee_math.time_to_verdict_weeks(trades_per_week)) and compare to out.json; any mismatch is a finding.
6. ci_excludes_zero = out.json ci95 has both bounds > 0 (n ≥ 2; false when ci95 is null). Per-screen bootstrap p-value (one-sided upper bound on P(mean ≤ 0), ladder resolution, lib only — do NOT write your own resampler): python3 -c "import pandas as pd; from research.swarm.lib import bootstrap_ci as bc; x=pd.read_csv('${RUN_DIR}/screens/${k.id}/trades.csv')['net_bps'].to_numpy(); L=[0.0005,0.001,0.002,0.005,0.01,0.02,0.05,0.1,0.2,0.3,0.5,0.8,1.0]; print(next((a/2 for a in L if len(x)>=2 and bc.mean_ci(x, alpha=a)[0] > 0), 1.0))". Record it as numbers.p_boot. Benjamini-Hochberg across the run is applied by the Statistics committee seat, not here — leave bh_significant out.
Verdict: CONFIRMED only if steps 1-5 all pass; REFUTED on lookahead/cost/era violations; RERUN_MISMATCH on step 1/2 failure. n == 0 is CONFIRMED-with-finding "zero trades" (ci_excludes_zero false).
Write ${RUN_DIR}/screens/${k.id}/audit.json as {verdict, ci_excludes_zero, findings[], numbers{n, net_bps_mean, ci95, wr, p_star, time_to_verdict_weeks, p_boot, rerun{n, net_bps_mean, ci95}}} and return verdict, audit_path, ci_excludes_zero, findings.`

const economicsPrompt = (ids, files) => `${RULES}
RISK COMMITTEE — ECONOMICS seat. Candidates: ${ids.join(', ')}. Files: ${files}. Judge ONLY from those files plus research.swarm.lib.fee_math (read the frozen spec ${RUN_DIR}/specs/<id>.frozen.json for tp/sl/hold/universe). For each candidate, all of: observed wr ≥ p_star (both from out.json); lot_check ok for every universe symbol at fee_math.position_notional() (out.json lot_check); feasible on a 5-min poller (signal timeframe ≥ 5m, closed bars, no sub-bar timing, no data the bot does not have); funding exposure at max_hold (bars × bar size > 8h ⇒ state the funding cost per CONSTRAINTS and whether the net edge survives it); time_to_verdict_weeks ≤ 26 (out.json). Pass only if all hold; each reason cites the file and the number. The owner's goal of growing the account is the desk's purpose, not a threshold — no ROI targets. Write ${RUN_DIR}/committee/economics.json as {votes:[{id, pass, reasons[]}]} and return votes with path.`

const statisticsPrompt = (ids, files, screenedIds) => `${RULES}
RISK COMMITTEE — STATISTICS seat. Candidates: ${ids.join(', ')}. Files: ${files}. All screens in this run that produced out.json (the multiplicity set for BH): ${screenedIds.join(', ')}. Judge ONLY from those files plus research.swarm.lib (bootstrap_ci, fee_math). Per candidate, all of:
(a) n ≥ 30 (out.json); (b) CI95 excludes 0 with both bounds > 0 (out.json ci95); (c) Benjamini-Hochberg at q = 0.10 across the m = ${screenedIds.length} screens above: p_i = numbers.p_boot from each ${RUN_DIR}/screens/<id>/audit.json (if missing for a screen, compute it with the auditor's exact ladder command over that screen's trades.csv — never a hand-written resampler); sort p ascending, k* = largest k with p_(k) ≤ (k/m)·0.10, significant ⇔ rank ≤ k*; write the full table (id, p, rank, threshold, significant) to ${RUN_DIR}/committee/bh.json; bh_significant must be true for the candidate; (d) trades spread across the train span: no single calendar month > 50% of trades (trades.csv entry_ts); (e) per_symbol (out.json) not dominated by one symbol > 60% unless the universe size is 1;
(f) the ONE registered robustness read (STANDARDS #9): parameter tp_bps only, ±20% of the registered value, two variants. The frozen spec is never edited — you work on a COPY. Recipe per candidate <id>:
  mkdir -p ${RUN_DIR}/screens/<id>/robust
  write ${RUN_DIR}/screens/<id>/robust/make_variants.py with exactly this content:
    import json, sys
    frozen, out_dir = sys.argv[1], sys.argv[2]
    t = json.load(open(frozen))["thesis"]
    base = t["spec"]["tp_bps"]
    for name, mult in (("plus", 1.2), ("minus", 0.8)):
        v = json.loads(json.dumps(t)); v["spec"]["tp_bps"] = round(base * mult, 6)
        with open(f"{out_dir}/thesis_{name}.json", "w") as fh: json.dump(v, fh)
  python3 ${RUN_DIR}/screens/<id>/robust/make_variants.py ${RUN_DIR}/specs/<id>.frozen.json ${RUN_DIR}/screens/<id>/robust
  then for each variant V in (plus, minus):
    python3 -m research.swarm.lib.registrar ${RUN_DIR}/screens/<id>/robust/thesis_V.json ${RUN_DIR}/screens/<id>/robust/V ${NOW}
    python3 -m research.swarm.lib.screen ${RUN_DIR}/screens/<id>/robust/V/specs/<id>.frozen.json ${RUN_DIR}/screens/<id>/robust/V --era train
    cp ${RUN_DIR}/screens/<id>/robust/V/screens/<id>/out.json ${RUN_DIR}/screens/<id>/out.robust_V.json   (→ out.robust_plus.json and out.robust_minus.json)
  Pass (f) only if net_bps_mean keeps the SAME SIGN as the registered ${RUN_DIR}/screens/<id>/out.json in BOTH variants; record both variant numbers (with paths) in the reasons. No other parameter, no further steps, no grid. If a variant screen errors, record the error and fail (f).
Pass only if (a)-(f) all hold; each reason cites the file and the number. Write ${RUN_DIR}/committee/statistics.json as {votes:[{id, pass, reasons[]}]} and return votes with path.`

const synthesisPrompt = (ctx) => `${RULES}
SYNTHESIS seat: write ${RUN_DIR}/REPORT.md. Run context (from the orchestrator): ${JSON.stringify(ctx)}.
Verdict first (one sentence: how many theses, how many screened, how many passed committee). Then one paragraph per thesis in this run — gate-rejected ones (from ${RUN_DIR}/gate_rejections.json) in one line each with the dead row (or "source verification F" / "not screenable" / "duplicate" / "over cap" as recorded); screened ones with n, net bps, CI95, WR vs p*, evidence grade, audit verdict, committee votes (economics, statistics, BH table, tp±20% read) — EVERY number followed by the file path it came from (out.json, audit.json, committee/*.json, out.robust_*.json). Then "What was not done": every analyst lens that returned no thesis (with its exploratory_notes), every lens whose web_budget_exhausted is true in the run context (its sourcing was cut short), every registrar/screen/audit that errored (with the error text), any source that could not be fetched. Then "Next run should": 3 bullets, process not strategy. Plain English, verdict first, no tables wider than 6 columns, no daily-ROI targets. Numbers only from files you read this turn; if a file is missing say "not run". Return the report text.`

const criticPrompt = `${RULES}
COMPLETENESS CRITIC. Read ${RUN_DIR}/REPORT.md, then list the run dir recursively (find ${RUN_DIR} -type f | sort). Find and list, each with the concrete file/line: (a) any screens/<id>/ or exploratory/ or committee/ artifact not cited in the report; (b) any number in the report without a file path next to it; (c) contradictions between gate_rejections.json, theses/*.json, out.json, audit.json, committee/*.json, out.robust_*.json and the report (re-open the files; do not trust the report); (d) any thesis whose nearest_dead_rows is empty or whose why_different is generic, or whose evidence field has no number; (e) holdout access — grep -rn "COMMITTEE-HOLDOUT-READ\\|era=\\"holdout\\"\\|era='holdout'\\|era=\\"all\\"\\|--era holdout\\|--era all" ${RUN_DIR} (any hit is a process failure); (f) any frozen spec or signal.py whose sha no longer verifies (python3 -c "from research.swarm.lib import registrar as r; import glob; print({p: r.verify(p) for p in glob.glob('${RUN_DIR}/specs/*.frozen.json')})"); (g) any daily-ROI target or hand-computed statistic in the report. Write ${RUN_DIR}/CRITIC.md (a numbered list under headings a-g, "none" where nothing was found) and return it.`

const reconcilePrompt = (screenedIds, passed) => `${RULES}
RECONCILER. Rows go to the knowledge base ONLY for SCREENED theses — those with ${RUN_DIR}/screens/<id>/out.json (STANDARDS #15, spec §5 step 8). Screened this run: ${screenedIds.length ? screenedIds.join(', ') : 'none'}. Gate-rejected theses and theses whose registrar/screen errored get NO row anywhere — they live in ${RUN_DIR}/REPORT.md and ${RUN_DIR}/gate_rejections.json only. ${RUN_DIR}/theses/owner_record_probe.json is an exploratory probe, never a thesis.
For each screened thesis:
- If it did NOT pass committee (audit REFUTED/RERUN_MISMATCH, CI including zero, or a failed committee vote): append ONE row to ${KB}/DEAD_LIST.md. The row format is EXACTLY, verbatim: | n | family | why | source | date | — five cells, one line, no pipe characters inside any cell, where n = (max existing n in the file) + 1 (compute it by reading the file: python3 -c "from research.swarm.lib import kb_check as k; from pathlib import Path; print(max(r[0] for r in k.dead_rows(Path('${KB}/DEAD_LIST.md'))))"), family = the thesis id, why = the decisive reason in one line citing the numbers with their paths (out.json n / net_bps_mean / ci95, audit.json verdict, committee/*.json vote), source = ${RUN_DIR}/REPORT.md, date = ${TODAY}.
- If it passed committee (${passed.length ? passed.join(', ') : 'none this run'}): append a row to ${KB}/SURVIVORS.md instead, in that file's existing column format (run, id, train n, net bps, CI95, WR, p*, prereg doc = the frozen spec path, status = "committee pass — awaiting owner go"), numbers from out.json.
Then append dated lines ("- ${TODAY} — <what failed>. Rule: <process rule>") to ${KB}/LESSONS.md for every PROCESS failure the critic found in ${RUN_DIR}/CRITIC.md (not strategy lessons — process; if the critic found nothing, append one line recording that this run's critic was clean).${DRY ? ' This is a DRY RUN: nothing was screened, so the LESSONS entry (what the plumbing test showed) is the ONLY kb write.' : ''}
Never edit or delete existing rows or lines in any kb file; append only. Never edit ${KB}/CONSTRAINTS.md, STANDARDS.md, DATA.md or anything under ${KB}/owner_trades/.
Finally run exactly: python3 -m research.swarm.lib.kb_check — if it does not print KB OK, fix ONLY the row(s) you just wrote (never other rows) and re-run until it prints KB OK. Return the kb_check output verbatim plus every row/line you added, each with its file path.`

const abortPrompt = `${RULES}
RECONCILER (aborted run). Every analyst reported that WebSearch refused for budget/limit reasons, so this run stops before the gate under the internet-first directive. Append exactly ONE line to ${KB}/LESSONS.md: "- ${TODAY} — run ${RUN_ID} aborted: WebSearch budget exhausted at spawn — relaunch from a fresh session". Write nothing else to any kb file. Then run exactly: python3 -m research.swarm.lib.kb_check and return its output verbatim plus the line you added.`

// ---------------------------------------------------------------------------
// Schemas — every schema has an object root and required ⊆ properties.
// ---------------------------------------------------------------------------
const THESIS_SCHEMA = {
  type: 'object',
  properties: {
    theses: { type: 'array', maxItems: 2, items: {
      type: 'object',
      properties: {
        id: { type: 'string' }, lens: { type: 'string' }, mechanism: { type: 'string' }, counterparty: { type: 'string' },
        prediction: { type: 'string' },
        nearest_dead_rows: { type: 'array', items: { type: 'object', properties: { row: { type: 'integer' }, why_different: { type: 'string' } }, required: ['row', 'why_different'] } },
        source_urls: { type: 'array', minItems: 1, items: { type: 'string' } },
        evidence: { type: 'string' },
        spec: { type: 'object', properties: {
          dataset: { type: 'string', enum: ['mr_edge', 'long_1h'] }, universe: { type: 'array', items: { type: 'string' }, minItems: 1 },
          timeframe: { type: 'string', enum: ['5m', '1h'] }, tp_bps: { type: 'number' }, sl_bps: { type: 'number' },
          max_hold_bars: { type: 'integer' }, expected_trades_per_week: { type: 'number' }, doa_line: { type: 'string' } },
          required: ['dataset', 'universe', 'timeframe', 'tp_bps', 'sl_bps', 'max_hold_bars', 'expected_trades_per_week', 'doa_line'] },
        signal_py: { type: 'string' }, thesis_path: { type: 'string' },
      },
      required: ['id', 'lens', 'mechanism', 'counterparty', 'prediction', 'nearest_dead_rows', 'source_urls', 'evidence', 'spec', 'signal_py', 'thesis_path'],
    } },
    exploratory_notes: { type: 'string' },
    web_budget_exhausted: { type: 'boolean' },
  },
  required: ['theses', 'web_budget_exhausted'],
}

const GATE_SCHEMA = { type: 'object', properties: {
  kept: { type: 'array', items: { type: 'object', properties: {
    id: { type: 'string' }, thesis_path: { type: 'string' }, evidence_grade: { type: 'string', enum: ['A', 'B', 'C'] }, reason: { type: 'string' } },
    required: ['id', 'thesis_path', 'evidence_grade', 'reason'] } },
  rejected: { type: 'array', items: { type: 'object', properties: {
    id: { type: 'string' }, dead_row: { type: ['integer', 'null'] }, reason: { type: 'string' } },
    required: ['id', 'dead_row', 'reason'] } },
  rejections_path: { type: 'string' } }, required: ['kept', 'rejected', 'rejections_path'] }

const REGISTER_SCHEMA = { type: 'object', properties: { frozen_path: { type: 'string' }, sha256: { type: 'string' }, ok: { type: 'boolean' }, error: { type: 'string' } }, required: ['ok'] }
const SCREEN_SCHEMA = { type: 'object', properties: { ok: { type: 'boolean' }, out_path: { type: 'string' }, n: { type: 'integer' }, net_bps_mean: { type: 'number' }, ci95: { type: 'array', items: { type: 'number' } }, wr: { type: 'number' }, p_star: { type: 'number' }, error: { type: 'string' } }, required: ['ok'] }
const AUDIT_SCHEMA = { type: 'object', properties: { verdict: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'RERUN_MISMATCH'] }, audit_path: { type: 'string' }, ci_excludes_zero: { type: 'boolean' }, findings: { type: 'array', items: { type: 'string' } } }, required: ['verdict', 'audit_path', 'ci_excludes_zero'] }
const COMMITTEE_SCHEMA = { type: 'object', properties: { votes: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, pass: { type: 'boolean' }, reasons: { type: 'array', items: { type: 'string' } } }, required: ['id', 'pass', 'reasons'] } }, path: { type: 'string' } }, required: ['votes', 'path'] }

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------
log('run alone — controller confirmed no other Workflow live')
if ((A.max_screens ?? 5) > 5) log(`max_screens=${A.max_screens} requested; clamped to the hard cap of 5`)
log(`desk ${RUN_ID}: now=${NOW} today=${TODAY} analysts=${LENSES.length}/${MAX_ANALYSTS} max_screens=${MAX_SCREENS} judge_model=${JUDGE_MODEL ?? 'inherit'} dry_run=${DRY}; caps: ≤${LENSES.length} analysts, ≤${MAX_SCREENS} screens, ≤${MAX_SCREENS} audits, 2 committee seats, 3 closing seats`)
if (LENSES.length < ALL_LENSES.length) log(`analyst cap ${MAX_ANALYSTS}: lenses NOT run this time — ${ALL_LENSES.slice(LENSES.length).map(l => l.key).join(', ')}`)

// ---------- Phase 1: Brief ----------
phase('Brief')
const mandate = await agent(BRIEF_PROMPT, { label: 'desk-brief', phase: 'Brief', effort: 'medium' })
log(mandate ? 'mandate written' : 'desk-brief returned null — analysts will run without a mandate file')

// ---------- Phase 2: Analysts (barrier is correct: the gatekeeper needs ALL theses to dedup) ----------
phase('Analysts')
const analystOut = await parallel(LENSES.map((lens, i) => () =>
  agent(analystPrompt(lens, i), { label: `analyst:${lens.key}`, phase: 'Analysts', schema: THESIS_SCHEMA, effort: 'medium' })))
const lensSummary = LENSES.map((lens, i) => ({
  lens: lens.key,
  theses: analystOut[i] ? analystOut[i].theses.length : null,
  notes: analystOut[i] ? (analystOut[i].exploratory_notes ?? '') : 'agent returned null',
  web_budget_exhausted: analystOut[i] ? analystOut[i].web_budget_exhausted === true : null,
}))
for (const s of lensSummary) if (!s.theses) log(`analyst ${s.lens}: ${s.theses === null ? 'no result (null)' : '0 theses'} — ${s.notes.slice(0, 160)}`)
const live = analystOut.filter(Boolean)
if (live.length && live.every(r => r.web_budget_exhausted === true)) {
  log(`WebSearch budget exhausted at spawn: ${live.length}/${LENSES.length} analysts could not source — aborting before the gate (internet-first directive); relaunch from a fresh session`)
  phase('Close')
  const reconcile = await agent(abortPrompt, { label: 'reconcile', phase: 'Close', effort: 'low' })
  return { run_id: RUN_ID, result: 'WEB_BUDGET_EXHAUSTED', lenses: lensSummary, reconcile }
}
const exhausted = lensSummary.filter(l => l.web_budget_exhausted).map(l => l.lens)
if (exhausted.length) log(`WebSearch budget exhausted for ${exhausted.length}/${live.length} analysts (${exhausted.join(', ')}) — continuing; recorded for synthesis`)
const theses = analystOut.filter(Boolean).flatMap(r => r.theses)
log(`${theses.length} theses from ${analystOut.filter(Boolean).length}/${LENSES.length} analysts`)
if (!theses.length) {
  phase('Close')
  const closing = await closeOut([], [], null, lensSummary)
  return { run_id: RUN_ID, result: 'NO_THESES', lenses: lensSummary, closing }
}

// ---------- Phase 3: Gatekeeper (dedup + relabel + source verification) ----------
phase('Gate')
const gate = await agent(gatePrompt(theses.map(t => t.thesis_path)),
  judge({ label: 'gatekeeper', phase: 'Gate', schema: GATE_SCHEMA, effort: 'high' }))
const kept = (gate?.kept ?? []).slice(0, MAX_SCREENS)
if ((gate?.kept ?? []).length > MAX_SCREENS) log(`gate returned ${gate.kept.length} kept; truncated to max_screens=${MAX_SCREENS} — dropped ${gate.kept.slice(MAX_SCREENS).map(k => k.id).join(', ')}`)
log(`gate kept ${kept.length} (${kept.map(k => `${k.id}:${k.evidence_grade}`).join(', ') || 'none'}), rejected ${(gate?.rejected ?? []).length}`)
if (!kept.length) {
  phase('Close')
  const closing = await closeOut([], [], gate, lensSummary)
  return { run_id: RUN_ID, result: gate ? 'ALL_REJECTED_AT_GATE' : 'GATE_FAILED', gate, lenses: lensSummary, closing }
}

// ---------- Phases 4–6: per-thesis pipeline (register → screen → audit), no barrier ----------
const chains = await pipeline(kept,
  k => agent(registrarPrompt(k), { label: `register:${k.id}`, phase: 'Register', schema: REGISTER_SCHEMA, effort: 'low' }),
  (reg, k) => (reg?.ok && reg.frozen_path)
    ? agent(screenPrompt(k, reg), { label: `screen:${k.id}`, phase: 'Screen', schema: SCREEN_SCHEMA, effort: 'high' })
    : { ok: false, error: reg?.error ?? (reg ? 'registrar returned ok without frozen_path' : 'registrar returned null') },
  (scr, k) => scr?.ok
    ? agent(auditPrompt(k), { label: `audit:${k.id}`, phase: 'Audit', schema: AUDIT_SCHEMA, effort: 'high' })
        .then(a => a ? { ...a, screened: true, screen: scr } : { verdict: 'REFUTED', audit_path: '', ci_excludes_zero: false, findings: ['auditor returned null'], screened: true, screen: scr })
    : { verdict: 'REFUTED', audit_path: '', ci_excludes_zero: false, findings: [scr?.error ?? 'screen returned null'], screened: false, screen: scr },
)
const results = kept.map((k, i) => ({ id: k.id, evidence_grade: k.evidence_grade, audit: chains[i] }))
const screenedIds = results.filter(r => r.audit?.screened).map(r => r.id)
const eligible = results.filter(r => r.audit?.verdict === 'CONFIRMED' && r.audit.ci_excludes_zero)
log(`audits: ${results.map(r => `${r.id}=${r.audit?.verdict ?? 'null'}`).join(', ')}; screened ${screenedIds.length}; committee-eligible: ${eligible.length}`)

// ---------- Phase 7: Committee (barrier correct: BH needs every screen's p-value) ----------
phase('Committee')
let committee = []
if (eligible.length) {
  const ids = eligible.map(e => e.id)
  const files = ids.map(id => `${RUN_DIR}/screens/${id}/{out.json,audit.json,trades.csv}`).join(' ')
  committee = await parallel([
    () => agent(economicsPrompt(ids, files), judge({ label: 'committee:economics', phase: 'Committee', schema: COMMITTEE_SCHEMA, effort: 'high' })),
    () => agent(statisticsPrompt(ids, files, screenedIds), judge({ label: 'committee:statistics', phase: 'Committee', schema: COMMITTEE_SCHEMA, effort: 'high' })),
  ])
  if (committee.some(v => !v)) log('a committee seat returned null — no thesis can pass this run (both seats must vote)')
} else {
  log('committee skipped: no audit is CONFIRMED with a train CI excluding zero')
}
const votes = committee.filter(Boolean)
const passed = eligible.filter(e => votes.length === 2 && votes.every(v => v.votes.find(x => x.id === e.id)?.pass)).map(e => e.id)
log(`committee passed: ${passed.length ? passed.join(', ') : 'none'}`)

// ---------- Phase 8: Close ----------
phase('Close')
const closing = await closeOut(results, passed, gate, lensSummary)
return { run_id: RUN_ID, result: passed.length ? 'SURVIVORS' : 'NO_SURVIVORS', passed, results, gate_rejected: gate?.rejected ?? [], lenses: lensSummary, closing }

// synthesis → critic → reconciler are sequential by construction (each reads the previous seat's file).
async function closeOut(results, passed, gate, lensSummary) {
  const ctx = {
    run_id: RUN_ID, dry_run: DRY,
    lenses: lensSummary,
    gate_kept: (gate?.kept ?? []).map(k => ({ id: k.id, evidence_grade: k.evidence_grade })),
    gate_rejected: gate?.rejected ?? [],
    screened: results.map(r => ({ id: r.id, screened: !!r.audit?.screened, audit_verdict: r.audit?.verdict ?? null, ci_excludes_zero: !!r.audit?.ci_excludes_zero, screen_error: r.audit?.screen?.error ?? null })),
    committee_passed: passed,
  }
  const report = await agent(synthesisPrompt(ctx), judge({ label: 'synthesis', phase: 'Close', effort: 'high' }))
  const critic = await agent(criticPrompt, judge({ label: 'critic', phase: 'Close', effort: 'high' }))
  const screenedIds = results.filter(r => r.audit?.screened).map(r => r.id)
  const reconcile = await agent(reconcilePrompt(screenedIds, passed), { label: 'reconcile', phase: 'Close', effort: 'high' })
  if (!report || !critic || !reconcile) log(`closing seat returned null: report=${!!report} critic=${!!critic} reconcile=${!!reconcile}`)
  return { report, critic, reconcile }
}
