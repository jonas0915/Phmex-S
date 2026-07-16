# BTC-TSM (28,5) kill test — 2026-07-15 — VERDICT: DO NOT BUILD

Adjudicates whether the BTC-TSM slot (unblocked at $250 balance) deserves to be
built. Methodology = byte-identical reuse of the 2026-07-13 basket walk-forward
(`tsm_basket.py`, shasum d827ca61f8e5f18a37edb2c35c038ffabd9a21ed, copied from
session da6fc410 scratchpad — the script that produced "12-coin Sharpe 0.39,
DSR 0.63, ETH-only 0.71"). No new variants. Kill bar prespecified in
`kill_test_btc.py` header before first run. Full output: `results.txt`.

Cross-check: ETH-only post-2022 reproduces the memory-recorded number exactly
(Sharpe 0.71, results.txt line 4).

## Kill bar (prespecified) vs result — PRIMARY (cached 7/13 binanceus daily, 2021-01-01..2026-06-13)
1. Post-2022 walk-forward Sharpe > 0: **0.64** (annRet 14.8%, maxDD −29.1%, expo 33.8%) — PASS
2. Deflated-Sharpe prob > 0.95 (same 36-config grid, BTC-only): **0.635** — **FAIL**
   (identical failure mode to the 7/13 basket's 0.63)
3. Beats buy-and-hold risk-adjusted with diff-CI > 0: TSM 0.64 vs B&H 0.40,
   Sharpe-diff 95% CI **[−1.26, +1.55]** (straddles 0; independent block
   bootstrap per feedback_bootstrap_diff_ci.md) — **FAIL**

SECONDARY (fresh ccxt Phemex BTC/USDT:USDT daily, only serves 2022-11-04..2026-07-15):
Sharpe 0.89 but B&H over same window 0.88 — diff CI [−1.66, +1.40]; DSR 0.609
FAIL. Same verdict.

## Decisive texture
- Trades: n=50 full sample, net exp/trade +2.86% (~+$1.83 at 0.001 BTC), WR 38%,
  10 stops, avg hold 12.6d — all upside concentrated in 2021/2023/2024 bull legs.
- Pure bull-regime beta: 2022 Sharpe −1.39, 2026 YTD −2.05 (−17.0%). Same
  regime-dependence that killed the 12-coin basket on 7/13.
- The rule's post-2022 boot95 CI on its own Sharpe: [−0.44, +1.60] — cannot
  reject zero even before deflation.

## Standing
BTC-TSM per this rule is NOT a verified edge on our own data — it is bull-beta
with a trend filter, indistinguishable from grid luck after deflation, and does
not beat holding BTC. $250 unblocking the halt math does not change the signal
verdict. Do NOT build; do NOT re-mine this grid (36 configs already burned
here and on 7/13). ETH-TSM-28 paper slot remains what it always was: a
fidelity/scaling-rights probe, not a proven edge (its own DSR would face the
same bar).
