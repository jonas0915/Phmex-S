# owner-record lens — run 2026-10-04-0645 (EXPLORATORY, not evidence)

Probe: `probe.py` (command in its docstring) -> `owner_record_probe.json` (canonical) + copy at `../../theses/owner_record_probe.json` (task-mandated path; it is a probe, not a thesis). stdout: `probe.out.txt`.
Reads only research/swarm/kb/owner_trades/{api_closed_pnl,api_deposit_list_full,api_withdraw_list_full}.json. No market data, no holdout, no load_data call.

## Result: 0 theses
- Profitable subset = ONE symbol, ONE morning: u100TRYBUSD, 33 trades, 2022-11-10 4:47 AM to 8:44 AM UTC (8:47 PM to 12:44 AM PT, Nov 9-10), +$8,128.01 (owner_record_probe.json:tryb_detail). The price alternated between two levels (openEp range [43550, 85270]); the owner bought the low and sold the high repeatedly.
- Everything else (n=786) lost $-3,270.79, bootstrap mean CI95 fully negative (owner_record_probe.json:ex_tryb.mean_usd_ci95). No hold, side, or stress-window slice of ex-TRYB is positive (ex_tryb_by_hold, stress_event_windows).
- Owner withdrew ADA/XRP/MATIC during and right after the episode (owner_record_probe.json:equity_path.withdrawals_within_3d_of_peak).
- Mechanism sourced: FTX froze withdrawals 2022-11-09; trapped users bid FTX-listed tokens to large premiums to exit (fxstreet, JST up to 1,196%); index providers removed FTX, FTX US and FTX TR as pricing sources from 2022-11-10 3:10 AM UTC because of "significant divergence from market cohort" (Brave New Coin). A thin contract whose price references a venue with frozen withdrawals oscillates between the trapped-venue premium and the outside price; the counterparty is trapped-capital and liquidated takers. The owner's TRYB morning matches that shape.
- Why no thesis: (1) the same episode was already proposed as owner_record_delist_peg_dislocation_fade (run 2026-09-25-2036) and gate-recorded NOT SCREENABLE (gate_rejections.json there); restating it with a different counterparty label adds nothing screenable. (2) Neither mr_edge nor long_1h contains a venue-freeze / index-contamination event or a pegged asset; frequency of such events is a few per decade, so CONSTRAINTS viable item 3 (time-to-verdict <= 26 wk) cannot be met. (3) The only screenable generalization (fade wicks after market-maker withdrawal / crash reversion) is a relabel of DEAD_LIST rows 6, 104, 110, 114 (and 76).

## Fetch log (every URL attempted, with status)
Searches (5): "BiLira TRYB price spike November 10 2022 FTX collapse"; "market maker liquidity withdrawal crypto crash perpetual futures price dislocation paper 2024 2025"; "FTX users buy TRYB stablecoin to withdraw November 2022 premium"; "FTX collapse cross-exchange price premium arbitrage frozen withdrawals paper"; "Phemex index price constituent exchanges FTX removed November 2022".
Fetches:
1. https://www.coingecko.com/en/coins/bilira — OK. ATH $0.1927 (no date shown), current $0.02049; "stopped trading 11 days ago". The search snippet's "ATH $0.673 on 2022-11-10" was NOT confirmed on this page; not used.
2. https://www.fxstreet.com/cryptocurrencies/news/tron-based-tokens-sell-at-1200-premium-as-ftx-users-scramble-to-withdraw-202211110615 — OK. 2022-11-11: BTT 525% premium, JST up to 1,196%, TRX ~5x, bid up by FTX users to recoup locked funds.
3. https://blog.amberdata.io/the-liquidity-that-vanished-inside-octobers-40-depth-collapse — OK. 10bps depth fell 46% in 48h ($48M -> $26M), Oct 10-11 2025; $29M three months later. No price-reversion statistic.
4. https://bravenewcoin.com/insights/update-to-the-constituents-of-bnc-indices-ftx — OK. FTX, FTX US, FTX TR removed effective 2022-11-10 3:10 AM UTC (Nov 9 7:10 PM PT), 24h phase-out; reasons: no uninterrupted deposits/withdrawals, divergence from cohort.
5. https://blog.bitmex.com/site_announcement/bitmex-has-removed-ftx-from-the-bitmex-indices — 301 redirect.
6. https://www.bitmex.com/blog/site-announcement/bitmex-has-removed-ftx-from-the-bitmex-indices — 404. Not cited.
Readable: 4 of 6 attempts (1-4).
