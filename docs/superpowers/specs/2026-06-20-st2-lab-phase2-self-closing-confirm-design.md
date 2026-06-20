# Phase 2 — ST2.0 Lab Self-Closing Confirm (Forward Adjudication)

**Date:** 2026-06-20
**Status:** Design — pending review
**Depends on:** Phase 1 Step 1 (`stats.py` + `walkforward.py` + adverse-fill gate in `loop.py`)
and Step 2 (`labeler.py` + `features.py`) — all shipped offline.
**Unblocks:** Lab Dashboard (separate unit).
**Hard rule:** never imports `bot.py`, never touches live, never auto-promotes. Offline only.

## Goal

Close the loop the lab leaves open today. Right now `loop.py` emits a *manual*
PAPER-CONFIRM proposal ("run this as a paper variant and forward-confirm ≥ confirm_sample
real trades") that a human must act on and eyeball. Phase 2 builds `confirm.py`: an
offline, **self-closing** adjudicator that, each daily run, advances a forward verdict on
every registered hypothesis and auto-emits CONFIRM / REJECT — replacing the human eyeball
with a recorded, statistically-gated verdict driven by real data.

It produces verdicts. It still does NOT deploy anything. A CONFIRM is a strong,
human-gated recommendation; the lab's never-touch-live invariant is unchanged.

## Why this shape (the documented constraints)

- **Sandbox fills 100%, live ST2.0 fills ~43% and wildly by symbol** (ETH ~80%, BTC ~33%,
  some 0%). Sandbox PnL is an optimistic upper bound that contradicts live (sandbox +$32 vs
  live −$1.89). So a paper slot that fills everything is the artifact machine, not a truth
  source — only **real fills from the live ST2.0 slot adjudicate** (project_st2_lab, the
  honesty stance Jonas pushed hard on).
- **You cannot get real-fill evidence on an undeployed config** without deploying it. So the
  confirm splits candidates honestly: a *narrowing-filter* candidate can be judged on the
  **subset of real live trades its filter would have kept** (real fills, no deploy); a
  *base-loosening* candidate fires setups that never happened, so it gets SCREEN-only and is
  explicitly flagged "needs a human-approved live deploy before any TRUTH verdict."
- **A single split lets the vol-fade artifact pass** (OOS +0.26% on one lucky window,
  full-sample −0.187%). So SCREEN uses forward-OOS replay (data recorded *after* a hypothesis
  is registered — never seen in search) through the Step-1 walk-forward + deflated-Sharpe gate.

## What exists today (build on, don't rebuild)

- `real_trades.load_real_trades()` / `real_summary()` — real LIVE ST2.0 closed trades projected
  to `{features…, net}` records (mode=="live" only). The TRUTH data source.
- `fills.measured_fill_stats()` — measured real maker fill rate from `bot.log`.
- `evaluator.evaluate(cfg, by_symbol, adverse=…)` + `_replay_adverse` — adverse-fill replay.
- `walkforward.walk_forward_splits()` + `stats.py` (deflated Sharpe, BH, bootstrap diff-CI).
- `labeler.label_dataset()` (Step 2) — adverse-fill labels; `calibrate_adverse()`.
- `safe_exec.compile_filter()` — AST-sandboxed filter evaluation (used to apply candidate
  filters to real-trade records).
- `proposer.config_hash()` — canonical config fingerprint (the registry key).
- `champion.json` — recursive state + lineage + `loop` config (`confirm_sample=30`,
  `wf_windows`, `wf_embargo_secs`, `wf_min_trades`, `dsr_min`, `data_epoch`).
- `loop.py` `_maybe_write_proposal` / accept gate — the registration trigger point.

## New component: `scripts/st2_lab/confirm.py`

Pure stdlib, no `bot.py` import, no I/O beyond the lab's own files. Three responsibilities:

### 1. Registry (in `champion.json["confirm_registry"]`)
A list of hypotheses under forward adjudication. Two registration sources:
- A permanent entry `id == "LIVE"` for the live ST2.0 config (TRUTH = all real trades).
- A candidate **only after it clears the Step-1 in-search gate** (walk-forward majority-positive
  + deflated-Sharpe). Deduped by `config_hash`; bounded (reuse `HISTORY_CAP`-style prune).

**Live config provenance (the eligibility baseline).** `confirm.py` cannot import `bot.py`, so
the live ST2.0 config (entry params + exits + filters) is recorded in
`champion.json["live_config"]`, set/updated by the human at deploy time — the same human-gated
step that runs `/pre-restart-audit`. TRUTH eligibility (below) compares a candidate against this
baseline to tell *narrowing* from *loosening*. If `live_config` is absent, the candidate TRUTH
path is **disabled** (only the `LIVE` entry's TRUTH = all real trades runs, and candidates get
SCREEN-only), and that assumption is logged — confirm.py never silently infers the live config.

Each hypothesis record:
```
{ "id": <config_hash | "LIVE">,
  "config": {params, filters, symbols},
  "kind": "filter" | "base",          # narrowing (TRUTH-eligible) vs loosening (SCREEN-only)
  "registered_ts": <data_epoch at registration>,   # forward boundary for SCREEN
  "registered_run": <run_count>,
  "screen": { "trades": N, "windows": [...], "expectancy": x, "deflated_sharpe": d,
              "status": "accruing"|"pass"|"fail", "updated_ts": ts },
  "truth":  { "applicable": bool, "considered": N, "kept": N, "dropped": N,
              "expectancy": x, "ci": [lo,hi], "status": "accruing"|"confirm"|"reject",
              "updated_ts": ts },
  "verdict": "accruing"|"screen_pass"|"screen_fail"|"truth_confirm"|"truth_reject" }
```

### 2. SCREEN verdict — forward-OOS replay
Each daily run, replay the hypothesis config over snapshots with `ts > registered_ts` only
(strictly forward / never-seen-in-search), adverse-fill ON, through `walk_forward_splits` +
`stats`. `status`: `accruing` until the forward slice has ≥ `wf_windows × wf_min_trades`
trades, then `pass` (walk-forward majority-positive AND deflated-Sharpe ≥ `dsr_min`) or `fail`.
SCREEN is explicitly labeled **"screening, NOT truth"** (modeled fills, queue position unknown).

### 3. TRUTH verdict — real-fill subset
On `load_real_trades()`:
- **Eligibility (`truth.applicable`):** True iff the hypothesis is TRUTH-judgeable on existing
  real trades — i.e. `id=="LIVE"`, OR a candidate whose **exit params (sl/tp/hold) equal the
  live config** AND whose **entry conditions are stricter-or-equal** (every real trade the
  candidate admits, the live config also admitted) AND whose filters reference only **raw
  record fields** (not engineered `features.py` keys — real trades are isolated single
  snapshots without a stream, so engineered features are undefined for them). Otherwise False
  → SCREEN-only, with reason recorded.
- **Compute:** apply the candidate's `_entry_ok` + AST filters (via `safe_exec`) to each real
  trade's record; `kept` = passing subset, `dropped` = the rest. `truth.expectancy` =
  mean realized `net` over `kept`; `ci` = `stats` bootstrap CI. `status`: `accruing` until
  `kept ≥ confirm_sample`, then `confirm` (CI lower bound > 0) or `reject` (upper bound < 0);
  ambiguous CI stays `accruing` (honest: not enough signal).
- The `LIVE` entry's `reject` is the load-bearing alert: **"live ST2.0 failing real
  confirmation"** — distinct from (and finer than) the crude −$5 / neg-Kelly auto-demote rails.

### Orchestration — `loop.py` wiring
After the accept/reject step each run: `confirm.register_if_survivor(champ, candidate, …)` for
any Step-1 survivor, ensure the `LIVE` entry exists, then `confirm.tick(champ, dataset,
real_records)` advances every registered hypothesis's SCREEN + TRUTH. Determinism, the `.halt`
kill-switch, `tried`-set dedup, and the human-gated proposal output are all preserved.

## Data flow
```
Step-1 gate survivor ─┐
live ST2.0 config ────┼─> confirm.register -> champion.json["confirm_registry"]
                       │
flow_capture (ts>reg) ─┼─> SCREEN: walk_forward + adverse replay + stats  -> screen.status
real LIVE trades ──────┴─> TRUTH:  filter-subset of real net + bootstrap CI -> truth.status
                              └─> on NEW confirm/reject transition (deduped):
                                   champion lineage entry + docs/fix-proposals/ update
                                   + one Telegram line via the st2-watch digest
                                   (LIVE truth_reject = loud standalone alert)
```

## Output contract
Each verdict transition (not every run — deduped on `(id, verdict)`):
- appends a `champion["lineage"]`/`history` entry with the verdict + evidence,
- updates the hypothesis's `docs/fix-proposals/st2-lab-paper-confirm-<hash>.md` with SCREEN +
  TRUTH status and the explicit `status: "hypothesis — forward-confirm; CONFIRM is a human-gated
  recommendation, NOT auto-deploy"`,
- emits one line through the existing `st2-watch` Telegram digest; a `LIVE` `truth_reject`
  fires a loud standalone alert.

## Isolation invariants (unchanged, re-asserted)
- No `bot.py` / `main.py` import; no order placement; no `.env`/live-state writes.
- Generated filter code only ever runs through `safe_exec` (AST interpreter, name whitelist).
- A CONFIRM never deploys; live promotion stays a human decision behind `/pre-restart-audit`.

## Scope / non-goals
- **No dashboard** (separate unit). No live changes. No new trading.
- Does not change the live ST2.0 signal or any `bot.py` logic.
- Does not re-derive net under different exits from closed trades (impossible without the price
  path) — that's exactly why exit-param-changing candidates are SCREEN-only.
- "No hypothesis confirms this round" / "all accruing" is a valid, expected, honest output.

## Testing
- **Registry:** Step-1 survivor registers (deduped by hash); `LIVE` entry always present;
  non-survivor does not register.
- **SCREEN:** replay uses only `ts > registered_ts`; `accruing` below trade threshold; `pass`
  on a synthetic forward-positive fixture, `fail` on a forward-negative one.
- **TRUTH eligibility:** looser-base candidate → `applicable False` (SCREEN-only); engineered-
  feature filter → `applicable False`; stricter-entry + same-exits raw-field filter → `True`.
- **TRUTH subset:** on a real-trade fixture, a narrowing filter's `truth.expectancy` == mean net
  of the kept subset; `dropped` excluded; `LIVE` == all trades; `accruing` below `confirm_sample`.
- **Self-closing transitions:** `accruing → confirm/reject` emits exactly one lineage entry +
  one alert (deduped across repeat ticks); `LIVE truth_reject` produces the loud alert.
- **Isolation:** `confirm.py` imports no `bot.py`; **Determinism:** two ticks → identical state.
- **End-to-end:** one `loop.tick` with a registered hypothesis on a fixture runs SCREEN + TRUTH
  and updates `champion.json` deterministically.

## Risks
- **Real-trade volume is tiny (29, all ob:null pre-Phase-0).** TRUTH will mostly read `accruing`
  for a while — honest and logged; complete rows accrue from the Phase-0 fix forward.
- **Engineered-feature filters can't get a TRUTH verdict** (featureless real records) → SCREEN-
  only. Documented; most diagnostics filters are raw-field and unaffected.
- **SCREEN inherits the adverse-fill assumption** (queue position unrecorded). Mitigation:
  labeled "screening, NOT truth"; TRUTH on real fills is authoritative.

## Decomposition (build order within Phase 2)
1. `confirm.py` registry + data model + `register_if_survivor` + `LIVE` entry + loop wiring.
2. SCREEN verdict (forward-OOS replay + self-close).
3. TRUTH verdict (eligibility + real-fill subset + self-close + LIVE-reject alert).
4. Outputs (lineage + proposal-doc update + st2-watch Telegram line). Dashboard = later unit.
