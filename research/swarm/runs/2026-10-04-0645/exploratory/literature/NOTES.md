# EXPLORATORY — literature seat (analyst #7), run 2026-10-04-0645. Not evidence.

Outcome: ZERO theses. No source opened this run gave a mechanism with a named, forced counterparty that (a) can be seen in OHLCV/funding data, (b) can pay 100-300 bps targets after c=11.5 bps, and (c) is not a relabel of a DEAD_LIST row.

## Sweep papers (docs/2026-09-16-edge-swarm-v1/sweep/), opened this run (head of each file read; matches the 2026-09-27 disposition)
- emoji_paper.txt (Zuo/Chen et al., "Emoji Driven Crypto Assets Market Reactions"). Mechanism: tweet emoji sentiment moves BTC. Counterparty: none named. NOT usable: the bot has no social feed; nearest dead row 18.
- garcia_schweitzer.txt (Garcia & Schweitzer, RSOS 2:150288, 2015). Mechanism: Twitter valence/polarization and exchange volume come before BTC moves. Counterparty: none. NOT usable: no social data; 2012-2014 era; row 18 family.
- hansen_periodicity.txt (Hansen/Kim/Kimbrough, arXiv 2109.12142v2). Mechanism: periodic patterns in volatility and liquidity by day, hour and within the hour. It is about magnitude, not return direction. Counterparty: none. NOT usable: rows 7/67.
- petukhina_hft.txt (Petukhina et al., "Rise of the Machines? Intraday High-Frequency Trading Patterns of Cryptocurrencies"). Mechanism: descriptive intraday volume/volatility patterns. Counterparty: none. NOT usable: descriptive only; rows 7/67.
- academic/ssrn_6932998.html. After tag strip it is a 372-character Elsevier "Content Blocked" (Cloudflare) page with no paper content. Mechanism: none. Counterparty: none. NOT usable.

## leadlag/local_check.py
- Copy: local_check_copy.py. The only change is the data source: the original read raw CSVs from backtest_data_june, bypassing load_data. The copy uses load_data.load_ohlcv(sym, "5m", era="train", dataset="mr_edge"). The original was not edited.
- Output: local_check_output.txt.
- Line 39: "pooled signed next-bar alt OC: mean 0.79 bps, se 0.17, n 66496, hit-rate 0.459". That is far below c=11.5 bps, and the lead-lag family is dead (row 106). No thesis uses this probe.
- No long_1h thesis is proposed, so the STANDARDS #6 cross-dataset rule is not triggered.

## Web fetch log (7 WebSearch, 3 WebFetch: 2 returned content, 1 returned 403)
Searches:
1. "perpetual futures return predictability 2025 forced selling net of costs". Hits: arXiv 2212.06888, 2506.08573 and 2607.09426. These cover funding design and the quarter-hour effect; funding is an owner-banned hunt (STANDARDS #14).
2. "bitcoin round number price barriers stop-loss clustering". The search snippet attributes "no significant pattern of returns after the round number" to https://eprints.soton.ac.uk/412873. Fetching that page returned HTTP 403, so the snippet is NOT cited as evidence. The round-number stop-run idea was dropped: its source is unverified, and it sits next to rows 114 (stop-sweep fade) and 110 (cascade continuation).
3. "bitcoin 10 AM dump US open". Fetched https://finance.yahoo.com/news/analyst-calls-jane-street-10am-211212186.html (OK): Alex Kruger reports IBIT cumulative return of "-1% during the 10 AM-10:15 AM window" and "0.9% in the 10 AM-10:30 AM window" since Jan 1 (2026), and calls the systematic-dump narrative "wrong". Dropped: the source refutes the pattern, it is time-of-day (rows 7/67), and the counterparty is speculative.
4. "arXiv 2026 crypto anomaly survives transaction costs". Hits were anomaly-detection papers (arXiv 2603.18021, 2607.13916) and a momentum-costs paper. No directional mechanism with a counterparty.
5. "crypto index rebalancing price impact". Only WisdomTree rebalance notices; no study with numbers. Events are quarterly, so time-to-verdict would also fail.
6. "intraday momentum cryptocurrency first half-hour". Shen/Urquhart/Wang (Financial Review 2022) is attributed by snippet to liquidity provision. Not fetched this run (it was blocked on 2026-09-27). Its last-half-hour horizon cannot carry 100+ bps; rows 7/67.
7. "Strategy MSTR weekly purchases price impact". Buying is voluntary and done OTC; no study found. Not a forced counterparty.

Fetched https://arxiv.org/abs/2607.09426 (OK; Quarter-Hour Effect). The abstract says "opening order imbalance predicts returns over four to twelve hours". The abstract gives no bps figure and claims no net-of-cost strategy. Not usable: it needs signed 10-second flow, and the 2026-09-27 seat recorded the authors' ~0.5 bp per boundary figure (fee-trapped).

Lens judged dry. WebSearch never refused for budget reasons.
