# HTF_L2 — Full Report (2026-07-27, 10:15 AM PT)

All numbers recomputed from state files this morning; era detail verified against
trading_state_HTF_L2.json. History receipts: reference_htf_l2_diagnosis_2026-07-16,
reference_htf_l2_signal_rnd_2026-07-17, reference_htf_l2_entry_features_2026-07-18,
reference_htf_l2_loss_audit_2026-07-23 (memory), scripts/research/* artifacts.

## Where it stands right now

- **Status: LIVE** (slot, promoted 7/23 9:54 PM PT), currently flat.
- **Era 2 record: 6 trades, 1W/5L, net −$3.48.** Budget rail −$5.00 → **$1.52 left**.
- **Registered verdict rules (owner, 7/26):** KILL at era net ≤ −$5 (auto-demote), else
  verdict at n=40 era trades — PASS if net > 0, KILL otherwise. No discretion remains.
- Era breakeven win rate: **37.3%** (geometry: SL −10% ROI / TP ~+20% effective, fees).
  Delivered so far: 16.7% — below the bar, on a sample too small to be conclusive.

## The three lives of htf_l2

| Era | Window | Config | Record | Verdict |
|---|---|---|---|---|
| Main path (legacy) | Apr → 7/13 halt | old geometry, partial-TP+trail, full gate stack | 235t, ≈−$27 net; 49 full-SL rides = 82% of loss $ | Halted; diagnosis: no entry edge, payoff needed 67.9% WR, delivered 55–60% |
| Slot era 1 | 7/20 → 7/22 auto-demote | new geometry BUT missing quiet-block, cross-book fights | 9t, 3W/6L, −$6.22 (avg win $0.29 / avg loss $1.18) | Self-demoted at −$6.22; audit: 57% of loss = quiet entries, plus balance-contention chase |
| Slot era 2 (current) | 7/23 → now | new geometry + full gate stack (thin∧ADX, quiet, cross-book, shared cap) | 6t, 1W/5L, −$3.48 (avg win $3.08 / avg loss $1.31) | Running; ends at −$5 or n=40 |

## Era 2 trade log

| Date | Sym | Side | Net | Exit |
|---|---|---|---|---|
| 7/24 7:26 AM | XLM | short | **+3.08** | take-profit (full +20% ROI ride) |
| 7/24 1:47 PM | ETH | short | −0.35 | 4h time-exit |
| 7/24 1:52 PM | AVAX | short | −1.19 | 4h time-exit |
| 7/24 8:34 PM | XLM | short | −1.74 | stop |
| 7/25 3:05 PM | ETH | short | −1.08 | 4h time-exit |
| 7/27 6:28 AM | 1000PEPE | long | −2.20 | stop |

## What the redesign changed (and proved)

- **Geometry works as designed:** era-2 winners average **$3.08** vs losers $1.31 (2.4:1).
  Era-1/legacy winners averaged $0.29–0.52 vs losers ~$1.2 (1:4 against). The math bar
  dropped from 67.9% WR to 37.3%.
- **Gates work:** lifetime slot blocks — thin∧ADX 63, quiet 10, cross-book 6, ensemble 10.
  Zero era-2 entries in the historically toxic thin∧ADX cell. The 7/23 loss audit verified
  each fix against the trades that motivated it.
- **What hasn't changed: the signal.** Five verified research rounds (13 L2-confirmation
  variants, tape/flow, gate stack, time-of-day, reconstructed entry indicators — all
  placebo-guarded) found winners and losers indistinguishable at entry. The redesign gives
  a coin-flip signal its best mathematical seat; it cannot make the coin fair.

## Watch items (pre-registered accruals, no action until n)

- VWAP >4-ATR overextension: NOT supported so far (running tally since 7/20, n≈20).
- High-ADX-on-active-tape shorts: 5 small time-exit losses across eras (~−$4.4) — the
  allowed "half-cell"; graded when n reaches 20.
- Losers cluster 3–11 AM PT (descriptive, n too small).

## How this ends

1. **−$5.00 era net** → slot auto-demotes to paper, adjudicator prints KILL. Max further
   real-money exposure: **$1.52**.
2. **40 era trades net-positive** → PASS; owner decides whether it earns scale.
3. **40 era trades net-negative** → KILL.

Daily scorecard: 6 AM PT adjudicator Telegram, `[htf_l2]` line. Dashboard box: HTF_L2 — LIVE SLOT.
