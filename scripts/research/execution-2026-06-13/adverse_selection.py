#!/usr/bin/env python3
"""
Adverse selection on maker fills.

Question: when a passive limit order DOES fill, which way does mid go next?
A passive BUY at best bid fills when a sell trade prints <= bid. After the fill,
a NEGATIVE forward mid move = adverse (price kept dropping after you bought).

Alignment: use 'et' (exchange event time). Trades are logged in batches sharing
one receive 'ts'; 'et' is the only reliable per-event clock. Book 'et' tracks
'et' within ~140ms and is monotonic.

Read-only. Data: logs/l2_ticks/<SYM>/2026-06-13.jsonl (book) + trades-2026-06-13.jsonl
06-12 has book only (no trades) -> excluded.
"""
import json, bisect, statistics, sys

SYMS = {
    "BTC": "logs/l2_ticks/BTC_USDT_USDT",
    "ETH": "logs/l2_ticks/ETH_USDT_USDT",
    "INJ": "logs/l2_ticks/INJ_USDT_USDT",
    "ARB": "logs/l2_ticks/ARB_USDT_USDT",
}
DATE = "2026-06-13"
HORIZONS = [1, 5, 30, 60]  # seconds
MAKER_FEE = 0.0001  # 0.01% per side
# "recent down move" lookback for reversion conditioning
DOWN_LOOKBACK_S = 30
DOWN_THRESH_BPS = 2.0  # mid must have dropped >= this many bps over lookback


def load_book(path):
    """Return parallel arrays: et[], bid[], ask[], mid[] sorted by et."""
    ets, bids, asks, mids = [], [], [], []
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            b = d["b"]; a = d["a"]
            if not b or not a:
                continue
            bid = b[0][0]; ask = a[0][0]
            if bid <= 0 or ask <= 0 or ask < bid:
                continue
            et = d["et"]
            # enforce monotonic et for bisect correctness
            if ets and et < ets[-1]:
                et = ets[-1]
            ets.append(et); bids.append(bid); asks.append(ask)
            mids.append((bid + ask) / 2.0)
    return ets, bids, asks, mids


def load_trades(path):
    out = []
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            d = json.loads(line)
            out.append((d["et"], d["px"], d["sz"], d["side"]))
    out.sort(key=lambda r: r[0])
    return out


def book_at(ets, vals, t):
    """Most recent book value at-or-before time t. None if before first book."""
    i = bisect.bisect_right(ets, t) - 1
    if i < 0:
        return None
    return vals[i]


def pct(xs, p):
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * p
    f = int(k)
    if f + 1 < len(s):
        return s[f] + (s[f + 1] - s[f]) * (k - f)
    return s[f]


def analyze(sym, bdir):
    ets, bids, asks, mids = load_book(f"{bdir}/{DATE}.jsonl")
    trades = load_trades(f"{bdir}/trades-{DATE}.jsonl")
    if not ets or not trades:
        return None

    book_t0, book_t1 = ets[0], ets[-1]

    # Spread stats (bps of mid) over book snapshots
    spreads_bps = []
    for bid, ask, mid in zip(bids, asks, mids):
        spreads_bps.append((ask - bid) / mid * 1e4)
    half_spread_bps_median = pct(spreads_bps, 0.5) / 2.0
    half_spread_bps_mean = (sum(spreads_bps) / len(spreads_bps)) / 2.0

    # Collect passive BUY fills: sell trade px <= current best bid
    # Forward mid move in bps (positive = mid rose after we bought = favorable)
    buy_fills = []   # list of dict per fill
    for (tet, px, sz, side) in trades:
        if side != "sell":
            continue
        if tet < book_t0 or tet > book_t1:
            continue
        bid = book_at(ets, bids, tet)
        mid0 = book_at(ets, mids, tet)
        if bid is None or mid0 is None:
            continue
        if px <= bid:  # passive buy at best bid would fill
            fwd = {}
            ok = True
            for h in HORIZONS:
                m1 = book_at(ets, mids, tet + h * 1000)
                if m1 is None or tet + h * 1000 > book_t1:
                    fwd[h] = None
                else:
                    fwd[h] = (m1 - mid0) / mid0 * 1e4  # bps
            # recent down-move conditioning (mimics reversion long setup)
            m_prev = book_at(ets, mids, tet - DOWN_LOOKBACK_S * 1000)
            down_move_bps = None
            if m_prev is not None and tet - DOWN_LOOKBACK_S * 1000 >= book_t0:
                down_move_bps = (mid0 - m_prev) / m_prev * 1e4
            buy_fills.append({"et": tet, "mid0": mid0, "fwd": fwd,
                              "down": down_move_bps})

    return {
        "sym": sym,
        "book_t0": book_t0, "book_t1": book_t1,
        "n_book": len(ets), "n_trades": len(trades),
        "half_spread_bps_median": half_spread_bps_median,
        "half_spread_bps_mean": half_spread_bps_mean,
        "spread_bps_median": pct(spreads_bps, 0.5),
        "buy_fills": buy_fills,
    }


def fwd_table(fills, key=None):
    """Aggregate forward-move stats per horizon. key filters fills."""
    rows = {}
    sel = [f for f in fills if (key is None or key(f))]
    n = len(sel)
    for h in HORIZONS:
        vals = [f["fwd"][h] for f in sel if f["fwd"][h] is not None]
        if not vals:
            rows[h] = None
            continue
        adverse = sum(1 for v in vals if v < 0)  # mid dropped after passive buy
        rows[h] = {
            "n": len(vals),
            "mean": sum(vals) / len(vals),
            "median": pct(vals, 0.5),
            "pct_adverse": 100 * adverse / len(vals),
        }
    return n, rows


def fmt_row(label, n, rows):
    out = [f"  {label:<28} (n={n})"]
    for h in HORIZONS:
        r = rows[h]
        if r is None:
            out.append(f"    {h}s: no data")
        else:
            out.append(f"    {h:>3}s | mean {r['mean']:+7.3f} bps | median {r['median']:+7.3f} bps | %adverse {r['pct_adverse']:5.1f}% | n={r['n']}")
    return "\n".join(out)


def main():
    import datetime
    def fmt(ms):
        return datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).strftime("%H:%M:%S UTC")

    results = {}
    for sym, bdir in SYMS.items():
        r = analyze(sym, bdir)
        if r:
            results[sym] = r

    print("=" * 78)
    print("ADVERSE SELECTION ON MAKER FILLS  (passive BUY at best bid, fills on sell prints)")
    print("Forward mid move in bps. NEGATIVE = adverse (price kept falling after you bought).")
    print("Date 2026-06-13 only (06-12 has no trades file). Clock = exchange et.")
    print("=" * 78)

    for sym, r in results.items():
        print(f"\n########## {sym} ##########")
        print(f"book {fmt(r['book_t0'])} -> {fmt(r['book_t1'])}  "
              f"({(r['book_t1']-r['book_t0'])/3.6e6:.2f}h)  "
              f"book_snaps={r['n_book']}  trades={r['n_trades']}")
        print(f"spread median {r['spread_bps_median']:.3f} bps  "
              f"-> half-spread captured ~{r['half_spread_bps_median']:.3f} bps (median) "
              f"/ {r['half_spread_bps_mean']:.3f} bps (mean)")

        fills = r["buy_fills"]
        print(f"passive BUY fills detected: {len(fills)}")

        # (A) ALL fills
        n, rows = fwd_table(fills)
        print("\n[A] ALL passive-buy fills -- forward mid move:")
        print(fmt_row("all fills", n, rows))

        # (B) reversion-conditioned: fill follows a recent DOWN move
        n2, rows2 = fwd_table(
            fills, key=lambda f: f["down"] is not None and f["down"] <= -DOWN_THRESH_BPS)
        print(f"\n[B] REVERSION setup -- fill AFTER mid dropped >= {DOWN_THRESH_BPS} bps over prior {DOWN_LOOKBACK_S}s")
        print(fmt_row("after down-move (buying weakness)", n2, rows2))

        # (C) contrast: fill after an UP move (buying strength) for reference
        n3, rows3 = fwd_table(
            fills, key=lambda f: f["down"] is not None and f["down"] >= DOWN_THRESH_BPS)
        print(f"\n[C] CONTRAST -- fill AFTER mid rose >= {DOWN_THRESH_BPS} bps (buying strength)")
        print(fmt_row("after up-move", n3, rows3))

        # store for net calc
        r["_all"] = rows
        r["_rev"] = rows2

    # ---- Net round-trip economics ----
    print("\n" + "=" * 78)
    print("NET ROUND-TRIP ECONOMICS (maker entry + maker exit)")
    print("Capture = 2 x half-spread (entry+exit) - 2 x maker fee. Then subtract adverse cost.")
    print(f"maker fee = {MAKER_FEE*1e4:.1f} bps/side -> {2*MAKER_FEE*1e4:.1f} bps round trip")
    print("=" * 78)
    print(f"\n{'SYM':<5}{'2xHalfSpread':>14}{'-Fees':>9}{'=GrossCap':>11}"
          f"{'AdvCost@5s':>13}{'AdvCost@30s':>13}{'AdvCost@60s':>13}")
    print("-" * 78)
    for sym, r in results.items():
        cap = 2 * r["half_spread_bps_median"]
        fees = 2 * MAKER_FEE * 1e4
        gross = cap - fees
        # adverse cost from REVERSION-conditioned fills = -mean fwd move (if negative)
        rev = r["_rev"]
        def advcost(h):
            x = rev.get(h)
            return None if x is None else -x["mean"]  # bps you LOSE on entry leg
        print(f"{sym:<5}{cap:>14.3f}{fees:>9.2f}{gross:>11.3f}"
              f"{(advcost(5) if advcost(5) is not None else float('nan')):>13.3f}"
              f"{(advcost(30) if advcost(30) is not None else float('nan')):>13.3f}"
              f"{(advcost(60) if advcost(60) is not None else float('nan')):>13.3f}")

    print("\nInterpretation:")
    print(" GrossCap = the spread+fee edge you keep if there were ZERO adverse selection.")
    print(" AdvCost  = mean adverse mid move on REVERSION-conditioned entries (bps lost on entry).")
    print(" If AdvCost (entry leg alone) > GrossCap (whole round trip), maker reversion loses.")


if __name__ == "__main__":
    main()
