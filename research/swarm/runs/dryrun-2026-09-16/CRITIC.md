# CRITIC — completeness review of run dryrun-2026-09-16 (DRY RUN)

Reviewed 2026-09-16 10:18 PM PT (clock 2026-09-17T05:18:08Z). Inputs re-opened: REPORT.md, gate_kept.json, gate_rejections.json, theses/dryrun_forced_flows_delever_fade.json, mandate.md, research/swarm/kb/DEAD_LIST.md. Run-dir file inventory (find -type f | sort, 5 files before this review): gate_kept.json, gate_rejections.json, mandate.md, REPORT.md, theses/dryrun_forced_flows_delever_fade.json. No specs/, screens/, exploratory/, audits/ or committee/ directory exists.

## (a) Artifacts not cited in the report

1. none — every file in the run dir is cited by path in REPORT.md: theses/dryrun_forced_flows_delever_fade.json (REPORT.md line 11), gate_rejections.json (line 7, 11), gate_kept.json (line 7), mandate.md (line 21). There are no screens/<id>/, exploratory/ or committee/ artifacts to orphan.

## (b) Numbers in the report without a file path

1. REPORT.md line 15 — "BTC/ETH/SOL each 20304 bars, values exactly {-1,0,1}, 196/179/253 nonzero signals". The report itself flags these as quoted stdout "not persisted to any file in the run dir". Critic re-ran the thesis's signal_py on era=train mr_edge 5m via load_data.load_ohlcv and reproduced them exactly: 20304 bars each, values [-1, 0, 1], nonzero 196/179/253 (research/swarm/runs/dryrun-2026-09-16/critic/signal_sanity_train.txt). Numbers are correct; the path was missing at report time and now exists.
2. REPORT.md line 20 — "budget exhausted at 200/200 before the analyst started". The "200/200" figure appears in no file in the run dir (grep "200/200" hits only REPORT.md:20); the thesis `evidence` field says only "WebSearch budget was exhausted for this session (0 searches possible)". Unsourced number; should be dropped or attributed to the orchestrator's run context explicitly.
3. REPORT.md line 11 — p_star(150) = 0.5383333333333333, time_to_verdict_weeks(4) = 12.5, position_notional() = 200.0, lot_check BTC 2 lots @ 77.74 / ETH 8 @ 24.9738 / SOL 197 @ 1.0143: cited to research/swarm/lib/fee_math.py and re-verified by critic this turn (same outputs). Not a defect.

## (c) Contradictions between artifacts and the report

1. none material. Checked: gate_rejections.json dead_row 6 and reason text match REPORT.md line 11 quotes verbatim; gate_kept.json is `[]` as stated (line 7); thesis spec (BTC/ETH/SOL, 5m, tp 150 / sl 150, max_hold_bars 24, expected_trades_per_week 4) matches line 11; DEAD_LIST.md line 18 = row 6, line 92 = row 80, line 15 = row 3 as cited; thesis `evidence` (arXiv 2507.08744 unrelated, coinglass placeholders "$0"/"undefined") matches line 20. No out.json, audit.json, committee/*.json or out.robust_*.json exist to contradict.
2. Minor wording: REPORT.md line 11 quotes row 6 as "vol-fade with extra steps" (lower-case v); DEAD_LIST.md line 18 reads "Vol-fade with extra steps". Case only.

## (d) Thesis fields — nearest_dead_rows / why_different / evidence

1. theses/dryrun_forced_flows_delever_fade.json `nearest_dead_rows`: non-empty (rows 6, 80, 3). `why_different` on all three is "NOT different" — an explicit admission of relabel, by design for the dry run, not a generic boilerplate; it is what the gatekeeper correctly acted on (gate_rejections.json).
2. theses/dryrun_forced_flows_delever_fade.json `evidence`: contains NO externally sourced number ("NO external number was read from any source"; the only figures are the coinglass placeholders "$0" and "undefined"). Fails STANDARDS #2 (at least one external source URL with the actual number that source reports). The gate rejected on row 6 before reaching step 2, so this second, independent failure is recorded here only.
3. Minor: thesis `prediction` and `spec.doa_line` write p*(150) as "0.5383" (truncated) while fee_math.p_star(150) returns 0.5383333333333333 (REPORT.md line 11; re-verified). Rounded transcription of a lib output, not hand arithmetic; the report uses the full value.

## (e) Holdout access

1. grep -rn "COMMITTEE-HOLDOUT-READ\|era=\"holdout\"\|era='holdout'\|era=\"all\"\|--era holdout\|--era all" → exactly one hit: research/swarm/runs/dryrun-2026-09-16/mandate.md:67, which is the mandate's own prohibition sentence ("No seat passes era=\"holdout\" or era=\"all\" ..."). It is prose stating the rule, not code or a command that reads holdout. No era-suffixed outputs (out.holdout.json / trades.holdout.csv) exist. Critic's own re-run used era="train" only (critic/signal_sanity_train.txt, date range ends 2026-08-10 11:55 UTC, consistent with the DATA.md train boundary). Assessed: no holdout access occurred; the literal grep hit is reported here for the record.

## (f) Frozen spec / signal.py sha verification

1. none — glob research/swarm/runs/dryrun-2026-09-16/specs/*.frozen.json is empty; registrar.verify output: `{}`. The registrar stage was never invoked (REPORT.md line 16), so there is nothing to verify and nothing to fail.

## (g) Daily-ROI target or hand-computed statistic in the report

1. none — grep -i "roi|% per day|daily target|/day" on REPORT.md returns nothing. Every statistic in REPORT.md (p*, time-to-verdict, notional, lot counts) is attributed to research/swarm/lib/fee_math.py and re-verified this turn; n / net bps / CI95 / WR / BH / tp±20% are all stated as "not run" (line 11, 17-19), not estimated.

## Other process notes (not in a-g)

1. STANDARDS #15 reconcile: no dated line for this run exists in research/swarm/kb/LESSONS.md (its 2026-09-16 lines 3-7 all describe the v1 swarm, not this dry run) and no DEAD_LIST/SURVIVORS row was added. REPORT.md line 22 defers this to the orchestrator; it remains open.
