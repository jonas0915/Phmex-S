#!/usr/bin/env python3
"""5m_mean_revert filter sweep — find a +EV sub-population, with ANTI-ARTIFACT guards.

Reads the enriched replay dump (reports/mr_replay_90d.json from mean_revert_replay.py)
and slices the signals by entry feature (side / RSI extremity / volume / ADX regime /
BB width / hour) to test whether some subset has a real MAKER edge while the rest drags
the strategy to breakeven.

ANTI-ARTIFACT (this is the whole point — slicing N ways manufactures false winners):
  * One-sided bootstrap p-value per bucket (H0: maker mean <= 0).
  * Benjamini-Hochberg FDR control across ALL tested buckets (stats.benjamini_hochberg).
  * Deflated Sharpe (Bailey/Lopez de Prado) on the best bucket, charged for n_trials.
  * Walk-forward sign check (3 chronological folds) — in-sample-only winners are killed.
  * Min-n floor; small buckets are reported but never "survive".
Per edge-hunt-exhaustion: this can only PROPOSE a hypothesis for a bounded live
forward-test. It CANNOT confirm an edge. Read-only.

Run:  python scripts/slot_lab/mean_revert_filters.py [--dump reports/mr_replay_90d.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
from st2_lab import stats as ST  # noqa: E402

MIN_N = 25          # buckets smaller than this are shown but cannot "survive"
FDR_ALPHA = 0.10    # Benjamini-Hochberg false-discovery rate
KEY = "maker_net"   # decision metric: ideal-fill edge (taker already rejected)


def _exp(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _boot_ci_p(xs, n_boot=4000, seed=0):
    """Return (lo, hi, p_one_sided) where p = P(bootstrap mean <= 0)."""
    n = len(xs)
    if n < 2:
        return (0.0, 0.0, 1.0)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        means.append(sum(xs[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot) - 1]
    p = sum(1 for m in means if m <= 0) / n_boot
    return (lo, hi, p)


def _sharpe(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    mu = sum(xs) / n
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    sd = math.sqrt(var)
    return mu / sd if sd > 0 else 0.0


def _walkforward_signs(rows, key, folds=3):
    if len(rows) < folds * 4:
        return None
    srt = sorted(rows, key=lambda r: r["ts"])
    sz = len(srt) // folds
    signs = []
    for f in range(folds):
        seg = srt[f * sz:(f + 1) * sz] if f < folds - 1 else srt[f * sz:]
        signs.append(_exp([r[key] for r in seg]) > 0)
    return signs


def _buckets(rows):
    """Yield (label, predicate-filtered rows). Single-dimension only (combos explode
    the multiple-comparison count); one falling-knife combo kept deliberately."""
    longs = [r for r in rows if r["side"] == "long"]
    shorts = [r for r in rows if r["side"] == "short"]
    b = {
        "side=long": longs,
        "side=short": shorts,
        # RSI extremity (longs fire <30, shorts >70)
        "long RSI<15": [r for r in longs if r["rsi"] < 15],
        "long RSI 15-22": [r for r in longs if 15 <= r["rsi"] < 22],
        "long RSI 22-30": [r for r in longs if 22 <= r["rsi"] < 30],
        "short RSI 70-78": [r for r in shorts if 70 <= r["rsi"] < 78],
        "short RSI 78-85": [r for r in shorts if 78 <= r["rsi"] < 85],
        "short RSI>85": [r for r in shorts if r["rsi"] >= 85],
        # volume confirmation strength
        "vol 1.3-1.7x": [r for r in rows if 1.3 <= r["vol_mult"] < 1.7],
        "vol 1.7-2.5x": [r for r in rows if 1.7 <= r["vol_mult"] < 2.5],
        "vol>2.5x": [r for r in rows if r["vol_mult"] >= 2.5],
        # ADX regime (falling-knife check — lessons.md ADX note)
        "ADX<15": [r for r in rows if r["adx"] < 15],
        "ADX 15-22": [r for r in rows if 15 <= r["adx"] < 22],
        "ADX 22-30": [r for r in rows if 22 <= r["adx"] < 30],
        # BB width terciles (computed below)
        # hour-of-day blocks (PT)
        "hour 0-6 PT": [r for r in rows if 0 <= r["hour_pt"] < 6],
        "hour 6-12 PT": [r for r in rows if 6 <= r["hour_pt"] < 12],
        "hour 12-18 PT": [r for r in rows if 12 <= r["hour_pt"] < 18],
        "hour 18-24 PT": [r for r in rows if 18 <= r["hour_pt"] < 24],
        # deliberate combo: longs in the flattest regime (cleanest reversion)
        "long & ADX<15": [r for r in longs if r["adx"] < 15],
    }
    widths = sorted(r["bb_width_pct"] for r in rows)
    if widths:
        t1, t2 = widths[len(widths) // 3], widths[2 * len(widths) // 3]
        b["bbwidth low"] = [r for r in rows if r["bb_width_pct"] <= t1]
        b["bbwidth mid"] = [r for r in rows if t1 < r["bb_width_pct"] <= t2]
        b["bbwidth high"] = [r for r in rows if r["bb_width_pct"] > t2]
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default="reports/mr_replay_90d.json")
    args = ap.parse_args()
    d = json.load(open(os.path.join(_BOT_DIR, args.dump)))
    rows = d["rows"]
    if "rsi" not in rows[0] or rows[0].get("rsi") is None:
        print("ERROR: dump lacks entry features — re-run mean_revert_replay.py first.")
        return

    print(f"5m_mean_revert FILTER SWEEP — n={len(rows)} signals, metric={KEY} (maker/ideal)")
    print(f"  baseline (all): exp ${_exp([r[KEY] for r in rows]):+.4f}/trade")
    print(f"  guards: BH FDR {FDR_ALPHA}, min-n {MIN_N}, walk-forward 3-fold, deflated Sharpe")
    print("  CAVEAT: screening only — can PROPOSE a forward-test hypothesis, NOT confirm.\n")

    buckets = _buckets(rows)
    results = []
    for label, rs in buckets.items():
        nets = [r[KEY] for r in rs]
        n = len(nets)
        lo, hi, p = _boot_ci_p(nets) if n >= 2 else (0, 0, 1.0)
        results.append({
            "label": label, "n": n, "exp": _exp(nets), "taker_exp": _exp([r["taker_net"] for r in rs]),
            "wr": (100 * sum(1 for x in nets if x > 0) / n) if n else 0,
            "lo": lo, "hi": hi, "p": p, "sharpe": _sharpe(nets),
            "wf": _walkforward_signs(rs, KEY),
        })

    # BH across buckets that clear the n floor (only those are eligible "trials")
    eligible = [r for r in results if r["n"] >= MIN_N]
    pvals = [r["p"] for r in eligible]
    mask = ST.benjamini_hochberg(pvals, alpha=FDR_ALPHA)
    for r, ok in zip(eligible, mask):
        r["bh"] = ok

    # deflated Sharpe on the best eligible bucket, charged for n_trials = len(eligible)
    dsr = None
    if eligible:
        best = max(eligible, key=lambda r: r["sharpe"])
        trial_sharpes = [r["sharpe"] for r in eligible]
        var_ts = (sum((s - sum(trial_sharpes) / len(trial_sharpes)) ** 2 for s in trial_sharpes)
                  / max(1, len(trial_sharpes) - 1))
        try:
            dsr = ST.deflated_sharpe_ratio(best["sharpe"], best["n"], len(eligible), var_ts)
        except Exception:
            dsr = None

    print(f"  {'bucket':<18}{'n':>5}{'maker exp':>12}{'taker':>10}{'WR%':>6}{'p':>7}  walk-fwd  flags")
    for r in sorted(results, key=lambda r: -r["exp"]):
        wf = "".join("+" if s else "-" for s in r["wf"]) if r["wf"] else "n/a"
        flags = []
        if r["n"] < MIN_N:
            flags.append("small-n")
        if r.get("bh"):
            flags.append("BH-SURVIVES")
        if r["lo"] > 0:
            flags.append("CI>0")
        if r["wf"] and all(r["wf"]):
            flags.append("WF-stable")
        fl = " ".join(flags)
        print(f"  {r['label']:<18}{r['n']:>5}{r['exp']:>+12.4f}{r['taker_exp']:>+10.4f}"
              f"{r['wr']:>6.0f}{r['p']:>7.3f}  {wf:>7}   {fl}")

    print("\n--- VERDICT ---")
    survivors = [r for r in eligible if r.get("bh") and r["wf"] and all(r["wf"]) and r["lo"] > 0]
    if survivors:
        print("  Candidate sub-population(s) survive BH + walk-forward + CI>0:")
        for r in survivors:
            print(f"    {r['label']}: n={r['n']}, maker ${r['exp']:+.4f}/trade, taker ${r['taker_exp']:+.4f}, WR {r['wr']:.0f}%")
        print("  -> propose a BOUNDED LIVE FORWARD-TEST of this filter (NOT a deploy).")
        print("     Taker still loses even in survivors unless taker_exp>0 — keep maker-only.")
    else:
        print("  NO sub-population survives BH-FDR + walk-forward + CI>0.")
        print("  The apparent per-symbol/per-bucket winners are consistent with multiple-")
        print("  comparison noise. No defensible filter edge in this data. Per edge-hunt-")
        print("  exhaustion: stop mining; the signal is marginal and execution-trapped at maker,")
        print("  loss-making at taker. Real improvement needs a different signal, not a filter.")
    if dsr is not None:
        print(f"\n  deflated Sharpe (best bucket, charged for {len(eligible)} trials): {dsr:.3f}"
              f"   ({'>0.95 = real' if dsr > 0.95 else 'below 0.95 bar -> not significant'})")


if __name__ == "__main__":
    main()
