# R5 — Patient Maker-Exit Study (2026-07-05 overnight)

Question: can the already-built patient maker-exit machinery cut the taker-exit fee leak (r2_fee_research.md: 81% of June exits taker; all-maker exits would have added +$4.20 in June)? Exit GEOMETRY is out of scope (closed dead-end) — this is exit EXECUTION only.

**Verdict: NOT-WORTH-IT.** The machinery is already live on every low-urgency exit path and has a measured **0/13 live fill rate** at 25s patience. The only untouched candidate (early_exit) has **negative EV under every fill assumption** (−$0.05 to −$0.11/trade). And the proposed lever — `MAKER_EXIT_ENABLED=true` — is **inert**: flipping it changes no behavior at all (receipts below).

---

## 1. Code map — how exits route today (verified this session)

### The router is the `urgent` flag, not the config flag

`close_long(symbol, amount, urgent=True)` / `close_short(...)` — exchange.py:496, 551:
- `urgent=True` (default): straight to `create_market_*_order` reduceOnly = **taker**, no maker attempt ever (exchange.py:517-520, 568-571).
- `urgent=False`: post-only limit at the touch via `_try_limit_exit(..., patience_s=PATIENT_EXIT_PATIENCE_S)` (exchange.py:512-513, 563-564), 25s rest (exchange.py:589), then cancel-by-id + market fallback.

### Who passes `urgent=False` (patient-maker today)
| Exit path | Site | Status |
|---|---|---|
| flat_exit | bot.py:1058-1060 | patient since 6/12 edge bundle |
| time_exit / hard_time_exit | bot.py:1173-1175 | patient |
| software take_profit (cycle path) | bot.py:1248-1252 (`urgent = reason != "take_profit"`) | patient |
| ST2.0 slot non-adverse closes | bot.py:3045-3047 | slot demoted to paper — inactive |

### Who stays taker-market (`urgent` defaults True)
| Exit path | Site |
|---|---|
| **early_exit** | bot.py:1030-1032 |
| **trailing_stop / stop_loss (cycle path)** | bot.py:1250-1252 (urgent because reason ≠ take_profit) |
| **live exit watcher** — enforces trailing/SL/TP breaches at ~1s; most trailing_stop exits actually route here | bot.py:2556-2558 |
| adverse_exit | bot.py:1111-1113 (threshold −999, disabled) |
| trend-flip exit | bot.py:1085-1087 |
| partial TP scale-out | bot.py:977-979 |
| sentinel kill / crumb close / slot demote | bot.py:774-776, 1722-1724, 2324-2325, 2954-2955 |
| **exchange_close** (exchange SL bracket fill) | not a bot close at all — resting exchange order; **stays as-is, safety, non-negotiable** |

### MAKER_EXIT_ENABLED is a dead switch
- Not set in `.env` (grep: absent) → default false (config.py:107).
- `_try_limit_exit` enters the patient branch on `patience_s is not None or Config.MAKER_EXIT_ENABLED` (exchange.py:643), and an explicit `patience_s` takes precedence (exchange.py:645).
- Its ONLY two call sites (exchange.py:512-513, 563-564) **always pass explicit `patience_s=25.0`**. Urgent closes never reach `_try_limit_exit` at all.
- Therefore `MAKER_EXIT_ENABLED=true` + `MAKER_EXIT_PATIENCE_S=30` changes **nothing**: no code path exists where the flag is consulted with `patience_s=None`. Any experiment here is a **code change** (pass `urgent=False` on a chosen exit path, or raise `PATIENT_EXIT_PATIENCE_S` toward the 45s clamp at exchange.py:584), not a flag flip.

---

## 2. Live ground truth: the patient machinery fills 0%

Logs (bot.log through bot.log.5, coverage ~6/20 → 7/6):

- **13 patient maker-exit attempts** (`[MAKER EXIT] Limit ...`), all at 24s effective patience.
- **0 fills** (`[MAKER EXIT] Filled` count: 0), **0 partials**, 13× `Not filled in 24s, market fallback`.
- Attribution (log context): the attempts are **flat_exit and hard_time_exit** closes — i.e., the literally-lowest-urgency exits the bot has ("no momentum" by definition of flat_exit). Examples: BTC flat exits 7/04 1:05 AM / 10:55 AM PT, ETH flat exit 7/05 6:07 AM PT (halt day), DOGE hard_time_exit 7/02 11:20 AM PT.

**0/13 at the touch on quiet exits.** Exact binomial 95% upper bound ≈ 23% (rule of three, 3/13). This is the bot's own answer to "would resting 30-45s very likely fill?" — **no**, consistent with the fill-rate research (7/03): posting at the touch lands at the back of the queue; a fill needs the market to trade through you, which at 25s on a quiet tape mostly doesn't happen, and when it does it's the adverse-selection direction. The +$4.20/June all-maker figure in r2 is a **ceiling, not an achievable number** with this machinery.

---

## 3. June+ exit classification (trading_state.json, n=115, 6/02 → 7/05)

Method: entry leg assumed maker (verified ~99% in fee-ground-truth doc); exit-leg fee = `fees_usdt` − 0.01%×entry notional; exit rate ≥0.035% → taker. Same method as r2.

| reason | n | taker | maker | zero-fee | fee≈1-leg-only |
|---|---|---|---|---|---|
| trailing_stop | 42 | 37 | 0 | 5 | 0 |
| exchange_close | 35 | 19 | 0 | 0 | 16 |
| early_exit | 18 | 12 | 0 | 6 | 0 |
| partial_tp | 6 | — | — | 6 (multi-leg, excluded) | — |
| flat_exit | 5 | 2 | 0 | 3 | 0 |
| stop_loss | 3 | 2 | 0 | 1 | 0 |
| min_margin_skip | 3 | crumbs, excluded | | | |
| hard_time_exit | 2 | 1 | 0 | 1 | 0 |
| take_profit | 1 | 1 | 0 | 0 | 0 |

- **Zero confirmed maker exits in June+** — matches the 0/13 log evidence.
- The 16 exchange_close rows with fee ≈ exactly 0.01%×one leg are the known fees_pending under-recording (r2 §2), not maker exits.
- Volume ceiling for the whole idea: 74 confirmed taker exits × ~$0.05 fee spread ≈ **$3.70/month** if every one filled maker — which nothing observed supports.

---

## 4. Drift/EV study — what a 30-45s rest would have done

Data: Phemex public 1m candles fetched around each of the 71 software-exit timestamps (cache: scratchpad candle_cache.json; script: scratchpad/maker_exit_study.py). Per taker exit:
- **Urgency** = adverse move over ~2-3 min before exit (close of T−3m candle vs exit fill).
- **Post drift** = next fully-post-exit 1m candle close vs exit fill, signed favorable-for-the-resting-order (+ = resting was free/better).
- **Touch** = post candle's high/low crossed the posting level (exit price ± entry-time spread, default 1bp); "through" = crossed by ≥2bps more. Touch ≠ fill (queue).
- **EV/trade** = P(fill)×feeSave(0.05%×notional) + (1−P(fill))×signed drift$ (i.e., no fill → market out 60-120s later, still taker). Bootstrap 95% CI, 10k resamples.

### Per-reason (taker exits only)
| reason | n | touch% | through% | median drift | mean drift$ | EV @touch-fill | EV @P(fill)=0 |
|---|---|---|---|---|---|---|---|
| early_exit | 12 | 50% | 33% | 0.0 bps | **−$0.082** | **−$0.100** | −$0.082 |
| trailing_stop | 37 | 70% | 65% | +4.5 bps | +$0.022 | −$0.011 | +$0.022 |
| stop_loss | 2 | 100% | 100% | +53 bps | +$0.309 | n<20 | n<20 |
| flat/time/tp | 4 | mixed | | | | already patient | |

### early_exit (the task's candidate) — NEGATIVE under every assumption
n=12 (⚠ <20, not statistically significant, but the sign is consistent):
| fill assumption | EV/trade | 95% CI | month (×12) |
|---|---|---|---|
| P(fill)=touch (optimistic) | −$0.100 | [−0.218, +0.004] | **−$1.20** |
| P(fill)=traded-through | −$0.111 | [−0.225, −0.008] | −$1.33 |
| P(fill)=0 (measured 0/13) | −$0.082 | [−0.215, +0.051] | −$0.99 |
| P(fill)=23% (rule-of-3 upper) | −$0.052 | [−0.153, +0.050] | −$0.62 |

Why: early_exit fires on momentum reversal — price keeps going against the position after the exit (INJ −46bps, WIF −48bps, ADA −33bps in the 60-120s window). These are HIGH-urgency exits wearing a soft name. Even the 5 genuinely low-urgency ones (<10bps adverse pre-move) net ≈ −$0.03 to −$0.11/month. Worst single trade: a 45s rest costs −$0.48 (WIF 6/27).

### trailing_stop — apparent +EV is a timing artifact, not a fee win
All-37 EV at measured P(fill)=0: +$0.022/trade [CI −0.034, +0.072] → +$0.80/month, **CI spans zero**. Crucially, at P(fill)=0 no maker order ever fills — the "gain" is purely *exiting 60-120s later than the trailing stop* (median +4.5bps bounce-back, the known 1s-watcher wick-enforcement trade-off). That is exit **timing/geometry**, the closed dead-end (SL-loss levers 7/02: full exit-geometry inventory dead), not execution. It also means delaying a protective exit — worst single trade −$0.48, worst-case month −$1.94 — on a path whose whole point is a deadline. Do not touch.

### exchange_close (35 exits, the June loss engine)
Stays an exchange-resting bracket. Non-negotiable: it is the only exit that survives host sleep / process death (lesson 6/24, −$1.42 XLM). Not analyzed for conversion.

---

## 5. Deliverable: is there a bounded experiment?

**No. NOT-WORTH-IT — three independent kills:**
1. **The lever doesn't exist as a flag.** `MAKER_EXIT_ENABLED=true` is provably inert (§1). Any experiment = code change on a real-money close path.
2. **The mechanism is already measured at 0/13 fills** on the bot's own lowest-urgency exits at 25s. Raising patience to the 45s clamp buys +80% rest time against a base rate of zero; expected fills ≈ 0, expected fee savings ≈ $0. (The r1 queue study / fill-rate research already identified the only real lever here: queue-state conditioning — post only into small/fresh queues — which is an ENTRY-side program.)
3. **The one convertible reason (early_exit) has negative EV** under every fill assumption, including the most optimistic (−$0.62 to −$1.33/month at June volume). The positive-looking cell (trailing_stop @ P=0) is a disguised exit-geometry change with n=37, CI spanning zero, and protective-deadline risk.

Expected value of best defensible experiment (early_exit → `urgent=False`): **−$0.99/month** point estimate at June volume; worst case ≈ −$1.55/month + one −$0.48 single-trade tail; revert = one-line code change. Not proposed.

What would change this verdict: a measured patient-exit fill rate meaningfully above 0 (e.g., the MR slot's re-quote forward test showing maker exits fill when re-quoted rather than left resting), or queue-state-conditioned posting. Until fills exist, fee-spread savings are theoretical.

**Estimate quality:** exit classification = HIGH (exchange-recorded fees, method cross-checked vs r2's 81%). Fill rate = MEASURED live but n=13 (upper bound 23%). Drift = MODERATE (1m public candles, next-candle close proxies the 45-75s fallback; touch-test uses only the uncontaminated post candle, undercounts first-minute touches). EV = screening-grade; all sub-20 buckets flagged.

Receipts: scratchpad/maker_exit_study.py + candle_cache.json + study_rows.json (session scratchpad); logs bot.log–bot.log.5; trading_state.json closed_trades.
