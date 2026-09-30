# ST2.0 Maker Execution — Nightly Optimization Research
**Night 77 | 2026-09-30 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–76)

Prior nights (last covered: N76, 2026-09-29) documented Tweaks 1–66 across: spread gates,
buy_ratio tightening, cancel-and-wait, queue depth/rank logging, early posting in absorption
window, quarter-hour blackout (Tweak 51), funding gate (Tweak 52), seconds-to-qh (Tweak 53),
OB imbalance regime audit (Tweak 54), 1s adverse-selection baseline (Tweak 55), aggressor-ratio
gate (Tweak 56), OFI saturation gate (Tweak 57), spread-normality gate (Tweak 58), multi-level
OFI depth concentration (Tweak 59), price-deviation cancel-and-repost trigger (Tweak 60), VPIN
suppression gate (Tweak 61), cycle-offset logging (Tweak 62), symbol-specific OFI reliability /
BTC vs ETH asymmetry (Tweak 63), flow intensity over LOB depth (Tweak 64), queue rank promoted
to #1 priority (Tweak 65), and LOB state snapshot at cancel events (Tweak 66).

Tonight's sweep searched four angles not previously covered at this depth:

1. **Optimal price offset for passive maker orders under adverse selection** — whether any 2026
   paper provides empirical placement-distance calibration for crypto perp makers
2. **Delayed initial posting** — whether any paper quantifies the adverse-selection reduction from
   waiting for taker flow to crest before posting a passive sell (distinct from cancel-and-repost,
   which acts on an existing order)
3. **October 2026 q-fin.TR new submissions** — direct crawl of the full listing
4. **Passive market impact (point process approach)** — arXiv:2412.07461, not previously checked

**What is genuinely NEW tonight:**

**Nothing.** All four angles returned no new applicable primary sources.

- **Angle 1 (optimal price offset):** arXiv:2508.20225 (Barzykin, Bergault, Guéant & Lemmel,
  Aug 2025 / revised Aug 2026) — "Optimal Quoting under Adverse Selection and Price Reading" —
  appears new to the corpus (not in any prior rejected list seen). However, it is a purely
  theoretical framework for FX OTC market makers with no empirical market data. Numerical
  examples use synthetic parameters ("daily volatility 100 bp", simulated intensities). Not
  calibrated to any exchange. The "price reading" component addresses how a maker's own quotes
  signal inventory direction — not relevant to ST2.0's single-side passive-sell structure.
  **Rejected: theoretical, FX-only, no empirical data.**

- **Angle 2 (delayed initial posting):** No paper found. The closest result is arXiv:1610.00261
  (already in corpus since N1) and arXiv:2609.18019 (in prior corpus, N73+). No new paper
  specifically addresses waiting for the taker-flow peak before placing a passive maker order,
  as distinct from cancel-and-repost on an existing order.

- **Angle 3 (October 2026 q-fin.TR listing):** Fetched directly. Page states explicitly: "No
  updates for this time period." Zero papers submitted to q-fin.TR in October 2026 to date.

- **Angle 4 (arXiv:2412.07461, Dec 2024):** "Passive Market Impact: A Point Process Approach"
  (Chahdi, Rosenbaum, Szymanski). Theoretical microstructure model with no specific market data
  in the abstract. Addresses passive meta-order market impact conceptually, not fill quality or
  adverse selection measurement. Not applicable to ST2.0.
  **Rejected: theoretical, no empirical data.**

Additional candidates checked and rejected:
- arXiv:2510.27334 (Oct 2025): RL market making in Hawkes LOB simulation — simulation-based,
  not empirical crypto data.
- arXiv:2606.05882 (June 2026): Agent-based computational model — simulation-based.
- October 2026 Medium article on crypto perp meta-order flow: HTTP 403, inaccessible.

---

## (b) No New Confirmed Finding

No new primary source was found tonight that is (a) new to the corpus, (b) empirically grounded
on real market data, and (c) applicable to ST2.0's passive-sell execution on Phemex crypto perps.

**The literature on this specific problem — passive CEX perpetual maker execution quality for
short-reversion strategies — is saturated with the current search methodology.**

N76 already flagged this: "Tonight's crawl of the full September 2026 q-fin.TR listing (9
papers)... returned only one new candidate, and that candidate is primarily simulation-based."
Tonight's October 2026 listing is empty. The corpus built over N1–N77 is comprehensive for the
available literature.

---

## (c) No New Forward-Testable Tweak

No new Tweak is proposed tonight. The highest-value undeployed action stack from N76 remains
unchanged and is reproduced below for reference.

---

## (d) Caveats

1. **arXiv:2508.20225 (Barzykin et al.):** Confirmed new to corpus tonight, but rejected as
   non-applicable: FX OTC context, synthetic parameters, no empirical data. The "adverse
   selection and price reading" framing is conceptually interesting (quote asymmetry reveals
   inventory direction) but cannot be operationalized for ST2.0's structure without real data.

2. **Persistent open gaps (N1–N77, unresolved):**
   - A Phemex-calibrated adverse-selection measure: no primary source found across all 77 nights
   - A crypto-perp-native study of OFI signal decay over the order-resting window: no paper
   - A passive-maker-specific markout paper on CEX perpetuals (not DEX, not spot): no paper
   - Optimal delayed-posting timing (wait for taker flow peak before entering): no paper

3. **Literature saturation is now confirmed.** The prior-corpus rejection lists across N1–N77
   cover the searchable space of applicable q-fin.TR papers. The most productive next action
   is deploying the undeployed instrumentation stack (Tweaks 45–66) to generate ST2.0's own
   empirical data — the gaps the literature cannot fill.

---

## Priority Ordering (Undeployed Actions, Full Stack)

**Unchanged from N76:**

1. `queue_rank_proxy` at posting + `time_to_fill` at fill (Tweaks 47/65) — #1 priority
   (arXiv:2609.13597: queue position ignorance costs ~0.4–1.0 bps, consuming 30–75% of gross edge)
2. `spread_pct` logging at every attempt (Tweaks 45/48) — 2 lines
3. `v_prior_sell` logging (Tweak 46) — 2 lines
4. `seconds_to_qh` logging (Tweak 53) — 1 line
5. `aggressor_ratio_at_attempt` logging (Tweak 56)
6. `ofi_percentile_at_attempt` logging (Tweak 57)
7. `spread_ratio_at_attempt` logging (Tweak 58)
8. `st2_ofi_depth_ratio` logging (Tweak 59)
9. `adverse_move_bps_at_cancel` + `cancel_reason` logging (Tweak 60)
10. `vpin_proxy_at_attempt` logging (Tweak 61)
11. `seconds_into_cycle` logging (Tweak 62)
12. `symbol + ob_imbalance + outcome` per-fill logging (Tweak 63)
13. `flow_imbal = 2*tape.buy_ratio-1` + `ob_imbalance` at every entry (Tweak 64)
14. Full LOB state snapshot at cancel events (Tweak 66)

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 46 (Tweaks 4–66) |
| New candidates tonight | 0 |
| Total candidates | 22 (Tweaks 45–66) |
| Negative findings | +0 new tonight |

---

*Sources checked this session:*
- *October 2026 q-fin.TR listing: fetched directly — zero papers submitted*
- *arXiv:2508.20225 (Barzykin et al., Aug 2025/Aug 2026 v6, FX OTC maker quoting — rejected:
  theoretical, synthetic parameters, no empirical data)*
- *arXiv:2412.07461 (Chahdi, Rosenbaum, Szymanski, Dec 2024/Jul 2026, passive impact model —
  rejected: theoretical, no empirical data)*
- *arXiv:2606.05882 (Ochędzan & Antulov-Fantulin, Jun 2026, agent-based model — rejected:
  simulation-based)*
- *arXiv:2510.27334 (Jafree, Jain & Firoozye, Oct 2025, RL Hawkes LOB — rejected:
  simulation-based)*
- *Rejected as prior corpus: arXiv:2609.18019, arXiv:2608.21888, arXiv:2609.13597,
  arXiv:2604.20949, arXiv:2607.09230, arXiv:1610.00261, arXiv:2502.18625*
