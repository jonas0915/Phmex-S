# 5m_mean_revert — real closed trades vs forming-bar regeneration

**SCREENING GRADE — n≈30-45 real trades; companion read reported alongside the replay, never a verdict on its own (prereg amendment v2, Change 3)**

Generated 2026-09-04T09:15:11.410579+00:00 | join: same symbol+side, |opened_at − snapshot ts| ≤ 120 s | regen match: same 5m bar ±1, same side | bootstrap 2000 reps, seed 0

Closed trades 51 | with snapshot 45 | without 6 | mode=live 31 (regen-matched 27, unmatched 1, unchecked/out-of-universe 3) | non-live 20

## Cohorts on REAL money (mode=live, regen-matched)

| cohort | n | net $ | WR | mean $/trade | 95% CI (one-sample bootstrap) |
|---|---|---|---|---|---|
| confirmed_at_close = True | 20 | +7.38 | 55% | +0.369 | [-0.418, +1.215] |
| confirmed_at_close = False (forming-only) | 7 | -4.72 | 29% | -0.674 | [-2.167, +0.921] |
| live, snapshot but NO regen match | 1 | +2.38 | 100% | +2.380 | [+2.380, +2.380] |

Diff CI (confirmed − forming-only, independent resample): [-0.709, +2.741]

## Per-trade

| opened (UTC) | symbol | side | mode | net $ | exit | snap dt s | snap min | regen match | fire_minute | confirmed_at_close |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-03-28T19:19:01+00:00 | SOL/USDT:USDT | long | None | — | adverse_exit | — | — | — | — | — |
| 2026-03-30T10:48:43+00:00 | SOL/USDT:USDT | long | None | — | hard_time_exit | — | — | — | — | — |
| 2026-04-01T21:29:58+00:00 | BTC/USDT:USDT | short | None | — | take_profit | — | — | — | — | — |
| 2026-04-08T21:33:21+00:00 | SUI/USDT:USDT | short | None | +2.00 | take_profit | 0.2 | 3 | n | — | — |
| 2026-04-17T06:54:39+00:00 | XLM/USDT:USDT | short | None | -0.55 | adverse_exit | 0.4 | 4 | n | — | — |
| 2026-04-17T10:44:26+00:00 | TAO/USDT:USDT | long | None | +1.44 | take_profit | 0.8 | 4 | n | — | — |
| 2026-04-21T12:20:05+00:00 | XRP/USDT:USDT | long | None | -0.62 | adverse_exit | 0.1 | 0 | n | — | — |
| 2026-04-22T07:30:56+00:00 | ADA/USDT:USDT | long | None | +0.06 | hard_time_exit | 0.6 | 0 | n | — | — |
| 2026-04-26T04:53:53+00:00 | AAVE/USDT:USDT | short | None | -0.65 | adverse_exit | 0.5 | 3 | n | — | — |
| 2026-05-12T20:04:22+00:00 | TAO/USDT:USDT | short | None | +0.74 | take_profit | 1.9 | 4 | n | — | — |
| 2026-05-13T18:29:36+00:00 | ARB/USDT:USDT | short | None | +2.92 | take_profit | 0.3 | 4 | n | — | — |
| 2026-05-19T07:36:20+00:00 | ZEC/USDT:USDT | long | None | -1.49 | stop_loss | 0.5 | 1 | n | — | — |
| 2026-05-19T16:59:48+00:00 | XLM/USDT:USDT | short | None | +1.41 | take_profit | 0.0 | 4 | n | — | — |
| 2026-05-20T13:44:23+00:00 | ONDO/USDT:USDT | long | None | +1.51 | take_profit | 0.7 | 4 | n | — | — |
| 2026-05-22T18:08:52+00:00 | WLD/USDT:USDT | long | None | -3.10 | stop_loss | 0.4 | 3 | n | — | — |
| 2026-05-27T01:04:52+00:00 | AVAX/USDT:USDT | short | None | -0.42 | hard_time_exit | 0.4 | 4 | n | — | — |
| 2026-05-27T09:08:34+00:00 | ADA/USDT:USDT | long | None | -0.01 | hard_time_exit | 0.5 | 3 | n | — | — |
| 2026-05-28T10:04:27+00:00 | RENDER/USDT:USDT | short | None | +1.52 | take_profit | 0.0 | 4 | n | — | — |
| 2026-06-11T06:11:16+00:00 | LTC/USDT:USDT | long | None | -1.61 | stop_loss | 0.5 | 1 | n | — | — |
| 2026-06-12T01:32:40+00:00 | AVAX/USDT:USDT | long | None | -1.45 | stop_loss | 0.5 | 2 | y | 5 | True |
| 2026-06-19T02:34:58+00:00 | WLD/USDT:USDT | long | live | +1.59 | exchange_close | 0.8 | 4 | y | 4 | True |
| 2026-06-24T20:26:21+00:00 | XLM/USDT:USDT | short | live | -1.47 | exchange_close | 0.8 | 1 | y | 5 | True |
| 2026-07-07T12:21:52+00:00 | XRP/USDT:USDT | short | live | +2.34 | exchange_close | 1.1 | 1 | y | 5 | True |
| 2026-07-08T11:49:43+00:00 | SOL/USDT:USDT | short | live | +2.34 | exchange_close | 1.0 | 4 | y | 5 | True |
| 2026-07-10T06:50:41+00:00 | XLM/USDT:USDT | long | live | +2.42 | exchange_close | 0.5 | 0 | y | 4 | True |
| 2026-07-15T00:23:50+00:00 | XLM/USDT:USDT | long | live | -0.87 | hard_time_exit | 1.0 | 3 | y | 2 | True |
| 2026-07-16T07:28:44+00:00 | SOL/USDT:USDT | long | live | -1.81 | exchange_close | 1.1 | 3 | y | 3 | False |
| 2026-07-16T13:35:49+00:00 | 1000PEPE/USDT:USDT | short | live | +0.17 | hard_time_exit | 0.5 | 0 | y | 5 | True |
| 2026-07-16T21:15:56+00:00 | TAO/USDT:USDT | short | live | +2.38 | exchange_close | 0.9 | 0 | n | — | — |
| 2026-07-17T09:05:50+00:00 | TAO/USDT:USDT | short | live | +0.38 | hard_time_exit | 0.3 | 0 | y | 4 | True |
| 2026-07-18T04:30:09+00:00 | INJ/USDT:USDT | long | live | -1.86 | exchange_close | 1.5 | 0 | y | 4 | False |
| 2026-07-20T04:21:45+00:00 | SOL/USDT:USDT | long | live | -0.53 | hard_time_exit | 1.0 | 1 | y | 5 | True |
| 2026-07-22T10:31:01+00:00 | XRP/USDT:USDT | short | live | -1.93 | exchange_close | 1.4 | 1 | y | 5 | True |
| 2026-07-23T20:22:20+00:00 | TAO/USDT:USDT | short | live | +2.38 | exchange_close | 1.3 | 2 | y | 2 | False |
| 2026-07-24T06:15:08+00:00 | XRP/USDT:USDT | short | live | +2.41 | exchange_close | 0.4 | 0 | y | 3 | True |
| 2026-07-26T20:41:02+00:00 | XRP/USDT:USDT | long | live | -0.10 | min_margin_skip | — | — | — | — | — |
| 2026-07-27T16:45:54+00:00 | ETH/USDT:USDT | short | live | +2.13 | exchange_close | 0.8 | 0 | y | 5 | True |
| 2026-07-29T09:24:51+00:00 | LTC/USDT:USDT | short | live | +1.06 | hard_time_exit | 0.3 | 4 | y | 3 | True |
| 2026-07-31T13:25:13+00:00 | ETH/USDT:USDT | short | live | +4.38 | exchange_close | 1.1 | 0 | y | 4 | True |
| 2026-08-03T20:03:28+00:00 | XRP/USDT:USDT | long | live | -0.21 | min_margin_skip | — | — | — | — | — |
| 2026-08-09T13:30:20+00:00 | ADA/USDT:USDT | short | live | -1.42 | hard_time_exit | 0.9 | 0 | y | 3 | False |
| 2026-08-13T00:19:20+00:00 | ADA/USDT:USDT | short | live | -0.84 | durable_sl | 0.9 | 4 | y | 3 | False |
| 2026-08-18T11:11:40+00:00 | PUMP/USDT:USDT | short | live | -3.57 | exchange_close | 1.0 | 1 | y | 4 | False |
| 2026-08-20T05:03:41+00:00 | SOL/USDT:USDT | short | live | -0.10 | min_margin_skip | — | — | — | — | — |
| 2026-08-20T05:06:32+00:00 | SOL/USDT:USDT | short | live | -1.89 | exchange_close | 1.0 | 1 | y | 3 | True |
| 2026-08-23T08:52:19+00:00 | SOL/USDT:USDT | short | live | -1.90 | exchange_close | 1.6 | 2 | y | 5 | True |
| 2026-08-24T13:41:20+00:00 | 1000SHIB/USDT:USDT | long | live | -1.91 | exchange_close | 1.2 | 1 | y | 5 | True |
| 2026-08-28T11:14:25+00:00 | HYPE/USDT:USDT | short | live | -1.11 | exchange_close | 0.8 | 4 | y | 2 | True |
| 2026-08-28T22:55:52+00:00 | 1000PEPE/USDT:USDT | short | live | +2.39 | exchange_close | 1.2 | 0 | y | 4 | False |
| 2026-08-31T05:32:59+00:00 | BTC/USDT:USDT | short | live | -0.48 | hard_time_exit | 0.6 | 3 | y | 4 | True |
| 2026-09-01T23:46:41+00:00 | ETH/USDT:USDT | short | live | +0.26 | durable_sl | 1.1 | 1 | y | 5 | True |

Notes: `regen match = —` means the trade has no snapshot, or its symbol is outside the regenerated universe/window. Cohorts use ONLY mode=live trades with a regen match. Screening grade; not a verdict.
