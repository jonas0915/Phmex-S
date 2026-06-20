# ST2.0 — How It Actually Takes Trades (Track A: empirical, real data only)

**Date:** 2026-06-20  •  **Author:** analysis agent (read-only)
**Scope:** EMPIRICAL only. Every number below is read from a file/log the same turn and cited to its source. No simulation, no proposals. This feeds the forward-confirm lab; it does **not** recommend deploying anything.

## TL;DR
- **Maker fill is the binding constraint.** Real fill rate = **41.5%** (27 fills / 38 misses / 65 unique attempts) across all logs `bot.log.1..3`, deduped by timestamp. Corroborates the documented ~43%.
- **Fill rate is wildly uneven by symbol.** ETH ~59% and INJ ~67% fill; BTC ~30%; ENA ~20%; HYPE/DOGE/ARB **never filled** (0/2, 0/2, 0/1) in this window.
- **On the 29 filled live trades persisted in state:** WR 41.4% (12W/16L/1 scratch), expectancy **−$0.12/trade**, net **−$3.50**. Avg loss (−$0.35) is ~2× avg win (+$0.18) — loss asymmetry, not low hit rate, is doing the damage.
- **Every number that depends on order-book imbalance from CLOSED trades is unavailable:** all 29 live trades have `entry_snapshot.ob == null` (the documented ob:null bug, fix shipped 2026-06-19/20 so it is not yet in the closed set). Imbalance is only recoverable from the log fill lines, not from the trade records.
- **Fills-vs-misses condition comparison is NOT possible on imb/buy_ratio/trade_count** — miss log lines carry only symbol + timestamp, no conditions. The only fill/miss discriminators observable are **symbol** and **time**.
- **n is small everywhere.** No per-bucket conclusion below survives a significance bar; treat all as hypotheses for forward-confirm.

## Data sources (real, cited)
- Fill/miss events: `logs/bot.log`, `logs/bot.log.1`, `logs/bot.log.2`, `logs/bot.log.3` (`.4/.5` contain no ST2.0 events). Lines: `[SLOT LIVE] ST2.0 ENTRY SHORT <sym> | Fill: <px> ... imb=<> br=<> tc=<>` (fills) and `[SLOT LIVE] ST2.0 <sym> short — no fill (PostOnly miss)` (misses). Logs are double-written (color+plain) and **rotated logs overlap in time**, so events were deduped on `(timestamp, symbol, fill_px)` / `(timestamp, symbol)`.
- Closed trades: `trading_state_ST2.0.json` → `closed_trades` with `mode=="live"`. Snapshot mtime **2026-06-19 21:13 PT**; 29 live closed trades (opened from 2026-06-13, last closed 2026-06-19 21:13 PT).
- Lab tools read first to trust them: `scripts/st2_lab/fills.py`, `scripts/st2_lab/real_trades.py`.

## ⚠️ Two discrepancies surfaced (not silently resolved)
1. **Lab `fills.measured_fill_stats()` default reads only `logs/bot.log`**, which currently has 0 ST2.0 attempts → it reports "no attempts yet". The real history is in the rotated logs. I parsed all of them with timestamp-keyed dedup.
2. **The bot's own runtime scoreboard says 45 live trades, WR 40.0%, PnL −$8.24** (`logs/bot.log:2026-06-20 16:58:00 [SLOT] ST2.0 (LIVE/ACTIVE) | 45 trades | WR: 40.0% | PnL: $-8.24`), but the **state snapshot has only 29 live closed trades, net −$3.50**. The state file is from 2026-06-19 21:13 PT; the bot has taken ~16 more live trades since. **All entry-condition analysis below covers the 29-trade snapshot only**, not the bot's full live history. The 41% WR and ~41% fill rate agree across both views.

---

## Q1 — Real maker fill rate, overall and by symbol

**Overall: 27 fills / 38 misses / 65 attempts = 41.5%.**
Source: parse of `logs/bot.log.1..3`, deduped on `(ts, symbol, fill_px)` and `(ts, symbol)`. Event time span 2026-06-13 15:59 → 2026-06-19 20:43.

| Symbol | Fills | Misses | Attempts | Fill % |
|--------|------:|-------:|---------:|-------:|
| ETH    | 10 | 7 | 17 | 59% |
| ZEC    |  5 | 8 | 13 | 38% |
| BTC    |  3 | 7 | 10 | 30% |
| INJ    |  4 | 2 |  6 | 67% |
| ENA    |  1 | 4 |  5 | 20% |
| BCH    |  2 | 2 |  4 | 50% |
| 1000PEPE | 1 | 2 | 3 | 33% |
| XRP    |  1 | 1 |  2 | 50% |
| HYPE   |  0 | 2 |  2 |  0% |
| DOGE   |  0 | 2 |  2 |  0% |
| ARB    |  0 | 1 |  1 |  0% |

Reads: ETH and INJ are the symbols that actually fill (combined 14/23 ≈ 61%); BTC fills poorly (~30%) despite being a frequent candidate; several symbols (HYPE/DOGE/ARB) **never** filled — but **all per-symbol cells have n ≤ 17 and most ≤ 6, so "X never fills" is not yet statistically real** (e.g. 0/2 is consistent with a 30–40% true rate by chance).

## Q2 — Among FILLED trades: winners vs losers (29-trade snapshot)

WR 41.4% (12W / 16L / 1 scratch). Expectancy **−$0.1208/trade**, net **−$3.50**. Avg win **+$0.177**, avg loss **−$0.352** (loss ≈ 2× win). Source: `trading_state_ST2.0.json` live trades.

**Entry features present at fill (W vs L means).** NOTE: `ob.imbalance`/`spread_pct` are `null` on all 29 trades (ob:null bug) → excluded. Only `flow` + `regime` are real.

| Feature (mean)     | Winners | Losers |
|--------------------|--------:|-------:|
| buy_ratio          | 0.790 | 0.757 |
| cvd_slope          | −0.193 | −0.136 |
| **trade_count**    | **51.7** | **131.5** |
| **large_trade_bias** | **0.433** | **0.066** |
| adx                | 23.2 | 25.3 |
| atr_pct            | 0.0034 | 0.0034 |
| vol_ratio          | 0.745 | 0.884 |
| **duration_s**     | **1351** | **2376** |

Two directional hypotheses (n far too small to confirm, flag heavily):
- Losers entered into **~2.5× higher trade_count** (busier tape) and **held ~75% longer**.
- Winners had **much higher large_trade_bias** (0.43 vs 0.07) — fills where big prints leaned the entry direction.

**By symbol (live PnL):**

| Symbol | n | Net | Avg | WR |
|--------|--:|----:|----:|---:|
| INJ    | 4 | −1.45 | −0.36 | 25% |
| ETH    | 12 | −1.31 | −0.11 | 42% |
| BTC    | 3 | −0.86 | −0.29 | 33% |
| ZEC    | 5 | −0.68 | −0.14 | 40% |
| 1000PEPE | 1 | −0.33 | −0.32 | 0% |
| XRP    | 1 | −0.29 | −0.29 | 0% |
| ENA    | 1 | +0.34 | +0.34 | 100% |
| BCH    | 2 | +1.06 | +0.53 | 100% |

The two profitable symbols (BCH, ENA) have n=2 and n=1 — meaningless individually. Note INJ/ETH **fill well but lose money** — i.e. the symbols that fill are not the symbols that win. The execution-vs-edge mismatch the docs warned about shows up here, with the caveat of tiny n.

**By divergence label:** bearish n=8 WR 38% net −1.27 / bullish n=7 WR 29% net −1.68 / none n=14 WR 50% net −0.56.
**By regime label:** TRENDING_DOWN n=5 WR 20% net −2.06 (worst) / QUIET n=7 WR 29% net −1.69 / CHOPPY n=8 WR 50% net +0.30 / TRENDING_UP n=6 WR 67% net +0.01. (All n≤8 — hypothesis only.)

## Q3 — FILL vs MISS condition comparison

**Cannot be done on imbalance / buy_ratio / trade_count.** Miss log lines (`... short — no fill (PostOnly miss)`) carry **only symbol + timestamp** — no entry conditions are logged at miss time. The `[ST FILTER] blocked (cvd= spread= br= tc=)` lines exist but log **empty values** (0 lines with real numbers across `bot.log.1..3`). The only fill/miss discriminators observable are:
- **Symbol** (Q1 table) — the strongest observable signal: misses concentrate on BTC/ZEC/ENA/HYPE/DOGE; fills concentrate on ETH/INJ.
- **Time** — not enough miss timestamps with matched conditions to compare regimes.

So the honest answer to "do conditions at a fill differ from a miss?" is: **not measurable from current logs.** The ob:null fix (shipped 2026-06-19/20) plus persisting conditions on miss events is what would make this answerable going forward.

## Q4 — Exit behavior

| Exit reason | n | Net | Avg | WR |
|-------------|--:|----:|----:|---:|
| st2_hold        | 22 | −1.76 | −0.080 | 50% |
| exchange_close  |  6 | −1.74 | −0.291 | 17% |
| min_margin_skip |  1 | 0.00 | 0.00 | 0% |

`st2_hold` (the intended maker-exit-after-hold path) is roughly breakeven-ish (50% WR, small avg loss). `exchange_close` (n=6) is where the money is lost (17% WR, −$0.29 avg) — these are the trades that ran past the maker-exit and got force-closed.

**Hold time:** median 1364s (~23 min), mean 1870s, min 1s, max 17962s (~5h, one outlier). 25 of 29 sit in the **15–30 min** bucket — consistent with the documented ~15-min reversion thesis. The `time_exit=hard240` tag in the position-open log is a **label, not the realized hold** (realized holds are minutes-to-tens-of-minutes, far past 240s). Hold-bucket PnL: the 15–30m bucket (n=25) is net −$2.55; the single >60m trade is −$0.88. Longer holds skew negative, but n is too small to call the ~15-min hold helpful or harmful.

## Q5 — Time of day (PT, by opened_at, 4h blocks)

| Block (PT) | n | Net | WR |
|------------|--:|----:|---:|
| 12:00a–4:00a | 11 | −0.20 | 55% |
| 4:00a–8:00a  | 5 | −1.15 | 40% |
| 8:00a–12:00p | 3 | −1.88 | 0% |
| 12:00p–4:00p | 4 | −0.83 | 0% |
| 4:00p–8:00p  | 4 | +0.07 | 50% |
| 8:00p–12:00a | 2 | +0.48 | 100% |

Directional hint: **US daytime (8:00a–4:00p PT) is 0% WR across 7 trades**; overnight/early (12:00a–4:00a) and evening are where the wins cluster. **n ≤ 11 per block — not significant.** Hypothesis only.

---

## What the real data says the bottleneck / lever is

1. **The bottleneck is execution, exactly as documented.** ~41% maker fill, heavily symbol-dependent. The symbols that fill (ETH, INJ) are not the symbols that win in this snapshot — so improving fill rate naively could just buy more of the losing fills.
2. **The damage is loss asymmetry + force-closes, not the hit rate.** 41% WR with a +1R/−2R payoff is structurally negative; the `exchange_close` bucket (17% WR) is where it bleeds. The maker-hold (`st2_hold`) path is near breakeven.
3. **The single biggest data gap is `ob.imbalance` being null on every closed trade** and **no conditions logged on misses.** Until the shipped ob:null fix lands in the closed set and miss conditions are persisted, Q3 (the core "how it takes trades" comparison) is unanswerable from data — this is the highest-value instrumentation lever, not a parameter change.

## Significance flags (read before acting on anything above)
- Overall fill n=65, overall trade n=29 — both below the 30–50 floor for stable rates; **treat as screening-grade, not training-grade.**
- Every per-symbol, per-regime, per-hour, per-divergence bucket has **n ≤ 12**; several have n=1–2. None is statistically conclusive.
- The state snapshot lags the live bot by ~16 trades / ~$4.7 of PnL — re-run against a fresh state file before any forward-confirm decision.
- All directional reads (trade_count↑→lose, large_trade_bias↑→win, US-day→lose, longer-hold→lose) are **hypotheses for the forward-confirm lab**, cross-check against `memory/lessons.md` before acting.
