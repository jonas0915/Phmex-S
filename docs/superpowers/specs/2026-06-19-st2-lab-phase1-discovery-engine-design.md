# Phase 1 — ST2.0 Lab Discovery Engine (Honest Hypothesis Generation)

**Date:** 2026-06-19
**Status:** Design — pending review
**Depends on:** Phase 0 (`ob:null` capture fix — shipped). Approach A (honest AI lab).
**Unblocks:** Phase 2 (self-closing paper loop), Lab Dashboard.
**Hard rule:** never imports `bot.py`, never touches live. Offline only.

## Goal

Turn the existing `scripts/st2_lab/` from a *100%-fill sandbox optimizer* (which
produces artifacts — sandbox +0.31/trade vs live −0.14/trade) into an **honest
discovery engine**: it generates candidate entry signals over the 211K-snapshot
dataset and ranks them on *realistic* fitness with anti-overfitting guards, so that
what survives is a genuine hypothesis worth forward-testing — not a deflated-Sharpe
mirage.

Phase 1 produces **ranked, evidence-backed hypotheses**. It does NOT promote them to
paper (Phase 2) or to live (human gate). Its whole job is to stop generating fakes.

## Why this shape (the documented constraints)

- Backtesting this data reliably makes artifacts; the better the headline, the more
  suspicious (edge-hunt-exhaustion). → ranking must be adverse-fill-aware and
  multiple-testing-corrected, never naive.
- ST2.0's edge is maker-only and the fill wall is structural (~43% fills, adversely
  selected, queue position unrecorded). → a 100%-fill objective is fiction; the
  objective must model adverse fills.
- The vol-fade death: "looked OOS +0.26% on ONE split; independent re-derivation
  full-sample −0.187%, Sharpe −2.45." → a single 70/30 split is not enough; need
  walk-forward + a deflated-Sharpe / multiple-testing gate that accounts for trials.
- Forward paper-confirm on real fills is the ONLY adjudicator. → Phase 1 output is a
  hypothesis, explicitly labeled not-truth, handed to Phase 2.

## What exists today (build on, don't rebuild)

- `evaluator._replay` (naive 100%-fill) and `evaluator._replay_adverse(cfg, by_symbol, af)`
  — the adverse-fill model already exists (cites arxiv 2407.16527), wired through
  `evaluate(cfg, by_symbol, adverse=...)`. Currently the loop always calls it with
  `adverse=None`. `config.ADVERSE_FILL` exists but `enabled=False`.
- `dataset.chronological_split(by_symbol, train_frac=0.7)` — the single split to
  replace with walk-forward.
- `proposer.propose`, `diagnostics.analyze_failures` / `propose_filter_codes` —
  existing candidate generators (param neighbors + quantile loss-cluster filters).
- `safe_exec.py` — AST-sandboxed filter execution (keep; all generated conditions
  must pass it).
- `real_trades.py`, `fills.py` — real-outcome and measured-fill ingestion.
- `champion.py` / `champion.json` — recursive state + lineage + history.

## New components (added to `scripts/st2_lab/`)

### 1. `labeler.py` — adverse-fill-aware labeled examples
Builds the supervised dataset the model and the ranker score against.
- Input: `flow_capture.jsonl` (211K snapshots, ob+flow) + real trades.
- For each snapshot, simulate an ST2.0-style maker entry and label the outcome
  using the **adverse-fill model** (`_replay_adverse` logic): did a resting maker
  order fill within the window, and what is the net (fees + adverse selection)? An
  unfilled signal is dropped, not counted as a free win — this is the core honesty.
- Output: labeled examples `{features…, filled: bool, net_roi: float}` plus a
  `tradeable` flag (ST2.0-like conditions). Real trades (now carrying `ob` post
  Phase 0) are labeled with their TRUE realized PnL and union'd in, weighted higher.
- Calibrate the adverse-fill params (`maker_edge_pct`, `fill_window_snaps`) against
  the measured ~43% live fill rate from `fills.py`.

### 2. `features.py` — feature engineering
Derives a richer feature set from the snapshot stream (absorption is one input, not
the signal): CVD acceleration, bid/ask depth ratios, multi-snapshot deltas
(imbalance/price momentum), spread regime, realized-vol regime, time-of-day.
Deterministic, pure functions; every feature documented with its definition.

### 3. `walkforward.py` — windowed validation (replaces single split)
- Expanding or rolling windows: train `[0,t)`, test `[t, t+w)`, step by `w`; ≥5
  windows over the 40-day span.
- **Purge + embargo**: drop training/label rows whose forward-return horizon
  (15 min) overlaps the test window boundary — prevents label leakage.
- A candidate's OOS score = aggregate over test windows; also record the per-window
  vector (a candidate positive in only 1 window is regime-luck, not edge).

### 4. `stats.py` — anti-artifact statistics
- **Deflated Sharpe Ratio** (Bailey/López de Prado): deflate a candidate's Sharpe by
  the number of trials evaluated (tracked in `champion["history"]`) and the
  non-normality of returns. A candidate must clear the deflated bar, not the naive one.
- **Multiple-testing correction**: Benjamini–Hochberg across the candidate batch so
  the accepted set controls false-discovery rate.
- **Bootstrap diff-CI (correct form)**: for `mean(candidate) − mean(champion)`,
  resample the two arrays INDEPENDENTLY each iteration and difference the draw-order
  means, sorting only at the end (per the documented bug — sorting each mean-array
  first makes the CI ~2.4× too narrow and manufactures significance).
- Unit-tested against known values.

### 5. `model.py` — hypothesis-ranker (Approach A "discover new signals")
- A **regularized** model (start: L2 logistic / shallow GBDT, depth ≤3) over the
  `features.py` set, trained on `labeler.py` outputs, predicting P(favorable net
  fill). Heavy regularization + small capacity by design — the dataset is
  screening-grade, not training-grade.
- The model is a **generator, not a deployable**: its high-signal splits are emitted
  as candidate filter/param conditions (AST-safe) that flow through the SAME
  walk-forward + adverse-fill + deflated-Sharpe gate as every other candidate. No
  model object is ever shipped to live.

### 6. `loop.py` changes (orchestration)
Replace the single-split evaluation with: generate candidates (proposer + diagnostics
+ model) → label (adverse-fill) → walk-forward evaluate → `stats.py` gate
(deflated-Sharpe + BH + bootstrap CI) → rank survivors → update `champion.json` with
the per-window evidence and trial count. Keep determinism, the `tried`-set dedup, the
`.halt` kill-switch, and the human-gated proposal output.

## Data flow

```
flow_capture.jsonl (211K, ob+flow)  ─┐
real trades (TRUE pnl, now w/ ob)  ──┼─> labeler.py (adverse-fill labels)
                                      │
candidate conditions  <── proposer + diagnostics + model.py (features.py)
        │
        └─> walkforward.py (purged windows) ─> evaluator (_replay_adverse)
                  └─> stats.py (deflated Sharpe, BH, bootstrap diff-CI)
                        └─> ranked survivors + evidence ─> champion.json / proposals
```

## Output contract (consumed by Phase 2 + dashboard)

Each surviving hypothesis records: config (params + AST filters), adverse-fill-adjusted
expectancy, per-window OOS vector, deflated Sharpe, trials-to-date, fill-rate
assumption, and an explicit `status: "hypothesis — forward-confirm required, NOT
truth"`. Written to `champion.json` lineage + an enriched `docs/fix-proposals/` entry.

## Scope / non-goals

- **No paper-slot promotion** (Phase 2). No live changes. No dashboard (separate unit).
- Does not change the live ST2.0 signal or any `bot.py` trading logic.
- The model is a screener; the spec deliberately does NOT claim its output is
  trustworthy without forward-confirm. If walk-forward + deflated-Sharpe leave no
  survivor, "no edge found this round" is a valid, expected, honestly-reported result.

## Testing

- `stats.py`: deflated Sharpe against published worked examples; BH on synthetic
  p-values; bootstrap diff-CI width sanity (the correct independent-resample form vs
  the buggy comonotonic form, asserting the documented ~2.4× difference).
- `walkforward.py`: purge/embargo removes exactly the overlapping horizon rows; no
  test-window row appears in any train set.
- `labeler.py`: unfilled signals are dropped (not counted as wins); fill rate on a
  synthetic stream matches the configured adverse params; real trades labeled with
  true PnL.
- `features.py`: each feature deterministic and correct on a tiny fixture.
- End-to-end: one `loop.py` iteration on a fixture dataset runs the full
  generate→label→walk-forward→stats→rank pipeline and is deterministic across runs.

## Risks

- **Data is screening-grade, not training-grade.** Mitigation: small/regularized
  model, walk-forward, deflated-Sharpe, and the non-negotiable forward-confirm gate.
  The spec's honesty contract makes "no edge" an acceptable outcome.
- **Adverse-fill model is itself an assumption** (queue position is unrecorded).
  Mitigation: calibrate to measured fill rate; treat sandbox as *relative ranking*
  only; Phase 2 real fills are the truth.
- **Compute**: walk-forward × model training is heavier than today's loop. Mitigation:
  cap candidates/iteration, keep the daily launchd cadence, profile and adjust.

## Decomposition note

Phase 1 is itself sizable. Suggested build order within it (each its own plan unit):
1. `stats.py` + `walkforward.py` (the honest evaluation backbone) wired into `loop.py`,
   adverse-fill turned ON for ranking — this alone makes the *current* search honest.
2. `labeler.py` + `features.py` (richer labeled dataset).
3. `model.py` (the ranker) feeding candidates into the now-honest pipeline.

Step 1 delivers value immediately (stops the artifact ranking) even before the model.
