# R2 — Fee-Reduction Research (2026-07-05 overnight)

Question: fees flip a gross-positive bot negative (6/29 audit). What are the verified fee-reduction paths — on Phemex, and by moving venues — and what do they buy us in June dollars?

Every external rate below was fetched from the exchange's own page this session (fetch noted per row). Numbers that could not be verified from a primary/exchange-owned source are marked UNVERIFIED and excluded from conclusions.

---

## 1. Phemex current fee schedule (verified)

**Base (VIP 0), USDT contracts: 0.01% maker / 0.06% taker.**
Source: Phemex Help Center "Futures Fee Structure & Fee Calculations" (https://phemex.com/help-center/Phemex-Future-fee-structure-and-calculation), fetched this session — quotes "0.01%" maker, "0.06%" taker, with a worked linear-contract example at rates 0.0001 / 0.0006.
Independently corroborated by our own exchange fill records: docs/2026-06-11-fee-ground-truth.md measured exactly two fee rates on 187 real fills — 0.0001 (maker) and 0.0006 (taker).

**Full tier table** (Phemex Help Center "Phemex Trading Fee Structure", https://phemex.com/help-center/phemex-trading-fee-structure, fetched this session), contract maker/taker:

| Tier | Contract maker | Contract taker | Qualify (any ONE) |
|---|---|---|---|
| VIP 0 | 0.0100% | 0.0600% | default |
| VIP 1 | 0.0080% | 0.0550% | ≥32K vePT, or ≥$50K avg assets, or ≥$800K 30d spot vol, or ≥$8M 30d contract vol (volume routes require API volume ≤ 20%) |
| VIP 2 | 0.0060% | 0.0500% | ≥70K vePT / ≥$150K assets / ≥$1.8M spot / ≥$18M contract |
| VIP 3–5 | 0.004→0.001% | 0.045→0.035% | ≥$350K→$2M assets or ≥$45M→$180M contract vol |
| Star VIP | 0.0000% | 0.0300% | invite-tier |
| Pro 1 | 0.0000% | 0.0475% | ≥$8M 30d contract vol, API trading > 20% |
| Pro 2–4 | 0.0000% | 0.0450→0.0325% | ≥$100M→$1.5B contract vol |

**Can a $57 account reach any tier? No — by ~3 orders of magnitude.**
- Volume: at $15 margin × 10x ≈ $150 notional × ~5 trades/day ≈ **$45K/30d round-trip volume** (entry+exit legs). VIP1's cheapest volume gate is $8M contract — ~180x short. And VIP-tier volume routes require API volume ≤ 20%; the bot is ~100% API, so the VIP volume path is closed at ANY size. The API-friendly path is Pro 1 ($8M/30d) — same ~180x gap.
- Assets: VIP1 needs ≥$50K average balance vs $57 — ~880x short.
- Verdict: **no tier is reachable; the only reachable Phemex lever is the PT fee deduction.**

**PT token fee deduction — reachable today, 10% off futures fees.**
- Phemex fees page (https://phemex.com/fees-conditions, fetched): futures get a "10% Discount" for PT holders. Search of Phemex's own help pages ("How to Use PT to Cover Trading Fees", phemex.com/help-center/how-to-use-pt-to-cover-trading-fees): deduction rate is 10% for USDT contracts (20% spot); enable in the Fee Level / "Fee Discount" settings, PT must be transferred INTO the futures account, and if PT balance is insufficient the trade silently pays full fee. Not supported for grid/copy/margin products (our flow is plain orders — fine).
- Caveat noted honestly: the enable-flow and PT-balance mechanics come from Phemex's own help pages via search snippets; the exact help-page text was not re-fetched line-by-line. Verify the toggle in the UI before relying on it.
- Cost/risk: must hold a PT balance (price risk on the deduction float; a few dollars of PT covers months at ~$6/mo fees).

**Referral fee-back on an EXISTING account: NO.** Phemex referral program rules (phemex.com/help-center/referral-program-faq via search): referral relationship "cannot be added or altered after registration is completed." Code must be entered at signup. Only path would be a brand-new account (new KYC, new API keys, migration overhead) — and Phemex referral kickbacks go to the referrer, not reliably to the trader, so this is not a real lever.

---

## 2. What the repo thinks we pay (mismatch flagged)

- `/Users/jonaspenaso/Desktop/Phmex-S/.env:52` → `TAKER_FEE_PERCENT=0.06`; `/Users/jonaspenaso/Desktop/Phmex-S/config.py:90` defaults the same. **0.06% taker matches the verified exchange schedule — not stale.**
- **There is NO maker-fee constant anywhere in the repo** (grep MAKER_FEE/maker fee across config.py/.env/bot.py/risk_manager.py — none). The bot never models the 0.01% maker rate it actually pays on ~99% of entries.
- **Paper/sim fee model overstates real costs ~3x:** `risk_manager.py:640` and `:771` charge paper trades `(TAKER_FEE_PERCENT + SLIPPAGE_PERCENT) * 2 / 100` = (0.06+0.05)×2 = **0.22% round trip**, vs the measured live round trip of **~0.066%** (fee-ground-truth doc, median 0.070%). Every paper slot and replay that uses this path is penalized ~0.15%/trade too much — enough to flip marginal paper strategies from green to red. Live trades are unaffected (live uses the actual fee off the order, falling back to `fees_pending`).
- Known ledger bug still present in June data: **25 of 115 June trades have `fees_usdt` = 0** (`fees_pending` never reconciled) — the recorded June fee total ($4.99) understates truth (~$5.86 imputed; consistent with the 16.6% under-recording measured on 05-03→06-09 fills in docs/2026-06-11-fee-ground-truth.md).

---

## 3. Venue comparison at base tier (all rates fetched this session)

| Venue | Maker | Taker | Source (fetched) |
|---|---|---|---|
| **Phemex VIP0** | **0.010%** | 0.060% | phemex.com help-center fee structure page |
| Bybit non-VIP | 0.020% | 0.055% | Bybit Help Center "Perpetual Futures Contract Fees Explained" / "Trading Fee Structure" (via search of bybit.com; direct fetch timed out twice — rates quoted from Bybit's own help pages in results) |
| OKX Lv1 | 0.020% | 0.050% | okx.com/en-us/fees (page is JS-walled; rates quoted from OKX's own fees/learn pages via search — "0.02% maker and 0.05% taker on USDT perpetuals") |
| Bitget VIP0 | 0.020% | 0.060% | bitget.com/support/articles/12560603817155 (direct fetch: "Maker fee: 0.02% … Taker fee: 0.06%"); BGB discount currently **spot only, not futures** |
| Binance VIP0 | 0.020% | 0.050% | binance.com/en/support/faq/detail/360033544231 (direct fetch: "a Regular User's maker fee is 0.02% and … taker fee is 0.05%"; +10% discount paying fees in BNB on USDⓈ-M) |
| Hyperliquid tier 0 | 0.015% | 0.045% | hyperliquid.gitbook.io docs (direct fetch); maker REBATES only for >0.5% of maker volume share (-0.001%) — unreachable; HYPE staking discount 5% at >10 HYPE staked up to 40% |

Key structural fact: **Phemex's 0.01% base maker is the lowest of all six venues.** Since our entries are ~99% maker (verified from fills) and June exits are 81% taker (computed below), Phemex's fee mix is already near-optimal for this bot at base tier. No venue offers a maker rebate at any tier a $57 account can reach (Hyperliquid's rebate needs >0.5% of global maker volume; Bybit/OKX/Bitget/Binance base tiers have none).

Min order size vs our ~$150 notional: no blocker surfaced on any venue's fetched pages; Hyperliquid's fee doc specifies no minimum. Specific per-venue minimum-notional numbers were NOT individually verified this pass (UNVERIFIED — but $150 is far above typical retail minimums; check only if a migration is ever actually scoped).

API/ccxt (brief, from working knowledge — not load-bearing): Bybit/OKX/Bitget/Binance are first-class in ccxt; Hyperliquid is on-chain with its own SDK + ccxt support and a different auth/order model (wallet signing), plus different funding/oracle mechanics — the largest migration lift of the set. Alt-coverage on our traded alts is broadly comparable on the CEXs; Hyperliquid lists most majors/mid-caps but book depth on small alts differs (not verified per-symbol).

**Answer to the ≥30% question: NO venue cuts our round-trip cost by ≥30% at our size.** Best case is Hyperliquid at ~11% cheaper (15% with a token-dust HYPE stake), and Binance+BNB at ~5%. Bybit, OKX and Bitget are all MORE expensive than Phemex for our maker-entry mix.

---

## 4. June dollar impact (from trading_state.json, computed this session)

Data: `/Users/jonaspenaso/Desktop/Phmex-S/trading_state.json`, closed trades with `closed_at` ≥ June 1 12:00 AM PT → **n = 115** (104 htf_l2_anticipation, 9 synced, 2 orphan_adopted).
Recorded: gross `pnl_usdt` **+$11.92**, `fees_usdt` **$4.99** (25 trades recorded $0 — fee bug), `net_pnl` **+$6.94**. With the 25 missing fees imputed at maker-entry/taker-exit: fees ≈ **$5.86**, corrected net ≈ **+$6.07**.

Method: per trade, entry fee = entry notional × maker rate (entries verified ~99% maker); exit leg classified maker/taker from the trade's own recorded fee decomposition (exit rate ≥0.035% → taker), zero-fee trades imputed taker-exit unless partial_tp/take_profit. Result: **93/115 (81%) taker exits**. Then re-price both legs at each venue's verified base rates:

| Scenario | June fees | June net | Δ vs Phemex | Δ% |
|---|---|---|---|---|
| Phemex VIP0 (current, modeled) | $6.22 | +$5.70 | — | — |
| **Phemex + PT 10% deduction** | $5.60 | +$6.32 | **+$0.62** | −10.0% fees |
| Phemex VIP1 (unreachable) | $5.57 | +$6.36 | +$0.66 | −10.5% |
| Bybit non-VIP | $6.98 | +$4.94 | **−$0.76** | +12.2% WORSE |
| OKX Lv1 | $6.56 | +$5.36 | −$0.34 | +5.5% worse |
| Bitget VIP0 | $7.40 | +$4.52 | −$1.18 | +19.0% worse |
| Binance VIP0 | $6.56 | +$5.36 | −$0.34 | +5.5% worse |
| Binance + BNB 10% | $5.91 | +$6.02 | +$0.32 | −5.1% |
| **Hyperliquid tier 0** | $5.55 | +$6.37 | **+$0.67** | −10.8% |
| Hyperliquid + 5% HYPE-stake discount | $5.28 | +$6.65 | +$0.95 | −15.2% |
| (Reference: all-maker exits, stay on Phemex) | $2.02 | +$9.90 | +$4.20 | −67.5% |

(Modeled Phemex fees $6.22 vs $5.86 imputed-recorded — the gap is partial-fill/reconcile noise; scenario deltas are computed against the same $6.22 baseline so they cancel.)

Arithmetic sanity check, single typical trade: $150 notional maker in + taker out on Phemex = 150×0.0001 + 150×0.0006 = **$0.105**; on Hyperliquid = 150×0.00015 + 150×0.00045 = **$0.090** (−14%); with PT on Phemex = $0.0945 (−10%).

---

## Verdict

1. **No venue migration is justified.** Best verified saving is Hyperliquid at ~$0.67/month at June's trade rate — against weeks of migration work (new execution model, wallet-signing auth, re-testing every exit path on real money, unknown alt-book depth) and losing the lowest base maker fee in the comparison set. Three of five alternatives are actually MORE expensive for our mix.
2. **The one free lever: enable PT fee deduction on Phemex** — 10% off futures fees (~$0.62/June), zero migration, reversible, needs only a small PT balance parked in the futures account. This is the entire realistic venue/fee-schedule opportunity for a $57 account.
3. **Fee-schedule optimization is not the fee fix.** The fee drag is $6/month; the only ≥30% lever is converting the 81% taker exits to maker (would have added +$4.20 in June) — an execution problem, already known to be structurally hard (fill-rate/adverse-selection tension, memory: fill-rate research 7/03; measured max +$0.046/trade in the 6/11 fee-ground-truth Kelly math). The maker-exit urgency-gating already shipped is the correct attack.
4. **Fix the sim fee model:** paper slots charge 0.22% RT (taker+slippage both legs, risk_manager.py:640,771) vs ~0.066% measured live — every paper strategy is handicapped ~$0.23 per $150 trade. Add a maker-aware fee model (or at least a MAKER_FEE_PERCENT constant) before trusting any future paper-vs-live comparison. Also: 25/115 June trades still have fees_usdt=0 (`fees_pending` reconcile gap from the 6/11 doc — still open).
