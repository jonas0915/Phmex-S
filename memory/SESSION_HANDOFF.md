# Session Handoff — Resume Here

**Last session ended:** 2026-04-16 ~10:30 PM PT
**Session grade:** A- — major entry gate hardening + scanner redesign shipped, 7 commits
**Bot PID:** 30967 (restarted 2026-04-16 10:18 PM PT)
**Balance at session end:** ~$72.82 USDT (peak $76.24, drawdown 4.5%)

---

## What was deployed this session

### Code commits (tonight)
1. **`18fe372`** feat: block 2 AM PT (UTC 9) — 26% WR, -$4.22 all-time
2. **`9c8dfca`** feat: soft tape gate — block buy_ratio <40%/>60% when trade_count 5-20
3. **`0cf8072`** feat: divergence gate cooldown — 3 clean cycles or 10 min before re-entry
4. **`75ac65a`** feat: add _compute_history_scores() + scanner config updates
5. **`f2bc79d`** feat: rewrite volatility_scan() with composite history x market scoring
6. **`1c8101b`** feat: remove daily symbol cap gate, add RATE WATCH monitoring log
7. **`fe362fd`** config: scanner top_n 5→8, min_volume 10M→3M, add min_history_trades=10

### Changes summary
| Change | File | What |
|---|---|---|
| 2 AM PT time block | bot.py:1091 | UTC 9 added to `_BLOCKED_HOURS_UTC` — 26% WR, -$4.22 all-time |
| Soft tape gate | bot.py:~1017 | buy_ratio <40%/>60% blocks entry when trade_count 5-20 |
| Divergence cooldown | bot.py:1014 + init | `_divergence_cooldown` dict — 3 clean cycles OR 10 min before re-entry |
| History score helper | scanner.py | `_compute_history_scores()` — sigmoid(avg_net_pnl × 10) per symbol |
| Composite scanner | scanner.py | `volatility_scan()` rewritten — composite = history × market score |
| Daily cap removed | bot.py:894 | Hard cap gate replaced with `[RATE WATCH]` monitoring log at 4+ entries |
| Scanner params | .env | SCANNER_TOP_N 5→8, SCANNER_MIN_VOLUME $10M→$3M, SCANNER_MIN_HISTORY_TRADES=10 |

---

## New scanner — what to watch

First scan result (10:18 PM PT):
- **New symbols in rotation**: ORDI, XLM, AAVE, TAO (were never in the old watchlist)
- **Dropped**: LINK (low history score + flat market)
- **Scores are all very small (0.001–0.012)** because market was flat tonight (-0.5% BTC). `market_score = change_norm × vol_rank`, and vol_rank is normalized by BTC's $369M volume, making smaller caps near zero. This is correct behavior on flat days — on active days scores will spread more.
- **SUI hist=0.22** — accurately reflects its poor track record
- **ORDI had +91.8% 24h** but scored only 0.006 due to tiny vol_rank ($4.7M vs $369M BTC)

**Monitor next 24-48h:**
1. Do new symbols (ORDI, XLM, AAVE, TAO) generate valid signals?
2. Do scores spread meaningfully on a volatile day?
3. Any `[RATE WATCH]` lines — how often does a symbol exceed 4 entries/day?
4. Gate fixes (soft tape, divergence cooldown) — do they reduce adverse_exits?

---

## Root causes found in Apr 16 trade audit

1. **Tape gate inactive overnight** — trade_count ≤ 20 during 12-3 AM PT = gate always skipped
2. **Divergence gate cleared in 1 cycle** — bot re-entered immediately after repeated blocks
3. **Daily cap burned before daylight** — XRP/SUI/LINK hit 3/3 by 3:29 AM PT, zero daytime trades
4. **Scanner locked to 5 symbols** — BTC/ETH had ADX 13-20 (no signals), capped symbols locked out

---

## Phase 2 status (unchanged)

### Next: Phase 2a (fee reduction)
- All prereqs met (C1/C2/C3/I9 landed)
- Verify maker/taker ratio from exchange order history
- Completion gate: fee rate ≤ 50% of pre-deploy rate over 48h

### Open decisions (still pending)
- Phase 2b regime-aware slot gating
- Phase 2d changelog writer
- Autonomous mutation cap: 1/day + 2/week (TBD)

---

## Outstanding follow-ups (carried forward)

- **`.env` tracked in git** — `git rm --cached .env` needed (Jonas's call, keys rotated 04-13)
- **backfill_fees.py** — has hardcoded machine-specific paths, not committed yet
- **Phase 2a** — fee reduction work unblocked
- **Scanner vol_rank tuning** — BTC dominates vol_rank; may need log normalization after a few days of data
- **Fee data in trading_state.json** — `fee_usdt` field is 0 for all 417 trades. Real net loss is worse than reported. Root cause unknown.

---

## Active monitoring (carried forward)
- `[RATE WATCH]` log lines — new, monitors high-frequency symbol entries
- `[TAPE GATE SOFT]` log lines — new, fires on thin tape with extreme buy ratio
- `[DIVERGENCE COOLDOWN]` log lines — new, fires when divergence cooldown active
- `[TIMEOUT]` log entries (DNS wrap from 04-10)
- Maker fill rate (postOnly fix from 04-09)
- Orphan-position 3-layer defense (live since 04-13)
- Overwatch hourly health checks
- Reconcile every 15min
