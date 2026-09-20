# CRITIC.md — completeness review of run 2026-09-20-0300

Method: read REPORT.md in full; listed the run dir recursively (`find research/swarm/runs/2026-09-20-0300 -type f`); re-opened every `out.json`/`audit.json`/`gate_kept.json`/`gate_rejections.json`/`theses/*.json`/`specs/*.frozen.json`/`exploratory/*` file rather than trusting REPORT.md's prose; ran `registrar.verify` on all 5 frozen specs; grepped for holdout-access strings; grepped DEAD_LIST.md for every row number cited.

## a) screens/<id>/, exploratory/, or committee/ artifacts not cited in the report

REPORT.md never once contains the string "exploratory" (confirmed by grep). Every file under `exploratory/` therefore exists but is not cited by path anywhere in REPORT.md, even though some of them are the actual evidentiary basis for claims the report repeats via `gate_kept.json`/thesis-file paraphrase:

1. `research/swarm/runs/2026-09-20-0300/exploratory/forced_flows/probe_adl_reversal.py` — underlies the forced_flows_adl_winner_reversal thesis's "97th-pct rolling trigger" claim (cited only inside `theses/forced_flows_adl_winner_reversal.json`, never in REPORT.md).
2. `research/swarm/runs/2026-09-20-0300/exploratory/forced_flows/probe_dayclose_relever.py` — underlies `gate_kept.json`'s "probe_dayclose_relever.py used long_1h train only" claim for forced_flows_daily_relever_flow; REPORT.md repeats none of this path.
3. `research/swarm/runs/2026-09-20-0300/exploratory/informed_flow/probe_btc_alt_lag_freq.py`
4. `research/swarm/runs/2026-09-20-0300/exploratory/informed_flow/probe_btc_alt_lag_freq.out.txt` — these two underlie informed_flow_btc_alt_lag's frequency claim; unused in REPORT.md.
5. `research/swarm/runs/2026-09-20-0300/exploratory/literature/btc_threshold_probe.py`
6. `research/swarm/runs/2026-09-20-0300/exploratory/literature/btc_threshold_probe_output.txt` — cited inside `theses/literature_btc_alt_drift.json`'s evidence field (the 90th-pct/64.4bps/17-per-week figures) but that thesis is only summarized in REPORT.md's gate-rejected list, and the path is dropped there.
7. `research/swarm/runs/2026-09-20-0300/exploratory/literature/local_check_copy.py`
8. `research/swarm/runs/2026-09-20-0300/exploratory/literature/local_check_output.txt`
9. `research/swarm/runs/2026-09-20-0300/exploratory/literature/signal_causality_test_copy.py`
10. `research/swarm/runs/2026-09-20-0300/exploratory/owner-record/probe.py` — the actual script that produced `theses/owner_record_probe.json`'s numbers; REPORT.md cites `theses/owner_record_probe.json` itself (line 15) but never this underlying probe script.
11. `research/swarm/runs/2026-09-20-0300/exploratory/vol_structure/smoke_test_signal.py`

Also uncited by path anywhere in REPORT.md, despite existing for all 4 completed screens: `screens/<id>/trades.csv` (4 files) and `research/swarm/runs/2026-09-20-0300/specs/<id>.frozen.json` (5 files — confirmed by `grep -n "trades.csv\|specs/\|.frozen.json" REPORT.md`, which returns zero hits for any of these paths). The report cites `out.json` and `audit.json` for each screened thesis but never the frozen spec or the trade-level CSV that STANDARDS #11 treats as the artifact of record.

No `committee/*.json` exists anywhere under the run dir — consistent with the report's own "not run"/"never ran" language (REPORT.md lines 9, 11, 13, 15, 17, 31), so this is not an omission, just confirmed absent.

## b) numbers in the report without a file path next to it

Five separate claims in REPORT.md are attributed to "the run context" / "run-context" — a source that does not exist as a file anywhere in the run directory (confirmed: `find research/swarm/runs/2026-09-20-0300 -maxdepth 1` shows only `REPORT.md`, `gate_kept.json`, `gate_rejections.json`, `launch_args.json`, `mandate.md`, `exploratory/`, `screens/`, `specs/`, `theses/` — no `run_context.json`, `context.json`, or similarly named file). Per STANDARDS #11 ("every number in a report links to a file"), these are uncitable:

1. Line 5: `` run-context `screened`/`committee_passed` arrays `` — no file.
2. Line 9: "`committee_passed` is empty in the run context" — no file.
3. Line 13: `audit_verdict: "REFUTED"` attributed to "the run context" for informed_flow_btc_alt_lag — no file (the report does flag this as an unbacked annotation, which is good practice, but the underlying source is still not a citable artifact on disk).
4. Line 17: "the vol_structure lens's own run-context notes say both WebFetch attempts on the primary Springer/ScienceDirect papers were blocked (403/303)…" — this is a substantive claim (a sourcing-verification discrepancy against `gate_kept.json`'s "confirmed independently … via WebFetch/WebSearch") with no file path at all, so it cannot be independently re-verified from artifacts on disk.
5. Line 31: "`committee_passed` is empty in the run context" (repeated).

All other numeric claims in the "Screened theses" section (n, net_bps_mean, ci95, wr, p_star) do carry file paths and were spot-checked against `out.json`/`audit.json` in this review — they match exactly (see section c).

## c) contradictions between gate_rejections.json, theses/*.json, out.json, audit.json, committee/*.json, out.robust_*.json and the report

None found. Re-opened all 4 `out.json`/`audit.json` pairs and diffed their `n`, `net_bps_mean`, `ci95`, `wr`, `p_star` fields against REPORT.md's prose — exact matches in every case (e.g. forced_flows_daily_relever_flow: out.json `net_bps_mean=-34.605118794131904` / `ci95=[-45.40469719898698,-23.184164343209346]` / `wr=0.3836477987421384` vs REPORT.md line 11 "-34.61, ci95=[-45.40, -23.18] … wr=38.36%" — matches to rounding). `gate_kept.json` and `gate_rejections.json` reasons match REPORT.md's paraphrase of ranks, evidence grades, and dedup logic. No `committee/*.json` or `out.robust_*.json` exist to contradict (see a). `informed_flow_btc_alt_lag`'s frozen spec (`specs/informed_flow_btc_alt_lag.frozen.json`) verifies `True` via `registrar.verify` and its embedded `thesis.signal_py` field already contains the same malformed docstring text found in `screens/informed_flow_btc_alt_lag/signal.py` — i.e. the corruption was baked in at freeze time, not introduced by a later copy step; this is consistent with, not contradictory to, the report's account.

## d) any thesis whose nearest_dead_rows is empty or why_different generic, or evidence has no number

None. Checked `nearest_dead_rows` and `evidence` on all 9 thesis files (5 gate-kept + 4 gate-rejected): every thesis has 2–5 `nearest_dead_rows` entries, each with a specific, mechanism-level `why_different` string (not a generic "different asset" or "different timeframe" statement), and every `evidence` field contains at least one concrete number (coefficients, t-stats, AUCs, dollar figures, percentages). Cross-checked the DEAD_LIST.md rows actually cited (2, 3, 5, 6, 7, 13, 18, 20, 33, 76, 80, 82, 84, 105, 106, 107) — all exist at the cited descriptions and match the mechanism each thesis distinguishes itself from.

## e) holdout access

`grep -rn "COMMITTEE-HOLDOUT-READ\|era=\"holdout\"\|era='holdout'\|era=\"all\"\|--era holdout\|--era all" research/swarm/runs/2026-09-20-0300` returns zero hits. No holdout-access process failure found. Also spot-checked the cross-dataset holdout caveat (STANDARDS #6): `forced_flows_daily_relever_flow` and `vol_structure_volscale_continuation` both use `long_1h` (train_span ends 2026-04-23 in both `out.json` files) and `exploratory/forced_flows/probe_dayclose_relever.py` explicitly notes it "touch[es] no mr_edge data at all" — consistent, no leakage found.

## f) frozen spec / signal.py sha verification

```
python3 -c "from research.swarm.lib import registrar as r; import glob; print({p: r.verify(p) for p in glob.glob('research/swarm/runs/2026-09-20-0300/specs/*.frozen.json')})"
```
Output:
```
{'research/swarm/runs/2026-09-20-0300/specs/owner_record_liq_cascade_continuation.frozen.json': True,
 'research/swarm/runs/2026-09-20-0300/specs/vol_structure_volscale_continuation.frozen.json': True,
 'research/swarm/runs/2026-09-20-0300/specs/forced_flows_adl_winner_reversal.frozen.json': True,
 'research/swarm/runs/2026-09-20-0300/specs/informed_flow_btc_alt_lag.frozen.json': True,
 'research/swarm/runs/2026-09-20-0300/specs/forced_flows_daily_relever_flow.frozen.json': True}
```
All 5 frozen specs verify. Note: `informed_flow_btc_alt_lag`'s frozen spec verifies fine even though its `screens/informed_flow_btc_alt_lag/signal.py` fails to import — the sha covers the frozen spec json's own integrity (including its embedded, already-broken `thesis.signal_py` text), not a claim that the code is syntactically valid Python. This is not a contradiction of REPORT.md, which correctly describes the failure as a `SyntaxError` on import, not a sha-verification failure.

## g) daily-ROI target or hand-computed statistic in the report

None. `grep -n "daily-ROI\|10%\|ROI per day\|% per day" REPORT.md` returns zero hits. All win rates, p*, CI, and time-to-verdict figures quoted in REPORT.md are copied verbatim from `out.json`/`audit.json` `numbers` blocks (confirmed by direct diff in section c) rather than computed in prose. `mandate.md` §1 explicitly records the owner's +10%/day aspiration as "never a bar," "never written anywhere in this run as a daily-ROI target," and REPORT.md complies — it is not mentioned anywhere in REPORT.md.

## Summary

REPORT.md's factual claims (n, net_bps_mean, ci95, wr, p_star, verdicts, gate ranks, dead-row citations) all check out against the underlying artifacts — no numeric contradictions found (c, d, f, g clean; e clean). The two real gaps are citation hygiene, not fabrication: (a) 11 `exploratory/` files plus every `trades.csv` and `specs/*.frozen.json` exist but are never cited by path in REPORT.md, and (b) 5 claims (including one substantive sourcing-discrepancy allegation on vol_structure_volscale_continuation) are attributed to an unfilable "run context" that has no corresponding artifact anywhere in the run directory.
