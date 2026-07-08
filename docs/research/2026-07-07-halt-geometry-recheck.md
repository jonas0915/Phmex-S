# Halt-Geometry Recheck Under the $5 Floor — Does a Second Slow-Trend Slot Fit? (2026-07-07)

**Scope:** analysis only, no code changes. Re-runs the R5 slow-horizon sizing math
(docs/overnight-2026-07-05/r5_slow_horizon_research.md §6.3) with tonight's new
daily-loss halt: `today_net <= -max(3% × balance, $5.00)` (bot.py:108-120, read
this session; balance $59.73 per logs/bot.log 7/7 8:44 PM PT "Starting balance:
59.73 USDT" → budget = **$5.00**, vs $1.79 under the old 3%-only rule).

## Verdict

**No. BTC-TSM-28 still fails the halt math at today's balance** — one 0.001-BTC
minimum step ($62.76 notional at tonight's $62,763.7) risks **−$5.02 at the −8%
trend stop, which alone equals the entire new $5.00 daily budget** before the
scalper spends a cent of it. Under R5's own sizing formula it needs **balance
≈ $209** (single slot) to **≈ $268** (stacked with the ETH slot). The existing
ETH-TSM-28 slot, by contrast, goes from borderline (stop ≈ 98% of its old $1.43
allocation) to comfortable (**35% of the new $4.00 allocation, ~2.9× headroom**),
and 0.02 ETH now clears the halt math on paper — though the frozen forward-test
spec forbids resizing until verdict. One material code-truth discrepancy found
(§4): slot losses never actually feed `today_net`, so the R5/R6 "shared budget"
premise is economic, not mechanical.

## 1. R5's original methodology (exact, from the file)

- Formula (R5 §6.3): **max notional = budget × 0.8 / 0.08** — 3% budget, 20%
  reserved as "scalper headroom", divided by the −8% disaster stop. At the then
  budget $1.72: max notional ≈ **$17**.
- Verdicts then (R5 §6.3, prices 7/5-6: BTC $63,166 / ETH $1,770.51):
  ETH 0.01 step = $17.7 notional, stop ≈ **−$1.42** → accepted (barely: $1.42 vs
  the $1.38 = 0.8×$1.72 allocation — R5 accepted the ~3% overage).
  BTC 0.001 step = $63.2 notional, stop ≈ **−$5.05 — "triple the halt threshold;
  BTC is unusable at this account size with honest trend stops."**
- Candidate list: **BTC and ETH only.** The verified edge (Han/Kang/Ryu; market
  portfolio ~79% BTC+ETH, R5 §2.1) is BTC/ETH-specific; no other asset was
  evaluated, so there is no third candidate to re-admit. BTC's ONLY rejection
  reason was halt math — its edge evidence is the same as ETH's.
- Interaction treatment (R5 §6.3 impl. 2, §7.9, R6 §8): NOT worst-case stacking
  and NOT independence — a fixed 80/20 budget split, with "one trend stop-out +
  a normal scalper losing day can combine to halt everything" accepted and
  pre-registered as a KILL criterion if it happens twice.

## 2. The math re-run (new budget $5.00; prices + steps fetched this session)

Inputs fetched tonight: BTC $62,763.7 / ETH $1,752.34 (api.phemex.com/md/v2/ticker/24hr);
qtyStepSize BTC 0.001 / ETH 0.01 (api.phemex.com/public/products).
Scalper full-stop cost: **−$2.05** per full $15 stop (r2_halt_geometry.md §4,
empirical −13.66% of margin, n=21); worst normal scalper day ≈ 2 stops = **−$4.10**.

| Quantity | Old (3% rule) | New ($5 floor) | Source of method |
|---|---|---|---|
| Daily budget @ $59.73 | $1.79 | **$5.00** | bot.py:108-120 |
| Max trend notional (budget×0.8/0.08) | $17.9 | **$50.00** | R5 §6.3 formula |
| ETH 0.01 step: notional / stop | $17.52 / −$1.40 | same | ticker × step × 8% |
| ETH stop vs trend allocation (0.8×budget) | 98% ($1.40/$1.43) | **35% ($1.40/$4.00)** | computed |
| BTC 0.001 step: notional / stop | $62.76 / −$5.02 | same | ticker × step × 8% |
| BTC fits? ($62.76 vs max notional) | NO (3.5×) | **NO (1.26× over; stop = 100% of full budget)** | computed |
| Left for TSM if scalper stacks 2 stops first | −$2.31 (already halted) | **$0.90 → max notional $11.25 — even ETH fails worst-case stacking** | computed |
| ETH stop + 1 scalper stop vs budget | $3.45 vs $1.79 (halt) | $3.45 vs $5.00 (**survives, $1.55 spare**) | computed |
| ETH stop + 2 scalper stops | halt | $5.50 vs $5.00 → halt (the pre-registered kill pattern) | computed |

R5's chosen frame (80/20 split, kill-criterion on joint halts) says: ETH slot now
has ~2.9× headroom; a realistic joint bad day (one ETH trend stop + one full
scalper stop = −$3.45) no longer ends the day, where under the old rule even one
trend stop alone (−$1.40 vs −$1.79) left only $0.39 of scalper room.

## 3. Balance thresholds (R5 formula, tonight's prices)

- **BTC-TSM-28, single second slot:** needs budget ≥ $62.76 × 0.08 / 0.8 = **$6.28**.
  The $5 floor never reaches that; the 3% branch does at **balance ≥ ~$209**.
- **BTC + ETH slots together** (two trend stops can fire the same day — the 28d
  signals are the same regime bet, though not identical day-to-day: tonight the
  sidecar shows ETH ON / BTC replica OFF, eth_tsm_28_signal.json 7/8 record):
  budget ≥ ($5.02 + $1.40)/0.8 = **$8.03 → balance ≥ ~$268**.
- **ETH scale-up to 0.02 ETH** ($35.05 notional, stop −$2.80): needs budget ≥
  **$3.50**. Old rule: balance ≥ **~$117**. New rule: **$5.00 > $3.50 — fits at
  today's $59.73 already.** The floor pulled this forward by ~$57 of balance
  growth. (0.03 ETH needs budget $5.26 → balance ~$175.)
- Floor→percent crossover: **$166.67** (3% × 166.67 = $5.00).

## 4. Discrepancy found (surfaced, not resolved silently)

R6 §8 (r6_eth_tsm_build.md) states a live TSM disaster stop "lands in the same
realized-PnL daily budget as the scalper." **The code says otherwise:** the halt
sums main-bot trades only — `_compute_today_net_pnl(self.risk.closed_trades)`
(bot.py:1382); a live TSM stop-out is booked in the SLOT's book
(trading_state_ETH_TSM_28.json, R6 §2 reconcile Path A) and never enters
`today_net`. r2_halt_geometry.md §1 agrees: "Live-slot trades are NOT counted
toward today_net." The interaction is **one-directional**: a scalper-tripped
halt blocks TSM live entries (`.pause_trading` check, bot.py:3410-3412), but a
TSM stop cannot trip or consume the halt. So §2-§3 above is the R5 *sizing
discipline* (self-imposed risk budget), not a mechanical trip condition — the
conservative frame R5 sized with, kept here deliberately. If Jonas ever wants
slot losses to count toward the halt, that is a code change, not a config one.

## 5. Verdict detail + non-halt constraints the floor does NOT relax

1. **Second slot now?** No. BTC is the only rejected candidate and still fails:
   its single-step stop (−$5.02) consumes 100% of the new budget by itself.
   Fits at ~$209 balance alone, ~$268 alongside the ETH slot (both at tonight's
   BTC price — the threshold moves with price).
2. **Unchanged constraints** (halt floor does nothing for these):
   - **Forward-test integrity:** ETH-TSM-28 is on day 2 of a frozen,
     pre-registered 6-month spec ("no mid-test parameter edits", R5 §7) and is
     still PAPER (sidecar mode "paper"). Adding a slot or resizing to 0.02 ETH
     before a verdict changes the experiment mid-flight.
   - **Correlation:** a BTC slot duplicates the same slow-trend regime bet; R5
     §7.1 pre-registered the answer — log the BTC replica signal (already live
     in the sidecar) and compare later, don't trade it.
   - **Edge decay threat:** Rosen & Wang (R5 §8) unverified — flagged as the
     thing to check "before scaling beyond the forward test."
   - **Min-lot granularity:** BTC has nothing between $0 and $62.76 notional.
3. **Cost of the floor, stated honestly:** $5.00 is **8.4% of the $59.73
   balance** — the floor buys stop headroom by accepting daily drawdowns nearly
   3× deeper than the old 3% rule until balance reaches $166.67.

## Sources

- r5_slow_horizon_research.md §2.1, §6.1, §6.3, §7, §8 — methodology + original numbers
- r6_eth_tsm_build.md §4, §8 — deployed size (0.01 ETH, 3x isolated, margin ≈ $5.90 at build) 
- r2_halt_geometry.md §1, §4 — halt mechanics, −$2.05 empirical full stop, today_net scope
- bot.py:108-120 (new halt), 1382-1384 (call site), 3410-3412 (TSM halt gate), 504-517 (slot def) — read this session
- logs/bot.log 7/7 8:44 PM PT — balance $59.73
- api.phemex.com/md/v2/ticker/24hr (BTC $62,763.7 / ETH $1,752.34) + /public/products (steps 0.001 / 0.01) — fetched this session
- eth_tsm_28_signal.json — sidecar: paper mode, ETH signal ON, BTC replica OFF (7/8 UTC record)
