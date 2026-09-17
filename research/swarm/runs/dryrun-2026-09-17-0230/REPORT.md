# REPORT — run dryrun-2026-09-17-0230 (DRY RUN — plumbing test)

Clock: 2026-09-17T09:30:28Z (2:30 AM PT). Run dir: `research/swarm/runs/dryrun-2026-09-17-0230/`. Mandate: `research/swarm/runs/dryrun-2026-09-17-0230/mandate.md` (kb_check "KB OK", mandate.md:103).

## Verdict

One thesis was produced, zero were screened, zero passed committee — the single thesis was a deliberate relabel of DEAD_LIST row 6 and the gatekeeper rejected it row-cited, which is exactly the plumbing path this dry run was meant to exercise.

## Theses in this run

### Gate-rejected (from `research/swarm/runs/dryrun-2026-09-17-0230/gate_rejections.json`)

- **dryrun_forced_flows_deleverage_snapback** (lens: forced_flows) — REJECTED, dead row **6** (Liquidation-cascade reversion: "vol-fade with extra steps; high-vol bars CONTINUE, don't revert", `research/swarm/kb/DEAD_LIST.md:18`). Same family also killed as row 80 (`DEAD_LIST.md:92`), row 29 (`DEAD_LIST.md:41`), row 3 (`DEAD_LIST.md:15`). The thesis's own `nearest_dead_rows` entries all state "NOT different" (`research/swarm/runs/dryrun-2026-09-17-0230/theses/dryrun_forced_flows_deleverage_snapback.json:8-11`). Gatekeeper step 2 (source verification) was not reached; the thesis's own `evidence` field concedes the sole cited source, arXiv 2607.27070, covers pre-cascade early-warning signals and does not support post-cascade reversion (`theses/dryrun_forced_flows_deleverage_snapback.json:16`). Sanity checks that did pass per `gate_rejections.json:5`: id regex, universe symbols in `mr_edge`, lot_check at $200 notional, 5m timeframe exists, signal imports only pandas/numpy, source_urls non-empty.

Lib numbers attached to this thesis (reproduced this turn from `research/swarm/lib/fee_math.py` and `research/swarm/lib/load_data.py`; no screen numbers exist because no screen ran):
- `fee_math.p_star(150)` = 0.5383333333333333 (`research/swarm/lib/fee_math.py`)
- `fee_math.time_to_verdict_weeks(6)` = 8.333333333333334 weeks (`research/swarm/lib/fee_math.py`)
- `fee_math.position_notional()` = 200.0; `fee_math.lot_check` ok=True for ETH (8 lots @ 24.9738), SOL (197 @ 1.0143), XRP (199 @ 1.0044), DOGE (199 @ 1.001) (`research/swarm/lib/fee_math.py`)
- `fee_math.C_BPS` = 11.5 (`research/swarm/lib/fee_math.py`)
- `load_data.list_symbols('mr_edge')` = 35 symbols; ETH/SOL/XRP/DOGE all present (`research/swarm/lib/load_data.py`)

### Screened

None. `research/swarm/runs/dryrun-2026-09-17-0230/gate_kept.json` is `[]`. No `specs/*.frozen.json`, no `screens/<id>/out.json`, no `audits/`, no `committee/` exist in the run dir — n, net bps, CI95, WR vs p*, evidence grade, audit verdict, committee votes, BH table and tp±20% reads are all **not run**.

### Committee-passed

None (not run — nothing reached committee).

## What was not done

- **Analyst lenses returning no thesis:** none — the only lens (forced_flows, `max_analysts` = 1 per `launch_args.json:6`) returned exactly one thesis.
- **Lens exploratory notes (forced_flows, from the orchestrator run context):** no exploratory probes were run on train data (skipped per dry-run instruction); no holdout touched; no bot code modified; `fetch_ohlcv_ccxt` not called; web work capped at 1 WebSearch + 1 WebFetch; signal validated to compile and emit only {-1, 0, 1} on a synthetic frame. The lens flagged its own source/claim mismatch (arXiv 2607.27070 is about pre-cascade early warnings, not snap-back).
- **Web budget exhausted:** no lens — forced_flows reports `web_budget_exhausted: false`. Sourcing was not cut short; it was capped by the dry-run instruction.
- **Registrar / screen / audit errors:** none recorded — none of these stages were invoked, because `gate_kept.json` was empty (`max_screens` = 1 was never consumed, `launch_args.json:7`).
- **Sources that could not be fetched:** none reported. The one cited source (arXiv 2607.27070) was fetched by the analyst. The WebSearch-snippet liquidation figures the analyst mentions (Oct 10 2025, >$19B force-closed, $3.21B in one minute) were NOT fetched from a page and are explicitly not evidence (`theses/dryrun_forced_flows_deleverage_snapback.json:16`).
- **Gatekeeper source verification (step 2):** not reached — rejection happened at the dead-row step (`gate_rejections.json:5`). The source-verification code path is therefore still untested by this dry run.
- **Reconciliation (STANDARDS #15):** no row was added to DEAD_LIST.md or SURVIVORS.md this run; the thesis was never screened, and it is already covered by rows 6/80/29/3. No LESSONS.md line written by this seat.

## Next run should

- Exercise the gatekeeper's source-verification step (STANDARDS #2) on purpose: include one thesis that clears the dead-row filter but pairs a real paper title with a fabricated statistic, so the step-2 rejection path ("source verification F") is proven to fire — this dry run only proved the dead-row path.
- Run at least one thesis end to end through `registrar.freeze` → `screen.run_screen` → audit → committee so the era-suffixed artifact naming (STANDARDS #7), `out.robust_*.json` tp±20% reads and the BH table from `numbers.p_boot` are all produced once; none of those files exist in this run dir, so their plumbing is unverified.
- Have the orchestrator write each lens's `exploratory_notes` and `web_budget_exhausted` to a file in the run dir (e.g. `lenses.json`) rather than only passing them inline; this report had to quote them from the run context string, which leaves those claims without a citable path.
