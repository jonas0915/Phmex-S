# Trend-Day Fuse Replay — 5m_mean_revert (8/1/2026)

**Question:** Would a "trend-day fuse" have saved 5m_mean_revert money historically?
**Frozen rule (primary, pre-stated, no tuning):** after **2** full-stop losses (exit_reason in {stop_loss, exchange_close} with negative net) on the SAME side within the same PT day, stand down on that side until next PT midnight. 1-stop and 3-stop variants reported as sensitivity only.

**Verdict: NO SIGNAL — the primary 2-stop fuse would have prevented zero trades and changed PnL by $0.00 in both eras. Does not support a forward test.**

## Data

- Source: `/Users/jonaspenaso/Desktop/Phmex-S/trading_state_5m_mean_revert.json` (read-only), 39 closed trades.
- Live era (`mode: "live"`, closes 6/18–7/31): 19 trades, total net **+$15.40**.
- Pre-promotion era (no mode field, closes 3/28–6/11): 20 trades, total net **+$2.50** — exactly 10W/10L +$2.50, independently matching the 7/28 forensics receipt, so the ledger read cross-verifies.
- Replay: `scripts/research/mr-trend-fuse-2026-08-01/fuse_replay.py`; full output in `replay_output.txt` (same dir). Event-driven walk: stops counted at close time, entries blocked at open time; prevented trades removed from stop-counting on a second pass (fixpoint).

## Results (sum of prevented trades' actual net; negative = fuse saves)

| Variant | Live era trips / prevented / Δ | Pre-promotion trips / prevented / Δ | Full ledger Δ |
|---|---|---|---|
| **2-stop (PRIMARY)** | 0 / 0 / **$0.00** | 1 / 0 / **$0.00** | **$0.00** |
| 1-stop (sensitivity) | 4 / 0 / $0.00 | 3 / 1 / **−$1.45** (saves) | −$1.45 |
| 3-stop (sensitivity) | 0 / 0 / $0.00 | 0 / 0 / $0.00 | $0.00 |

## Why the fuse never bites — the actual sequences

All 8 full-stop losses in the 39-trade ledger, with the day's other trades:

- **5/19 (pre):** ZEC long stop −$1.49 (closed 3:44 AM PT). Only other trade that day: XLM **short** TP +$1.41. No same-side follow-up.
- **5/23 (pre):** WLD long stop −$3.10. Only trade that day.
- **6/11 (pre) — the ONLY day with 2 same-side stops ever:** LTC long stop −$1.61 (closed 8:45 AM PT), then AVAX long entered 6:32 PM, stopped −$1.45 (closed 11:37 PM PT). The 2-stop fuse trips at 11:37 PM — **23 minutes before it expires at midnight**, with no further entries. It cannot prevent the AVAX trade because that trade IS the second stop. Only the 1-stop variant blocks it (entry came after the first stop) — that single trade is the entire −$1.45 "saving," pre-promotion era, n=1.
- **6/24 (live):** XLM short exchange_close −$1.47. Only trade that day.
- **7/16 (live):** SOL long exchange_close −$1.81 (closed 1:10 AM PT). The day's later trades were both **shorts** (+$0.17, +$2.38) — a fuse on longs blocks nothing; a side-agnostic fuse would have *cost* +$2.55.
- **7/17 (live):** INJ long exchange_close −$1.86 (closed 10:00 PM PT). No later entries that day.
- **7/22 (live):** XRP short exchange_close −$1.93. Only trade that day.

## Trend-day check (daily OHLCV via ccxt, cached in `daily_ohlcv_cache.json`)

Stop days are **not** identifiably large trend days (UTC daily candles; PT/UTC day offset noted as an approximation):

- 6/11 (the lone 2-stop day): LTC +1.80% (range 2.9%), AVAX +4.19% — moderate; AVAX's stop actually resolved into the 6/12 UTC day (−1.19%). Not a runaway trend.
- 7/22 XRP short stop: day −0.16%, range 2.5% — a quiet day.
- 7/16 SOL long stop: −2.59% — modest downday, and the slot then made +$2.55 on shorts the same day.
- 7/17 INJ: the +5.95% candle is the UTC day *before* the stop resolved; the stop's own UTC day was +0.45%.
- 5/23 WLD (+10.6%) is the only stop coinciding with a genuinely large move — pre-promotion, single stop, no follow-up entry to prevent.

No coherent "stops cluster on trend days" pattern.

## Reconciliation with the 7/5 anti-clustering prior

The 7/5 streak analysis (streaks = payoff asymmetry + chance, NOT dependence; big losses ANTI-cluster) predicted this outcome, and the replay confirms it: in 39 trades, same-side full stops landed on the same PT day exactly **once**, and even then hours apart with no third entry. The slot averages ~1 trade every 2–3 days — intra-day loss clustering barely has the trade density to exist, let alone be exploitable. The result and the prior agree; no discrepancy to investigate.

## Caveats (honest)

- **n is tiny:** 8 full stops total, 4 per era. Zero preventions is the expected outcome under the prior at this density; it is also weak evidence in absolute terms — but the burden is on the fuse to show savings, and it shows none.
- **No counterfactual bias:** this is a pure subtraction replay — prevented trades actually happened, so their PnL is known, not modeled. (Cuts both ways: we cannot know what the slot would have entered *instead*.)
- Three earliest trades (3/28–4/1) lack `net_pnl`/fee fields; gross `pnl_usdt` used. None are stops or candidates for prevention, so the fuse math is unaffected — only the pre-era total carries this fee approximation on those 3 rows.
- One `min_margin_skip` close (7/26, −$0.11) is in the totals but is not a full stop under the frozen definition.
- The 1-stop variant's −$1.45 "saving" is one pre-promotion trade. It would also have imposed 4 stand-down windows in the live era that happened to block nothing this time — with this WR (live era +$15.40 on 19 trades, stops are the minority) a 1-stop fuse mostly risks blocking recoveries. Not supported either.

## Bottom line

**Fuse would have done nothing / no signal.** The 2-stop trend-day fuse prevents zero trades across the entire ledger (live and paper). Do not build; do not pre-register a forward test. Re-visit only if trade frequency rises enough (multiple trades/day) for intra-day sequencing rules to have a sample to act on.

Artifacts: `scripts/research/mr-trend-fuse-2026-08-01/` (`fuse_replay.py`, `replay_output.txt`, `fetch_trend_context.py`, `daily_ohlcv_cache.json`, `trend_context_output.txt`).
