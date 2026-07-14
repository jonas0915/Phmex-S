#!/usr/bin/env python3
"""MR symbol map — per-symbol edge table, discriminator scan, combined-book estimate.

Reads the existing replay dumps (no refetch, no live state):
  * reports/mr_replay_90d.json      (baseline 15-pair replay, fetched 6/30)
  * reports/mr_expansion_90d.json   (expansion candidates, fetched 7/13 — optional)

Outputs:
  1. Per-symbol table: n, maker net, expectancy, WR, seeded bootstrap CI vs zero.
  2. Discriminator scan: per-symbol behavior properties from the cached 5m OHLCV
     (median ATR%, fraction of closes inside the Bollinger bands, median ADX,
     median BB width) vs per-symbol maker expectancy — Spearman rho with a
     permutation p-value. n_symbols is tiny; this is descriptive, not proof.
  3. Combined-book scenarios (drop bleeders / add positive candidates) with a
     3-fold chronological walk-forward, restricted to the window where baseline
     and expansion data OVERLAP (they were fetched 13 days apart).

HONESTY: every per-symbol n is 10-40 — nearly all CIs straddle zero. Any
"drop the losers, add the winners" book is assembled by PEEKING at outcomes:
selection bias by construction. Output is hypothesis-generation for a bounded
live forward test, never proof. Per edge-hunt-exhaustion: replay can only REJECT.

Run from repo root:
    python3 scripts/slot_lab/mr_symbol_map.py
    python3 scripts/slot_lab/mr_symbol_map.py --no-expansion   # baseline only
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import random
import sys
from collections import defaultdict

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))

KEY = "maker_net"           # decision metric (taker already rejected by baseline run)
N_BOOT = 4000
WARMUP = 200                # match mean_revert_replay.WARMUP


def _boot_ci(xs, n_boot=N_BOOT, alpha=0.05, seed=0):
    if len(xs) < 2:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(xs)
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return (means[int(alpha / 2 * n_boot)], means[int((1 - alpha / 2) * n_boot) - 1])


def _sym_table(rows, label):
    by = defaultdict(list)
    for r in rows:
        by[r["sym"]].append(r)
    out = []
    for sym, rs in by.items():
        nets = [r[KEY] for r in rs]
        n = len(nets)
        exp = sum(nets) / n
        lo, hi = _boot_ci(nets, seed=hash(sym) % 10000)
        out.append({
            "sym": sym, "n": n, "net": sum(nets), "exp": exp,
            "wr": 100 * sum(1 for x in nets if x > 0) / n,
            "lo": lo, "hi": hi,
            "taker_exp": sum(r["taker_net"] for r in rs) / n,
            "verdict": ("POS(CI>0)" if lo > 0 else
                        "BLEEDER(CI<0)" if hi < 0 else
                        "pos?" if exp > 0 else "neg?"),
        })
    out.sort(key=lambda r: -r["exp"])
    print(f"\n=== {label}: per-symbol maker results (ranked by expectancy) ===")
    print(f"  {'sym':<10}{'n':>4}{'net$':>9}{'exp$/tr':>10}{'WR%':>6}"
          f"{'CI lo':>9}{'CI hi':>9}{'taker$':>9}  verdict")
    for r in out:
        print(f"  {r['sym']:<10}{r['n']:>4}{r['net']:>+9.2f}{r['exp']:>+10.4f}"
              f"{r['wr']:>6.0f}{r['lo']:>+9.4f}{r['hi']:>+9.4f}"
              f"{r['taker_exp']:>+9.4f}  {r['verdict']}")
    straddle = sum(1 for r in out if r["lo"] <= 0 <= r["hi"])
    print(f"  NOTE: {straddle}/{len(out)} symbol CIs straddle zero (tiny n — expected).")
    return out


# ---------------- discriminator ----------------

def _sym_props(sym, days=90):
    """Behavior properties from the cached 5m OHLCV this rig wrote. SAFE pickle:
    self-generated DataFrames in our own reports/cache/ only — never untrusted."""
    from indicators import add_all_indicators
    path = os.path.join(_BOT_DIR, "reports", "cache",
                        f"{sym}_USDT_USDT_5m_{days}d.pkl")
    if not os.path.exists(path):
        return None
    df = add_all_indicators(pickle.load(open(path, "rb"))).iloc[WARMUP:]
    df = df.dropna(subset=["atr", "adx", "bb_upper", "bb_lower"])
    if df.empty:
        return None
    atr_pct = (df["atr"] / df["close"] * 100)
    inside = ((df["close"] < df["bb_upper"]) & (df["close"] > df["bb_lower"]))
    return {
        "atr_pct_med": float(atr_pct.median()),
        "inside_bb_frac": float(inside.mean() * 100),
        "adx_med": float(df["adx"].median()),
        "bb_width_med": float((df["bb_width"] * 100).median()),
    }


def _spearman_perm(xs, ys, n_perm=10000, seed=0):
    """Spearman rho + two-sided permutation p (implemented locally; no scipy dep)."""
    def _rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        rk = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk

    def _pearson(a, b):
        n = len(a)
        ma, mb = sum(a) / n, sum(b) / n
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        da = math.sqrt(sum((x - ma) ** 2 for x in a))
        db = math.sqrt(sum((y - mb) ** 2 for y in b))
        return num / (da * db) if da > 0 and db > 0 else 0.0

    rx, ry = _rank(xs), _rank(ys)
    rho = _pearson(rx, ry)
    rng = random.Random(seed)
    hits = 0
    ry2 = ry[:]
    for _ in range(n_perm):
        rng.shuffle(ry2)
        if abs(_pearson(rx, ry2)) >= abs(rho):
            hits += 1
    return rho, hits / n_perm


def _discriminator(sym_rows):
    print("\n=== DISCRIMINATOR SCAN: symbol property vs maker expectancy ===")
    props, exps, syms = [], [], []
    for r in sym_rows:
        p = _sym_props(r["sym"])
        if p:
            props.append(p)
            exps.append(r["exp"])
            syms.append(r["sym"])
    if len(props) < 5:
        print("  too few symbols with cached 5m data — skipped")
        return
    print(f"  symbols with cached 5m data: {len(syms)}")
    print(f"  {'sym':<10}{'exp$/tr':>10}{'ATR%med':>9}{'insideBB%':>11}{'ADXmed':>8}{'BBw%med':>9}")
    for s, e, p in sorted(zip(syms, exps, props), key=lambda t: -t[1]):
        print(f"  {s:<10}{e:>+10.4f}{p['atr_pct_med']:>9.3f}{p['inside_bb_frac']:>11.1f}"
              f"{p['adx_med']:>8.1f}{p['bb_width_med']:>9.3f}")
    for k, name in [("atr_pct_med", "median ATR%"), ("inside_bb_frac", "% closes inside BB"),
                    ("adx_med", "median ADX"), ("bb_width_med", "median BB width%")]:
        rho, p = _spearman_perm([pp[k] for pp in props], exps)
        flag = " <-- candidate" if p < 0.05 else ""
        print(f"  Spearman({name} , exp): rho={rho:+.3f}  perm-p={p:.3f}{flag}")
    print(f"  CAVEAT: n_symbols={len(syms)} — descriptive only; a 'significant' rho at"
          f" this n across 4 tested properties is fragile (multiple comparisons).")


# ---------------- combined book ----------------

def _book(rows, label):
    nets = [r[KEY] for r in rows]
    n = len(nets)
    if not n:
        print(f"  {label:<44} n=0")
        return
    exp = sum(nets) / n
    lo, hi = _boot_ci(nets, seed=1)
    wr = 100 * sum(1 for x in nets if x > 0) / n
    print(f"  {label:<44} n={n:>3}  net ${sum(nets):+8.2f}  exp ${exp:+.4f}"
          f"  CI[{lo:+.4f},{hi:+.4f}]  WR {wr:.0f}%")


def _folds(rows, label, folds=3):
    srt = sorted(rows, key=lambda r: r["ts"])
    if len(srt) < folds * 4:
        print(f"  {label}: too few rows for folds")
        return
    sz = len(srt) // folds
    parts = []
    for f in range(folds):
        seg = srt[f * sz:(f + 1) * sz] if f < folds - 1 else srt[f * sz:]
        nets = [r[KEY] for r in seg]
        parts.append(f"fold{f+1} n={len(seg)} ${sum(nets)/len(nets):+.4f}")
    print(f"  {label} walk-forward: " + " | ".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default="reports/mr_replay_90d.json")
    ap.add_argument("--expansion", default="reports/mr_expansion_90d.json")
    ap.add_argument("--no-expansion", action="store_true")
    args = ap.parse_args()

    base = json.load(open(os.path.join(_BOT_DIR, args.baseline)))
    brows = base["rows"]
    bt = (min(r["ts"] for r in brows), max(r["ts"] for r in brows))
    print(f"BASELINE {args.baseline}: n={len(brows)} rows, "
          f"ts {bt[0]}..{bt[1]} (epochs; fetched 6/30)")

    bsym = _sym_table(brows, "BASELINE 90d (fetched 6/30)")
    _discriminator(bsym)

    erows = []
    if not args.no_expansion and os.path.exists(os.path.join(_BOT_DIR, args.expansion)):
        exp = json.load(open(os.path.join(_BOT_DIR, args.expansion)))
        erows = exp["rows"]
        et = (min(r["ts"] for r in erows), max(r["ts"] for r in erows))
        print(f"\nEXPANSION {args.expansion}: n={len(erows)} rows, ts {et[0]}..{et[1]}")
        _sym_table(erows, "EXPANSION candidates 90d (fetched 7/13)")

    # ---- combined-book scenarios ----
    print("\n=== COMBINED-BOOK SCENARIOS (maker fill-all; SELECTION-BIASED — ===")
    print("===  assembled by peeking at outcomes; hypothesis-generation ONLY) ===")
    strict_bleed = {r["sym"] for r in bsym if r["hi"] < 0}
    loose_bleed = {r["sym"] for r in bsym if r["exp"] < 0}
    print(f"  strict bleeders (CI hi<0): {sorted(strict_bleed) or 'NONE'}")
    print(f"  loose bleeders (exp<0):    {sorted(loose_bleed) or 'NONE'}")

    _book(brows, "baseline (all 15 pairs)")
    _book([r for r in brows if r["sym"] not in strict_bleed], "baseline - strict bleeders")
    _book([r for r in brows if r["sym"] not in loose_bleed], "baseline - loose bleeders")

    if erows:
        esym = _sym_table(erows, "(recap for scenario build)") if False else None
        eby = defaultdict(list)
        for r in erows:
            eby[r["sym"]].append(r)
        epos = {s for s, rs in eby.items()
                if sum(r[KEY] for r in rs) / len(rs) > 0}
        print(f"  expansion positives (exp>0, PEEKED): {sorted(epos) or 'NONE'}")

        # overlap window so folds compare like-for-like periods
        o0 = max(min(r["ts"] for r in brows), min(r["ts"] for r in erows))
        o1 = min(max(r["ts"] for r in brows), max(r["ts"] for r in erows))
        bo = [r for r in brows if o0 <= r["ts"] <= o1]
        eo = [r for r in erows if o0 <= r["ts"] <= o1]
        print(f"  overlap window: {o0}..{o1} "
              f"({(o1-o0)/86400:.0f}d; baseline rows {len(bo)}, expansion rows {len(eo)})")

        _book(bo, "baseline (overlap window)")
        comb_all = bo + eo
        _book(comb_all, "baseline + ALL candidates (overlap)")
        comb = ([r for r in bo if r["sym"] not in loose_bleed]
                + [r for r in eo if r["sym"] in epos])
        _book(comb, "(-loose bleeders) + (+pos candidates) [PEEKED]")
        print()
        _folds(bo, "baseline (overlap)")
        _folds(comb_all, "baseline + ALL candidates (overlap)")
        _folds(comb, "curated book [PEEKED]")

    print("\n  REMINDER: curated-book numbers are in-sample selection. The only")
    print("  legitimate use is choosing FORWARD-TEST candidates, not forecasting PnL.")


if __name__ == "__main__":
    main()
