# ST2.0 Execution Optimization — Nightly Report N63
**Date:** 2026-09-04  
**Focus:** Passive maker fill quality / adverse selection mitigation for ST2.0 short-reversion on Phemex CEX perp  
**Prior coverage:** 62 nights (N1–N62); all arXiv q-fin.* through August 2026 screened; SSRN universally 403-blocked

---

## What's New vs. Prior Reports

Three candidates identified as potentially unswept by prior arXiv sweeps. All three fetched and screened:

| Paper | Source | Date | Verdict |
|-------|--------|------|---------|
| arXiv:2606.15715 — "Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid" (Barone & Lillo) | arXiv | June 2026 | NOT APPLICABLE — mechanism requires on-chain order transparency unique to Hyperliquid DEX; no CEX analog |
| arXiv:2512.05734 — "KANFormer for Predicting Fill Probabilities via Survival Analysis in Limit Order Books" (Zhong et al.) | arXiv | Dec 2025 | NOT APPLICABLE — Euronext CAC 40 equity futures 2016–2017; requires full ML/survival-analysis pipeline; only heuristic extractable (queue position matters) is already common knowledge |
| arXiv:2407.16527 — "The Negative Drift of a Limit Order Fill" (DeLise) | arXiv | July 2024 | NOT APPLICABLE for new tactics — Treasury futures on CBOT/TT; confirms adverse-drift-after-fill mechanism already in the N0 synthesis; no mitigation playbook offered |

**Net new verified findings: zero.**

September 2026 arXiv remains sparse (confirmed empty through Sep 3 in N62; today's sweep returned the same three candidates above, all now screened). SSRN remains universally blocked.

---

## Honest Assessment

The literature space for this sub-problem (passive maker adverse selection at small size, no rebate, on a crypto CEX perp) is saturated. 63 consecutive nightly sweeps have not produced a new actionable execution tweak in 16 nights. This is consistent with the standing recommendation issued at N47 and reiterated every night since.

**The binding constraint is not missing literature — it is the undeployed tweak queue.**

---

## Forward-Testable Execution Tweaks (Unchanged from Prior Reports)

No new tweaks are added tonight. The actionable queue from prior nights remains:

**Priority (deploy first):** Tweaks 4, 6, 9, 10, 11, 12, 14 (documented in prior nightly reports N1–N59).

**Simplest immediate action (Tweak 45 — N60):**  
Standalone spread gate — skip ST2.0 entry when bid-ask spread ≥ 75th percentile rolling per-symbol.  
Source: arXiv:2602.00776 (Binance Futures perp, 5 assets, 1-second, 2022–2025).  
Implementation: log `spread_pct` at every entry attempt immediately (zero trading risk); calibrate threshold after 1–2 weeks of data; then gate.

**Next simplest (Tweak 44 — N59):**  
L2 3-metric regime check (top-20 book levels; spread/depth/imbalance terciles).  
Source: arXiv:2607.09230 (Jeon, Binance BTC/ETH perp 2023–2026).  
Action: skip entry in "calm" regime for BTC; log-only tier for ETH.

---

## Caveats

- The three papers fetched tonight are verified non-applicable; claims above from prior reports (Tweaks 44/45) were verified in N59–N60 and source URLs remain cited there.
- Hyperliquid paper (arXiv:2606.15715) is the most rigorous 2026 adverse-selection study on a crypto perp LOB, but is non-transferable to CEX context: Hyperliquid's on-chain transparency is the mechanism, not a proxy for CEX dynamics.
- No empirical paper in 63 nights has measured OFI-flip decay or passive fill adverse selection at 60-second granularity on a crypto CEX perp. Internal bot data remains the only source for this sub-question; the data logging fix (ob/flow conditions at every miss) deployed 2026-06-19/20 should be the primary instrument.

---

## Standing Recommendation (Night 17 — unchanged)

**Suspend nightly literature sweeps.** Resume when September 2026 arXiv submissions accumulate (estimated Sep 5–7).  
**Deploy Tweak 45 (spread gate logging) immediately — zero trading risk, unblocks threshold calibration.**  
Then deploy priority tweaks from the existing 44-item queue.
