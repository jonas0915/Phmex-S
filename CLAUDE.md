# Phmex-S — Project Instructions

Global workflow rules (plan mode, subagents, self-improvement, verification, elegance, task management) are in `~/.claude/CLAUDE.md`. This file covers project-specific context only.

## What This Is
Crypto perpetual futures scalping bot on Phemex via ccxt. **Live trading with real money.**
Current version: **Sentinel (v11)** — deployed 2026-04-01.

## Critical Rules
- **NEVER restart without running `/pre-restart-audit` first.** Real money is at stake.
- **Editing a file ≠ the bot using it.** When working via the remote tunnel (or any editor), saved changes hit the home Mac's disk instantly, but the live bot keeps running the old code/`.env` until an audited restart. Never start a second instance on another machine. See `docs/remote-access.md`.
- **NEVER change parameters without checking `memory/lessons.md` first.** Read META-RULES.
- **NEVER propose new infrastructure without grepping existing code.** L2 orderbook, tape/flow, CVD, divergence systems already exist.
- **Always verify numbers before presenting.** Deploy verification agents in the first pass.
- **EVERY bot update must propagate to Telegram AND the dashboard.** Any change that adds/removes/renames a metric, field, gate, strategy, exit reason, or report section MUST be reflected in:
  1. `notifier.py` + `scripts/daily_report.py` (Telegram reports)
  2. `web_dashboard.py` (browser dashboard)
  3. Any cached chart or helper that reads the changed field
  Failing this rule creates silent reporting lies (e.g., gross vs net PnL, fee capture, exit_reason tagging — all caused real-money errors in 04-07 session). Before declaring a bot update "done", verify both surfaces show the new/changed data correctly.

## Current Parameters
| Parameter | Value | Location |
|-----------|-------|----------|
| Trade size | $15 margin main book (restored from $5 on 2026-08-09, owner order, after the gated-era n=40 verdict PASSED — n=42 +$4.30, ladder rung $10, owner chose the $15 registered ceiling; 5m_mean_revert $15/trade per-slot pin — cut from $30 on 2026-08-18, owner "stop losing" order). MIN/MAX_TRADE_MARGIN pinned 15.0 so every Kelly path resolves to $15; weekend cap follows TRADE_AMOUNT_USDT. The BTC exchange-min-qty bump (~$13) is moot at $15 | .env: TRADE_AMOUNT_USDT |
| Daily loss halt | max(3% × balance, $8.00) — floor raised $5→$8 2026-07-27 (owner directive, with 5m_mean_revert $30 resize + $92 balance) preserving the 2026-07-07 semantics: ~2 worst stops of the largest book (≈−$3.86 each at $30) tolerated, halt on the 3rd | bot.py:_should_halt_daily_loss |
| Leverage | 10x | .env: LEVERAGE |
| Max open trades | 3 | .env: MAX_OPEN_TRADES |
| Stop loss | 1.2% | .env: STOP_LOSS_PERCENT |
| Take profit | 1.6% | .env: TAKE_PROFIT_PERCENT |
| Adverse exit | **DISABLED** (ADVERSE_EXIT_THRESHOLD=-999.0 since 2026-05-07; CYCLES=10 moot) — losers ride to the full -1.2% SL with no early cut. Re-enable only after both-sides replay (see loss-asymmetry note). | .env: ADVERSE_EXIT_THRESHOLD/CYCLES |
| Candle lookback | 500 (Phemex requires value in {5,10,50,100,500,1000}) | .env: CANDLE_LOOKBACK |
| Per-pair cooldown | 10 min after loss | bot.py:1032 |
| Global cooldown | 120s between entries | bot.py |
| Daily symbol cap | 3 trades/symbol (enforced 2026-06-11 — was log-only) | bot.py:~966 |
| ADX threshold | 25 | strategies.py |
| Ensemble confidence | 4/7 minimum | bot.py |
| OB imbalance gate | ±0.25 | bot.py:1433,1883 |
| Tape buy_ratio gate | 0.45/0.55 | bot.py:1295,1905 |
| Pullback session gate | `false` (shadow-only, Phase 2b Gate A) — blocks UTC {5,8,13,14,16} when `true` | .env: PULLBACK_SESSION_GATE |
| Pullback volatile gate | `false` (reserved, Gate B shadow-only) | .env: PULLBACK_VOLATILE_GATE |

## Architecture
```
main.py → bot.py (main loop, 60s cycle)
  ├── strategies.py (signal generation)
  ├── risk_manager.py (position management, exits)
  ├── exchange.py (ccxt/Phemex API, orderbook)
  ├── ws_feed.py (WebSocket trade stream, tape/flow)
  ├── strategy_slot.py (paper slot framework)
  ├── config.py (.env-driven config)
  ├── notifier.py (Telegram alerts)
  ├── web_dashboard.py (browser dashboard)
  └── war_room.py (terminal dashboard)
```

## Entry Gate Flow (Sentinel)
```
Signal → Global cooldown (2 min) → Per-pair cooldown (10 min) → Daily cap (3/symbol)
  → Ensemble confidence → Tape gate → OB gate → Order placement
```

## Key Files
- `bot.py` — Entry logic, gate checks, paper slot evaluation, cooldowns
- `strategies.py` — Strategy functions (confluence, htf_momentum, bb_reversion, liq_cascade)
- `risk_manager.py` — Position tracking, SL/TP, adverse_exit, drawdown halts
- `.env` — API keys + thresholds (NEVER commit)
- `trading_state.json` — Live trade history
- `trading_state_5m_*.json` — Paper slot state files

## Memory System
- `memory/lessons.md` — **Read first every session.** META-RULES + operational lessons.
- `memory/MEMORY.md` — Index of all reference files
- `memory/reference_*.md` — Architecture, infrastructure, baselines, Sentinel deployment

## Key Docs
- `docs/superpowers/specs/2026-04-01-entry-quality-gates-design.md` — Sentinel design spec
- `docs/RD_PROCESS.md` — Strategy pipeline and weekly R&D cadence

## Running
```bash
# Start bot (append logs, don't overwrite)
cd ~/Desktop/Phmex-S
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &

# Dashboard
python3 web_dashboard.py  # localhost:8050

# Daily report
python3 scripts/daily_report.py
```
