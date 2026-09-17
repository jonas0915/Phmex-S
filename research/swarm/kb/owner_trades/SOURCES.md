# Owner trade-history investigation — sources and receipts

Investigated 2026-09-16, read-only. All numbers below were read directly from the files/endpoints
cited; bot was NOT started, nothing was written outside this directory except this file.
Account: Phemex userID 4034703 (API key confirmed working against `/Users/jonaspenaso/Desktop/Phmex-S/.env` `API_KEY`/`API_SECRET`).

## 1. LOCAL files (bot-generated only — no manual trades found)

| File | Rows (closed_trades) | Earliest | Latest | Manual or bot? |
|---|---|---|---|---|
| `trading_state_v8_245trades.json` | 245 | 2026-03-13 05:03:38 AM UTC / 2026-03-12 10:03:38 PM PDT (19 of these rows have no `opened_at` at all — oldest rows before the timestamp field existed) | 2026-03-20 10:07:13 PM UTC / 3:07 PM PDT | **Bot.** `reason` field on every row is one of `early_exit/stop_loss/exchange_close/time_exit` (bot exit taxonomy); margin is a fixed $10/$8.3 per trade; no `strategy`/timestamp fields until row 19 — consistent with the bot's earliest build, not manual clicking. |
| `trading_state.json` (main book, current) | 871 | same earliest as above (1773378218.49 = 2026-03-13 05:03:38 AM UTC) | 2026-09-10 12:40:51 AM UTC / 2026-09-09 5:40:51 PM PDT (this last row is `mode: paper`, not a real fill) | **Bot.** Schema includes `strategy`, `ensemble_layers`, `entry_snapshot`, `gate_tags` — all bot instrumentation. |
| All other `trading_state_<slot>*.json` | 2–136 each | ranges from 2026-03-28 to 2026-08-31 | up to 2026-09-10 | **Bot** (paper/live strategy slots). Same schema markers as above. |

Git repo first commit: `58c0509` "Add active crypto trading bot", **2026-03-07 21:25:36 +0000** (`git log --reverse`). This is 6 days before the earliest timestamped local trade (2026-03-13), consistent with the bot going live almost immediately after the repo was created — there is no local evidence of any manual trading before or after the bot existed. No `trading_state*.json`, reconciler output, or fee ledger in the repo contains a trade that looks manually placed (no round/odd-lot sizing outside the bot's fixed margins, no missing-strategy rows after row 19 of the earliest file).

`/Users/jonaspenaso/Desktop/Phmex-S-archive/` contains only the 1.97 GB market-data tar (`phmex-s-market-data-2026-09-09.tar.gz`) — no trade records, not opened (per instructions, not copied).

## 2. PHEMEX API (ccxt.phemex, read-only calls)

### a) USDT-margined perpetual fills — `fetch_my_trades`
- File: `api_my_trades_per_symbol.json` (200 rows; walked backward+forward per-symbol with `since=0` across the 51 symbols the bot ever traded, and cross-checked with an all-symbol aggregate walk — both hit the identical 200-row set, so this is exhaustive, not a partial page).
- **Earliest fill: 2026-07-29 02:33:06 PM UTC / 07:33:06 AM PDT** (AVAX/USDT:USDT).
- **Latest fill: 2026-09-07 10:29:43 PM UTC / 03:29:43 PM PDT** (ETH/USDT:USDT).
- 179 real fills (`info.tradeType=="1"`) + 21 funding settlement rows (`tradeType=="4"`) interleaved, per the known Phemex/ccxt behavior.
- **This floor is a hard wall, not a rolling 40-day window**: the same 2026-07-29 floor was already observed on 2026-09-07 (per `memory/reference_phemex_fees_funding_api_2026-09-07.md`, 40 days back from then) and is *still* 2026-07-29 today, 2026-09-16 (49 days back). If it were rolling it should have advanced to ~8/7. It has not moved — treat it as fixed, not "~40 days from now."
- Cross-check: local `trading_state.json` shows 2 trades closed after the 9/7 10:29 PM cutoff (LTC/USDT:USDT, 9/9 and 9/10) — both are `mode: paper`, so their absence from the real-fill API is expected and confirms the API floor is genuine, not a bug.
- `fetch_closed_orders(since=0)` — `api_closed_orders.json`, 200 rows, same window: 2026-08-12 to 2026-09-07 (narrower than trades; orders roll off faster than fills).
- Endpoints that require a `symbol` and rejected non-existent ones: `privateGetApiDataFuturesTrades`/`Orders` returned `"Missing parameter - symbol"` with none, and `"Symbol not supported"` for `BTCUSDT`/`BTCUSD` under both `futures` and `g-futures` prefixes — these history readers belong to the OLD inverse-contract product line only (see below), not the current USDT perp.

### b) OLD inverse (coin-margined, USD-settled) closed positions — **this is very likely the manual $20→ run**
- Endpoint: `private_get_phemex_user_order_closedpositionlist`, paginated with `offset`/`limit=200` until a short (<200) page confirmed exhaustion.
- File: `api_closed_pnl.json` — **819 rows total**.
- **Earliest: 2022-03-26 06:11:32 AM UTC / 2022-03-25 11:11:32 PM PDT** (LUNAOLDUSD).
- **Latest: 2023-02-16 12:16:06 AM UTC / 2023-02-15 04:16:06 PM PST** (ADAUSD).
- Symbols: ADAUSD, AVAXUSD, MATICUSD, XRPUSD, BTCUSD/uBTCUSD, ETHUSD, SOLUSD, BNBUSD, LINKUSD, DOGEUSD, MANAUSD, AAVEUSD, STORJUSD, APEUSD, APTUSD, GALAUSD, DASHUSD, MASKUSD, LUNAOLDUSD, u100ANKRUSD, u100TRYBUSD — all `currency: "USD"`, i.e. Phemex's legacy coin-margined "Standard Contract" line, distinct from the USDT-margined perps the bot trades. Leverage on individual rows ranges up to 100x (e.g. uBTCUSD row at 100x leverage) — consistent with someone manually running up a small account aggressively, not the bot (bot is pinned at 10x).
- Dollar values decoded: Phemex `*Ev` fields for this product use a value scale of 10^4 (`realizedPnlEv / 10000` = USD). Verified two independent ways: (1) ADAUSD row — manual notional recompute from `openPriceEp`/`closePriceEp`/`closedSize`/contract size matched `closedPnlEv/1e4` to the cent; (2) uBTCUSD row — same recompute against the known ~$46,580 BTC price on 2022-03-26 matched exactly.
- Cumulative realized PnL (sum of `realizedPnlEv/1e4` across all 819 rows, chronological): **starts near zero, drops to about –$1,968 by end of Oct 2022, then jumps to +$5,405 cumulative in Nov 2022 (one very large win), peaks at +$6,335.62 cumulative on 2022-11-10, and ends the window at +$4,857.22 cumulative** on 2023-02-16. This is a sum of realized PnL only — it is NOT account equity (excludes the actual deposit/withdrawal cash flows and any unrealized PnL), but the shape (deep drawdown → one huge Nov-2022 spike → leveling off ~$4,800–6,300) is fully consistent with an aggressively leveraged manual account that could plausibly have started at ~$20 and, at least briefly, been carrying several thousand dollars of realized gains — well past $500. I could not derive a clean $ equity curve without also using deposits/withdrawals (below), and did not attempt to force one given leverage/withdrawal noise; if the owner wants an exact equity line I can build `equity(t) = starting_balance + Σdeposits – Σwithdrawals + Σrealized_pnl(t)` next.
- No `total`/pagination-count field exists in the raw response; exhaustion was confirmed empirically (offset 800 → 19 rows, i.e., a short final page).

### c) Deposits — `private_get_exchange_wallets_depositlist`, paginated
- File: `api_deposit_list_full.json` — **112 rows total** (first page already returned all of them, <200).
- **Earliest: 2022-03-25 05:20:26 AM UTC / 2022-03-24 10:20:26 PM PDT** — 3000000000 raw units of XRP (an XRP deposit, not a dollar figure; I did not convert this to a USD-at-the-time value).
- **Latest: 2026-07-27 06:02:34 PM UTC / 11:02:34 AM PDT** — USDT.
- Deposits continue steadily from 2022 through 2026, including small USDT/ETH deposits in March 2026 right as the bot's git repo was created — i.e., the same account was topped up right before the bot went live.

### d) Withdrawals — `private_get_exchange_wallets_withdrawlist`, paginated
- File: `api_withdraw_list_full.json` — **68 rows total**.
- **Earliest: 2022-04-18 05:59:56 AM UTC / 2022-04-17 10:59:56 PM PDT** — USDT.
- **Latest: 2025-04-14 05:29:36 PM UTC / 10:29:36 AM PDT** — AVAX.
- A cluster of large ADA/XRP/MATIC withdrawals on 2022-11-09/10 lines up exactly with the huge PnL spike in the closed-position data above (2 cancelled withdrawals also present that day) — this is the point where the manual account looks like it took its biggest win and started cashing out.

### e) Current balance — `fetch_balance(type=swap)`
- File: `api_balance_swap.json`.
- **USDT-margined perp account balance right now: $87.120628536367 USDT** (`info.data.account.accountBalanceRv`). This matches the memory record from the 9/9 winddown ($87.12 idle) — cross-verified.
- Spot wallet (`api_balance_spot.json`/`api_balance.json`): small dust only (ADA, TRX, SOL, PT, PEPE, POL — all sub-$1 amounts), no USD/USDT.
- The old inverse "USD" currency wallet no longer exists on this account (`fetch_balance({'code':'USD'})` → `"Currency not supported"`), consistent with that product line having been fully closed out by Feb 2023.

### f) Endpoints tried that returned nothing useful
- `private_get_phemex_user_wallets_tradeaccountdetail` → `{"data": []}` (`api_trade_account_detail.json`).
- `ccxt.fetch_transfers()` → requires a `code` argument, not pursued further (transfers are internal account-to-account moves, not deposit/trade history).
- `private_get_assets_transfer` → `"Missing parameter - currency"`, not pursued (would only show internal spot↔futures moves, not external funding history — deposits/withdrawals above already cover that).

## 3. Phemex web UI export

I could not verify Phemex's website export range for this session — the web-search budget was exhausted before I could pull their help-center CSV-export article, and a direct fetch of a guessed help-center URL redirected to the generic help-center homepage with no specifics. **I did not guess at the export range.** What I can say from the API behavior above: Phemex's UI for "Order History"/"Closed P&L" almost certainly reads from the same backend as `closedPositionList` for the old inverse product (reaching back to 2022-03-26) and from the same ~fixed floor as `fetch_my_trades`/`fetch_closed_orders` for the current USDT perp (2026-07-29 onward) — so a web export is unlikely to reach further back than what's already captured in `api_closed_pnl.json` and `api_my_trades_per_symbol.json` in this folder. To confirm exactly, log into phemex.com → Assets/Orders → Order History (or Closed P&L) → look for an Export/Download CSV button and check what date range it lets you pick; if it offers a range earlier than 2022-03-26 or between 2023-02-16 and 2026-03-07, that would be new information this API investigation could not reach.

## 4. The unreachable gap

**2023-02-16 → 2026-03-07 (roughly 3 years) has no trade-level data anywhere I could reach.** Deposits/withdrawals show the account stayed active and funded through this whole period (steady USDT/ADA/XRP/MATIC deposits every 1–2 months, e.g. 2023-09 through 2026-03), so trading almost certainly continued — but:
- The old inverse `closedPositionList` endpoint has nothing after 2023-02-16 (the product line/account either stopped being used or Phemex's retention for it ended there).
- The USDT-perp `fetch_my_trades`/`fetch_closed_orders` only reach back to 2026-07-29.
- No local file has anything before the bot's first commit (2026-03-07).

If the owner traded manually on USDT-margined perps during 2023–2026 (the same product the bot uses today), that history is very likely gone from the API for good — Phemex's fill-history retention for that product appears to be capped at roughly 40–50 days, and it has already rolled past everything before 2026-07-29. The only remaining way to recover 2023–2026 is the Phemex web UI export described in §3, if Phemex retains it there longer than the API does — worth checking before concluding it's unrecoverable.
