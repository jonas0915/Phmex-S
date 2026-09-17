EXPLORATORY ONLY — lens forced_flows, run 2026-09-17-0732. Nothing here is evidence; the screen is the only adjudicator.
Dataset: long_1h TRAIN via load_data.load_ohlcv(era="train"). No mr_edge data loaded anywhere in this folder (STANDARDS #6 caveat).
probe1: 19 symbols incl. GIGGLE (GIGGLE's loader train span runs 2026-01-13 -> 2026-06-12, i.e. into the long_1h holdout window by date; it is excluded from probe2 onward and from the thesis universe). Variant A = own cascade bar; B = +no-recovery confirmation (worse).
probe2: 18 symbols, variant A, adds day-clustered CI (mean_ci over per-entry-day means). Trade-level CI positive; day-clustered null/negative.
probe3: BTC-conditioned (market-wide) variant — NOT screenable (signals(df) sees one symbol; cross-symbol loads would be era-blind in a holdout run). Day-clustered CIs all include 0.
probe4: breadth split of probe2 trades — edge lives on 8+-symbol days (22 days); single-symbol days revert.
probe5: majors-only universes — day-clustered CI still includes 0.
Web: 7 WebSearch, 5 WebFetch opened (arXiv 2608.03616, arXiv 2607.27070, cryptoslate, coinchange, news.bitcoin.com); researchgate 403.
