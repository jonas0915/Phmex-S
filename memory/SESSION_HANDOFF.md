---
name: SESSION_HANDOFF — last touched 2026-05-02 7:05 PM PT
description: Read this FIRST in next session. Pullback culled tactically; bot running on htf_l2_anticipation only; may go quiet. Research path remains strategic plan but paused.
type: project
---

# Session Handoff — 2026-05-02 (Sat evening)

## Bot state right now
- **PID 26589** running. Started 7:01 PM PT 2026-05-02 after pullback cull deployed.
- **Balance $67.65** at deploy time.
- **1 strategy live** (real money): `htf_l2_anticipation` only. `htf_confluence_pullback` commented out at `strategies.py:671`.
- **Open positions:** 0 live (1 paper-slot position restored on startup).
- **Today's 3 trades** (all BEFORE the cull deploy): TAO long pullback +$0.12, TAO long pullback -$0.58, ETH long pullback -$0.37 → **net -$0.83. All 3 were `htf_confluence_pullback`. Zero `htf_l2_anticipation` fires today.**

## ⚠️ Critical caveat
- **Bot may go quiet.** Pullback drove 100% of today's trades. l2_anticipation didn't fire today. Now pullback is gone.
- **No idle alarm.** Code review I-4: PnL halts (daily loss / consecutive loss / DD tier) are the only kill switches. Zero entries for hours triggers nothing. Watch the bot log if no Telegram entries within 24h.

## What changed this session
1. **Bot restarted 11:25 PM PT 04-30** — overrode the 05-01 research-path pause when Jonas said "start bot." (See lessons.md: should have flagged the conflict at session-start preflight.)
2. **Investigation pass** — 3 parallel agents (forensic + verifier + reference_*.md research read).
3. **D1: profitable-hours filter audit** — wired correctly via `_BLOCKED_HOURS_UTC = {0,1,2,9,17,18,19,20}` at bot.py:1166-1178. Updated from Apr 10-16 417-trade analysis (more current than the older `_PROFITABLE_HOURS_UTC` whitelist). Working as designed.
4. **D2: gate_tags=null root cause** — never wired into live entry path. Populate site exists ONLY for paper slots at bot.py:1742. Live path at bot.py:1282-1326 has no equivalent. Persist (risk_manager.py:303-322) and restore (272-301) also miss the field. 517-trade history confirms always null.
5. **OHLCV AE-threshold replay** — sweep across {-2%, -2.5%, -3%, -3.5%, -4%, -5%, -6%} on n=32 post-cull + n=182 pre-cull. **Caps > rescues at every threshold.** AE feature is dollar-negative regardless of parameter. Threshold tuning rejected. Artifacts at `/tmp/ae_replay/`.
6. **Pullback cull (single line, fully reversible)** — `strategies.py:671` commented out.
   - **Originally proposed culling l2_anticipation** on agent's stale numbers (n=10/-$0.254). Verification re-counted: actual was n=13/-$0.194, AND pullback was WORSE (n=18/-$0.236). Cull target inverted.
   - Jonas chose B (cull pullback). Edit applied, audit GREEN, bot restarted clean.
   - Reverse: uncomment `strategies.py:671` + restart.

## Verified per-strategy edge (post-cull window, 2026-05-02 7 PM PT)
| Strategy | n | WR | Edge/trade | Verdict |
|---|---|---|---|---|
| htf_l2_anticipation (LIVE) | 13 | 30.8% | -$0.194 | CI [-$0.44, +$0.05] brackets zero |
| htf_confluence_pullback (CULLED 05-02) | 18 | 22.2% | -$0.236 | worse; culled tonight |
| synced (orphan-adopted, not a strategy) | 3 | 66.7% | +$0.407 | safety mech |

Combined l2_anticipation pre+post (n=26): **-$0.022/trade**, CI [-$0.19, +$0.15] brackets zero. **No statistical signal of edge.** The cull is tactical risk-reduction, not an edge play.

## Strategic plan (paused, still strategic)
The 2026-05-01 research-path remains the strategic plan: build a calibrated backtest harness, simulate 90 days OHLCV with realistic fees+slippage, deploy only with positive simulated edge. Decomposes into 3 sub-projects: (1) calibrate one backtester within ±15% of live, (2) strategy testing harness CLI, (3) deployment gate policy. See MEMORY.md "Backtest infra survey (2026-05-01)" and the prior 05-01 handoff archived in lessons.md for full context.

The 2026-05-02 cull is a tactical risk-reduction move while the research path proceeds — **not a substitute for it**.

## Top-priority next-session work
1. **Watch trade frequency.** If l2_anticipation fires <1 trade/day for 3+ days, decide: revert pullback cull, or pause and accelerate research path.
2. **AE feature investigation (separate from threshold tuning).** Today's replay showed AE is dollar-negative at every threshold. Next: replay with AE disabled entirely on n=182. If confirmed, "kill AE" is higher-leverage than threshold tuning.
3. **gate_tags wiring** — non-trivial code work; needed before any future gate-level forensic. Defer until research path is unblocked or until a specific gate question demands it.
4. **5m_narrow paper slot decision** — still calls `htf_confluence_pullback` directly (bot.py:1536, 1551), unaffected by cull. Useful as counterfactual ("what would we have earned with pullback?"). Revisit after 14d.
5. **Resume backtest-harness brainstorm** — A/B/C decision on OB/tape simulation, then calibration target selection.

## Open questions
- Will l2_anticipation fire enough to keep the bot meaningfully live?
- Should 5m_narrow paper slot mirror the live cull or remain a counterfactual?
- When does the research path resume — after 14d cull observation, or sooner if bot goes quiet?

## Critical rules added to lessons.md this session
- **Re-derive headline numbers between agent run and proposal acceptance.** Bot trades while agents work; numbers go stale within minutes for active windows.
- **Surface active "stop work" directives at session-start preflight.** Scan MEMORY.md for stop-words ("stopped", "paused", "no more", "research path", "halt") and flag conflicts with the user's first ask.
- **AE feature is dollar-negative at every threshold tested.** Threshold tuning is dead — future AE work must use different methodology or jump to "kill AE" entirely.
- **gate_tags is null on 517 live trades — never wired** (paper slot only).
- **Pullback hour-bleed gate is stale; do not flip.** Hour set inverted vs current data.

## Lower-priority pending
- `~/Desktop/Phmex-S.backup-2026-04-26` past 05-03 deletion deadline. Safe to delete.
- `bb_mean_reversion` shorts-only spec — deferred indefinitely (research path supersedes).
- Order-path timeout wrap spec at `docs/superpowers/specs/2026-04-24-order-path-timeout-wrap.md` — needs no-position window if/when redeployed.
