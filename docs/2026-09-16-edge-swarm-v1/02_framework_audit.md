# Phmex-S framework audit — 2026-09-14 (read-only)

Repo: `/Users/jonaspenaso/Desktop/Phmex-S`. Bot STOPPED since 9/9/2026 7:50 PM PT (owner wind-down). Nothing was edited, no bot process started, no launchd job loaded, no orders placed. Only pytest and git read commands were run. All paths below are absolute unless prefixed with the repo root; `bot.py` means `/Users/jonaspenaso/Desktop/Phmex-S/bot.py`. Times are Pacific, 12-hour.

Side effect of this audit (see §2.3 and §9): running the test suite appended 4 synthetic rows to the gitignored `logs/entry_snapshots.jsonl`. Not reverted (read-only mandate). Fix is one line; see §2.3.

---

## 1. Git state

| Item | Value | Source |
|---|---|---|
| Branch | `main` | `git branch --show-current` |
| HEAD | `ac6551b` "wind-down 2026-09-09: closing record, TASKS review, final ledger state" | `git log --oneline -1` |
| Working tree | clean (`git status --short` printed nothing) | |
| Ahead/behind origin/main | 0 / 0 (`git rev-list --left-right --count origin/main...HEAD` → `0 0`) | remote `git@github.com:jonas0915/Phmex-S.git` |
| Tags | `wound-down-2026-09-09`, `pre-winddown-2026-09-08` | `git tag --sort=-creatordate` |
| Last 15 commits | `ac6551b` wind-down record, then 14 × `chore(auto-backup)` hourly commits from 9/9 12:17 AM through 7:17 PM (`6624484`, `3d7fbec`, `147b573`, `476238a`, `7841ddd`, `a6a7e5a`, `90ffc07`, `862b051`, `e3367ab`, `21f94a0`, `b4191c7`, `4742ded`, `2890d1e`, `b1930ec`) | `git log --oneline -15` |

Funding/fee-capture commits named in `docs/2026-09-09-winddown.md:38` — all six are ancestors of HEAD (`git merge-base --is-ancestor` true for both ends; `git log 36dceb8^..5279b8a`):

| Commit | Date | Subject |
|---|---|---|
| `36dceb8` | 2026-09-07 | risk_manager: merge reconciler-written fees/funding on save |
| `8d5db08` | 2026-09-07 | bot: sum all exchange-close fills for fees, real fee on crumb closes |
| `6f2e211` | 2026-09-07 | daily_report: show funding next to fees |
| `48a243d` | 2026-09-07 | reconcile: cover slot ledgers, capture funding, claim-once matching, atomic per-file apply |
| `c1faefe` | 2026-09-07 | risk_manager: serialize merge + state dump under one lock (review finding) |
| `5279b8a` | 2026-09-07 | reconcile: global claim-once across ledgers, qty-capped side matching, narrow apply window |

The last running bot binary was code `b3d88ad` (wind-down doc line 15; PID 78531 started 9/3 9:31 PM PT), which predates all six. So the `bot.py` / `risk_manager.py` halves of these commits have never executed in a live process. The reconciler half (`scripts/reconcile_phemex.py`) is a separate launchd job and DID run under the new code from 9/7 until 9/9 (see §4).

---

## 2. Test suite

Command: `cd /Users/jonaspenaso/Desktop/Phmex-S && python3 -m pytest -q -x --timeout=600` (pytest-timeout is installed; flag accepted). Output saved at `/private/tmp/claude-501/-Users-jonaspenaso-Desktop/ae940530-2b50-4adf-95cd-95ffdbd3a915/scratchpad/pytest_out.txt`.

### 2.1 Results

| Run | Result |
|---|---|
| `-q -x --timeout=600` | `1 failed, 514 passed, 107820 warnings in 78.54s` (stopped at first failure) |
| `-q -p no:warnings` (full, no `-x`) | `1 failed, 1005 passed in 131.62s (0:02:11)` |
| The failing test alone | `1 passed in 0.02s` |

### 2.2 The one failure (verbatim)

```
FAILED tests/test_mr_edge_screen.py::test_isolation_never_imports_live_bot_modules
E           AssertionError: assert 'bot' not in {'PIL': <module 'PIL' from '...'>, ...}
tests/test_mr_edge_screen.py:495: AssertionError
```

Source (`tests/test_mr_edge_screen.py:493-498`):
```python
def test_isolation_never_imports_live_bot_modules():
    for name in ("bot", "exchange", "config", "risk_manager"):
        assert name not in sys.modules
```
This asserts that no earlier test in the same pytest process imported `bot`. When the whole suite runs, dozens of other tests import `bot` first, so the assertion fails on ordering; in isolation it passes. It is a test-design fragility (should check the research script's own imports, which the second half of the test already does), not a code defect. Warnings are all `pytest_asyncio` deprecation noise on Python 3.14 (`asyncio.iscoroutinefunction` deprecated, `asyncio_default_fixture_loop_scope` unset).

### 2.3 Side effect: the suite writes to a real log file (full detail in §9)

`bot.py:4047` opens the relative path `"logs/entry_snapshots.jsonl"` in append mode. `tests/test_entry_snapshot_ob.py:30` and `:44` call `bot._log_entry_snapshot("BTC/USDT:USDT", "short", "ST2.0", "st2", 0.85, 100.0, 0, ...)` without redirecting that path. Each full-suite run therefore appends 2 synthetic rows (`slot: "ST2.0"`, `price: 100.0`) to the real file. My two runs added rows at `ts` 1789441832 (9/14/2026 8:10:32 PM PT) and 1789441924 (8:12:04 PM PT), 2 each — 4 rows total. File is now 1,374 lines / 782,277 B; the archived copy in the wind-down tarball is 780,293 B. The file is gitignored (`.gitignore:5: logs/`), so `git status` stays clean. Recommended cleanup (not done, read-only): drop the last 4 lines, or filter `price == 100.0` / `ts > 1789430000` in any research reader; and patch the test to monkeypatch the path.

---

## 3. Slot framework

### 3.1 Definition and registration

- Data structure: `StrategySlot` dataclass, `/Users/jonaspenaso/Desktop/Phmex-S/strategy_slot.py:22-98`. Fields at `:28-68`: `slot_id`, `strategy_name`, `timeframe`, `max_positions=2`, `capital_pct=0.5`, `enabled=True`, `killed_at=None`, `paper_mode=False`, `trade_amount_usdt=None`, `loss_cap_usdt=-5.0`, `kelly_min_trades=10` (module constants `LIVE_LOSS_CAP_USDT` / `LIVE_KELLY_MIN_TRADES` at `:12-13`), `adverse_exit_roi`, `adverse_exit_cycles`, `sl_percent`, `tp_percent`, `exact_geometry=False`, `durable_trail_enabled=False`, `requote_attempts=0`, `entry_patience_s=None`.
- `__post_init__` (`:70-98`) validates `exact_geometry` (`:75-77`), builds a private `RiskManager(state_file=f"trading_state_{slot_id}.json")` (`:79-80`), sets sidecar paths, calls `_load_mode()`.
- Helpers: `set_live` `:160-166`, `set_paper` `:168-172`, `set_killed` `:174-178`, `live_trades`/`live_pnl` `:180-184` (filter rows with `mode=="live"`), `should_auto_demote` `:186-216`, `is_active`/`is_killed` `:218-234`, `can_enter` `:245-252`, `stats_summary` `:267-279`.
- Registration is a hardcoded list `self.slots = [...]` in `Phmex2Bot.__init__`, `bot.py:676-864`:

| slot_id | strategy_name | bot.py lines | Notes |
|---|---|---|---|
| `5m_scalp` | `confluence` | `:677-687` | label for the main book |
| `5m_mean_revert` | `bb_mean_reversion` | `:688-722` | `$15`, `requote_attempts=1`, `entry_patience_s=45`, durable trail |
| `5m_liq_cascade` | `liq_cascade` | `:723-730` | paper |
| `5m_narrow` | `confluence` | `:734-741` | shadow paper |
| `ST2.0` | `ST2.0` | `:748-769` | `$5`, `loss_cap -10`, `kelly_min_trades=40` |
| `ETH_TSM_28` | `eth_tsm_28` (not a `STRATEGIES` key) | `:778-791` | rails opt-out `loss_cap -999`, `kelly_min_trades=10**9` |
| `DONCHIAN_BTC`, `DONCHIAN_ETH` | `donchian_ensemble` (not a key) | `:801-827` | same opt-out; `paper_mode=True` at `:807`, `:822` |
| `HTF_L2` | `htf_l2_anticipation` | builder `:882-919`, appended `:832-834` | gated by `Config.HTF_L2_ENABLED` |
| `VWAP_CROSS` | `vwap_sma_cross` | builder `:921-951`, appended `:838-840` | gated by `Config.VWAP_CROSS_ENABLED` |
| `SR_BOUNCE` | `sr_bounce` | `:856-868` | `$5`, SL 1.5 / TP 2.5, `exact_geometry=True` |

Two idioms:
1. Generic — `strategy_name` is a key in `STRATEGIES` (`strategies.py:1050-1060`); the slot runs the full `_evaluate_slots` gate/exit engine (`bot.py:2952+`).
2. Bespoke — `strategy_name` deliberately absent from `STRATEGIES` so `_evaluate_slots` skips it (`bot.py:2959-2961`); its logic lives in a dedicated method called from `_evaluate_all_slots` (`bot.py:2927-2950`: `_evaluate_eth_tsm` `:2940`, `_evaluate_donchian` `:2948`). Rationale comment `bot.py:796-800`.

Config: no `SLOT_*` / `PAPER_*` / `LIVE_*` env keys exist in `.env` (only `SLOT_REQUOTE_MAX_DRIFT_PCT`, `config.py:128`). Per-slot enable/geometry flags: `HTF_L2_ENABLED`, `HTF_L2_SL_PCT`, `HTF_L2_TP_PCT`, `HTF_L2_QUIET_BLOCK_ENABLED`, `HTF_L2_CROSS_BOOK_LOCK` (`config.py:86-105`); `VWAP_CROSS_ENABLED`, `VWAP_CROSS_SL_PCT`, `VWAP_CROSS_TP_PCT` (`config.py:111-113`). Global fee constants `config.py:144-151`. Donchian/TSM parameters are frozen module constants (`donchian_slot.py:48-67`, `tsm_slot.py:35-50`).

Per-slot state files:
- `trading_state_<slot_id>.json` — ledger (`positions`, `closed_trades`), written by `risk_manager.py` `_save_state` (~`:428-452`).
- `trading_state_<slot_id>_blocked.json` — rejection counters (`strategy_slot.py:90-92`, `bump_blocked` `:111-118`).
- `trading_state_<slot_id>_mode.json` — `{paper_mode, capital_pct, promoted_at, loss_cap_usdt, trade_amount_usdt, kelly_min_trades, killed_at}` (`strategy_slot.py:145-158`), read at boot by `_load_mode` (`:120-135`); only written by `set_live`/`set_paper`/`set_killed`.
- Bespoke sidecars are deliberately NOT prefixed `trading_state_` because the dashboard globs that prefix (`web_dashboard.py:290-306`; rationale `donchian_slot.py:36-39`): `donchian_slot_state.json`, `donchian_signal_{BTC,ETH}.json` (`donchian_slot.py:63-66`), `eth_tsm_28_signal.json` (`tsm_slot.py:48-49`).
- Era archive convention: `trading_state_SR_BOUNCE_era1.json` via `scripts/rotate_sr_bounce_era.sh:34`.

### 3.2 Paper vs live

- Flag: `slot.paper_mode` (`strategy_slot.py:40`), restored from the mode sidecar (`:126`), mirrored into `slot.risk.is_paper` by `_sync_risk_semantics` (`:137-143`). `RiskManager.__init__` initially sets `is_paper = state_file != "trading_state.json"` (`risk_manager.py:319-320`). `Config.MODE` (`config.py:131`) and the `.paper_main` sentinel (`bot.py:88-89`) govern the MAIN book only.
- Paper entry price: `_fresh_paper_entry_price` (`bot.py:49-70`) — WS tick if age ≤ `PAPER_PX_MAX_AGE_S = 10.0` (`bot.py:46`), else one REST ticker, else cycle-cached price tagged `age=-1.0`. Used at `bot.py:3438-3440` (generic), `:4942-4944` (Donchian), `:5013` (paper-main). Provenance persisted as `px_src`/`px_age_s` (`bot.py:3694-3697`).
- Paper exits: each cycle against the cycle `prices` map; SL/TP touch closes at current price, not the level (`bot.py:2998-3009`); trend-flip/adverse/time exits `:3011-3036`. Donchian paper exits at the daily eval (`bot.py:4916-4933`).
- Paper fee model: `risk_manager.py:805-819` — `fees = notional × (MAKER 0.01% + TAKER 0.06% + SLIPPAGE 0.05%)` = 0.12% round trip, subtracted from `pnl_usdt` (`:830-831`) and in `net_pnl` (`:841`). No price slippage is applied to the fill price. Duplicated for partial TP (`:957-962`) and paper-main (`bot.py:91-100`).
- Mode tagging: paper closes omit `mode` (`bot.py:4971`); live closes pass `mode="live"` (`bot.py:4998-4999`, `:4295-4296`, `:3635`).
- Live slot entry: `bot.py:3492-3676` — halts `:3495`, long-side block `:3502`, TSM lock `:3509`, stale levels `:3520-3532`, `exchange.open_long/open_short(...)` `:3538-3544`, PostOnly re-quote `:3550-3603`, fill price `:3607`, `slot.risk.open_position` `:3629-3633`, crumb close `:3646-3657`, `exchange.place_sl_tp` `:3654-3661`, `notify_entry` `:3663`.
- Live slot exit: `_close_slot_position` live arm `bot.py:4975-5008`. Reconcile ownership excludes paper slots: `_build_position_owners` `bot.py:503-521`, `_sync_exchange_closes` `:4142`.
- Donchian live path is a no-op: `bot.py:4886-4895` logs "LIVE but live execution is not implemented — no orders placed" once per UTC day and returns. Spec non-goal at `docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md:42,56`; test `tests/test_donchian_slot.py:545`.

### 3.3 Promotion / demotion / sentinels

All bot sentinels are processed in `_process_sentinels` (`bot.py:1421-1601`).

| Sentinel | Read at | Effect | Written by |
|---|---|---|---|
| `.promote_<slot_id>` | `bot.py:1553-1590` | JSON `{"capital_pct": …}` (default 0.10); flushes open paper positions as `promote_reset` (`:1571-1583`), `set_live()`, Telegram, file deleted | `scripts/auto_lifecycle.py:190,239,247` (job disabled); manual |
| `.demote_<slot_id>` | `bot.py:1592-1601` → `_demote_slot` `:4278-4302` | closes real positions at market, cancels orders, `set_paper()` | `auto_lifecycle.py:175,227`; manual |
| `.kill_<slot_id>` | `bot.py:1481-1539` | `set_killed()` persists `killed_at` (`:1493`); paper positions closed in-book (`:1503-1509`); live closed on exchange (`:1510-1525`) | `scripts/telegram_commander.py:291`, `mcp_server.py:454`, `auto_lifecycle.py:96` |
| `.pause_<slot_id>` | `bot.py:1541-1551` | `enabled=False`, auto-expires 24 h | `auto_lifecycle.py:120` |
| `.pause_trading` | `bot.py:1426-1471`, `:2870-2879`, `:4643` | global entry halt; exits still run | bot daily-loss halt `:1408-1418`, `_set_pause_sentinel` `:1268-1274`, `telegram_commander.py:301` |
| `.daily_loss_override` | `bot.py:273-292`, `:1430-1436` | on the PT date in the file, neutralizes a daily-loss pause | manual (on disk: `2026-06-30`, expired) |
| `.max_dd_halt` / `.clear_dd_halt` | `bot.py:1288-1347`, `:2877` | MAX-DD halt / clear latch | bot writes `:1329`; owner clears |
| `.halt_main_entries` | `bot.py:2170-2183` | halts main-book entries only | adjudicator `adjudicate.py:883-890`; manual |
| `.paper_main` | `bot.py:88-89`; also `adjudicate.py:369-372`, `web_dashboard.py:74`, `scripts/daily_report.py:15` | main book on paper; `pos.paper=True` (`risk_manager.py:54-60`) | owner (present, 8/26) |
| `.block_longs_<book>` | `bot.py:76-77`, `:3502` | blocks LONG entries for `main` or a slot_id | adjudicator `adjudicate.py:822-830`; owner (`.block_longs_main` present) |
| `.block_shorts_<book>` | `adjudicate.py:246,255,800` | never written (`watch_only` `:803-810`) | — |
| `.restart_bot` | `scripts/monitor_daemon.py:196` | monitor restarts bot | `auto_lifecycle.py:317` |
| `scripts/.halt_nightly_research` | `scripts/nightly_research.py:27` | halts nightly research | manual (absent) |

Automatic rails (non-sentinel):
- `should_auto_demote` (`strategy_slot.py:186-216`): era-scoped (rows with `closed_at >= promoted_at`) live net ≤ `loss_cap_usdt`, or negative live Kelly once `len(era) >= kelly_min_trades`; called after every live close via `_maybe_auto_demote` (`bot.py:4270-4276`, `:5003`).
- `is_killed` (`strategy_slot.py:223-234`): raw Kelly < 0 after ≥ 50 closed trades (paper included) → `is_active` False → no new entries (`bot.py:3045`), exits still serviced (`:2955-2957`). This is recomputed in memory each cycle; `set_killed()` is called only from the `.kill_` sentinel path (`bot.py:1493`), so `killed_at` is not persisted by the Kelly path (SR_BOUNCE sidecar shows `killed_at: null` despite the 9/2 neg-Kelly kill).
- Account-wide daily-loss halt `bot.py:1408-1418`; MAX-DD halt `:1288-1347`.
- Bespoke slots opt out with `loss_cap_usdt=-999.0, kelly_min_trades=10**9` (`bot.py:786-790, 809-812`) and are graded only by the adjudicator.
- `scripts/auto_lifecycle.py` iterates `strategy_factory_state.json` (`:83-107`), a March-era registry whose names do not match current slot ids; treat as legacy.

### 3.4 Kill lines, verdicts, adjudicator

- Registry: `EXPERIMENTS = {...}` at `/Users/jonaspenaso/Desktop/Phmex-S/scripts/lab_adjudicator/adjudicate.py:98-288` ("single source of truth", `:8`). 14 entries: `trail_arm_8`, `sizing_15`, `mr_bundle`, `eth_tsm_28`, `htf_l2`, `vwap_cross`, `main_gated`, `main_resize15`, `main_long_side`, `mr_long_side`, `main_short_side`, `mr_short_side`, `sr_bounce`, `sr_bounce_v2`.
- No fixed schema; each grader reads its own keys. Example (`adjudicate.py:281-287`):
  ```python
  "sr_bounce_v2": {"deployed_ts": _pt_ts(2026, 7, 30, 21, 0), "honest_since": 1785991620,
                   "verdict_n": 50, "era1_per_trade": -0.0158, "breakeven_wr": 0.405}
  ```
  Common keys: `deployed_ts`/`registered_ts` (`_pt_ts` `:91-92`), `verdict_n`, `breakeven_wr`, `kill_net_usd`, `sentinel`, `watch_only`, `require_live_mode`.
- Grading: one `grade_*` function per experiment (`:401-1052`). E.g. `grade_sr_bounce_v2` (`:997-1052`): filter `closed_at >= deployed_ts and opened_at >= honest_since`, sum `net_pnl` as-is (`:1001-1004`); at `n >= verdict_n`: `net <= 0 → "KILL"` else `"PASS-ELIGIBLE"`, otherwise `WATCH`. `grade_htf_l2` (`:656-722`) era-filters by `promoted_at` from the mode sidecar.
- Graders that write sentinels: `grade_side_line` → `.block_longs_*` (`:822-830`); `grade_main_resize15` → `.halt_main_entries` (`:883-890`). Slot graders never write; the slot's rails or the owner act on a KILL.
- Reporting: `build_digest` (`:1141-1198`), `main` (`:1200-1224`) logs to `~/Library/Logs/Phmex-S/lab_adjudicator.log` (`:79-80`) and with `--telegram` sends via `st2_lab.notify.telegram_alert` (`:1220-1223`). Runner `scripts/lab_adjudicator/nightly.py:16-24` (adjudicate + `drift_watchdog`), launchd `com.phmex.lab-adjudicator` daily 6:00 AM (currently unloaded). Tests: `tests/test_lab_adjudicator.py`.

### 3.5 Specs in `docs/superpowers/specs/` (46 files; slot-relevant ones)

- `2026-03-21-top1-multi-strategy-design.md` — origin of the slot architecture.
- `2026-06-12-live-slot-execution-design.md` — paper → live: `.promote_`, PostOnly entries, exchange-resting SL/TP, reconcile ownership, auto-demote at −$5 / neg-Kelly@10, `.demote_` rollback (lines 43-118).
- `2026-07-16-donchian-ensemble-slot-design.md` — the bespoke template: frozen rules, pure module + `_evaluate_*`, sidecar naming, adjudicator-graded kill criteria, non-goals incl. no live orders.
- `2026-07-28-sr-bounce-design.md` — generic-path pattern: `STRATEGIES` key + `StrategySlot(..., paper_mode=True, trade_amount_usdt=5.0)`, backtest kill-gate first, adjudicator lines registered the day it ships (§4).
- `2026-07-30-sr-bounce-v2-fixed-geometry-prereg.md` — pre-registration format for a new era: what changes, era hygiene, frozen verdict line, anti-fishing clause, prior.
- Research pre-regs: `2026-07-29-sr-bounce-htf-rescan-prereg.md`, `2026-07-29-sr-bounce-snapshot-mining-prereg.md`, `2026-08-01-mr-universe-ranginess-scan-prereg.md`, `2026-09-03-mr-edge-search-prereg.md`.
- ST2 lab: `2026-06-15-st2-recursive-improvement-lab-design.md`, `2026-06-19-…phase1…`, `2026-06-20-…phase2…`.

### 3.6 What it takes to add a NEW pre-registered paper slot

Pick the idiom:
- Generic (scalper-style signal on the scanner universe): write a function returning `TradeSignal(signal, reason, strength, sl_price=None, tp_price=None)` (`strategies.py:20-26`), add it to `STRATEGIES` (`strategies.py:1050-1060`), add a `StrategySlot(...)` to `bot.py:676-864`. You inherit the gate stack: `is_active` `bot.py:3045`, `can_enter` `:3054`, 0.80 strength floor `:3183`, OB gate `:3302-3322`, tape gate `:3327-3355`, `_slot_entries_blocked`, paper SL/TP/time exits. If the function needs `htf_df`/`flow`/`cache_key`, add a dispatch branch at `bot.py:3115-3170` (see `sr_bounce` `:3123-3136` and its `_fetch_sr_bounce_htf` `:966`).
- Bespoke (daily / slow-horizon, own execution logic — Donchian template):

1. New pure module `<name>_slot.py` mirroring `donchian_slot.py`: frozen constants (`:48-67`), `SLOT_IDS`/`SYMBOLS`, `STATE_FILE` and `SIGNAL_FILES` not prefixed `trading_state_` (`:36-39, 63-66`), pure signal math (`advance_day` `:132-189`, `run_history` `:192-206`, `advance_state` `:209-254`), atomic `load_state`/`save_state` (`:259-289`), replica series writer `append_signal_days` (`:292-321`). No bot imports, no network.
2. `bot.py`: import next to `import donchian_slot` (`:113-117`); `StrategySlot(slot_id="<ID>", strategy_name="<not_a_STRATEGIES_key>", timeframe="1d", max_positions=1, capital_pct=0.0, paper_mode=True, trade_amount_usdt=None, loss_cap_usdt=-999.0, kelly_min_trades=10**9, durable_trail_enabled=False)` in `self.slots` (or a `_build_<name>_slot()` gated by a `Config.<NAME>_ENABLED` flag, pattern `:921-951` / `:838-840`); runtime state init after the list (`:876-880`); `self._evaluate_<name>(prices)` added to `_evaluate_all_slots` (`:2927-2950`) in its own try/except; methods modeled on `_evaluate_donchian` (`:4799-4824`), `_donchian_daily_eval` (`:4826-4875`), `_donchian_adjust_position` (`:4877-4934`), `_donchian_open_paper` (`:4936-4964`).
3. `config.py` (optional): `<NAME>_ENABLED` and SL/TP env overrides (pattern `config.py:86-92, 111-113`).
4. State files written automatically: `trading_state_<ID>.json`, `trading_state_<ID>_blocked.json` (if `bump_blocked` used), `trading_state_<ID>_mode.json` (first written on promote/demote/kill), plus your own `<name>_slot_state.json` / `<name>_signal_<SYM>.json`.
5. Register the experiment: `EXPERIMENTS["<name>"]` at `adjudicate.py:98-288` with `deployed_ts=_pt_ts(...)`, `verdict_n`, kill-line values, a comment deriving any breakeven; state-file constants `:289-296`; `grade_<name>(slot_state, cfg)` (copy `grade_sr_bounce_v2` `:997-1052`, sum `net_pnl` as-is); add to the `results` list and a `_line_<name>` formatter in `build_digest` (`:1141-1198`); tests in `tests/test_lab_adjudicator.py`.
6. Pre-registration doc `docs/superpowers/specs/<date>-<name>-slot-design.md` in the 07-16 / 07-30 format (frozen rules, kill criteria, non-goals, rollback `.kill_<ID>`).
7. Reporting propagation (mandatory per `CLAUDE.md:15-19`): dashboard auto-discovers `trading_state_<ID>.json` (`web_dashboard.py:290-306`) and live status from mode sidecars (`:573-587`); `scripts/daily_report.py:99-133` picks up promoted slots; Telegram via `notifier.notify_paper_entry/exit` (`notifier.py:161,173`).
8. Tests: `tests/test_<name>_slot.py` — AST wiring test that the `StrategySlot` call carries the rails opt-out and the name is absent from `STRATEGIES` (`tests/test_donchian_slot.py:344-372`), sidecar-name test (`:375-381`), bare-bot orchestration with `object.__new__(botmod.Phmex2Bot)` + `FakeExchange` (`:388-421`), "live mode places no orders" (`:545`).
9. Deploy: not live until an audited restart (`CLAUDE.md:10-11`, `/pre-restart-audit`). Rollback = `touch .kill_<ID>` (paper-only, zero market risk).

Minimal bespoke module outline:
```python
# <name>_slot.py — pure: no bot imports, no network
SLOT_IDS = {"BTC/USDT:USDT": "<ID>_BTC"}; SYMBOLS = list(SLOT_IDS)
STATE_FILE = os.path.join(_DIR, "<name>_slot_state.json")   # NOT trading_state_*
SIGNAL_FILES = {sym: os.path.join(_DIR, f"<name>_signal_{sym.split('/')[0]}.json") for sym in SYMBOLS}
def complete_daily_bars(df, now_utc=None) -> (dates, closes)    # drop the forming UTC bar
def default_coin_state() -> dict                                # {"w": 0.0, "last_close_date": None, "last_eval_utc_date": None, ...}
def advance_day(state_bits, closes) -> (new_bits, w_new, info)  # the pure rule step
def advance_state(st, dates, closes) -> [info...]               # idempotent fold, reseed on gaps
def load_state(path=None) / save_state(state, path=None)        # tmp + os.replace, never raises
def append_signal_days(symbol, records, path=None)             # replica series for fidelity grading
```
```python
# bot.py — orchestration only
def _evaluate_<name>(self, prices):                 # from _evaluate_all_slots
    today = <mod>.utc_date_str()
    for symbol in <mod>.SYMBOLS:
        slot = self._slot_by_id(<mod>.SLOT_IDS[symbol])
        if slot is None or not slot.enabled: continue
        st = self._<name>_state.setdefault(symbol, <mod>.default_coin_state())
        if st.get("last_eval_utc_date") == today: continue
        try: self._<name>_daily_eval(slot, symbol, st, today, prices)
        except Exception: logger.error(..., exc_info=True)      # day stays unstamped → retry next cycle
def _<name>_daily_eval(self, slot, symbol, st, today, prices):
    df = self.exchange.get_ohlcv(symbol, "1d", limit=500); dates, closes = <mod>.complete_daily_bars(df)
    infos = <mod>.advance_state(st, dates, closes); <mod>.save_state(self._<name>_state)
    <mod>.append_signal_days(symbol, [...])
    if not slot.paper_mode: log "LIVE not implemented" once/day; return   # as bot.py:4886-4895
    if self._slot_entries_blocked() and would_increase_exposure: return
    ... self._close_slot_position(slot, symbol, pos, price, reason) / slot.risk.open_position(symbol, fresh_px, notional, side=..., atr=0.0, strategy="<name>")
    st["last_eval_utc_date"] = today; <mod>.save_state(...)
```

Not found / unverified: `check_position_conflict` (`strategy_slot.py:254-265`) has no non-test caller; no automatic writer of `killed_at` for the 50-trade Kelly kill.

---

## 4. Data-integrity backlog — status on HEAD

Source of the four items: `/Users/jonaspenaso/.claude/projects/-Users-jonaspenaso-Desktop/memory/project_bot_backlog_2026-09-07.md`. The reconciler tests were run: `python3 -m pytest tests/test_state_merge_reconciled.py tests/test_sync_close_fills.py tests/test_reconcile_phemex.py tests/test_mcp_paper_split.py -q` → `40 passed`.

### (a) Funding never recorded — PARTIALLY FIXED; reconciler half exercised, bot half not

- What HEAD adds: `scripts/reconcile_phemex.py` (517 lines) covers main + every `trading_state_<slot>.json` (`ledger_files()` `:229-238`; slot rows only when `mode=="live"`, `is_real_row()` `:241-246`), fetches `fetch_funding_history` per symbol (`fetch_funding_rows` `:260`), attributes each settlement to the row whose (opened_at, closed_at] contains it (`attribute_funding` `:209`), and with `--apply` writes `funding_usdt` / `funding_source="phemex_reconcile"` / `funding_reconciled_at` and recomputes `net_pnl = gross − fees − funding` (`_patch_closed_rows` `:352-373`). Funding is stamped on every real row, zero included (`build_patches` `:315`). Atomic per-file apply with inode/mtime/size guard and 5 retries (`apply_patches` `:386-422`).
- `risk_manager.py:310-315, 389-418` add `RECONCILED_FIELDS` and `_merge_reconciled()`, called at the top of `_save_state_locked()` (`:426-427`) under `self._state_lock` (`:332`) so a bot save re-reads reconciler-patched fields instead of clobbering them.
- `scripts/daily_report.py:57-60, 191, 235, 392` add a "Funding:" line.
- Still open: the bot close path writes `funding_usdt = 0.0  # placeholder` (`risk_manager.py:838`; `:986` for partial-TP rows). Funding only enters via the external 15-minute reconciler, so in-memory `net_pnl` and the daily-loss halt are funding-blind. Rows outside the 7-day `--lookback-days` default (`:431-435`) or the ~40-day Phemex fill floor are never stamped.
- Evidence it ran: `com.phmex.reconcile` (`StartInterval 900`, `--apply`) ran until 9/9 7:49 PM PT (`~/Library/Logs/Phmex-S/reconcile.log` tail "Applied: 0 rows"). `trading_state_5m_mean_revert.json` has 4 live rows stamped `funding_source: phemex_reconcile` (reconciled 9/7 8:59 PM and 9/8 5:08 PM PT), one nonzero: ETH short closed 9/4 5:20 PM PT, `funding_usdt = −0.00175251`. Those patches survived only because that file's last writer was the reconciler (slot went paper 9/8 6:28 PM and never saved again) — the bot-side merge never ran. `reports/2026-09-07.md`…`09-09.md` line 14 show `Funding: $+0.0000`.
- Tests: `tests/test_reconcile_phemex.py` (23), `tests/test_state_merge_reconciled.py` (5).

### (b) Fee capture inconsistent — PARTIALLY FIXED; bot.py half unexercised

- `8d5db08` adds `_close_fills_summary()` `bot.py:455-497`: sums fees across all post-entry reduce-side fills (skips funding rows `tradeType "4"` / `action "13"`, skips same-side re-entries, VWAPs the exit); called from `_sync_exchange_closes` `bot.py:4188-4192`. Zero result still falls back to `_estimate_live_fees` + `fees_pending` (`risk_manager.py:824-827`). Crumb closes now pass the real exit-leg fee: `bot.py:2689-2690` (main) and `:3646-3647` (slot) via `extract_order_fee`.
- Reconciler patches `fees_usdt` when |local − phemex| > $0.01, only for complete round trips or a runner row's exit leg (`build_patches` `:282-323`). Exercised: 2 live 5m_MR rows carry `fees_source: phemex_reconcile` (ETH 9/1 $0.1015, XRP 9/4 $0.103).
- Still open: the three `min_margin_skip` rows from the backlog (5m_MR ledger idx 35/39/43 = XRP 7/26 1:41 PM, XRP 8/3 1:03 PM, SOL 8/19 10:03 PM PT; `fees` 0.105/0.21/0.105, `fees_pending: True`) are outside any reconcilable window and stay estimates. No fee-tier logic change; the fix is "reconciler overwrites with exact". `trading_state.json` main still has 247 rows `fees_pending: True` (182 of them already carry `fees_source` — the pending flag is never cleared; 65 never reconciled).
- Tests: `tests/test_sync_close_fills.py` (4) + reconciler fee tests. No test covers the crumb-close call sites.

### (c) MCP under-reports — STILL OPEN

`mcp_server.py:36` `STATE_FILE = trading_state.json`; `_read_state()` `:71-76` reads only that file; `phmex_open_positions()` `:215-233` iterates that file's `positions` only — slot positions invisible. `phmex_status()` `:192` uses `_today_utc_start()` (`:133-135`) and `:196-197` sums `pnl_usdt` (gross). `phmex_pnl` sums `pnl_usdt` (`:292`) despite its docstring saying net. None of the six 9/7 commits touch `mcp_server.py`. `tests/test_mcp_paper_split.py` asserts the current UTC/gross behaviour.

### (d) Reject 11082 counted as miss — STILL OPEN

`grep -rn 11082 --include=*.py` returns nothing. `exchange.py:479-481` is the catch-all `except Exception as e: logger.warning(f"[FILL MISS] {symbol} — limit order failed: {e}, skipping entry")`; `bot.py:3599` `slot.bump_blocked("requote_miss")` fires on any falsy order. No error-code bucket, no test.

### Hygiene items (all still open)

- `signal.alarm(180)` watchdog: armed `bot.py:1243`, cancelled after sleep `:1247`; rotated logs show `[WATCHDOG]` firings 8/27–9/5.
- `[SLOT]` summary skipped during REGIME pause: `bot.py:2125-2139` returns before the summary loop at `:2797-2801`.
- Paper-main loss streak sends a real ban-mode alert: `_close_paper_main` `bot.py:5056` → `_set_cooldown_if_loss` → `notifier.notify_ban_mode(30)` `bot.py:4073`, no paper gate.
- Overwatch `balance_anomaly` vs stale `peak_balance`: `scripts/overwatch.py:401-424` (moot while unloaded).
- Dashboard blotter chips blend live+paper WR: `web_dashboard.py:1926-1963`.
- SR_BOUNCE killed but evaluated every cycle: registered unconditionally `bot.py:856-868`; `strategy_slot.py:232` emits the neg-Kelly debug line each cycle (3,868 lines in `logs/bot.log` 9/7 10:12 PM → 9/9 7:50 PM PT).

Summary table:

| Bug | HEAD status | Exercised live? |
|---|---|---|
| (a) funding | Partially fixed (reconciler + merge-on-save); bot close path still writes 0.0 | Reconciler yes (4 rows, 1 nonzero); bot merge no |
| (b) fees | Partially fixed (fill-sum, crumb real fee, reconciler exact patch); old rows stay estimates | Reconciler yes (2 rows); bot.py no |
| (c) MCP | Open | n/a |
| (d) 11082 | Open | n/a |

---

## 5. Trading records on file (computed from rows)

Scripts: `/private/tmp/claude-501/-Users-jonaspenaso-Desktop/ae940530-2b50-4adf-95cd-95ffdbd3a915/scratchpad/{inspect_structure,compute_books,xchecks,reconstruct_882,verify_882}.py`.

Structure: every `trading_state*.json` has `peak_balance`, `closed_trades`, `trade_results`, `positions`. Row fields: `symbol, side, entry, exit, pnl_usdt, pnl_pct, fees_usdt, funding_usdt, net_pnl, reason, strategy, opened_at, closed_at`, optional `mode` (`"live"`/`"paper"`), `fees_pending`, `fees_source`, `entry_snapshot.slot`. No file stores a PnL total; the only summary field is `peak_balance` (a balance high-water mark, not derivable from rows).

Conventions (`risk_manager.py:794-860`): `net_pnl = gross − fees_usdt − funding_usdt` (`:840`). Live rows keep `pnl_usdt` gross (`:828-831`); paper books (`is_paper` = state file ≠ `trading_state.json`, `:319`) subtract fees from `pnl_usdt` (`:831`), so on paper rows `pnl_usdt == net_pnl`. "Net" below = `net_pnl` if present else `pnl_usdt` (rows lacking `net_pnl` are fee-blind legacy rows). Wins = net > 0.

| File | Book / mode | n | Net | W / L / 0 | WR | First → last close (PT) |
|---|---|---|---|---|---|---|
| `trading_state.json` | MAIN, all rows | 871 (555 with `net_pnl`, 316 fee-blind) | −90.8812 | 408/423/40 | 46.8% | 3/13/2026 12:01 AM → 9/9/2026 6:41 PM |
|  | `mode` absent = real money | 837 | −70.2450 | 390/407/40 | 46.6% | 3/13 12:01 AM → 8/26 8:19 PM |
|  | `mode=="paper"` (`.paper_main` era, `bot.py:5046-5067`) | 34 | −20.6362 | 18/16/0 | 52.9% | 8/26 9:45 PM → 9/9 6:41 PM |
| `trading_state_v8_245trades.json` | archive; 245/245 rows identical to first 245 of main — EXCLUDE | 245 | −23.4653 (fee-blind) | 88/145/12 | 35.9% | 3/13 → 3/20 |
| `trading_state_5m_mean_revert.json` | all | 54 | +3.5947 | 25/29/0 | 46.3% | 3/28 2:37 PM → 9/7 3:29 PM |
|  | `mode=="live"` (real) | 34 | +1.0940 (gross 3.9312, fees 2.8389, funding −0.0018) | 15/19/0 | 44.1% | 6/18 8:09 PM → 9/7 3:29 PM |
|  | paper era (`mode` absent) | 20 | +2.5007 | 10/10/0 | 50.0% | 3/28 → 6/11 |
| `trading_state_5m_narrow.json` | paper | 51 | −27.5833 | 10/41/0 | 19.6% | 4/20 4:30 AM → 6/11 9:49 AM |
| `trading_state_5m_liq_cascade.json` | paper | 50 | −5.1650 | 17/33/0 | 34.0% | 3/26 2:34 AM → 5/27 4:49 AM |
| `trading_state_5m_scalp.json` | empty | 0 | — | — | — | — |
| `trading_state_DONCHIAN_BTC.json` | paper (`bot.py:807`) | 12 | +4.6984 | 6/6/0 | 50.0% | 7/21 5:00 PM → 9/7 5:00 PM |
| `trading_state_DONCHIAN_ETH.json` | paper (`bot.py:822`) | 18 | +4.2338 | 12/6/0 | 66.7% | 7/18 5:00 PM → 9/9 5:01 PM |
| `trading_state_ETH_TSM_28.json` | paper, retired (`killed_at` 7/28) | 3 | +0.7493 | 3/0/0 | 100% | 7/13 5:00 PM → 7/28 1:48 PM |
| `trading_state_HTF_L2.json` | all | 43 | −10.9101 | 12/31/0 | 27.9% | 7/20 8:05 PM → 7/31 8:22 AM |
|  | `mode=="live"` (real) | 15 | −9.6972 | 4/11/0 | 26.7% | 7/20 9:09 PM → 7/27 6:28 AM |
|  | paper | 28 | −1.2129 | 8/20/0 | 28.6% | 7/20 → 7/31 |
| `trading_state_HTF_L2_PAPER.json` | orphan sidecar; all 3 rows duplicate HTF_L2 — EXCLUDE | 3 | +0.5252 | — | — | 7/20 |
| `trading_state_SR_BOUNCE.json` | paper (v2 era) | 136 | −0.4807 | 67/69/0 | 49.3% | 7/31 4:13 AM → 9/2 2:45 AM |
| `trading_state_SR_BOUNCE_era1.json` | paper archive | 50 | −0.7915 | 23/27/0 | 46.0% | 7/29 10:11 AM → 7/30 8:20 PM |
| `trading_state_ST2.0.json` | all | 51 | −9.4499 | 21/29/1 | 41.2% | 6/13 3:46 PM → 6/29 5:03 AM |
|  | `mode=="live"` (real; 19 rows `fees_pending`, fees total only 0.1779) | 35 | −4.7102 | 15/19/1 | 42.9% | 6/13 → 6/29 |
|  | paper | 16 | −4.7397 | 6/10/0 | 37.5% | 6/15 |
| `trading_state_VWAP_CROSS.json` | paper | 51 | −3.7137 | 20/31/0 | 39.2% | 7/21 1:32 AM → 7/27 4:00 PM |

Mode sidecars on disk all read `paper_mode: true` (5m_mean_revert `promoted_at` 6/11, demoted 9/8; HTF_L2 `killed_at` 7/31; ETH_TSM_28 `killed_at` 7/28; SR_BOUNCE `killed_at: null`; ST2.0 `promoted_at` 6/15).

Real-money reconstruction vs `docs/2026-09-09-winddown.md:11-12` ("−$82.94 on 882 trades, 48.3% WR"; 90d/30d −$22.41 / −$14.26): main `mode≠paper` (837) + 5m_MR live (34) + HTF_L2 live (15) + HTF_L2_PAPER live (2) + ST2.0 live (35) = 923 rows, net −82.9351, wins 426 / losses 456 / zeros 41 → 426/882 = 48.30%. So the doc's "882" is non-zero-PnL trades; the full real-row count is 923. 90-day net −22.4130 (n=320) and 30-day −14.2579 (n=55) reproduce the doc. Discrepancy: that reconstruction double-counts HTF_L2_PAPER's 2 duplicate live rows; de-duplicated it is 921 rows, net −83.5584, WR 424/880 = 48.2%. The doc's "de-dup estimate ≈ −$107" (fee-blind adjustment) could not be reproduced from the files.

MCP cross-check: `phmex_pnl(all)` returned trades=837, pnl −43.4965, WR 0.477, paper 34 / −14.8762 — it sums gross `pnl_usdt` (`mcp_server.py:292`) and so differs from net (−70.2450) by recorded fees (26.75).

Open positions still in ledgers (no exchange exposure per doc line 16; exchange not queried here):
1. `trading_state.json` → `1000SHIB/USDT:USDT` short, entry 0.005194, margin 15.0, `paper: true`, opened 9/9 7:22:57 PM PT.
2. `trading_state_DONCHIAN_BTC.json` → BTC long, margin 30.0145, opened 9/7 5:00:18 PM PT, row `paper: false`.
3. `trading_state_DONCHIAN_ETH.json` → ETH long, margin 30.4831, opened 9/9 5:01:19 PM PT, row `paper: false`.
The two Donchian rows carry `paper: false` although the slots are hard-coded paper and were opened by `_donchian_open_paper` (`bot.py:4936`) — that path does not set the position-level `paper` flag. `donchian_slot_state.json`: BTC `w`=0.3001, ETH `w`=0.3048, `last_close_date` 2026-09-09.

Sentinels present: `.paper_main` (8/26), `.block_longs_main` (8/12), `.daily_loss_override` = "2026-06-30" (expired). `.halt_main_entries` absent.

---

## 6. Market-data assets for research

Sizes from `du -sh`: repo 3.9G; `logs/` 2.4G (`logs/l2_ticks` 1.9G, `flow_capture.jsonl` 316 MB); `reports/cache` 386M; `scripts/research` 646M; `backtest_data{,_june,_may}` 7.5M / 18M / 5.9M; `~/Desktop/Phmex-S-archive` 1.8G; `~/Library/Logs/Phmex-S` 68M (launchd logs only, no captures). `Phmex-S/data/` does not exist.

### 6.1 Wind-down archive `~/Desktop/Phmex-S-archive/`
`phmex-s-market-data-2026-09-09.tar.gz` = 1,974,725,327 bytes (1.97 GB decimal; `du` shows 1.8G), SHA-256 matches the `.sha256` beside it, 470 entries (matches `docs/2026-09-09-winddown.md:22`): 461 files under `logs/l2_ticks/{ARB,BTC,ETH,INJ}_USDT_USDT/`, plus `flow_capture.jsonl` (315,869,699 B), `entry_snapshots.jsonl` (780,293 B), `gotAway.jsonl` (767,705 B), `shadow_adverse.jsonl` (90,098 B). Uncompressed 2,331,577,887 B. Originals still on disk; no copy exists off this Mac yet. Not archived: `shadow_trail.jsonl`, `mr_gate_blocks.jsonl`.

### 6.2 L2 tick recorder `logs/l2_ticks/` (1.9G, 461 files)
- Writer `scripts/l2_tick_recorder.py:60`; symbols BTC, ETH, INJ, ARB (`:39-44`); `DEPTH = 5` (`:45`); `RETENTION_DAYS = 60` (`:47`); 5 GB cap (`:55`). Public ccxt.pro `watch_order_book` + `watch_trades`.
- Layout `<SYM>/<YYYY-MM-DD>.jsonl[.gz]` (book) and `<SYM>/trades-<date>.jsonl[.gz]`, UTC day files. Book schema `{ts, et, n, sym, b:[[px,sz]×5], a:[[px,sz]×5]}`; trades `{ts, et, sym, px, sz, side}`.
- Range 2026-07-13 → 2026-09-10 02:49Z (58 book days per symbol; 7/31–8/1 missing for all four; INJ trades also missing 8/21). Earlier days purged by retention (recorder started 6/11 per `~/Library/Logs/Phmex-S/l2_recorder_error.log` line 1).
- Sizes: BTC 875M, ETH 781M, ARB 209M, INJ 56M. Row counts read: `BTC/2026-07-13.jsonl.gz` 838,874; `BTC/2026-09-10.jsonl` 136,917; `BTC/trades-2026-07-13.jsonl.gz` 43,770; `ARB/2026-07-25.jsonl.gz` 7,725.
- Caveat: `INJ/2026-09-10.jsonl` has 170 rows with empty `b`/`a` and a stale `et` (~8/20); INJ feed dead at the tail.
- Readers: `scripts/research/execution-2026-06-13/*.py`, `scripts/research/booktape-2026-06-13/build_features.py:22`, `scripts/l2x_lab/queue_at_placement.py:34`.

### 6.3 Bot-written JSONL captures `logs/`

| File | Bytes / rows | Range (UTC) | Symbols | Writer | Readers |
|---|---|---|---|---|---|
| `flow_capture.jsonl` | 315,869,699 / 918,051 | 2026-05-11 03:40Z → 2026-09-10 02:49Z | 96 | `_log_flow_snapshot` `bot.py:3781` (write `:3824`), per symbol per scan (`:2282`) | `scripts/flow_replay.py:64`, `flow_capture_sanity.py:22`, `calibrate_flow.py:91` |
| `entry_snapshots.jsonl` | 782,277 / 1,374 (incl. 4 test rows, §2.3) | 2026-04-07 03:35Z → (real) 2026-09-10 | 47 | `_log_entry_snapshot` `bot.py:3996` (write `:4047`) | `scripts/slot_lab/mr_edge_signal_table.py:1217`, `missed_fill_counterfactual.py:28` |
| `gotAway.jsonl` | 767,705 / 1,517 | 2026-04-11 22:35Z → 2026-09-10 01:27Z | 39 | `_log_gotaway` `bot.py:3748` | `gate_quantify.py:141`, `gate_block_counterfactual.py` |
| `shadow_trail.jsonl` | 215,055 / 895 | 2026-06-13 → 2026-09-10 | 28 | `_log_shadow_trail` `bot.py:3926` | none found |
| `shadow_adverse.jsonl` | 90,098 / 392 | 2026-06-19 → 2026-09-10 | 22 | `_record_shadow_adverse` `bot.py:4118` | tests only |
| `mr_gate_blocks.jsonl` | 2,180 / 18 | 8/24 → 9/8 (local ts) | — | `scripts/slot_lab/mr_gate_block_archiver.py:77` | — |

Schemas: flow rows `ts, symbol, price, ob{imbalance, bid_walls, ask_walls, spread_pct, bid_depth_usdt, ask_depth_usdt, illiquid}, flow{buy_ratio, cvd_slope, divergence, large_trade_bias, trade_count}`; entry snapshots add `direction, slot, strategy, strength, confidence, regime, htf_adx, rsi, rsi_fast, ema21_dist_pct, ema50_dist_pct, vwap_dist_pct`.

### 6.4 OHLCV CSV sets (Phemex via `fetch_history.py:9-11`; schema `timestamp,open,high,low,close,volume`)

| Dir | Symbols / files | TFs | Range (BTC file) | Rows (BTC) | Writer / readers |
|---|---|---|---|---|---|
| `backtest_data/` (7.5M) | BNB BTC ETH SOL XRP / 10 | 5m, 1h | 5m 2026-01-10 04:10 → 2026-04-10 04:00; 1h same span | 25,919 / 2,159 | `fetch_history.py`; `backtester.py:98,102` |
| `backtest_data_may/` (5.9M) | 16 symbols / 32 | 5m, 1h | 2026-05-08 22:15 → 2026-05-30 22:05 | 6,335 / 527 | `scripts/fetch_flow_window.py:29`; `cohort_gate_sweep.py:42` |
| `backtest_data_june/` (18M) | 22 symbols / 44 | 5m, 1h | 2026-05-20 03:50Z → 2026-07-04 03:40Z | 12,959 / 1,079 | reader `scripts/slot_lab/mr_edge_fetch.py:40` |

### 6.5 Pickle OHLCV caches `reports/cache/`
- `*_{1m,5m}_90d.pkl` (142M): 20 symbols × 1m/5m, rolling 90 d at fetch (BTC 1m 2026-04-01 → 2026-06-30, 129,599 rows; 5m 25,919). Writer `scripts/slot_lab/mean_revert_replay.py:277-289`; readers `mr_variant_grid.py:67`, `mr_expansion_replay.py:67`.
- `mr_edge_20260601_20260903/` (244M): 35 symbols × 1m/5m/1h pkl (105) + 35 `funding_*.json` (8h, 282 rows/symbol) + `manifest.json` (all complete, run 9/4 08:02–08:44Z). Range 2026-06-01 → 2026-09-02 23:59Z; BTC 1m 135,360 rows. 10 symbols end early (BICO 6/30, DEXE 7/31, EIGEN/GIGGLE/WIF/ZAMA 8/7, WLD 8/11, ALLO 8/14, INJ 8/18). Writer `scripts/slot_lab/mr_edge_fetch.py` (layout `:10-16`); readers `mr_edge_signal_table.py:1210`, `mr_edge_screen.py`. This is the highest-value Phemex OHLCV set.
- `reports/cache_l2x_drift/` (4.4M): 274 per-entry 1m windows (`scripts/l2x_lab/postentry_drift.py:50,117`).
- `reports/mr_edge_2026/` (6.0M): derived signal tables (`signals.json` 6.1 MB), not raw data.

### 6.6 Research-directory datasets `scripts/research/` (Phemex unless noted)

| Dir | Size | Coverage | Range | Rows |
|---|---|---|---|---|
| `liqcascade-2026-06-13/data` (Binance.US, `fetch_data.py:16`) | 383M | 15 symbols, 5m + 1h | 2021-01-01 → 2026-06-13 | BTC 5m 572,825; 1h 47,738 |
| `htf-rigorous-2026-06-13/data` (Binance.US + gateio) | 19M | 53 symbols 1d, 15 × 4h | 2021-01-01 → 2026-06-13 | BTC 4h 11,937; 1d 1,990 |
| `pairs-2026-06-13/data` (Binance.US) | 26M | 28 symbols 1d + 4h | 2021 → 6/13 | — |
| `pairs-verify-2026-06-13/data` (Binance.US) | 4.3M | 37 symbols 1d | 2021 → 6/13 | 1,990 |
| `gate_quantify_2026-06-13/klines5m` | 25M | 27 symbols 5m | 2026-04-14 → 2026-06-13 | 17,279 |
| `higher-tf-2026-06-13/data` | 3.9M | 10 symbols 1h + 4h | 2025-11-15 → 2026-06-13 | 5,057 / 1,264 |
| `volfade-verify-2026-06-13/` | 6.5M | 14 × 1h | 2025-06-13 → 2026-06-13 | 8,759 |
| `sr-bounce-scan/data` | 24M | 10 symbols 5m + 1h | 2026-04-29 → 2026-07-28 | 25,945 |
| `sr-bounce-htf-scan/data` | 37M | 10 symbols 15m/1h/4h/1d | 2025-06-25 → 2026-07-30 | 15m 38,437 |
| `mr-universe-scan-2026-08-01/cache` | 61M | 19 symbols, 38 parquet `_{5m,1h}_400d` | 2025-06-27 → 2026-08-01 | 5m 115,199; 1h 9,599 |
| `funding-2026-06-13/data` | 4.8M | 17 symbols funding 8h + 1h OHLCV | 2025-12-01 → 2026-06-13 | 585 / 4,673 |
| `funding-spread-kill-test-2026-07-15/raw_funding.json` | 141 KB | BTC/ETH linear + inverse | — | 1,300 each |
| `microstructure-2026-06-13/…ohlcv1h_binanceus.json` | 25M | 10 spot 1h | 2021 → 6/13 | 47,738 |
| `btc-tsm-kill-test-2026-07-15/data_phemex/BTC_1d.csv` | 112 KB | BTC 1d | 2022-11-04 → 2026-07-15 | 1,350 |
| `booktape-2026-06-13/out/*_features.csv` | 6.5M | ARB BTC ETH INJ derived L2 features (6/12–6/13) | — | 6,688 |
| `fee-truth-2026-06-11/raw_fills.json` | 90 KB | real fills | — | — |

No sqlite/feather/npz/h5 anywhere; parquet only in `mr-universe-scan-2026-08-01/cache`.

Data-quality flags: INJ L2 tail is dead; 10/35 mr_edge symbols stop before 9/2; `entry_snapshots.jsonl` carries 4 synthetic rows from this session's pytest (§2.3).

---

## 7. Infrastructure inventory — parked launchd jobs

Folder `/Users/jonaspenaso/Library/LaunchAgents/disabled/phmex-winddown-2026-09-09/` holds 22 plists (21 `com.phmex.*` + `com.phmexs.monitor`), matching `docs/2026-09-09-winddown.md:23`. All use `WorkingDirectory=/Users/jonaspenaso/Desktop/Phmex-S` and log to `~/Library/Logs/Phmex-S/`. Schedules are Mac-local wall time (currently PDT). Nothing phmex is loaded now except `com.phmex.web-dashboard` (`launchctl list | grep -i phmex` → `82621 0 com.phmex.web-dashboard`, plist in the live `~/Library/LaunchAgents/`); no `Python main.py`, overwatch, monitor_daemon, telegram_commander or l2_tick process is running.

| Label | Schedule | Script | Purpose | Effect if re-enabled | Risk |
|---|---|---|---|---|---|
| com.phmex.overwatch | every 4 h (12/4/8 AM, 12/4/8 PM), RunAtLoad | `scripts/overwatch.py` | health monitor + Telegram + fix specs | `check_process_alive()` `:189-207` sees no bot and runs `Python main.py` | STARTS THE BOT on load |
| com.phmexs.monitor | hourly, RunAtLoad | `scripts/monitor_daemon.py` | hourly health/trade digest | if `.restart_bot` exists (`:196-216`) kill -9 + relaunch `main.py`; else hourly "BOT IS DOWN" alert (`:223`) | restarts bot conditionally |
| com.phmex.auto-lifecycle | every 4 h, RunAtLoad | `scripts/auto_lifecycle.py` | legacy kill/promote/decay scanner | writes `.kill_*`/`.pause_*`/`.promote_*`/`.demote_*`/`.restart_bot` (`:190-191, 317-319`); can edit `.env` (`:337-339`) | can promote a slot to live / trigger restart |
| com.phmex.telegram-commander | KeepAlive daemon | `scripts/telegram_commander.py` | phone control via sentinels | `/kill` `.kill_<slot>`, `/pause`, `/resume`; `/overwatch` runs overwatch.py (`:327-329`) → starts bot | can start bot via `/overwatch` |
| com.phmex.reconcile | every 15 min, RunAtLoad | `scripts/reconcile_phemex.py --apply` | fills + funding reconciler | authenticated Phemex reads; patches `trading_state*.json` in place (`:386-419`) | writes ledgers; no orders |
| com.phmex.halt-watcher | every 5 min | `scripts/halt_watcher.py` | auto-clears `.pause_trading` after cooldown | deletes `.pause_trading` (`:65`) | removes a safety pause |
| com.phmex.auto-backup | hourly at :17 | `scripts/auto_backup.py` | git add/commit/push | `git push -q origin main` (`:46-61`) | GIT PUSH |
| com.phmex.icloud-backup | daily 5:13 AM | `scripts/icloud_backup.py` | rsync non-git data to iCloud (excludes `.env`, `l2_ticks`) | data copy | low |
| com.phmex.l2-recorder | KeepAlive daemon | `scripts/l2_tick_recorder.py` | public WS L2 + tape recorder | resumes writing `logs/l2_ticks/` | disk growth only |
| com.phmex.daily-report | 6 AM, 12 PM, 6 PM, 11:55 PM | `scripts/daily_report.py` | report → `reports/` + Telegram | Telegram | low |
| com.phmex.report-catchup | every 30 min, RunAtLoad | `scripts/report_catchup.py` | re-runs report if stale | Telegram | low |
| com.phmex.code-health | daily 7:30 AM | `scripts/code_health.py` | pytest + lint → Telegram | would WARN "no entry in 48h" | low (note: pytest side effect §2.3 applies) |
| com.phmex.flow-sanity | daily 6:00 AM | `scripts/flow_capture_sanity.py` | flow_capture health | would alert degradation daily (`:117`) | noise |
| com.phmex.forensics | Sunday 8:00 PM | `scripts/weekly_forensics.py` | weekly pattern report | Telegram | low |
| com.phmex.weekly-sweep | Sunday 8:00 PM | `scripts/weekly_sweep.py` | backtester param sweep | public OHLCV fetch, Telegram | low |
| com.phmex.lab-adjudicator | daily 6:00 AM | `scripts/lab_adjudicator/nightly.py` | grades EXPERIMENTS + drift watchdog | may write `.block_longs_*` / `.halt_main_entries` (`adjudicate.py:822-827, 883-887`) | safety-direction sentinels |
| com.phmex.mr-gate-archiver | every 6 h | `scripts/slot_lab/mr_gate_block_archiver.py` | archives gate-block log lines | log scrape | low |
| com.phmex.mr-watch | every 5 h | `scripts/mr_watch.py` | 5m_MR digest | Telegram | low |
| com.phmex.nightly-research | daily 3:00 AM | `scripts/nightly_research.py` | headless `claude -p` research (`:75-76`) | spends API usage nightly; kill file `scripts/.halt_nightly_research` absent | cost |
| com.phmex.st2-lab | daily 4:30 AM | `scripts/st2_lab/loop.py --iterations 5` | ST2 param lab, proposals only | writes `docs/fix-proposals/` | low |
| com.phmex.proposals-digest | days 3,6,…,30 at 5:00 AM | `scripts/proposals_digest.py` | verifies proposals, Telegram | read-only | low |

Restore caveat: the doc's restore loop (`docs/2026-09-09-winddown.md:33`) globs `com.phmex*.plist`, which also matches `com.phmexs.monitor`; bootstrapping overwatch alone auto-starts `main.py` on load regardless of the manual start line. Older retired plists remain in the parent `disabled/` folder (com.phmex.floor-watcher, com.phmex.sprint-checkpoint, com.phmex.st2-watch) and are not part of the 22.

---

## 8. Things worth knowing before designing on this framework

1. The framework is complete for paper slots: register a `StrategySlot`, an `EXPERIMENTS` entry, a spec, and tests; the dashboard, daily report, and adjudicator pick it up from `trading_state_<ID>.json` and the mode sidecar. Live promotion is a JSON sentinel; auto-demote rails are era-scoped on `promoted_at`.
2. Only generic (`STRATEGIES`-keyed) slots have a real live execution path; Donchian/TSM bespoke slots are paper-only by construction (`bot.py:4886-4895`).
3. Funding and exact fees enter ledgers only through the external reconciler; the bot's own close path is still funding-blind (`risk_manager.py:838`). A restart from HEAD loads the unexercised merge-on-save and fill-sum code (40 tests pass), but the MCP and 11082 items are untouched.
4. Paper fills use the WS tick with a 0.12% flat fee and no price slippage; the record (memory `feedback_no_shadow_live_deploy`, `reference_edge_hunt_exhaustion`) says paper edges have not survived live.
5. Best research data: Phemex 35-symbol 1m/5m/1h + funding for 6/1→9/2 (`reports/cache/mr_edge_20260601_20260903/`), L2 book+tape for BTC/ETH/ARB/INJ 7/13→9/10, and 918k flow snapshots across 96 symbols 5/11→9/10. Longest histories are Binance.US (2021→6/13), not Phemex.
6. Real-money lifetime from the files: −82.94 on 923 rows (882 non-zero) with HTF_L2_PAPER duplicates included; −83.56 de-duplicated. Two Donchian paper positions and one paper-main position remain in ledgers with no exchange exposure.

---

## 9. Side effects of this audit

Nothing in the repo was edited or deleted by me, no bot process was started, no launchd job loaded, no orders placed. One unintended write happened as a consequence of running the test suite, which the brief permitted:

- What: 4 synthetic rows were appended to `/Users/jonaspenaso/Desktop/Phmex-S/logs/entry_snapshots.jsonl` (now 1,374 lines / 782,277 B; the wind-down archive copy is 780,293 B, so the delta is exactly these 4 rows, ~496 B each).
- Which rows: the last 4 lines of the file. Two carry `"ts": 1789441832` (9/14/2026 8:10:32 PM PT, from the `-x` run) and two carry `"ts": 1789441924` (9/14/2026 8:12:04 PM PT, from the full run). All four are `"symbol": "BTC/USDT:USDT", "direction": "short", "slot": "ST2.0", "strategy": "st2", "strength": 0.85, "confidence": 0, "price": 100.0`; one of each pair has `"ob": null`.
- Which test: `tests/test_entry_snapshot_ob.py:30-31` and `:44-45` call `bot._log_entry_snapshot("BTC/USDT:USDT", "short", "ST2.0", "st2", 0.85, 100.0, 0, ob, flow)` / `(…, None, flow)` on a bare bot without redirecting the output path.
- Why it reaches the real file: `bot.py:4047` opens the relative path `"logs/entry_snapshots.jsonl"` in append mode; pytest runs with the repo root as cwd, so the relative path resolves to the real capture. Other tests that touch bot writers redirect to `tmp_path` (e.g. `tests/test_live_slot.py:298`); this one does not.
- Blast radius: the file is gitignored (`.gitignore:5: logs/`), so `git status` is clean and nothing reached the remote. The archive tarball is unaffected. Any research reader of `entry_snapshots.jsonl` (`scripts/slot_lab/mr_edge_signal_table.py:1217`, `scripts/slot_lab/missed_fill_counterfactual.py:28`) would see 4 bogus ST2.0 rows at price 100.0 dated after the wind-down.
- Note this also means every past run of `com.phmex.code-health` (daily pytest) and every manual pytest run since that test was added has appended 2 such rows; the market-data agent's row count of 1,374 already includes those plus mine. A row-level filter (`price == 100.0 and slot == "ST2.0"`) identifies all of them.
- Not done (owner decision): removing the last 4 lines (e.g. `head -n -4`), and patching the test to monkeypatch the path or `chdir` to `tmp_path`.
