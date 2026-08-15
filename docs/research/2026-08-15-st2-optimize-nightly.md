# ST2.0 Execution Optimization — Night 46
**Date:** 2026-08-15 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 45 Nights

N45 closed with no new tweak (13th consecutive night, literature declared saturated since N33). Prior 45 nights exhaustively covered: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, taker buy/sell variance, informed-trading detection, post-only repricing, queue-priority effects, short-term price reversal regime detection, sentiment regimes, ETH/BTC order flow asymmetry, sunshine trading / TWAP transparency (Hyperliquid), OFI shock dissipation speed (E-mini baseline), OFI concavity at extremes (Binance Futures 2022–2025).

Tonight searched four angles (all execution-focused):
1. New 2026 arXiv preprints on crypto perpetual futures passive maker adverse selection / fill quality
2. arXiv:2607.27070 — "Where does the criticality live? Early-warning signals are event-heterogeneous across seven crypto-perpetual liquidation cascades" (July 2026 — new paper not in any prior night's citation list; BTC perp 2022-2025)
3. arXiv:2409.12721v3 — "Market Simulation under Adverse Selection" (CME futures; appeared in search, evaluated for crypto transfer)
4. arXiv:2510.27334 — "When AI Trading Agents Compete: Adverse Selection of Meta-Orders by RL-Based Market Making" (appeared in search)

Additional papers surfaced but screened out without full fetch:
- arXiv:2502.18625 ("The Market Maker's Dilemma") — confirmed = SSRN 5074873; covered in June-20 synthesis
- arXiv:2602.00776 — covered N43
- arXiv:2607.09230 — covered N45
- arXiv:2608.04373 — covered N39
- arXiv:2509.10094 ("Competition and Incentives in a Shared Order Book") — fetched; electricity markets, not applicable
- arXiv:2605.24242 ("Explicit Signal-Adaptive Sequential Optimal Execution Quotes") — fetched; traditional finance only, not crypto
- MDPI 2227-7072/14/5/103 ("Temporal Dynamics of Market Microstructure in Cryptocurrency Perpetual Futures") — 403; funding rate dynamics, not maker fill quality
- SSRN 6693260 (Lawrence Chang) — not re-attempted; 10 consecutive 403s; status unchanged

**Net result tonight: One new VERIFIED paper by paper ID (arXiv:2607.27070) with BTC perp crypto data. Key finding: liquidation cascade early-warning signals are event-heterogeneous; the only consistent predictor is taker order-flow variance compression acting as a population-level indicator rather than a per-event alarm. This finding adds a meaningful NEGATIVE RESULT for the cascade-blocking tweak class in the queue — per-event cascade gates are unreliable. No new forward-testable execution tweak. This is the 14th consecutive night without a new actionable finding. Tweak queue unchanged at 42.**

---

## Papers Evaluated Tonight

### arXiv:2607.27070 — "Where does the criticality live? Early-warning signals are event-heterogeneous across seven crypto-perpetual liquidation cascades"
**Author:** Ramon Marc Garcia Seuma
**Published:** July 2026. arXiv preprint.
**URL:** https://arxiv.org/abs/2607.27070
**Dataset:** Seven BTC perpetual futures liquidation cascades (2022–2025), including the October 10, 2025 event ($19B USD). Minute-level price data and 5-minute leverage/order-flow data.

**Verification status: VERIFIED** — Abstract and summary content fetched and analyzed.

**Key findings:**

1. **Signal heterogeneity across events:**
The paper's central finding is that no single early-warning signal works reliably across all seven liquidation cascades. Price signals (critical-slowing-down signatures) worked in 5 of 7 events but failed in the two tariff-shock scenarios.

2. **Order-flow variance compression — the only consistent signal:**
> "taker order-flow variance compression passed a placebo test (Fisher p ~5e-6) but functioned as a population-level indicator rather than per-event alarm"

Taker order-flow variance compression is statistically significant as a population-level indicator across the full event set but cannot be used as a reliable per-event trigger. This distinguishes between statistical regularities at the ensemble level and actionable per-event gates.

3. **Cascade mechanism:**
> "slowing down is absent exactly where the destabilising mechanism is most abrupt"

The paper characterizes cascades as "discontinuous, shock-driven transitions rather than critical ones" in the tariff-shock scenarios — implying the cascade happens faster than any measurable precursor can signal.

**What this means for ST2.0 and the existing Tweak queue:**

The cascade-blocking tweak class (entries in the queue that would suppress or abort a passive short posting when cascade early-warning indicators fire) is directly affected by this finding:

- **The heterogeneity finding is a meaningful NEGATIVE RESULT** for per-event cascade gates. Any single indicator (OFI spike, leverage surge, order-flow one-sidedness) will have high false-positive rate in events where it doesn't function, and high false-negative rate in the shock-driven scenarios where "slowing down is absent."
- **The population-level vs. per-event distinction matters operationally:** a gate that works in 5 of 7 historical cascades misses ~29% of events and would suppress valid ST2.0 entries in the false-positive scenario.
- **Implication for the queue:** The cascade-blocking tweak class should either be (a) abandoned as a per-event gate, or (b) reformulated as a composite multi-indicator gate (requiring coincidence of price + leverage + order-flow signals) which would have lower false-negative rate at the cost of extreme rarity — firing almost never.

**Why NOT a new standalone tweak:**
- The topic ("liquidation cascade early-warning") is in the covered list from prior nights.
- The paper explicitly says the order-flow signal is a population-level indicator — it cannot be used as a per-event real-time gate for ST2.0's 60-second entry cycle.
- No passive maker fill data, no adverse selection measurement.

**Assessment: VERIFIED. New by paper ID and provides the first quantitative heterogeneity analysis across 7 historical BTC perp cascades. The operative finding for the tweak queue: per-event cascade-blocking gates are unreliable (signal works in ~71% of events at best, zero in shock-driven scenarios). Argues for retiring or severely downgrading the cascade-blocking tweak class priority.**

---

### arXiv:2409.12721v3 — "Market Simulation under Adverse Selection"
**Authors:** Luca Lalor and Anatoliy Swishchuk (University of Calgary)
**Published:** June 2026 (v3). arXiv preprint.
**URL:** https://arxiv.org/html/2409.12721v3
**Dataset:** CME futures — ES (E-mini S&P 500), NQ (E-mini Nasdaq 100), CL (Crude Oil), ZN (10-Year Treasury Note). April 23–25, 2024.

**Verification status: VERIFIED** — HTML fetched and analyzed.

**Key quantitative finding (direct from fetch):**
- ES Jun24: 767 adverse fills vs. 174 non-adverse — **81.5% adverse rate**
- NQ Jun24: 1,269 adverse vs. 660 non-adverse — **65.8% adverse rate**
- CL Jun24: 518 adverse vs. 107 non-adverse — **82.9% adverse rate**
- ZN Jun24: 199 adverse vs. 25 non-adverse — **88.8% adverse rate**

> "Adverse fills are unavoidable in limit order posting strategies, especially in short-term trading environments."

> "Many previous works aim to measure different types of adverse selection in the limit order book (LOB), however, they often simulate price processes and market orders independently."

**Why NOT applicable to ST2.0:**
- CME futures only. No crypto content anywhere.
- The measurement methodology (next mid-price direction after fill = adverse if against position) is a simpler definition than ST2.0 would use.
- However, the benchmark data is useful context: CME futures adverse fill rates of 65–89% suggest ST2.0's estimated ~43% adverse selection rate (from the June-20 synthesis) is comparatively good — though market differences (crypto CEX vs. regulated futures) limit direct comparison.

**Assessment: VERIFIED, NOT APPLICABLE. CME futures only. Benchmark data (65–89% adverse fill rate) provides cross-market context but no new crypto perp execution tweak.**

---

### arXiv:2510.27334 — "When AI Trading Agents Compete"
**Authors:** Ali Raza Jafree, Konark Jain, Nick Firoozye
**URL:** https://arxiv.org/abs/2510.27334
**Dataset:** Hawkes Limit Order Book simulation — no historical exchange data; equity market microstructure framing.

**Verification status: VERIFIED** — Abstract and key claims confirmed via fetch.

**Assessment: VERIFIED, NOT APPLICABLE.** Equity market simulation only. RL-based market maker adversarially selects against meta-order takers — the adverse selection direction is opposite to ST2.0's problem. No crypto content.

---

## New Forward-Testable Tweak Tonight

**None.** arXiv:2607.27070 is verified and new by paper ID but provides a negative result rather than a positive direction: per-event cascade-blocking gates are unreliable across historical BTC perp cascades.

**Tweak queue remains at 42 (unchanged from N33).**

**Recommended queue adjustment (not a new tweak — a retirement/downgrade):** The cascade-blocking tweak class should be flagged for retirement or severe priority downgrade given arXiv:2607.27070's heterogeneity finding. A gate that works in 5 of 7 events at the population level but has zero per-event reliability in shock-driven scenarios is not useful for ST2.0's 60-second real-time entry cycle.

---

## Honest Caveats

1. **arXiv:2607.27070 is the only genuinely new verified paper tonight.** Its primary contribution to the tweak queue is a NEGATIVE result: the cascade-blocking tweak class is less reliable than assumed. This is a meaningful finding (avoid a dead-end implementation path) even though it adds no new tweak.

2. **CME adverse fill rate benchmark (arXiv:2409.12721v3):** The 65–89% adverse fill rates in CME futures are interesting as a cross-market benchmark. ST2.0's ~43% adverse rate from the June-20 synthesis is better than these benchmarks, but market structure differences (crypto CEX vs. CME, post-only vs. general limit orders, intraday vs. 60-second) prevent direct comparison.

3. **SSRN 6693260 (Lawrence Chang) — unchanged at 10 consecutive 403s.** The single most directly applicable inaccessible paper in the 46-night corpus. Last untried route: direct author contact via NCCU Finance department institutional email.

4. **46 nights, 42 tweaks, 0 deployed.** 14th consecutive night without a new actionable tweak. The literature for the specific problem space (passive maker adverse selection, crypto perp CEX, small size, no speed, no rebate) is confirmed exhausted through public search. The only path forward is deployment of priority Tweaks 4, 6, 9, 10, 11, 12, 14 to generate the 30+ labeled fills needed to validate or discard the queue.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N46): **4 [elevated], 6, 9, 10, 11, 12, 14**
**Cascade-blocking tweak class: FLAGGED FOR RETIREMENT** (per arXiv:2607.27070 heterogeneity finding).
No new tweak added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 46 Bottom Line

**No new actionable execution tweak tonight.** Three papers evaluated:

**arXiv:2607.27070** ("Where does the criticality live?", 7 BTC perp liquidation cascades, 2022–2025, July 2026): VERIFIED. New by paper ID. Liquidation cascade early-warning signals are event-heterogeneous. The only consistent predictor is taker order-flow variance compression (Fisher p ~5e-6), but it functions as a population-level indicator, not a per-event alarm. Shock-driven cascades show zero critical-slowing-down signatures. **Operative finding: per-event cascade-blocking gates are unreliable; the cascade-blocking tweak class should be retired or severely downgraded in the queue.** Not an execution study; no new tweak.

**arXiv:2409.12721v3** ("Market Simulation under Adverse Selection", CME futures ES/NQ/CL/ZN, April 2024): VERIFIED, NOT APPLICABLE. CME only. Adverse fill rates 65–89% across four CME futures contracts. Cross-market benchmark context only; no new ST2.0 tweak.

**arXiv:2510.27334** ("When AI Trading Agents Compete", Hawkes LOB simulation, equities): VERIFIED, NOT APPLICABLE. Simulation only, equity framing, adverse selection direction inverted vs. ST2.0.

**Final recommendation after 46 nights:** Suspend nightly literature search. Deploy priority Tweaks 4, 6, 9, 10, 11, 12, 14 and log-only Tweaks 36–38. Retire or downgrade the cascade-blocking tweak class. The single remaining optional action: NCCU Finance department page → Lawrence Chang's institutional email → one contact attempt for SSRN 6693260.
