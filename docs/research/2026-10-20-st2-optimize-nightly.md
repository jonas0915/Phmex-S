# ST2.0 Execution Optimization — Night 94 (2026-10-20)

**Focus:** Passive maker fill quality / adverse selection reduction for ST2.0 on Phemex perps.
**Prior coverage:** Tweaks 1–82 across Nights 1–93. Night 93 (2026-10-19): arXiv 1803.05690 (Lehalle — Bund futures optimal OBI-cancel policy) corroborated Tweak 74; no new tweak. Night 92: arXiv 2608.04373 (Hyperliquid wallet-level adverse selection); no new tweak. Night 91: Tweak 82 (FIFO time-to-fill queue classification). Undeployed #1 priority remains Tweaks 47/65. Third consecutive night with no new actionable tweak.

---

## (a) What's New vs. Prior Reports

**Search angles pursued tonight:**
1. Bid-wall depletion / LOB depth consumption as a passive-maker cancel trigger (new angle)
2. arXiv 2607.11888 θ* formula — attempt to recover equation 30 from the partially-fetched paper
3. "Queuing and inventories in limit order markets" (ScienceDirect pii/S1386418125000229) — prior 403
4. Yueshen "Queuing Uncertainty of Limit Orders" (Management Science 2025) — new lead from search

**Papers surfaced and their disposition:**

| Paper | Fetch status | Disposition |
|-------|-------------|-------------|
| arXiv 2604.21993 ("When Quotes Crumble: Detecting Transient Mechanical Liquidity Erosion," Xu et al., Stony Brook/Bloomberg, Apr 2026) | Already in corpus | Confirmed already covered in ≥10 prior nights. Simulation-only (ABIDES), no real exchange data, no passive maker strategy. Previously excluded. |
| arXiv 2610.09691 ("Optimal Regret for Online Market Making with Limit Order Book," Vischi et al., Politecnico di Milano, Oct 7 2026) | HTML fetched tonight | NEW to corpus. Purely theoretical — improves regret bound from Õ(T^{2/3}) to Õ(√T) for abstract market maker. No real data, no crypto/perpetuals, assumes "incurring no additional transaction costs or inventory constraints." NOT actionable for ST2.0. |
| Garriott, van Kervel, Zoican — "Queuing and inventories in limit order markets" (Journal of Financial Markets, vol. 75, 2025, DOI 10.1016/j.finmar.2025.100982) | Abstract via IDEAS/repec; full text paywalled | Abstract confirms: "queue position of a limit order influences its adverse selection risk"; "inventory shock reduces liquidity provision by market makers later in the queue" (crowding-out); empirically tested on futures data; optimal queuing sequence reduces quoted depth by up to 8.4%. Full text still unavailable. Direction corroborates existing corpus (queue-position adversity). No new threshold or signal for ST2.0. PARTIALLY VERIFIED (abstract only). |
| Yueshen, B.Z. — "Queuing Uncertainty of Limit Orders" (Management Science, 2025, DOI 10.1287/mnsc.2023.03371) | Primary source not directly fetched (INFORMS 403, SMU page empty) | NEW to corpus if verified. Search engine summary claims: "end-of-queue limit orders always lose money in equilibrium" and "cancel-to-add count ratio reflects adverse selection." Direction is structurally consistent with the existing corpus. But since the abstract was not directly fetched from a primary source, specific claims are UNVERIFIED — labeled as such below. |
| arXiv 2403.02572 ("Fill Probabilities in a Limit Order Book with State-Dependent Flow") | Search result only | Prior corpus status unknown; not fetched tonight (equity, fill-probability model — would corroborate synthesis's exponential fill-decay finding without adding new gates). De-prioritized. |

---

## (b) Concrete Forward-Testable Execution Tweak

**No new tweak this night.**

**arXiv 2610.09691** is the only paper new to the corpus tonight with a verified fetch. It is purely theoretical (regret bounds for abstract market making, no real data, no adverse selection, no crypto). It does not produce any executable tweak.

**Garriott et al. (JFM 2025)** and **Yueshen (Management Science 2025)** are the two new leads with potential structural relevance. Both share the same problem: the full text is inaccessible. Without direct quotes from the results section, they cannot anchor a new executable tweak — the constraint established in prior reports.

**What Yueshen's abstract-level findings would suggest (UNVERIFIED):**

If the claims from the search summary hold under direct verification:

> "end-of-queue limit orders always lose money in equilibrium"

This would be the strongest equilibrium-level theoretical support yet for the synthesis's empirical result (back-of-queue fills show −0.775 bp adverse selection on Binance BTC perp, arXiv 2502.18625). It would strengthen the structural case for deploying Tweaks 47/65 as the only path to measuring whether ST2.0 is back-of-queue.

> "cancel-to-add count ratio reflects adverse selection"

This is structurally new relative to the 82-tweak stack. It suggests that counting how often ST2.0 cancels relative to how often it posts (i.e., its own historical cancel-to-add ratio) is an adversely-selected signal indicator — periods with high cancel rates may reflect worse market conditions for passive fills. This would suggest a **shadow-log measurement of ST2.0's own cancel-to-add ratio as a market-state proxy** — but this cannot be elevated to a concrete tweak without verifying the claim from the primary source.

**Status of arXiv 2607.11888 θ* formula:** The search confirmed the paper's existence (Zeng & Liu, "Optimal Adaptive Market Making: A Theoretical Framework for High-Yield Liquidity Provision in Perpetual Futures Markets"), but no snippet of equation 30 was retrievable. The partial-fetch status from prior nights is unchanged. Still partially blocked.

---

## (c) Caveats and Unverified Items

1. **arXiv 2610.09691 (Vischi et al.) is a theory paper with no empirical component.** Regret bounds for abstract LOB market making. Assumes zero inventory constraints and a perfectly liquid secondary market. Not applicable to ST2.0's execution context.

2. **Yueshen "Queuing Uncertainty" — ALL CLAIMS UNVERIFIED.** The findings cited above ("end-of-queue always loses," "cancel-to-add ratio reflects adverse selection") came from a web search engine summary of the abstract, NOT a direct fetch of the primary source. The INFORMS DOI page returned HTTP 403; the SMU institutional repository returned an empty page. These claims should not be acted upon until the paper is directly accessed.

3. **Garriott et al. (JFM 2025) abstract-only.** The 8.4% depth-reduction finding is from the abstract summary on IDEAS/repec. The result that matters (quantitative relationship between queue position and adverse selection in bps) is in the full text, which remains inaccessible.

4. **Persistent unverified leads (unchanged):**
   - SSRN 6693260 (Chang, BTC perp flow-adjusted bid-absorption): HTTP 403 persists.
   - Microstructure Lab Substack (post-sweep LOB recovery, 180,590 events, Binance/GateIO/OKX): paywalled.
   - arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77): partially fetched, θ* not retrieved.

5. **Literature saturation status: Third consecutive night with no new actionable tweak.** The standard arXiv sweep, practitioner blogs, and SSRN searches are cycling through the same papers. The two new leads with directional relevance (Yueshen, Garriott) are inaccessible. The only forward path in the research series is empirical deployment of Tweaks 47/65 to generate ST2.0-specific fill data.

---

## Summary

| Item | Description | Status |
|------|-------------|--------|
| arXiv 2610.09691 (Vischi et al., Oct 2026) | New to corpus: pure theory (regret bounds for abstract market making); no real data, no crypto, not actionable. | NEW — VERIFIED (HTML fetched); NOT actionable |
| Garriott/van Kervel/Zoican (JFM 2025) | Abstract-level: queue position affects adverse selection, crowding-out effect, futures data, 8.4% depth reduction. Corroborates corpus; no new threshold. | PARTIALLY VERIFIED (abstract only); NOT actionable |
| Yueshen "Queuing Uncertainty" (Mgmt Science 2025) | Search summary: "end-of-queue always loses money in equilibrium"; "cancel-to-add count ratio reflects adverse selection." Structurally new if verified. | UNVERIFIED — primary source inaccessible (403/empty) |
| Tweak 83 | None proposed. | N/A |

**No new forward-testable execution tweak tonight.**

**New unverified lead:**
| — | Yueshen (2025): "cancel-to-add count ratio reflects adverse selection" — ST2.0's own cancel-to-add ratio as a market-state proxy | UNVERIFIED — attempt primary source access in future night |

**Unverified leads (persistent, unchanged from Night 93):**
| — | Flow-adjusted ask-absorption proxy (SSRN 6693260, BTC perp) | TBD | UNVERIFIED — HTTP 403 |
| — | Post-sweep delayed entry + LOB recovery timing (Microstructure Lab Substack) | TBD | UNVERIFIED — paywalled |
| — | arXiv 2607.11888 equation 30 (full θ* optimizer for Tweak 77) | TBD | PARTIALLY FETCHED |

**Undeployed priority stack (unchanged from Night 93):**
1. Tweaks 47/65 — queue rank proxy + time-to-fill logging
2. Tweak 75 — OBI upper-bound gate
3. Tweak 76 — Realized-vol gate
4. Tweak 77 — σ-adaptive cancel threshold
5. Tweak 78 — Gate hysteresis
6. Tweak 79 — Tape intensity gate
7. Tweak 74 — stale-gate per-cycle re-validation (two theoretical anchors: arXiv 2607.28323 + arXiv 1803.05690)
8. Tweak 72 — funding-window gate
9. Tweaks 70, 73 — cancel-side asymmetry, OBI percentile logging
10. Tweak 71 — transient-order OBI filter
11. Tweak 80 — Quarter-hour proximity shadow log
12. Tweak 81 — Robust volume Z-score shadow log
13. Tweak 82 — FIFO time-to-fill queue classification

**Research series status:** 82 tweaks, 94 nights. Third consecutive night with no new actionable tweak. Literature saturation confirmed. Empirical deployment of Tweaks 47/65 is the only path to advancing beyond "proposed" on the most important hypotheses. New lead: Yueshen (2025) on cancel-to-add ratio as adverse-selection signal — requires primary source access to verify.
