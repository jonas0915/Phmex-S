# ST2.0 Execution Research — Nightly (2026-06-29)

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
- Micro-Price Placement Filter: only post if P_micro ≤ limit_price (Stoikov SSRN 2970694 / arxiv 2411.13594)
- 20:00–23:00 UTC thin-liquidity gate (Amberdata secondary source, Binance spot only)
- Boltzmann Price β Calibration (arxiv 2507.09734)
- Multi-Level OFI (MLOFI) — Depth-Weighted Imbalance (arxiv 1907.06230, abstract only)
- Cancel-and-repost made losses worse; "cancel-and-walk, never repost" rule (arxiv 2502.18625 full extract)
- Phemex RPI Orders: ST2.0 has no protection in the regular book (Phemex official docs)

---

## Status: Eighth Night — One Genuinely New Finding; Everything Else Exhausted or Blocked

Four papers pursued tonight. One new verified primary source. Two papers remain permanently blocked
(SSRN 6693260 still 403 for the fourth consecutive night; Tandfonline 2025 latency paper still 403).
One paper (arxiv 2506.05764) found to be about price prediction, not maker execution — not actionable.

The LOB resilience paper (arxiv 1602.00731, Xu et al. 2016) produced one result — "spread and depth
return to sample average within 20 best limit updates" — but covers Chinese equities from 2016 and
provides no crypto perp maker execution guidance. Not cited further.

---

## What Is NEW Tonight

### 1. Sentiment Regime Adversely Selects Passive Sellers — Measured by Regime Category

**Verified source:** arxiv 2602.07018, "The Extremity Premium: Sentiment Regimes and Adverse
Selection in Cryptocurrency Markets" (Murad Farzulla, Dissensus AI / King's College London).
Full HTML fetched directly (https://arxiv.org/html/2602.07018v2). Published February 2026.
**Confidence:** VERIFIED from primary source HTML (not just abstract/snippet). Caveats below.

**What the paper does:** Studies whether Crypto Fear & Greed (F&G) Index regimes predict adverse
selection costs for passive liquidity providers in cryptocurrency markets. Uses a Bayesian neural
network's output uncertainty as a proxy for information asymmetry (aleatoric + epistemic components),
framed within the Glosten & Harris (1985) adverse selection decomposition framework.

**Regime definitions (verbatim):**
> "We classify regimes based on index thresholds: Extreme fear: <25; Fear: 25–44; Neutral: 45–55;
> Greed: 56–75; Extreme greed: >75"

**Quantitative results — mean uncertainty by regime (Table 5 from fetched HTML):**

| Regime          | Uncertainty | Δ vs Neutral | Significance |
|-----------------|-------------|-------------|--------------|
| Extreme Greed   | 0.521       | +0.055      | ***p<0.001   |
| Extreme Fear    | 0.403       | +0.039      | **p<0.01     |
| Fear            | 0.436       | +0.034      | **p<0.01     |
| Neutral         | 0.303       | —           | (baseline)   |

(Regression results with volatility control; Table 6 coefficients match Table 5 deltas above.)

**Granger causality (Table 17, fetched verbatim):**
> "uncertainty predicts spreads (F₃,₇₃₂ = 12.79, p<0.001) but not vice versa"

**Key interpretive statement (verbatim from paper):**
> "intensity, not direction, drives uncertainty-linked liquidity withdrawal."

Both sentiment extremes (>75 Extreme Greed AND <25 Extreme Fear) increase adverse selection proxies
relative to neutral, even after controlling for realized volatility.

**What this means for ST2.0:**

ST2.0 is a passive short on bid-absorption — it fires when aggressive buying is pushing a
bid-heavy book. This signal is directionally correlated with high-greed conditions (buyers
dominating). The paper's finding: **Extreme Greed is the regime with the highest adverse selection
cost (+5.5 pp over neutral, significant at p<0.001)**. This means ST2.0's signal condition
(absorption-driven buying pressure) correlates with the regime that produces the highest adverse
selection for passive sellers.

Two additional observations:

1. **Extreme Fear also elevates adverse selection (+3.9 pp).** This is less expected but relevant:
   if ST2.0 fires on a snap-back during a fear spike, adverse selection is also elevated.

2. **Contrarian return pattern (Table 13, fetched):** Extreme Greed → −0.14% next-day return;
   Extreme Fear → +0.34% next-day return. The difference is **not statistically significant**
   (t=1.02, p=0.31). This is consistent with the known ST2.0 problem: a weak directional signal
   that doesn't survive execution costs.

**The new gate hypothesis (not proposed in any prior report):**
Log the Crypto Fear & Greed index value at each ST2.0 entry. Separate fill outcomes by regime:
does Extreme Greed (>75) produce worse fill quality (lower WR, higher adverse selection) vs
Neutral (45–55)? If the paper's finding transfers, Extreme Greed entries should show the worst
adverse selection profile. Shadow-log first; do not use as a gate until the correlation is
confirmed on our own fill data.

---

## What Could Not Be Verified Tonight

- **SSRN 6693260** (Lawrence Chang, May 2026, "Do Order-Book States Predict Passive-Buy Toxicity?
  Evidence from BTC Perpetual Futures"): HTTP 403, **fourth consecutive night**. The delivery URL
  `https://papers.ssrn.com/sol3/Delivery.cfm/6693260.pdf?abstractid=6693260&mirid=1` also returned
  403. This paper remains the most directly on-point unread source in the entire research series.
  Its abstract describes a "flow-adjusted bid-absorption proxy" that is "substantially more
  informative than raw directional flow alone" in predicting passive-buy adverse selection in BTC
  perps — exactly ST2.0's setup. Until accessible, this is a permanent open item.
- **Tandfonline 2025 paper** ("The good, the bad, and latency: exploratory trading on Bybit and
  Binance"): HTTP 403. Paywalled. Unknown relevance.
- **ScienceDirect S0275531925004192** (VPIN vs Bitcoin price jumps): HTTP 403, sixth consecutive
  night. Crypto VPIN calibration from primary source remains unverified.

---

## Concrete Forward-Testable Tweak

### Tweak A — Log Fear & Greed Regime at ST2.0 Entry (Shadow Logging Only)

**What this is:** Not a trading gate — a logging addition. At each ST2.0 signal trigger,
record the current Crypto Fear & Greed Index value (or its regime bucket) alongside the
fill outcome. After 2–3 weeks of data, test whether Extreme Greed (>75) entries show
statistically worse fill outcomes than Neutral (45–55) entries.

**Implementation:** The Crypto Fear & Greed API is free and public:
`https://api.alternative.me/fng/?limit=1` returns the current index as JSON in one HTTP call.
The index updates daily — a cached value updated at the start of each bot cycle costs
virtually nothing. Log as `fg_regime` ("extreme_greed", "greed", "neutral", "fear", "extreme_fear")
in the ST2.0 entry log alongside existing fields.

```python
# One-time daily fetch (cache in bot state):
import requests
r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=3)
fg_value = int(r.json()["data"][0]["value"])
# Map to regime:
if fg_value > 75:   fg_regime = "extreme_greed"
elif fg_value > 55: fg_regime = "greed"
elif fg_value > 44: fg_regime = "neutral"
elif fg_value > 24: fg_regime = "fear"
else:               fg_regime = "extreme_fear"
```

**Hypothesis:** Entries during Extreme Greed will show lower WR and/or larger loss asymmetry
than Neutral entries, consistent with arxiv 2602.07018's regime-specific adverse selection results.

**Why this is different from all prior gates:**
- All prior gates are intraday / microsecond-to-minute frequency (OFI, funding window, tape gate,
  micro-price). The F&G index is a **daily macro regime** variable.
- This doesn't replace any existing gate — it adds a macro context layer.
- If the hypothesis is confirmed, the action would be to require stricter tape/OFI confirmation
  during Extreme Greed (not a full block — a higher threshold).

**Source:** arxiv 2602.07018 (VERIFIED from primary source HTML). Working paper only (Dissensus AI,
not peer-reviewed). Dataset not specified in the fetched sections — assumed to be BTC/crypto spot.
No direct perp-specific results.

**Caveats (important):**
1. The "uncertainty" metric in this paper is a Bayesian neural network's output uncertainty
   (model-specific), not traditional spread-based adverse selection in bps (like Glosten-Harris
   decomposition directly applied). The F=12.79 Granger causality to spreads validates it as
   an adverse selection proxy, but the magnitudes (+5.5 pp) are in model-specific "uncertainty
   units," not directly translatable to bps cost.
2. The paper studies crypto spot (or unspecified instrument). Transfer to Phemex perpetuals is an
   assumption. Perpetual funding mechanics add a confound not in the paper (F&G extremity often
   coincides with extreme funding rates, which are a separate adverse selection driver already
   covered in the funding-window gate).
3. The F&G index updates daily — it doesn't distinguish between a 9:00 AM and 11:00 PM UTC entry
   on the same day. Intraday adverse selection variation (already gated by funding-window and
   thin-liquidity gates) may dominate the daily-regime effect.
4. The contrarian return result (which would validate ST2.0's directional premise in Extreme Greed)
   is NOT statistically significant (p=0.31). The paper shows the regime increases adverse
   selection cost but does NOT confirm that short signals fire more correctly in that regime.

**Risk assessment:** Low — shadow logging only. One API call per day, zero trading impact.
The hypothesis is falsifiable in 2–3 weeks of filled ST2.0 entries.

---

## Honest Assessment

**Tonight yields one marginal new finding.** The Extremity Premium / F&G regime finding (arxiv
2602.07018) is verified from primary source HTML and is genuinely not in any prior report. However:
- It is a daily-frequency macro variable, less sharp than intraday gates already proposed.
- The adverse selection metric is model-specific, not in traditional bps.
- It's a working paper (not peer-reviewed).

The finding is worth logging because it costs almost nothing and the hypothesis is directly
testable on our own data. If Extreme Greed entries cluster in our losing fills, the gate earns
further investigation. If not, this is a null result and we move on.

**The research series is now definitively exhausted.** Eight nights of research have covered every
major execution angle. The binding work is in the paper-slot forward-test queue, not in the
literature. SSRN 6693260 (Chang 2026) remains the only unread primary source with material
probability of new actionable content — check access periodically.

**Forward-test queue (unchanged from 06-26 report, with this addition):**
1. Shadow-gate micro-price check (06-24 Tweak A) — 2 lines, no live impact
2. Shadow-gate 90s cancel-and-walk with `miss_expired` log (06-23 Tweak A, 06-26 clarified)
3. Shadow-gate VPIN computation (06-23 Tweak B) — log-only for 1 week
4. Log `tape_max_single_trade` at signal time (06-26 Tweak B) — 1 line
5. Log `fg_regime` at signal time (tonight Tweak A) — 1 API call/day + 1 log field
6. Only after 1–2 weeks shadow data: evaluate which gates to enforce in paper slot

**Sources used tonight:**
- arxiv 2602.07018 (verified, full HTML fetched directly)
- arxiv 2506.05764 (verified, full HTML; not actionable — price prediction, not maker execution)
- arxiv 1602.00731 (abstract only; Chinese equities 2016, not applicable)
- SSRN 6693260 delivery URL (HTTP 403, fourth night)
- Tandfonline 2025 latency paper (HTTP 403, paywalled)
