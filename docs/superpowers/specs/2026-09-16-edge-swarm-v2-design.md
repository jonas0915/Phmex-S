# Edge Swarm v2 — "the desk" — design

Date: 2026-09-16. Owner order (12:44 PM PT): "go" on the four-stage research → build → paper → (human) live pipeline, designed for a **$200** account.
Supersedes the v1 swarm (`docs/2026-09-16-edge-swarm-v1/`, 0 of 8 candidates, 5 launch attempts, ~11M tokens).

## 1. Problem

v1 failed on process, not on effort:

- Ideation was pattern-named ("compression breakout", "OFI rollover"), not mechanism-named, so 8 of 8 candidates were relabels of dead-list families.
- Ideation agents *did* run real screens on real data (six folders, bootstrap CIs, ~124k bars) but the only handoff between phases was a prose `summary`, so every screen was discarded and refuters judged on precedent plus fee arithmetic. Report admits "every rejection is arithmetic and precedent, not a fresh empirical test".
- Headline numbers ("needs 56.5% WR") appeared with no derivation; the same figure was asserted for two unrelated ideas.
- Agents had to *discover* the data and each hand-rolled its own statistics (the record has a documented bootstrap diff-CI bug that this invites).
- Nothing persisted between runs. The swarm cannot get better because it has no memory.
- Every prior search — v1 and all of 2026 — was intraday. The multi-day / event-driven space the owner's scope allows was never touched.

## 2. Goal and non-goals

**Goal.** A repeatable research desk that (a) starts from mechanisms, (b) tests every thesis on data before anyone opines, (c) hands artifacts not prose between phases, (d) leaves a richer knowledge base after every run, and (e) carries a survivor through slot build and paper forward test, stopping at the owner's gates.

**Success for run 1 is an honest run**: every candidate reaches a real screen with a CI; every rejection cites data or a dead-list row; no orphaned artifacts; knowledge base updated. A survivor is upside, not the bar. The record (76 dead families, lifetime ≈ −$119, paper repeatedly failing to predict live) is the prior; the process does not change the market, it changes whether the answer can be trusted.

**Non-goals.** No live trading by the swarm, ever. No re-arming of demoted books (main live, ST2.0, 5m_MR live, Donchian live). No internet sweep in run 1 (separate optional workflow later). No changes to bot trading code outside a new, flag-gated, kill-file-reversible slot.

## 3. Capital assumption: $200

Break-even math is in bps and does not move with capital: round-trip cost `c = 11.5 bps` (0.07% maker-taker fees + 4.5 bps measured adverse selection), so required WR for a symmetric target `x` is `p* = (x+c)/(2x)` (25 bps → 73.0%, 50 → 61.5%, 100 → 55.8%, 300 → 51.9%, 1000 → 50.6%). What $200 changes vs $87: BTC's $77.74 lot is one lot at ~$20 margin (10x), a single SL no longer trips the daily halt, and two paper slots can run at honest sizing. What it does not buy vs $500: 3–4 concurrent slots or cross-sectional baskets. The desk filters in bps first, then checks dollar sizing against $200 and per-symbol lot minimums.

## 4. Architecture

```
Phmex-S/research/swarm/
  kb/            knowledge base — mandatory reading, version-controlled
    CONSTRAINTS.md   fees, p* table, $200 sizing, lot mins, bot execution reality
    DEAD_LIST.md     consolidated: v1 01_dead_list.md (76 rows) + memory reference_* kills
    STANDARDS.md     pre-reg, DOA line, diff-CI, forming-bar, holdout, BH, fill realism
    DATA.md          every dataset + engine by path, era boundaries, schema
    LESSONS.md       swarm's own process lessons; appended by the reconciler every run
  lib/           shared Python — no agent hand-rolls stats
    bootstrap_ci.py  correct independent-resample diff-CI + single-sample CI
    fee_math.py      p*, net bps after c, time-to-verdict at $200 sizing, lot check
    load_data.py     loaders for mr_edge cache (35 sym, 1m/5m/1h, 6/1–9/2/2026),
                     400d 1h parquet (19 sym, 6/27/2025–8/1/2026), funding JSON,
                     ccxt public OHLCV fetch (Phemex) for longer daily history
    screen.py        pre-registered screen scaffold: spec in → trades + JSON out;
                     enforces era split, closed-vs-forming bar flag, fee application
    registrar.py     freezes a thesis spec to file with sha256 before any data read
  runs/<YYYY-MM-DD-HHMM>/   one dir per run
    mandate.md, theses/*.json, specs/*.frozen.json, screens/<id>/{screen.py,out.json,audit.json},
    committee/*.json, REPORT.md, CRITIC.md
  workflows/
    desk.js        the Workflow script (research stage)
    build.js       the build stage (invoked only on a committee pass, after owner go)
```

Everything under `research/swarm/` except `runs/*/screens/**/data*` is committed to the Phmex-S GitHub repo. Run dirs are small (JSON + markdown + short scripts); raw data is never copied into a run dir.

## 5. Research stage — `desk.js`

Phases, in order. Effort levels in brackets. Agent counts are caps.

1. **Desk brief** [1, medium]. Reads all of `kb/`. Writes `mandate.md`: capital $200, minimum net edge (bps after `c`), horizons in scope (intraday through multi-day; event-driven explicitly in scope), execution reality (5-min poller, maker entries, 60s book snapshots, Mac may sleep — slow horizons preferred), symbol universe, era boundaries, the list of dead-list row numbers most likely to be relabeled.

2. **Analysts** [7, parallel, medium]. One lens each, framed as a *market participant*, not an indicator: forced flows (liquidations, funding settlement, listings/delistings); informed vs uninformed flow (cross-venue lead-lag, on-chain); dealer/market-maker inventory; session and calendar structure across venues; volatility structure and term behaviour; cross-asset spillover (BTC→alts, equities/FX→crypto); literature (opens the 5 papers v1 fetched, runs `sweep/leadlag/local_check.py`). Each produces ≤2 theses as JSON matching a strict schema:
   `id, mechanism, counterparty (who pays and why they are forced to), prediction (falsifiable), nearest_dead_rows [{row, why_different}], spec {universe, timeframe, era, entry, exit, tp_bps, sl_bps, max_hold, closed_bar: true, expected_trades_per_week, doa_line}`. An analyst may run exploratory probes but must label them exploratory; they do not count as the screen.

3. **Gatekeeper** [1, high]. Dedup + relabel check against `DEAD_LIST.md`, row-cited. Passes ≤5 theses with a genuinely new mechanism. Every rejection is written to `runs/<id>/gate_rejections.json` with the row and reason.

4. **Registrar** [deterministic script, no agent]. `registrar.py` writes each surviving spec to `specs/<id>.frozen.json` with sha256 and timestamp. Train/holdout split fixed here: holdout = final 25% of the dataset's time range for the chosen timeframe (for the mr_edge cache that is ≈ 8/10–9/2/2026; for the 400d cache ≈ 4/24–8/1/2026). Holdout is not readable by the screen phase — `load_data.py` refuses holdout rows unless called with the committee token.

5. **Screen** [1 per thesis, ≤5, high]. Runs the frozen spec via `screen.py` on train era only, closed-bar, fees = `c`, using `lib/`. Output `out.json`: `n, net_bps_mean, ci95 [lo,hi], wr, p_star, trades_per_week, time_to_verdict_weeks (n≥50 & CI excl 0 at $200 sizing), lot_check, script_sha`. **No `out.json`, no candidate.** A screen may not alter the frozen spec; if the spec is unrunnable the screen fails with a reason and the thesis dies.

6. **Audit** [1 per screen, high]. Re-runs `screen.py` from the frozen spec, diffs `out.json`, checks: lookahead (any `iloc[-1]`/forming-bar use), fee application, era boundary respected, holdout untouched, BH adjustment across the run's ≤5 screens. Recomputes `p*` and time-to-verdict independently from `fee_math.py`. Writes `audit.json` with `CONFIRMED | REFUTED | RERUN_MISMATCH` and the numbers.

7. **Risk committee** [2, high: economics, statistics]. Sees only screens with `CONFIRMED` audit *and* train CI excluding 0. Judges from `out.json`/`audit.json` only. Economics: observed WR vs `p*`, sizing at $200 vs lot minimums, feasibility on the 5-min poller, funding exposure at the hold horizon. Statistics: n, CI width, multiplicity, regime coverage across the train era, fragility to ±1 parameter step (one registered robustness read, not a grid). **Both must pass.** Output `committee/<id>.json`.

8. **Synthesis + Critic + Reconciler** [3, high]. Writer produces `REPORT.md` (verdict first, one paragraph per thesis, every number linked to its file). Critic hunts orphaned artifacts (any `screens/*/` without a citation in the report), unsourced numbers, and contradictions between gate/screen/audit/committee. Reconciler appends every screened thesis — pass or fail — as a new row in `kb/DEAD_LIST.md` (or `kb/SURVIVORS.md`), and every process failure as a dated entry in `kb/LESSONS.md`. This is the learning loop.

**Pipelining.** `pipeline()` so each thesis flows gate → registrar → screen → audit as soon as it is ready; committee waits for all audits (needs BH across the set).

**Budget and discipline.** Run alone, never concurrent with another workflow (v1's four deaths were a shared rate ceiling). Caps: 7 analysts, ≤5 screens, ≤5 audits, 2 committee, 3 closing ≈ 22–23 agents. Target ≤2M tokens, 20–30 min. Every agent prompt embeds the *content* of `kb/CONSTRAINTS.md` and `kb/STANDARDS.md` (not just paths) and the path to `DATA.md`/`DEAD_LIST.md`.

## 6. Build stage — `build.js` (only after a committee pass and owner "go")

Input: one `committee/<id>.json` PASS plus its frozen spec. Output: a paper slot on the bot, per the framework recipe (`docs/2026-09-16-edge-swarm-v1/02_framework_audit.md` §recipe):

1. **Pre-registration doc** [1]: `docs/superpowers/specs/<date>-<id>-prereg.md` — what the slot does, era hygiene, frozen verdict line (`verdict_n`, kill rule: at n ≥ verdict_n, net ≤ 0 → KILL; plus a dollar loss cap), anti-fishing clause, prior from the train screen. Holdout read happens here, once, and is recorded in the doc.
2. **Slot implementation** [1 implementer + 1 reviewer]: bespoke `<id>_slot.py` mirroring `donchian_slot.py`; `_evaluate_<id>` in `_evaluate_all_slots`; `EXPERIMENTS` entry + `grade_<id>` in `scripts/lab_adjudicator/adjudicate.py`; dashboard/report propagation per CLAUDE.md; `tests/test_<id>_slot.py` mirroring `tests/test_donchian_slot.py`; rollback `touch .kill_<id>`. TDD; full suite must pass (baseline 1005 pass / 1 ordering-only fail).
3. **Stop.** Nothing restarts. Owner runs `/pre-restart-audit` and says "go". The bot is currently wound down; starting it for a paper slot is the owner's call and the wind-down doc's restore steps apply.

## 7. Paper stage and live

Paper slot runs on the live feed at honest $200-scaled sizing, `.paper` sentinel, graded daily at 6 AM PT by the existing adjudicator → Telegram. Kill line enforced automatically. If it survives to `verdict_n` with net > 0 on its pre-registered line, the numbers are surfaced to the owner. **Funding it live is a human decision** — the record says forward test is the only adjudicator and paper has lied before; that step is not automated.

## 8. Records in git (owner request, 12:44 PM PT)

`research/swarm/kb/` and `runs/` are committed and pushed after every run so the knowledge base is durable and readable from any machine. Session preflight adds a `git pull` of Phmex-S before reading `kb/`. Multi-GB market data (l2_ticks, flow_capture, archive tarball) is **not** git-appropriate (100 MB file cap, repo size limits) and stays local / external drive; the disk audit running in parallel will say what can actually free space.

## 9. Testing the desk itself

- `lib/` has pytest coverage: `bootstrap_ci` against a known-answer case (and the documented sort-first bug as a regression test), `fee_math.p_star` against the table in §3, `load_data` holdout refusal, `registrar` sha stability, `screen.py` on a synthetic series with a planted edge and a planted lookahead (must catch the lookahead).
- A dry run of `desk.js` with `MAX_ANALYSTS=1, MAX_SCREENS=1` on a deliberately dead thesis (e.g., a 5m_MR relabel) must end with the gatekeeper rejecting it row-cited and the reconciler writing a LESSONS entry — proving the plumbing before spending a full run.

## 10. Out of scope / later

Internet sweep v2 (same artifact discipline, separate script). Scheduled autonomous runs. Streaming order book. Anything requiring >$200 (funding spread parked at $2K).
