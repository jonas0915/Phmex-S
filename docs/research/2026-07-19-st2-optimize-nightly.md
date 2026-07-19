# ST2.0 Execution Optimization — Night 23
**Date:** 2026-07-19 | **Focus:** Maker execution quality, passive fill adverse selection

---

## What's NEW vs Prior 22 Nights

**Summary entering Night 23:** Nights 1–22 exhausted the academic literature for small passive directional maker execution on crypto perpetual altcoin futures. Night 22 closed the research series with 22 tweaks queued, 0 deployed, and a recommendation to halt and implement instead. Tonight ran 4 genuinely new search angles (round-number price clustering, systematic repricing/chasing, time-to-fill tail risk, placement depth inside spread). Two findings are new material; two angles were complete misses.

---

## Searches Run Tonight

| Angle | New? | Verdict |
|---|---|---|
| Round number price clustering effects on passive fill rates | Complete miss — no literature found | No applicable material |
| Post-only repricing / chase order mechanics | No academic papers; exchange-native feature docs found | Practically applicable — see Finding A |
| Passive limit order time-to-fill distribution / adverse fill baseline | New empirical paper found | Applicable — see Finding B |
| Optimal placement depth inside spread for crypto | No new papers | Angle covered via prior micro-price / OFI nights |

---

## Finding A — Chase Limit Orders: Industry-Standard Repricing Is Productized

**Source type:** Exchange help center documentation (not academic)

**Bybit documentation** (https://www.bybit.com/en/help-center/article/Chase-Order):

> "A Chase Limit Order is a limit order placed at the best bid or ask that dynamically adjusts its entry price to match changing market conditions until the order is filled, canceled, or reaches a maximum chase distance. Since Chase Limit Orders are Maker orders, you can benefit from lower trading fees."

BingX (https://bingx.com/en/support/articles/12297207022991) offers the same feature labeled "Chase Limit Order" for perpetual futures. MEXC also offers it. Phemex does **not** appear to offer this feature natively.

**What this confirms for ST2.0:**

Systematic cancel-and-reprice to the current best bid, while maintaining POST_ONLY (maker) status throughout, is a well-established and production-grade execution strategy — productized into exchange UI by at least three competing perp venues. The strategy is: post at best bid → if the bid moves away, cancel and repost at new best bid → repeat until filled or max-distance threshold is hit.

**The unsolved piece:** What is the correct "maximum chase distance" before the original signal is stale? Bybit/BingX expose this as a user parameter but do not specify how to set it. This is the critical calibration question — chasing too far means executing at a materially different price than the signal triggered at, which may invert the expected edge entirely.

**Why this matters for ST2.0 specifically:** ST2.0 currently posts once and waits. If the inside bid moves away by even 1–2 ticks, ST2.0 sits back-of-queue (or off-book) for the full wait period. Systematic repricing to stay at the inside bid would increase fill rate — but at the cost of chasing the price, which is exactly the adverse selection pattern already documented. The max-distance parameter is the dial that determines whether this helps or hurts. Without data on how far the bid moves in the 15–20 seconds after a buy-absorption signal, this cannot be calibrated safely.

**Forward-test tweak (shadow-log, Tweak 23):** Log `bid_drift_bps` — how many basis points the inside bid moves from the signal price over the 20s post-signal window, for filled and unfilled trades separately. If bid_drift_bps is small on filled trades (bid stays near signal price) and large on misses (bid runs away), systematic repricing to stay at the inside is warranted. If bid_drift_bps is large on both, repricing just increases adverse fill volume.

**Caveats:** This is practitioner/exchange documentation, not peer-reviewed. No empirical data on whether chase orders improve or worsen adverse selection outcomes. The Bybit/BingX docs do not quantify fill rate improvement or net PnL impact.

---

## Finding B — ~80% of Passive Limit Order Fills Are Structurally Adverse (CME Empirical)

**Source:** arXiv:2409.12721v2 — "Market Simulation Under Adverse Selection." CME data: ES, NQ, CL, ZN futures. April 23–25, 2024.

Verified direct quotes from the HTML version (https://arxiv.org/html/2409.12721v2):

> "Adverse fills occur when a passive MM's limit order executes at a disadvantageous price, specifically when the order is 'picked off,' meaning that immediately after execution, the new trade position is out of the money when marked-to-market."

> "A significant portion of the total number of LO fills in ES, NQ, CL and ZN were adverse" — the authors calibrate their simulation with non-adverse fill probability **ρ = 0.2 based on empirical evidence**, implying roughly **80% of passive fills on these CME contracts were adverse**.

> "Existing simulation frameworks overestimate strategy performance by treating price processes and market orders independently, thereby failing to capture adverse fills."

**What this establishes for ST2.0:**

ST2.0's 43% fill rate with adversely-clustered outcomes is not an anomaly fixable by timing alone — it appears to be the baseline regime for passive limit orders in liquid futures markets, even before any signal or strategy is applied. The 80% adverse fill rate on CME liquid contracts is the structural floor: if even highly liquid, heavily-traded markets have ~80% adverse passive fills, then a slow, small, no-rebate maker on Phemex altcoin perps is operating in the worst possible regime (slower queue, worse position, more adverse selection, no rebate to compensate).

**Critical implication:** This reframes the question. The problem is NOT "how do we get filled more" — higher fill rate on adverse conditions makes the strategy worse. The question IS "how do we selectively get filled only on the non-adverse ~20% of opportunities." That means the LOB state gating work from prior nights (Tweaks 6, 9, 10, 11, 20, 21, 22) — filtering to only post when the book is in states that correlate with non-adverse fills — is the correct direction, not repricing/chasing.

**Limitations:** CME equity index and commodity futures (ES/NQ/CL/ZN) have profoundly different microstructure from Phemex altcoin perps: different tick sizes, HFT presence, queue mechanics, and participant mix. The 80% number should not be directly imported as a Phemex figure. Treat as directional confirmation that adverse fill dominance is structural, not as a precise estimate for our venue/size/symbol.

---

## Unverified Source (Manual Review Recommended)

**arXiv:2307.04863** — Title not confirmed (HTML version returned 404; full PDF 4.3 MB, not parseable). Abstract page describes a paper covering: (1) the decision to post a limit order vs immediately execute, (2) optimal placement distance, and (3) **"clean-up cost that occurs in the case of non-execution."**

The "clean-up cost" framing is directly relevant to ST2.0: if a limit order misses, the bot still has a signal it wants to act on. The cost of either abandoning the signal or chasing with a market order is the clean-up cost. If this paper models it formally, it may provide a framework for calibrating the max-chase-distance from Finding A. **UNVERIFIED — full text not read. Manual read recommended before acting on this.**

---

## Forward-Testable Tweaks Tonight

| # | Tweak | Source | Priority |
|---|---|---|---|
| 23 | Log `bid_drift_bps` — how far the inside bid moves from signal price in 20s post-signal, for fills vs misses separately | Finding A (exchange chase-order docs) | **PRIORITY (2–3 lines)** |

Prior priority tweaks 4, 6, 9, 10, 11, 12, 14 remain unimplemented. Tweak 23 is additive — log only, no gate change.

---

## Honest Caveats

1. **Finding A (Chase Limit Orders)** is exchange documentation, not empirical research. It confirms the mechanism is viable and productized, but provides no data on whether systematic repricing helps or hurts PnL on adversely-selected signals.

2. **Finding B (80% adverse baseline)** is CME, not crypto perps. The magnitude is not transferable. The structural conclusion (adverse dominance is the baseline regime) is directionally credible but not quantitatively precise for Phemex altcoin perps.

3. **arXiv:2307.04863** is promising but UNVERIFIED — full text inaccessible tonight. Should be manually read before any implementation decision.

4. **Two search angles were complete misses:** round-number price clustering effects on fill rates produced no literature; optimal placement depth inside spread returned only prior-covered material.

5. **22 tweaks remain queued, 0 deployed.** Tweak 23 brings the total to 23. The binding constraint has never been knowledge — it is empirical data from live shadow-logging. Priority tweaks 4, 6, 9, 10, 11, 12, 14 are each 2–5 lines and have been queued for 3–7 weeks.

---

## Cumulative Forward-Test Queue (23 Tweaks)

Priority tweaks (unchanged from N22) are: **4, 6, 9, 10, 11, 12, 14** — each 2–5 lines of shadow logging.

Tweak 23 (bid_drift_bps log) added tonight. Full queue archived in N22 report; not reproduced here to save space.

---

## Night 23 Bottom Line

Two new findings. One (Finding A — Chase Limit Orders) is practically applicable but requires calibration data we don't have; it points to logging bid_drift_bps (Tweak 23) before any repricing logic is implemented. One (Finding B — 80% adverse fill baseline) reinforces that increasing fill rate is not the objective — selective gating to hit the non-adverse ~20% is, which validates the LOB-state gating queue (Tweaks 6, 9, 10, 11, 20, 21, 22) as the highest-leverage direction. The paper 2307.04863 warrants manual follow-up.

**Research series status:** 23 nights, 23 tweaks queued, 0 deployed. The recommendation from Nights 20–22 stands: implement priority tweaks 4, 6, 9, 10, 11, 12, 14 (one coding session), collect 30+ tagged fills per diagnostic variable, then return to research if data suggests new questions.
