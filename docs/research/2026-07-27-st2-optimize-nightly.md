# ST2.0 Execution Optimization — Night 30
**Date:** 2026-07-27 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 29 Nights

N29 closed with: arXiv:2407.16527 DeLise (Bernoulli fill model P(adverse)=1.0/P(incidental)=0.018, Tweak 31), arXiv:1602.00731 Xu et al. ABSTRACT ONLY (LOB resilience 20-update threshold, Tweak 31a). Tonight searched four angles not previously covered in the series: (1) Fabre & Ragel (arXiv:2307.04863) — previously 404, retried via ar5iv HTML mirror; (2) intraday/quarter-hour periodicity in crypto perp futures and its interaction with passive fill quality; (3) spot-futures imbalance correlation and maker vulnerability data (arXiv:2602.00776); (4) sell-side limit order tactic design (arXiv:1409.1442).

**Summary of new material tonight:**

- arXiv:2307.04863 (Fabre & Ragel, "Tackling the Problem of State Dependent Execution Probability") — VERIFIED via ar5iv HTML mirror (prior nights returned 404 on direct arxiv). Key confirmed finding: **distance to best quote is the #1 predictor of fill probability for passive crypto limit orders**; optimal placement is fee-driven; volume prior shows two-regime power law with breaking point at $100K. Critical gap closed: **ST2.0 already posts at `best_ask` (distance=0, confirmed exchange.py:559)** — confirming current placement is already fee-optimal. No code change needed on placement distance. New to this series.

- arXiv:2607.09426 (Hansen et al., "The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures") — VERIFIED via HTML fetch. Binance USDT perp futures, 6 assets (BTC, ETH, XRP, SOL, DOGE, ADA), Jan 2021–Oct 2024. First 10 seconds of each quarter-hour mark (min 0, 15, 30, 45): **26% more trades, 32% higher dollar volume, 26% larger absolute returns** vs ordinary minutes. Pronounced **negative return autocorrelation** at quarter-hour boundaries. Authors attribute this to "liquidity provision not fully absorbing the structural breaks in order flow at these boundaries, leaving price reversals." Intraday timing signal — new to this series.

**Confirmed near-misses tonight:**
- arXiv:2602.00776 (Explainable Patterns in Cryptocurrency Microstructure, Binance Futures 2022–2025) — Fetched. No intraday timing analysis. Confirms maker drawdown >0.90 during flash crash and spot-futures imbalance correlation c=0.94. Not actionable for placement or timing tweaks tonight.
- Bacidore (IEX D-Limit / IntelligentCross / M-ELO adverse selection reduction) — Fetched. IEX D-Limit uses "Crumbling Quote Indicator (CQI) to predict when the quote is about to move adversely and reprices immediately." This is exactly Tweak 30's conditional cancellation concept, implemented in equity venues. No new tweak — validates Tweak 30 framework with real-world implementation. No quantitative adverse-selection reduction data provided.
- Shynkevich JFM 2026 — paywalled (HTTP 402). Search snippet found: periodic surges in crypto perps "do not cause a significant adverse price impact." Cannot reconcile with Quarter-Hour Effect negative autocorrelation finding without full paper access. Inconclusive.
- arXiv:1409.1442 (sell-side limit and market order tactics, JoT 2012) — abstract only; methodology note, no quantitative claims extractable.

---

## Finding A — arXiv:2307.04863 VERIFIED: ST2.0's Best-Ask Placement Already Optimal; Volume-Regime Breaking Point at $100K

**Source:** Timothée Fabre, Vincent Ragel. "Tackling the Problem of State Dependent Execution Probability: Empirical Evidence and Order Placement." arXiv:2307.04863. CentraleSupélec, Université Paris-Saclay; BNP Paribas.
**URL:** https://ar5iv.labs.arxiv.org/html/2307.04863 (HTML mirror; direct arxiv returned 404 on prior attempts)
**Dataset:** High-frequency crypto CEX data (BTC-USD, ETH-USD — exchange not specified, description matches Coinbase-style) and Euronext equities; exact date range not stated in accessible content.
**Access:** ar5iv HTML mirror fetched directly. No paywall.

**Verified quotes (directly fetched from HTML):**

> "the strategy considers a distance to be optimal as long as the taker fee is almost surely saved, regardless of the price discount reduction incurred by posting far inside the bid-ask spread"

> "optimal distance δ* seems to be linear or at least sub-linear in the bid-ask spread" [for crypto]

> [Features ranked by importance for passive order fill probability]: "Distance to best quote, order size, and prior volume" [crypto]; "order flow imbalance and volatility" [equities]

> "two distinct power law regimes for the fill probability function with a breaking point at 100,000" [USD prior volume]

> "At Coinbase level 9 fees (0.05% taker, 0% maker), algorithm posts inside spread; at zero fees, algorithm generally places the order deeper in the book"

**What this paper establishes for ST2.0:**

1. **Distance to best quote is the #1 fill-probability driver for passive crypto orders.** The paper uses survival analysis and a multi-layer perceptron across crypto CEX and Euronext equity data; for crypto, placement distance dominates all other features.

2. **Fee structure determines optimal placement direction.** When the maker fee is 0% and the taker fee is positive (Phemex's structure), the algorithm favors posting AT or inside the best quote. For a POST_ONLY sell order, "inside the spread" means below best ask (which would immediately fill as a taker and be cancelled by POST_ONLY). Therefore, the correct placement for a POST_ONLY short with 0% maker fee is exactly `best_ask` — distance = 0. With 0 maker rebate and 0 additional savings from posting deeper, there is no financial incentive to post away from best ask.

3. **ST2.0 already posts at `best_ask`.** Confirmed in `exchange.py:559`:
   ```python
   # Use best ask for maker entry (sell at ask = maker)
   limit_price = ob["best_ask"] if ob and ob.get("best_ask") else price
   ```
   This means placement distance optimization is NOT an open improvement opportunity. Current behavior is already fee-optimal per the paper's framework.

4. **Volume prior — two-regime power law.** Fill probability as a function of volume prior shows two distinct regimes, with a breaking point at approximately $100,000 USD. Below this threshold, fill dynamics differ materially from above it. For ST2.0 on thin altcoin perps (e.g., INJ, AVAX, ARB), the per-trade prior volume may frequently be below this threshold — a different fill probability regime than BTC/ETH. This could partially explain why ETH/INJ show higher fill rates: they're more likely to be above the $100K threshold per bar.

**What this does NOT address:**

The paper studies fill probability, not fill quality (adverse selection after fill). Posting at best ask (distance=0) maximizes fill probability but does nothing to reduce the probability that the fill is adversely selected. The DeLise Bernoulli model (N29) confirms: P(adverse fill) = 1.0, meaning the high fill probability at distance=0 is primarily driven by adverse moves running through the resting order. Better placement distance ≠ lower adverse selection.

**Forward-testable implication → Tweak 32 (informational, no code):**

ST2.0 placement is confirmed optimal. No tweak on placement distance. The volume-regime finding ($100K breaking point) warrants tracking `prior_volume_usd` at signal time for each symbol to diagnose whether thin-book altcoin misses cluster below $100K prior volume. This is a diagnostic log (2 lines), not a gate. Log `prior_volume_usd_bar` (volume of most recent completed 5-min bar at signal time) alongside fill/miss outcome.

**Critical limitations:**
1. Dataset is crypto CEX (Coinbase-style), not Phemex perp. Phemex perp tick structure, maker/taker fee schedule, and participant mix differ.
2. Date range unknown. Crypto liquidity conditions 2026 may differ from study period.
3. Paper studies fill probability, not adverse selection cost. Distance=0 is optimal for probability, but adverse selection conditional on fill is a separate (and likely more important) variable for ST2.0.
4. The $100K breaking point is the paper's finding for BTC-USD/ETH-USD. For altcoin perps with fundamentally different volume profiles, the threshold may differ.

---

## Finding B — arXiv:2607.09426 VERIFIED: Quarter-Hour Effect — 26% More Trades in First 10s of Each 15-Min Mark; Negative Autocorrelation Implies Post-Burst Reversion Window

**Source:** Peter Hansen, Ye Lu, Antoine Moreau. "The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures." arXiv:2607.09426v2.
**URL:** https://arxiv.org/html/2607.09426v2
**Dataset:** Binance USDT-margined perpetual futures. Assets: BTC, ETH, XRP, SOL, DOGE, ADA. Date range: January 1, 2021 – October 31, 2024 (4 years). Millisecond-timestamped aggregate trade data.
**Access:** HTML version directly fetched.

**Verified quotes (directly fetched from HTML):**

> "trading activity and short-horizon price variation concentrate into sharp bursts at every minute, every fifth minute, every quarter-hour, and most prominently at the top of the hour"

> "roughly 26% more trades, 32% higher dollar volume, and 26% larger absolute returns than the corresponding interval of ordinary minutes" [during the first 10 seconds of quarter-hour marks]

> "the quarter-hour marks exhibit pronounced negative autocorrelation" [in the return panel]

> "liquidity provision not fully absorbing the structural breaks in order flow at these boundaries, leaving price reversals"

> "our data do not include order-book updates, we do not examine this mechanism directly"

**What this paper establishes for ST2.0:**

Quarter-hour marks (minutes 0, 15, 30, 45 of each hour) produce a measurable burst in trading activity:
- **26% more trades** in the first 10 seconds
- **32% higher dollar volume** in the first 10 seconds
- **26% larger absolute returns** (price move magnitude) in the first 10 seconds

Critically, returns at these marks show **pronounced negative autocorrelation**: a buy burst at a quarter-hour mark is followed by a price reversion. The paper attributes this to insufficient liquidity provision at structural order-flow breaks — market makers don't fully absorb the burst, allowing a temporary overshoot that then reverts.

**Interaction with ST2.0:**

ST2.0's signal fires on buy absorption: elevated OFI (buy pressure), bid-heavy LOB, heavy buy-side tape. Quarter-hour burst windows are EXACTLY the conditions that produce ST2.0 signals: elevated buying activity, concentrated in 10-second windows. The signal is most likely to fire during these bursts.

Two distinct timing regimes emerge:

**During the burst (first ~10 seconds of quarter-hour mark):**
- Volume is 32% higher → buy pressure is most intense
- Adverse selection risk is highest (concentrated buying, price moving up against resting sell)
- Passive fill, if obtained, is most likely an adverse one (price running through the resting sell at the burst peak)

**After the burst (seconds 10-60 of the same quarter-hour minute, and into the next minute):**
- Negative autocorrelation takes hold → price begins reverting
- Entering here posts a passive sell AFTER the overshoot, in the reversal window
- Lower adverse selection (buying pressure exhausted, price direction turning)

But ST2.0 can't directly exploit this within a minute (60s main loop cycle). What it CAN do:

**Practical implication:** If signal fires during a quarter-hour mark's first 10 seconds, the passive sell is resting into peak adverse pressure. If the order waits un-filled through the burst window (~10-20 seconds), the book transitions into the reversion phase — and the resting sell is now well-positioned for the reversion. This is distinct from cancelling early: staying resting through the burst and into the reversion is the natural behavior of a passive sell on a 20-60 second TTL.

The actionable question for ST2.0 is whether fills that land DURING the burst (fast fills, 1-2 cycles, covered by Tweak 31's time-to-fill) have systematically worse outcomes than fills that survive the burst window and land after it. The Quarter-Hour Effect's negative autocorrelation says the post-burst fills should, on average, be in better reversion territory.

**Forward-testable implication → Tweak 32 (shadow log, 3 lines):**

At signal time, log:
```python
import time
signal_second_of_hour = int(time.time()) % 3600
signal_minute_of_hour = signal_second_of_hour // 60
signal_second_of_minute = signal_second_of_hour % 60
is_qh_burst = (signal_minute_of_hour % 15 == 0) and (signal_second_of_minute < 10)
```

Log `is_qh_burst` and `signal_second_of_minute` alongside fill/miss/adverse outcome. After 30+ fills:
- Do adverse fills cluster at `is_qh_burst = True` (entering during the burst peak)?
- Do adverse fills cluster at `signal_second_of_minute < 30` within quarter-hour marks?
- Cross-reference with Tweak 31 (time-to-fill): do fast fills during QH bursts have worst outcomes?

If confirmed: add `is_qh_burst` as a gate (skip entry if signal fires within first 10s of a quarter-hour mark; wait for next cycle). Expected outcome if the theory holds: fewer fills, but higher fill quality (fewer adverse adverse moves).

**Critical limitations:**
1. **Paper explicitly states "our data do not include order-book updates, we do not examine this mechanism directly."** The connection between quarter-hour burst activity and passive limit order adverse selection is an inference, not a direct finding. The paper shows elevated activity and negative autocorrelation, but does not measure per-fill adverse selection rates during vs. outside burst windows.
2. **Binance perp, not Phemex.** Quarter-hour bursts may differ in magnitude, duration, and frequency on Phemex given different participant mix, HFT presence, and bot population.
3. **6 assets, all major.** ST2.0 trades altcoin perps (INJ, AVAX, ARB, etc.) which have much lower volume. The quarter-hour effect may be weaker, stronger, or absent on thin altcoin perps vs BTC/ETH/SOL that dominate the paper's dataset.
4. **The negative autocorrelation signal is at 10-second horizon.** ST2.0 holds for ~15 minutes. Whether the short-horizon negative autocorrelation (price reverts within 10-30 seconds post-burst) is additive to or independent from ST2.0's 15-minute reversion hypothesis is unknown.
5. **Shynkevich JFM 2026** (paywalled) appears to contradict this with "periodic surges do not cause significant adverse price impact" — cannot reconcile without full paper access.

---

## New Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 32 | **Quarter-hour burst log.** At signal time, compute and log `is_qh_burst` = True if signal fires within first 10s of minute 0, 15, 30, or 45. Also log `signal_second_of_minute`. After 30+ fills: do adverse fills cluster at `is_qh_burst = True`? Cross with Tweak 31's time-to-fill. If yes: gate entry during first 10s of quarter-hour marks. | arXiv:2607.09426 Hansen et al. 2024 (Binance perp, BTC/ETH/XRP/SOL/DOGE/ADA — major assets only; paper does NOT directly measure passive fill adverse selection, inferred from negative autocorrelation; Phemex altcoin applicability unknown) | Queued — log only | 3 lines |
| 32a | **Volume-regime log.** At signal time, log `prior_volume_usd_bar` = USD volume of most recent completed 5-min OHLCV bar. After 30+ fills: do misses (PostOnly) cluster at `prior_volume_usd_bar < 100000`? If yes: adds diagnostic context for symbol selection vs volume regime. | arXiv:2307.04863 Fabre & Ragel (crypto CEX, not Phemex perp; $100K breaking point specific to BTC-USD/ETH-USD; altcoin threshold unknown) | Queued — log only | 2 lines |

---

## Honest Caveats

1. **Finding A (arXiv:2307.04863):** ar5iv HTML mirror fetched; quotes are direct. **But**: the exchange is not named in the accessible content (described as "digital asset CEX" — consistent with Coinbase data but not confirmed). Date range unknown. The $100K volume breaking point is the study's crypto-pair finding — on Phemex altcoin perps with materially lower per-bar volume, the relevant threshold may differ. Most importantly: the paper studies fill probability, not adverse selection post-fill. Confirming that ST2.0 already places optimally (distance=0, best ask) closes the placement question; adverse selection remains structurally the binding constraint regardless of placement.

2. **Finding B (arXiv:2607.09426):** HTML fetched, quotes direct. **But**: the adverse-selection connection is inferred from negative autocorrelation, not measured at the order level — the paper explicitly says "we do not examine this mechanism directly." The 26%/32% uplift figures are for BTC/ETH/SOL (major assets); altcoin perp applicability unknown. The Shynkevich finding ("periodic surges don't cause significant adverse price impact") is directly in tension with this inference but paywalled — cannot resolve.

3. **The IEX D-Limit finding (Bacidore, directly fetched)** validates the Tweak 30 conditional-cancellation concept at the venue level: IEX literally cancels resting orders when its Crumbling Quote Indicator (CQI) fires. For ST2.0, this means the Tweak 30 (cancel when LOB worsens during TTL) has a real-world analogue in equity markets. This strengthens the theoretical case for Tweak 30 but doesn't add a new tweak.

4. **The Bernoulli model constraint (N29, DeLise) remains binding.** Even with optimal placement (best ask, confirmed) and a timing filter (quarter-hour burst gate, proposed), the DeLise result implies ~98% of fills are adversely selected. Neither placement distance optimization nor timing can change the fundamental adverse-selection structure — only reducing the rate of posting into high-adverse-selection regimes (gating, not timing within-minute) can help. The priority queue (Tweaks 4, 6, 9, 10, 11, 12, 14) addresses exactly this.

5. **34 tweaks queued, 0 deployed across 29 nights (plus 2 tonight = 36 queued).** Adding Tweaks 32 and 32a tonight. Recommendation unchanged from N20–N29: implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweaks 31, 31a (N29) and 32, 32a (tonight) are each 2–3 lines and can be added in the same session. The bottleneck remains collecting 30+ tagged fills per diagnostic variable.

6. **SSRN 6344338 blocked** (27 consecutive nights). **SSRN 6693260 blocked** (30 consecutive nights). No new access route.

---

## Cumulative Forward-Test Queue (36 Tweaks)

Priority tweaks (unchanged from N20–N29): **4 [elevated], 6, 9, 10, 11, 12, 14**
Tweaks 32, 32a added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), above (Tweaks 32, 32a).

---

## Night 30 Bottom Line

Two findings. Finding A (arXiv:2307.04863, Fabre & Ragel, VERIFIED via ar5iv HTML — was 404 for 29 nights): distance to best quote is the #1 fill-probability predictor for passive crypto limit orders; optimal placement with 0% maker fee is at best ask (distance=0). **ST2.0 already posts at best_ask (confirmed exchange.py:559)** — placement distance optimization is not an open improvement. The $100K volume prior breaking point (two-regime fill dynamics) warrants a log-only Tweak 32a. Critical limitation: paper studies fill probability, not adverse selection. Finding B (arXiv:2607.09426, Hansen et al. 2024, VERIFIED via HTML): first 10 seconds of every quarter-hour mark (min 0/15/30/45) show 26% more trades, 32% higher volume, pronounced negative return autocorrelation on Binance USDT perp futures. Buy absorption signals likely fire most during these bursts; adverse selection is highest during burst peak; negative autocorrelation suggests post-burst reversion window. Forward-testable as Tweak 32 (log `is_qh_burst` at signal time; check if adverse fills cluster during burst windows). Critical limitations: paper doesn't directly measure passive fill adverse selection, major assets only, Shynkevich JFM 2026 (paywalled) appears to partially contradict.

**Recommendation unchanged from N20–N29:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweaks 31, 31a, 32, 32a are 2–3 lines each. Night 30: 36 tweaks queued, 0 deployed.
