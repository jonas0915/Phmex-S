# ST2.0 Execution Research — Nightly (2026-06-24)

**Scope:** New execution material only — no repetition of prior reports.

Prior covered (full list — skip anything from this set):
- Adverse selection by construction: fills cluster at extreme imbalance (arxiv 2502.18625, 1610.00261)
- Binance BTC perp imbalance-maker without cancellation: −0.47 bp mean over 8,851 trades
- Queue position: front −0.058 bp vs back −0.775 bp; speed requirement for cancel/reinsert
- Phemex rebate = 0; δ = half-spread only, frequently beaten by adverse-selection β
- OFI-flip concept; post-offset / deeper-in-spread variants
- CQI / Crumbling Bid pre-entry gate (IEX SEC Release 34-89686)
- Trade-OFI outperforms LOB-OFI for entry timing (arxiv 2507.22712)
- Post-entry cancellation on persistent informed flow (unverified hypothesis, paywalled primary)
- Fill predictability AUC: 0.72 @1min → 0.66 @10min (deep-lob-2021)
- Cross-asset adverse selection stability (arxiv 2602.00776)
- Funding-window gate: U-shaped adverse selection around 00:00/08:00/16:00 UTC (SSRN 4218907)
- Negative drift of limit order fill: 100% fill rate on adverse moves (arxiv 2407.16527)
- OFI Signal Half-Life ~120 seconds → 90s limit order expiry gate (Coinmonks secondary source)
- VPIN Pre-Entry Toxicity Gate (practitioner blog / Easley et al. framework, uncalibrated)

---

## What Is NEW Tonight

### 1. Micro-Price as Dynamic Placement Reference

**Sources:**
- Stoikov, S. (2017). "The Micro-Price: A High Frequency Estimator of Future Prices." SSRN 2970694.
  (Primary academic source. Full text blocked via SSRN tonight — 403. Existence confirmed via
  multiple search results and citations. Formula extracted from citing paper below.)
- arxiv 2411.13594v1, "High Resolution Microprice Estimates from Limit Orderbook Data Using
  Hyperdimensional Vector Tsetlin Machines" (Fetched HTML directly.)

**The formula (from arxiv 2411.13594, verbatim):**
> "I = Qb/(Qb + Qa)" [top-of-book imbalance, where Qb = best-bid volume, Qa = best-ask volume]
> "Pmicro = M + g(I,S)" [M = midprice, g = adjustment function of imbalance and spread]
> "the microprice, a high-frequency estimator of future prices... The microprice is constructed as
>  'the limit of expected future mid-prices, taking into account the top of the book orderbook
>  state variables imbalance and spread.'"

**Numerical result (from fetched text, TSLA equities data):**
> "adjusted error averaged 0.0619 versus standard microprice error of 0.0925 across six trading
>  days — approximately 33% reduction"

**From search result aggregation (multiple sources consistent on this):**
The micro-price is a martingale by construction — it is the "fair value" of the asset given the
current LOB state, adjusted for the probability that either queue depletes first. The simplified
closed-form: when bid volume is large (I → 1), micro-price approaches the ask (market expects
upward move); when ask volume is large (I → 0), micro-price approaches the bid.

**The standard practitioner formula, consistent across multiple search results citing Stoikov 2017:**
```
P_micro = P_ask × (V_bid / (V_bid + V_ask)) + P_bid × (V_ask / (V_bid + V_ask))
```
Note the CROSSED weights: bid PRICE weighted by ask VOLUME, ask PRICE weighted by bid VOLUME.
This encodes: heavy bid queue → expects upward tick → micro-price tilts toward ask.

**The ST2.0 implication — NEW, not stated in any prior report:**

All prior reports addressed WHERE to post (deeper-in-spread) and WHEN to post (OFI-flip,
crumbling bid, trade-OFI confirmation). None addressed WHAT PRICE to use as the threshold for
"our limit is above fair value." The micro-price provides that threshold.

For a passive SELL limit at price `L`:
- If `P_micro > L`: the market's current "fair value" estimate exceeds our limit price. We are
  posting BELOW fair value — the fill we get will almost certainly be a fill where price ticked
  UP through our limit (adverse by construction). The micro-price check quantifies exactly this.
- If `P_micro ≤ L`: our limit is AT OR ABOVE current fair value. We are posting at the "right"
  side of the market's current estimate.

**Concrete placement rule:** Before posting the ST2.0 limit sell, compute P_micro from the
current top-of-book bid/ask volumes and prices. Only post if `P_micro ≤ intended_limit_price`.

**Why this is different from existing gates:**
- The OFI-flip gate says "wait for buy pressure to roll over (directionality)."
- The micro-price gate says "our specific price must be at or above the current fair value estimate."
- They address different failure modes: OFI-flip guards against posting too early; micro-price
  guards against posting at the wrong price level even after OFI rolls over.
- The check is DYNAMIC and self-calibrating: in heavy imbalance, P_micro → P_ask. If our limit
  is slightly inside the spread (e.g., at P_ask - 1 tick), the check will fail and block the
  entry. This naturally applies tighter placement requirements during the highest-imbalance
  (most adversely-selected) moments — exactly when ST2.0 is most at risk.

**Implementability:** All inputs are already in the bot's L2 data (`ob.bids[0]`, `ob.asks[0]`).
Computation is 2 lines. The check is a simple comparison before the order is placed.

**Caveat:** The Stoikov 2017 primary paper (SSRN 2970694) was inaccessible tonight (403).
The formula is extracted from a citing paper (arxiv 2411.13594, US equity data) and from
consistent practitioner descriptions across multiple sources. The original paper's quantitative
results for cryptoassets are NOT verified — the performance data (33% improvement) is from
TSLA equities. Transfer to Phemex crypto perps is an assumption. The rule is directionally
correct (posting below fair value = adverse by definition), but the magnitude of improvement
requires forward-testing. This is a placement discipline finding, not a "new alpha" claim.

---

### 2. Intraday Liquidity Depth Patterns: 20:00–23:00 UTC Is the Danger Zone

**Source:** Amberdata, "The Rhythm of Liquidity: Temporal Patterns in Market Depth" (blog.amberdata.io).
Fetched directly. **SECONDARY SOURCE — practitioner data blog, not peer-reviewed.**
Dataset described as "minute-by-minute orderbook data from summer 2025" for BTC/FDUSD on Binance.

**Fetched findings (verbatim):**
> "11:00 UTC...the optimal hour for execution, with $3.86 million in liquidity within 10 basis
>  points of the mid-price." (daily peak)
> "At 21:00 UTC...the same BTC/FDUSD pair now shows only $2.71 million in depth, a 42% reduction."
> "European session (08:00-16:00): $3.61M average (highest)"
> "Target 09:00-13:00 UTC for large orders" while avoiding "20:00-23:00 UTC unless necessary."
> "87% variation in available liquidity" across the 24-hour cycle.
> "the first 12 hours average +1.54% imbalance, while the second 12 hours shift to +3.18%"
>  — a doubling of bid-side imbalance in afternoon/evening UTC hours.
> "A trade that costs 3 basis points in slippage at one hour might cost 5 basis points at
>  another — a 67% difference in execution cost based solely on timing."

**The ST2.0 implication — NEW:**

The prior funding-window gate (blocks entry ±30 min around 00:00/08:00/16:00 UTC) addresses
settlement-period adverse selection. This is a different finding: it describes a **structural
low-liquidity zone (20:00–23:00 UTC)** — not tied to any settlement event — where the order
book is 42% thinner than peak. In thin conditions:
1. Bid-ask spreads widen → our passive sell limit is further from mid → worse adverse selection
   exposure if and when filled.
2. Thinner ask-side → our posted sell has less competing volume hiding it → more visible,
   more likely to be specifically targeted by informed flow.
3. The imbalance DOUBLES in the 12:00–24:00 UTC window (from +1.54% to +3.18% bid-side bias).
   For ST2.0, more frequent signal triggers in an already-thinner book = more adverse entries.

The 20:00–23:00 UTC window is distinct from all funding settlement windows and has not
appeared in any prior report.

**Why this is different from the funding-window gate:**
Funding settlements (00:00/08:00/16:00 UTC) are about informed flow SPIKING around settlement.
This is about aggregate liquidity being STRUCTURALLY LOW in a 3-hour daily window. Both matter;
they address different failure modes.

**Caveat (IMPORTANT):** This is Binance BTC/FDUSD SPOT data, not Phemex perpetuals and not
small-cap alts (PEPE, ARB, ETH). The specific magnitudes ($3.86M, 42% reduction) almost
certainly do not transfer to Phemex and will differ by symbol. The structural finding
(US pre-market/Asia pre-market = thin liquidity) is directionally well-supported by the
crypto session literature and likely to hold qualitatively. The specific gate (avoid 20:00–23:00)
should be treated as a HYPOTHESIS requiring validation against Phemex/ST2.0 outcomes, not as
a calibrated threshold. Start with shadow logging, not enforcement.

---

## What Could Not Be Verified Tonight

- **Stoikov SSRN 2970694 full text:** HTTP 403. Formula confirmed from citing paper and consistent
  practitioner descriptions. Original quantitative results not directly read.
- **Stoikov "Market Making in Crypto" (SSRN 5066176):** HTTP 403. This paper develops a "Bar Portion"
  (BP) alpha signal for crypto perp market-making. Only LinkedIn summary read ("uncovered fresh
  microstructure alphas in the wild world of crypto markets"). Potentially relevant for maker
  signal design — high priority for a direct access attempt. Authors: Stoikov, Zhuang, Chen et al.
  (Dec 2024).
- **MDPI 2227-7072/14/5/103** ("Temporal Dynamics of Market Microstructure in Cryptocurrency
  Perpetual Futures"): HTTP 403 for third consecutive night. Appears to be the best available
  primary source for intraday execution quality in crypto perps on CEXs.
- **ScienceDirect S0275531925004192** (VPIN vs Bitcoin price jumps): Paywalled, third consecutive
  night unread. Remains highest-priority for crypto VPIN calibration.
- **arxiv 2507.09734** ("Boltzmann Price: Toward Understanding the Fair Price in High-Frequency
  Markets"): Surfaced tonight but not fetched. Potentially relevant as a fair-price reference
  alternative to micro-price — July 2025, worth reading if prior sources remain blocked.

---

## Concrete Forward-Testable Tweaks

### Tweak A — Micro-Price Placement Filter (NEW)
**Implementation:**
```python
# Before posting the ST2.0 limit sell at price limit_price:
bid_price = ob.bids[0][0]
bid_vol   = ob.bids[0][1]
ask_price = ob.asks[0][0]
ask_vol   = ob.asks[0][1]
P_micro   = ask_price * (bid_vol / (bid_vol + ask_vol)) + bid_price * (ask_vol / (bid_vol + ask_vol))
if P_micro > limit_price:
    # Fair value already above our sell limit — adverse post; skip this cycle
    return skip("micro_price_below_limit")
```
**Rationale:** A passive sell below the micro-price is posting below fair value. The fill we
eventually get will be one where price ticked up through our limit — adverse by construction.
This check is a direct LOB-state quantification of the "posting at the wrong price" failure mode.
**Source:** Stoikov (2017) SSRN 2970694 (existence verified, formula confirmed from citing paper
and consistent practitioner sources; primary text not read tonight). arxiv 2411.13594 (formula
extracted; performance results in equity data only).
**Risk:** In high-OBI situations (P_micro → P_ask), this check will block entries where the
intended limit is slightly inside the spread. That's the CORRECT behavior — but it will reduce
entry frequency. Shadow-gate (log skips but don't block) for 1 week first. Measure what fraction
of would-be ST2.0 entries are blocked, and whether those missed entries have different WR than
those that pass.

### Tweak B — 20:00–23:00 UTC Thin-Liquidity Gate (NEW)
**Implementation:** Check UTC hour before entry. If `utc_hour in {20, 21, 22}`, skip this cycle.
Log as `skip_thin_liquidity`. Shadow-gate first — do NOT block without data.
**Rationale:** Intraday orderbook depth is 42% below daily peak during this window (Amberdata,
BTC/FDUSD, summer 2025). Thin book → wider spreads → higher adverse selection exposure. The
imbalance doubling (+1.54% → +3.18% bid-side in the second 12 hours) also suggests more
frequent but lower-quality signal triggers in this window.
**Source:** Amberdata blog (secondary, practitioner data blog; Binance spot, not Phemex perps).
Directional applicability to Phemex likely; magnitude uncertain.
**Risk:** 20:00–23:00 UTC covers the US afternoon + Asia pre-market overlap. If these hours
contain valid ST2.0 signals, the gate will reduce total entries. Shadow-gate and correlate with
ST2.0 outcomes before enforcing. Note the funding-window gate already blocks ±30 min around
16:00 UTC; this adds a separate 3-hour window that is NOT funding-driven.

---

## Honest Assessment

**Tonight's two findings are NEW vs all prior reports.** Both are at the lower end of source
quality (one academic formula extracted from a citing paper because the primary is 403-blocked;
one practitioner blog with real but non-Phemex data). That said:

**Tweak A (micro-price placement filter)** is the more defensible of the two. The logic is
mathematically tight — posting below the micro-price is adverse by the definition of the
micro-price as the martingale "fair value." The formula is simple and implementable in 5 lines
from existing L2 data. The shadow gate costs nothing and will produce a direct log of "would
this have filtered bad entries?" — a cleanly measurable hypothesis.

**Tweak B (20:00–23:00 UTC gate)** is directionally sound but the weakest source of all 6 nightly
reports. The Binance spot → Phemex perp transfer is speculative. Treat as a shadow gate
hypothesis only.

**Cumulative research state (after 6 reports):**
The execution improvement literature for this setup (passive crypto perp short, small, slow,
no rebate) is now genuinely near-exhausted. Every major dimension has been surfaced:
pre-entry quality (CQI, trade-OFI, funding window, VPIN, micro-price), at-entry pricing
(deeper-in-spread, OFI-flip), post-entry management (90s expiry, cancellation on informed flow),
and intraday timing (funding cycle, thin-liquidity window).

**The binding bottleneck has moved to forward-testing.** The paper-slot lab (existing
infrastructure) now has 7–9 hypotheses queued. No further nightly research sessions are likely
to produce peer-reviewed, crypto-perp-specific, directly actionable material that isn't already
covered. Recommend pausing nightly research and shifting compute budget to:
1. Shadow-gate instrumentation for the highest-priority tweaks (micro-price, 90s expiry, VPIN)
2. 2-week paper-slot forward test with outcomes logged per hypothesis
3. Revisit research if and when an accessible primary source emerges (MDPI 2227-7072/14/5/103,
   SSRN 5066176 "Market Making in Crypto," ScienceDirect VPIN/Bitcoin jumps)
