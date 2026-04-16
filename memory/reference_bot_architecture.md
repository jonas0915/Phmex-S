---
name: Bot Architecture
description: Phmex-S trading bot structure — entry logic, cooldowns, exits, config values, slot system (updated for Sentinel v11)
type: reference
---

## Core Loop
- 60-second main loop (bot.py)
- Scans active_pairs for entry signals each cycle
- MAX_OPEN_TRADES: 3 (config.py:24)
- TRADE_AMOUNT_USDT: 10.0 (config.py:22)

## Entry Flow (Sentinel v11, updated 2026-04-07)
1. Global 2-min cooldown (bot.py:667)
2. Per-pair cooldown check (bot.py:669-671)
3. Per-symbol daily trade cap: 3 (bot.py:~671)
4. can_open_trade() — position limit + drawdown check (risk_manager.py:296-333)
5. Strategy signal (strategies.py)
6. Ensemble confidence (bot.py:803-812, 7 layers) — **threshold now 4/7 for all strategies** (was 3), liq_cascade explicit
7. **Tape gate** — buy_ratio <0.45, CVD slope, divergence, large trade bias (bot.py:~789). NOTE: CVD bearish divergence veto EXISTS at bot.py:845-847, but trade_count<20 guard can bypass entire tape gate.
8. **OB gate** — imbalance ±0.25, wall veto, spread >0.15% (bot.py:~857)
9. Order placement (calls _log_entry_snapshot() to append to logs/entry_snapshots.jsonl)

## Cooldown System (Sentinel v11)
- Per-pair after loss: 600s / 10 min (bot.py:1032)
- 3 consecutive losses on pair: 14400s / 4 hr blacklist (bot.py:1028)
- Global regime pause: 3 of 5 losses → 1800s / 30 min (bot.py:1037-1038)
- Drawdown halts: 20%→30min, 25%→1hr, 30%→1.5hr (risk_manager.py:302-327)

## Exit System
- adverse_exit: ROI <= -5% after 10 cycles/10 min (risk_manager.py:162-171)
- stop_loss: strategy-set SL level
- take_profit: strategy-set TP level
- hard_time_exit: 4 hours max hold (risk_manager.py:173-190)
- early_exit: profitable exit before TP
- exchange_close: exchange-initiated close

## Active Hours Filter (updated 2026-04-07)
- `_PROFITABLE_HOURS_UTC = {10, 16, 21, 3}` — PT 3, 9, 14, 20 only (bot.py:881)
- Previously: {6, 7, 8, 9, 10, 13, 16}
- SOL/USDT:USDT added to SCANNER_BLACKLIST in .env (0W/6L, 2026-04-07)

## New Methods (added 2026-04-07)
- `_log_entry_snapshot()` — appends OB/tape snapshot JSONL to logs/entry_snapshots.jsonl on every live and paper entry
- `_process_sentinels()` — checks sentinel files (.pause_trading, .kill_*, .pause_*, .promote_*, .demote_*) each cycle for file-based IPC

## Paper Slots (Sentinel v11)
- Legacy Control (trading_state_5m_legacy_control.json) — ungated Pipeline replica for A/B
- 1H Momentum (trading_state_1h_momentum.json) — gated
- Liq Cascade (trading_state_5m_liq_cascade.json) — gated
- Mean Revert (trading_state_5m_mean_revert.json) — gated

## Removed Slots (as of Sentinel)
- SMA+VWAP, ATR Gate, V10 Control, 8H Funding

## Key Strategy: htf_confluence_pullback
- Location: strategies.py:724-847
- Entry: HTF EMA21>EMA50 + ADX>=20 + VWAP gate + 0.5% pullback to EMA + RSI 35-60 + green candle
- Base strength: 0.84, boosters up to 0.92
- Short penalty: -0.04 applied in bot.py:722
- OB imbalance gate: ±0.25 (strategies.py:139-142)

## Dashboard (web_dashboard.py)
- Bloomberg/terminal dark theme, fixed 3-column grid, cyan/teal accent (#00d4aa)
- Row 1: Balance + PnL | Session Performance (4 horizontal tiles) | Slot Lifecycle
- Row 2: A/B Test (Sentinel vs Legacy Control) | Performance Audit (compact tables, collapsible trade log)
- /tracker route: Project Tracker page with auto-detection of Phase completion
- Version labels use trade-index boundaries (Pipeline=247-341, Sentinel=342+)
- Sentinel deploy timestamp: 2026-04-01 23:01 PT (not midnight)

## Version History
Genesis → Patch → Filter → Razor → Razor v2.1 → Clarity → v5-v9 → Pipeline → **Sentinel**
