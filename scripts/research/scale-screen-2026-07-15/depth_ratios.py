#!/usr/bin/env python3
"""Addendum: order size vs visible depth per MR symbol, + projected 30d volume.

Reads the snapshot captured by scale_screen.py (out.json) — no new API calls.
"""
import json
import os

OUT = os.path.dirname(os.path.abspath(__file__))
o = json.load(open(os.path.join(OUT, "out.json")))
books = o["order_books"]
notionals = o["order_notionals"]  # today $150 / prop+2sl-safe at 250 & 500

print(f"Book snapshot: {o['order_books_ts']}")
print(f"Order notionals tested: {notionals}\n")

rows = []
for sym, bk in sorted(books.items()):
    if "error" in bk:
        continue
    # thinner side of book = worst case for a resting maker order
    top_min = min(bk["top_bid_usd"], bk["top_ask_usd"])
    l5_min = min(bk["bid5_usd"], bk["ask5_usd"])
    r = {"symbol": sym.split("/")[0], "spread_bps": bk["spread_bps"],
         "top_thin_usd": top_min, "L5_thin_usd": l5_min}
    for name, n in notionals.items():
        r[f"pct_top[{name}]"] = round(100 * n / top_min, 0)
        r[f"pct_L5[{name}]"] = round(100 * n / l5_min, 0)
    rows.append(r)

hdr = ["symbol", "spread_bps", "top_thin_usd", "L5_thin_usd"]
nkeys = list(notionals.keys())
print(f"{'sym':8s} {'sprd':>5s} {'topThin$':>9s} {'L5thin$':>9s} | order as % of thin top-of-book / thin 5-level")
for r in rows:
    tops = " ".join(f"{k.split('_')[0][:4]}${notionals[k]:.0f}:{r[f'pct_top[{k}]']:.0f}%/{r[f'pct_L5[{k}]']:.0f}%"
                    for k in nkeys)
    print(f"{r['symbol']:8s} {r['spread_bps']:5.1f} {r['top_thin_usd']:9.0f} {r['L5_thin_usd']:9.0f} | {tops}")

# how many symbols does each order size exceed thin top-of-book on?
print()
for k in nkeys:
    n_over_top = sum(1 for r in rows if r[f"pct_top[{k}]"] > 100)
    n_over_half_l5 = sum(1 for r in rows if r[f"pct_L5[{k}]"] > 50)
    print(f"{k} (${notionals[k]:.0f}): exceeds thin top-of-book on {n_over_top}/{len(rows)} symbols; "
          f">50% of thin 5-level depth on {n_over_half_l5}/{len(rows)}")

# projected 30d volume for the fee-tier question
# MR 90d baseline n=309 (reports/mr_variant_grid_90d.json V0) -> 309/3 trades/30d, x2 legs
n30 = o["mr_90d_v0"]["n"] / 3.0
print("\nProjected 30d futures volume (MR only, n from 90d grid V0):")
for k in nkeys:
    vol = n30 * notionals[k] * 2
    print(f"  {k}: {n30:.0f} trades x ${notionals[k]:.0f} x 2 legs = ${vol:,.0f}/30d")
print("Phemex VIP1 requires >= $8M 30d futures volume (help-center page, fetched 7/15).")

json.dump({"rows": rows, "notionals": notionals,
           "vol_30d": {k: n30 * v * 2 for k, v in notionals.items()}},
          open(os.path.join(OUT, "depth_ratios.json"), "w"), indent=1)
