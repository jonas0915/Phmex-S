# DATA — what exists, where, how to load it

Use `research.swarm.lib.load_data`; never read caches by hand in a screen.

| dataset key | path | coverage | timeframes | notes |
|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC | 1m, 5m, 1h | pkl DataFrames, cols open/high/low/close/volume, UTC index. Funding: `funding_<SYM>_USDT_USDT.json`, a list of `{ts ms, rate}` rows, loaded via `load_funding(symbol, era, token)` — funding is holdout-gated exactly like price data, anchored to the same era boundary. Train ends ≈ 2026-08-10; holdout after. |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols (1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP), 1h 2025-06-27 → 2026-08-01 | 1h (5m partial) | parquet. **Use this for multi-day / event-driven theses.** Train ends ≈ 2026-04-24. |

**Cross-dataset holdout caveat:** `long_1h` holdout (final 25% of 2025-06-27→2026-08-01) ≈ 2026-04-23→08-01; `mr_edge` train (2026-06-01→~08-10) falls inside that window, and 18 of the 19 `long_1h` symbols also exist in `mr_edge` — so `mr_edge` train data overlaps the `long_1h` holdout window. Rule: a thesis on the `long_1h` dataset may not use `mr_edge` data dated on or after 2026-04-23 in any exploratory probe or signal; the gatekeeper rejects a `long_1h` thesis whose probes did.

`load_data.fetch_ohlcv_ccxt(symbol, timeframe, since_ms, until_ms, token=...)` pulls longer public Phemex history (up to ~2 years of 5m/15m/1h/1d bars) when a thesis horizon exceeds what the local caches above cover. It is gated to the same holdout boundary as `load_ohlcv`/`load_funding` (anchored to the symbol's `mr_edge` 1h cache, falling back to `ETH`'s bounds when the symbol has none): a request reaching at/after that boundary without the committee token raises `HoldoutError` before any network call. It is available only to the build stage / committee-token holders, for longer public history beyond the local caches — analysts and screens do not call it (see desk.js `RULES`). Any such pull must be recorded in the frozen spec's dataset field. Save fetched frames under the run dir `screens/<id>/data_*.pkl` (gitignored).

Non-train screen outputs are era-suffixed (`out.holdout.json`, `trades.holdout.csv`) inside `screens/<id>/` and never overwrite the train-era `out.json` / `trades.csv` that downstream phases cite by path (`screen.run_screen`, controller ruling, Task 5).

Other bot-collected data (not loadable via `load_data`; exploratory only):
- `logs/l2_ticks/<SYM>/<date>.jsonl.gz` — depth-5 book + tape, BTC/ETH/INJ/ARB, 2026-07-13 → 09-10 (1.9 GB).
- `logs/flow_capture.jsonl` — OB + flow snapshots 2026-05-11 → 09-09 (301 MB, 918k rows).
- `logs/entry_snapshots.jsonl` — 1,374 live entry contexts 2026-04-07 → 09-14.
- Archive tarball: `~/Desktop/Phmex-S-archive/phmex-s-market-data-2026-09-09.tar.gz` (1.97 GB) — same content.

Engines (reference; the desk uses `lib/screen.py`): `backtest.py`, `backtester.py`, `scripts/slot_lab/mr_edge_screen.py` (holdout guard pattern), `scripts/slot_lab/mr_edge_signal_table.py` (forming-bar regen).
