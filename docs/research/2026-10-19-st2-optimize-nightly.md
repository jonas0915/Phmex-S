# ST2.0 Execution Optimization — Night 93 (2026-10-19)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–82 across Nights 1–92. Night 92 (2026-10-18): no new tweak; arXiv 2608.04373 (Hyperliquid wallet-level adverse selection) verified but not actionable for Phemex CEX. Night 91: Tweak 82 (FIFO time-to-fill queue classification). Night 90: Tweak 81 (robust volume Z-score burst detector). Undeployed #1 priority remains Tweaks 47/65.

---

## (a) What's New vs. Prior Reports

**Search angles pursued tonight (all 4 are new angles vs. prior nights):**
1. LOB resilience / post-sweep recovery (academic 2025–2026)
2. Iceberg order detection and passive-fill adverse selection (2025–2026)
3. Cross-venue price discovery / latency arbitrage detection for crypto perps
4. Post-only repricing / cancel-replace strategies for crypto maker execution

**Papers fetched tonight and disposition:**

| Paper | URL fetched | Disposition |
|-------|-------------|-------------|
| arXiv 2607.16970 (Novotny — "Herding and Liquidity: Fundamental Anchoring and Resilience," Jul 2026) | arxiv.org/html/2607.16970v1 | Agent-based simulation, no real exchange data, no crypto mechanics, no bps numbers. **NOT actionable.** |
| arXiv 2608.09188 (Seo et al. — "When Cross-Venue Agreement Is Not Price Discovery," Aug 2026) | arxiv.org/html/2608.09188 | Covers equity perpetuals (AAPL/NVDA/TSLA/AMZN) on crypto venues — mark construction for margin/funding/liquidation. No passive maker execution component. **NOT actionable.** |
| arXiv 2603.28898 (McAuliffe et al. — "Model Predictive Control For Trade Execution," Mar 2026) | arxiv.org/html/2603.28898v1 | NASDAQ equities, parent-order VWAP/TWAP execution. Mentions a "fast-cancel module" that withdraws resting orders on OBI shift, but: equities only, no threshold specified, no bps numbers reported for that module alone, requires FPGA-latency. **NOT actionable for ST2.0.** |
| arXiv 2609.22785 (Yang & Xu — "Robust Market Making with Hawkes Order Flow," Sep 2026) | arxiv.org/html/2609.22785 | Simulation only, no real exchange data, no crypto asset class, no adverse selection in bps. **NOT actionable.** |
| arXiv 1803.05690 (Lehalle, Mounjid, Rosenbaum — "Optimal Liquidity-Based Trading Tactics," 2018) | arxiv.org/html/1803.05690v1 | **NEW to corpus** (grep confirmed not present in any prior night). See Section (b) below. |

**Papers re-surfaced from prior corpus (rejected):**
- arXiv 2609.18019 (Model-Free Passive Execution) — Night 77.
- arXiv 2606.15715 (Hyperliquid adverse selection, sunshine trading) — Night 82.
- arXiv 2502.18625 (Market Maker's Dilemma, Binance BTC perp) — synthesis.
- arXiv 2608.04373 (Hyperliquid wallet-level adverse selection) — Night 92.

---

**What is genuinely NEW tonight:**

**arXiv 1803.05690 (Lehalle, Mounjid, Rosenbaum — "Optimal Liquidity-Based Trading Tactics," March 2018, q-fin.TR)**

This paper is NOT in the prior corpus. Grep against all 92 prior nightly files confirmed zero prior mention of arXiv 1803.05690.

Fetched tonight from https://arxiv.org/html/1803.05690v1.

**Authors / affiliation:** Charles-Albert Lehalle (Capital Fund Management / Imperial College London), Othmane Mounjid, Mathieu Rosenbaum (École Polytechnique, CMAP).

**Data:** Bund futures on Eurex, one week (1–5 September 2014), 3,407,574 event-level records with microsecond timestamps. NOT crypto. NOT equities.

**What the paper does:** Solves a stochastic control problem for a passive limit-order trader who can choose at each event: stay in the book, cancel (avoid adverse selection), or cross the spread (market order). The state variable is order book imbalance, I = (Q¹ − Q²) / (Q¹ + Q²). The paper derives the optimal three-action policy as a function of imbalance and remaining time.

**Direct quotes from fetched HTML:**

> "When imbalance is highly negative, it is optimal to cancel the order to avoid adverse selection."
> "sending a limit order in between first limits highly increases the adverse selection risk."
> "our optimal tactic enables us to outperform significantly naive execution strategies."

**Key finding (Figure 4, quantitative result from the fetched page):**

The optimal OBI-conditional policy achieves approximately **+2.4 ticks above the "join the bid" naive benchmark** in the T=100s, Δ=10s simulation window, driven primarily by the cancel-when-negative-OBI component of the policy.

**Why this is new vs. the prior 82 tweaks — and what it overlaps with:**

This paper provides a **second independent theoretical anchor** for Tweak 74 (stale-gate per-cycle re-validation, proposed Night 82). Tweak 74 proposes: while a ST2.0 resting order is live, re-check OBI and tape at every 60s cycle; cancel if gates no longer pass. The motivation cited in Night 82 was structural (arXiv 2607.28323's passive impact accumulation argument). The new paper (arXiv 1803.05690) provides the *optimal-control derivation* of the same mechanism: the theoretically optimal rule for a resting passive order is to cancel when OBI is negative (book no longer bid-heavy), not just to re-check gates stochastically.

**Structural difference from Tweak 74's current formulation:**

Tweak 74 re-validates both OBI AND tape buy_ratio gates jointly. arXiv 1803.05690 suggests OBI alone is sufficient as a cancel signal in the optimal policy — the OBI sign flip (from positive at entry to negative during the hold) is the trigger. This gives Tweak 74 a sharper formulation: the OBI channel (not just "both gates failed") may carry the majority of the adverse-selection avoidance gain.

**Why NOT a new tweak:**

The mechanism (OBI-based cancel of resting order) is covered by Tweak 74. This paper strengthens the existing Tweak 74 proposal with a rigorous theoretical derivation and a quantitative estimate of the benefit (2.4 ticks on Bund futures). It is corroborating evidence, not a structurally new idea.

**Classification:** New to corpus, verified (HTML fetched, direct quotes + Figure 4 result extracted). NOT a new tweak — provides theoretical backing and a sharper formulation hint for existing Tweak 74. Venue is Bund futures (Eurex), not crypto perps. Magnitudes (ticks, Eurex calibration) are not transferable.

---

## (b) Concrete Forward-Testable Execution Tweak

**No new tweak this night.**

arXiv 1803.05690 strengthens Tweak 74 theoretically but does not add a structurally new gate, timing signal, or measurement not already in the 82-tweak stack. The four search angles (LOB resilience, iceberg detection, cross-venue price discovery, post-only repricing) produced papers that were either:
- Agent-based simulations with no real data (arXiv 2607.16970, arXiv 2609.22785)
- Equity/FX venue — not crypto perps (arXiv 2603.28898, arXiv 1803.05690)
- Wrong problem domain — equity perp mark construction (arXiv 2608.09188)

The persistent gaps remain:
1. **SSRN 6693260** (Chang, BTC perp flow-adjusted bid-absorption proxy): still HTTP 403.
2. **Microstructure Lab Substack** (LOB resilience after sweeps, 180,590 events, Binance/GateIO/OKX): still paywalled.
3. **arXiv 2607.11888 equation 30** (full θ* optimizer for Tweak 77): still partially fetched.

**Refinement note for Tweak 74 (not a new tweak — an implementation sharpening):**

Based on arXiv 1803.05690's optimal control derivation, Tweak 74's cancel condition could be sharpened from "OBI and tape no longer pass both gates" to a **primary OBI-sign cancel** — cancel immediately if OBI has flipped from bid-heavy (>0) to offer-heavy (<0) at any point during the hold, rather than waiting for the full ±0.25 gate threshold to reverse. The paper's result shows the cancel region is when imbalance is "highly negative" — i.e., the full reversal from positive to clearly negative. Whether "highly negative" maps to OBI < 0, < −0.10, or the full < −0.25 entry threshold requires calibration against ST2.0's own resting-order data (which is why Tweaks 47/65 remain the #1 priority: without the fill data, calibration is impossible).

---

## (c) Caveats and Unverified Items

1. **arXiv 1803.05690: Bund futures (Eurex), NOT crypto perps.** The optimal policy (Figure 4) uses Eurex-specific tick size and imbalance calibration. The +2.4 tick gain cannot be translated to Phemex bps without re-calibrating k, λ⁺, λ⁻ on Phemex's own LOB data. The directional claim (OBI-negative → cancel is optimal) is structural and applies broadly, but the magnitude is Bund-specific.

2. **Paper's sign convention inconsistency.** The fetched HTML shows an inconsistency between Section 2.1 (agents cancel when imbalance is positive) and Section 5.2 (cancel when imbalance is negative). The likely interpretation is that the sign convention flips by buy/sell side: for a resting ask (passive short in ST2.0), cancel when OBI is negative (offer-heavy, no longer bid-heavy). This interpretation is structurally consistent with the synthesis result but has not been independently verified.

3. **arXiv 2603.28898's fast-cancel module.** The paper mentions it but gives no threshold, no bps figure, and requires FPGA-class latency. ST2.0 has no speed edge. The module's existence in an equity context confirms the mechanism is used in practice; it does not provide a deployable spec.

4. **JFR iceberg paper (Lajbcygier, 2025)** — HTTP 403 on direct fetch tonight. The search summary indicates: aggressive icebergs show higher price impact (information-driven); non-aggressive icebergs mostly supply liquidity. This is directionally consistent with existing corpus (informed flow concentrates in aggressive fills). No direct verification — labeled **UNVERIFIED.**

5. **Persistent unverified leads (unchanged from Night 92):**
   - SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): HTTP 403.
   - Microstructure Lab Substack (post-sweep LOB recovery, Binance/GateIO/OKX): paywalled.
   - arXiv 2607.11888 equation 30 (full θ* for Tweak 77): partially fetched.

6. **Literature saturation assessment (unchanged):** The standard q-fin.TR arXiv sweep, practitioner microstructure blogs, and SSRN crypto perp execution searches are saturating. Two consecutive nights (92 and 93) have produced no new actionable tweak. The highest-leverage next step remains empirical deployment of Tweaks 47/65.

---

## Summary

| Item | Description | Status |
|------|-------------|--------|
| arXiv 1803.05690 (Lehalle/Mounjid/Rosenbaum, 2018) | New to corpus: Bund futures optimal cancel rule — OBI-based cancel of resting passive order when book flips from bid-heavy to offer-heavy is theoretically optimal (≈+2.4 ticks vs. naive benchmark). Corroborates Tweak 74's OBI per-cycle re-validation; suggests sharper primary-OBI-sign cancel within that mechanism. NOT crypto-specific. | NEW — VERIFIED (HTML fetched, direct quotes + Figure 4); corroborates Tweak 74, no new tweak |
| Tweak 83 | None proposed. | N/A |

**Refinement note:** arXiv 1803.05690 supports sharpening Tweak 74's cancel condition to trigger on OBI sign flip (positive → negative) rather than waiting for the full entry threshold to invert. Threshold calibration (< 0, < −0.10, or < −0.25?) requires ST2.0 fill data — which is why Tweaks 47/65 are prerequisite.

**Unverified leads (persistent):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry + LOB recovery timing (Microstructure Lab Substack) | TBD | UNVERIFIED — paywalled |
| — | arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77) | TBD | PARTIALLY FETCHED |

**Undeployed priority stack (unchanged from Night 92):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging
2. Tweak 75 — OBI upper-bound gate
3. Tweak 76 — Realized-vol gate
4. Tweak 77 — σ-adaptive cancel threshold
5. Tweak 78 — Gate hysteresis
6. Tweak 79 — Tape intensity gate
7. Tweak 74 — stale-gate per-cycle re-validation (now with two theoretical anchors: arXiv 2607.28323 + arXiv 1803.05690)
8. Tweak 72 — funding-window gate
9. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging
10. Tweak 71 — transient-order OBI filter
11. Tweak 80 — Quarter-hour proximity shadow log
12. Tweak 81 — Robust volume Z-score shadow log
13. Tweak 82 — FIFO time-to-fill queue classification

**Research series status:** 82 tweaks, 93 nights. Second consecutive night with no new actionable tweak. Literature saturation confirmed. The empirical deployment of Tweaks 47/65 is the only path to advancing beyond "proposed" on the most important hypotheses.
