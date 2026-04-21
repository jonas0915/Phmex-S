# Phmex-S — Project Instructions

Global workflow rules (plan mode, subagents, self-improvement, verification, elegance, task management) are in `~/.claude/CLAUDE.md`. This file covers project-specific context only.

## What This Is
Crypto perpetual futures scalping bot on Phemex via ccxt. **Live trading with real money.**
Current version: **Sentinel (v11)** — deployed 2026-04-01.

## Critical Rules
- **NEVER restart without running `/pre-restart-audit` first.** Real money is at stake.
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
| Trade size | $10 margin | .env: TRADE_AMOUNT_USDT |
| Leverage | 10x | .env: LEVERAGE |
| Max open trades | 3 | .env: MAX_OPEN_TRADES |
| Stop loss | 1.2% | .env: STOP_LOSS_PERCENT |
| Take profit | 1.6% | .env: TAKE_PROFIT_PERCENT |
| Adverse exit | **-3% ROI after 10 cycles (10 min)** | .env: ADVERSE_EXIT_THRESHOLD/CYCLES |
| Candle lookback | 500 (Phemex requires value in {5,10,50,100,500,1000}) | .env: CANDLE_LOOKBACK |
| Per-pair cooldown | 10 min after loss | bot.py:1032 |
| Global cooldown | 120s between entries | bot.py |
| Daily symbol cap | 3 trades/symbol | bot.py:~671 |
| ADX threshold | 25 | strategies.py |
| Ensemble confidence | 4/7 minimum | bot.py |
| OB imbalance gate | ±0.25 | strategies.py:139 |
| Tape buy_ratio gate | 0.45/0.55 | bot.py:~789 |

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
