---
name: SESSION_HANDOFF — last touched 2026-04-26 9:54 PM PT
description: Read this FIRST in next session. Full handoff after the strategy cull + key rotation marathon.
type: project
---

# Session Handoff — 2026-04-26 (Sat night, late)

## Bot state right now
- **PID** changed multiple times tonight; check `ps aux | grep "Python.*main\.py"` for current
- **2 strategies live** (real money): `htf_confluence_pullback` + `htf_l2_anticipation` only. All others culled in commit `479f879` (originally `af0c942` pre-rewrite).
- **2 open positions:** ETH long entry $2392.11 ($9.62 margin) + TAO long entry $255.39 ($9.96 margin). Total equity $74.73 (peak $74.80).
- **All 3 API keys rotated tonight:** Phemex new key `44597c26...` with **"Don't Bind"** (no IP whitelist — required because ExpressVPN rotates IPs every few seconds), Anthropic + Telegram also fresh.

## What was shipped tonight (commits on `github.com/jonas0915/Phmex-S`)
1. **Strategy cull (Option A)** — disabled `momentum_continuation`, `htf_confluence_vwap`, `bb_mean_reversion` in `confluence_strategy` router (`strategies.py:670-703`)
2. **Dashboard:** Today Total bar in Sessions card; **Sentinel-era audit card** (above all-time, filtered to 146 trades since 2026-04-02 06:01 UTC); Win Rate added; chart flicker fixed (server cache headers + JS img stashing)
3. **Monitor false-drawdown bug fix** — `bot.py` skips STATS log when `get_balance()=0` with open positions; `scripts/monitor_daemon.py` skips alert when `parsed_balance ≤ locked_margin` (the stale-STATS pattern from API failures). Telegram alerts now use 12-hour PT timestamps.
4. **Git history rewrite** — scrubbed `.env` from all 131 commits via `git-filter-repo`. Force-pushed clean to `Phmex-S` (canonical, was `Phmex2`). Backup at `~/Desktop/Phmex-S.backup-2026-04-26` — **DELETE on/after 2026-05-03** if no rollback needed.

## Verified per-strategy edge (30 days, 184 trades, n=verified-from-trading_state.json)
| Strategy | n | WR | Edge/trade | Verdict |
|---|---|---|---|---|
| htf_l2_anticipation | 13 | 80% | **+$0.20** | KEEP — only proven winner |
| synced (orphan-adopted) | 32 | 56% | +$0.02 | safety mech, not cullable |
| htf_confluence_pullback | 126 | 39.7% | **-$0.13** | KEPT — biggest data source, recent 7d shows 46.7% / +$0.19 (recovering or noise) |
| htf_confluence_vwap | 5 | — | -$0.10 | CULLED |
| momentum_continuation | 11 | — | -$0.40 | CULLED |
| bb_mean_reversion (live) | 0 | — | n/a | CULLED — was dead anyway |

**Net per-trade expectancy: -$0.10 with 95% CI entirely below zero. Strategy mix problem, not parameter problem.**

## Paper slots
| Slot | Strategy | n | WR | PnL | Note |
|---|---|---|---|---|---|
| 5m_mean_revert | bb_mean_reversion | 9 | 55.6% | +$2.47 | **Misleading** — 3 of 5 wins are TP lottery hits; without them = -$1.97. Same falling-knife pattern lessons.md flagged. |
| 5m_liq_cascade | liq_cascade | 28 | 32.1% | +$0.45 | No edge. Should likely kill. |
| 5m_narrow | confluence (filtered) | 50 | 20.0% | -$12.99 | Auto-killed by Kelly switch. |

## Top-priority next-session work
1. **Write research spec for `bb_mean_reversion` tweak.** Jonas wants culled strategies fixed not abandoned. Concrete hypothesis: directional filter (shorts-only OR require lower-highs/higher-lows confirmation). Path: `docs/superpowers/specs/2026-04-27-bb-mean-reversion-fix.md`. Spec only, no code.
2. **Decide on paper slots** — `5m_liq_cascade` (no edge) and `5m_mean_revert` (lottery winners hide bleeder). Jonas hasn't approved kills yet.
3. **Watch the cull effect.** `htf_confluence_pullback` 7d WR jumped from 30d-avg 39.7% to 46.7% (+$0.19). Either real recovery from cull's collateral effect or pure variance. Reassess after 14 more days.

## Critical rules from this session (added to lessons.md)
- **Never trust agent impact estimates without OHLCV simulation.** Yesterday's "trail-to-breakeven +$5" was actually -$0.20 in OHLCV replay. Earlier today I quoted 45.2% WR for pullback when verified is 39.7%. Always re-derive from `trading_state.json` directly before quoting per-strategy numbers.
- **Repo HAS unit tests** (4 files / 12 functions in `tests/`). Earlier "zero tests" claim was wrong; corrected.
- **Phemex new keys default to IP-bound.** Use the **"Don't Bind"** radio button explicitly. ExpressVPN rotates IPs every few seconds → instant 401 on any whitelisted key.
- **Jonas is in California PT.** Don't assume "tired" before 11 PM PT.
- **STATS log line lies during API failures** — `get_balance()=0` + open position → `real_balance = 0 + margin` → bot logs the locked margin as "Balance" → monitor alerts false drawdown. Both fixes deployed (skip log + sanity check downstream).

## Open questions
- Paper slots (`5m_mean_revert`, `5m_liq_cascade`) — kill or watch? Awaiting Jonas decision.
- Should `bb_mean_reversion` shorts-only experiment go straight to a paper slot, or backtest first? Jonas hasn't decided.
