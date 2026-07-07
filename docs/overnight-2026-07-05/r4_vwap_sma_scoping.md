# R4 — VWAP + 9/15 SMA Cross Scoping Scan (SCREENING-GRADE)

**Date:** 2026-07-05 overnight | **Status:** SCOPING ONLY — per project rules, backtests on our own data are artifact-prone and are NEVER a deploy justification. This scan only sizes the signal for slot design.

**Verdict: NEGATIVE expectancy, both variants, both halves, majors and alts. Signal is roughly flat-to-slightly-negative gross; fees make it clearly negative. No slot design warranted on this evidence.**

## Strategy under test (owner's manual)

5m chart, LONG-only:
- **CROSS variant:** 9SMA crosses above 15SMA at bar close AND close > session VWAP → enter at cross-bar close.
- **RETEST variant:** after a qualifying cross, within 6 bars (30 min) a bar's low touches (≤) the 9SMA or the VWAP AND that bar closes back above BOTH → enter at retest-bar close. One retest entry max per cross.

## Data & method

- `backtest_data_june/*_5m.csv` — **22 symbols** (not 20; actual file count), 2026-05-20 03:50 UTC → 2026-07-04 03:40 UTC, **45.0 days**. Halves split at 2026-06-11 15:45 UTC.
- Indicators from `indicators.py`: `sma()` rolling; `vwap()` session VWAP resetting at **UTC midnight** (indicators.py:68 `index.normalize()`), typical price (H+L+C)/3 — helper convention followed as-is.
- Naive fills at signal-bar close. Bracket: SL 1.2% / TP 1.6% off entry (same numbers as live), walked bar-by-bar on H/L; **intrabar both-touched → counted SL (conservative)**; unresolved at data end → marked at last close. Fees 0.12% RT subtracted from every return.
- Script + raw JSON: `docs/overnight-2026-07-05/r4_receipts/` (standalone; strategies.py/bot.py untouched). One config per variant, first-reasonable choices, **zero parameter tuning**.

## Degrees of freedom (honesty ledger)

**9 definitional choices**, each a degree of freedom: (1) strict cross confirmation on closed bars; (2) VWAP = UTC-midnight session per helper; (3) "above VWAP" = signal-bar close > VWAP; (4) retest window N=6 bars; (5) touch = low ≤ 9SMA OR low ≤ VWAP; (6) retest confirm = close > both; (7) SL-wins-ties intrabar; (8) 0.12% RT fee on close fills; (9) 15-bar SMA warmup skip. None were varied.

## 1. Signal frequency (SCREENING-GRADE)

| | CROSS | RETEST |
|---|---|---|
| Total signals (45d × 22 sym) | 5,781 | 3,409 |
| Per day, all symbols | 128.5 | 75.8 |
| Per day per symbol | **5.84** | **3.44** |
| Same-5m-bar cross-symbol collisions | 2,562 | 1,211 |

- **Hours overlap:** bot trades 24h since 2026-06-30 (`TRADING_BLOCKED_HOURS_UTC=` empty, config.py:132) → overlap is 100% by construction.
- **Cooldown:** the 2-min global cooldown is shorter than one 5m bar, so it never blocks two signals on the *same* symbol; raw same-bar multi-symbol collision count above (≈44% of cross signals share a bar with another symbol's signal — a single-position slot would take at most 1 anyway).

## 2. Naive outcome scan (SCREENING-GRADE, net of 0.12% RT fees)

Breakeven WR for the 1.2/1.6 bracket at these fees is **47.1%**. Both variants sit ~10 points below it.

### Bracket exit (SL 1.2% / TP 1.6%)

| Slice | CROSS n / WR / avg net | RETEST n / WR / avg net |
|---|---|---|
| **All** | 5,781 / 37.7% / **−0.263%** | 3,409 / 37.5% / **−0.271%** |
| BTC+ETH | 534 / 34.1% / −0.364% | 330 / 34.2% / −0.363% |
| Alts (20) | 5,247 / 38.1% / −0.253% | 3,079 / 37.8% / −0.262% |
| Half 1 (5/20–6/11) | 2,818 / 33.4% / −0.385% | 1,673 / 33.4% / −0.386% |
| Half 2 (6/11–7/4) | 2,963 / 41.8% / −0.148% | 1,736 / 41.4% / −0.161% |

Outcome mix (cross): 2,162 TP / 3,583 SL / 36 open. Retest: 1,262 TP / 2,118 SL / 29 open.
Expectancy at live $10 notional: cross ≈ **−$0.026/trade**, retest ≈ **−$0.027/trade** (SCREENING-GRADE).

### Fixed-horizon forward returns (net avg, % positive)

| Horizon | CROSS | RETEST |
|---|---|---|
| +15m | −0.118% (33.3% pos) | −0.153% (30.5% pos) |
| +1h | −0.154% (38.1% pos) | −0.186% (36.5% pos) |
| +4h | −0.171% (40.8% pos) | −0.192% (40.3% pos) |

Gross (add back 0.12%): ≈ +0.00% to −0.07% at every horizon — the signal is **flat-to-slightly-negative before fees**. This is not a fee-only problem; there is no positive drift to harvest.

## 3. Honest reading

- **Retest filtering does not help:** WR and expectancy are statistically indistinguishable from the plain cross (−0.271% vs −0.263%). The pullback-confirm step just halves frequency.
- **Consistent negative:** every slice (majors/alts, both halves, all horizons) is negative net. Half 2 is less bad (41.8% WR) but still ~5 points under breakeven — that's regime, not edge.
- **If any number here had been positive** it would still be in-sample naive-fill artifact territory: fills at bar close assume taker-like certainty, while the live slot's PostOnly fill rate is ~15–25% and maker fills are adversely selected by construction (see reference_st2_execution_research). A maker implementation would fill preferentially on the entries that immediately go against you.
- This matches the June-13 edge-hunt-exhaustion finding: momentum/trend entries on this data at this scale don't clear fees.

## Top design gotcha (had this been built)

**VWAP session convention:** `indicators.vwap()` resets at **UTC midnight**, so the first ~1–2 hours of each UTC day have a nearly-degenerate VWAP (few bars in the anchor) that sits on top of price — the "above VWAP" filter is close to a coin-flip there and cross signals cluster right after the reset. Any slot would need either a minimum-bars-into-session guard or an explicit decision that UTC-midnight anchoring (vs. a liquidity-session anchor) is the intended "session." That's also a hidden degree of freedom that could be tuned into fake edge.

## Bottom line

SCREENING-GRADE across 9,190 signals: both variants lose ~0.26–0.27% net per bracket trade at a 37.5% WR vs 47.1% breakeven, negative in every split, and gross returns are flat. **Do not build this slot; do not tune the 9 knobs to make it green — that's the artifact machine.**
