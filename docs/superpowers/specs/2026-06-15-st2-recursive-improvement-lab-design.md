# ST2.0 Recursive Improvement Lab — Design Spec

**Date:** 2026-06-15
**Status:** Approved design, pending spec review → implementation plan
**Author:** Claude (with Jonas)

## 1. Purpose

A recursive, self-improving loop that autonomously evolves the **ST2.0** strategy
(book×tape absorption short) toward a real edge. Each iteration analyzes the current
champion, proposes mutations (params and/or entry-filter code), ranks them, carries the
winner forward, and repeats — fully autonomous **inside an isolated lab**, with human
approval required only where generated code would enter the live trading process.

ST2.0 today: 22 trades, ~32% WR, negative in both live (−$1.89/10) and paper (−$4.03/12),
maker fill rate 43%. **No proven edge.** The loop must therefore treat "no improvement
found" / "retire it" as a first-class, likely outcome — not optimize noise into a false win.

## 2. Goals / Non-Goals

**Goals**
- Autonomous recursive iteration over ST2.0 params **and** entry-filter logic.
- Honor documented R&D: backtester used for **relative ranking only**, never as truth
  (`reference_edge_hunt_exhaustion`: "backtesting this data only makes artifacts; forward-
  testing is the only adjudicator").
- Forward-test (paper, live data stream) is the **truth gate** before any live proposal.
- Reuse existing human-gated infra (`proposals_digest.py`, Telegram, `/pre-restart-audit`).

**Non-Goals**
- No autonomous changes to the **live** ST2.0 slot (params or code). Ever.
- No autonomous loading of generated **code** into the live `bot.py` process.
- No absolute-PnL forecasting from the sandbox (relative ranking only).
- Not a general multi-strategy framework in v1 — ST2.0 only.

## 3. Hard Invariants (safety)

1. **Isolation:** the lab is a standalone process under `scripts/st2_lab/`. It never
   imports into, mutates, or restarts `bot.py`. It reads recorded data + ST2.0 paper
   results read-only.
2. **The code-into-live gate:** autonomy ends exactly where generated code would run in
   the live trading process. Params-only champions may auto-advance to a real paper slot;
   **filter-bearing** champions require human audit (`/pre-restart-audit`) before they run
   as a real paper slot, and all **live** promotions require explicit approval.
3. **Sandboxed codegen:** generated filter functions are pure, single-signature
   (`def f(ctx) -> bool`) over a whitelisted input set; executed under a restricted sandbox
   (AST whitelist, no imports, no IO, wall-clock timeout). Unsafe code is rejected, logged,
   never run.
4. **Truth gate:** a sandbox champion is a *hypothesis*. Nothing reaches a live proposal
   without forward-confirmation on the real data stream over a minimum sample.
5. **Kill switch:** `st2_lab/.halt` flag stops the lab immediately.
6. **Honesty:** every champion is tagged `sandbox-only until paper-confirmed`; the loop
   reports "no improvement" explicitly and never inflates sandbox results into truth.

## 4. Architecture

Standalone package `scripts/st2_lab/`, scheduled by a new launchd job
`com.phmex.st2-lab.plist`. Five units, each independently testable:

### 4.1 Champion store — `champion.py` + `st2_lab/champion.json`
- **Does:** persists the recursive state — the current best config:
  `{params:{imb_min,br_min,min_trades,hold_cycles,atr_mult,tp_mult,sl_mult},
    filters:[{id,code,hash}], metrics:{...}, lineage:[...]}`.
- **Interface:** `load()`, `save(cfg)`, `append_lineage(cfg, metrics)`.
- **Depends on:** nothing (pure JSON IO in the lab dir).

### 4.2 Proposer — `proposer.py`
- **Does:** given champion + diagnostics, emits K candidate mutations (param deltas and/or
  one new entry-filter as pure code over whitelisted inputs: `imb, br, tc, cvd, regime,
  time, rsi`).
- **Interface:** `propose(champion, diagnostics, k) -> list[Candidate]`.
- **Depends on:** an LLM agent call (or, for v1 params, a bounded deterministic mutator);
  the input whitelist contract.

### 4.3 Sandbox evaluator — `evaluator.py`
- **Does:** replays recorded `flow_capture.jsonl` + L2 ticks + OHLCV through each candidate,
  returns **relative** metrics vs champion (net, WR, Kelly, maker-fill proxy). Runs filter
  code in the restricted sandbox.
- **Interface:** `evaluate(candidate, dataset) -> Metrics`; `rank(candidates) -> ordered`.
- **Depends on:** recorded datasets (read-only), the sandbox executor.
- **Note:** explicitly relative-only; reuses/forks existing `backtest.py` replay where sound,
  but inherits its known exit-model crudeness — hence ranking-only.

### 4.4 Sandbox executor — `safe_exec.py`
- **Does:** compiles + runs a generated filter under AST whitelist, no imports/IO, timeout;
  returns bool or rejects.
- **Interface:** `compile_filter(code) -> callable | Rejection`.
- **Depends on:** nothing (stdlib `ast`).

### 4.5 Orchestrator — `loop.py`
- **Does:** one iteration = load champion → diagnostics → propose K → sandbox-rank →
  if winner beats champion by margin M, promote to champion (autonomous) + log lineage →
  decide gate action (below). Reports a digest.
- **Interface:** `run_iteration()`; invoked by launchd.
- **Depends on:** all of the above + the proposals/Telegram emitters.

## 5. Data Flow (one iteration)

```
champion.json ─▶ diagnostics(ST2.0 paper results, read-only)
              ─▶ proposer → K candidates (params and/or filter code)
              ─▶ safe_exec compiles any filter code (reject unsafe)
              ─▶ evaluator replays recorded data → relative ranking
              ─▶ best > champion + margin?  ── no ─▶ log "no improvement", stop
                                             └ yes ─▶ champion := best (lineage logged)
              ─▶ gate:
                   params-only champion ─▶ auto-register real paper-confirm slot
                   filter-bearing       ─▶ write spec+diff to docs/fix-proposals/ (human audit)
                   paper-confirmed & strong ─▶ emit LIVE promotion proposal (human approval)
```

## 6. Human Gates (summary)

| Action | Gate |
|--------|------|
| Sandbox iteration / champion update | **Autonomous** |
| Params-only → real paper-confirm | **Autonomous** (no new code) |
| Filter code → real paper-confirm | **Human audit** (`/pre-restart-audit`) |
| Any → LIVE | **Human approval** (always) |

## 7. Scheduling

`com.phmex.st2-lab.plist`: sandbox iterations daily (cheap); paper-confirm maturation is the
slow gate (orchestrator checks confirm-slot sample size each run, proposes only at ≥30 trades).

## 8. Testing

- `safe_exec`: rejects imports/IO/loops-over-budget; accepts valid pure filters.
- `evaluator`: deterministic replay → stable metrics on a fixed dataset; relative ordering sane.
- `proposer`: every candidate is schema-valid and within param bounds; filters compile.
- `champion`: update only on margin beat; lineage integrity; halt flag respected.
- End-to-end dry run on recorded data, producing a digest, **before** any launchd scheduling
  and **before** any real paper slot is touched.

## 9. Phasing (implementation ordering)

- **Phase 1 — param loop end-to-end:** champion store, deterministic param mutator, evaluator,
  orchestrator, params-only auto paper-confirm, digest. Proves the machinery on the safe path.
- **Phase 2 — filter codegen:** agent proposer for filters, `safe_exec`, the fix-proposal
  emitter for human-audited filter paper-confirm.

Same final system; Phase 1 ships and proves value before any code-generation exists.

## 10. Open Questions

None blocking. Defaults chosen: margin M and confirm-sample (30) are config in `champion.json`,
tunable after first dry run.
