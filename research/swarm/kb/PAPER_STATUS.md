# PAPER_STATUS — paper-slot forward tests (auto-written by `scripts/swarm_desk.py --mode maint`; do not edit — regenerated daily)

Written 2026-09-17 07:32 AM PT. Bot process: STOPPED — no state file advances until an audited restart. Adjudicator digest: Sep 9 6:00 AM PT (8.1 d old) — kill lines are not being graded automatically (com.phmex.lab-adjudicator is unloaded until the bot restart; README Cadence, Gate B).

Per slot: n and net USD are the registered era's closed trades (no registered era → every closed trade in the file; net_pnl as-is, fee-inclusive at the source); WR = share of era trades with net > 0; days = era start (registration, else first trade) → now, or → kill. Distance = USD above the kill line. Nothing here promotes or restarts anything.

## Active slots (registered in bot.py, not killed)

| slot | mode | n | net USD | WR | days | last close | kill line | distance | verdict_n | adjudicator (latest digest) |
|---|---|---|---|---|---|---|---|---|---|---|
| 5m_mean_revert | paper | 54 | +3.59 | 46% | 173 | 2026-09-07 | live rail only: auto-demote at $-5.00 (sidecar loss_cap_usdt); no paper kill line registered | — | — | — |
| DONCHIAN_BTC | paper | 12 | +4.70 | 50% | 62 | 2026-09-07 | KILL if paper net <= $-15.00 (spec; fidelity line graded separately) (docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md) | 19.70 above $-15.00 | — | — |
| DONCHIAN_ETH | paper | 18 | +4.23 | 67% | 62 | 2026-09-09 | KILL if paper net <= $-15.00 (spec; fidelity line graded separately) (docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md) | 19.23 above $-15.00 | — | — |

## Killed / retired

| slot | n | net USD | WR | days | last close | killed | line | adjudicator (latest digest) |
|---|---|---|---|---|---|---|---|---|
| 5m_liq_cascade | 50 | -5.16 | 34% | 62 | 2026-05-27 | bot kill switch: negative Kelly (-0.079) after 50 trades | none registered | — |
| 5m_narrow | 51 | -27.58 | 20% | 52 | 2026-06-11 | bot kill switch: negative Kelly (-0.441) after 51 trades | none registered | — |
| ST2.0 | 51 | -9.45 | 41% | 16 | 2026-06-29 | bot kill switch: negative Kelly (-0.762) after 51 trades | live rail only: auto-demote at $-10.00 (sidecar loss_cap_usdt); no paper kill line registered | — |
| ETH_TSM_28 | 3 | +0.75 | 100% | 22 | 2026-07-28 | killed 2026-07-28 (sidecar killed_at) | KILL if net <= $-10.00; also >= 2 disaster stops / tracking drift (adjudicator) (scripts/lab_adjudicator/adjudicate.py EXPERIMENTS["eth_tsm_28"]) | RETIRED — killed 2026-07-27 by the pre-registered tracking-drift line — clean, criteria-driven exit. Final net $+0.75. Final. | live 0 trades $+0.75 (kill -10) · 0 disaster-stops | 0 days · None div | track n/a | no days yet |
| SR_BOUNCE | 117 | -4.89 | 47% | 27 | 2026-09-02 | bot kill switch: negative Kelly (-0.007) after 136 trades | KILL if n>=50 & net<=0 (honest era: opened_at >= 8/5 fix) (scripts/lab_adjudicator/adjudicate.py EXPERIMENTS["sr_bounce_v2"]) | KILL — registered verdict: n=117, net $-4.89 <= 0 — fixed geometry doesn't save it; kill the slot (touch .kill_SR_BOUNCE) | 117 trades 55W $-4.89 | WR 47.0% (BE 40.5%) |
| HTF_L2 | 43 | -10.91 | 28% | 11 | 2026-07-31 | killed 2026-07-31 (sidecar killed_at) | live rail only: auto-demote at $-5.00 (sidecar loss_cap_usdt); no paper kill line registered | RETIRED — demoted to paper by owner 2026-07-27 — era ended at n=6, net $-3.48 (pre-empted the -$5.00 rail; coin-flip diagnosis). Final. | slot 6 trades 1W $-3.48 | WR 16.7% vs 37.3% BE | thin_adx blocked 104 · conf<4 blocked 22 |
| VWAP_CROSS | 51 | -3.71 | 39% | 7 | 2026-07-27 | bot kill switch: negative Kelly (-0.035) after 51 trades | none registered (owner-set pending; adjudicator REPORT-ONLY) (scripts/lab_adjudicator/adjudicate.py EXPERIMENTS["vwap_cross"]) | KILLED — auto-killed at n=51 by the negative-Kelly switch (Kelly -0.035) — forward test answered 2026-07-27. Final. | slot 51 trades 20W $-3.71 | WR 39.2% vs 32.9% BE | blocked 0 |
