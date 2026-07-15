#!/usr/bin/env python3
"""Scale screen 2026-07-15: what changes at $250 / $500 balance vs today's ~$46.

READ-ONLY: public order books + fetch_balance only. No orders, no state writes.
Every constant below is sourced:
  - Halt rule: bot.py:120-131  _should_halt_daily_loss -> max(3% x balance, $5)
  - Trade size / leverage / SL / max open: .env:9-11,22,64
    (LEVERAGE=10, TRADE_AMOUNT_USDT=15, MAX_OPEN_TRADES=3, STOP_LOSS_PERCENT=1.2,
     MIN_TRADE_MARGIN=15)
  - Full-SL cost: mean net of the 12 closed main-book trades with margin 14.5-15.5
    and exit stop_loss/exchange_close and net < -$1.50 in trading_state.json
    (computed live below from the state file, read-only)
  - MR 90d: reports/mr_variant_grid_90d.json V0_baseline net=+7.8336, n=309 @ $15 margin
  - Carry: memory reference_basis_carry_screen_2026-07-14.md best case $0.16/mo @ $46 (linear)
  - ETH-TSM paper record: trading_state_ETH_TSM_28.json (read live below)
"""
import json
import os
import sys

REPO = "/Users/jonaspenaso/Desktop/Phmex-S"
OUT = os.path.join(REPO, "scripts/research/scale-screen-2026-07-15")

BALANCES = [None, 250.0, 500.0]  # None -> live balance
HALT_PCT, HALT_FLOOR = 0.03, 5.0          # bot.py:120-131
LEV, MARGIN_NOW, MAX_OPEN, SL_PCT = 10, 15.0, 3, 1.2  # .env:9-11,22


def halt_threshold(bal):
    return max(bal * HALT_PCT, HALT_FLOOR)


def main():
    out = {}

    # ---- ground truth: full-SL cost from main state file ----
    st = json.load(open(os.path.join(REPO, "trading_state.json")))
    sl_trades = [t for t in st["closed_trades"]
                 if t.get("margin") and 14.5 <= t["margin"] <= 15.5
                 and t.get("exit_reason") in ("stop_loss", "exchange_close")
                 and t["net_pnl"] < -1.5]
    sl_cost = sum(t["net_pnl"] for t in sl_trades) / len(sl_trades)
    sl_frac_of_margin = abs(sl_cost) / 15.0   # margins are ~$15 in this sample
    out["full_sl"] = {"n": len(sl_trades), "mean_net": round(sl_cost, 4),
                      "frac_of_margin": round(sl_frac_of_margin, 5),
                      "source": "trading_state.json closed_trades, margin 14.5-15.5, big-loss stop exits"}

    # ---- MR live record + symbol list ----
    mr = json.load(open(os.path.join(REPO, "trading_state_5m_mean_revert.json")))
    mr_ct = mr["closed_trades"]
    mr_net = sum(t.get("net_pnl", t["pnl_usdt"]) for t in mr_ct)
    mr_syms = sorted(set(t["symbol"] for t in mr_ct))
    out["mr_live_record"] = {"n": len(mr_ct), "net": round(mr_net, 4),
                             "symbols": mr_syms,
                             "source": "trading_state_5m_mean_revert.json"}

    # ---- MR 90d backtest baseline ----
    grid = json.load(open(os.path.join(REPO, "reports/mr_variant_grid_90d.json")))
    v0 = next(r for r in grid["results"] if r["name"] == "V0_baseline")
    out["mr_90d_v0"] = {"net": v0["net"], "n": v0["n"], "ci_per_trade": v0["ci"],
                        "win_rate": v0["win_rate"],
                        "source": "reports/mr_variant_grid_90d.json V0_baseline"}

    # ---- ETH-TSM paper record ----
    tsm = json.load(open(os.path.join(REPO, "trading_state_ETH_TSM_28.json")))
    tsm_ct = tsm["closed_trades"]
    out["eth_tsm_paper"] = {
        "n_closed": len(tsm_ct),
        "trades": [{"net": t["net_pnl"], "margin": t["margin"],
                    "reason": t["exit_reason"],
                    "days_held": round(t["duration_s"] / 86400, 2)} for t in tsm_ct],
        "open_positions": list(tsm["positions"].keys()),
        "source": "trading_state_ETH_TSM_28.json"}

    # ---- live balance via ccxt (read-only) ----
    import ccxt
    keys = {}
    for line in open(os.path.join(REPO, ".env")):
        line = line.strip()
        if line.startswith("API_KEY="):
            keys["apiKey"] = line.split("=", 1)[1]
        elif line.startswith("API_SECRET="):
            keys["secret"] = line.split("=", 1)[1]
    ex = ccxt.phemex({"apiKey": keys.get("apiKey"), "secret": keys.get("secret"),
                      "enableRateLimit": True})
    ex.load_markets()
    bal = ex.fetch_balance({"type": "swap", "code": "USDT"})
    live_bal = bal["USDT"]["total"]
    out["live_balance_usdt"] = live_bal
    out["live_balance_free"] = bal["USDT"]["free"]

    # ---- fee metadata from exchange ----
    ethm = ex.market("ETH/USDT:USDT")
    out["fees"] = {"perp_maker": ethm.get("maker"), "perp_taker": ethm.get("taker"),
                   "source": "ccxt phemex market('ETH/USDT:USDT') maker/taker fields (live)"}
    ftiers = ex.describe().get("fees", {})
    out["fees"]["ccxt_fee_struct"] = ftiers.get("trading", {})

    # ---- halt math per balance ----
    rows = []
    for b in BALANCES:
        B = live_bal if b is None else b
        thr = halt_threshold(B)
        # margin that keeps exactly 2 full SLs under the halt:
        # 2 * sl_frac_of_margin * M <= thr  ->  M = thr / (2*sl_frac)
        m_2sl = thr / (2 * sl_frac_of_margin)
        m_prop = MARGIN_NOW * B / live_bal
        rows.append({
            "balance": round(B, 2),
            "halt_thr": round(thr, 4),
            "halt_branch": "3%" if B * HALT_PCT > HALT_FLOOR else "$5 floor",
            "full_sl_at_15margin": round(sl_cost, 3),
            "n_full_15margin_SLs_under_halt": int(thr / abs(sl_cost)),
            "margin_proportional": round(m_prop, 2),
            "sl_cost_at_prop_margin": round(-sl_frac_of_margin * m_prop, 3),
            "n_prop_SLs_under_halt": int(thr / (sl_frac_of_margin * m_prop)),
            "margin_keeping_2_SLs": round(m_2sl, 2),
            "mr_90d_naive_at_prop_margin": round(v0["net"] * m_prop / 15.0, 2),
            "mr_90d_naive_at_2sl_margin": round(v0["net"] * m_2sl / 15.0, 2),
            "concurrency_3x_prop_margin_pct_bal": round(100 * 3 * m_prop / B, 1),
            "concurrency_3x_2sl_margin_pct_bal": round(100 * 3 * m_2sl / B, 1),
        })
    out["halt_math"] = rows
    out["halt_crossover_balance"] = HALT_FLOOR / HALT_PCT  # 3%*B = $5

    # ---- carry recompute (linear in balance; source: 7/14 memory file) ----
    CARRY_BEST_MO_AT = (0.16, 46.0)  # $0.16/mo at $46, reference_basis_carry_screen_2026-07-14.md
    out["carry"] = {b if b else round(live_bal, 2):
                    round(CARRY_BEST_MO_AT[0] * (live_bal if b is None else b) / CARRY_BEST_MO_AT[1], 2)
                    for b in BALANCES}
    out["carry_source"] = "reference_basis_carry_screen_2026-07-14.md best-case $0.16/mo @ $46, linear"

    # ---- order book depth for MR symbols vs hypothetical order sizes ----
    order_notionals = {"today_$15m_10x": MARGIN_NOW * LEV}
    for b in (250.0, 500.0):
        m_prop = MARGIN_NOW * b / live_bal
        m_2sl = halt_threshold(b) / (2 * sl_frac_of_margin)
        order_notionals[f"prop_${b:.0f}"] = round(m_prop * LEV, 0)
        order_notionals[f"2slsafe_${b:.0f}"] = round(m_2sl * LEV, 0)
    out["order_notionals"] = order_notionals

    books = {}
    for sym in mr_syms:
        try:
            ob = ex.fetch_order_book(sym, limit=20)
            def usd(levels, n):
                return sum(p * q for p, q in levels[:n])
            bb_p, bb_q = ob["bids"][0][0], ob["bids"][0][1]
            ba_p, ba_q = ob["asks"][0][0], ob["asks"][0][1]
            books[sym] = {
                "best_bid": bb_p, "best_ask": ba_p,
                "spread_bps": round((ba_p - bb_p) / ((ba_p + bb_p) / 2) * 1e4, 2),
                "top_bid_usd": round(bb_p * bb_q, 0),
                "top_ask_usd": round(ba_p * ba_q, 0),
                "bid5_usd": round(usd(ob["bids"], 5), 0),
                "ask5_usd": round(usd(ob["asks"], 5), 0),
            }
        except Exception as e:  # noqa: BLE001
            books[sym] = {"error": str(e)[:120]}
    out["order_books"] = books
    out["order_books_ts"] = ex.iso8601(ex.milliseconds())

    with open(os.path.join(OUT, "out.json"), "w") as f:
        json.dump(out, f, indent=1)

    # ---- printable summary ----
    print(f"LIVE BALANCE: ${live_bal:.2f} (free ${out['live_balance_free']:.2f})")
    print(f"Full-SL cost @$15 margin: mean {sl_cost:+.3f} over n={len(sl_trades)}"
          f" -> {100*sl_frac_of_margin:.2f}% of margin")
    print(f"Halt crossover (3% overtakes $5): ${out['halt_crossover_balance']:.2f}")
    print(f"MR live: n={len(mr_ct)} net {mr_net:+.2f} | MR 90d V0: net {v0['net']:+.2f} n={v0['n']}")
    for r in rows:
        print(json.dumps(r))
    print("CARRY $/mo:", out["carry"])
    print("ORDER NOTIONALS:", order_notionals)
    print(f"FEES: maker={out['fees']['perp_maker']} taker={out['fees']['perp_taker']}")
    for s, bk in books.items():
        print(s, json.dumps(bk))


if __name__ == "__main__":
    sys.exit(main())
