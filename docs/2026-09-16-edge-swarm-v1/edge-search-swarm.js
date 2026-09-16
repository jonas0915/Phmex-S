export const meta = {
  name: 'edge-search-swarm',
  description: 'Ideate, vet, test, and audit candidate trading strategies for a $87 Phemex perp account; outputs pre-registered paper-slot specs',
  phases: [
    { title: 'Ideate', detail: 'six lenses propose mechanisms not on the dead list' },
    { title: 'Dedup', detail: 'merge and rank to at most 8 candidates' },
    { title: 'Vet', detail: '3 adversarial refuters per candidate' },
    { title: 'Test', detail: 'pre-registered replay on local data + independent audit' },
    { title: 'Synthesize', detail: 'rank survivors, draft slot specs, completeness critic' },
  ],
}

const S = '/private/tmp/claude-501/-Users-jonaspenaso-Desktop/cada294f-0cc3-4fac-8342-724c46c4fb06/scratchpad'
const REPO = '/Users/jonaspenaso/Desktop/Phmex-S'
const today = args.today

const RULES = `
HARD RULES (non-negotiable):
- READ-ONLY on ${REPO}: never edit repo files, never run main.py/bot.py, never touch launchd, never place/cancel orders or change leverage. Any scripts or outputs you create go under ${S}/swarm/ (create subfolders as needed).
- Never invent a number. Every figure must come from a file or API response you read in this task, and you cite it (file:line or endpoint).
- Context files to read first: ${S}/01_dead_list.md (76 killed families/levers, structural constraints, owner directives, untested space), ${S}/03_exchange_economics.md (live fees maker 0.01%/taker 0.06%, lot minimums, funding, book depth). Also read ${S}/02_framework_audit.md and ${S}/04_edge_candidates.md IF they exist (they may still be being written).
- Owner requirements: capital stays at $87.12; scope = intraday USDT perps on the existing 5-minute framework, multi-day/weekly holds, and other Phemex instruments (inverse perps, spot); NOT other venues. Owner wants a bot that trades consistently and whose exits are mostly take-profit hits. Pass bar = per-trade net expectancy (after fees + funding) with a 95% bootstrap CI excluding zero. Paper screens, live fills give the final verdict.
- Known traps from the record: the live bot fires on the FORMING candle so closed-bar replays test the wrong population; maker exits fill ~0%, assume taker exits; maker entries are adversely selected (~-4.5 bps) so assume taker entries unless you model queue honestly; two stops erase 6-8 small wins; bootstrap diff-CI must resample independently then sort DIFFS (never sort each side first); BTC lot = ~$78 notional so BTC is effectively untradeable at $87; halt math: one full $15-margin stop is about -$2.`

const IDEAS_SCHEMA = { type: 'object', required: ['ideas'], properties: { ideas: { type: 'array', items: { type: 'object',
  required: ['name','mechanism','instrument','timeframe','entry','take_profit','stop_loss','hold_period','expected_trades_per_week','why_not_dead','evidence','local_data_needed','tp_dominance_rationale'],
  properties: {
    name: { type: 'string' }, mechanism: { type: 'string' }, instrument: { type: 'string' }, timeframe: { type: 'string' },
    entry: { type: 'string' }, take_profit: { type: 'string' }, stop_loss: { type: 'string' }, hold_period: { type: 'string' },
    expected_trades_per_week: { type: 'string' }, why_not_dead: { type: 'string' }, evidence: { type: 'string' },
    local_data_needed: { type: 'string' }, tp_dominance_rationale: { type: 'string' } } } } } }

const LENSES = [
  { key: 'execution-flip', prompt: 'Lens: EXECUTION FLIP. The record killed maker-entry books because passive fills are adversely selected. Propose mechanisms where the signal is strong enough to justify TAKER entry at signal time, where the TP is set to a level with structural reason to be hit (e.g. prior swing, session VWAP, liquidation cluster) and the fee (0.12% RT taker-taker, 0.07% maker-taker) is small relative to the TP distance.' },
  { key: 'higher-timeframe', prompt: 'Lens: HIGHER TIMEFRAME LEVELS. Volume-profile, prior-session / prior-day / weekly levels, and multi-hour to multi-day holds are listed as untested in the dead list. Propose mechanisms trading those levels on ETH and the $1-floor alts where fees are a small fraction of the move and TP sits at the next level.' },
  { key: 'breakout-regime', prompt: 'Lens: BREAKOUT / VOLATILITY REGIME. Breakout mode is untested. Propose range-expansion / compression-breakout mechanisms with TP at a measured-move target and a stop back inside the range, and say how the TP-hit rate would be kept high (e.g. partial target at 1R).' },
  { key: 'event-catalyst', prompt: 'Lens: CATALYST / EVENT SELECTION. The record says the literature edge for VWAP-type entries is catalyst SELECTION, and catalyst selection as a mechanism is untested. Propose mechanisms keyed to scheduled or detectable events (funding settlements every 8h, US macro prints, exchange listings, large liquidation prints, open-interest jumps) with concrete data sources reachable from a home Mac via ccxt/public APIs.' },
  { key: 'instrument-structure', prompt: 'Lens: OTHER PHEMEX INSTRUMENTS. Inverse (coin-margined) perps are untested as a traded instrument; spot exists. Propose mechanisms that exploit instrument structure at $87 (e.g. inverse BTCUSD $1 contracts to trade BTC under the $78 linear lot wall, spot-vs-perp behaviours, funding-settlement timing) and be explicit about fees on each leg.' },
  { key: 'flow-toxicity', prompt: 'Lens: ORDER-FLOW / TOXICITY. OFI-rollover, crumbling-bid gates, and ML toxicity gating are untested (data-starved then; there is now a 1.97 GB l2_ticks/flow_capture archive). Propose mechanisms that use the locally recorded L2/flow data to time entries so TP is hit before adverse selection bites, and say exactly which local files would test them.' },
]

phase('Ideate')
log('Ideation: 6 lenses')
const ideaSets = await parallel(LENSES.map(l => () => agent(
`${RULES}

You are a quantitative strategy designer. ${l.prompt}

Propose up to 3 mechanisms. For each fill every field. "why_not_dead" must name the closest dead-list entries in ${S}/01_dead_list.md and explain the concrete difference in MECHANISM (not parameters). "expected_trades_per_week" must be an estimate with the reasoning (e.g. symbols x signals/day). "local_data_needed" names files under ${REPO} (backtest_data*, logs/, *.jsonl) or the archive at /Users/jonaspenaso/Desktop/Phmex-S-archive that would test it; inspect what exists (ls, head) before naming them. Be concrete: exact entry rule, exact TP and SL in % or ATR, exact hold limit. If your lens yields nothing that survives fees at $87, return fewer ideas and say so in the evidence field.`,
  { label: `ideate:${l.key}`, phase: 'Ideate', schema: IDEAS_SCHEMA })))

const allIdeas = ideaSets.filter(Boolean).flatMap((r, i) => r.ideas.map(x => ({ ...x, lens: LENSES[i].key })))
log(`Ideation produced ${allIdeas.length} raw ideas`)

const DEDUP_SCHEMA = { type: 'object', required: ['candidates','dropped'], properties: {
  candidates: { type: 'array', items: { type: 'object', required: ['id','name','summary','merged_from','rank_reason'], properties: {
    id: { type: 'string' }, name: { type: 'string' }, summary: { type: 'string' }, merged_from: { type: 'array', items: { type: 'string' } }, rank_reason: { type: 'string' } } } },
  dropped: { type: 'array', items: { type: 'object', required: ['name','reason'], properties: { name: { type: 'string' }, reason: { type: 'string' } } } } } }

phase('Dedup')
const dedup = await agent(
`${RULES}

Here are ${allIdeas.length} raw strategy ideas from 6 lenses (JSON):
${JSON.stringify(allIdeas, null, 1)}

Merge duplicates and near-duplicates (same mechanism, different dressing). Drop anything that is plainly a relabel of a dead-list entry in ${S}/01_dead_list.md, citing the entry. Rank the rest by: (1) plausibility of positive expectancy after 0.07-0.12% RT fees at $87, (2) trade frequency (owner wants consistent trading), (3) TP-dominant exits, (4) testability on local data. Return AT MOST 5 candidates, each with a full self-contained "summary" (entry, TP, SL, hold, instrument, timeframe, expected frequency, data to test) so downstream agents need nothing else. List everything dropped with the reason.`,
  { label: 'dedup+rank', phase: 'Dedup', schema: DEDUP_SCHEMA, effort: 'high' })

const candidates = (dedup?.candidates || []).slice(0, 5)
log(`Dedup: ${candidates.length} candidates kept, ${(dedup?.dropped || []).length} dropped`)
if (!candidates.length) return { candidates: [], note: 'no candidates survived dedup', dropped: dedup?.dropped }

const VERDICT_SCHEMA = { type: 'object', required: ['refuted','confidence','reason'], properties: {
  refuted: { type: 'boolean' }, confidence: { type: 'string', enum: ['low','medium','high'] }, reason: { type: 'string' } } }

const REFUTERS = [
  { key: 'record', prompt: `Lens: THE RECORD. Read ${S}/01_dead_list.md fully. Is this candidate a relabel or thin variant of any killed family or lever, or does it depend on a mechanism the record already showed fails (maker exits, entry gates, OB imbalance, L2 confirmation, backtest-only edges)? Refute if the record already answered it.` },
  { key: 'economics', prompt: `Lens: FEES, SIZE, EXECUTION AND STATISTICS. Read ${S}/03_exchange_economics.md. At $87 with the stated instrument and sizing: can it be traded at the exchange lot minimum? What is the RT fee as a % of the TP distance? With taker entries (the record says maker fills are adversely selected) and taker exits, plus ~-4.5 bps drift, does the stated TP/SL geometry and a realistic hit rate leave positive expectancy? Show the arithmetic. Also: the pass bar is a 95% bootstrap CI on per-trade net excluding zero — given expected trade frequency and a realistic edge vs. its standard deviation, how many trades/weeks to reach that bar, and is "TP-dominant exits" achievable without a payoff asymmetry that makes 2 stops erase 6 wins? Refute if either the economics or the statistics don't work.` },
]

phase('Vet')
const vetted = await pipeline(candidates,
  c => parallel(REFUTERS.map(r => () => agent(
`${RULES}

You are an adversarial reviewer. Your job is to REFUTE this strategy candidate. Default to refuted=true if uncertain. ${r.prompt}

CANDIDATE ${c.id} — ${c.name}
${c.summary}

Return refuted (bool), confidence, and a reason with the specific numbers or record citations that decide it.`,
    { label: `refute:${r.key}:${c.id}`, phase: 'Vet', schema: VERDICT_SCHEMA, effort: 'medium' }))).then(votes => {
      const v = votes.filter(Boolean)
      const refutations = v.filter(x => x.refuted).length
      // 2 refuters now (was 3): require BOTH to approve, not a majority — keeps the bar
      // at least as strict as the old 3-vote "majority survives" rule.
      return { ...c, votes: v, refutations, survives: v.length >= 2 && refutations === 0 }
    })
)
const survivors = vetted.filter(Boolean).filter(c => c.survives)
const killed = vetted.filter(Boolean).filter(c => !c.survives)
log(`Vet: ${survivors.length} survive, ${killed.length} refuted`)

const TEST_SCHEMA = { type: 'object', required: ['tested','method','n_trades','net_pnl_usd','per_trade_mean_usd','ci95_low','ci95_high','tp_hit_rate','sl_hit_rate','fee_assumptions','fill_assumptions','script_path','caveats'], properties: {
  tested: { type: 'boolean' }, method: { type: 'string' }, n_trades: { type: 'number' }, net_pnl_usd: { type: 'number' }, per_trade_mean_usd: { type: 'number' },
  ci95_low: { type: 'number' }, ci95_high: { type: 'number' }, tp_hit_rate: { type: 'number' }, sl_hit_rate: { type: 'number' },
  fee_assumptions: { type: 'string' }, fill_assumptions: { type: 'string' }, script_path: { type: 'string' }, caveats: { type: 'string' } } }

const AUDIT_SCHEMA = { type: 'object', required: ['valid','issues','verdict','corrected_summary'], properties: {
  valid: { type: 'boolean' }, issues: { type: 'array', items: { type: 'string' } }, verdict: { type: 'string', enum: ['PASS','FAIL','INCONCLUSIVE'] }, corrected_summary: { type: 'string' } } }

phase('Test')
const tested = await pipeline(survivors,
  c => agent(
`${RULES}

You are a quant researcher running a PRE-REGISTERED measurement of one candidate on LOCAL data only (no live API needed; you may use ccxt public fetch_ohlcv to fill gaps if local data is insufficient, but say so). Work under ${S}/swarm/test_${c.id}/.

CANDIDATE ${c.id} — ${c.name}
${c.summary}

Reviewer notes that survived vetting: ${JSON.stringify(c.votes)}

Steps: (1) Write the pre-registration FIRST to ${S}/swarm/test_${c.id}/prereg.md: exact rules, symbols, date range, fee model (taker 0.06% each side unless the mechanism justifies maker, plus a -4.5 bps entry drift haircut), fill model (fills at the NEXT bar's open or next tick after the signal, never the signal bar's close), position size at $87 (respect lot minimums from 03_exchange_economics.md), and the pass/fail line (95% bootstrap CI on per-trade net excludes zero). (2) Inspect what local data exists (${REPO}/backtest_data*, ${REPO}/logs/, jsonl files, the archive) and use the longest honest sample. (3) Run it with a python script saved in that folder. (4) Bootstrap the per-trade mean CI (10,000 resamples, independent). (5) Report all fields; if the data cannot test the mechanism, set tested=false and explain in caveats. Do not tune parameters after seeing results; if you must change the rules, say so and re-register.`,
    { label: `test:${c.id}`, phase: 'Test', schema: TEST_SCHEMA, effort: 'high' }),
  (t, c) => agent(
`${RULES}

You are an independent auditor. Another agent tested candidate ${c.id} — ${c.name} and reported:
${JSON.stringify(t, null, 1)}

Read the pre-registration and the script at the reported script_path and the folder ${S}/swarm/test_${c.id}/. Check for: look-ahead (signal uses the same bar it fills on, forming-bar issue), fill fantasy (fills at signal-bar close, maker fills assumed), fee/funding omissions, the sorted-bootstrap bug (must resample independently then sort DIFFS), survivorship or symbol cherry-picking, rule changes after seeing results, n too small for the CI to mean anything, and whether TP hits actually dominate exits. RE-RUN the script yourself to confirm the numbers reproduce. Set valid=false if any issue would change the verdict. verdict PASS only if CI excludes zero on the positive side with an honest fill/fee model and n is meaningful; FAIL if CI includes or is below zero or the result is an artifact; INCONCLUSIVE if untestable on local data. corrected_summary: 5-8 lines a busy owner can read.`,
    { label: `audit:${c.id}`, phase: 'Test', schema: AUDIT_SCHEMA, effort: 'high' }).then(a => ({ candidate: c, test: t, audit: a }))
)
const results = tested.filter(Boolean)
const passed = results.filter(r => r.audit?.verdict === 'PASS')
const inconclusive = results.filter(r => r.audit?.verdict === 'INCONCLUSIVE')
log(`Test: ${passed.length} PASS, ${inconclusive.length} INCONCLUSIVE, ${results.length - passed.length - inconclusive.length} FAIL`)

phase('Synthesize')
const synthesis = await agent(
`${RULES}

You are writing the final report for the owner (plain English, verdict first, no fluff, no strategy pitches beyond what the evidence supports). Write it to ${S}/swarm/REPORT.md and also return it as your final text.

Inputs:
- Raw ideas: ${allIdeas.length}; candidates after dedup: ${candidates.length}; dropped at dedup: ${JSON.stringify(dedup?.dropped || [])}
- Vetting results (with votes): ${JSON.stringify(vetted.filter(Boolean).map(c => ({ id: c.id, name: c.name, refutations: c.refutations, survives: c.survives, votes: c.votes })), null, 1)}
- Test + audit results: ${JSON.stringify(results.map(r => ({ id: r.candidate.id, name: r.candidate.name, summary: r.candidate.summary, test: r.test, audit: r.audit })), null, 1)}

Report sections: (1) Verdict in 3 lines: how many candidates PASSED an audited pre-registered test, and whether anything is worth a paper slot. (2) For each PASS or INCONCLUSIVE candidate: a pre-registered PAPER SLOT SPEC draft — entry, TP, SL, hold, symbols, sizing at $87 honoring lot minimums, expected trades/week, KILL line (e.g. n>=N and net<=X, or CI upper bound < 0) and PASS line (CI lower bound > 0 at n>=N), estimated weeks to verdict, and what code the slot framework needs (read ${S}/02_framework_audit.md if it exists). (3) For each FAIL and each candidate refuted at vetting: one line, name + the deciding reason, so the owner's dead list can be extended. (4) Honest limits: what local data could not test, what only live fills can answer. Dates: today is ${today}.`,
  { label: 'synthesis', phase: 'Synthesize', effort: 'high' })

const critique = await agent(
`${RULES}

You are the completeness critic. Read ${S}/swarm/REPORT.md and the folder ${S}/swarm/. Answer: what is missing or unverified? Which claims in the report lack a cited file or number? Which lenses or untested mechanisms from ${S}/01_dead_list.md section D were never turned into a candidate and why? Did any PASS rest on a fill model the record says is unrealistic? Return a short list (max 12 bullets) of concrete gaps, each with what the next round of work would be. Append it to ${S}/swarm/REPORT.md under a heading "Critic: gaps" and return the same list.`,
  { label: 'critic', phase: 'Synthesize', effort: 'high' })

return { summary: synthesis, critique, counts: { raw: allIdeas.length, candidates: candidates.length, survivors: survivors.length, passed: passed.length, inconclusive: inconclusive.length } }