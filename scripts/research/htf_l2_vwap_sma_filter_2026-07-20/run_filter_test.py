#!/usr/bin/env python3
"""Owner-proposed entry filter test on the 205-trade htf_l2 ledger (IN-SAMPLE).

Rule under test: "LONGS only if price is above the 5-minute AND 15-minute VWAP,
and the 9SMA is crossing above the 15SMA. Vice versa for shorts."

Fidelity contract (identical to htf_l2_entry_features_2026-07-18/build_features.py):
- closed 5m bars (ts+300s <= opened_at) + synthetic forming bar
  (open = first closed 1m open in window else entry px; high/low = extremes of
  closed 1m bars unioned with entry px; close = entry px; vol = sum closed 1m),
  then last 500 rows.
- VWAP = the bot's own session-anchored (midnight-UTC reset) vwap() from
  indicators.py, NOT reimplemented. SMA = indicators.sma (rolling mean).
- 15m VWAP: 5m bars (incl. forming) resampled 3:1 onto 900s boundaries
  (OHLCV agg; last group is the partial/forming 15m bar), then the same
  session-anchored vwap() on the 15m frame.
- 9/15 SMA on 5m closes (incl. forming bar close = entry px).
  ALIGNMENT: oriented diff d*(sma9-sma15) > 0 at entry (d=+1 long, -1 short).
  STRICT CROSS K: oriented diff flipped from <=0 to >0 at some bar among the
  last K bar-transitions (forming bar counts as the most recent bar).

Variants (12): vwap5_only, vwap15_only, vwap_both, sma_align, sma_cross_K1/3/6,
full_align, full_cross_K1/3/6, and full rule with 5m-leg dropped (marginal check).
Books: FULL 205 / RESIDUAL 149 (non-toxic).
Stats: saved $, winners lost / losers avoided, surviving WR, bootstrap 95% CI on
mean-$/trade diff (trades resampled i.i.d.), permutation placebo (1000 shuffles
of the net-pnl vector vs fixed block masks) per-variant + family-wise max.
"""
import json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FEAT = os.path.join(HERE, "..", "htf_l2_entry_features_2026-07-18")
GEOM = os.path.join(HERE, "..", "htf_l2_geometry_2026-07-18")
sys.path.insert(0, ROOT)
from indicators import vwap, sma  # bot's own math

rng = np.random.default_rng(20260720)
positions = json.load(open(os.path.join(GEOM, "positions.json")))

rows = []
gaps = []
for i, p in enumerate(positions):
    f5 = os.path.join(FEAT, "cache", f"{i}_5m.json")
    f1 = os.path.join(FEAT, "cache", f"{i}_1m.json")
    if not (os.path.exists(f5) and os.path.exists(f1)):
        gaps.append((i, p["symbol"], "no cache")); continue
    entry_ts = int(p["opened_at"])
    entry_px = float(p["entry"])
    bar5_ms = (entry_ts // 300) * 300 * 1000
    c5 = json.load(open(f5))
    c1 = json.load(open(f1))
    closed = [c for c in c5 if c[0] + 300000 <= entry_ts * 1000]
    if len(closed) < 60:
        gaps.append((i, p["symbol"], f"only {len(closed)} closed 5m bars")); continue
    ones = [c for c in c1 if c[0] >= bar5_ms and c[0] + 60000 <= entry_ts * 1000]
    if ones:
        o = ones[0][1]
        h = max(max(c[2] for c in ones), entry_px)
        l = min(min(c[3] for c in ones), entry_px)
        v = sum(c[5] for c in ones)
    else:
        o = h = l = entry_px; v = 0.0
    bars = (closed + [[bar5_ms, o, h, l, entry_px, v]])[-500:]
    df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)

    px = df["close"].iloc[-1]
    d = 1.0 if p["side"] == "long" else -1.0

    # --- 5m session VWAP (bot convention) ---
    vw5 = vwap(df["high"], df["low"], df["close"], df["volume"]).iloc[-1]

    # --- 15m resample (3:1 on 900s boundaries; last group = forming 15m) ---
    g = (df.index.astype("int64") // 10**9 // 900) * 900
    df15 = df.groupby(pd.to_datetime(g, unit="s")).agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    vw15 = vwap(df15["high"], df15["low"], df15["close"], df15["volume"]).iloc[-1]

    # --- 9/15 SMA on 5m closes ---
    diff = d * (sma(df["close"], 9) - sma(df["close"], 15))  # oriented
    dv = diff.values
    align = bool(dv[-1] > 0)
    crossed = {}
    for K in (1, 3, 6):
        c = False
        for t in range(len(dv) - K, len(dv)):
            if t >= 1 and not (np.isnan(dv[t]) or np.isnan(dv[t - 1])):
                if dv[t] > 0 and dv[t - 1] <= 0:
                    c = True; break
        crossed[K] = c

    if pd.isna(vw5) or pd.isna(vw15):
        gaps.append((i, p["symbol"], "nan vwap")); continue

    ok5 = bool(d * (px - vw5) > 0)    # right side of 5m VWAP
    ok15 = bool(d * (px - vw15) > 0)  # right side of 15m VWAP
    rows.append({
        "idx": i, "symbol": p["symbol"], "side": p["side"],
        "net": float(p["actual_net"]), "toxic": bool(p["toxic"]),
        "ok5": ok5, "ok15": ok15, "align": align,
        "x1": crossed[1], "x3": crossed[3], "x6": crossed[6],
    })

print(f"trades evaluated: {len(rows)}/{len(positions)}")
for gp in gaps:
    print("GAP:", gp)

R = pd.DataFrame(rows)
json.dump(rows, open(os.path.join(HERE, "per_trade_flags.json"), "w"), indent=1)

# ---- variant pass-masks (True = trade PASSES the filter, i.e. kept) ----
variants = {
    "vwap5_only":        R["ok5"],
    "vwap15_only":       R["ok15"],
    "vwap_both":         R["ok5"] & R["ok15"],
    "sma_align":         R["align"],
    "sma_cross_K1":      R["x1"],
    "sma_cross_K3":      R["x3"],
    "sma_cross_K6":      R["x6"],
    "FULL_align":        R["ok5"] & R["ok15"] & R["align"],
    "FULL_cross_K1":     R["ok5"] & R["ok15"] & R["x1"],
    "FULL_cross_K3":     R["ok5"] & R["ok15"] & R["x3"],
    "FULL_cross_K6":     R["ok5"] & R["ok15"] & R["x6"],
    "vwap15_and_align":  R["ok15"] & R["align"],   # full rule minus the (near-redundant) 5m leg
}

def book_stats(mask_book, label):
    B = R[mask_book].reset_index(drop=True)
    net = B["net"].values
    n = len(B)
    win = net > 0
    print(f"\n===== BOOK: {label}  n={n}  winners={win.sum()}  sum_net={net.sum():+.2f} =====")
    out = []
    masks = []
    for name, passmask in variants.items():
        keep = passmask[mask_book].values
        blocked = ~keep
        nb = int(blocked.sum())
        saved = float(-net[blocked].sum())
        wl = int((blocked & win).sum())
        la = int((blocked & ~win).sum())
        surv_n = int(keep.sum())
        surv_wr = float(win[keep].mean() * 100) if surv_n else float("nan")
        surv_net = float(net[keep].sum())
        # bootstrap CI on mean-$/trade difference (filtered-vs-original, per trade)
        dvec = np.where(blocked, -net, 0.0)
        bs = np.array([dvec[rng.integers(0, n, n)].mean() for _ in range(5000)])
        lo, hi = np.percentile(bs, [2.5, 97.5])
        out.append(dict(variant=name, n_blocked=nb, pct_blocked=100 * nb / n,
                        winners_lost=wl, losers_avoided=la, saved=saved,
                        surv_n=surv_n, surv_wr=surv_wr, surv_net=surv_net,
                        mean_diff=float(dvec.mean()), ci_lo=float(lo), ci_hi=float(hi)))
        masks.append(blocked)
    # permutation placebo: shuffle net vector, recompute saved per variant
    NP_ = 1000
    perm_saved = np.zeros((NP_, len(masks)))
    for k in range(NP_):
        pn = rng.permutation(net)
        for j, bl in enumerate(masks):
            perm_saved[k, j] = -pn[bl].sum()
    for j, o in enumerate(out):
        o["placebo_p_cell"] = float((perm_saved[:, j] >= o["saved"]).mean())
    fam_max = perm_saved.max(axis=1)
    real_best = max(o["saved"] for o in out)
    fam_p = float((fam_max >= real_best).mean())

    hdr = f"{'variant':<18}{'blk':>5}{'blk%':>7}{'W lost':>7}{'L avoid':>8}{'saved$':>9}{'survWR%':>9}{'survNet$':>10}{'mean$/t':>9}{'CI95':>18}{'p_cell':>8}"
    print(hdr)
    for o in out:
        flag = "  KILL>60%" if o["pct_blocked"] > 60 else ""
        print(f"{o['variant']:<18}{o['n_blocked']:>5}{o['pct_blocked']:>6.1f}%{o['winners_lost']:>7}{o['losers_avoided']:>8}"
              f"{o['saved']:>+9.2f}{o['surv_wr']:>8.1f}%{o['surv_net']:>+10.2f}{o['mean_diff']:>+9.3f}"
              f"  [{o['ci_lo']:+.3f},{o['ci_hi']:+.3f}]{o['placebo_p_cell']:>8.3f}{flag}")
    print(f"family-wise placebo ({len(masks)} variants, {NP_} perms): real best saved = {real_best:+.2f}, "
          f"perm max median = {np.median(fam_max):+.2f}, perm max p95 = {np.percentile(fam_max,95):+.2f}, familywise_p = {fam_p:.3f}")
    return {"book": label, "n": n, "variants": out,
            "familywise": {"n_variants": len(masks), "n_perm": NP_,
                           "real_best_saved": real_best,
                           "perm_max_median": float(np.median(fam_max)),
                           "perm_max_p95": float(np.percentile(fam_max, 95)),
                           "familywise_p": fam_p}}

results = {}
results["FULL"] = book_stats(pd.Series(True, index=R.index), "FULL (205)")
results["RESIDUAL"] = book_stats(~R["toxic"], "RESIDUAL (non-toxic)")

# ---- overlap accounting: what does each leg newly block? ----
print("\n===== LEG OVERLAP (FULL book) =====")
n = len(R)
f5 = ~R["ok5"]; f15 = ~R["ok15"]; fa = ~R["align"]
print(f"fails 5m-VWAP side:  {f5.sum():>3}/{n}  ({100*f5.mean():.1f}%)  [bot already enforces this at signal time]")
print(f"fails 15m-VWAP side: {f15.sum():>3}/{n}  ({100*f15.mean():.1f}%)")
print(f"fails both VWAP legs:{(f5&f15).sum():>3}/{n}")
print(f"15m NEWLY blocks (passes 5m, fails 15m): {(R["ok5"]&f15).sum():>3}")
print(f"5m NEWLY blocks (passes 15m, fails 5m):  {(R["ok15"]&f5).sum():>3}")
print(f"fails SMA alignment: {fa.sum():>3}/{n}  ({100*fa.mean():.1f}%)")
print(f"SMA-align NEWLY blocks beyond vwap_both: {((R["ok5"]&R["ok15"])&fa).sum():>3}")
for K in ("x1", "x3", "x6"):
    fx = ~R[K]
    print(f"fails SMA cross {K}:  {fx.sum():>3}/{n} ({100*fx.mean():.1f}%);  newly beyond vwap_both: {((R["ok5"]&R["ok15"])&fx).sum():>3}")

results["overlap"] = {
    "fail_5m": int(f5.sum()), "fail_15m": int(f15.sum()),
    "fail_both_vwap": int((f5 & f15).sum()),
    "new_block_15m": int((R["ok5"] & f15).sum()),
    "new_block_5m": int((R["ok15"] & f5).sum()),
    "fail_align": int(fa.sum()),
    "align_new_beyond_vwap": int(((R["ok5"] & R["ok15"]) & fa).sum()),
}
json.dump(results, open(os.path.join(HERE, "results.json"), "w"), indent=1)
print("\nwrote results.json + per_trade_flags.json")
