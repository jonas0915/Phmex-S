# Phemex USDT-perp account economics probe (READ-ONLY)

Probe run 9/14/2026 8:10 PM PT (`ts_utc` 2026-09-15T03:10:45Z), ccxt 4.4.100, markets loaded: 2062. Exchange built exactly as `exchange.py:14-20` (`ccxt.phemex`, `defaultType=swap`, keys from `.env` via `config.py:10-11`). Scripts: `probe_econ.py`, `probe2.py`, `probe3.py`; raw responses: `probe_out.json`, `probe2_out.json`, `probe3_out.json` (same folder). No orders, leverage or margin changes were made; the bot was not started.

## 1. Balance, positions, open orders

- `fetch_balance()` USDT: total **87.120628536367**, free **87.120628536367**, used **0.0** (raw `accountBalanceRv` = 87.120628536367, `totalUsedBalanceRv` = 0, `bonusBalanceRv` = 0, accountId 40347030003).
- `fetch_positions()` returned 36 rows, **0 with non-zero contracts** (no open positions).
- `fetch_open_orders()` without a symbol raises `ArgumentsRequired` on Phemex; called per symbol for the 10 symbols: {'BTC/USDT:USDT': 0, 'ETH/USDT:USDT': 0, 'SOL/USDT:USDT': 0, 'XRP/USDT:USDT': 0, 'DOGE/USDT:USDT': 0, '1000PEPE/USDT:USDT': 0, '1000SHIB/USDT:USDT': 0, 'SUI/USDT:USDT': 0, 'LINK/USDT:USDT': 0, 'ADA/USDT:USDT': 0} → **0 open orders**.
- Per-symbol margin settings as reported by `fetch_positions()` (`info.leverageRr`): all 10 symbols are **isolated, leverage ['10']** (matches `.env:9 LEVERAGE=10`). Positive `leverageRr` = isolated per `exchange.py:1116`.

## 2. Fee schedule: exchange vs bot config

Endpoints tried: `fetch_trading_fees()` and `fetch_trading_fee('BTC/USDT:USDT')` both raise `NotSupported` in ccxt 4.4.100 for Phemex (`ex.has.fetchTradingFee/fetchTradingFees` = false). `market['maker']`/`market['taker']` are **None** for every symbol (Phemex g-futures product info has no fee field; keys checked in `probe3_out.json:btc_market_info_keys`). ccxt's static `ex.fees['trading']` says 0.001/0.001 — that is ccxt's placeholder, not this account's rate; do not use it.

Ground truth used instead: the private read endpoint `GET /api-data/g-futures/trading-fees?symbol=…` (daily fee ledger per symbol, `probe3_out.json:fees_*`). Recent rows:

| Symbol | Day (UTC) | takerValueRv | takerFeeRateRr | makerValueRv | makerFeeRateRr | exchangeFeeRv | taker×0.0006 + maker×0.0001 | match |
|---|---|---|---|---|---|---|---|---|
| ETHUSDT | 2026-09-08 | 149.1822 | 0.0006 | 149.376 | 0 | 0.10444692 | 0.10444692 | yes |
| ETHUSDT | 2026-09-06 | 147.1476 | 0.0006 | 0.0 | 0 | 0.08828856 | 0.08828856 | yes |
| ETHUSDT | 2026-09-05 | 0.0 | 0 | 147.0822 | 0.0001 | 0.01470822 | 0.01470822 | yes |
| SOLUSDT | 2026-08-24 | 150.96 | 0.0006 | 149.152 | 0 | 0.1054912 | 0.10549120 | yes |
| SOLUSDT | 2026-08-21 | 152.8462 | 0.0006 | 151.0518 | 0 | 0.1068129 | 0.10681290 | yes |
| SOLUSDT | 2026-07-30 | 50.2748 | 0.0006 | 49.6468 | 0 | 0.03512956 | 0.03512956 | yes |
| u1000PEPEUSDT | 2026-08-30 | 0.0 | 0 | 147.8081069 | 0.0001 | 0.01478081 | 0.01478081 | yes |
| u1000PEPEUSDT | 2026-08-29 | 0.0 | 0 | 150.2098718 | 0.0001 | 0.01502099 | 0.01502099 | yes |
| u1000PEPEUSDT | 2026-08-28 | 149.261202 | 0.0006 | 150.001515 | 0 | 0.10455687 | 0.10455687 | yes |
| BTCUSDT | 2026-09-01 | 78.4092 | 0.0006 | 77.9849 | 0 | 0.05484401 | 0.05484401 | yes |
| BTCUSDT | 2026-07-24 | 130.352 | 0.0006 | 129.3964 | 0 | 0.09115084 | 0.09115084 | yes |
| BTCUSDT | 2026-07-22 | 131.4398 | 0.0006 | 130.858 | 0 | 0.09194968 | 0.09194968 | yes |
| DOGEUSDT | 2026-08-27 | 148.49854 | 0.0006 | 0.0 | 0 | 0.08909912 | 0.08909912 | yes |
| DOGEUSDT | 2026-08-26 | 0.0 | 0 | 149.92135 | 0.0001 | 0.01499214 | 0.01499214 | yes |
| DOGEUSDT | 2026-08-13 | 149.29476 | 0.0006 | 149.89709 | 0 | 0.10456657 | 0.10456657 | yes |

**Account fee rates (verified from 15 ledger rows above, every row reconciles to the cent): maker 0.01% (0.0001), taker 0.06% (0.0006)** — Phemex VIP-0 base tier. Quirk: on days with both maker and taker volume the ledger prints `makerFeeRateRr: "0"`, yet `exchangeFeeRv` only reconciles if maker volume is charged 0.0001, so the printed 0 is a display artifact, not a zero-maker-fee day. Any script that reads `makerFeeRateRr` literally would under-count.

Bot assumptions (file:line):

| Constant | Value | Source | vs exchange |
|---|---|---|---|
| TAKER_FEE_PERCENT | 0.06 | `.env:52`, default `config.py:144` | matches 0.06% |
| MAKER_FEE_PERCENT | 0.01 | `config.py:151` default (not set in `.env`) | matches 0.01% |
| SLIPPAGE_PERCENT | 0.05 | `.env:60`, `config.py:145` | model input, not a fee |
| `_estimate_live_fees` | notional × (0.01+0.06)/100 = 0.07% | `risk_manager.py:792` | = maker-in / taker-out round trip; correct |
| Paper round-trip fee | (0.01+0.06+0.05)/100 = 0.12% of notional | `risk_manager.py:817-819` | fee part matches; +0.05% slippage is a modelling choice |
| BE-stop buffer comment | 0.25% "covers 0.06%×2 + 0.05%×2 = 0.22%" | `risk_manager.py:296` | assumes taker-taker; real maker-in/taker-out is 0.07%, so buffer is ~3.5x conservative (comment stale, harmless) |
| LEVERAGE | 10 | `.env:9` | exchange shows 10x isolated on all 10 symbols |
| MIN/MAX_TRADE_MARGIN | 15.0 / 15.0 | `.env:64-65` | — |

No live mismatch: the account is charged exactly what `config.py` assumes. Stale doc note: `docs/overnight-2026-07-05/r2_fee_research.md:44-45` says there is no maker constant and paper charges 0.22% — superseded by `config.py:151` / `risk_manager.py:817` (0.12%).

## 3. Contract specs at current price

Source: `load_markets()` (`probe_out.json:market_specs`) and `fetch_ticker().last` (`probe_out.json:tickers`). Phemex g-futures publish `qtyStepSize` (the lot = the step; ccxt `limits.amount.min` is None), `minOrderValueRv` (min order value, USDT) and `maxLeverage`. Min position notional = smallest multiple of the step whose value ≥ `minOrderValueRv`.

| Symbol | id | last price | lot = qty step | min order value | max lev | min qty (steps) | min notional USD |
|---|---|---|---|---|---|---|---|
| BTC | BTCUSDT | 77740.0 | 0.001 | 1 USDT | 150x | 0.001 (1) | $77.7400 |
| ETH | ETHUSDT | 2497.38 | 0.01 | 1 USDT | 150x | 0.01 (1) | $24.9738 |
| SOL | SOLUSDT | 101.43 | 0.01 | 1 USDT | 50x | 0.01 (1) | $1.0143 |
| XRP | XRPUSDT | 1.4147 | 0.01 | 1 USDT | 50x | 0.71 (71) | $1.0044 |
| DOGE | DOGEUSDT | 0.08342 | 1 | 1 USDT | 50x | 12 (12) | $1.0010 |
| 1000PEPE | u1000PEPEUSDT | 0.0034533 | 1 | 1 USDT | 50x | 290 (290) | $1.0015 |
| 1000SHIB | u1000SHIBUSDT | 0.005196 | 1 | 1 USDT | 50x | 193 (193) | $1.0028 |
| SUI | SUIUSDT | 0.7184 | 1 | 1 USDT | 50x | 2 (2) | $1.4368 |
| LINK | LINKUSDT | 11.511 | 0.01 | 1 USDT | 50x | 0.09 (9) | $1.0360 |
| ADA | ADAUSDT | 0.2059 | 0.01 | 1 USDT | 50x | 4.86 (486) | $1.0007 |

BTC and ETH are the only symbols whose single lot exceeds $1 (BTC 0.001 × 77,740 = $77.74; ETH 0.01 × 2,497.38 = $24.97). Everything else bottoms out at the $1 `minOrderValueRv` floor. Also note `maxLeverage` is 150x for BTC/ETH and 50x for the other 8; the account is set to 10x isolated on all ten.

## 4. Tradability for an $87.12 account

Formula: notional N = margin × leverage; lots = floor(N / (step × price)); qty = lots × step; tradable iff lots ≥ 1 AND qty × price ≥ minOrderValueRv (1 USDT). Prices/steps from §3. Margin is what is locked; N is the exposure.

| Symbol | $5 1x | $5 3x | $5 5x | $10 1x | $10 3x | $10 5x | $15 1x | $15 3x | $15 5x | $20 1x | $20 3x | $20 5x |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | NO (0 lots, $0.00) | 1 lot ($77.74) |
| ETH | NO (0 lots, $0.00) | NO (0 lots, $0.00) | 1 lot ($24.97) | NO (0 lots, $0.00) | 1 lot ($24.97) | 2 lots ($49.95) | NO (0 lots, $0.00) | 1 lot ($24.97) | 3 lots ($74.92) | NO (0 lots, $0.00) | 2 lots ($49.95) | 4 lots ($99.90) |
| SOL | 4 lots ($4.06) | 14 lots ($14.20) | 24 lots ($24.34) | 9 lots ($9.13) | 29 lots ($29.41) | 49 lots ($49.70) | 14 lots ($14.20) | 44 lots ($44.63) | 73 lots ($74.04) | 19 lots ($19.27) | 59 lots ($59.84) | 98 lots ($99.40) |
| XRP | 353 lots ($4.99) | 1060 lots ($15.00) | 1767 lots ($25.00) | 706 lots ($9.99) | 2120 lots ($29.99) | 3534 lots ($50.00) | 1060 lots ($15.00) | 3180 lots ($44.99) | 5301 lots ($74.99) | 1413 lots ($19.99) | 4241 lots ($60.00) | 7068 lots ($99.99) |
| DOGE | 59 lots ($4.92) | 179 lots ($14.93) | 299 lots ($24.94) | 119 lots ($9.93) | 359 lots ($29.95) | 599 lots ($49.97) | 179 lots ($14.93) | 539 lots ($44.96) | 899 lots ($74.99) | 239 lots ($19.94) | 719 lots ($59.98) | 1198 lots ($99.94) |
| 1000PEPE | 1447 lots ($5.00) | 4343 lots ($15.00) | 7239 lots ($25.00) | 2895 lots ($10.00) | 8687 lots ($30.00) | 14478 lots ($50.00) | 4343 lots ($15.00) | 13031 lots ($45.00) | 21718 lots ($75.00) | 5791 lots ($20.00) | 17374 lots ($60.00) | 28957 lots ($100.00) |
| 1000SHIB | 962 lots ($5.00) | 2886 lots ($15.00) | 4811 lots ($25.00) | 1924 lots ($10.00) | 5773 lots ($30.00) | 9622 lots ($50.00) | 2886 lots ($15.00) | 8660 lots ($45.00) | 14434 lots ($75.00) | 3849 lots ($20.00) | 11547 lots ($60.00) | 19245 lots ($100.00) |
| SUI | 6 lots ($4.31) | 20 lots ($14.37) | 34 lots ($24.43) | 13 lots ($9.34) | 41 lots ($29.45) | 69 lots ($49.57) | 20 lots ($14.37) | 62 lots ($44.54) | 104 lots ($74.71) | 27 lots ($19.40) | 83 lots ($59.63) | 139 lots ($99.86) |
| LINK | 43 lots ($4.95) | 130 lots ($14.96) | 217 lots ($24.98) | 86 lots ($9.90) | 260 lots ($29.93) | 434 lots ($49.96) | 130 lots ($14.96) | 390 lots ($44.89) | 651 lots ($74.94) | 173 lots ($19.91) | 521 lots ($59.97) | 868 lots ($99.92) |
| ADA | 2428 lots ($5.00) | 7285 lots ($15.00) | 12141 lots ($25.00) | 4856 lots ($10.00) | 14570 lots ($30.00) | 24283 lots ($50.00) | 7285 lots ($15.00) | 21855 lots ($45.00) | 36425 lots ($75.00) | 9713 lots ($20.00) | 29140 lots ($60.00) | 48567 lots ($100.00) |

Reading: BTC needs N ≥ $77.74 → only $20×5x = $100 works (1 lot, $77.74 exposure, using $15.55 of margin at 5x). At the bot's actual 10x, $15 margin = $150 N → 1 BTC lot ($77.74). ETH needs N ≥ $24.97 → fails at $5×1x/$5×3x/$10×1x/$15×1x/$20×1x, works everywhere else. The other eight symbols clear the $1 floor at every combination, with lot counts shown. Granularity matters too: at $15×1x SOL gets 14 lots ($14.20), LINK 130 lots ($14.96), SUI 20 lots ($14.37).

## 5. Fee round-trip cost

Rates: maker 0.0001, taker 0.0006 (§2). Formula: round-trip fee = N × (rate_in + rate_out), N = margin × leverage. Break-even price move = (rate_in + rate_out) × 100 in % of price — independent of leverage, because both fee and PnL scale with N. In margin-ROI terms it is that × leverage.

| Combo | % of notional | $15 @1x (N=$15) | $15 @3x (N=$45) | $15 @5x (N=$75) | price move to cover | margin-ROI to cover @1x/3x/5x |
|---|---|---|---|---|---|---|
| maker-maker | 0.02% | $0.0030 | $0.0090 | $0.0150 | 0.02% | 0.02% / 0.06% / 0.10% |
| maker-taker | 0.07% | $0.0105 | $0.0315 | $0.0525 | 0.07% | 0.07% / 0.21% / 0.35% |
| taker-taker | 0.12% | $0.0180 | $0.0540 | $0.0900 | 0.12% | 0.12% / 0.36% / 0.60% |

The bot's real mix is maker-in/taker-out (entries PostOnly, exits mostly taker: `reference_phemex_fees_funding_api_2026-09-07.md`, confirmed by the ledger rows in §2), so 0.07% of N: $0.0105 / $0.0315 / $0.0525 at 1x/3x/5x, and $0.105 at the bot's 10x ($150 N). Compare the ETH 9/5→9/6 round trip in §2: 0.01470822 + 0.08828856 = $0.1030 on ~$147 N = 0.070%.

## 6. Funding rates

Source: `fetch_funding_rate(symbol).fundingRate` (`probe_out.json:funding_rates`, raw `fundingRateRr`). Interval: `market.info.fundingInterval` = ['28800'] s (= 8h) for all 10; BTC `fetch_funding_rate_history` timestamps are spaced exactly 8.0h (`probe3_out.json:fr_hist_BTC`). Annualized = rate × 3 × 365. Positive = longs pay shorts.

| Symbol | 8h rate | 8h % | annualized % | mark price | per $150 N per 8h |
|---|---|---|---|---|---|
| BTC | 0.0001 | 0.0100% | +10.95% | 77741.8 | $+0.0150 |
| ETH | -3.21e-05 | -0.0032% | -3.51% | 2500.16 | $-0.0048 |
| SOL | 7.89e-05 | 0.0079% | +8.64% | 101.46 | $+0.0118 |
| XRP | 0.0001 | 0.0100% | +10.95% | 1.4153 | $+0.0150 |
| DOGE | -4.282e-05 | -0.0043% | -4.69% | 0.08342 | $-0.0064 |
| 1000PEPE | -0.00033127 | -0.0331% | -36.27% | 0.0034546 | $-0.0497 |
| 1000SHIB | 1.796e-05 | 0.0018% | +1.97% | 0.005196 | $+0.0027 |
| SUI | 0.0001 | 0.0100% | +10.95% | 0.7184 | $+0.0150 |
| LINK | 0.0001 | 0.0100% | +10.95% | 11.511 | $+0.0150 |
| ADA | 0.0001 | 0.0100% | +10.95% | 0.2059 | $+0.0150 |

BTC's last six settlements (`fr_hist_BTC`): 0.000066, 0.000026, 0.000100, 0.000051, 0.000025, 0.000009 — the 0.0001 'default' rate is the cap-clamped normal, not a live signal. 1000PEPE is the outlier at −0.0331%/8h (shorts pay ≈ −36%/yr).

## 7. Top-of-book depth

Source: `fetch_order_book(symbol, 5)` (`probe_out.json:orderbook`, ts 1789441860984 ms). Spread bps = (ask − bid) / mid × 10,000. USD size = qty × price at that level.

| Symbol | best bid (qty) | best ask (qty) | spread | spread bps | bid USD | ask USD | $15 / $75 as % of thinner side |
|---|---|---|---|---|---|---|---|
| BTC | 77735.1 (0.669) | 77735.2 (0.911) | 0.1 | 0.01 | $52,005 | $70,817 | 0.0% / 0.1% |
| ETH | 2499.49 (5.43) | 2499.63 (32.46) | 0.14 | 0.56 | $13,572 | $81,138 | 0.1% / 0.6% |
| SOL | 101.43 (1.4) | 101.44 (21.3) | 0.01 | 0.99 | $142 | $2,161 | 10.6% / 52.8% |
| DOGE | 0.0834 (7177.0) | 0.08341 (7193.0) | 1e-05 | 1.20 | $599 | $600 | 2.5% / 12.5% |

Other six (from `probe2_out.json:tob_rest`, one snapshot):

| Symbol | best bid (qty) | best ask (qty) | spread bps | bid USD | ask USD |
|---|---|---|---|---|---|
| XRP | 1.4136 (1.24) | 1.4145 (3290.76) | 6.36 | $2 | $4,655 |
| 1000PEPE | 0.00345 (131775.0) | 0.0034523 (206457.0) | 6.66 | $455 | $713 |
| 1000SHIB | 0.005188 (29810.0) | 0.005191 (31773.0) | 5.78 | $155 | $165 |
| SUI | 0.7173 (3047.0) | 0.7179 (1713.0) | 8.36 | $2,186 | $1,230 |
| LINK | 11.494 (253.11) | 11.495 (602.29) | 0.87 | $2,909 | $6,923 |
| ADA | 0.2055 (32487.09) | 0.2056 (168341.09) | 4.86 | $6,676 | $34,611 |

A $15–$75 order is negligible against BTC ($52K/$71K at touch) and ETH ($13.6K/$81K). SOL's best bid was only $142 in this snapshot (ask $2,161; the next bid level 101.39 holds 720.72 SOL ≈ $73K), and DOGE ~$600 per side at touch, so a $75 taker order is 12.5–53% of the touch on SOL/DOGE — still fills within one tick given the next levels, but it is not 'invisible' the way it is on BTC/ETH. Spreads: BTC 0.01 bps (one 0.1 tick), ETH 0.56 bps, SOL 0.99 bps, DOGE 1.20 bps; XRP 6.4 bps and 1000PEPE 6.7 bps are the widest of the ten (one snapshot each).

## Endpoint failures (all handled)

- `fetch_trading_fees` / `fetch_trading_fee`: `NotSupported` in ccxt → replaced by private `GET /api-data/g-futures/trading-fees` (needs `symbol`; without it Phemex returns code 412).
- `fetch_funding_rates` (plural): `NotSupported` → per-symbol `fetch_funding_rate`.
- `fetch_open_orders()` without symbol: `ArgumentsRequired` → per-symbol.
- `publicGetCfgFundingRates`: Phemex code 39999 'Please try again' → not needed (interval taken from market info + history spacing).
- `fetch_ticker` returned `bid`/`ask` = None on Phemex swaps → order book used for bid/ask.
