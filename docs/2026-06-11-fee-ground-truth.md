# Fee Ground Truth — 2026-06-11

What we actually pay Phemex, measured from the exchange's own fill records, and what it means for the maker-fee hypothesis left open at the 05-30 sprint close.

**Artifacts:** `scripts/research/fee-truth-2026-06-11/` — `fee_truth.py` (fetch, read-only), `raw_fills.json` (cache), `analyze_fees.py` (this analysis), `summary.json`.

## Methodology and window — stated honestly

- Source: ccxt `fetch_my_trades` per symbol (37 symbols from closed_trades), read-only, cached to `raw_fills.json`.
- **Window: 37.07 days — 2026-05-03 7:17 AM PT to 2026-06-09 9:01 AM PT, 200 fill records.** The fetch requested history from 2026-03-12 (earliest closed trade minus 1 day) but Phemex returned nothing before 05-03. Per-symbol counts max out at 37 fills (page limit 200), so pagination was not truncating — **the API itself capped history depth at ~37 days.** The ~370 closed trades before 05-03 have no exchange fills available; all numbers below are for this window only.
- ccxt's `takerOrMaker` flag is null on every Phemex fill (this is why the first pass produced empty maker/taker buckets). **Classification instead uses the exchange's own per-fill fee rate** (`fee.rate` / raw `feeRateRr`, present on 200/200 fills): rate ≤ 0.02% → maker, ≥ 0.05% → taker, in-between flagged. After removing funding records (below), the observed rates are exactly two values — 0.0001 (0.01%, maker tier) and 0.0006 (0.06%, taker tier) — so nothing was flagged and the inference is effectively exact. It is fully corroborated by two independent raw fields: `execStatus` (6 = maker fill, 7 = taker fill — agrees on 187/187 trading fills) and `ordType` (limit/limit-if-touched orders → maker, market/stop orders → taker).
- Entry/exit roles: fill matched to a closed_trade on symbol + timestamp within 60s of `opened_at`/`closed_at` (same rule as `scripts/reconcile_phemex.py`).

## 13 of the 200 records are funding settlements, not trades

All 13 `ordType=0 / execStatus=0` records land at exactly 00:00/08:00/16:00 UTC (Phemex funding times) with rates like −0.0001 to +0.00008 — funding rates, not fee tiers. Net across the window the account **received** $0.022 of funding (paid $0.0175, received $0.0394). These were the source of the "weird" 0.0244% unmatched bucket rate. They are excluded from all fee numbers below.

## Maker/taker split (187 trading fills)

| Bucket | Fills | Maker by count | Maker by notional | Fees | Eff. rate |
|---|---|---|---|---|---|
| **Entry** (matched) | 95 | **94/95 = 98.9%** | **98.5%** | $0.704 | 0.0107% |
| **Exit** (matched) | 77 | **6/77 = 7.8%** | **9.9%** | $2.948 | 0.0550% |
| Unmatched trading fills | 15 | 5/15 | ~33% | $0.510 | — |
| **All trading fills** | 187 | 105/187 = 56.1% | ~59% | $4.162 | 0.0319% |

- Entries are already almost pure maker — limit orders resting, one taker entry in 37 days.
- Exits are 92% taker by count, 90% by notional: market closes (`ordType=1`, 62 fills) and stop triggers (`ordType=3`, 18 fills). The 6 maker exits are limit TP fills.
- The 15 unmatched trading fills are mostly exits too (13 of 15 nearest a close); folding them in, exit maker share stays ~8–12%.
- **Per-trade round trip (65 trades with both legs matched): mean 0.0663%, median 0.0700%** of entry notional — i.e. maker in + taker out (0.01% + 0.06%), already ~half the canonical 0.12% all-taker assumption.
- Fee burn: $4.16 trading fees in 37 days → **~$41/yr annualized** at this trade rate (≈ 73% of the current ~$56 balance — material to the account, but see decision math: it is not why the strategy loses).

## Why 28 fills were "unmatched" at a weird 0.024% rate

Fully explained, nothing anomalous:

1. **13 funding settlements** (above) — near-zero/negative rates dragged the blend down.
2. **8 fills are real exits 61–95s after the recorded `closed_at` anchor** — just outside the 60s match window. The bot stamps `closed_at` when its 60s cycle notices the close, so the exchange fill can lag-mismatch by a cycle. Includes two partial-fill pairs (TON $16.99+$82.84 same timestamp; CFX $26.64+$73.01 same timestamp).
3. **7 fills are exchange-side closes filled 9–102 min away from the bot's recorded anchor** (APT −27 min, XRP −74 min, BIO −75 min, BTC −9 min, INJ +31 min partial pair, AIGENSYN −65s). These are SL/TP executed on the exchange long before the bot's poll recorded the close — same trades that show fee mismatches in the cross-check below.

The 0.0244% bucket rate is just the meaningless blend of ~0% funding records with a maker/taker mix.

## Cross-check vs trading_state.json `fees_usdt`

Matched by symbol + timestamp within ±5 min of `opened_at`/`closed_at`. Only 77 of 287 fee-bearing closed trades overlap the 37-day fill window.

| | Total |
|---|---|
| Bot-recorded `fees_usdt` (77 trades) | $3.4135 |
| Phemex fills (184 fills, same trades) | $3.9797 |
| **Delta** | **+$0.5662 (bot under-records by 16.6%)** |

32 trades differ by > $0.005. Two failure patterns:

- **`fees_usdt = 0` with `fees_pending`** on early_exit / trailing_stop / min_margin_skip trades — reconciliation never completed (e.g. ETH 05-23 6:56 AM PT-equivalent local=0, Phemex $0.057).
- **Maker/taker guessed wrong on `exchange_close` trades** — bot recorded $0.0100 (maker) when the real exit fill was $0.0706 taker (BCH 05-29, TON 05-23), and the inverse $0.0592 vs $0.0100 (APT 05-06, XRP 05-14). These are exactly the exchange-side closes from the unmatched bucket — the real exit fill was minutes away from the bot's `closed_at`, so reconcile matched the wrong fill.

Minor caveat: the ±5 min sweep can capture an adjacent funding record (≤$0.001 effect). The 16.6% gap stands either way: **the bot's internal fee ledger understates true fees.**

## Decision math at measured fees

Formula: `breakeven WR = (L + F) / (W + L)`, with F = round-trip fee rate × $100 notional ($10 margin × 10x).

**With the audit's last-50 figures (avg win +$0.485, avg loss −$0.660):**

| Scenario | RT rate | Fee/trade | Breakeven WR |
|---|---|---|---|
| (a) Measured live | 0.0663% | $0.066 | **63.43%** |
| (b) Canonical all-taker | 0.12% | $0.120 | 68.12% |
| (c1) Full maker | 0.02% | $0.020 | 59.39% |
| (c2) Full maker, upper | 0.04% | $0.040 | 61.14% |

Headroom: we already bank **4.69 WR pts** vs the canonical assumption (b→a); converting exits to maker buys at most **4.04 more** (a→c1), 2.3 pts at the 0.04% case.

**Discrepancy flag:** the audit's −$0.660 avg loss does not match the current last-50 window (05-18 → 06-09, from `trading_state.json`): net avg loss is **−$0.916** (avg win +$0.485 net matches). On the actual gross last-50 (W=$0.531, L=$0.922, 26W/17L/7 flat): BE = 68.0% measured, 71.7% canonical, **64.9% full-maker** — against an actual ~52% win rate. Under either set of numbers the strategy is far below breakeven, fees or no fees.

**Kelly f\* (last-50 net PnL, f\* = p − (1−p)/b):**

| Scenario | p | b | f* |
|---|---|---|---|
| As-is (measured fees) | 50.0% | 0.529 | **−0.445** |
| Exits → maker, 0.04% RT (+$0.026/trade) | 66.0% | 0.417 | −0.156 |
| Exits → maker, 0.02% RT (+$0.046/trade) | 68.0% | 0.409 | **−0.103** |

(Per-trade fee savings added back to each trade's net PnL, then p and b recomputed — several near-zero losers flip to tiny wins, which is why p jumps but b drops.)

**Does cheaper exit flip Kelly positive? No.** It improves f* substantially (−0.445 → −0.103) but stays negative.

## Bottom line on the maker-fee hypothesis

- **Measured, not assumed: real round-trip cost is ~0.066%** (median 0.070%) — entries are already 99% maker, exits 92% taker. The canonical 0.12% all-taker figure used in sprint math overstated fees ~2x.
- **The remaining fee lever is small: $0.046/trade max.** Going full-maker on exits moves breakeven WR by ~3–4 pts and leaves last-50 Kelly negative. (It would also add fill risk on exits — unfilled limit exits on a scalper are not free.)
- **Fees are not why the bot loses.** At actual last-50 numbers the gap to breakeven is ~13–16 WR pts (52% actual vs 65–68% required); fee optimization closes at most 3–4 of them. The loss asymmetry (avg loss $0.92 vs avg win $0.53 gross) is the dominant problem — consistent with the 05-30 finding that the exit model, not entry costs, is wrong.
- **Side findings to act on:** (1) bot's fee ledger under-records by ~17% — `fees_pending` zeros and wrong-fill matches on exchange closes in `scripts/reconcile_phemex.py`-style 60s matching; widening the reconcile window and matching by order linkage would fix it; (2) Phemex fill history is only retrievable ~37 days back — if we want a longer fee record, snapshot fills periodically.
