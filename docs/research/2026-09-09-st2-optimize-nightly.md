# ST2.0 Maker Execution — Nightly Optimization Research
**Night 68 | 2026-09-09 | Focus: Passive POST-ONLY limit SELL execution quality**

---

## What's New vs. Prior Nights (Nights 1–67)

Prior nights have confirmed 50 tweaks across: spread gates, buy_ratio tightening, cancel-and-wait, queue depth (v_prior_sell) logging, queue_rank logging, and posting timing (early in absorption window). The confirmed 20-night prior drought (N47-N66) was broken on N67 with Tweaks 48-50.

Tonight's search focused on four angles not fully mined in prior nights:
1. Optimal tick-distance from mid for adverse-selection tradeoff
2. Intraday session timing effects on maker fill quality
3. Partial fill remainder handling
4. Funding rate state as an entry condition gate

**What is genuinely NEW tonight:** Angles 2 and 4 yielded confirmed primary-source findings not cited in any prior night. Angle 1 produced one new paper (arXiv:2407.16527) that formalizes the negative-fill-drift mechanism but does not change the practical recommendation set. Angle 3 is fully covered by prior Tweak 50 (cancel-and-wait, Albers QF 25(6)).

---

## Confirmed New Findings

### Finding A — Quarter-Hour Boundary Effect (Angle 2)
**Source:** arXiv:2607.09426v2 — "The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures," Chan Kim & Peter Reinhard Hansen (UNC, Aug 2026)
**URL:** https://arxiv.org/html/2607.09426v2

**Verified quotes from paper:**
> "trading activity and short-hour price variation concentrate into sharp bursts at every minute, every fifth minute, every quarter-hour, and most prominently at the top of the hour"

> "roughly 26% more trades, 32% higher dollar volume, and 26% larger absolute returns than the corresponding interval of ordinary minutes"

> "the pattern is essentially unchanged when we exclude the three quarter-hours each day that coincide with funding settlement (00:00, 08:00, and 16:00 UTC), so the effect is not driven by the funding-settlement events"

**What this means for ST2.0:** The 60s before :00, :15, :30, :45 of any hour carries ~26-32% elevated volume and absolute price moves in crypto futures. A passive SELL posted into that window is more likely to be immediately run through by algorithmic volume spikes (adverse fill via burst activity rather than genuine absorption). Funding settlement hours (00:00, 08:00, 16:00 UTC on Phemex) are *not* specially elevated beyond the general pattern — no extra avoidance needed for those specifically.

**NOT in prior nights.** This paper is Aug 2026 and was not available during N1–N67.

---

### Finding B — Funding State Affects Short Inventory Economics (Angle 4)
**Source:** arXiv:2605.06405 — "Funding-Aware Optimal Market Making for Perpetual DEXs" (2025/2026)
**URL:** https://arxiv.org/html/2605.06405

**Verified quotes and claims from paper (HTML fetch):**
> "inventory creates both mark-to-market exposure and a state-dependent funding cash flow"

> "a long position can be either desirable when expected funding is negative and costly when expected funding is positive"

Empirically confirmed funding mean-reversion half-lives: **2.3 to 5.6 hours** across ETH, BTC, SOL on Hyperliquid (Nov-Dec 2025 data).

> "OU-plus-jump diagnostics showed significant likelihood improvements, suggesting pure Gaussian diffusion underestimates funding tail risk"

**What this means for ST2.0:** This paper is DEX-focused (Hyperliquid), not Phemex CEX, so numbers are not directly portable. But the mechanism is exchange-agnostic: when a passive SELL fills on ST2.0, the resulting short position either earns carry (positive funding, longs pay shorts) or pays carry (negative funding, shorts pay longs). With a 15-min reversion horizon and a 2.3-5.6h funding half-life, the current funding rate is a meaningful predictor of the carry cost over the hold period. When funding is deeply negative (shorts paying longs > threshold), every bar the position sits open is more expensive, compounding the loss on an adverse fill. A **funding-state gate** — suppressing new passive SELL entries when funding < -X bps — is mechanistically supported. The threshold X requires calibration against Phemex funding data (unverified at the code level tonight).

**NOT in prior nights** as a concrete entry gate recommendation with primary source support.

---

### Supporting Finding — Negative Drift of a Limit Order Fill (Angle 1)
**Source:** arXiv:2407.16527 — "The Negative Drift of a Limit Order Fill," DeLise (July 2024)
**URL:** https://arxiv.org/abs/2407.16527

**Verified quotes from abstract:**
> "limit order fills are caused by and coincide with adverse price movements, which create a drag on the market maker's profit and loss"

> "Buy order fills are accompanied by downward mid price movements and sell orders are accompanied by upward movements, on average."

> "traditionally, market making models rely on an assumption of low-cost random fills, when in reality there is high-cost non-random fill behavior"

**Implication for ST2.0:** This formalizes the adverse-selection-by-construction mechanism already confirmed in the June 2026 synthesis. It does NOT yield a new actionable tweak on its own — it confirms that posting at the inside offer concentrates adverse fills (price has to run up to your level = adverse). Posting 1 tick back from the inside ask has lower fill probability but yields fills that are relatively less adversely driven. This is consistent with existing logic; no new deployment action required.

**Note on quantitative claims:** A magnitude of approximately -0.0065 ticks per fill was referenced in the search summary but was NOT directly quotable from a fetched primary source text. Treating as **PLAUSIBLE, not verified.** Do not use in live decision-making.

---

## Forward-Testable Execution Tweaks

### Tweak 51 — Quarter-Hour Boundary Blackout Gate
**Source:** arXiv:2607.09426 (verified)
**Mechanism:** Block new ST2.0 passive SELL entries in the 45-second window before each quarter-hour mark (:59:15→:00:00, :14:15→:15:00, :29:15→:30:00, :44:15→:45:00 of any hour).
**Implementation sketch:** In `bot.py` at the ST2.0 entry check, add:
```python
import datetime
now_utc = datetime.datetime.utcnow()
seconds_in_quarter = (now_utc.minute % 15) * 60 + now_utc.second
if seconds_in_quarter >= (15 * 60 - 45):  # last 45s of quarter
    return  # skip entry
```
**What to measure:** Log `qh_blocked=True/False` at each attempt. Compare adverse-fill rate for attempts within vs. outside the 45s window. Calibrate window width (try 30s, 45s, 60s).
**Caveat:** The 2607.09426 finding is for crypto futures broadly (paper does not specify Phemex or linear perps specifically). Apply cautiously; instrument before deploying as a hard gate.

---

### Tweak 52 — Funding-State Entry Gate (Candidate)
**Source:** arXiv:2605.06405 (verified mechanism; threshold unverified)
**Mechanism:** Suppress passive SELL entry when current Phemex funding rate is below a negative threshold (e.g., funding < -0.01% per 8h = shorts paying longs at elevated rate). Funding is already fetched by the bot periodically (verify in exchange.py or bot.py — grep for "funding").
**Implementation sketch:** At ST2.0 entry check, add funding gate:
```python
if current_funding_rate < FUNDING_GATE_THRESHOLD:  # e.g., -0.0001
    log("st2_blocked: negative funding")
    return
```
**What to measure:** Log `funding_at_attempt` and `funding_gate_blocked` for every ST2.0 attempt. Compare win rate / avg outcome grouped by funding quintile before deciding the threshold.
**Caveat:** This is a DEX-paper mechanism applied to a CEX (Phemex). Phemex uses 8-hour funding intervals. The paper's results are Hyperliquid-specific. Treat as Candidate (instrument first, deploy only after backtesting against Phemex funding data). Do NOT deploy as a hard gate without data.

---

### Tweak 53 — Log `seconds_to_quarter_hour` at Every Attempt (Instrumentation)
**Source:** Enables Tweak 51 calibration (arXiv:2607.09426)
**Mechanism:** At every ST2.0 entry attempt, log the number of seconds remaining until the next quarter-hour boundary. This is a 1-line addition:
```python
seconds_to_qh = (14 - now_utc.minute % 15) * 60 + (60 - now_utc.second)
log(f"st2_attempt seconds_to_qh={seconds_to_qh}")
```
**What to measure:** Correlate `seconds_to_qh` with subsequent fill/no-fill and adverse/non-adverse outcome. This data pays down Tweak 51 before it becomes a hard gate.

---

## Priority Against Existing Undeployed Actions

The following were flagged in N64-N67 as highest-priority undeployed instrumentation (5 lines of code each). They remain undeployed per prior reports and take precedence over tonight's new tweaks:

1. `time_to_fill` logging (N64) — needed for all fill-quality analysis
2. `spread_pct` logging at each attempt (Tweaks 45/48) — needed to validate spread gate
3. `v_prior_sell` logging (Tweak 46) — needed to validate queue-depth gate
4. `queue_rank_at_fill` logging (Tweak 47) — needed to validate front-of-queue hypothesis
5. Deploy confirmed Tweaks 4, 6, 9, 10, 11, 12, 14

Tweak 53 (seconds_to_quarter_hour logging) slots in at the same instrumentation level — add it alongside items 2-4 above.

---

## What Was NOT Found (Honest Gaps)

- **No paper** gives a quantitative tick-distance recommendation specific to crypto perpetuals (e.g., "post N ticks back from best ask for optimal adverse-selection-adjusted fill rate"). The theoretical result from Cont et al. (arXiv:1610.00261) was binary-compressed and unreadable from fetch.
- **No paper** measures maker fill adversity rates by UTC hour on Phemex/Binance with maker-vs-taker granularity. The quarter-hour result is for all-trades volume/return, not specifically maker fill adversity.
- **No empirical paper** tests funding-regime-binned maker fill adversity on any CEX. The 2605.06405 finding is optimal-control theory on a DEX.
- **Partial fill handling** (Angle 3): No dedicated paper found. The inferential chain (DeLise 2407.16527 → 1707.01167) supports cancel-on-adverse-signal but is fully covered by Albers QF (Tweak 50). No new tweak warranted.

---

## Cumulative Tweak Count

| Category | Count |
|----------|-------|
| Confirmed + deployed | 3 (Tweaks 1, 2, 3) |
| Confirmed + undeployed | 44 |
| New candidates tonight | 3 (Tweaks 51, 52, 53) |
| Total candidates | 9 (45–53) |
| Conditional | 1 |

---

*Sources fetched and verified this session: arXiv:2607.09426v2, arXiv:2605.06405, arXiv:2407.16527, arXiv:2409.12721v2, arXiv:1707.01167v1. All claims marked "verified" were read from the fetched source text. Claims marked "unverified" or "PLAUSIBLE" were not directly confirmed from a fetched source.*
