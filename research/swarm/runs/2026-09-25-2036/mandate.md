# MANDATE — desk run 2026-09-25-2036

Run id: 2026-09-25-2036 · written 2026-09-25 8:36 PM PT (2026-09-26T03:36:47Z per `research/swarm/runs/2026-09-25-2036/launch_args.json`).
kb_check status: **KB OK** (verbatim output in the last section).
Governing documents: `research/swarm/kb/CONSTRAINTS.md`, `research/swarm/kb/STANDARDS.md`, `research/swarm/kb/DATA.md` (canonical if anything below differs).
Run limits (from `launch_args.json`): max_analysts 8, max_screens 5, dry_run false.

## 1. Purpose

The desk exists to grow a small account. That is its **purpose**, not a screening threshold.

The owner's ultimate aspiration, recorded 2026-09-17 in the owner's words "keep it in mind, don't set it yet", is +10% account ROI per day. The desk works toward it only by compounding real, verified edges. It is never a bar that any thesis is judged against. It never justifies leverage or aggression as a stand-in for edge.

The pass bar is, and stays: **per-trade net expectancy > 0 after c, with the 95% bootstrap CI excluding zero**, together with CONSTRAINTS "viable" criteria 1-5:
1. Train-era screen with n ≥ 30, and the bootstrap CI95 of net bps (after `c`) excludes 0.
2. Observed WR ≥ p* for the spec's TP.
3. Time-to-verdict at n=50 is ≤ 26 weeks at the expected frequency (`fee_math.time_to_verdict_weeks`).
4. Every symbol in the universe passes `fee_math.lot_check` at $200 notional.
5. The signal is computable on closed bars from data the bot actually has.

**No daily-ROI target is applied to any thesis in this run.**

## 2. Capital and sizing

- Design basis is **$200**. Screen position size is `fee_math.position_notional()` = **200.0** USD notional (10% margin at 10x). Output checked this run: `python3 -c "from research.swarm.lib import fee_math as f; print(f.position_notional())"` → `200.0`.
- At this size there are at most two paper slots and no cross-sectional baskets.
- Lot minimums come from `fee_math.LOT_MIN_USD` (printed this run): `{'BTC': 77.74, 'ETH': 24.9738, 'SOL': 1.0143, 'XRP': 1.0044, 'DOGE': 1.001}`. `minOrderValueRv` is 1 USDT.
- `fee_math.lot_check(sym, fee_math.position_notional())` output this run:
  - BTC `{'ok': True, 'lots': 2, 'lot_usd': 77.74}`
  - ETH `{'ok': True, 'lots': 8, 'lot_usd': 24.9738}`
  - SOL `{'ok': True, 'lots': 197, 'lot_usd': 1.0143}`
  - XRP `{'ok': True, 'lots': 199, 'lot_usd': 1.0044}`
  - DOGE `{'ok': True, 'lots': 199, 'lot_usd': 1.001}`
- Every other universe symbol must be checked the same way at registration.
- `max_concurrent = fee_math.max_concurrent(sl_bps)` is filled by `registrar.freeze` (STANDARDS #17).

## 3. Minimum net edge after c

- Cost per round trip is **c = 11.5 bps** (`fee_math.C_BPS`). It is made of **7.0 bps** fees (`fee_math.FEES_RT_BPS`: maker entry 0.01% plus taker exit 0.06%) and **4.5 bps** measured adverse selection (`fee_math.ADVERSE_BPS`). Values printed this run: `11.5 7.0 4.5`.
- The minimum acceptable edge is **net bps per trade > 0 after the full 11.5 bps c**, with the bootstrap CI95 (`bootstrap_ci.mean_ci`) excluding 0. Gross edge that only covers fees but not adverse selection fails.
- Target ladder is 100-300 bps moves. The command run was exactly `python3 -c "from research.swarm.lib import fee_math as f; print({x: f.p_star(x) for x in (100,150,200,300)})"`, and its output was:

```
{100: 0.5575, 150: 0.5383333333333333, 200: 0.52875, 300: 0.5191666666666667}
```

- So p* runs from about 52% (300 bps) to about 56% (100 bps). Why these targets: CONSTRAINTS says "Scalping is fee-trapped: sub-0.1% moves cannot pay". Its p* table shows 25 bps needs 73.0% and 50 bps needs 61.5%, so the desk works only where the cost share of the target is small.

## 4. Horizons in scope

- **In scope:** intraday to multi-day holds (hours to days).
- **Explicitly NOT in scope:** scalping, meaning sub-100 bps targets or minute-scale holds that depend on sub-5-min reaction.
- **Explicitly IN scope:** event-driven theses, such as scheduled macro prints, exchange or listing events, token unlocks as an input rather than a base short (see row 19), and forced-flow events.
- **At least two analyst lenses must target holds > 8h.** Any hold over 8h must account for funding at every 8h settlement. Load funding via `load_data.load_funding(symbol, "train")`, or `load_reference_funding` for a second symbol. It is holdout-gated like price. CONSTRAINTS reference: BTC ≈ +0.01%/8h, and meme perps are often negative.

## 5. Execution reality of the Phmex-S bot (from CONSTRAINTS)

- **5-min poller**, so there is no sub-minute reaction.
- Entries are **maker limit orders**. Real maker fill is about **27%**, and the misses are adversely selected. Exits are **taker**.
- Order book snapshots arrive every 60s, depth 5, for BTC/ETH/INJ/ARB only. There is no streaming book.
- **The Mac may sleep.** Slow horizons (hours to days) tolerate that; 5-min horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel. They are graded daily at 6 AM PT by `scripts/lab_adjudicator/adjudicate.py` and killed via `touch .kill_<slot>`.
- Simulated fills are screening-grade upper bounds. The forward test is the only adjudicator (STANDARDS #10).
- Signals must use closed bars only. Forming-bar live slots reproduce only about 40% of closed-bar replays (STANDARDS #4).

## 6. Datasets and train/holdout boundaries (from `research/swarm/kb/DATA.md`)

Load everything through `research.swarm.lib.load_data`. Holdout is the final 25% of each dataset's range (`load_data.holdout_start`, frac=0.25).

| dataset key | path | coverage | timeframes | train ends |
|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC; funding JSON per symbol | 1m, 5m, 1h | ≈ 2026-08-10 |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols (1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP), 2025-06-27 → 2026-08-01 | 1h (5m partial) | ≈ 2026-04-24 |

- **Use `long_1h` for multi-day and event-driven theses.** GIGGLE was delisted on 2026-08-07 (DATA.md, LESSONS 2026-09-21). The screenable `long_1h` universe is the other 18 symbols. `universe_check` runs before every freeze.
- **Cross-dataset caveat:** the `long_1h` holdout (≈ 2026-04-23 → 08-01) overlaps `mr_edge` train. A `long_1h` thesis may not use any `mr_edge` data dated on or after 2026-04-23 in any probe or signal.
- **Reference symbols** load only through `load_data.load_reference` / `load_reference_funding`, never through `load_ohlcv`/`load_funding` with an era argument (STANDARDS #16).
- Other bot-collected data is exploratory only and cannot be loaded via `load_data`: `logs/l2_ticks/`, `logs/flow_capture.jsonl`, `logs/entry_snapshots.jsonl`.
- **Holdout is never read in this run.** That covers: no era="holdout"/"all", no committee token, no direct cache-file reads, and no `load_data.fetch_ohlcv_ccxt`, which is committee-token gated and outside the research stage. Frozen specs (`specs/*.frozen.json`) and `screens/<id>/signal.py` are never edited.

## 7. Gatekeeper watch list: 15 DEAD_LIST rows most likely to be relabeled

Source: `research/swarm/kb/DEAD_LIST.md`, rows 1-112. This is a FILTER, not a source of ideas (STANDARDS #2, #13).

| row | family | 5-word gist |
|---|---|---|
| 3 | 1h vol-expansion fade | single-split selection bias, negative |
| 4 | Funding harvest (naked perp short) | return was drift, not funding |
| 6 | Liquidation-cascade reversion | high-vol bars continue, not revert |
| 7 | Calendar/microstructure | time-of-day noise after FDR |
| 13 | BTC-TSM (28,5) | deflated Sharpe fails, beats nothing |
| 19 | Token-unlock short | real drift, −86.6% max DD |
| 76 | Multi-day MR / overnight / vol-scaling | dead post-2022 per web sweep |
| 82 | S1 funding-settlement vol breakout | relabel of time-gate plus taker |
| 83 | S2 funding z-score contrarian | own funding study: R² ~0 |
| 84 | S3 FOMC/CPI first-candle momentum | macro-print breakeven asserted, unpulled |
| 106 | cross_asset_btc_shock_lag | BTC-lead alt-lag CI fully negative |
| 107 | cross_asset_ethbtc_regime_rotation | ETH/BTC rotation CI fully negative |
| 110 | owner_record_liq_cascade_continuation | cascade continuation CI fully negative |
| 111 | vol_structure_volscale_continuation | vol-scaled continuation CI straddles zero |
| 112 | informed_flow_btc_alt_cascade_v2 | paper killed on dollar cap |

Also remember STANDARDS #14: never re-propose the demoted books, the BTC blacklist, gate loosening, universe swaps without a new mechanism, or the funding/XS/OI hunt (rows 5, 10, 11, 16, 20, 34).

## kb_check

Command run: `python3 -m research.swarm.lib.kb_check`

```
KB OK
```
