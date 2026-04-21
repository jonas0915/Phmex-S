# Recursive Improvement System — Phase 1 Design Spec

**Date:** 2026-04-02
**Status:** Proposed
**Goal:** Connect the measurement layer to the action layer. Bot auto-kills, auto-promotes, auto-rollbacks, and accepts phone commands — Jonas goes hands-off.
**Deploy After:** 2026-04-07 (Sentinel v11 5-day evaluation ends Apr 6 — deploying earlier confounds the A/B baseline with legacy_control slot)

## Decisions (From Brainstorming)

- **Autonomy level:** Full auto — bot acts within guardrails, notifies via Telegram
- **Parameter guardrails:** Moderate — ±25% max change/week, 30+ shadow trades, auto-rollback on 15%+ WR drop in 48 hrs
- **Promotion model:** Auto-promote at 10% capital, ramp after proving out. Kill switch from phone.
- **Slot model:** Additive with cap — max 2 live slots. Promotion bumps weakest if at cap.
- **Communication:** Sentinel files (filesystem-based IPC). No sockets, no shared memory.

## Components

### 1. Auto-Lifecycle Scanner (`scripts/auto_lifecycle.py`)

Scheduled every 4 hours via launchd. Single script handles kill, promote, decay, and rollback.

#### Kill Scan
Imports `recalibration.compute_metrics()` and `recalibration.kill_switch_check()`.

For each slot's `trading_state_{slot_id}.json`:
- Skip slots with 0 trades (no metrics to compute)
- Negative Kelly after 50+ trades → write `.kill_{slot_id}` sentinel, update `strategy_factory_state.json` stage to "killed", Telegram: "AUTO-KILL: {slot} — negative Kelly ({value}) after {N} trades"
- Win rate < 30% after 25+ trades → same action
- Edge decay > 30% (7d WR vs historical) → write `.pause_{slot_id}` sentinel (auto-expires 24 hrs), Telegram: "EDGE DECAY: {slot} — 7d WR {X}% vs historical {Y}% ({Z}% drop). Paused 24 hrs."

#### Promote Scan
For each paper slot's trading state:
- Check against promotion criteria:
  - 50+ trades
  - Win rate >= 40%
  - Kelly > 0
  - Profit factor >= 1.1
  - Max drawdown < 15%
- If all pass AND live slot count < 2: write `.promote_{slot_id}` sentinel with `capital_pct=0.10`
- If live slot count = 2: compare candidate metrics vs weakest live slot. If candidate is better, demote weakest (write `.demote_{slot_id}`), then promote candidate.
- On promote: update `strategy_factory_state.json` stage to "live", set `promoted` timestamp
- Telegram: "AUTO-PROMOTE: {slot} to live at 10% ({N} trades, {WR}% WR, Kelly {K}, PF {PF})"
- Ramp schedule: after 25 profitable live trades → update capital_pct to 0.20. After 50 → 0.30.
- Auto-demote: if Kelly turns negative after 25 live trades → demote back to paper, update `strategy_factory_state.json` stage to "paper", Telegram notification.
- All paper slots remain eligible for promotion regardless of count. The cap applies only to concurrent live slots (max 2).

#### Auto-Rollback
Reads `parameter_changelog.json`:
- For each change made in the last 48 hours:
  - Compare post-change metrics (last 20 trades) vs pre-change metrics
  - If WR dropped 15%+ → revert using `param_source` field to determine target, write `.restart_bot` sentinel, Telegram: "AUTO-ROLLBACK: {param} {new}→{old} reverted — WR dropped {X}% in {hours} hrs"
- Changelog entry format (note `param_source` field — required for rollback targeting):
```json
{
  "param": "ADVERSE_EXIT_THRESHOLD",
  "old_value": -5.0,
  "new_value": -6.0,
  "changed_at": 1775100000,
  "pre_change_metrics": {"wr": 42.0, "pnl": 1.20, "ae_rate": 28.0, "trades": 20},
  "source": "auto_lifecycle",
  "param_source": "env",
  "param_source_key": "ADVERSE_EXIT_THRESHOLD"
}
```

**`param_source` values:**
| Value | Rollback action |
|-------|----------------|
| `"env"` | Update `.env` file, `param_source_key` = env var name |
| `"bot_py"` | Update `bot.py` constant, `param_source_key` = variable name + line hint |
| `"strategies_py"` | Update `strategies.py` constant, same format |

Rollback must use exact file/key — no guessing. If `param_source` is missing from a changelog entry, skip rollback and alert via Telegram: "ROLLBACK SKIPPED: {param} — missing param_source"
```

### 2. Telegram Commander (`scripts/telegram_commander.py`)

Separate always-on daemon. Polls Telegram for commands, acts via sentinel files.

#### Commands

| Command | Action | Response |
|---------|--------|----------|
| `/status` | Read trading_state.json, show open positions + today's PnL | "2 open: BTC long @ 68400, SOL short @ 79.20 \| Today: 3 trades, +$1.42" |
| `/kill <slot>` | Write `.kill_{slot_id}` sentinel | "Killed {slot}. Will stop trading next cycle." |
| `/pause` | Write `.pause_trading` sentinel | "All trading paused. Exits still processed." |
| `/resume` | Remove `.pause_trading` sentinel | "Trading resumed." |
| `/slots` | Read all trading_state_*.json + factory state | "LIVE: 5m_scalp (42% WR) \| PAPER: liq_cascade (12 trades), mean_revert (8 trades) \| KILLED: none" |
| `/balance` | Read balance from exchange or state | "Balance: $73.18 \| Peak: $109.11 \| DD: 14.6%" |

#### Security
- Only responds to `TELEGRAM_CHAT_ID` from .env
- All other messages silently dropped
- PID file prevents duplicate instances

#### Infrastructure
- **Note:** Existing `notifier.py` is send-only (raw HTTP POST to Telegram API). The commander is a completely separate daemon using `python-telegram-bot` for polling/receiving. These are independent — commander does NOT modify or depend on notifier.py.
- Dependency: `pip install python-telegram-bot`
- Runs via launchd with `RunAtLoad: true` and `KeepAlive: true`
- Auto-restarts on crash
- Logging to `logs/telegram_commander.log`

### 3. Sentinel File Protocol

Bot.py checks for sentinel files at the top of each main loop cycle (~60s latency).

| Sentinel File | Created By | Read By | Action |
|---------------|-----------|---------|--------|
| `.pause_trading` | telegram_commander, auto_lifecycle | bot.py | Skip all entries (exits still processed) |
| `.kill_{slot_id}` | telegram_commander, auto_lifecycle | bot.py | Disable slot, close open positions |
| `.pause_{slot_id}` | auto_lifecycle | bot.py | Skip entries for slot (auto-expire after 24 hrs) |
| `.promote_{slot_id}` | auto_lifecycle | bot.py | Set paper_mode=False, capital_pct from file contents |
| `.demote_{slot_id}` | auto_lifecycle | bot.py | Set paper_mode=True, capital_pct=0.0 |
| `.restart_bot` | auto_lifecycle (rollback) | monitor_daemon | Kill and restart bot process |

**Implementation note:** `monitor_daemon.py` currently has NO sentinel file logic. Phase 1 must add a sentinel file check to the monitor daemon's main loop (~5 lines): check for `.restart_bot`, kill the bot PID, re-launch via the standard start command, delete the sentinel, and log the restart.

Bot.py processes and deletes sentinels after acting on them (one-shot signals).

**Implementation note:** `bot.py` currently has NO sentinel file checks. Phase 1 adds ~10 lines at the top of the main loop (after line ~330, after `signal.alarm(0)` cancel) to glob for sentinel files and dispatch actions before proceeding with the cycle.

### 4. Entry Snapshot Logging

Added to bot.py after order placement (live) and paper slot entry.

**Log format:** `logs/entry_snapshots.jsonl` (append-only, one JSON line per entry)

```json
{
  "ts": 1775100000,
  "symbol": "BTC/USDT:USDT",
  "direction": "long",
  "slot": "5m_scalp",
  "strategy": "confluence",
  "strength": 0.87,
  "price": 68400.5,
  "ob": {"imbalance": 0.15, "bid_walls": 2, "ask_walls": 0, "spread_pct": 0.02},
  "flow": {"buy_ratio": 0.52, "cvd_slope": 0.1, "divergence": null, "large_trade_bias": 0.05, "trade_count": 45},
  "hurst": 0.62,
  "funding_rate": -0.000045
}
```

**Size:** ~1KB/entry, ~15KB/day, ~5.5MB/year. No rotation needed.

## Files

### New Files
| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `scripts/auto_lifecycle.py` | Kill/promote/decay/rollback scanner | ~300 |
| `scripts/telegram_commander.py` | Phone command listener (new dep: `python-telegram-bot`) | ~120 |
| `parameter_changelog.json` | Tracks parameter changes for rollback | Auto-created |
| `logs/entry_snapshots.jsonl` | OB/tape snapshots at entry time | Auto-created |

### Modified Files
| File | Changes |
|------|---------|
| `bot.py` | Sentinel file checks at top of loop (~10 lines), entry snapshot logging (~15 lines) |
| `scripts/monitor_daemon.py` | Add `.restart_bot` sentinel check (~5 lines) |

### New launchd Jobs
| Plist | Script | Schedule |
|-------|--------|----------|
| `com.phmex.auto-lifecycle.plist` | `scripts/auto_lifecycle.py` | Every 4 hours (14400s) |
| `com.phmex.telegram-commander.plist` | `scripts/telegram_commander.py` | Always on (RunAtLoad + KeepAlive) |

## Guardrails

| Rule | Enforced By |
|------|------------|
| Parameter changes ±25% max per week | auto_lifecycle.py (validates before applying) |
| 30+ shadow trades before deploying param change | auto_lifecycle.py (Phase 2 — not in Phase 1 scope) |
| Auto-rollback on 15%+ WR drop in 48 hrs | auto_lifecycle.py (reads parameter_changelog.json) |
| Auto-promote at 10% capital only | auto_lifecycle.py (hardcoded initial capital) |
| Ramp: 10% → 20% after 25 trades → 30% after 50 | auto_lifecycle.py (checks live trade count) |
| Max 2 live slots | auto_lifecycle.py (checks before promoting) |
| Never increase position size or leverage | auto_lifecycle.py (no code path for this) |
| Can reduce risk autonomously (kill, pause, demote) | auto_lifecycle.py + telegram_commander.py |
| Emergency stop from phone | telegram_commander.py /pause |

## What This Does NOT Change

- Strategy logic (signal generation unchanged)
- Exit logic (adverse_exit, SL/TP unchanged)
- Sentinel entry gates (L1/L2/L3 unchanged)
- Position sizing (Kelly-based, unchanged)
- Daily report generation (unchanged, still runs 4x daily)
- Monitor daemon (unchanged, still runs hourly)

## Phase 2 (Deferred)

- Optuna/WFO parameter optimization
- Shadow parameter testing infrastructure
- Regime-aware slot activation
- Capital reallocation proposals
- Automated strategy hypothesis generation

## Success Criteria

After 2 weeks of Phase 1 running:
- Zero manual kills needed (auto-lifecycle catches them)
- Zero missed promotions (auto-lifecycle detects readiness)
- Edge decay detected within 4 hours of threshold breach
- Jonas uses /status and /balance daily from phone
- Entry snapshots collecting for Phase 2 backtesting
