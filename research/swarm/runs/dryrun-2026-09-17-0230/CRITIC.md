# CRITIC — completeness review, run dryrun-2026-09-17-0230 (DRY RUN — plumbing test)

Reviewed: `research/swarm/runs/dryrun-2026-09-17-0230/REPORT.md` against every file in the run dir (`find research/swarm/runs/dryrun-2026-09-17-0230 -type f | sort` → 6 files: `REPORT.md`, `gate_kept.json`, `gate_rejections.json`, `launch_args.json`, `mandate.md`, `theses/dryrun_forced_flows_deleverage_snapback.json`). No `specs/`, `screens/`, `exploratory/`, `audits/`, or `committee/` directories exist. Every file was re-opened; the report was not trusted.

## (a) Uncited artifacts (screens/, exploratory/, committee/)

1. none — no `screens/`, `exploratory/`, or `committee/` directory exists in the run dir. All six files present are cited by path in `REPORT.md` (`gate_rejections.json` at REPORT.md:11, `gate_kept.json` at REPORT.md:24, `launch_args.json` at REPORT.md:32/35, `mandate.md` at REPORT.md:3, `theses/dryrun_forced_flows_deleverage_snapback.json` at REPORT.md:13). No orphans.

## (b) Numbers in the report without a file path next to them

1. `REPORT.md:33` — "web work capped at 1 WebSearch + 1 WebFetch" and "signal validated to compile and emit only {-1, 0, 1} on a synthetic frame": these counts/claims are attributed to "the orchestrator run context" and have no file in the run dir. Unverifiable from artifacts. (The report itself flags this at REPORT.md:44 and proposes a `lenses.json`; the defect stands until that file exists.)
2. `REPORT.md:34` — `web_budget_exhausted: false` is quoted with no file path; same root cause as item 1.
3. `REPORT.md:16-20` — the lib numbers (`p_star(150)` = 0.5383333333333333, `time_to_verdict_weeks(6)` = 8.333333333333334, `position_notional()` = 200.0, `lot_check` lots 8/197/199/199, `C_BPS` = 11.5, `list_symbols('mr_edge')` = 35) are cited to the library source files (`research/swarm/lib/fee_math.py`, `research/swarm/lib/load_data.py`) rather than to any output artifact in the run dir. Re-run by this seat this turn; every value reproduces exactly (`python3 -c "from research.swarm.lib import fee_math as f, load_data as ld; ..."` — output: `p_star(150)= 0.5383333333333333`, `ttv(6)= 8.333333333333334`, `notional= 200.0`, `C_BPS= 11.5`, ETH `{'ok': True, 'lots': 8, 'lot_usd': 24.9738}`, SOL `197`, XRP `199`, DOGE `199`, `n_syms= 35`). Minor: correct and reproducible, but STANDARDS #11 wants an artifact path, not a source path — nothing in the run dir records these outputs.
4. `REPORT.md:3` — the clock string `2026-09-17T09:30:28Z` is not cited to `launch_args.json:3` (`"now": "2026-09-17T09:30:28Z"`), which is where it lives in the run dir. Trivial.

## (c) Contradictions between gate_rejections.json / theses / out.json / audit.json / committee / out.robust_* and the report

1. `mandate.md:52-55` (section 4) states "Explicitly NOT scalping. No sub-100-bps targets, no 5-minute-horizon mechanisms" and "At least two analyst lenses must target holds > 8h." The only thesis (`theses/dryrun_forced_flows_deleverage_snapback.json:36-39`) is on `timeframe: "5m"` with `max_hold_bars: 48` (= 4h at 5m, under 8h). `gate_rejections.json:5` rejects it solely on dead row 6 and lists the passed sanity checks without mentioning the mandate-§4 horizon violation; `REPORT.md:13` repeats that list and never surfaces the mandate conflict. The report and gatekeeper record are silent on a mandate breach that is visible in the thesis file. (Dry-run context notwithstanding, the omission is a completeness defect.)
2. `mandate.md:55` requires "at least two analyst lenses" targeting >8h holds, but `launch_args.json:6` sets `max_analysts: 1`. The report (`REPORT.md:32`) cites `max_analysts = 1` without noting it makes the mandate's two-lens requirement unsatisfiable in this run.
3. `REPORT.md:13` and `gate_rejections.json:5` both state that the thesis's `nearest_dead_rows` entries "all state 'NOT different'". Re-opened: rows 6, 80, 29 do (`theses/...json:8-10`: "NOT different.", "NOT materially different.", "NOT different in family."), but row 3 (`theses/...json:11`) says "Same family (vol-expansion fade) on 1h rather than 5m ... does not introduce a new mechanism" — same meaning, not the quoted wording. Minor paraphrase presented as a quote.
4. `out.json`, `audit.json`, `committee/*.json`, `out.robust_*.json`: none exist (confirmed by `find`), and the report says so at `REPORT.md:24`, `REPORT.md:28`. No contradiction. Everything else cross-checked matches: `gate_kept.json` is literally `[]`; `gate_rejections.json:4` `dead_row: 6` matches `REPORT.md:13`; DEAD_LIST line cites `DEAD_LIST.md:18` (row 6), `:92` (row 80), `:41` (row 29), `:15` (row 3) all resolve to the stated rows (verified with `sed -n '15p;18p;41p;92p' research/swarm/kb/DEAD_LIST.md`); `mandate.md:103` is `KB OK`; `launch_args.json:7` is `"max_screens": 1`.

## (d) Theses with empty nearest_dead_rows, generic why_different, or evidence with no number

1. none. `theses/dryrun_forced_flows_deleverage_snapback.json:7-12` lists four rows (6, 80, 29, 3), each with a row-specific `why_different` (all deliberately conceding "not different", which is the dry-run's intent and is what the gatekeeper correctly rejected). `evidence` (`theses/...json:16`) contains source-reported numbers: seven cascades 2022-2025, price early-warning in five of seven events, 67-85% and 3-10% of configurations, Fisher-combined p~5e-6. Note (not a defect): the thesis itself concedes that source (arXiv 2607.27070) does not support the snap-back claim; gatekeeper step 2 was never exercised (`REPORT.md:37`).

## (e) Holdout access

1. none. `grep -rn "COMMITTEE-HOLDOUT-READ\|era=\"holdout\"\|era='holdout'\|era=\"all\"\|--era holdout\|--era all" research/swarm/runs/dryrun-2026-09-17-0230` → no matches (grep exit 1).

## (f) Frozen spec / signal.py sha verification

1. none to verify. `python3 -c "from research.swarm.lib import registrar as r; import glob; print({p: r.verify(p) for p in glob.glob('research/swarm/runs/dryrun-2026-09-17-0230/specs/*.frozen.json')})"` → `{}` (no `specs/` directory exists; nothing was frozen, consistent with `gate_kept.json` = `[]`). The registrar verify path is therefore untested by this run (already noted at `REPORT.md:43`).

## (g) Daily-ROI targets or hand-computed statistics in the report

1. none. `grep -n -i "roi\|per day\|/day\|daily\|%\|sharpe\|win rate\|WR"` over `REPORT.md` hits only lines 24, 38, 43, 44, all of which are "not run" / process notes with no target and no arithmetic. All statistics in the report (`REPORT.md:16-20`) are lib outputs, reproduced exactly this turn (see (b) item 3). The "2:30 AM PT" at `REPORT.md:3` is a timezone conversion of `launch_args.json:3`, not a statistic.

## Summary

Process failures: none (no holdout access, no sha drift, no fabricated or hand-rolled numbers, no ROI target, no orphaned artifacts). Completeness defects: (b)1-2 — two lens claims in the report have no artifact path; (c)1-2 — the report and `gate_rejections.json` do not surface that the sole thesis is a 5m / <8h-hold mechanism the mandate's section 4 forbids, nor that `max_analysts: 1` makes the mandate's two->8h-lens requirement unsatisfiable. Minor: (b)3-4, (c)3.
