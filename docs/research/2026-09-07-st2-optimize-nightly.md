# ST2.0 Execution Nightly — Night 66 (2026-09-07)
**Focus:** Passive maker fill quality / adverse selection mitigation  
**Prior coverage:** N1–N65 complete

---

## (a) What's New vs. Prior Reports

### Two new papers screened — both NOT APPLICABLE

**arXiv:2607.28323 — "Optimal Execution with Passive Market Impact"**  
Barzykin, Boyce, Neuman, Tuschmann — July 30, 2026  
URL: https://arxiv.org/abs/2607.28323

Data: NASDAQ equities (LOBSTER, Jan–Dec 2016) + FX (LSEG, 2026). **No crypto, no CEX perps.**

Key mechanism: fill intensity modeled as Λ(δ) = λe^(−kδ), where δ is quote distance from mid. Calibrated k ≈ 0.49–3.72 for equities/FX. The optimal quote distance is 1/k ticks from mid, plus an inventory adjustment term (η/λ)·q that pushes wider as inventory grows. At negligible size ($15), η/λ → 0 and the inventory term drops out — the only relevant guidance reduces to rest at ~1/k ticks from mid (k uncalibrated for Phemex).

The model assumes continuous repricing to maintain a fixed δ offset from the moving midprice. A static resting POST-ONLY order that isn't repriced as mid drifts is implicitly widening δ over time, shrinking fill probability by the same exponential law — confirmed empirically from the paper's calibration but not modeled for crypto.

**Verdict: NOT APPLICABLE as a new tweak.** The paper models self-impact (your fills move price), which is irrelevant at $15 size. It does not model adverse selection from incoming informed flow — the primary risk mechanism for ST2.0. No crypto data. The fill-probability decay finding (exponential in δ) is consistent with prior corpus but adds no new actionable threshold for Phemex.

---

**arXiv:2605.24242 — "Explicit Signal-Adaptive Sequential Optimal Execution Quotes"**  
Fenghui Yu — May 22, 2026  
URL: https://arxiv.org/abs/2605.24242

Data: **None.** Purely theoretical extension of Avellaneda-Stoikov. Derives closed-form HJB solutions when a directional price signal is present. Fill intensity is the same λe^(−κδ) exponential.

Key structural result: a stronger bearish directional signal (parameter a) shifts the optimal quote *closer* to mid (smaller δ*). Verbatim from abstract: "More aggressive quotes increase the likelihood of fills but reduce execution revenues, whereas more passive quotes improve prices but expose the trader to fill risk and inventory risk." The signal-drift term justifies accepting tighter execution to capture the signal.

**Verdict: NOT APPLICABLE as a new tweak.** No empirical validation on any market. Does not address adverse selection from informed flow. Conceptually consistent with prior corpus (stronger signal → tighter ask) but provides no empirically calibrated threshold applicable to Phemex.

---

### One conceptual refinement from existing corpus — OFI timing direction corrected

Source: arXiv:2502.18625 — "The Market Maker's Dilemma" (Binance BTC perp, already in corpus since the June 20 synthesis)

The synthesis extracted the queue-position finding correctly (front-of-queue: −0.058 bp; back-of-queue: −0.775 bp adverse selection). But it proposed "wait for OFI flip before posting" as a forward-test candidate — which is **opposite** to what the paper actually implies for queue positioning.

The paper states (fetched content, directly):  
> "Post the order when the queue is still small but becomes large shortly thereafter. This usually implies posting the order when the order book imbalance is unfavorable."

For a SHORT maker: "OFI unfavorable" = buying pressure present. ST2.0 already posts during absorption (heavy buying into the ask). The implication is: **post at the START of the absorption window — when the ask queue is still thin — not after waiting for peak signal confirmation.** By the time the absorption signal peaks (OFI strongly confirming), the ask queue may already be full, placing you at the back.

"Wait for OFI flip before posting" (synthesis option) would mean waiting until buying pressure *subsides* before posting your ask — arriving at a queue that reformed after the burst, probably thin again, but also potentially in a lower-signal regime. This is a different strategy that remains untested.

The correct reading of the MM Dilemma paper for ST2.0's entry: **post earlier in the absorption window to obtain front-of-queue position**, accepting that the signal confirmation is less mature at posting time. This is a timing discipline, not a parameter change.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Candidate Tweak 47 — Post at absorption onset, not peak (conceptual, not yet deployable)

**Source:** arXiv:2502.18625 (verified, in corpus), re-interpreted tonight  
**Claim:** Front-of-queue position reduces adverse selection by ~13× vs. back-of-queue (−0.058 vs −0.775 bp). Getting front-of-queue requires posting when the ask queue is still thin — which is early in the absorption window, not at peak OFI.  
**Implementation direction:** Before implementing, instrument first: log `queue_rank_at_fill` — the position of the filled order within the total ask quantity at that price level. Compute from (quantity-ahead / total-at-level) at fill time, using the existing L2 feed. This costs 2–3 lines of Python on the fill confirmation path. After 30+ fills, check whether queue rank correlates with post-fill adverse selection in ST2.0's data.  
**Cost to log:** Zero trading risk. Requires L2 snapshot at fill confirmation time.  
**Caveat:** Posting earlier (lower signal maturity) likely reduces signal quality. The tradeoff between queue position and signal strength is not modeled by the paper and is not calibrated for ST2.0. Do not change entry timing before logging.

---

### Existing undeployed tweaks (still the priority — not new tonight)

The following candidates from prior nights remain undeployed. They are higher priority than Tweak 47 because they have more direct evidence:

- **Tweak 45 (N60):** Log `spread_pct` at every ST2.0 entry attempt; gate on spread ≥ 75th pct rolling per-symbol. Source: arXiv:2602.00776. Still undeployed.
- **Tweak 46 (N65):** Log `v_prior_sell` (volume resting ahead at target ask level). Gate later. Still undeployed.
- **`time_to_fill` logging (N64):** Log elapsed seconds from post-only submission to fill confirmation; bucket by <60s, 60–300s, >300s; compute post-fill 5-min markout per bucket. Still undeployed.

---

## (c) Caveats and Unverifiable Items

1. **September 2026 arXiv still sparse.** As of Sep 7: q-fin.TR and q-fin.ST empty; q-fin.CP 6 papers all pricing math. The sole September 2026 paper found (arXiv:2609.04917, AI in equity/crypto markets) was not screened in detail — its snippet did not indicate relevance to passive execution or adverse selection. Expected accumulation Sep 8–12 per prior reports.

2. **arXiv:2605.24242 (2605.24242) signal-strength → tighter quote** is purely theoretical. No empirical support for any specific δ parameter for Phemex or any CEX. Do not apply without data.

3. **arXiv:2607.28323 k calibration** — the fill-decay exponent k is equity/FX-specific. k for Phemex BTC/ETH perps is unknown and may differ significantly. The 1/k guideline is not usable until k is empirically estimated from ST2.0's own fill-vs-distance logs.

4. **Queue rank at fill (Tweak 47)** — Phemex does not report queue position directly. Queue rank must be inferred from L2 snapshot quantity-ahead at fill time. This is an approximation; if multiple fills occur simultaneously from other market participants, the L2 snapshot may not accurately reflect the rank at the moment of fill.

5. **Counterintuitive OFI timing (Tweak 47 direction)** — the MM Dilemma paper studied symmetric market-making on Binance BTC perp, not directional short-only entry. Applying its queue-timing insight to an asymmetric case (ST2.0) is an inference, not a directly tested finding.

---

## Standing Recommendation (Night 20)

Suspend nightly sweeps. Resume Sep 8–12 when September 2026 arXiv accumulates.

**Immediate priority actions (unchanged from N65):**
1. Deploy `time_to_fill` logging (N64) — 5 lines Python, zero risk
2. Deploy `spread_pct` logging at every entry attempt (Tweak 45 from N60)
3. Deploy `v_prior_sell` logging at every entry attempt (Tweak 46 from N65)
4. Add `queue_rank_at_fill` logging (Tweak 47 direction tonight) — 2–3 lines on fill path

Then deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14 from the existing confirmed queue.

---

## New Papers Screened Tonight

| Paper | Month | Verdict |
|-------|-------|---------|
| arXiv:2607.28323 — Optimal Execution with Passive Market Impact | July 2026 | NOT APPLICABLE (equity/FX, no informed-flow model) |
| arXiv:2605.24242 — Explicit Signal-Adaptive Sequential Optimal Execution Quotes | May 2026 | NOT APPLICABLE (purely theoretical, no CEX data) |

Cumulative confirmed tweak queue: 44 confirmed + 3 candidates (Tweaks 45, 46, 47) + 1 conditional (43, SSRN blocked).  
Consecutive nights with 0 new confirmed tweaks from peer-reviewed sources: **20**
