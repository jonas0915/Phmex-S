# REPORT — run dryrun-2026-09-16 (DRY RUN / plumbing test)

Written 2026-09-16 10:18 PM PT (clock 2026-09-17T05:18:08Z). Run dir: research/swarm/runs/dryrun-2026-09-16/. Knowledge base: research/swarm/kb/.

## Verdict

One thesis was produced, zero were screened, zero passed committee — the single thesis was a deliberate relabel of DEAD_LIST row 6 and the gatekeeper rejected it, which is the outcome this dry run was designed to produce (research/swarm/runs/dryrun-2026-09-16/gate_rejections.json; research/swarm/runs/dryrun-2026-09-16/gate_kept.json is an empty list).

## Theses

**dryrun_forced_flows_delever_fade** (lens forced_flows) — GATE-REJECTED, dead row 6 (Liquidation-cascade reversion: "vol-fade with extra steps; high-vol bars CONTINUE, don't revert", research/swarm/kb/DEAD_LIST.md line 18). The thesis proposed fading a closed 5m bar on BTC/ETH/SOL whose range and volume both exceed 3 sigma of a trailing 48-bar baseline, TP/SL 150/150 bps, 24-bar max hold, 4 expected trades/week (research/swarm/runs/dryrun-2026-09-16/theses/dryrun_forced_flows_delever_fade.json, `spec`). Its own `nearest_dead_rows` field says the mechanism is "NOT different" from row 6, row 80 (tape_snapback, DEAD_LIST.md line 92: "economically the same bet as the killed liquidation-cascade-reversion family") and row 3 (1h vol-expansion fade, DEAD_LIST.md line 15). The gatekeeper's recorded reason: "relabel of DEAD_LIST row 6 ... only the indicator name (z_range>3 & z_volume>3 'deleveraging-exhaustion z-score') changed"; step-1 sanity (id regex, universe in mr_edge, 5m timeframe, signal imports, non-empty source_urls) otherwise passed and step 2 (source verification) was not reached (research/swarm/runs/dryrun-2026-09-16/gate_rejections.json). Sourcing would have failed independently: the thesis `evidence` field states that zero web searches ran (session budget exhausted), fetch 1 was a guessed arXiv URL that resolved to an unrelated paper and was not cited, and fetch 2 (https://www.coinglass.com/LiquidationData) is a real feed but returned client-rendered placeholders, so "NO external number was read from any source" (theses/dryrun_forced_flows_delever_fade.json, `evidence`). The only numbers the thesis carries are from research/swarm/lib/fee_math.py, re-run this turn: p_star(150) = 0.5383333333333333, time_to_verdict_weeks(4) = 12.5 weeks, position_notional() = 200.0, lot_check ok for BTC (2 lots at 77.74), ETH (8 lots at 24.9738), SOL (197 lots at 1.0143). No screen numbers exist for this thesis: n, net bps, CI95, WR, evidence grade, audit verdict, committee votes, BH table and the tp±20% read are all **not run** (no specs/, screens/, audits/ or committee/ directory exists in the run dir).

## What was not done

- Lenses: only one lens (forced_flows) ran, and it returned one thesis rather than none. Its exploratory notes, from the orchestrator's run context: "No exploratory probes were run (per dry-run instruction)"; the signal was sanity-checked on train-era mr_edge 5m data only for value-set and count (BTC/ETH/SOL each 20304 bars, values exactly {-1,0,1}, 196/179/253 nonzero signals — stdout of the analyst's write script, not a screen result and not persisted to any file in the run dir, so unverifiable from here). No other analyst lens existed in this run, so there is no "lens returned no thesis" entry.
- Registrar: not run — no specs/*.frozen.json exists (research/swarm/runs/dryrun-2026-09-16/specs absent). No error text, because the stage was never invoked; the thesis died at the gate.
- Screen: not run — research/swarm/runs/dryrun-2026-09-16/screens absent. No out.json, trades.csv, or out.robust_*.json anywhere in the run.
- Audit: not run — audits/ absent. No audit.json, no p_boot, so no BH input for the Statistics seat.
- Committee: not run — committee/ absent. Zero votes recorded.
- Sources that could not be fetched (per theses/dryrun_forced_flows_delever_fade.json `evidence`): WebSearch — 0 of 0 possible, budget exhausted at 200/200 before the analyst started; https://arxiv.org/abs/2507.08744 — fetched but wrong paper (guessed URL), discarded; https://www.coinglass.com/LiquidationData — fetched, page is client-rendered, placeholder values only ("total liquidations comes in at $0", largest liquidation "undefined"), no number read.
- Holdout: never read, as mandated (mandate.md section 6). No era-suffixed outputs exist.
- DEAD_LIST / SURVIVORS reconciliation (STANDARDS #15): a gate-rejected relabel of an existing row is not a new screened thesis, so no new DEAD_LIST row was written by this seat; the orchestrator should confirm whether its reconcile stage adds a dated "relabel rejected" line to LESSONS.md.

## Next run should

- Give the analyst seats a fresh WebSearch budget before they start, and have the orchestrator abort the analyst stage (not silently continue) when the budget reads exhausted at spawn time — this run's sourcing failure was a plumbing condition, not a research finding.
- Persist the analyst's signal sanity-check output (bar counts, value set, nonzero count per symbol) to a file under theses/ so the synthesis seat can cite a path instead of quoting stdout it never saw.
- Exercise the full pipeline on the plumbing side: one dry-run thesis that the gatekeeper is expected to KEEP (a non-relabel with a real fetched number), so registrar freeze, screen, audit, robustness (tp±20%) and committee stages each produce their artifacts and any stage-level errors surface before a real run.
