# ST2.0 Execution Optimization — Night 27
**Date:** 2026-07-23 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 26 Nights

N26 closed with: arXiv:2602.07018 (Levi sentiment regimes, Tweak 27), SSRN 4218907 (U-shaped funding cycle adverse selection, Tweak 28). Tonight searched four angles: (1) Hawkes process / order-arrival clustering as adverse selection pre-indicator, (2) microprice-based passive placement timing for crypto perps, (3) arrival-rate z-score as institutional flow detector, (4) altcoin-specific adverse selection rates vs BTC via new 2025-2026 data.

**Summary of new material tonight:**
- Frontiers in Blockchain (Pindza, June 2026, 10.3389/fbloc.2026.1811716) — VERIFIED (full paper fetched). New data: 6 crypto assets (BTC, ETH, SOL, AVAX, LINK, DOT) on Binance spot + perp futures, Aug 2025–Feb 2026. Two relevant findings: (a) VPIN distributions are comparable across assets — informed trading proportion is similar whether you're on BTC or an altcoin perp; (b) **all 5-min forecast strategies failed under realistic Binance fees and slippage**. Second-most important new empirical data point in the series after the 2026-06-20 synthesis.
- Tigro Blanc, Coinmonks (Feb 2026) — PRACTITIONER PIECE, not academic. 14 days of OKX L2 data. New angle: **arrival-rate z-score** (trade count in last 30s vs rolling 5-min baseline) as a concrete institutional flow signal distinct from Tweak 4's `tape_max_single_trade`. Distinguishes TWAP-style splitting (many small orders arriving fast) from large single prints (which Tweak 4 already captures).

**Confirmed misses tonight:**
- arXiv:2508.20225 (Barzykin, Bergault, Guéant, Lemmel — "Optimal Quoting under Adverse Selection and Price Reading") — fetched, found purely theoretical, FX dealer-to-client RFQ markets, no empirical data, no applicability to a small passive crypto perp maker. The "price reading" concept is about institutional FX dealers managing tiered clients, not about resting limit orders on a perp exchange.
- arXiv:2408.03594 (Hawkes OFI forecasting) — fetched, NSE NIFTY equity futures, single day September 2018 data. Framework concept (clustering detects sustained directional pressure) is directionally consistent with Tweak 4 orientation but is not calibrated to crypto perps and provides no fill-level adverse selection quantification.
- IOC/FOK order type information content angle — no academic or practitioner source found that connects IOC/FOK aggressive order type distribution to passive fill adverse selection rates on crypto perps.
- SSRN 6344338 — 25th consecutive night blocked.

---

## Finding A — Frontiers 2026 (Pindza) VERIFIED: VPIN Comparable Across Crypto Assets; All Cost-Adjusted Strategies Fail

**Source:** Edson Pindza. "Microstructure alpha: hierarchical learning and cross-asset transfer in cryptocurrency markets." *Frontiers in Blockchain*, Vol. 9, June 11, 2026.
**URL:** https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full
**Dataset:** 3,417,972 minute-level observations (~285,000 bars per asset–venue pair). Assets: Bitcoin, Ethereum, Solana, Avalanche, Chainlink, Polkadot. Venue: Binance (spot and perpetual futures). Date range: August 2025 – February 2026.

**Verified quotes (directly fetched from full paper):**

> "Bitcoin and Ethereum exhibit the tightest spread proxies, reflecting their greater liquidity and trading volume. Smaller-capitalization assets such as Avalanche and Polkadot show wider spreads and higher Amihud ratios, indicating higher trading costs and price impact."

> "VPIN shows relatively similar distributions across assets, suggesting that the proportion of informed trading activity is comparable across the cryptocurrency ecosystem."

> "No trading strategy based on these 5-min forecasts survives standard Binance exchange fees and slippage."

**What this means for ST2.0:**

Finding 1 (VPIN comparable): Prior intuition might suggest that altcoin perps have more retail noise and less informed flow — better conditions for a short-reversion maker. The Pindza paper challenges this directly: VPIN (a standard informed-flow proxy) is statistically similar across BTC, ETH, SOL, AVAX, LINK, and DOT on Binance perps. If the informed-trading proportion is comparable across assets, then ST2.0's ~43% fill rate on altcoins (vs lower on BTC) likely reflects **liquidity differences** (altcoins have thinner books, so a resting sell is hit more often), NOT lower informed-flow risk. Filling more does not mean filling less adversely.

Finding 2 (cost-adjusted strategies fail): The paper tests statistical edge at 5-minute horizons using hierarchical learning models across 6 crypto assets with 7 months of recent data (Aug 2025–Feb 2026). None survive Binance's fees and slippage. This is the most current out-of-sample corroboration (after the 2026-06-20 synthesis) that short-horizon passive execution strategies on crypto perps are fee-trapped at the retail scale.

**Internal consistency check:** The 2026-06-20 synthesis established the same conclusion for 2022-era Binance BTC perp data (Tweak analog: imbalance-conditioned maker strategy, −0.4705 bp mean, net-negative). Pindza extends this finding to a 6-asset, 7-month window ending February 2026 — closer to current market conditions, broader asset coverage, and still confirming the fee trap.

**What this does NOT mean:** Pindza uses 5-minute ML forecasts as the signal, not ST2.0's specific book×tape absorption signal. The "strategies fail" finding cannot be imported directly as "ST2.0 fails" — it means that 5-min microstructure predictability alone is insufficient to cover costs. ST2.0 uses a different signal shape. However, it narrows the confidence interval on "execution refinements are enough to save a short-reversion passive strategy at small size."

**Critical limitations:**
1. Binance perp, not Phemex perp. Participant mix, fees, and tick structure differ.
2. VPIN at 1-minute cadence. ST2.0 operates at 5-second tape + 1-minute LOB snapshots. Sub-minute VPIN may vary more across assets than this paper captures.
3. No per-asset adverse selection coefficient published. The VPIN comparability finding is a distributional summary, not a per-fill rate.
4. "All strategies fail" tested against 5-min signals, not against ST2.0's specific signal. Cannot import as a definitive verdict on ST2.0 specifically.

**Forward-testable implication (no new tweak needed):** This finding is calibration context for the existing tweak queue — specifically, it argues against interpreting higher altcoin fill rates as lower adverse selection risk. The distinction to log is not "did we fill?" but "what happened to price in the 30s/5min post-fill?" Tweaks 4, 6, 9, 10, 11, 12 already target this; this finding raises their implementation priority again.

---

## Finding B — Tigro Blanc (Medium, Feb 2026) PRACTITIONER-UNVERIFIED: Arrival-Rate Z-Score as Institutional Flow Detector

**Source:** Tigro Blanc. "Meta-Order Flow in Crypto Perps: Catching Big Whale." *Coinmonks / Medium*, February 13, 2026.
**URL:** https://medium.com/coinmonks/meta-order-flow-in-crypto-perps-catching-big-whale-6a127e2f70e8
**Dataset:** 14 days of OKX L2 order book data (dates and assets not specified). Author identified as "Crypto, Stock, Commodity Trader (10Y+)." Not peer-reviewed.

**Verified quotes (directly fetched):**

> "arrival-rate z-score > 1.5 and absolute volume imbalance > 0.2" [trigger threshold for institutional flow detection]

> "aggressive one-sided pressure tends to continue, at least over 10–30 seconds," indicating "parent-order execution pressure that has not finished."

> "use this signal to avoid crossing the spread against detected one-sided flow"

> "if expected gross edge is below your modeled all-in cost floor, it is not alpha, it is noise"

**What the arrival-rate z-score is:**

```
arrival_rate_zscore = (trades_in_last_30s - rolling_5min_mean) / rolling_5min_std
```

This measures whether trade *frequency* (arrivals per unit time) is unusually elevated relative to the recent baseline. It is **different from Tweak 4** (`tape_max_single_trade`): Tweak 4 catches large individual orders; the arrival z-score catches high-frequency clusters of normal-sized orders — the signature of TWAP/VWAP-style algorithmic splitting.

**Why this is a new angle for ST2.0:**

Institutional flow in crypto perps comes in two forms:
- **Large individual prints** → Tweak 4 already targets this
- **Sustained high-frequency clusters of smaller orders** (TWAP splitting) → NOT currently captured in the tweak queue

A buyer running a TWAP program slices a large order into many smaller trades at regular intervals. Each individual trade looks retail-sized, so `tape_max_single_trade` stays low. But the arrival rate spikes above the baseline. The author finds this signature (z > 1.5) is associated with pressure that "tends to continue 10–30 seconds" — making a passive short posted into this regime more likely to be adversely filled by sustained buying rather than a squeeze that reverts.

**Combined trigger:** Both conditions together (z > 1.5 AND |volume_imbalance| > 0.2) appear more reliable than either alone. Volume imbalance alone fires on momentary spikes; z-score alone fires on any busy period. The conjunction filters for *sustained directional busyness* — the institutional signature.

**What this means for ST2.0:**

ST2.0's signal fires on buy absorption: an imbalance-heavy book being aggressively bought. High arrival-rate z-score at signal time means the buying is not just intense (already captured in imbalance) but *unusual relative to the symbol's recent rhythm* — elevated probability it's programmatic, not a noise-level retail squeeze. Post-entry, the author finds 10–30 second persistence, which at ST2.0's ~3–4 minute hold horizon implies the adverse pressure has ample time to run.

**Forward-testable tweak → Tweak 29 (shadow log, 3 lines):**
At signal time, compute and log:
```python
recent_30s_count = sum(1 for t in tape if current_time - t['timestamp'] <= 30)
mean_rate = rolling_5min_trade_count / 10  # trades per 30s window
std_rate = rolling_5min_std_30s_window
arrival_rate_zscore = (recent_30s_count - mean_rate) / max(std_rate, 1)
```
Log `arrival_rate_zscore` alongside fill/miss outcome. After 30+ tagged fills: do adverse fills cluster at z > 1.5 while |volume_imbalance| > 0.2? If yes, consider adding this as a pre-entry gate (skip entry when both thresholds exceeded). This is implementable in ~3 lines and is a TRUE complement to Tweak 4 — different institutional flow signature.

**Critical limitations:**
1. **Not peer-reviewed.** 14 days of OKX data. Author unknown in academic literature. Treat as a practitioner hypothesis, not a verified finding.
2. OKX is not Phemex. L2 book structure, tick size, and participant mix differ.
3. The "10–30 second continuation" claim is a sample average, not a calibrated distribution. Cannot import as a precise gate threshold.
4. The z-score requires a stable rolling baseline — works best on liquid pairs where the baseline is stable (BTC, ETH). For thin altcoin perps with sporadic volume, the rolling baseline may be unstable and z-scores noisy.
5. No per-asset breakdown. Whether the threshold (z > 1.5) holds for altcoin perps with materially different arrival rates is unknown.

---

## New Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority | Code size |
|---|---|---|---|---|
| 29 | Log `arrival_rate_zscore` at signal time = (trades in last 30s − 5-min rolling mean per 30s window) / rolling std. After 30+ tagged fills: do adverse fills cluster at z > 1.5 with |volume_imbalance| > 0.2? If yes, add institutional-flow-splitting gate. | Finding B (Tigro Blanc, Medium, practitioner-UNVERIFIED — shadow log only, no gate) | Queued — log only | 3 lines |

Finding A (Pindza Frontiers 2026): does not add a new tweak — raises existing priority queue (tweaks 4, 6, 9, 10, 11, 12) as the correct immediate next step.

---

## Honest Caveats

1. **Finding A (Frontiers/Pindza):** Full paper fetched and directly quoted. BUT: Binance perp, not Phemex; 1-minute cadence; VPIN comparability is distributional, not per-fill; "strategies fail" tested on 5-min ML signals, not ST2.0's signal. Treat as calibration context, not a verdict on ST2.0.

2. **Finding B (Tigro Blanc):** Directly fetched and quoted. BUT: practitioner piece, not peer-reviewed, 14 days of OKX data, no academic validation. The z-score concept is sound (arrival clustering is a documented feature of algorithmic order flow in academic literature), but the specific thresholds (z > 1.5, imbalance > 0.2) are empirically derived from a very small OKX sample. Implement as log only; no gate until Phemex-specific data validates.

3. **Hawkes OFI angle (arXiv:2408.03594):** Fetched and read. NSE NIFTY 2018 equity futures — too different in venue, asset class, and era to be actionable for Phemex altcoin perps. The clustering concept it represents is the academic basis for Finding B's arrival z-score, so it provides theoretical context but adds nothing concrete.

4. **SSRN 6344338 blocked for 25 consecutive nights.** No new access route found. This remains the most directly applicable blocked source in the series.

5. **29 tweaks queued, 0 deployed across 27 nights.** Research recommendation from N20–N26 remains: implement priority tweaks 4, 6, 9, 10, 11, 12, 14 first. Each is 2–5 lines of shadow logging. Tweak 29 (arrival_rate_zscore) is 3 lines and can be added in the same session. Continuing research before collecting 30+ tagged fills per diagnostic variable has zero ROI.

6. **The Pindza finding narrows the altcoin-fill-rate interpretation.** Prior analysis noted that ST2.0 fills better on ETH/INJ than BTC and considered this a quality signal. Pindza's VPIN finding argues the informed-flow proportion is similar across assets — meaning the higher fill rate on altcoins is a liquidity artifact, not a signal quality improvement. This is the most important practical recalibration from tonight.

---

## Cumulative Forward-Test Queue (29 Tweaks)

Priority tweaks (unchanged): **4 [elevated], 6, 9, 10, 11, 12, 14**
Tweak 29 added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), above (Tweak 29).

---

## Night 27 Bottom Line

Two findings. Finding A (Pindza, Frontiers in Blockchain, June 2026, VERIFIED): new 6-asset crypto perp data (Aug 2025–Feb 2026) showing VPIN is comparable across BTC and altcoins — the higher altcoin fill rate likely reflects thinner books, not lower informed-flow risk — and all 5-minute microstructure strategies fail under realistic fees, a second-independent corroboration of the 2026-06-20 synthesis fee-trap conclusion. Finding B (Tigro Blanc, Coinmonks, Feb 2026, PRACTITIONER-UNVERIFIED): arrival-rate z-score (z > 1.5 vs 5-min rolling baseline) + |volume imbalance| > 0.2 as a composite institutional TWAP-splitting detector, complementary to Tweak 4's max-single-trade signal. One-sided pressure detected this way tends to continue 10–30 seconds. Forward-testable as Tweak 29 (3-line shadow log).

**Recommendation unchanged from N20–N26:** Implement priority tweaks 4, 6, 9, 10, 11, 12, 14. Tweak 29 is 3 lines and can be added in the same session. Night 27: 29 tweaks queued, 0 deployed.
