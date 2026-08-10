# ST2.0 Execution Optimization — Night 41
**Date:** 2026-08-10 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 40 Nights

N40 closed with no new tweak (7th consecutive night without a new finding, literature declared saturated since N33). Prior 40 nights exhaustively covered: micro-price, cancel-reprice, VPIN, post-fill alpha decay, price-reading/skew-sniffing, miss-feedback signal, OFI diminishing returns, VWAP-to-mid, cross-asset transfer, funding-aware quoting, LOB depth profile, fleeting order filtration, passive market impact, fill-time distribution, flow-adjusted absorption, state-dependent order flow, altcoin price discovery, order book resilience, Hawkes burst decay, liquidation cascade early-warning, taker buy/sell variance, informed-trading detection, post-only repricing, queue-priority effects, short-term price reversal regime detection, sentiment regimes.

Tonight searched five angles not previously searched:
1. Passive limit order fill timing around absorption exhaustion (broad angle)
2. OFI decay / imbalance reversal as passive maker entry timing (the "wait for OFI flip" hypothesis from N1 synthesis — never verified in a primary source)
3. Optimal delay before passive order placement / microstructure mean reversion timing (new 2026 theory paper)
4. Order book resilience after buying shocks / fundamental anchoring
5. Liquidity withdrawal forecasting for passive maker risk

**Net result tonight: One new partially relevant paper (arXiv:2607.09230 — Binance perp, Jul 2026). Four candidates not applicable (non-crypto or pure theory). No new forward-testable execution tweak.**

---

## Papers Evaluated Tonight

### arXiv:2607.09230 — "When Does Order Flow Matter? State-Dependent L2 Liquidity-State Transitions in Crypto Futures"
**Published:** July 2026. arXiv preprint.
**URL:** https://arxiv.org/html/2607.09230v1
**Dataset:** Binance perpetual futures. BTCUSDT and ETHUSDT. January 2023 through mid-2026. One-minute cadence. Top-20 LOB snapshots + aggregate trade flow + macro event calendar. 47,513 windows across 40 monthly folds.

**Verification status: VERIFIED** — HTML fetched and analyzed.

**Key findings (verified from fetch):**

The paper's central finding is **asset-asymmetric and regime-conditional**: order flow adds predictive value for liquidity state transitions only in specific asset × regime combinations.

1. **ETH — stress-amplified order flow effect (verbatim):** "The increment rises monotonically from calm to mixed to stressed, reaching 0.004, 0.020, and 0.038 at the one-minute horizon." Order flow adds 0.038 to the prediction model's score in stressed ETH regimes specifically.

2. **BTC — order flow essentially noise in stressed regimes (verbatim):** "Only one of the six BTC cells clears its null, the five-minute calm regime, while the stressed regime is at or below its null at both horizons." No robust order flow effect for BTC.

3. **Explicit scope limitation (verbatim):** "the model cannot address queue position, own-order fill probability, sub-second market-order impact." Paper operates at one-minute aggregation and studies liquidity-state prediction (calm/mixed/stressed regime labels), not passive maker fill quality.

**What this means for ST2.0:**

The asset-asymmetric finding corroborates ST2.0's empirical pattern documented in the N1 synthesis (ETH ~59% fill, BTC ~30% fill). The N1 synthesis attributed this to symbol-specific queue dynamics; this paper now offers a one-minute-resolution explanation: ETH order flow in stressed regimes (the kind of state ST2.0 fires in, i.e., aggressive bid-heavy absorption) is measurably more informative than BTC order flow in the same regimes. From an adverse selection angle: if ETH order flow is more persistent and informative in stressed states, that means the aggressive buying that triggers an ST2.0 signal on ETH is more likely to be "real" sustained buying — which is precisely the condition that creates adverse selection for a passive short.

**Why NOT a new actionable tweak:**
- Paper studies liquidity-state prediction (3 regime labels), not passive fill quality or adverse selection magnitude.
- One-minute frequency. ST2.0 operates at 60-second cycle; the paper cannot distinguish intra-minute absorption dynamics.
- The ETH/BTC asymmetry is already practically represented in ST2.0's fill rate differential — nothing new to log or gate that isn't already captured.
- No primary source connection to whether delaying entry on ETH (waiting for the stress regime to dissipate) reduces adverse selection.

**Assessment: VERIFIED. Corroborative — confirms ETH vs BTC order flow asymmetry at 1-minute resolution on Binance perp. No new metric, no new gate, no new tweak.**

---

### arXiv:2608.00885 — "Optimal Trading of Microstructure Mean Reversion"
**Published:** August 1, 2026. arXiv preprint.
**URL:** https://arxiv.org/abs/2608.00885
**Dataset:** None — purely theoretical. Applies to large-tick liquid equities.

**Verification status: VERIFIED** — HTML fetched.

**Key finding (verbatim from fetch):**
> "Trading as soon as the gap covers the spread earns exactly zero on the surrogate: the whole rate is the option value of waiting."

The paper derives an optimal symmetric no-churn band θ* = ½(φ + √(φ² + 4s²_G)) where φ is half-spread and s_G is the gap standard deviation. Entry is triggered only when the gap (mid vs. efficient price) exceeds this threshold — not as soon as a signal fires.

**Why NOT applicable to ST2.0:**
The "gap" is the deviation of mid-price from the latent efficient price — not order flow imbalance. The model holds bid/ask as exogenous; it does not model how aggressive buying in a bid-heavy book evolves after signal detection. The result that "all profit is option value of waiting" applies within the paper's theoretical framework for large-tick securities with diffusive efficient prices. The authors explicitly note: "liquidity providers may respond strategically to being picked off at the gap's extremes, which turns the problem into a game" — ST2.0's exact scenario (being picked off by sustained aggressive buyers). The model does not resolve this game.

**Assessment: VERIFIED, NOT APPLICABLE.** Pure theory, large-tick equities, gap-state-variable model does not map onto OFI-based absorption entry.

---

### arXiv:2409.12721v3 — "Market Simulation under Adverse Selection"
**Published:** 2024; v3 updated June 2026. arXiv preprint.
**URL:** https://arxiv.org/html/2409.12721v3
**Dataset:** CME futures — ES (E-mini S&P 500), NQ, CL (Crude Oil), ZN (10-Year Treasury). April 2024.

**Verification status: VERIFIED** — HTML fetched.

**Key finding (verbatim from fetch):**
> "a significant portion of the total number of LO fills in ES, NQ, CL and ZN were adverse"

Measured adverse fill rates: 81.4% for ES, 65.8% for NQ, 82.9% for CL, 88.8% for ZN. Core claim: simulations ignoring adverse fills "systematically overstate strategy profitability."

**Assessment: VERIFIED, NOT APPLICABLE.** CME futures only, no crypto content. The high adverse fill rates (65–89%) are consistent with the N1 synthesis (41.5% fill rate for ST2.0 with adverse selection), but the CME microstructure is fundamentally different from Phemex CEX perps. No new execution tweak for ST2.0.

---

### arXiv:2607.16970 — "Herding and Liquidity in Order-Book Markets. II. Fundamental Anchoring and the Resilience of Liquidity"
**Published:** July 2026. arXiv.
**URL:** https://arxiv.org/abs/2607.16970
**Dataset:** None confirmed — theoretical model.

**Verification status: VERIFIED** (abstract confirmed).

**Key finding (verbatim):** "the price mean-reverts to value and the book refills after a shock." Liquidity crisis is characterized as a "failure of fundamental anchoring, not of market making."

**Assessment: VERIFIED, NOT APPLICABLE.** Pure theory, no crypto content, no passive fill quality analysis. No new tweak.

---

### arXiv:2509.22985 — "Forecasting Liquidity Withdraw with Machine Learning Models"
**Published:** September 2025. MIT working paper.
**URL:** https://arxiv.org/html/2509.22985
**Dataset:** NASDAQ — 7 tickers (AAPL, NVDA, TSLA, HIMS, NBIS, RKLB, SNAP). July 30, 2025, 1 hour of MBO data, 250ms resolution.

**Verification status: VERIFIED** — HTML fetched.

**Key finding (verbatim):** "At 5 s, XGB dominates with R² above 0.90 for most tickers, capturing nonlinear interactions that linear models miss." Liquidity withdrawal (cancellation ratio) is predictable at 1–5 second horizons using lagged LWI and volatility.

**Assessment: VERIFIED, NOT APPLICABLE.** NASDAQ equity only. Phemex has no cancel-flow observable from the API feed. No new tweak.

---

## New Forward-Testable Tweak Tonight

**None.** The arXiv:2607.09230 finding (ETH order flow stress-amplified at 1-min, BTC order flow noise in stressed regimes) is corroborative and at the wrong resolution for ST2.0's entry logic. All other papers tonight are not applicable to Phemex CEX crypto perp.

**Tweak queue remains at 42 (unchanged from N33).**

---

## Honest Caveats

1. **arXiv:2607.09230 is the one genuinely new paper tonight.** The ETH/BTC order flow asymmetry in stressed regimes (Binance perp, Jan 2023–mid-2026, 47,513 windows) is the strongest evidence to date that the N1 empirical finding (ETH fills more, BTC less) has a regime-level microstructure explanation. But the paper operates at 1-minute and studies regime prediction, not passive fill adverse selection directly. It cannot motivate a new gate without sub-minute labeled fill data on ETH vs BTC.

2. **The "OFI flip" hypothesis remains unverified by primary source.** Despite searching extensively, no paper was found that empirically studies whether waiting for OFI to start declining before placing a passive short reduces adverse selection. The N1 synthesis identified this as hypothesis (a); 41 nights have not produced a primary source. This absence is itself meaningful: if the mechanism were well-documented, a paper would exist. The hypothesis may require proprietary labeled fill data to test — exactly what deploying Tweaks 4 and 6 would produce.

3. **Literature saturation is genuine.** Night 41 is the 8th consecutive night without a new actionable tweak. Every search path returns: (a) papers already evaluated in N1–N40, (b) papers from non-crypto venues (CME, NASDAQ, FX), (c) theoretical papers not grounded in crypto perp data, or (d) DEX-specific papers (Hyperliquid, already confirmed inapplicable). The specific problem space — passive maker adverse selection for short-reversion on crypto perp CEX, small size, no speed, no rebate — appears genuinely exhausted in the accessible literature.

4. **42 tweaks queued, 0 deployed across 41 nights.** The path to reducing adverse selection is now through live-data fill labeling, not more literature. Deploying priority Tweaks 4, 6, 9, 10, 11, 12, 14 + log-only Tweaks 36–38 in one session would generate labeled fills within 1–2 weeks that could validate or discard all 42 hypotheses. No further literature search can do this.

---

## Cumulative Forward-Test Queue (42 Tweaks — Unchanged)

Priority tweaks (unchanged from N20–N40): **4 [elevated], 6, 9, 10, 11, 12, 14**
No new tweak added tonight.
Full queue archived: N22 (Tweaks 1–22), N23 (Tweak 23), N24 (Tweaks 24–26), N26 (Tweaks 27–28), N27 (Tweak 29), N28 (Tweaks 30, 30a), N29 (Tweaks 31, 31a), N30 (Tweaks 32, 32a), N31 (Tweak 33), N32 (Tweaks 34, 34a), N34 (Tweaks 35, 35a), N35 (Tweak 36), N36 (Tweak 37 — conditional on SSRN 6693260 access), N37 (Tweak 38 — conditional on tape buffer check).

---

## Night 41 Bottom Line

**No new actionable execution tweak tonight.** One new verified paper:

**arXiv:2607.09230** (Binance BTCUSDT/ETHUSDT, Jan 2023–mid-2026, 47,513 one-minute windows): ETH order flow adds measurable value in stressed liquidity regimes (increment +0.038 at 1-min) while BTC order flow is essentially noise in stressed regimes (5 of 6 cells below null). This is the first primary source to offer a regime-level explanation for ST2.0's empirical ETH/BTC fill asymmetry. Corroborative — no new metric or gate because the paper operates at 1-minute resolution and studies liquidity-state prediction, not passive fill adverse selection.

Four candidates not applicable: arXiv:2608.00885 (pure theory, large-tick equities, gap-state model inapplicable to OFI entry); arXiv:2409.12721v3 (CME futures simulation, 65–89% adverse fill rates documented, not crypto); arXiv:2607.16970 (pure theory, fundamental anchoring); arXiv:2509.22985 (NASDAQ cancel-flow prediction, no crypto).

**Recommendation after 41 nights:** The binding constraint is deployment, not knowledge. Shift all research effort to deploying priority Tweaks 4, 6, 9, 10, 11, 12, 14 (fill-time logging, post-fill alpha decay logging, OFI-at-fill labeling, fill-time elevation gate, per-symbol adverse selection tracking, VWAP-to-mid gate, placement delay variant). Deploy Tweaks 36–38 (log-only, 1–5 lines each) in the same session. Suspend literature search until 30+ labeled fills exist — that data is the only thing that can validate or discard the 42-item tweak queue.
