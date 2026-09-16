export const meta = {
  name: 'internet-edge-sweep',
  description: 'Internet-wide sweep for crypto-perp edges feasible at $87 on Phemex: 10 search modalities, source verification, adversarial vetting, pre-registered tests, audited synthesis',
  phases: [
    { title: 'Sweep', detail: '10 search modalities, each blind to the others' },
    { title: 'Verify sources', detail: 'fetch every cited source; kill fabricated evidence' },
    { title: 'Dedup', detail: 'merge and rank to at most 10 candidates' },
    { title: 'Vet', detail: '3 adversarial refuters per candidate' },
    { title: 'Test', detail: 'pre-registered test on local or public data + independent audit' },
    { title: 'Synthesize', detail: 'rank survivors, slot specs, completeness critic' },
  ],
}

const S = '/private/tmp/claude-501/-Users-jonaspenaso-Desktop/cada294f-0cc3-4fac-8342-724c46c4fb06/scratchpad'
const OUT = S + '/sweep'
const REPO = '/Users/jonaspenaso/Desktop/Phmex-S'
const today = args.today

const RULES = `
HARD RULES:
- READ-ONLY on ${REPO}: never edit repo files, never run main.py/bot.py, never touch launchd, never place/cancel orders or change leverage. Scripts/outputs go under ${OUT}/ (create subfolders).
- Never invent a number or a citation. Every figure must come from a page, paper, file, or API response you actually read in this task; cite the URL or file:line. The known hallucination pattern is "real paper title + made-up statistic" — do not do it. If you could not open a source, say so and mark the claim unverified.
- The owner's account: $87.12 USDT on Phemex, USDT linear perps (maker 0.01%, taker 0.06%, min order 1 USDT; BTC lot 0.001 = ~$78 notional so BTC linear is effectively out; ETH lot 0.01 = ~$25; SOL/XRP/DOGE/1000PEPE/1000SHIB/SUI/LINK/ADA lots are ~$1). Inverse (coin-margined) perps and spot are also allowed; other venues are NOT. Bot polls every 5 minutes on a home Mac (no colocation, no sub-second speed). Full economics in ${S}/03_exchange_economics.md.
- The record of what was already tried and killed is in ${S}/01_dead_list.md. Use it ONLY as a filter (do not re-propose those), NOT as a source of ideas. The source of ideas is the outside world.
- Owner wants: a bot that trades consistently, exits mostly at take-profit, and has positive per-trade net expectancy (after fees, funding, and realistic fills) with a 95% bootstrap CI excluding zero. Paper screens candidates; live fills decide.
- Realism: maker exits fill ~0% in the record, so cost exits as taker; maker entries are adversely selected, so cost entries as taker unless the mechanism can wait; the live bot evaluates on the FORMING candle, so any test must fill at the NEXT bar/tick after the signal.`

const IDEAS_SCHEMA = { type: 'object', required: ['ideas'], properties: { ideas: { type: 'array', maxItems: 2, items: { type: 'object',
  required: ['name','mechanism','instrument','timeframe','entry','take_profit','stop_loss','hold_period','expected_trades_per_week','evidence','source_urls','feasibility_at_87','data_to_test'],
  properties: {
    name: { type: 'string' }, mechanism: { type: 'string' }, instrument: { type: 'string' }, timeframe: { type: 'string' },
    entry: { type: 'string' }, take_profit: { type: 'string' }, stop_loss: { type: 'string' }, hold_period: { type: 'string' },
    expected_trades_per_week: { type: 'string' }, evidence: { type: 'string' }, source_urls: { type: 'array', items: { type: 'string' } },
    feasibility_at_87: { type: 'string' }, data_to_test: { type: 'string' } } } } } }

const MODALITIES = [
  { key: 'academic-2024-26', prompt: 'Modality: ACADEMIC. arXiv q-fin, SSRN, Journal of Financial Markets, Finance Research Letters, 2024-2026. Search for crypto perpetual-futures return predictability, intraday/short-horizon anomalies in altcoins, funding-rate predictability, liquidation-driven price impact and reversal, order-flow imbalance at minute horizons. Extract the concrete rule the paper tested, its net-of-cost result if any, and the horizon.' },
  { key: 'open-source-live', prompt: 'Modality: OPEN-SOURCE BOTS WITH LIVE RECORDS. GitHub (freqtrade strategies, jesse, hummingbot, octobot, passivbot, nautilus), strategy leaderboards, published live dry-run/real trade logs. Find strategies with VERIFIED live or paper track records in 2025-2026 (not backtest screenshots). Extract exact rules, timeframe, pairs, fee assumptions, and what evidence of live profit exists.' },
  { key: 'practitioner', prompt: 'Modality: PRACTITIONER COMMUNITIES. r/algotrading, r/CryptoCurrencyTrading, Elite Trader, QuantConnect/Quantpedia community, quant Substacks and X/Twitter threads by crypto quants 2025-2026. Look for mechanisms people report working at small retail size on perps, with any receipts (screenshots of PnL, exchange exports). Weigh evidence quality honestly.' },
  { key: 'onchain-data', prompt: 'Modality: ON-CHAIN AND EXCHANGE-FLOW DATA. Exchange netflows, stablecoin mints/burns, whale transfers, liquidation heatmaps (Coinglass, Hyblock), open-interest and long/short ratio feeds, with FREE APIs reachable from a home Mac. Find documented lead-lag between these signals and 1h-1d perp returns on ETH and the major alts. Extract the rule and the data source URL.' },
  { key: 'cross-venue-laglead', prompt: 'Modality: CROSS-VENUE AND CROSS-INSTRUMENT LEAD-LAG at 1-5 minute horizons (not sub-second): Binance/Bybit/Hyperliquid/Coinbase spot or perp leading Phemex perps; perp-vs-spot basis oscillations; funding-settlement price behaviour around the 8h mark; index-vs-mark divergences. Find documented evidence and whether a 5-minute poller can capture it.' },
  { key: 'event-driven', prompt: 'Modality: EVENT-DRIVEN. Token unlocks, exchange listings/delistings, ETF flow prints, options expiries and max-pain (Deribit), US macro releases, protocol upgrades, airdrop claims, index rebalances. For each: the documented average move, the window, the hit rate if published, a free data source for the calendar, and whether the tradeable symbols exist on Phemex USDT perps.' },
  { key: 'alt-seasonality-vol', prompt: 'Modality: ALTCOIN INTRADAY SEASONALITY AND VOLATILITY STRUCTURE 2025-2026. Time-of-day / day-of-week return and volume patterns in SOL, XRP, DOGE, SUI, LINK, ADA, PEPE, SHIB perps; volatility-compression breakouts; overnight vs US-session behaviour. Find studies or data-backed posts with numbers, and whether the effect survives 0.12% RT.' },
  { key: 'liquidity-provision', prompt: 'Modality: RETAIL-FEASIBLE LIQUIDITY PROVISION. Wide-spread alts (XRP, 1000PEPE, SUI show 6-8 bps spreads on Phemex), inventory-skewed quoting, Avellaneda-Stoikov style market making at 5-minute update rates, and evidence of whether retail MM on a CEX without rebates can be net positive. Be honest about adverse selection.' },
  { key: 'ml-sentiment-news', prompt: 'Modality: ML / LLM / SENTIMENT / NEWS with OUT-OF-SAMPLE evidence. Social sentiment, news-flow, LLM-scored headlines, Google Trends, funding+OI feature models. Only include approaches with published out-of-sample or live results and free data. Be skeptical: extract exactly what the OOS test was.' },
  { key: 'contrarian-structural', prompt: 'Modality: CONTRARIAN AND STRUCTURAL. What do professional crypto market makers, prop firms, and funds say retail can still do (and cannot) in 2025-2026 interviews, podcasts, and blog posts? Which structural niches (illiquid hours, small-cap perps, funding extremes, forced-flow moments like liquidation cascades) do they name as retail-accessible? Extract concrete mechanisms, not platitudes.' },
]

phase('Sweep')
log('Sweep: 10 modalities')
const sweep = await parallel(MODALITIES.map(m => () => agent(
`${RULES}

You are a research scout. ${m.prompt}

Use WebSearch and WebFetch efficiently: aim for 6-8 targeted searches and 4-6 fetched pages, and stop early once you can tell the modality has nothing credible rather than continuing to search. Propose up to 2 mechanisms with every field filled. "entry"/"take_profit"/"stop_loss"/"hold_period" must be concrete rules (numbers), even if you have to state them as the paper/post implied. "evidence" states what the source actually reports, with the number and the URL. "feasibility_at_87": can it be traded at the lot minimums, and is the fee (0.07-0.12% RT) small vs the target move? "data_to_test": what data (local under ${REPO} or public via ccxt fetch_ohlcv / a free API) would test it. Check ${S}/01_dead_list.md before finalizing and drop anything that is a relabel of a killed family. If your modality yields nothing credible, return fewer ideas and say why in the evidence field.`,
  { label: `sweep:${m.key}`, phase: 'Sweep', schema: IDEAS_SCHEMA })))

const raw = sweep.filter(Boolean).flatMap((r, i) => r.ideas.map(x => ({ ...x, modality: MODALITIES[i].key })))
log(`Sweep produced ${raw.length} raw ideas`)

const DEDUP_SCHEMA = { type: 'object', required: ['candidates','dropped'], properties: {
  candidates: { type: 'array', items: { type: 'object', required: ['id','name','summary','merged_from','rank_reason','source_urls'], properties: {
    id: { type: 'string' }, name: { type: 'string' }, summary: { type: 'string' }, merged_from: { type: 'array', items: { type: 'string' } }, rank_reason: { type: 'string' }, source_urls: { type: 'array', items: { type: 'string' } } } } },
  dropped: { type: 'array', items: { type: 'object', required: ['name','reason'], properties: { name: { type: 'string' }, reason: { type: 'string' } } } } } }

phase('Dedup')
const dedup = await agent(
`${RULES}

Here are ${raw.length} raw strategy ideas from 10 internet search modalities, each with its own claimed evidence and source_urls (JSON, NOT yet independently verified):
${JSON.stringify(raw, null, 1)}

Merge duplicates/near-duplicates (same mechanism, different dressing). Drop anything that is a relabel of a dead-list entry in ${S}/01_dead_list.md (cite the entry), or whose claimed evidence is obviously thin (no real source, or a source that plainly doesn't back the claim as described). Rank the rest by: (1) plausibility of the cited evidence, (2) plausibility of positive net expectancy after 0.07-0.12% RT at $87, (3) trade frequency, (4) TP-dominant exits, (5) testability with local or public data. Return AT MOST 6 candidates with ids S1..S6, a fully self-contained "summary" (entry, TP, SL, hold, instrument, timeframe, expected frequency, data to test), and the key source_urls to verify. List everything dropped with the reason. Independent source verification happens next — do not skip weak-but-plausible ideas just because you haven't checked the URL yourself.`,
  { label: 'dedup+rank', phase: 'Dedup', schema: DEDUP_SCHEMA, effort: 'high' })
const dedupedCandidates = (dedup?.candidates || []).slice(0, 6)
log(`Dedup: ${dedupedCandidates.length} candidates kept, ${(dedup?.dropped || []).length} dropped`)
if (!dedupedCandidates.length) return { candidates: [], note: 'no candidates survived dedup', dropped: dedup?.dropped }

const SRC_SCHEMA = { type: 'object', required: ['sources_checked','sources_confirmed','fabricated_or_unsupported','evidence_grade','note'], properties: {
  sources_checked: { type: 'number' }, sources_confirmed: { type: 'number' }, fabricated_or_unsupported: { type: 'array', items: { type: 'string' } },
  evidence_grade: { type: 'string', enum: ['A','B','C','F'] }, note: { type: 'string' } } }

phase('Verify sources')
// Verify only the deduped finalists (not every raw idea) — cuts verify-phase agent count
// from "every raw idea" (up to ~20) down to at most 6.
const verified = await pipeline(dedupedCandidates,
  c => agent(
`${RULES}

You are a citation verifier. This candidate survived dedup with these claimed sources:
${JSON.stringify(c, null, 1)}

Open EVERY URL in source_urls with WebFetch (try archive.org if a page 403s). For each: does the page actually contain the claim and the number attributed to it? List each source that is unreachable, does not contain the claim, or contradicts it under fabricated_or_unsupported with a one-line reason. Grade: A = primary source(s) confirm the mechanism and the numbers; B = confirmed mechanism, numbers partially confirmed; C = only secondary/anecdotal support; F = key claims unsupported or fabricated. Keep note under 5 lines.`,
    { label: `verify:${c.id}`, phase: 'Verify sources', schema: SRC_SCHEMA, effort: 'low' }).then(v => ({ ...c, evidence_grade: v?.evidence_grade, source_check: v }))
)
const candidates = verified.filter(Boolean).filter(x => x.source_check && x.source_check.evidence_grade !== 'F')
log(`Source verification: ${candidates.length} of ${verified.filter(Boolean).length} candidates keep credible evidence`)
if (!candidates.length) return { candidates: [], note: 'no candidate survived source verification', raw }

const VERDICT_SCHEMA = { type: 'object', required: ['refuted','confidence','reason'], properties: {
  refuted: { type: 'boolean' }, confidence: { type: 'string', enum: ['low','medium','high'] }, reason: { type: 'string' } } }
const REFUTERS = [
  { key: 'record', prompt: `Lens: THE RECORD AS FILTER. Read ${S}/01_dead_list.md. Is this a relabel or thin variant of a killed family, or does it depend on something the record showed fails at this account (maker exits, entry gates, OB-imbalance, L2 confirmation, backtest-only edges)? Refute only if the record already answered THIS mechanism; a genuinely new mechanism is not refuted just because it is intraday.` },
  { key: 'economics', prompt: `Lens: FEES, SIZE, EXECUTION AND STATISTICS. Read ${S}/03_exchange_economics.md. At $87 with the stated instrument: tradeable at the lot minimum? RT fee as % of the TP distance? With taker entry and exit plus a -4.5 bps drift haircut, does the TP/SL geometry and a realistic hit rate leave positive expectancy? Show the arithmetic. Also: the pass bar is a 95% bootstrap CI on per-trade net excluding zero — given expected frequency and realistic edge/sd, how many trades/weeks to a verdict, and can a 5-minute poller execute it without look-ahead? Refute if either the economics or the statistics don't work.` },
]

phase('Vet')
const vetted = await pipeline(candidates,
  c => parallel(REFUTERS.map(r => () => agent(
`${RULES}

You are an adversarial reviewer whose job is to REFUTE this candidate. Default to refuted=true if uncertain. ${r.prompt}

CANDIDATE ${c.id} — ${c.name} (evidence grade ${c.evidence_grade})
${c.summary}

Return refuted, confidence, and a reason with the numbers or citations that decide it.`,
    { label: `refute:${r.key}:${c.id}`, phase: 'Vet', schema: VERDICT_SCHEMA, effort: 'medium' }))).then(votes => {
      const v = votes.filter(Boolean)
      const refutations = v.filter(x => x.refuted).length
      // 2 refuters now (was 3): require BOTH to approve, not a majority — keeps the bar
      // at least as strict as the old 3-vote "majority survives" rule.
      return { ...c, votes: v, refutations, survives: v.length >= 2 && refutations === 0 }
    })
)
const survivors = vetted.filter(Boolean).filter(c => c.survives)
log(`Vet: ${survivors.length} survive, ${vetted.filter(Boolean).length - survivors.length} refuted`)

const TEST_SCHEMA = { type: 'object', required: ['tested','method','n_trades','net_pnl_usd','per_trade_mean_usd','ci95_low','ci95_high','tp_hit_rate','sl_hit_rate','fee_assumptions','fill_assumptions','data_source','script_path','caveats'], properties: {
  tested: { type: 'boolean' }, method: { type: 'string' }, n_trades: { type: 'number' }, net_pnl_usd: { type: 'number' }, per_trade_mean_usd: { type: 'number' },
  ci95_low: { type: 'number' }, ci95_high: { type: 'number' }, tp_hit_rate: { type: 'number' }, sl_hit_rate: { type: 'number' },
  fee_assumptions: { type: 'string' }, fill_assumptions: { type: 'string' }, data_source: { type: 'string' }, script_path: { type: 'string' }, caveats: { type: 'string' } } }
const AUDIT_SCHEMA = { type: 'object', required: ['valid','issues','verdict','corrected_summary'], properties: {
  valid: { type: 'boolean' }, issues: { type: 'array', items: { type: 'string' } }, verdict: { type: 'string', enum: ['PASS','FAIL','INCONCLUSIVE'] }, corrected_summary: { type: 'string' } } }

phase('Test')
const tested = await pipeline(survivors,
  c => agent(
`${RULES}

You are a quant researcher running a PRE-REGISTERED measurement of one candidate. Work under ${OUT}/test_${c.id}/. Data: local files under ${REPO} (backtest_data*, logs/, *.jsonl, the archive at /Users/jonaspenaso/Desktop/Phmex-S-archive) OR public data via ccxt (Phemex public fetch_ohlcv needs no keys; up to 2 years of 5m/15m/1h/1d candles) or the free API the candidate names. Prefer the longest honest sample.

CANDIDATE ${c.id} — ${c.name}
${c.summary}
Reviewer notes that survived vetting: ${JSON.stringify(c.votes)}

Steps: (1) Write ${OUT}/test_${c.id}/prereg.md FIRST: exact rules, symbols, date range, fee model (taker 0.06% each side unless the mechanism can genuinely wait for a maker fill, plus a -4.5 bps entry haircut, plus funding for holds crossing 8h marks), fill model (next bar open / next tick after the signal, never the signal bar), size at $87 honoring lot minimums, and the pass/fail line (95% bootstrap CI on per-trade net excludes zero, independent resampling). (2) Fetch/inspect the data. (3) Run a python script saved in that folder. (4) Report all fields. If untestable, tested=false and explain. No parameter tuning after seeing results; if rules change, say so and re-register.`,
    { label: `test:${c.id}`, phase: 'Test', schema: TEST_SCHEMA, effort: 'high' }),
  (t, c) => agent(
`${RULES}

You are an independent auditor. Another agent tested candidate ${c.id} — ${c.name} and reported:
${JSON.stringify(t, null, 1)}

Read the prereg and script in ${OUT}/test_${c.id}/. Check for: look-ahead (forming-bar issue), fill fantasy (signal-bar close fills, assumed maker fills), fee/funding omissions, the sorted-bootstrap bug, symbol/date cherry-picking, rule changes after results, n too small, and whether TP hits actually dominate exits. RE-RUN the script to confirm the numbers reproduce. valid=false if any issue would change the verdict. PASS only if the CI excludes zero on the positive side with honest fills/fees and meaningful n; FAIL if the CI includes/below zero or the result is an artifact; INCONCLUSIVE if untestable. corrected_summary: 5-8 plain-English lines.`,
    { label: `audit:${c.id}`, phase: 'Test', schema: AUDIT_SCHEMA, effort: 'high' }).then(a => ({ candidate: c, test: t, audit: a }))
)
const results = tested.filter(Boolean)
const passed = results.filter(r => r.audit?.verdict === 'PASS')
const inconclusive = results.filter(r => r.audit?.verdict === 'INCONCLUSIVE')
log(`Test: ${passed.length} PASS, ${inconclusive.length} INCONCLUSIVE, ${results.length - passed.length - inconclusive.length} FAIL`)

phase('Synthesize')
const synthesis = await agent(
`${RULES}

Write the final report for the owner (plain English, verdict first, no fluff). Save to ${OUT}/REPORT.md and return it as your final text.

Inputs:
- Raw ideas from the internet sweep: ${raw.length}; candidates after dedup: ${dedupedCandidates.length}; source-verified (grade != F): ${candidates.length}; dropped at dedup: ${JSON.stringify(dedup?.dropped || [])}
- Vetting (votes): ${JSON.stringify(vetted.filter(Boolean).map(c => ({ id: c.id, name: c.name, grade: c.evidence_grade, refutations: c.refutations, survives: c.survives, votes: c.votes })), null, 1)}
- Test + audit: ${JSON.stringify(results.map(r => ({ id: r.candidate.id, name: r.candidate.name, summary: r.candidate.summary, test: r.test, audit: r.audit })), null, 1)}

Sections: (1) Verdict in 3 lines. (2) For each PASS or INCONCLUSIVE candidate: a pre-registered PAPER SLOT SPEC draft — entry, TP, SL, hold, symbols, sizing at $87 honoring lot minimums, expected trades/week, KILL line, PASS line (CI lower bound > 0 at n>=N), estimated weeks to verdict, data feeds the bot would need, and what the slot framework needs built (read ${S}/02_framework_audit.md if it exists). (3) One line per FAIL and per candidate refuted at vetting with the deciding reason. (4) Ideas killed at source verification (fabricated/unsupported evidence), one line each. (5) Honest limits. Today is ${today}.`,
  { label: 'synthesis', phase: 'Synthesize', effort: 'high' })

const critique = await agent(
`${RULES}

Completeness critic. Read ${OUT}/REPORT.md and the folder ${OUT}/. What is missing or unverified? Which claims lack a cited URL/file/number? Which modalities returned nothing and should be re-run with a different angle? Did any PASS rest on an unrealistic fill model? Max 12 bullets, each with the concrete next step. Append under "Critic: gaps" in ${OUT}/REPORT.md and return the list.`,
  { label: 'critic', phase: 'Synthesize', effort: 'high' })

return { summary: synthesis, critique, counts: { raw: raw.length, deduped: dedupedCandidates.length, credible: candidates.length, survivors: survivors.length, passed: passed.length, inconclusive: inconclusive.length } }