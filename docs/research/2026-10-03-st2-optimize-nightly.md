**Night 80 | 2026-10-03 | Focus: Passive POST-ONLY limit SELL execution quality**

## (a) What's New vs. Prior Reports (Nights 1–79)

N77 formally declared the academic literature saturated. N78 found nothing. N79 rotated to practitioner sources and added Tweaks 67 (OBI-conditioned continuous price skew) and 68 (exponential-decay optimal posting depth). Tonight is the first pass post-saturation that catches September 2026 arXiv submissions (2609.XXXXX range).

**Prior corpus coverage:** Tweaks 1–68 covering spread gates, queue-rank logging (Tweak 47/65 = #1 undeployed priority), OFI/OBI gates (57, 59, 64), price-deviation cancel/repost (Tweak 60), continuous OBI placement offset (Tweak 67), exponential-decay depth calibration (Tweak 68). Structural constraint is unchanged: passive fills adversely selected by construction; ST2.0 lacks speed, queue position, and rebate compensation.

**What is genuinely NEW tonight:**

- **arXiv 2609.18019 (September 16, 2026)** — "Model-Free Passive Execution via Order-Level Shadowing" by Vincent Maciejewski. VERIFIED — abstract page fetched. This paper is from *after* the N77 saturation declaration and was not in any prior report's rejected list. The central mechanism (Shadow-PPOV) is: observe a third-party resting passive order by order ID, post at the same price, and cancel with identifier-based cancellation when that order is withdrawn. Evaluated on CME ES futures, not crypto. The paper's finding: "information is inherited from the flow rather than derived from a model."
  
  **Direct applicability to ST2.0:** Shadow-PPOV requires level-3 order book data (order IDs) which Phemex's API does not expose. NOT directly implementable. However, the paper provides a *structural insight*: the mechanism's cancel trigger (withdraw when the resting order you're shadowing withdraws) has an observable proxy — a sharp drop in depth at your posting level *without* a corresponding fill. This derivative concept is new relative to all prior tweaks.

- **arXiv 2607.09230 (July 2026)** — "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures" by Joohyoung Jeon. VERIFIED — abstract page fetched. Uses Binance BTCUSDT/ETHUSDT futures 2023–2026. Finding: "for ETH it is present across calm, mixed, and stressed regimes and largest under stressed pre-event liquidity, whereas BTC shows only isolated five-minute passes." **Not new vs. prior work** — this reinforces Tweak 63 (ETH OFI reliability > BTC). No new tweak warranted.

- **arXiv 2608.04373 (August 2026)** — "Public Trader Identity: Adverse Selection and Return Predictability" by Daojing Zhai. VERIFIED — abstract page fetched. Studies Hyperliquid DEX with public wallet addresses, 14.3M aggressive orders. Not applicable: Phemex is a CEX without persistent public wallet identifiers and ST2.0 is a maker (passive), not a taker. Rejected.

---

## (b) Concrete Forward-Testable Execution Tweaks

### Tweak 69 — Queue-Depletion Cancel Trigger (shadow-PPOV derivative)

**Source:** arXiv 2609.18019 — Maciejewski, "Model-Free Passive Execution via Order-Level Shadowing," September 2026.  
**Source URL:** https://arxiv.org/abs/2609.18019  
**Verified:** Yes — abstract fetched. Full paper not fetched (CME ES, not crypto-native — full read not warranted).

**Structural insight from the paper:**  
Shadow-PPOV cancels when the large resting order it tracks withdraws. The logic: if the order ahead of you in queue disappears *without consuming you*, it was withdrawn (not filled), meaning the price level is going stale or a directional sweep is incoming. The same signal exists on Phemex without order IDs: if the total depth at your resting ask price drops sharply *and you were not filled*, the top-of-queue position was cancelled or swept clean — both are cancel signals for ST2.0.

**Proposed implementation:**  
At each bot cycle while ST2.0 has a resting POST-ONLY ask:
1. Snapshot `depth_at_ask_level` = sum of all resting ask volume at ST2.0's exact posting price.
2. If `depth_at_ask_level` drops by >50% from the snapshot taken at posting time, AND no fill received → cancel and wait 1 cycle before reposting.
3. Log `queue_depletion_cancel=True` + `depth_drop_pct` for replay analysis.

**Why this is new vs. Tweak 60:**  
Tweak 60 (price-deviation cancel/repost) triggers on adverse *price movement*. Tweak 69 triggers on *queue exhaustion without fill* — the complement case: price hasn't moved yet but the queue ahead is being cleared, making your fill imminent and adversely selected. Two orthogonal cancel signals.

**Forward testability:** Binary flag on cancel events; no parameter tuning required until replay data exists.  
**Implementation complexity:** Low — requires one LOB depth lookup per cycle while order is resting.  
**Caveats:** Phemex's L2 feed aggregates depth at each price level; individual order visibility is unavailable. The 50% threshold is arbitrary — calibrate from Tweak 66's cancel-state snapshot data once deployed.

---

## (c) Caveats and Unverified Claims

- The full text of arXiv 2609.18019 was not fetched. The abstract confirms the mechanism. The CME ES dataset (not crypto, not perpetual) means the fill-rate numbers cited in that paper are NOT applicable to ST2.0's Phemex context. The structural insight (queue-depletion as cancel signal) is the only portable finding.

- The 50% depth-drop threshold in Tweak 69 is **unverified** — it's a starting point. Calibration requires the Tweak 66 cancel-state snapshot data that has not yet been deployed and collected.

- arXiv 2607.09230 was verified but adds nothing beyond reinforcing Tweak 63 (ETH OFI more reliable than BTC). Treat as corroboration, not a new finding.

- The remaining structural gaps identified in N77 remain open: no primary source found for Phemex-calibrated adverse-selection measure, no crypto-perp native OFI signal decay study, no passive-maker markout paper on CEX perpetuals. These gaps are confirmed to persist after N80.

---

## Summary

**New this night:** 1 genuinely new paper post-N77 saturation (arXiv 2609.18019, Sep 2026). Not directly implementable (requires level-3 order IDs), but the structural concept translates to an implementable proxy: cancel the resting ask when depth at posting level drops >50% without fill.

**Tweak count:** 69 total (3 deployed, 66 undeployed).

**Priority remains unchanged:** Deploy Tweaks 47/65 (queue_rank_proxy + time_to_fill logging) first — they are still the #1 undeployed priority and gate all calibration work including Tweak 69's threshold tuning.
