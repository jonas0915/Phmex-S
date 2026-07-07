# R6 — ETH-TSM-28 Build: Slow-Horizon Trend Slot (2026-07-06)

**What:** New strategy slot `ETH_TSM_28` implementing the pre-registered spec in
`r5_slow_horizon_research.md` §7 — long-only daily time-series momentum
(Han/Kang/Ryu 28-day lookback / 5-day min hold / top-tercile), one fixed
0.01-ETH position on ETH/USDT:USDT, −8% resting exchange stop as the ONLY
protective exit. **Ships DEFAULTING TO PAPER** via the standard slot framework;
going live is an explicit promote-sentinel touch (§9).

**Status at write time:** code merged in working tree, `py_compile` clean, full
test suite **381 passed** (354 pre-existing + 27 new in `tests/test_eth_tsm.py`),
adjudicator digest renders the new experiment line (run read-only this session).
**Bot NOT restarted** — nothing here is live until the next audited restart.

---

## 1. The rule as implemented (and every declared deviation)

| Spec item (§7, frozen) | Implementation | Deviation? |
|---|---|---|
| Daily signal at 00:00 UTC close | Once-per-cycle check: when the UTC date differs from `last_eval_date`, fetch 1d candles and evaluate. First cycle after restart also evaluates (same signal — complete candles only). No threads, no cron. | Evaluation happens at the first bot cycle of the UTC day (~00:00-00:02 UTC), not exactly at 00:00. Declared; immaterial at daily horizon. |
| Top tercile of expanding-window 28d-return history | `tsm_slot.compute_signal`: signal ON ⇔ current 28d return ≥ 66.667th percentile (numpy linear) of PRIOR 28d returns, **current observation excluded** from the history it is ranked against; boundary ties are ON (≥). Interpretation stated in the module docstring. | Window capped at `limit=500` daily candles (Phemex OHLCV whitelist {5,10,50,100,500,1000}, lessons.md) → ≤471 historical returns ≈ 1.3y, vs the spec's "≥2 years". Declared; `TSM_OHLCV_LIMIT=1000` is the one-line extension. Minimum 90 historical returns before any signal (fails CLOSED). |
| Entry: post-only at bid; take after 30 min | One PostOnly maker attempt per cycle (existing `exchange.open_long`, 20s rest); after 30 min from the day's first attempt → one market order (`exchange.open_long_market`, new). | A single 30-min resting order is impossible inside the 180s cycle watchdog; per-cycle re-posting at the fresh touch is the architecture-native equivalent. Declared. |
| Exit: signal leaves top tercile after 5d min hold; maker-first, 30-min taker fallback | Daily eval sets `exit_pending`; `_close_slot_position(..., "signal_exit")` runs with `urgent=False` → patient maker (25s at the touch) then market fallback, retried each cycle until closed. | Maker window is 25s/cycle (bounded by `PATIENT_EXIT_PATIENCE_S` watchdog math, exchange.py:586-589), not 30 min. Worst-case extra cost = taker−maker = 5bp on ~$17.7 ≈ **$0.009**. Declared. |
| Disaster stop −8% from entry, exchange-side | SL-only conditional order placed at fill (`exchange.place_stop_loss`, new — NO TP leg), `triggerDirection="descending"` for the long, `price_to_precision` rounding. If placement fails: loud ERROR + Telegram + per-cycle re-placement (heal loop), because this slot has no software exit fallback. | None. |
| 0.01 ETH fixed, isolated 3x, no pyramiding/vol-scaling | Fixed `TSM_AMOUNT_ETH=0.01`; leverage flipped to 3x isolated per-symbol before the order, restored to 10x after exit (§4). Margin recorded as notional/3 ≈ $5.90. | None. |
| No Kelly / no auto-demote | Existing per-slot rails re-used to opt OUT: `loss_cap_usdt=-999.0`, `kelly_min_trades=10**9` (ST2.0 precedent — same fields, opposite direction). Kill criteria live in the adjudicator (§7). | None. |
| BTC + market-portfolio signals logged in parallel | BTC replica signal (same rule) logged daily in the sidecar (`btc_signal_on`, `btc_ret_28d`), best-effort. | Value-weighted market-portfolio signal NOT logged (needs cap-weighting infra); declared skip. |
| Log every funding payment | NOT in the bot. Funding is retrievable offline from Phemex (`fetch_funding_history`) — flagged as an adjudicator/nightly follow-up (§11). | Declared. |

**Min-hold semantics:** entry day = day 0; `held_days ≥ 5` first true on the 5th
daily eval after entry (`tsm_slot.held_days`/`min_hold_met`, tested).

**State:** all slot decisions persist in `eth_tsm_28_signal.json` (root; atomic
tmp+replace). Deliberately NOT `trading_state_*`-prefixed — the dashboard globs
that prefix and would render the sidecar as a phantom slot
(web_dashboard.py:231-236). Daily records carry
`{date, signal_on, ret_28d, threshold, close, replica_position, actual_position, mode, note, btc_*}` —
the replica is the pure-rule paper twin the adjudicator computes tracking error
against. Trades/positions persist in the framework-standard
`trading_state_ETH_TSM_28.json` (auto-created; auto-discovered by the dashboard).

---

## 2. Investigation #1 — symbol collision / ownership (the big one)

**Findings from reading the code:**
- Phemex one-way mode merges all positions per symbol. The existing framework
  only *detects* overlap after the fact: `_build_position_owners` (bot.py:239-253)
  warns "held by both main bot and slot … slot copy excluded from sync this
  cycle" — main copy wins reconcile, the slot copy is unmanaged. Nothing
  *prevented* overlap: the main entry loop never checked slot holdings, and
  `check_position_conflict` (strategy_slot.py:211-222) blocks only *opposing*
  cross-slot positions, and never consults the main bot.
- **Startup was worse:** `sync_positions` at startup (bot.py, start()) adopted
  ALL exchange positions into the main bot and re-pinned scalper SL/TP
  (1.2%/1.6%) over them (risk_manager.py:596-601 recomputes fixed-%, bot.py
  places them). A TSM position held across a restart — near-certain at 48%
  deployment — would have had its −8% stop cancelled and replaced with a 1.2%
  SL + a TP the spec forbids.
- **Promote had a phantom-trade bug:** promoting a slot holding a PAPER position
  makes the owner map treat it as exchange-backed; the next
  `_sync_exchange_closes` "closes" it and records a fabricated LIVE trade.
  Rare for 5m slots; near-certain for this one.

**Ownership design shipped (all receipts in §6):**
1. **Main bot skip** — main entry loop skips ETH whenever `_tsm_locks_symbol`
   returns a reason: live TSM position held, entry in flight today, or the 3x
   leverage flip not yet restored. Telegram notice each time, deduped per UTC
   day per kind (owner directive).
2. **Other live slots skip too** — same check inserted in the `_evaluate_slots`
   live-entry branch (5m_mean_revert is LIVE and could otherwise take ETH into
   a merged position).
3. **TSM skips the day** if the main bot (or another live slot) holds ETH at
   daily eval or at order time — logged + Telegram, recorded as SKIP-DAY in the
   sidecar day record. No retry until the next daily eval.
4. **Belt-and-suspenders merge guard (owner addendum):** immediately before any
   live TSM order — and before the 3x leverage flip, which would move a
   foreign position's liq price — positions are re-fetched from the EXCHANGE;
   if ANY ETH position exists that the slot doesn't own (manual trade, orphan,
   desynced state), the entry ABORTS for the day with log + Telegram. A failed
   fetch also aborts (unknown = no order). Never trusts local bookkeeping alone.
5. **Startup ownership filter:** live-slot-owned symbols are excluded from the
   main-bot startup sync (fixes the SL/TP re-pin for ALL live slots, not just
   TSM). The slot's own state file restores the position; per-cycle reconcile
   (slot-aware via `_build_position_owners`) manages it from there.
6. **Promote flush:** the promote sentinel now closes any open PAPER positions
   as `promote_reset` (paper book, current ticker price) BEFORE `set_live`, so
   no phantom live trade can be fabricated. Applies to every slot.

**Reconcile proof (path-by-path, read against bot.py:_sync_exchange_closes):**
- TSM live position, stop fires on exchange → Path A: owner map resolves ETH →
  (tsm.risk, tsm_slot); position closed in the SLOT's book with real fill +
  fees from `fetch_my_trades`, reason `exchange_close` (= the disaster stop by
  construction, see §7), `_maybe_auto_demote` no-ops (rails opted out).
- TSM signal exit fills as maker but the close call races to a reduceOnly abort
  → `_slot_pending_exit_reason` stash (existing machinery) makes reconcile tag
  the fill `signal_exit`, not `exchange_close`.
- Orphan scan: slot position is in the owner map → never adopted as an orphan.
  If the slot's state file were LOST, the exchange position would be orphan-
  adopted by the MAIN bot with scalper SL/TP — accepted failure mode (protective,
  visible via Telegram ORPHAN alert; see §3 recovery).
- Live-exit watcher iterates `self.risk.positions` only (main bot) — never
  touches slot positions (bot.py comment at reconcile Path A confirms).

## 3. Collision failure modes + recovery (owner addendum)

| Failure mode | What happens | Recovery |
|---|---|---|
| Main bot and TSM both end up holding ETH (race that beat every guard, e.g. main filled in the same cycle window as a manual trade) | Exchange merges into ONE position. `_build_position_owners` logs `[SYNC] ETH… held by both main bot and slot ETH_TSM_28 — slot copy excluded from sync this cycle` every cycle. Main copy is reconciled; slot copy is frozen (not priced against exchange truth). Both books' SL orders rest — tightest trigger wins. | `touch .demote_ETH_TSM_28` — `_demote_slot` market-closes the slot's recorded amount and flips it to paper; the main-bot remainder stays under normal scalper management. Then check Phemex UI that remaining size matches the main book, and let the TSM leverage-restore loop return ETH to 10x (it runs even for a demoted slot). |
| Manual/unknown ETH position exists when TSM wants to enter | Pre-entry exchange fetch sees it → entry ABORTED for the day, Telegram `[TSM] … ABORTED — exchange already shows an ETH position`. No leverage flip is attempted. | Nothing to do; slot retries at the next daily eval. |
| TSM entry order half-lands untracked (open_long returned None but a fill landed) | Next cycle's pre-entry exchange check sees the unattributed ETH → aborts the day; the per-cycle orphan scanner adopts the fill into the MAIN bot with scalper SL/TP + ORPHAN Telegram. | Close the adopted position manually or let the scalper exits manage it; TSM stays flat that day. |
| Leverage restore to 10x fails after TSM exit | `leverage_3x_set` flag stays set in the sidecar → main bot + live slots stay locked out of ETH (`_tsm_locks_symbol`); restore retried every cycle with ERROR logs. | If persistent: fix manually on Phemex UI (set ETH to 10x isolated), then `rm eth_tsm_28_signal.json`-level surgery is NOT needed — edit the flag or wait: the next successful `set_leverage` clears it. |
| Bot restarts mid-hold | Slot position restores from `trading_state_ETH_TSM_28.json` (stop_loss/take_profit persist, risk_manager.py:327-347); startup filter (§2.5) keeps the main bot's hands off; the −8% SL keeps RESTING on Phemex (placed at entry; `sl_order_id` is not persisted, but heal-loop (1b) only re-places when the id is missing AND … note: after restart the id IS missing, so one duplicate-SL placement can occur — the old SL is swept by `cancel_open_orders` at exit; both are reduceOnly so a double-fire cannot over-close). | None needed. |
| Host asleep at 00:00 UTC | Daily eval runs at wake (first cycle of the new UTC date). Exchange stop protects throughout — this strategy is the shape LEAST hurt by the known host-sleep issue (lessons.md 2026-06-24). | None needed. |

## 4. Investigation #2 — leverage (verified numbers)

- Leverage is set per SYMBOL: `exchange.ensure_leverage` (exchange.py:980-988,
  called once per symbol from the main entry loop, bot.py `_leverage_set`
  cache) → `ccxt.phemex.set_leverage` → `PUT /g-positions/leverage` with
  `leverageRr`. **Positive leverageRr = isolated, negative = cross** (Phemex
  hedged-API convention; the bot's `LEVERAGE=10` has been running positive →
  isolated 10x). Per-position leverage in one-way mode is NOT possible — it's
  per-symbol, which is exactly why the ownership lock exists.
- **Maintenance margin, fetched live this session** from
  `api.phemex.com/public/products` (`leverageMargins`, ETHUSDT index 1036,
  tier 1 ≤ $1M notional): **MMR = 0.5%** (`maintenanceMarginRateRr: "0.005"`).
- Isolated-long liq distance ≈ 1/L − MMR:
  - **3x: 33.3% − 0.5% ≈ −32.8%** from entry (margin ≈ $5.90 on $17.7 notional). Stop at −8% sits 4× closer than liquidation. ✅
  - 10x: 10% − 0.5% ≈ −9.5% — only ~1.5% beyond the −8% stop; a gap/wick
    through the stop region risks liquidation instead of a stop fill. ❌
  - Chosen: **3x isolated** (spec), implemented via new
    `exchange.set_symbol_leverage` (raises on failure — complete-or-skip;
    unlike `ensure_leverage` which swallows errors).
- **Sequencing:** persist `leverage_3x_set=true` in the sidecar BEFORE the flip
  (a crash can never leave ETH at 3x unflagged) → flip to 3x → order → hold →
  exit (any path: signal exit, stop via reconcile, demote, kill) → restore 10x
  (`_tsm_restore_leverage`, immediate attempt + unconditional per-cycle retry;
  flag holds the ETH lock until restore CONFIRMS). Main bot's `_leverage_set`
  cache is re-primed on restore so it won't re-set redundantly.
- **Go-live checklist item:** on the first live entry, verify on Phemex that the
  position shows *Isolated 3x* — the positive-is-isolated convention is from
  Phemex docs and should be eyeballed once with real money.

## 5. Investigation #3 — daily data

- `exchange.get_ohlcv(ETH, "1d", limit=500)` — 500 is on the Phemex whitelist
  {5,10,50,100,500,1000} (lessons.md; CANDLE_LOOKBACK note in CLAUDE.md).
- Phemex returns the in-progress UTC day as the last candle:
  `tsm_slot.complete_daily_closes` drops any row dated today (UTC) so the
  signal only ever sees complete closes (tested).
- Timing: one `last_eval_date != today` check per cycle; on fetch failure the
  date is NOT stamped so the eval retries every cycle until it succeeds. No new
  threads, no cron. REST cost: 2 calls/day (ETH + BTC replica) + 1
  `fetch_positions` per entry-window cycle.

## 6. Change map (file:line, this build)

| File | Lines | Change |
|---|---|---|
| `tsm_slot.py` | NEW (180) | Frozen spec constants; tercile signal math (interpretation documented in docstring); complete-candle filter; min-hold date math; pure-rule replica; sidecar state IO (atomic, per-date idempotent day records). |
| `bot.py` | 22-27 | Import tsm_slot + constants. |
| `bot.py` | 474-501 | `ETH_TSM_28` StrategySlot: paper default, `strategy_name="eth_tsm_28"` deliberately NOT in STRATEGIES (⇒ `_evaluate_slots` skips the entire slot at bot.py:1961-1963 — the scalper exit opt-out), rails opted out (`loss_cap_usdt=-999.0`, `kelly_min_trades=10**9`), no durable trail. |
| `bot.py` | 502-507 | Runtime state: sidecar mirror, entry-in-flight flag, ownership-Telegram dedup map. |
| `bot.py` | 662-676 | Startup sync ownership filter (live-slot-owned symbols excluded from main-bot adoption). |
| `bot.py` | 871-889 | Promote sentinel: paper-position flush (`promote_reset`) before `set_live`. |
| `bot.py` | 1400-1412 | Main entry loop: ETH skip via `_tsm_locks_symbol` + deduped Telegram. |
| `bot.py` | 1913-1920 | `_evaluate_eth_tsm(prices)` wired after `_evaluate_slots` (ERROR-level on failure). |
| `bot.py` | 2318-2326 | Live-slot entry branch: same ETH ownership skip for other live slots. |
| `bot.py` | 3124-3507 | TSM orchestration: `_tsm_slot`, `_tsm_locks_symbol`, `_tsm_notify_ownership` (per-day dedup), `_tsm_restore_leverage`, `_evaluate_eth_tsm` (leverage-restore retry → paper stop replica → live SL heal loop → daily eval → exit retry → entry attempts), `_tsm_price`, `_tsm_daily_eval` (signal + skip-day + replica + BTC log + intents), `_tsm_try_entry` (paper fill; live: halt check → main-holds check → EXCHANGE merge guard → 3x flip → maker/taker per spec → SL-only placement → notify). |
| `bot.py` | 3521-3529 | `_close_slot_position`: `eth_tsm_28` added to the maker-first (urgent=False) exit set. |
| `exchange.py` | 990-1001 | `set_symbol_leverage` (isolated, per-symbol, RAISES on failure). |
| `exchange.py` | 1003-1033 | `place_stop_loss` (SL-only conditional; descending trigger for long; price_to_precision; 3 attempts). |
| `exchange.py` | 1035-1057 | `open_long_market` (taker fallback; ground-truth check on exception). |
| `scripts/lab_adjudicator/adjudicate.py` | 27-31, 119-131, 378-441, 483-520 | Experiment registry `eth_tsm_28` (kill −$10 / 2 disaster stops / 0.1%-per-day tracking over a full 14d window), `grade_eth_tsm`, digest line, file constants. |
| `tests/test_eth_tsm.py` | NEW (478) | 27 tests (see §10). |

## 7. Investigation #5 — exit-path proof (why no scalper exit can touch this position)

- `_evaluate_slots` (bot.py:1961-1963): `strategy_fn = STRATEGIES.get(slot.strategy_name)`;
  `"eth_tsm_28"` is not a key (strategies.py:924-932, asserted by test) → `continue`
  fires BEFORE the exit block — so paper SL/TP, st2_hold, trend-flip,
  adverse_exit, time_exit and the durable-trail ratchet are all unreachable for
  this slot. (The 2026-06-11 "killed slots still run exits" audit note doesn't
  apply: that guard is `is_active`, which sits AFTER the strategy_fn check.)
- Main-bot exits (`check_positions`, partial-TP, trail, live-exit watcher) all
  iterate `self.risk.positions` — the ownership design (§2) keeps ETH out of it.
- `should_take_profit` is None-safe (risk_manager.py:117-119) and
  `take_profit=None` round-trips the state file (risk_manager.py:308/336) — the
  slot sets `pos.take_profit = None` at entry, and `place_stop_loss` never
  creates a TP order.
- Exchange side: the ONLY resting order the slot ever places is the −8% SL
  (`place_stop_loss`, `triggerDirection="descending"` for the long per
  lessons.md, `price_to_precision` rounding). Therefore `exchange_close` on this
  slot ≡ disaster stop — that identity is what the adjudicator's
  disaster-stop counter keys on.
- Remaining exits: `signal_exit` (this build), `slot_demote` / kill sentinel
  (operator-initiated, framework-standard), `promote_reset` (paper flush).

## 8. Investigation #6 — daily-halt interaction (no code change)

A live disaster stop realizes ≈ −$1.42 (−8% of $17.7) plus fees, landing in the
same realized-PnL daily budget as the scalper (halt −3% of balance ≈ −$1.72,
realized-only: bot.py `_compute_today_net_pnl` / `_should_halt_daily_loss`). One
TSM stop-out + a mildly red scalper day ⇒ full-account entry halt for the day.
Spec §9 pre-registers this as a KILL criterion if it happens twice (budget-
sharing broken → pause trend leg). Adjudicator surfaces halt days via the
existing `sizing_15` halt counter; no bot change shipped, per the task.

## 9. Ship / promote / rollback

- **This restart ships:** slot in PAPER (constructor default; no mode sidecar
  exists). Paper trades simulate fills/stop and write the same sidecar records,
  so signal fidelity data accrues immediately.
- **Promote to LIVE (Jonas, explicit):**
  `touch .promote_ETH_TSM_28`
  (sentinel path bot.py:860-908; optional JSON body `{"capital_pct": 0.0}` —
  capital_pct is irrelevant, sizing is fixed 0.01 ETH; any open paper position
  is auto-flushed as `promote_reset`.)
- **Rollback to paper:** `touch .demote_ETH_TSM_28` — market-closes any live
  position, flips to paper, Telegram alert; leverage restore then runs
  automatically. **Hard kill:** `touch .kill_ETH_TSM_28`.
- **Pre-restart:** `/pre-restart-audit` is mandatory before the restart that
  ships this (CLAUDE.md critical rule). Nothing was restarted in this session.

## 10. Quality gate

- `python3 -m py_compile bot.py exchange.py tsm_slot.py strategy_slot.py scripts/lab_adjudicator/adjudicate.py` → clean.
- Full suite: **381 passed** (354 baseline + 27 new), run this session.
- New tests (`tests/test_eth_tsm.py`): tercile boundary inclusive + history
  excludes current + fail-closed on short history; in-progress candle dropped;
  min-hold (day-5 boundary); replica enter/hold/exit; bot-slot config carries
  rails opt-out and a non-STRATEGIES name; no Kelly anywhere in the sizing path
  (source-level assert) + rails never demote at −$9; ownership lock (live
  holding / leverage flag / entry-in-flight; paper = no lock; other symbols
  unaffected); Telegram ownership dedup (1/day/kind); paper entry (0.01 ETH,
  −8% stop, take_profit=None, no leverage call); paper disaster stop; daily
  eval signal-exit respects min-hold; signal-ON sets entry-pending; live
  skip-day when main holds ETH (+Telegram); live entry ABORT on unattributed
  exchange ETH (no leverage call, no order, Telegram); live entry sequencing
  (3x BEFORE order, flag persisted, SL-only at −8%, margin ≈ notional/3);
  leverage restore when flat; adjudicator registration + n=0 honesty + net
  kill line + 2-disaster-stop trip + tracking-error full-window requirement +
  digest line.
- Adjudicator run read-only this session: `[eth_tsm_28] WATCH — n=0 — no verdict | live 0 trades $+0.00 (kill -10) · 0 disaster-stops | 0 days · 0 div | track n/a | no days yet`.
- Telegram/dashboard propagation (CLAUDE.md rule): dashboard auto-discovers
  `trading_state_ETH_TSM_28.json` (web_dashboard.py:227-250) + mode sidecar;
  Telegram covered by the slot's dedicated entry message, standard
  `notify_exit`/paper notifications, ownership notices, and the nightly
  adjudicator digest line. The per-cycle `[SLOT]` status log includes the slot
  automatically.

## 11. Follow-ups (not shipped, declared)

1. **Funding-payment logging** (spec §7.6): add `fetch_funding_history` pull to
   the adjudicator nightly so realized funding lands in the cost budget. Offline,
   no bot change.
2. **History depth:** consider `TSM_OHLCV_LIMIT=1000` (~2.7y) at the first
   monthly review — changes the tercile threshold slightly; log both before
   switching (it's a pre-registered-spec deviation either way, so decide once,
   before promote if possible).
3. **Market-portfolio replica signal** (spec §7.1) — skipped; needs
   value-weighting infra.
4. First live entry: eyeball *Isolated 3x* on Phemex UI (§4 checklist).
