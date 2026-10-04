# forced_flows lens notes — run 2026-10-04-0645 (EXPLORATORY; not evidence)

Outcome: ZERO theses registered. No train-data probes were run this session; no load_data calls were made.

## Web fetch log (every URL with status)
WebSearch calls: 12 (none refused; budget not exhausted).
WebFetch attempts:
1. https://arxiv.org/pdf/2607.09426 — fetched (PDF binary). Text extracted locally with pypdf to `kim_hansen_2607.09426.txt` (76 pages).
2. https://www.sciencedirect.com/science/article/pii/S1544612322001179 — HTTP 403, not read, not cited.
3. https://ideas.repec.org/a/eee/beexfi/v41y2024ics221463502400008x.html — OK (Han 2024 JBEF, price clustering abstract; no crossing/return result).
4. https://arxiv.org/abs/2607.09426 — OK (abstract).

## Candidates considered and why each was dropped
- Quarter-hour opening order imbalance -> 4-12h returns (Kim & Hansen, arXiv 2607.09426, Binance BTC/ETH/XRP/SOL/DOGE/ADA perps, 2021-01-01 to 2024-10-31). Text (kim_hansen_2607.09426.txt lines 960-970): the public-signal component grows from <1 bp at 4h to 9.8 and 16.9 bp at 8h and 12h. Dropped: (a) the signal needs trade-level signed order imbalance in the first 10 seconds of each quarter-hour, which neither mr_edge nor long_1h carries (OHLCV only, no buy/sell split); (b) the reported magnitudes are far below c = 11.5 bps plus a 100-300 bps target band (fee-trapped); (c) periodic execution algos are scheduled, not forced, flow.
- Round-number stop clustering continuation: already probed NULL by this lens in run 2026-09-27-0300 (exploratory/forced_flows/probe_round_cross*.out.txt); Han 2024 reports clustering, not a crossing return.
- Prior-extreme breakout/stop-run continuation: 2026-09-27-0300 probe_sweep_reclaim.out.txt breakout_hold means are tens of bps at 3-6h (fee-trapped); adjacent to DEAD rows 77, 110, 114.
- Leveraged-ETF (BITX/ETHU) 3-4 PM ET rebalancing continuation: same NY window and same continuation bet as DEAD row 113 (BRRNY window continuation); 1h-scale move cannot reach 100+ bps targets.
- Liquidation cascades / heatmap magnets / ADL / daily relever: DEAD rows 6, 108, 109, 110, 114; heatmap sources were practitioner marketing pages with no numbers; liquidation data not in the caches (arXiv 2607.27070 notes Binance discontinued liquidationSnapshot dumps).
- Funding-settlement flows: DEAD rows 4, 7, 82, 83 and owner ban on the funding/XS/OI hunt (STANDARDS #14).
- Listings / airdrop sell pressure (Arrakis 2025 via search snippet only, not opened), perp delistings (Binance announcements), CoinDesk index rebalances (WisdomTree Jan 2026, quarterly), token unlocks (DEAD row 19): event calendars are not in either dataset and event counts within the train windows are far below n=30 / 26-week time-to-verdict.
