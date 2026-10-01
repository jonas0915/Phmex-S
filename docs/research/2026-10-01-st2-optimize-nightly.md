# ST2.0 Maker Execution — Nightly Optimization Research
**Night 78 | 2026-10-01 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## (a) What's New vs. Prior Reports (Nights 1–77)

Prior nights (last covered: N77, 2026-09-30) documented Tweaks 1–66. N77 explicitly concluded
that **the literature is saturated** and that October 2026 q-fin.TR had zero submissions. N78
searched four genuinely new angles not previously attempted at this depth:

1. **Hawkes process trade-arrival clustering as a fill-timing gate** — whether conditioning passive
   entry on low-intensity inter-trade phases (between Hawkes clusters) reduces adverse selection
2. **Iceberg/hidden order detection at the ask level** — whether hidden sell liquidity above
   ST2.0's posting price reduces adverse fills (2025–2026 papers)
3. **Passive maker order survival time prediction on crypto CEX** — separate framing from prior
   OFI-decay searches; focused on predictive models for how long a passive sell survives before
   fill or cancel
4. **q-fin.TS (statistical methods) arxiv category Oct 2026** — parallel to q-fin.TR crawls
   in N73–77; fetch of q-fin.TS Oct 2026 listing

**What is genuinely NEW tonight: Nothing.**

Six candidate papers were fetched and evaluated. All rejected:

- **arXiv:2502.17417** (Lalor & Swishchuk, Feb 2025) — "Event-Based LOB Simulation under a
  Neural Hawkes Process: Application in Market-Making." Uses some real data to calibrate
  simulations, but is primarily a market-making *simulation framework*. No empirical fill quality
  or adverse selection measurement for passive orders on crypto CEX.
  **Rejected: simulation framework, no empirical passive fill quality data.**

- **arXiv:2606.15715** (Barone & Lillo, June 2026) — "Trading in the Sunshine or in the Shade:
  Market Impact and Adverse Selection on Hyperliquid." Studies 4.3M hidden metaorders vs.
  465K visible TWAP executions on Hyperliquid DEX. Finds visible (announced) TWAP orders face
  lower execution costs. Conceptually interesting but not applicable: this is a DEX, ST2.0
  posts on Phemex CEX where all orders are already visible, and ST2.0 is a passive *maker* not
  a TWAP taker.
  **Rejected: DEX, taker execution framework, not passive CEX maker fill quality.**

- **arXiv:2607.11888** (Zeng & Liu, July 2026) — "Optimal Adaptive Market Making: A Theoretical
  Framework for High-Yield Liquidity Provision in Perpetual Futures Markets." Explicitly a
  theoretical stochastic control framework with zero maker fees. Numerical analysis with
  synthetic parameters. No real exchange data.
  **Rejected: theoretical, no empirical data.**

- **arXiv:2403.02572** (Lokin & Yu, March 2024) — "Fill Probabilities in a Limit Order Book with
  State-Dependent Stochastic Order Flows." Derives semi-analytical fill probability expressions,
  validated on FX spot market data (not crypto). Good model but wrong asset class.
  **Rejected: FX spot market, not crypto perpetual.**

- **arXiv:2609.13597** — Already in corpus (N75). Returned again in queue-position searches.

- **arXiv:2609.18019** — Already in corpus (N77). Returned again in survival-time searches.

The q-fin.TS October 2026 listing fetch returned HTTP 400 (no cached content yet). The q-fin.TR
October 2026 listing confirmed empty in N77 and there has been no new submission in the 24 hours
since.

---

## (b) No New Confirmed Finding

No primary source was found tonight that is (a) new to the corpus, (b) empirically grounded on
real market data, and (c) applicable to ST2.0's passive-sell execution on Phemex crypto perps.

The N77 saturation conclusion stands: **78 nights of search have covered the accessible
literature on passive CEX perpetual maker execution quality.** No new applicable paper has been
found since N76 (Tweak 66, LOB cancel-state snapshot). The three persistent open gaps
(Phemex-calibrated adverse-selection measure; crypto-perp-native OFI decay study; passive-maker
CEX markout paper) remain unfilled by external literature and are unlikely to be filled by
further searches on the same angles.

---

## (c) No New Forward-Testable Tweak

No new Tweak is proposed tonight. The undeployed action stack from N77 is unchanged.

---

## (d) Caveats

1. **arXiv:2606.15715 (Barone & Lillo, Hyperliquid):** The "sunshine trading" concept has an
   interesting structural inversion for CEX passive makers: on a DEX where TWAP orders are
   publicly visible *and* come with a commitment signal, liquidity provision improves. On Phemex
   CEX, ST2.0's passive sell is visible but carries no commitment signal — it can be cancelled
   at any time. The paper's finding that "visible TWAPs face lower execution costs" relies on
   the permanence of the signal, not mere visibility. Cannot operationalize for ST2.0.

2. **arXiv:2607.11888 (Zeng & Liu, perp MM framework):** "Zero maker fees" framing is
   Phemex-relevant, but the paper is purely theoretical. The phase transition between profitable
   and unprofitable regimes (23 figures of numerical analysis) is computed from synthetic
   volatility and inventory parameters, not real exchange data. Unverifiable.

3. **Persistent open gaps (N1–N78, unresolved):**
   - Phemex-calibrated adverse-selection measure: no primary source found in 78 nights
   - Crypto-perp-native OFI signal decay over the order-resting window: no paper
   - Passive-maker-specific markout paper on CEX perpetuals: no paper
   - Optimal delayed-posting timing (wait for taker flow peak before entering): no paper

4. **Recommended pivot:** The undeployed instrumentation stack (Tweaks 45–66, prioritized with
   Tweak 47/65 queue rank logging at #1) is the highest-value next action. Further literature
   sweeps are low-probability. Generating ST2.0's own empirical data — specifically `queue_rank_proxy`
   at posting and `time_to_fill` at fill — is the only path to filling the gaps the literature
   cannot fill.

---

## Priority Ordering (Undeployed Actions, Full Stack)

**Unchanged from N77:**

1. `queue_rank_proxy` at posting + `time_to_fill` at fill (Tweaks 47/65) — #1 priority
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
| New papers rejected tonight | 4 (2502.17417, 2606.15715, 2607.11888, 2403.02572) |
| Total rejection events (N1–N78) | cumulative; see prior reports |

---

*Sources fetched and evaluated this session:*
- *arXiv:2502.17417 (Lalor & Swishchuk, Feb 2025, Neural Hawkes LOB simulation — rejected: simulation framework)*
- *arXiv:2606.15715 (Barone & Lillo, June 2026, Hyperliquid DEX TWAP execution — rejected: DEX, taker execution)*
- *arXiv:2607.11888 (Zeng & Liu, July 2026, theoretical perp MM framework — rejected: theoretical, no empirical data)*
- *arXiv:2403.02572 (Lokin & Yu, March 2024, FX spot fill probabilities — rejected: FX spot, not crypto perp)*
- *Confirmed prior corpus: arXiv:2609.13597, arXiv:2609.18019*
- *q-fin.TS Oct 2026 listing: HTTP 400, inaccessible; q-fin.TR Oct 2026: zero submissions (confirmed N77)*
