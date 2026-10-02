**Night 79 | 2026-10-02 | Focus: Passive POST-ONLY limit SELL execution quality**

## (a) What's New vs. Prior Reports (Nights 1–78)

N77–N78 formally concluded the academic literature is saturated. Tonight rotated to **non-arXiv primary sources** — practitioner/exchange docs and recent practitioner publications — to check whether that saturation conclusion holds outside academic preprints.

**Prior corpus coverage (confirmed read):** Tweaks 1–66 covering spread gates, buy_ratio tightening, cancel-and-wait, queue-rank logging (Tweak 47/65 = #1 undeployed priority), OFI saturation gate (Tweak 57), OBI depth concentration (Tweak 59), price-deviation cancel/repost (Tweak 60), LOB cancel-state snapshot (Tweak 66). The key structural result — passive fills are adversely selected by construction, ST2.0 lacks the three compensations (speed, queue position, rebate) — established in 2026-06-20 synthesis and not revisited below.

**What is genuinely NEW tonight:**

- **Source A:** The Microstructure Lab (Substack, 2026-02), "Microstructure Essentials: Queue Position" — Feb 2026, OKX BTC-USDT, 11.6M limit order samples. **New verified data** for the queue-rank argument, not arXiv. Prior reports cited the Binance BTC perp study (arXiv 2502.18625) for queue-position effects. This source provides a second independent CEX perpetual dataset with concrete fill-rate and adverse-selection numbers by position.

- **Source B:** hftbacktest documentation, "Market Making with Alpha — Order Book Imbalance" — a live implemented strategy (Python, open source). **New execution mechanism not in prior tweaks:** continuous OBI-conditioned placement offset (shift limit price, not just a binary gate). Prior OFI/OBI tweaks (57, 59, 64) are binary gates or logging; this is the first verified reference for a *continuous price adjustment* approach.

- **Source C:** arXiv 2607.28323 (Balata et al., July 2026) — "Optimal Execution with Passive Market Impact." **Not found in N76–N78 rejected paper lists.** Empirically-calibrated exponential decay of fill probability with distance from mid, with a computable optimal posting depth. NASDAQ/FX data — not crypto-native, but the exponential decay principle is standard microstructure.

- arXiv 2408.03594 (Anantha & Jain, 2024) — Hawkes OFI forecasting. Verified fetched. Conceptually overlaps Tweak 57 (OFI saturation gate), but provides a specific forecasting mechanism. Treat as supporting evidence for Tweak 57, not a new tweak.

**What literature sweep skipped tonight:** Oct 2026 q-fin.TR confirmed empty in N77; not re-checked. Bybit Chase Order article timed out (marked UNVERIFIED below).

---

## (b) New Forward-Testable Execution Tweaks

### Tweak 67 — OBI-Conditioned Placement Offset (continuous price skew)

**Source:** hftbacktest docs — "Market Making with Alpha — Order Book Imbalance"
URL: https://hftbacktest.readthedocs.io/en/latest/tutorials/Market%20Making%20with%20Alpha%20-%20Order%20Book%20Imbalance.html
**Status: VERIFIED — page directly fetched.**

Quote:
> "fair_price = mid_price + c1 * alpha" where alpha = standardize(∑Q_bid^i − ∑Q_ask^i)

The hftbacktest implementation uses c1=160 for BTC, a 1-hour standardization lookback, and 2.5%-from-mid depth window, updating every 1 second.

**Mechanism for ST2.0:** When standardized OBI is large-positive (heavy bid pressure, i.e. the absorption signal that triggers ST2.0), shift the passive sell limit 1–2 ticks *higher* than best ask, rather than posting at best ask. When OBI compresses below a threshold (pressure exhausting), drop back to best ask.

**Hypothesis:** Posting slightly above best ask during peak absorption delay-filters fills to the post-peak window, reducing adverse selection from being filled while buyers are still actively sweeping. Trades fill rate for fill quality.

**Caveat:** This is market-making logic applied to a directional entry. The hftbacktest implementation quotes both sides; ST2.0 only posts a short side. The OBI skew may reduce fill rate below usable levels if the threshold is too aggressive. Requires forward lab testing, not parameter-based deployment.

**Implementation sketch:**
```python
# At ST2.0 entry, after existing gates pass:
obi_raw = sum(ob.bids[i][1] for i in range(5)) - sum(ob.asks[i][1] for i in range(5))
obi_z = (obi_raw - obi_mean_1h) / obi_std_1h   # rolling 1-hr z-score
offset_ticks = max(0, int(obi_z * OBI_SKEW_FACTOR))  # e.g. OBI_SKEW_FACTOR=0.5
limit_price = best_ask + offset_ticks * tick_size
# log: obi_z, offset_ticks, limit_price vs best_ask
```

**Forward-test criterion:** Fill rate by offset_ticks tier (0, 1, 2+) vs. post-fill 5s/1min adverse move. If offset_ticks=1 reduces adverse 0.3+ bps with ≤10% fill rate drop, keep. If fill rate drops >30%, gate is too aggressive.

**Priority:** Medium. Zero-risk instrumentation (log obi_z and what offset *would have been* without actually changing the price) is step one.

---

### Supporting data for Tweak 47/65 (already #1 priority — new evidence)

**Source:** The Microstructure Lab (Substack), "Microstructure Essentials: Queue Position"
URL: https://themicrostructurelab.substack.com/p/microstructure-essentials-queue-position
Data: OKX BTC-USDT perpetuals, February 2026, 11.6M limit order observations.
**Status: VERIFIED — page directly fetched.**

Quotes:
> "Both dimensions get worse as queue depth increases."
> "In BTC perpetuals, the gap between front (1.1 bps adverse) and back (3.0 bps adverse) is nearly 2 bps per fill."

| Queue Depth Ahead | Fill Rate | Adverse Selection |
|---|---|---|
| 7 BTC (front) | 82% | 1.1 bps |
| 1,075 BTC (back) | 3% | 3.0 bps |

The mechanism: front-of-queue orders are filled on all-touches (including uninformed bounces). Back-of-queue orders only fill when the level is swept by directional, informed flow — which is definitionally adverse for a passive order.

**For ST2.0:** This independently corroborates the Binance perp finding (arXiv 2502.18625: front −0.058 bps vs back −0.775 bps). Two independent CEX perp datasets, both confirming ~2–3× worse adverse selection at back of queue. ST2.0 posts-and-waits ~20s → almost certainly structural back-of-queue. Tweak 47/65 (log `queue_rank_proxy` and `time_to_fill`) remains the highest-value undeployed action.

---

### Tweak 68 — Optimal Posting Depth Exploration (exponential decay calibration)

**Source:** arXiv 2607.28323, "Optimal Execution with Passive Market Impact," Balata et al., July 2026.
URL: https://arxiv.org/abs/2607.28323
**Status: VERIFIED — abstract page fetched. Full text not accessed.**

Quote from abstract:
> "approximately exponential decay of limit-order fill probabilities with distance from the midprice"
> "a trade-off between higher fill intensity and larger accumulated impact on the one hand, and lower impact but greater non-execution risk on the other"

**Mechanism:** There is an empirically-computable optimal posting depth that minimizes the sum of adverse selection cost and non-execution opportunity cost. Posting too close to mid = more fills but more adverse-selected fills. Posting too deep = cleaner fills but near-zero fill rate.

**For ST2.0:** Currently always posts at best ask (distance = 0). The exponential decay principle (NASDAQ/FX-calibrated) suggests testing 1-tick-off variants. Note: full paper data is NASDAQ/FX, not crypto perp. The shape principle is robust; the actual optimal depth requires Phemex-specific empirical calibration.

**Forward-test criterion:** Paper lab test posting at [best_ask, best_ask+1, best_ask+2] ticks. Track fill rate, adverse-selection-at-fill, and win rate by depth tier. Expected: fill rate drops sharply at +2 ticks; adverse selection bps improves at +1. Accept +1 if win rate delta is positive.

**Priority:** Low-medium. Requires Tweaks 47/65 (queue rank + fill time logging) first to understand *why* current fills are adverse before adjusting *where* to post.

**Caveat:** arXiv 2607.28323 is NASDAQ equities + FX. The exponential decay shape transfers; the exact decay constant does not. Do not use the paper's numerical outputs as Phemex thresholds.

---

## (c) Caveats and Unverified Items

1. **Bybit "Chase Order" feature (UNVERIFIED):** Search snippets describe a ~1s reprice cadence, post-only enforced, up to 5% offset from mid. Page URL: https://www.bybit.com/en/help-center/article/Chase-Order. Could not be fetched (timed out twice). Architecture is plausible and consistent with how other exchanges implement repricing. If Phemex has an equivalent undocumented mechanism, it is not exposed in the standard ccxt API layer. Do not rely on this until verified against Bybit docs directly.

2. **arXiv 2408.03594 (Hawkes OFI forecasting):** Verified fetched. Data is NSE (Indian equities), not crypto perp. The conceptual mechanism (forecasted OFI as adverse selection indicator) transfers; specific Hawkes decay parameters do not. Treat as motivation for Tweak 57 (OFI saturation gate), not a new tweak.

3. **hftbacktest OBI parameters (c1=160, 1-hr lookback, 2.5% depth):** These are calibrated for BTC on the hftbacktest backtest environment. Do not transplant these numbers to Phemex ST2.0. They establish the mechanism is viable; calibration must be Phemex-native.

4. **arXiv 2607.28323 full text:** Only abstract accessed. The numerical optimal-depth results are in the full paper (paywalled or not yet on arXiv full-text). Abstract confirms the conceptual result; specific parameters require the full paper.

5. **Literature saturation stands:** N77–78 reached this conclusion; N79 confirms it for non-arXiv practitioner sources as well. No new papers were found via the academic preprint pipeline. The two new practical sources (Microstructure Lab, hftbacktest) are practitioner-grade verified, not peer-reviewed.

---

## Priority Ordering (Undeployed Actions) — Updated from N78

| Priority | Tweak | Action |
|---|---|---|
| 1 | 47/65 | `queue_rank_proxy` at posting + `time_to_fill` at fill |
| 2 | 45/48 | `spread_pct` logging at every attempt |
| 3 | 46 | `v_prior_sell` logging |
| 4 | 53 | `seconds_to_qh` logging |
| 5 | 56 | `aggressor_ratio_at_attempt` logging |
| 6 | 57 | `ofi_percentile_at_attempt` logging |
| 7 | 67 (NEW) | OBI z-score logging + shadow offset calculation |
| 8 | 58 | `spread_ratio_at_attempt` logging |
| 9 | 59 | `st2_ofi_depth_ratio` logging |
| 10 | 60 | `adverse_move_bps_at_cancel` + `cancel_reason` logging |
| 11–16 | 61–66 | VPIN, cycle offset, symbol OBI/outcome, flow_imbal, cancel-state snapshot |
| 17 | 68 (NEW) | Posting depth exploration (requires Tweak 47/65 data first) |

## Cumulative Tweak Count

| Category | Count |
|---|---|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 48 (Tweaks 4–66 + 67 + 68) |
| New candidates tonight | 2 (Tweak 67: OBI price offset; Tweak 68: optimal posting depth) |
| Supporting data for existing tweak | 1 (New OKX dataset → Tweak 47/65 evidence) |
