# R2 — Restricted Adverse-Exit (symbol / regime gated) — June replay

Date: 2026-07-06 (overnight run). Rig: `scripts/calibrate_exits.py` (exit-model
isolation, live entries replayed through `backtest.check_exits_live`).
Window: 2026-06-01 → 2026-07-04, `backtest_data_june`, 86 live htf_l2 entries,
`--trail-arm-roi 8` on ALL runs (matches the pending arm-8 forward test).
Dumps: `reports/ae_june_{baseline,sym57,symworst,regchoppy,regtrendvol}.json`.

## Why this test

Last untested exit lever per `reference_sl_loss_levers`: AE restricted by
symbol/regime. Blanket AE threshold sweeps {−2..−6%} are DEAD (do-not-retry).
Hypothesis source: the 2026-05-07 replay (n=117, pre-Sentinel exits) — AE-off
was −$8.27 worse overall, SUI/ETH/LINK benefited from AE, CI bracketed zero.

## Rig changes (research-only, live files untouched)

Added to `scripts/calibrate_exits.py`: `--ae-threshold`, `--ae-cycles`,
`--ae-symbols` (comma allowlist), `--ae-regime` (comma allowlist of the
bot's 5m regime labels via `backtest._classify_regime_label`, computed at the
entry candle with no lookahead). Default None = AE off (−999/10) = prior
hardcode exactly. py_compile clean.

**Regression check: PASS.** No-flag run (arm-8) reproduces the pre-change
baseline `reports/trail_june_arm8.json` with totals identical and 0 per-row
diffs (sim_net $+14.57, n=86).

## Variants (all AE −5% ROI, 10 cycles)

| run | gate | sim_net | Δ vs baseline | H1/H2 Δ | rescues | clipped |
|---|---|---|---|---|---|---|
| baseline | — | +$14.57 | — | — | — | — |
| sym57 | SUI,ETH,LINK | +$13.97 | **−$0.60** | +0.00 / −0.60 | 1 (+$0.40) | 1 (−$1.00) |
| symworst | XLM,INJ,TAO | +$14.06 | **−$0.51** | +0.01 / −0.52 | 6 (+$3.59) | 4 (−$4.10) |
| regchoppy | regime=CHOPPY | +$9.72 | **−$4.85** | −1.88 / −2.97 | 15 (+$6.47) | 11 (−$11.32) |
| regtrendvol | TRENDING_UP/DOWN, VOLATILE | +$6.69 | **−$7.88** | −3.99 / −3.89 | 5 (+$2.70) | 10 (−$10.58) |

Symbol-pick receipts:
- **sym57**: 5/7-era beneficiaries. HONESTY: SUI and LINK have ZERO June
  trades — this variant is effectively ETH-only, n=5 eligible, 2 AE fires.
  The 5/7 beneficiary list did not survive the era change even as a universe.
- **symworst**: current-era top-3 exchange_close loser symbols, derived from
  `trading_state.json` June htf_l2 closed trades — XLM −$4.40 (3 losers),
  INJ −$2.82 (2), TAO −$1.49 (1). In-sample pick (chosen on the same window
  it's tested on) — and it STILL loses.
- Regime data available in rig: yes (`_classify_regime_label` port of
  bot.py `_classify_regime`). June entry mix: CHOPPY 52, TRENDING_UP 20,
  TRENDING_DOWN 6, VOLATILE 5, QUIET 3. regchoppy = where the losers live
  (20/27 baseline losers; in-sample pick). regtrendvol = the continuation
  prior (adverse moves should continue in trends).

## Per-trade decomposition — same killer as every prior AE variant

Caps > rescues in ALL four variants. Mechanics are stable across gates:
- A rescue converts an exchange_close at the −1.2% SL into an AE cut at
  ~−0.5% price → saves ~$0.4–0.7 per rescue.
- A clip converts a would-be winner (mostly `early_exit` +$0.3–0.9, plus two
  big recoveries: ZEC +$1.58 and WLD +$1.52 → −$0.6 each in regchoppy) into
  a ~−$0.5 loser → costs ~$0.7–2.2 per clip.
- Rescue ceiling is structurally smaller than clip cost, so even gating AE to
  the exact symbols/regimes where losses concentrate cannot go positive.
  This matches the DOA study finding inverted: the trades that dip below
  −5% ROI and then recover are exactly the avg-win engine (early_exit).

## Honesty guards

- Post-hoc splits: sym57 is out-of-era (list didn't transfer); symworst and
  regchoppy are in-sample picks — best-case framing, still negative.
- Candidate bar was: both-halves positive AND delta outside the rig's ±25%
  band. No variant clears even the first hurdle (no variant is positive in
  ANY half except two +$0.00/+$0.01 noise halves).
- Rig caveat: 77.8% of bars used bar-close fallback (thin flow coverage in
  June) — AE fires at bar-close prices there. Cuts both ways; the sign is
  consistent across all four gates and both halves, so not band-sensitive.
- All numbers read from tool output this session; dumps in `reports/`.

## Verdict

- **sym57 (SUI/ETH/LINK): NULL** — hypothesis untestable this era (SUI/LINK
  absent); the ETH-only remnant is negative (−$0.60, n=5).
- **symworst (XLM/INJ/TAO): DEAD** — in-sample best-case, still −$0.51,
  clips > rescues.
- **regchoppy: DEAD** — −$4.85, both halves negative.
- **regtrendvol: DEAD** — −$7.88, both halves negative, worst of all.

**Restricted AE is dead in every tested form. The exit-side lever inventory
(reference_sl_loss_levers) is now fully exhausted — including its last
surviving direction. Do not re-enable AE in any scope. Fix entries, not exits.**
