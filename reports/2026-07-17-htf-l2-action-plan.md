# htf_l2_anticipation — Final Debug Verdict & Action Plan (2026-07-17)

Three debug rounds, 13 agents + 5 independent verification agents. Every number below
survived independent re-derivation (R1: 10/10; R2: 10/10 + DOA arbitration; R3: 11/11 + 2
reconciliation checks). Full evidence ledger: memory reference_htf_l2_diagnosis_2026-07-16.md.

## Verdict (one paragraph)

htf_l2_anticipation loses because its payoff geometry needs a 67.9% win rate (median winner
+4.3% ROI vs median loser −12.7%) while it delivers 55–60%, on top of measured entry adverse
selection (−4.5 bps 1m post-fill drift, CI excludes 0). The refined loss engine is the
**thin-tape ∧ htf_adx≥35 conjunction** — extended 1h trends entered on a dead tape — which
holds 99% of July's bleed and −$29.22 lifetime, while thin-only is +$6.86 and adx-only is
mildly negative. Even applying BOTH known filters (drift gate + ADX block), the residual book
is statistically breakeven (+$0.055/trade, CI [−$0.12, +$0.22] includes 0), and every one of
these findings is in-sample on the same 215-trade ledger. **There is no evidenced path to
positive expectancy. The halt stands** (its rationale survives all corrections; the one false
line — "never a profitable month," June was +$5.26 — has been annotated in memory).

## Track 1 — Safety fixes (no strategy decision needed; protect live money & forensics)

Ship via normal flow: TDD per fix → audit agents → batch audited fixes → ONE restart
(pre-restart-audit + your "go"). Architect specs are written and location-verified.

1. **H1 (DO FIRST — live-money):** during global `.pause_trading`, live-slot software exits
   and SL-ratchet freeze (bot.py:1516 return precedes `_evaluate_all_slots` at 2095). Fix =
   mirror the `.halt_main_entries` pattern (evaluate slots before the pause return) **plus**
   add the missing pause check to the PAPER slot entry branch (bot.py:2517 — the live branch
   at 2535 already has one; a naive mirror would resume paper entries during pause). 4 tests
   specced. This is the only hole touching live money today (5m_mean_revert).
2. **H3:** pause/halt never cancels resting entry orders. New `cancel_entry_orders(symbol)`
   (skips reduceOnly SL/TP), one-shot sweep on the pause transition edge in
   `_process_sentinels`, flag `CANCEL_ENTRIES_ON_PAUSE` for instant revert, Telegram line
   when ≥1 cancelled. 4 tests specced. Risk: verify reduceOnly field shape on Phemex trigger
   orders before trusting the filter.
3. **H2:** `_try_limit_entry` cancel-fail leaves a live resting order forever
   (exchange.py:444-466 — the 4/13 and likely 6/14 ghost mechanism). Registry + per-cycle
   re-cancel sweep alongside the existing reconcile call; adoption stays exclusively with the
   existing orphan scan (no duplicate adoption logic). TTL alert if stuck >24h. 5 tests specced.
4. **H4 (lowest risk):** adoption records get `adopted: true` + `adopted_at` provenance
   fields (additive, `.get()`-defaulted like sl_ratcheted/scaled_out precedent) so restart
   adoptions can never again masquerade as entries (the 6/14 "pause bypass" that wasn't).
   5 tests specced.

## Track 2 — Decisions that are YOURS (evidence attached, nothing shipped)

- **D1 — htf_l2 fate. Recommendation: RETIRE (leave halted permanently).** The residual-book
  analysis is the decision-critical number: even with the drift gate AND the ADX block, the
  surviving book is breakeven with a CI including zero, positive only because of June. If you
  ever want to revisit: the only honest route is a PAPER slot (Donchian precedent) with a
  pre-registered thin∧ADX shadow gate, telemetry fixed first (Track 3), and adjudicator-graded
  kill criteria at a fixed n — never a live re-arm on this evidence. I will not re-propose.
- **D2 — drift gate falsifiability.** It's shipped code that only gates a halted strategy —
  ungradeable as-is (evidence debt: shipped at n=38 vs pre-registered n≈60). Options: grade it
  offline with the round-2 replay machinery, write down resume-grading criteria now, or accept
  it as dormant. If D1 = retire, it's moot dead code; removal can ride any future cleanup.
- **D3 — standing open items (unchanged, yours):** PT fee toggle (10% off both legs, PT in
  futures wallet); duplicate memory-file merge OK; V17 stays DORMANT per your 7/15 final.

## Track 3 — Telemetry debt (only matters if anything ever resumes; hold otherwise)

- gate_tags never written on main-path entries (all 215 htf_l2 trades: None) — entered-trade
  gate forensics impossible without it.
- Ensemble 4/7 gate: confirmed dead weight (0 blocks ever; min live confidence is exactly 4/7)
  and its blocks wouldn't reach gotAway anyway. Remove or instrument on resume — not before.
- Frozen-by-halt studies (prefill toxicity n=12, thin-tape n-accrual, drift-gate grading):
  cannot gain power while halted. Closed-as-moot under D1=retire.

## What is closed — do NOT re-open (with receipts)

Exit-geometry levers (inventory 100% complete 7/6; the round-2 SL@−8% table is measurement,
not a proposal); gate-stack re-runs (6/13 directive); basket-TSM / BTC-TSM (kill-tested);
funding/XS/OI at this scale; maker re-quote port; posting inside spread; symbol blacklists
(loss is diffuse — and BTC stays, per your standing order).

## Corrections written to memory this session

1. "Never a profitable month" → June 2026 +$5.26 net (halt file annotated; halt stands).
2. DOA "71%/58% never reached +1%" → 30-minute-window artifact; honest ≈39-43% of EC losers
   (sl-loss-levers file corrected; both later studies were wrong in opposite directions).
3. Paper-sim fee "open bug" → fixed 7/5, note was stale.
4. 6/14 "pause bypass" → restart-adoption record, not a violation (solved, closed).

## Current live state (unchanged by this work)

Bot PID 83245 (up since 7/16 9:00 PM PT), main halted, 5m_mean_revert live (+$7.08 since
promotion, $12.08 headroom), ETH-TSM paper holding, DONCHIAN_BTC/ETH paper day-1 fidelity
PASS. Dashboard/report balance surfaces fixed 7/16. Watch: Donchian daily eval ~5 PM PT.
