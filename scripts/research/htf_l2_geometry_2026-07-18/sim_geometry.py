#!/usr/bin/env python3
"""Exit-geometry grid replay for htf_l2_anticipation.

Grid: SL x TP x partial-TP x trail-arm, simulated on 1m candle paths per position.
Mechanics mirror risk_manager.py:
  - tiered trail: tiers [(20,15,5),(15,10,5),(10,6,4),(8,4,4),(5,2,3)], default (2,3);
    trail_price = peak*(1 -/+ trail_pct/100/LEV), lock = entry*(1 +/- lock/100/LEV),
    ratchet monotonic; arms at configurable ROI (live: 8.0)
  - partial-TP: half out at +10% ROI (taker); runner TP lifted to +25% ROI
    (live PARTIAL_RUNNER_TP_ROI); here runner TP = 25 if config TP <= 25 else config TP,
    or None if TP=none
  - fees: entry maker 0.01%, exit taker 0.06% (SL/trail/partial/software/cap),
    TP limit fill maker 0.01% (empirically confirmed from ledger fee rates)
Conservative intrabar ordering: stop checked against PRIOR-candle trail level and
candle adverse extreme BEFORE TP/partial/peak update (SL-first worst case).
Software exits (early_exit/adverse_exit/flat_exit/hard_time_exit) force-close the
remainder at the actual exit price/time. Geometry-exit trades run to 24h cap
(exit at last close, 'time_cap').
No slippage on stops (actual data shows late SL fills; uniformly optimistic).
IN-SAMPLE: same ledger the strategy was diagnosed on.
"""
import json, os, itertools
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LEV = 10.0
MAKER, TAKER = 0.0001, 0.0006
TIERS = [(20.0, 15.0, 5.0), (15.0, 10.0, 5.0), (10.0, 6.0, 4.0), (8.0, 4.0, 4.0), (5.0, 2.0, 3.0)]
GEOM = {"exchange_close", "trailing_stop", "stop_loss", "take_profit"}
PARTIAL_ROI = 10.0
RUNNER_TP = 25.0

positions = json.load(open(os.path.join(HERE, "positions.json")))


def load_candles(i):
    fp = os.path.join(HERE, "cache", f"{i}.json")
    if not os.path.exists(fp):
        return None
    return json.load(open(fp))


def roi_of(entry, price, sgn):
    return sgn * (price / entry - 1.0) * LEV * 100.0


def price_at_roi(entry, roi, sgn):
    return entry * (1.0 + sgn * roi / 100.0 / LEV)


def trail_update(entry, sgn, peak, cur_roi, arm, trail_level):
    """Mirror risk_manager.update_trailing_stop. cur_roi = ROI at current price proxy."""
    if cur_roi < arm:
        return trail_level
    lock, trail = 2.0, 3.0
    for th, lk, tr in TIERS:
        if cur_roi >= th:
            lock, trail = lk, tr
            break
    if sgn > 0:
        tp_price = peak * (1 - trail / 100.0 / LEV)
        lock_price = entry * (1 + lock / 100.0 / LEV)
        new = max(tp_price, lock_price)
        if trail_level is None or new > trail_level:
            return new
    else:
        tp_price = peak * (1 + trail / 100.0 / LEV)
        lock_price = entry * (1 - lock / 100.0 / LEV)
        new = min(tp_price, lock_price)
        if trail_level is None or new < trail_level:
            return new
    return trail_level


def simulate(pos, candles, sl_roi, tp_roi, partial_on, arm):
    """Return (net_pnl, exit_reason, resolved) for one position under one geometry."""
    entry = pos["entry"]; amount = pos["amount"]
    sgn = 1.0 if pos["side"] == "long" else -1.0
    soft = pos["exit_reason"] not in GEOM
    end_ts = pos["closed_at"] if soft else pos["opened_at"] + 24 * 3600

    sl_price = price_at_roi(entry, -sl_roi, sgn)
    tp_price = price_at_roi(entry, tp_roi, sgn) if tp_roi is not None else None
    part_price = price_at_roi(entry, PARTIAL_ROI, sgn)
    # partial can't fire if TP sits below the partial trigger
    partial_active = partial_on and (tp_roi is None or tp_roi > PARTIAL_ROI)

    frac = 1.0
    scaled = False
    trail_level = None
    peak = entry
    entry_fee = amount * entry * MAKER
    cash = -entry_fee  # accumulate leg pnl - fees

    def leg(exit_price, f, taker=True):
        fee_rate = TAKER if taker else MAKER
        return f * amount * (exit_price - entry) * sgn - f * amount * exit_price * fee_rate

    last_close = entry
    for c in candles:
        ts = c[0] / 1000.0
        if ts < pos["opened_at"] - 60:
            continue
        if ts > end_ts:
            break
        o, hi, lo, cl = c[1], c[2], c[3], c[4]
        last_close = cl
        adverse = lo if sgn > 0 else hi
        favor = hi if sgn > 0 else lo

        # 1) stop check (prior trail level; SL-first worst case)
        if trail_level is not None:
            eff = max(trail_level, sl_price) if sgn > 0 else min(trail_level, sl_price)
        else:
            eff = sl_price
        hit_stop = adverse <= eff if sgn > 0 else adverse >= eff
        if hit_stop:
            cash += leg(eff, frac, taker=True)
            reason = "trail_stop" if (trail_level is not None and eff != sl_price) else "hard_sl"
            return cash, reason, True

        # 2) partial
        if partial_active and not scaled:
            hit_part = favor >= part_price if sgn > 0 else favor <= part_price
            if hit_part:
                cash += leg(part_price, frac / 2.0, taker=True)
                frac /= 2.0
                scaled = True
                if tp_roi is not None:
                    lifted = RUNNER_TP if tp_roi <= RUNNER_TP else tp_roi
                    tp_price = price_at_roi(entry, lifted, sgn)

        # 3) TP
        if tp_price is not None:
            hit_tp = favor >= tp_price if sgn > 0 else favor <= tp_price
            if hit_tp:
                cash += leg(tp_price, frac, taker=False)
                return cash, "tp", True

        # 4) trail arm/ratchet from favorable extreme
        if sgn > 0:
            peak = max(peak, favor)
        else:
            peak = min(peak, favor)
        if arm is not None:
            trail_level = trail_update(entry, sgn, peak, roi_of(entry, peak, sgn), arm, trail_level)

    # loop exhausted
    if soft:
        cash += leg(pos["exit_price"], frac, taker=True)
        return cash, "software", True
    cash += leg(last_close, frac, taker=True)
    return cash, "time_cap", True


def run_book(book_idx, label, configs, boot=4000, seed=7):
    rows = []
    rng = np.random.default_rng(seed)
    for (sl, tp, part, arm) in configs:
        nets = []
        reasons = {}
        for i in book_idx:
            pos = positions[i]
            candles = CANDLES[i]
            if candles is None or len(candles) == 0:
                continue
            net, reason, _ = simulate(pos, candles, sl, tp, part, arm)
            nets.append(net)
            reasons[reason] = reasons.get(reason, 0) + 1
        a = np.array(nets)
        n = len(a)
        wins = a[a > 0]; losses = a[a <= 0]
        wr = len(wins) / n * 100
        aw = wins.mean() if len(wins) else 0.0
        al = losses.mean() if len(losses) else 0.0
        idx = rng.integers(0, n, size=(boot, n))
        means = a[idx].mean(axis=1)
        lo, hi = np.percentile(means, [2.5, 97.5])
        rows.append({
            "sl": sl, "tp": tp, "partial": part, "arm": arm, "n": n,
            "wr": round(wr, 1), "avg_win": round(float(aw), 3),
            "avg_loss": round(float(al), 3),
            "wl_ratio": round(float(aw / -al), 2) if al < 0 else None,
            "net": round(float(a.sum()), 2),
            "mean": round(float(a.mean()), 4),
            "ci_lo": round(float(lo), 4), "ci_hi": round(float(hi), 4),
            "time_cap": reasons.get("time_cap", 0),
            "reasons": reasons,
        })
    return rows


if __name__ == "__main__":
    CANDLES = [load_candles(i) for i in range(len(positions))]
    missing = [i for i, c in enumerate(CANDLES) if c is None or len(c) == 0]
    print(f"positions={len(positions)} candle-covered={len(positions)-len(missing)} missing={len(missing)}")
    if missing:
        print("missing idx:", missing, [positions[i]['symbol'] for i in missing])

    # MAE/MFE through actual exit (step-1 deliverable)
    maes, mfes = [], []
    for i, pos in enumerate(positions):
        c = CANDLES[i]
        if not c:
            continue
        sgn = 1.0 if pos["side"] == "long" else -1.0
        lo_r, hi_r = 0.0, 0.0
        for cd in c:
            ts = cd[0] / 1000.0
            if ts < pos["opened_at"] - 60 or ts > pos["closed_at"]:
                continue
            lo_r = min(lo_r, roi_of(pos["entry"], cd[3] if sgn > 0 else cd[2], sgn))
            hi_r = max(hi_r, roi_of(pos["entry"], cd[2] if sgn > 0 else cd[3], sgn))
        maes.append(lo_r); mfes.append(hi_r)
    maes = np.array(maes); mfes = np.array(mfes)
    print(f"MAE/MFE computed for {len(maes)} positions: median MAE {np.median(maes):.2f}% ROI, "
          f"median MFE {np.median(mfes):.2f}% ROI")
    np.save(os.path.join(HERE, "mae.npy"), maes)
    np.save(os.path.join(HERE, "mfe.npy"), mfes)

    SLS = [4.0, 6.0, 8.0, 10.0, 12.0]
    TPS = [8.0, 12.0, 16.0, 24.0, 32.0, None]
    PARTS = [True, False]
    ARMS = [None, 8.0, 12.0, 16.0]
    configs = list(itertools.product(SLS, TPS, PARTS, ARMS))
    print("configs:", len(configs))

    full_idx = list(range(len(positions)))
    resid_idx = [i for i in full_idx if not positions[i]["toxic"]]
    print(f"full n={len(full_idx)} residual n={len(resid_idx)}")

    out = {}
    out["full"] = run_book(full_idx, "full", configs)
    out["residual"] = run_book(resid_idx, "residual", configs)
    json.dump(out, open(os.path.join(HERE, "grid_results.json"), "w"), indent=1)

    for label in ("full", "residual"):
        rows = out[label]
        rows_s = sorted(rows, key=lambda r: -r["net"])
        print(f"\n=== {label}: top 10 by net $ ===")
        for r in rows_s[:10]:
            print(r["sl"], r["tp"], r["partial"], r["arm"], "| n", r["n"], "WR", r["wr"],
                  "avgW", r["avg_win"], "avgL", r["avg_loss"], "ratio", r["wl_ratio"],
                  "net", r["net"], "CI", (r["ci_lo"], r["ci_hi"]), "cap", r["time_cap"])
        pareto = [r for r in rows_s if r["wl_ratio"] and r["wl_ratio"] > 1.0]
        print(f"{label}: configs with avg_win > avg_loss: {len(pareto)}; "
              f"of those WR>=68: {sum(1 for r in pareto if r['wr'] >= 68)}")
    print("done")
