# R1 — Web Research: Fill Rate, Fill Toxicity, and Exit Geometry Beyond What We Already Know

**Date:** 2026-07-05 (overnight run)
**Scope:** New (since ~2023) academic + practitioner work on (a) queue-state-conditional maker placement, (b) short-horizon fill-toxicity prediction from public L2/tape, (c) partial-profit / scale-out geometry for high-WR low-payoff scalping, (d) signal-conditional maker vs taker switching.
**Prior context respected (not re-litigated):** fill-rate↔toxicity tension is structural; front-of-queue ~13x less toxic (the Binance 233k-order study); never post inside spread; no speed/rebate edge at our scale.

**Verification method:** every source below was fetched directly (WebFetch of the arXiv HTML/abstract page, or PDF downloaded and text-extracted locally with pypdf). Numbers are quoted from the fetched text. One source (SSRN 6344338) could not be fetched (HTTP 403 twice) — it is flagged UNVERIFIED and excluded from conclusions.

---

## Verification ledger

| # | Source | How verified | Status |
|---|--------|--------------|--------|
| 1 | arXiv 2502.18625v2 — Albers, Cucuringu, Howison, Shestopaloff, "The Market Maker's Dilemma: Navigating the Fill Probability vs. Post-Fill Returns Trade-Off" (v2 dated Nov 2025) | Fetched HTML twice (overview + reversal section) | VERIFIED |
| 2 | arXiv 2604.27150v1 — Li, Laryea, Ihlamur, "Optimal Stop-Loss and Take-Profit Parameterization for Autonomous Trading Agent Swarm" (Apr 29, 2026) | PDF downloaded, full text extracted with pypdf, read directly | VERIFIED (full text) |
| 3 | arXiv 2403.02572 — Lokin & Yu, "Fill Probabilities in a Limit Order Book with State-Dependent Stochastic Order Flows" (Mar 2024, v2 Feb 2026) | Fetched abstract page | VERIFIED (abstract only, no usable numbers) |
| 4 | arXiv 2506.05764v2 — Wang, "Exploring Microstructural Dynamics in Cryptocurrency Limit Order Books: Better Inputs Matter More Than Stacking Another Hidden Layer" (May 2025) | Fetched HTML | VERIFIED |
| 5 | arXiv 2602.00776v1 — Bieganowski & Ślepaczuk, "Explainable Patterns in Cryptocurrency Microstructure" (Univ. of Warsaw) | Fetched HTML | VERIFIED |
| 6 | Quant Arb, "Execution — Without The Fluff" (algos.org, Apr 24, 2023) | Fetched page | VERIFIED |
| 7 | Multicoin Capital, Applebaum & Sengupta, "Adverse Selection Rules Everything Around Me" (Feb 17, 2026) | Fetched page | VERIFIED (DeFi-focused, low applicability) |
| 8 | Crypto Chassis, "Defensive Market Making Against Market Manipulators" (Medium, Sep 20, 2021) | Fetched page | VERIFIED (pre-2023, included as practitioner background) |
| 9 | Lucas Astorian, "Order Flow Toxicity in the Bitcoin Spot Market" (Medium, Jun 22, 2021) | Fetched page | VERIFIED (pre-2023, weak result, background only) |
| 10 | SSRN 6344338 — Rajendran & Singaravelu, "Predicting Adverse Selection in High-Frequency Cryptocurrency Markets Using Gradient Boosting" (Mar 2026) | SSRN + Delivery.cfm both HTTP 403; numbers seen only in search-index snippets of the abstract | **UNVERIFIED — excluded from conclusions, listed as a lead** |

---

## (a) Queue-state-conditional order placement

### 1. The Market Maker's Dilemma (arXiv 2502.18625v2) — the new parts of the known study

This is the same Binance BTCUSDT-perp experiment we already know (232,897 minimum-sized maker orders, Feb 12–19 and Aug 21–31, 2024; 127,051 filled). What we had NOT extracted before:

**Verified claim 1 — fill probability is almost fully a function of the two queue sizes.** An OLS on normalized queue sizes fits the fill-probability surface with **R² = 0.946**; coefficients β₀=0.5649, β₁=0.0159 (near-side queue), β₂=0.1013 (opposite-side queue), β₃=−0.3166 (imbalance). Fill probability ranges "~30% (large near, small opp) to >90% (small near, large opp)."

**Verified claim 2 — the full markout table by queue configuration (1-second markouts, bp):**

| Queue config | Front (QP 0–10%) | Back (QP 75–100%) |
|---|---|---|
| Large near, small opp | −0.058 | −0.775 |
| Large near, large opp | −0.296 | −1.157 |
| Small near, large opp | −0.539 | −0.763 |

Unconditional: "negative expected return of approximately −0.8 bp, or −0.3 bp net of rebate." The only configuration with near-zero (and in the paper's words "notably positive" in some cells) markout is **front-of-queue in a LARGE near-side queue with a SMALL opposite queue** — i.e., exactly the placement with the LOWEST fill probability (~30%). This is the structural tension quantified end-to-end on one dataset.

**Verified claim 3 — the "reversal" resolution.** The paper's proposed way out: orders achieve "high fill probability and positive price drift" when the initially adverse imbalance **reverses favorably after submission**. A reversal = order fills AND achieves positive return between fill and the next midprice change. They fit a logistic regression on 182,381 orders (first half train, second half test) using: multi-scale price moves (100ms, 1s, 5s, 30s, 5min in three consecutive windows), realized vol over 100/500 ten-second returns, taker order-flow imbalance, depth/spread, time-of-day. (The HTML fetch truncated before the model's AUC/markout-improvement numbers — those specific performance figures are NOT verified and are not claimed here.)

**Applicability at our scale — decent, with one big caveat.** We can't manage queue position at 60s cycle, but everything above is *placement-time* information available from one REST/WS book snapshot: near-side queue size, opposite queue size, recent multi-scale returns, recent taker flow. Nothing requires speed. The caveat: their markouts are 1-second; our adverse drift is measured over 1 minute and our own pre-fill toxicity study found "tape quiet before fills — patient adverse selection, undetectable" (2026-07-02 NULL). The reversal framing is different from what we tested, though: we tested *cancel-on-toxicity after posting*; this conditions *whether/where to post at all* on queue sizes + multi-scale return context.

**Concrete experiment on our own data:** we already log entry_snapshot ob/flow on fills. (1) Reconstruct near/opp queue sizes at placement for our historical placements (filled AND unfilled — main bot has the 100-miss dataset, slot has the 148-fill htf_l2 set). (2) Fit the same 4-term OLS for OUR fill probability; check if R² is anywhere near theirs at 60s patience. (3) Bucket our −3 to −4.5bp 1-minute drift by the 3×2 queue-config table above and see if the "large-near/small-opp" cell is materially less toxic for us too. If yes → placement gate: only post when near-queue is large relative to opposite queue (accepting lower fill rate on a per-attempt basis, offset by the 45s patience leg already live). This is precisely the "queue-size study on our own fills" already queued in memory — this paper supplies the exact regression form and bucketing to copy.

### 2. Lokin & Yu (arXiv 2403.02572)

**Verified claim (abstract only):** semi-analytical fill probabilities at best quotes and deeper levels under state-dependent order flows, validated on FX spot data; fill probabilities "are typically negligible" at deeper levels. No usable numbers in the abstract; the model machinery (interacting queueing systems) is over-engineered for our use.

**Applicability: low.** The one transferable point — fill probability is state-dependent and computable from queue state — is already covered better by source 1. No experiment proposed.

---

## (b) Short-horizon fill-toxicity prediction from public L2/tape

### 3. Better Inputs Matter More Than Stacking Another Hidden Layer (arXiv 2506.05764v2)

**Verified claims:** Bybit BTC/USDT, 100ms LOB snapshots, single day (2025-01-30). Mid-price direction classification: with Savitzky–Golay filtering of inputs, accuracy improved from 0.5941–0.6542 (raw) to 0.6260–0.7284 across models — "approximately 6–8% improvement." At 1000ms horizon, **XGBoost 0.7150 beat DeepLOB 0.6947 and logistic regression hit 0.7089**. 40 book levels vs 5 levels: 0.715 vs 0.580 accuracy. Top features: previous mid-price, first-level order imbalance, five-level aggregate imbalance, weighted mid-price changes.

**Applicability: moderate as a design principle, weak as evidence** (one day, one venue). The transferable lessons for any toxicity/direction model we build: (i) simple models (logistic/XGBoost) on well-engineered book features match deep nets — good, because that's all we can run; (ii) smoothing inputs matters more than model choice; (iii) L1-only imbalance is much weaker than multi-level aggregate imbalance — our entry_snapshot should capture ≥5 levels if it doesn't already.

**Concrete experiment:** when we run the queue-config study in (a), include 5-level aggregate imbalance alongside L1 imbalance as a conditioning feature and compare drift separation. Zero new infrastructure if snapshots already store depth.

### 4. Explainable Patterns in Cryptocurrency Microstructure (arXiv 2602.00776v1)

**Verified claims:** Binance Futures perps, 1-second data, Jan 1, 2022 – Oct 12, 2025, five assets across the cap spectrum (BTC, LTC, ETC, ENJ, ROSE). Findings: "order flow imbalance has a largely monotone effect with concavity at extremes"; wider "spreads are associated with diminished predictability"; "VWAP-to-mid deviations display asymmetric effects coherent with short-lived pressure and microstructure reversion." Their taker strategy was statistically significant (5% level) only on the SMALL caps: ETC ARC 5.78% (IR* 8.97), ENJ 4.06% (IR* 6.58), ROSE 7.00% (IR* 5.28) — not on BTC. Their maker strategy, in the Oct 10, 2025 flash crash, "repeatedly gets filled on the bid side, accumulating a losing long position" — textbook adverse selection.

**Applicability: moderate.** Two usable points. First, short-horizon microstructure predictability concentrates in smaller-cap perps — consistent with our scanner trading alts, and an argument against concentrating in BTC/ETH for maker entries. Second, "wide spread ⇒ less predictable" is a cheap placement filter: skip maker entries when spread is abnormally wide for the symbol (wide spread = makers already pricing in toxicity, per source 7's framing too).

**Concrete experiment:** bucket our 148 htf_l2 fills' 1-minute drift by spread-at-placement percentile (per-symbol normalized). If the widest-spread tercile carries disproportionate drift, add a max-spread placement gate. One afternoon of work on existing data.

### 5. TailScore paper — Rajendran & Singaravelu (SSRN 6344338) — **UNVERIFIED**

Search-index snippets of the abstract claim: composite TailScore = predicted toxicity probability × predicted 99th-percentile absolute move; gating the top 0.1% highest-risk seconds "reduces CVaR99 tail risk 25.85× more efficiently than random gating," replicating on ETH at 27.50×; inference <1ms on CPU. **Both SSRN URLs returned HTTP 403 — I could not read the paper. These numbers are NOT verified and no conclusion rests on them.** Flagged as a lead only. Note also the internal tension with our own 2026-07-02 NULL: our fills happen in *quiet* tape, so second-level toxicity spike gating plausibly wouldn't touch our loss engine even if the paper checks out. Low priority.

### 6. Background (pre-2023, verified, low value)

- **Astorian VPIN on Binance BTC (2021):** VPIN-based classifier reached only AUC 0.55 even with a volatility filter (0.49 without). Confirms VPIN is a weak standalone toxicity signal at retail data granularity — supports NOT building a VPIN gate.
- **Crypto Chassis (2021):** practitioner "quote-pause" guard — halt quoting when price rate-of-change exceeds a threshold. Same family as our tested-and-NULL pre-fill toxicity cancel; their evidence is a single-day visual backtest. Nothing new to test.

---

## (c) Partial-profit / scale-out geometry

### 7. Optimal Stop-Loss and Take-Profit Parameterization for Autonomous Trading Agent Swarm (arXiv 2604.27150, Apr 2026) — full text read

**Setup (verified from full text):** crypto agent swarm (~10–20 agents, refresh ~every 15 min), >900 closed trades with full price paths, counterfactual replay of 8,960 exit configurations. Baseline production config: 25% SL, 3% trailing activation, 2% trailing distance, 5% partial-TP threshold, **50% partial-TP fraction**, 24h stale close.

**Verified results:**
- Baseline Sharpe 0.419 → best first-pass config 0.525 (+25.2%) → with ATR overlay + circuit breaker 0.653 (+56.0% over baseline). Profit factor 1.639 → 1.760 → 2.375.
- **All top-5 first-pass configs use: 10% SL (vs 25% baseline), 48h stale close, and a 75% partial-take-profit fraction** at a 5–10% threshold. Four of five use 2–3% trailing distance. The paper: "the production baseline appears too permissive on losses and too slow to lock in gains" and (from the abstract) results "generally favor tighter loss limits, earlier profit capture, and closer trailing protection."
- The winning region is "a coherent band in the parameter surface," not one point — some robustness.

**Honest caveats (stated in the paper itself):** the chronological 70/30 split was abandoned because the test window hit the "war-driven market period" (test Sharpes "as low as −5"); the headline comparison uses a **randomized split**, which "weakens the interpretation of the results as a strict forward test." 8,960-config search on 900 trades = heavy selection bias, acknowledged. Self-published (Vela Research + one Oxford student). Their trades are hours-to-days holds, not 60s-cycle scalps.

**Applicability: directional only, but it directly targets our avg-win problem.** Our current partial-TP: 50% off at +10% ROI, runner to +25%. Our loss asymmetry: avg win $0.46 vs full-SL loss $1.25–2.00. The paper's consistent pattern — **take a LARGER fraction (75%) at the FIRST threshold and cut the SL tighter** — is the opposite of the "let more ride" instinct and is at least a coherent, externally-tested hypothesis for high-WR low-payoff books. Important tension to respect: our own verified exit inventory says "HOLD beats cut 9/9 cells" and time-ratchet SL is dead — so the *tighter SL* half of their recipe contradicts our own data and should NOT be adopted; only the *scale-out fraction* half is untested on our data.

**Concrete experiment (fits the already-planned partial-TP study @30 scale-outs):** replay our trade price paths over a small grid — partial fraction ∈ {25%, 50%, 75%} × first threshold ∈ {+5%, +10% ROI} — holding SL geometry FIXED (per our own null results on exit tightening). Score by net expectancy and by avg-win/avg-loss ratio. This is the cheapest of the three experiments; the replay harness already exists (exit_replay.py pattern).

Also checked: QuantifiedStrategies profit-taking backtest page — blocked by bot verification, could not fetch, excluded. Generic practitioner pages (chartwisehub, chartingpark, tradezella) contain no backtests, only mechanics — excluded from conclusions.

---

## (d) Signal-conditional maker vs taker switching

### 8. Market Maker's Dilemma, taker result (arXiv 2502.18625v2)

**Verified claim:** their imbalance-following TAKER strategy: "the taker strategy is rendered unprofitable by the taker fee: while its pre-fee PnL is impressive (around +1 bp per roundtrip), paying the taker fee on each leg of the roundtrip erodes its profitability completely" — at an assumed taker fee of **1.5 bp per leg** on Binance BTC perp.

**Applicability: high, as a NEGATIVE result.** Phemex taker fee is 6 bp per leg (4x Binance's assumed fee) and our symbols have wider spreads than BTC. If a clean, in-sample-best imbalance signal nets ~+1 bp pre-fee per roundtrip on the most liquid perp in the world, a taker-entry variant of our signal must clear ~12 bp fees + spread — an order of magnitude above the bps-scale edge we've ever measured. **Verdict: signal-conditional taker switching is almost certainly dead at our fee tier; do not build it.** This also retro-confirms the 2026-07-02 finding that our 100 missed PostOnly fills were NOT missed winners (−$4.04 occupancy-corrected) — chasing them with taker orders would have paid fees to capture nothing.

### 9. Quant Arb, "Execution — Without The Fluff" (Apr 2023, practitioner)

**Verified claims:** Take when the signal is strong/fast-decaying and passive fill probability is low ("If we try to make we will not get filled, and end up moving our limit order constantly to chase the price"); make when horizon is longer and conditions stable; condition quotes on order-flow imbalance and queue position so "our quotes don't get picked off by informed flow"; small accounts "primarily face spread and slippage costs rather than market impact."

**Applicability: framing only.** The decision rule (take iff expected-alpha × decay > spread + fee delta) is standard; combined with source 8's numbers it resolves AGAINST taker switching for us. The one refinement worth keeping: fill probability belongs in the entry EV calculation explicitly — which the (a) experiment produces as a byproduct (our own fitted fill-prob model).

### 10. Multicoin (Feb 2026)

**Verified claims:** taxonomy of adverse-selection mitigations (batching, private routing, flow segmentation, dynamic fees, post-fill cancellation windows, refusing flow); "Whether order flow is toxic or non-toxic is measured over periods from a few microseconds up to 10 minutes, depending on the asset."

**Applicability: near zero operationally** (venue-design essay, DeFi-centric). One conceptual echo worth noting: the industry-level answer to toxic flow is *refusing to quote into it* (segmentation/dynamic fees), not out-trading it — consistent with our placement-gating direction in (a) rather than smarter cancels.

---

## Bottom line — ranked by transferability

1. **Queue-config placement gating with a reversal overlay (a+b, from the verified deep-dive into arXiv 2502.18625v2).** New actionable detail beyond the known 13x fact: fill probability is ~fully determined by near/opp queue sizes (R²=0.946, coefficients published), the 3×2 markout table identifies "large near-queue + small opposite-queue" as the only clean cell, and the profitable-fill mechanism is *imbalance reversal after posting*, predictable from multi-scale returns + flow features we already snapshot. Experiment is cheap and is the exact "queue-size study on our own fills" already queued in memory — now with a copyable regression form and bucketing scheme.

2. **Scale-out fraction 75/25 at first TP (c, arXiv 2604.27150, full text read).** All top-5 of 8,960 replayed configs on 900+ crypto trades took 75% (not 50%) off at the first +5–10% threshold; Sharpe 0.419→0.525 first pass. Evidence is weak-ish (randomized split, selection bias, slower timescale) but it plugs directly into our planned partial-TP study; test fraction only, keep SL geometry fixed per our own nulls.

3. **Taker switching: verified dead-end (d).** Best-case imbalance taker on Binance BTC = ~+1 bp pre-fee, killed by 1.5 bp fees; Phemex charges 6 bp. Do not build maker→taker switching; the fee math fails by ~an order of magnitude. Negative result, but it closes a branch permanently and cheaply.

Supporting design notes: use ≥5-level aggregate imbalance not L1-only, simple models (logistic/XGBoost) suffice (arXiv 2506.05764); add a per-symbol max-spread placement filter candidate (arXiv 2602.00776); VPIN gate not worth building (AUC 0.55, verified); TailScore paper UNVERIFIED (403) — revisit only if it becomes fetchable.
