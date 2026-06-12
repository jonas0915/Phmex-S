#!/usr/bin/env python3
"""
Phase 3 cohort-gate simulation — method 1: exact both-sides accounting over
ACTUALLY TAKEN trades. 2026-06-11.

Universe: trading_state.json closed_trades where strategy == htf_l2_anticipation
and entry_snapshot is populated (91 trades; the 16 snapshot-less htf_l2 records
are min_margin_skip-era artifacts with no snapshot — verified 0 of the 25
min_margin_skip records in the book carry a snapshot).

For an ENTRY FILTER, blocking historical trades is the complete counterfactual:
no new trades appear. For each gate:
    blocked      = trades the gate would have prevented
    losers_saved = +sum(-net_pnl) over blocked trades with net_pnl < 0
    winners_clip = -sum(net_pnl)  over blocked trades with net_pnl > 0
    NET          = -sum(net_pnl over blocked)  (positive = gate helps)

Alignment formula (matches strategies.py:600-606 whale-boost semantics):
    aligned_lt_bias = flow.large_trade_bias   if side == long
                    = -flow.large_trade_bias  if side == short
(i.e. sign-flipped so positive = whales agree with the trade direction; same
convention for cvd_slope.)

Overfit guards:
  G1 half-split  : sort by opened_at, first 45 vs last 46; pass needs same NET
                   sign in both halves (and net-positive overall).
  G2 minimum n   : blocked n < 8 -> "insufficient n", cannot pass.
  G3 leave-one-out: drop the single biggest saved loser from the blocked set;
                   NET must stay positive.

Whale-boost removal (strategies.py:601-606, +0.03 when lt_bias aligned beyond
0.2): separate accounting. A taken trade got the boost iff
(long and lt_bias > 0.2) or (short and lt_bias < -0.2). Without the boost it
fails the SCALP_MIN_STRENGTH=0.80 bar (bot.py:1052) iff its gate-time strength
< 0.83. Gate-time strength is NOT stored: entry_snapshot.strength is recorded
AFTER the funding strength_mod (bot.py:1202-1203, range +/-0.03) is added,
while the 0.80 gate fires BEFORE it (bot.py:1052). We therefore report a point
estimate (assume mod ~ 0: recorded < 0.83) and hard bounds
(recorded < 0.80 = definitely blocked even at mod=+0.03;
 recorded < 0.86 = possibly blocked at mod=-0.03).

READ-ONLY: this script only reads trading_state.json and prints.
"""

import json
import datetime
import random
import zlib

STATE = "/Users/jonaspenaso/Desktop/Phmex-S/trading_state.json"
MIN_BLOCKED_N = 8
N_PERM = 20000  # random-block permutation baseline draws


def load_trades():
    with open(STATE) as f:
        book = json.load(f)["closed_trades"]
    trades = []
    for t in book:
        if t.get("strategy") != "htf_l2_anticipation" or not t.get("entry_snapshot"):
            continue
        s = t["entry_snapshot"]
        side_sign = 1 if t["side"] == "long" else -1
        lt = s["flow"]["large_trade_bias"]
        trades.append({
            "opened_at": t["opened_at"],
            "side": t["side"],
            "symbol": t["symbol"],
            "net": t["net_pnl"],
            "lt_bias_raw": lt,
            "aligned_lt": side_sign * lt,
            "adx5m": s["regime"]["adx"],
            "conf": s["confidence"],
            "hour_utc": datetime.datetime.fromtimestamp(
                t["opened_at"], datetime.timezone.utc).hour,
            "strength_rec": s["strength"],
        })
    trades.sort(key=lambda x: x["opened_at"])
    # whole book (for hour-gate context only): all records with net_pnl
    whole = [{"net": t["net_pnl"],
              "hour_utc": datetime.datetime.fromtimestamp(
                  t["opened_at"], datetime.timezone.utc).hour}
             for t in book if t.get("net_pnl") is not None and t.get("opened_at")]
    return trades, whole


def accounting(blocked):
    saved = sum(-x["net"] for x in blocked if x["net"] < 0)
    clipped = -sum(x["net"] for x in blocked if x["net"] > 0)
    return saved, clipped, saved + clipped  # NET = saved + clipped (clipped<=0)


def perm_baseline(trades, k, observed_net, rng):
    """Random-block baseline: NET of blocking k uniformly random trades.
    Returns (expected_net, p_value = P(random NET >= observed))."""
    if k == 0:
        return 0.0, 1.0
    nets = [x["net"] for x in trades]
    mean_net = sum(nets) / len(nets)
    expected = -k * mean_net
    ge = 0
    for _ in range(N_PERM):
        if -sum(rng.sample(nets, k)) >= observed_net:
            ge += 1
    return expected, ge / N_PERM


def evaluate(trades, name, pred):
    n = len(trades)
    half1, half2 = trades[:n // 2], trades[n // 2:]
    blocked = [x for x in trades if pred(x)]
    saved, clipped, net = accounting(blocked)
    b1 = [x for x in half1 if pred(x)]
    b2 = [x for x in half2 if pred(x)]
    _, _, net1 = accounting(b1)
    _, _, net2 = accounting(b2)
    # G3: leave-one-out on the biggest saved loser
    losers = sorted((x for x in blocked if x["net"] < 0), key=lambda x: x["net"])
    if losers:
        best_save = losers[0]
        loo_net = net - (-best_save["net"])
        loo_desc = f"{best_save['symbol']} {best_save['net']:+.2f}"
    else:
        loo_net, loo_desc = net, "n/a (no losers blocked)"
    # random-block baseline (deterministic seed per gate name; crc32 is
    # stable across processes, unlike built-in str hash)
    rng = random.Random(zlib.crc32(name.encode()))
    exp_rand, p_rand = perm_baseline(trades, len(blocked), net, rng)
    # verdict
    fails = []
    if net <= 0:
        fails.append("net<=0")
    if len(blocked) < MIN_BLOCKED_N:
        fails.append(f"n={len(blocked)}<{MIN_BLOCKED_N}")
    if not (net1 > 0 and net2 > 0):
        fails.append(f"halves {net1:+.2f}/{net2:+.2f}")
    if loo_net <= 0:
        fails.append(f"LOO {loo_net:+.2f}")
    verdict = "PASS" if not fails else "FAIL(" + "; ".join(fails) + ")"
    return {
        "name": name, "n_blocked": len(blocked), "saved": saved,
        "clipped": clipped, "net": net, "net_h1": net1, "net_h2": net2,
        "n_h1": len(b1), "n_h2": len(b2),
        "loo_net": loo_net, "loo_drop": loo_desc, "verdict": verdict,
        "exp_rand": exp_rand, "p_rand": p_rand,
        "blocked": blocked,
    }


def fmt_row(r):
    return (f"{r['name']:<34} {r['n_blocked']:>3}  {r['saved']:>+8.2f} "
            f"{r['clipped']:>+8.2f} {r['net']:>+8.2f}  "
            f"{r['net_h1']:>+7.2f}({r['n_h1']:>2}) {r['net_h2']:>+7.2f}({r['n_h2']:>2})  "
            f"{r['loo_net']:>+7.2f}  {r['exp_rand']:>+6.2f} {r['p_rand']:>6.3f}  "
            f"{r['verdict']}")


HDR = (f"{'gate':<34} {'nBlk':>4} {'saved$':>8} {'clip$':>8} {'NET$':>8}  "
       f"{'H1$(n)':>11} {'H2$(n)':>11}  {'LOO$':>7}  {'rand$':>6} {'pRnd':>6}  verdict")


def main():
    trades, whole = load_trades()
    n = len(trades)
    total_net = sum(x["net"] for x in trades)
    t0, t1 = trades[0]["opened_at"], trades[-1]["opened_at"]
    weeks = (t1 - t0) / 86400 / 7
    print(f"Universe: {n} htf_l2_anticipation trades with entry_snapshot")
    print(f"Span: {datetime.datetime.fromtimestamp(t0, datetime.timezone.utc):%Y-%m-%d}"
          f" .. {datetime.datetime.fromtimestamp(t1, datetime.timezone.utc):%Y-%m-%d}"
          f" UTC ({weeks:.1f} weeks, {n / weeks:.1f} trades/wk)")
    print(f"Total net_pnl: {total_net:+.2f}")
    split_ts = trades[n // 2]["opened_at"]
    print(f"Half split at {datetime.datetime.fromtimestamp(split_ts, datetime.timezone.utc):%Y-%m-%d %H:%M} UTC"
          f" ({n // 2} / {n - n // 2} trades)")
    print(f"H1 net {sum(x['net'] for x in trades[:n//2]):+.2f} | "
          f"H2 net {sum(x['net'] for x in trades[n//2:]):+.2f}")
    print()
    print(HDR)

    results = {}

    # A. aligned large_trade_bias block
    for th in (0.25, 0.30, 0.35, 0.40, 0.45):
        r = evaluate(trades, f"A: aligned_lt_bias >= {th:.2f}",
                     lambda x, th=th: x["aligned_lt"] >= th)
        results[("A", th)] = r
        print(fmt_row(r))
    print()

    # B. 5m ADX at entry
    for th in (23, 24, 25, 26, 27):
        r = evaluate(trades, f"B: 5m_ADX >= {th}",
                     lambda x, th=th: x["adx5m"] >= th)
        results[("B", th)] = r
        print(fmt_row(r))
    print()

    # C. confidence floor >= 5 (block conf < 5)
    r = evaluate(trades, "C: conf floor >=5 (block conf=4)",
                 lambda x: x["conf"] < 5)
    results[("C", 5)] = r
    print(fmt_row(r))
    print()

    # D. extra blocked hours (UTC)
    hour_sets = [(21,), (21, 22), (21, 22, 23), (14,), (14, 21, 22, 23)]
    for hs in hour_sets:
        r = evaluate(trades, f"D: block UTC hrs {','.join(map(str, hs))}",
                     lambda x, hs=hs: x["hour_utc"] in hs)
        results[("D", hs)] = r
        print(fmt_row(r))
    print()

    # Whole-book hour context (287 records with net_pnl, all strategies)
    print("Whole-book hour context (records with net_pnl, n=%d):" % len(whole))
    for hs in hour_sets:
        blk = [x for x in whole if x["hour_utc"] in hs]
        s, c, nn = accounting(blk)
        print(f"  UTC {','.join(map(str, hs)):<12} n={len(blk):>3} "
              f"saved {s:+.2f} clipped {c:+.2f} NET {nn:+.2f}")
    print()

    # E. combination: best-net single threshold per family, union of blocked sets
    best = {}
    for fam in ("A", "B", "D"):
        fam_rs = [v for k, v in results.items() if k[0] == fam]
        best[fam] = max(fam_rs, key=lambda r: r["net"])
    best["C"] = results[("C", 5)]
    combo_preds = []
    print("E. combination components (best NET per family):")
    for fam in ("A", "B", "C", "D"):
        print(f"   {fam}: {best[fam]['name']}  NET {best[fam]['net']:+.2f}")
    # rebuild predicates for the chosen bests
    chosen = {
        "A": max([t for t in (0.25, 0.30, 0.35, 0.40, 0.45)],
                 key=lambda th: results[("A", th)]["net"]),
        "B": max([t for t in (23, 24, 25, 26, 27)],
                 key=lambda th: results[("B", th)]["net"]),
        "D": max(hour_sets, key=lambda hs: results[("D", hs)]["net"]),
    }

    def combo_pred(x):
        return (x["aligned_lt"] >= chosen["A"]
                or x["adx5m"] >= chosen["B"]
                or x["conf"] < 5
                or x["hour_utc"] in chosen["D"])

    r = evaluate(trades, "E: union(bestA,bestB,C,bestD)", combo_pred)
    results[("E", "union")] = r
    print()
    print(HDR)
    print(fmt_row(r))
    remain = n - r["n_blocked"]
    print(f"   residual book: {remain}/{n} trades -> {remain / weeks:.1f} trades/wk "
          f"(historical rate {n / weeks:.1f}/wk)")
    rem_net = total_net + r["net"]
    print(f"   residual net_pnl: {rem_net:+.2f} over {weeks:.1f} wk")
    # overlap accounting
    fam_sets = {
        "A": {id(x) for x in results[("A", chosen["A"])]["blocked"]},
        "B": {id(x) for x in results[("B", chosen["B"])]["blocked"]},
        "C": {id(x) for x in results[("C", 5)]["blocked"]},
        "D": {id(x) for x in results[("D", chosen["D"])]["blocked"]},
    }
    print("   blocked-set sizes: " + ", ".join(
        f"{f}={len(s)}" for f, s in fam_sets.items()) +
        f"; union={r['n_blocked']} (overlap "
        f"{sum(len(s) for s in fam_sets.values()) - r['n_blocked']})")
    resid = [x for x in trades if not combo_pred(x)]
    print(f"   residual WR {sum(1 for x in resid if x['net'] > 0) / len(resid):.1%}")
    print()

    # E2. moderate combination — keeps more book: A>=0.40 OR conf<5 OR UTC 21-23
    def combo2_pred(x):
        return (x["aligned_lt"] >= 0.40 or x["conf"] < 5
                or x["hour_utc"] in (21, 22, 23))

    r2 = evaluate(trades, "E2: A>=0.40 | conf<5 | UTC21-23", combo2_pred)
    print(fmt_row(r2))
    resid2 = [x for x in trades if not combo2_pred(x)]
    print(f"   residual book: {len(resid2)}/{n} trades -> {len(resid2) / weeks:.1f} trades/wk; "
          f"residual net {sum(x['net'] for x in resid2):+.2f}, "
          f"WR {sum(1 for x in resid2 if x['net'] > 0) / len(resid2):.1%}")
    print()

    # Whale-boost removal accounting
    print("=" * 78)
    print("Whale-boost removal (strategies.py:601-606, +0.03 when aligned lt_bias")
    print("beyond 0.2). Boosted trade fails 0.80 bar without boost iff gate-time")
    print("strength < 0.83. snapshot.strength includes post-gate funding mod")
    print("(+/-0.03), so: point estimate uses recorded<0.83; bounds use 0.80/0.86.")
    boosted = [x for x in trades
               if (x["side"] == "long" and x["lt_bias_raw"] > 0.2)
               or (x["side"] == "short" and x["lt_bias_raw"] < -0.2)]
    s, c, nn = accounting(boosted)
    print(f"\nTrades that received the boost: {len(boosted)}/{n} "
          f"(net_pnl of boosted cohort: {-nn:+.2f})")
    for label, cut in (("point estimate (recorded < 0.83)", 0.83),
                       ("lower bound  (recorded < 0.80)", 0.80),
                       ("upper bound  (recorded < 0.86)", 0.86)):
        blk = [x for x in boosted if x["strength_rec"] < cut]
        s, c, nn = accounting(blk)
        print(f"  {label}: n_blocked={len(blk)} "
              f"saved {s:+.2f} clipped {c:+.2f} NET {nn:+.2f}")
    # full guard evaluation on the point estimate
    r = evaluate(trades, "W: whale-boost removal (pt est)",
                 lambda x: ((x["side"] == "long" and x["lt_bias_raw"] > 0.2)
                            or (x["side"] == "short" and x["lt_bias_raw"] < -0.2))
                 and x["strength_rec"] < 0.83)
    print()
    print(HDR)
    print(fmt_row(r))
    print()

    # context: audit-cohort reproduction checks
    print("=" * 78)
    print("Audit-cohort reproduction checks (same data, sanity only):")
    al = sorted(trades, key=lambda x: x["aligned_lt"])
    terc = al[2 * n // 3:]
    print(f"  top aligned_lt tercile (n={len(terc)}, cut at "
          f"{terc[0]['aligned_lt']:.3f}): net {sum(x['net'] for x in terc):+.2f}, "
          f"WR {sum(1 for x in terc if x['net'] > 0) / len(terc):.1%}")
    hi = [x for x in trades if x["adx5m"] >= 24.9]
    print(f"  5m ADX >= 24.9 (n={len(hi)}): "
          f"WR {sum(1 for x in hi if x['net'] > 0) / len(hi):.1%}, "
          f"net {sum(x['net'] for x in hi):+.2f}")
    c4 = [x for x in trades if x["conf"] == 4]
    print(f"  conf=4 (n={len(c4)}): net {sum(x['net'] for x in c4):+.2f}")


if __name__ == "__main__":
    main()
