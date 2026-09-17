# CONSTRAINTS — read before anything else

## Capital and sizing
- Design basis **$200**. Position sizing for screens: `fee_math.position_notional()` = $200 notional (10% margin at 10x). Two paper slots max at this size; no cross-sectional baskets.
- Lot minimums (USD notional per lot), verbatim from `fee_math.LOT_MIN_USD` — do not round: BTC **77.74**, ETH **24.9738**, SOL **1.0143**, XRP **1.0044**, DOGE **1.0010**. `minOrderValueRv` 1 USDT. Check with `fee_math.lot_check`.

## Costs (never re-derive by hand — use `fee_math`)
- Fees VIP-0: maker 0.01%, taker 0.06%. Bot's real mix = maker entry / taker exit = **7.0 bps** round trip (`fee_math.FEES_RT_BPS`).
- Measured adverse selection after fill: **4.5 bps** (`fee_math.ADVERSE_BPS`). Total `c = 11.5 bps` (`fee_math.C_BPS`).
- Required win rate for symmetric TP/SL `x`: `p* = (x + c) / 2x` (`fee_math.p_star`) → 25 bps **73.0%**, 50 bps **61.5%**, 100 bps **55.8%**, 300 bps **51.9%**, 1000 bps **50.6%**. Scalping is fee-trapped: sub-0.1% moves cannot pay.
- Funding every 8h; BTC ≈ +0.01%/8h; meme perps often negative. Any hold > 8h must account for it.

## Execution reality of the Phmex-S bot
- **5-min poller** — no sub-minute reaction. Entries are maker limit orders (real maker fill ≈ 27%, and misses are adversely selected); exits taker.
- Order book snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only. No streaming book.
- The Mac may sleep; slow horizons (hours-days) tolerate that, 5-min horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel; graded daily 6 AM PT by `scripts/lab_adjudicator/adjudicate.py`; kill via `touch .kill_<slot>`.

## What "viable" means for this desk
1. Train-era screen: n ≥ 30 and bootstrap CI95 of net bps excludes 0 (after `c`).
2. Observed WR ≥ p* for the spec's TP.
3. Time-to-verdict (n=50) ≤ 26 weeks at expected frequency.
4. Every symbol in the universe passes `lot_check` at $200 notional.
5. Signal is computable on closed bars from data the bot actually has.
