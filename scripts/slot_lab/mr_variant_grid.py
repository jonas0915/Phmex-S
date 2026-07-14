#!/usr/bin/env python3
"""5m_mean_revert SIGNAL-LOOSENING variant grid — SCREENING-GRADE.

Question: does a LOOSER bb_mean_reversion signal definition produce MORE
signals while keeping net maker-fill expectancy non-negative? Or is the
current tight confluence the edge?

Reuses the validated machinery of scripts/slot_lab/mean_revert_replay.py
(same cached 90d OHLCV, same _build_path / _simulate / _net / bootstrap,
same fees & exit geometry) — this file only PARAMETERIZES the signal
definition and sweeps a small grid. DOES NOT modify any existing file.

Signal reimplementation is VALIDATED at runtime: variant V0 (= live params)
must reproduce the exact signal set of reports/mr_replay_90d.json
(same (sym, ts, side) keys, same n=309) or the script ABORTS.

Grid axes (mapped to strategies.py:22-118 internals):
  rsi_lo/rsi_hi   RSI(7) oversold/overbought bounds (live 30/70)
  vol_mult        volume > vol_avg20 * X          (live 1.3)
  pen             prev-bar wick penetration frac  (live 0.002 = 0.2%)
  adx_cap         ADX hard block above            (live 30)
  bbw_mult        BB width >= X * ATR%            (live 1.5)
  trend_k         trend votes needed to block     (live 2 of 3)
  confluence      'and' = RSI AND vol (live) | 'or' = RSI OR vol

NOTE on the slot's 0.80 strength gate: the strategy emits 0.85 base strength
whenever it fires (strategies.py:88,108), so 0.80 never blocks — lowering it
to 0.75/0.70 adds ZERO signals. Verified programmatically below.

HONESTY CAVEATS (inherited from mean_revert_replay.py, printed at runtime):
  * maker fill-all is OPTIMISTIC (real fill rate ~27%) — upper bound on edge.
  * OB/tape gates not modeled; occupancy not modeled.
  * Cached data window ends 2026-06-30 (cache mtime) — this is the SAME window
    as the baseline report, chosen deliberately for exact comparability.
  * Replay trail arms at 5% ROI (backtest.py:596 constant); live is 8% since
    7/5. Identical across variants, so A/B ranking unaffected.
  * Backtest can only REJECT, never confirm (edge-hunt-exhaustion).

Read-only w.r.t. live: touches no bot state, no restart.

Run from repo root:
    python scripts/slot_lab/mr_variant_grid.py
    python scripts/slot_lab/mr_variant_grid.py --dump-json reports/mr_variant_grid_90d.json
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys

import numpy as np

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts", "slot_lab"))

import mean_revert_replay as MR              # noqa: E402  (reuse, don't reinvent)
from indicators import add_all_indicators    # noqa: E402
from st2_lab.exit_replay import _simulate    # noqa: E402
from st2_lab import stats as ST              # noqa: E402

DAYS = 90
BASELINE_JSON = os.path.join(_BOT_DIR, "reports", "mr_replay_90d.json")
CACHE_DIR = os.path.join(_BOT_DIR, "reports", "cache")

LIVE = dict(rsi_lo=30.0, rsi_hi=70.0, vol_mult=1.3, pen=0.002,
            adx_cap=30.0, bbw_mult=1.5, trend_k=2, confluence="and")


def _v(name, **over):
    p = dict(LIVE)
    p.update(over)
    p["name"] = name
    return p


# ---- the grid (16 variants + V0 baseline = 17 signal definitions tested) ----
GRID = [
    _v("V0_baseline"),
    # single-axis looseners
    _v("V1_rsi32", rsi_lo=32, rsi_hi=68),
    _v("V2_rsi35", rsi_lo=35, rsi_hi=65),
    _v("V3_vol1.15", vol_mult=1.15),
    _v("V4_vol1.0", vol_mult=1.0),
    _v("V5_pen0.1pct", pen=0.001),
    _v("V6_pen0", pen=0.0),
    _v("V7_adx35", adx_cap=35),
    _v("V8_bbw1.2", bbw_mult=1.2),
    _v("V9_trendk3", trend_k=3),
    _v("V10_conf_or", confluence="or"),
    # mild combos
    _v("V11_rsi32_vol1.15", rsi_lo=32, rsi_hi=68, vol_mult=1.15),
    _v("V12_rsi32_pen0.1", rsi_lo=32, rsi_hi=68, pen=0.001),
    _v("V13_vol1.15_pen0.1", vol_mult=1.15, pen=0.001),
    _v("V14_rsi32_vol1.15_pen0.1", rsi_lo=32, rsi_hi=68, vol_mult=1.15, pen=0.001),
    # aggressive combos
    _v("V15_rsi35_vol1.0_pen0", rsi_lo=35, rsi_hi=65, vol_mult=1.0, pen=0.0),
    _v("V16_max_loose", rsi_lo=35, rsi_hi=65, vol_mult=1.0, pen=0.0,
       adx_cap=35, bbw_mult=1.2),
    # ROUND 2 — asymmetric decomposition, added AFTER seeing that round-1 added
    # trades were short-positive/long-negative (extra selection bias: these were
    # chosen with knowledge of the data; deflate accordingly). rsi_lo/rsi_hi are
    # independent, so loosening only one side is a faithful one-sided variant.
    _v("V17_short_rsi65", rsi_hi=65),            # loosen SHORTS only
    _v("V18_long_rsi35", rsi_lo=35),             # loosen LONGS only (control)
    _v("V19_short_rsi65_pen0", rsi_hi=65, pen=0.0),  # pen affects both sides
]
N_VARIANTS_TESTED = len(GRID) - 1  # exclude baseline; record for deflation


def _load_cached(sym, tf):
    key = f"{sym.replace('/', '_').replace(':', '_')}_{tf}_{DAYS}d.pkl"
    path = os.path.join(CACHE_DIR, key)
    if not os.path.exists(path):
        raise FileNotFoundError(f"cache missing: {path} — run mean_revert_replay.py first "
                                f"(this grid must use the SAME data window as the baseline)")
    # SAFE: cache written by our own rig (self-generated DataFrames), never untrusted.
    return pickle.load(open(path, "rb"))


def _features(df5):
    """Extract per-bar numpy features once; each variant is then pure array math
    replicating strategies.bb_mean_reversion_strategy exactly."""
    f = {}
    g = lambda c: df5[c].to_numpy(dtype=float)  # noqa: E731
    for c in ("close", "high", "low", "volume", "bb_upper", "bb_lower", "bb_mid",
              "rsi_fast", "adx", "plus_di", "minus_di",
              "ema_9", "ema_21", "ema_50", "ema_200", "atr"):
        f[c] = g(c)
    f["vol_avg20"] = df5["volume"].rolling(20).mean().to_numpy(dtype=float)
    for c in ("close", "high", "low", "bb_upper", "bb_lower"):
        f["prev_" + c] = np.roll(f[c], 1)
        f["prev_" + c][0] = np.nan
    f["epoch"] = (df5.index.view("int64") // 1_000_000_000).astype(np.int64)
    return f


def _variant_masks(f, p):
    """Boolean long/short candidate masks + strength arrays (pre-cooldown).
    Mirrors strategies.py:22-118 with parameterized thresholds. NaN comparisons
    are False (same semantics as the scalar code)."""
    with np.errstate(invalid="ignore"):
        adx_ok = ~(f["adx"] > p["adx_cap"])                      # ADX cap block
        bbw = np.where(f["bb_mid"] > 0,
                       (f["bb_upper"] - f["bb_lower"]) / f["bb_mid"], 0.0)
        atr_pct = np.where(f["close"] > 0, f["atr"] / f["close"], 0.0)
        bbw_ok = ~((atr_pct > 0) & (bbw < p["bbw_mult"] * atr_pct))

        ema_bear = (f["ema_9"] < f["ema_21"]) & (f["ema_21"] < f["ema_50"])
        ema_bull = (f["ema_9"] > f["ema_21"]) & (f["ema_21"] > f["ema_50"])
        below200 = (f["ema_200"] > 0) & (f["close"] < f["ema_200"])
        above200 = (f["ema_200"] > 0) & (f["close"] > f["ema_200"])
        di_bear = (f["adx"] > 20) & (f["minus_di"] > f["plus_di"] * 1.3)
        di_bull = (f["adx"] > 20) & (f["plus_di"] > f["minus_di"] * 1.3)
        downtrend = (ema_bear.astype(int) + below200.astype(int)
                     + di_bear.astype(int)) >= p["trend_k"]
        uptrend = (ema_bull.astype(int) + above200.astype(int)
                   + di_bull.astype(int)) >= p["trend_k"]

        vol_ok = f["volume"] > f["vol_avg20"] * p["vol_mult"]
        rsi_lo_ok = f["rsi_fast"] < p["rsi_lo"]
        rsi_hi_ok = f["rsi_fast"] > p["rsi_hi"]
        if p["confluence"] == "and":
            conf_long, conf_short = rsi_lo_ok & vol_ok, rsi_hi_ok & vol_ok
        else:
            conf_long, conf_short = rsi_lo_ok | vol_ok, rsi_hi_ok | vol_ok

        pen_long = ((f["prev_close"] <= f["prev_bb_lower"]) |
                    (f["prev_low"] < f["prev_bb_lower"] * (1 - p["pen"])))
        pen_short = ((f["prev_close"] >= f["prev_bb_upper"]) |
                     (f["prev_high"] > f["prev_bb_upper"] * (1 + p["pen"])))
        reenter_long = f["close"] > f["bb_lower"]
        reenter_short = f["close"] < f["bb_upper"]

        long_m = (adx_ok & bbw_ok & pen_long & reenter_long & ~downtrend & conf_long)
        short_m = (adx_ok & bbw_ok & pen_short & reenter_short & ~uptrend & conf_short)
        short_m &= ~long_m  # strategy evaluates LONG first (priority on conflict)

        str_long = np.where(f["rsi_fast"] < 15, 0.90, 0.85)
        str_short = np.where(f["rsi_fast"] > 85, 0.90, 0.85)
    return long_m, short_m, str_long, str_short


def _gen_signals(f, sym, p, strength_gate=0.80):
    """Apply masks bar-by-bar with the rig's per-symbol cooldown (= hold window)."""
    long_m, short_m, str_l, str_s = _variant_masks(f, p)
    sigs = []
    cooldown_until = 0
    n = len(f["close"])
    for i in range(MR.WARMUP, n):
        ts = int(f["epoch"][i]) + 300  # bar close = decision time (rig convention)
        if ts < cooldown_until:
            continue
        if long_m[i]:
            side, strength = "long", float(str_l[i])
        elif short_m[i]:
            side, strength = "short", float(str_s[i])
        else:
            continue
        if strength < strength_gate:
            continue
        sigs.append({"symbol": sym, "side": side, "close": float(f["close"][i]),
                     "entry_ts": ts, "strength": strength})
        cooldown_until = ts + MR.PARAMS["hold_secs"]
    return sigs


def _replay_memo(sig, df1m, memo):
    key = (sig["symbol"], sig["entry_ts"], sig["side"])
    if key in memo:
        return memo[key]
    path = MR._build_path(df1m, sig["entry_ts"], MR.PARAMS["hold_secs"], sig["side"])
    if not path:
        memo[key] = None
        return None
    px = sig["close"]  # maker fill at close (rig convention)
    exit_px, reason, _ = _simulate(sig["symbol"], sig["side"], px,
                                   sig["entry_ts"], path, MR.PARAMS, variant=True)
    row = {"sym": sig["symbol"].split("/")[0], "side": sig["side"],
           "ts": sig["entry_ts"], "strength": sig["strength"],
           "net": MR._net(px, exit_px, sig["side"], reason, MR.NOTIONAL, MR.MAKER_FEE),
           "reason": reason}
    memo[key] = row
    return row


def _fold_of(ts, bounds):
    for k, b in enumerate(bounds):
        if ts < b:
            return k
    return len(bounds)


def _summarize(name, rows, fold_bounds):
    nets = [r["net"] for r in rows]
    n = len(nets)
    tot = sum(nets)
    exp = tot / n if n else 0.0
    wins = sum(1 for x in nets if x > 0)
    lo, hi = MR._boot_mean_ci(nets)
    folds = [[], [], []]
    for r in rows:
        folds[_fold_of(r["ts"], fold_bounds)].append(r["net"])
    fexp = [(sum(f) / len(f) if f else float("nan")) for f in folds]
    # outlier sensitivity: expectancy with the top-2 winners removed
    trimmed = sorted(nets)[:-2] if n > 4 else nets
    texp = sum(trimmed) / len(trimmed) if trimmed else 0.0
    return {"name": name, "n": n, "net": tot, "exp": exp, "ci": [lo, hi],
            "win_rate": wins / n if n else 0.0, "fold_exp": fexp, "trim2_exp": texp,
            "n_long": sum(1 for r in rows if r["side"] == "long"),
            "n_short": sum(1 for r in rows if r["side"] == "short")}


def main():
    ap = argparse.ArgumentParser(description="bb_mean_reversion loosening variant grid")
    ap.add_argument("--dump-json", default=None)
    args = ap.parse_args()

    print("5m_mean_revert LOOSENING GRID — SCREENING-GRADE (maker fill-all upper bound)")
    print(f"  {N_VARIANTS_TESTED} variants + baseline | pairs={len(MR.DEFAULT_PAIRS)} | "
          f"days={DAYS} | fees maker {MR.MAKER_FEE}%/side | exits sl=1.2/tp=1.6/trail@5/4h")
    print("  CAVEATS: fill-all optimistic (~27% real); OB/tape gates + occupancy not modeled;")
    print("  data window = cached baseline window (ends 2026-06-30); reject-only evidence.")

    # ---- load data + indicators once ----
    feats, dfs1m = {}, {}
    t_lo, t_hi = None, None
    for sym in MR.DEFAULT_PAIRS:
        df5 = add_all_indicators(_load_cached(sym, "5m"))
        dfs1m[sym] = _load_cached(sym, "1m")
        f = _features(df5)
        feats[sym] = f
        lo, hi = int(f["epoch"][MR.WARMUP]) + 300, int(f["epoch"][-1]) + 300
        t_lo = lo if t_lo is None else min(t_lo, lo)
        t_hi = hi if t_hi is None else max(t_hi, hi)
        print(f"  loaded {sym}: {len(df5)} 5m bars, {len(dfs1m[sym])} 1m bars")
    fold_bounds = [t_lo + (t_hi - t_lo) / 3, t_lo + 2 * (t_hi - t_lo) / 3]
    print(f"  calendar folds (epoch): [{t_lo}..{fold_bounds[0]:.0f}.."
          f"{fold_bounds[1]:.0f}..{t_hi}]")

    # ---- generate + replay each variant (memoized exits) ----
    memo = {}
    results, rows_by_variant = [], {}
    for p in GRID:
        rows = []
        min_strength = 1.0
        for sym in MR.DEFAULT_PAIRS:
            sigs = _gen_signals(feats[sym], sym, p)
            for s in sigs:
                min_strength = min(min_strength, s["strength"])
                r = _replay_memo(s, dfs1m[sym], memo)
                if r:
                    rows.append(r)
        rows_by_variant[p["name"]] = rows
        s = _summarize(p["name"], rows, fold_bounds)
        s["params"] = {k: v for k, v in p.items() if k != "name"}
        s["min_emitted_strength"] = min_strength
        results.append(s)
        print(f"  {p['name']:<28} n={s['n']:>4}  net ${s['net']:+8.2f}  "
              f"exp ${s['exp']:+.4f}  CI [{s['ci'][0]:+.4f},{s['ci'][1]:+.4f}]  "
              f"win {s['win_rate']*100:4.1f}%  folds "
              f"[{s['fold_exp'][0]:+.4f},{s['fold_exp'][1]:+.4f},{s['fold_exp'][2]:+.4f}]")

    # ---- VALIDATION: V0 must reproduce the baseline report exactly ----
    base_rows = rows_by_variant["V0_baseline"]
    ref = json.load(open(BASELINE_JSON))
    ref_keys = {(r["sym"], r["ts"], r["side"]) for r in ref["rows"]}
    v0_keys = {(r["sym"], r["ts"], r["side"]) for r in base_rows}
    net_ref, net_v0 = ref["maker"]["net"], sum(r["net"] for r in base_rows)
    print(f"\nVALIDATION vs {os.path.basename(BASELINE_JSON)}:")
    print(f"  signal set: {len(v0_keys)} regenerated vs {len(ref_keys)} reference; "
          f"missing={len(ref_keys - v0_keys)} extra={len(v0_keys - ref_keys)}")
    print(f"  maker net:  ${net_v0:+.4f} regenerated vs ${net_ref:+.4f} reference")
    if v0_keys != ref_keys:
        print("  *** ABORT: baseline signal set does NOT reproduce the rig — "
              "variant numbers would be untrustworthy. ***")
        for k in sorted(ref_keys - v0_keys)[:10]:
            print(f"    missing: {k}")
        for k in sorted(v0_keys - ref_keys)[:10]:
            print(f"    extra:   {k}")
        sys.exit(1)
    if abs(net_v0 - net_ref) > 0.05:
        print("  *** ABORT: baseline net PnL mismatch > $0.05 — exit engine drifted. ***")
        sys.exit(1)
    print("  PASS — reimplementation is faithful.")

    base = next(r for r in results if r["name"] == "V0_baseline")
    print(f"\n  strength-gate note: min emitted strength across ALL variants = "
          f"{min(r['min_emitted_strength'] for r in results):.2f} -> the slot's 0.80 "
          f"gate blocks nothing; lowering it to 0.75/0.70 adds ZERO signals.")

    # ---- marginal (added-trade) analysis + diff CIs vs baseline ----
    base_keys = {(r["sym"], r["ts"], r["side"]) for r in base_rows}
    base_nets = [r["net"] for r in base_rows]
    print(f"\n{'variant':<28}{'n':>5}{'exp':>9}{'added':>6}{'addExp':>9}"
          f"{'addCI':>20}{'removed':>8}{'diffCI(v-base)':>20}")
    for res in results:
        if res["name"] == "V0_baseline":
            continue
        rows = rows_by_variant[res["name"]]
        keys = {(r["sym"], r["ts"], r["side"]) for r in rows}
        added = [r for r in rows if (r["sym"], r["ts"], r["side"]) not in base_keys]
        removed = len(base_keys - keys)
        a_nets = [r["net"] for r in added]
        a_exp = sum(a_nets) / len(a_nets) if a_nets else float("nan")
        a_ci = MR._boot_mean_ci(a_nets) if a_nets else (float("nan"),) * 2
        d_ci = ST.bootstrap_diff_ci([r["net"] for r in rows], base_nets)
        res["added_n"] = len(added)
        res["added_exp"] = a_exp
        res["added_ci"] = list(a_ci)
        res["removed_n"] = removed
        res["diff_ci_vs_base"] = list(d_ci)
        print(f"{res['name']:<28}{res['n']:>5}{res['exp']:>+9.4f}{len(added):>6}"
              f"{a_exp:>+9.4f}  [{a_ci[0]:+.4f},{a_ci[1]:+.4f}]{removed:>8}"
              f"  [{d_ci[0]:+.4f},{d_ci[1]:+.4f}]")

    # ---- honest selection discipline ----
    print(f"\nSELECTION DISCIPLINE ({N_VARIANTS_TESTED} variants tested):")
    print(f"  Deflation: {N_VARIANTS_TESTED} trials at family alpha 0.05 -> per-trial "
          f"~{0.05 / N_VARIANTS_TESTED:.4f} (Bonferroni).")
    print("  A SHIP-CANDIDATE must: (a) n >= 1.5x baseline; (b) beat baseline expectancy")
    print("  in ALL 3 calendar folds; (c) added-trades expectancy > 0; (d) survive top-2")
    print("  outlier trim; (e) diff-CI(v-base) lower bound > 0 at 95% (still weak vs the")
    print("  0.003 bar — anything less than ALL of (a)-(e) is WEAK or DEAD).")
    any_candidate = False
    for res in results:
        if res["name"] == "V0_baseline":
            continue
        checks = {
            "1.5x_count": res["n"] >= 1.5 * base["n"],
            "all_folds_beat": all((not np.isnan(v)) and (not np.isnan(b)) and v >= b
                                  for v, b in zip(res["fold_exp"], base["fold_exp"])),
            "added_exp_pos": (res["added_n"] > 0 and not np.isnan(res["added_exp"])
                              and res["added_exp"] > 0),
            "trim2_survives": res["trim2_exp"] >= base["trim2_exp"],
            "diff_ci_gt0": res["diff_ci_vs_base"][0] > 0,
        }
        res["checks"] = checks
        passed = sum(checks.values())
        if passed >= 4:
            any_candidate = True
        flag = "SHIP-CANDIDATE" if all(checks.values()) else (
            "NEAR-MISS" if passed >= 4 else "")
        print(f"  {res['name']:<28} {passed}/5  "
              f"{' '.join(k for k, v in checks.items() if v) or '-'}  {flag}")
    if not any_candidate:
        print("\n  VERDICT: no variant clears even 4/5 — loosening does not survive")
        print("  honest selection on this window. The tight definition IS the edge")
        print("  (or the sample cannot distinguish). Keep the live definition.")

    if args.dump_json:
        out = os.path.join(_BOT_DIR, args.dump_json) if not os.path.isabs(args.dump_json) else args.dump_json
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w") as fh:
            json.dump({"n_variants_tested": N_VARIANTS_TESTED,
                       "fold_bounds": fold_bounds, "results": results,
                       "rows": {k: v for k, v in rows_by_variant.items()}}, fh, indent=1)
        print(f"\n  dump: {out}")


if __name__ == "__main__":
    main()
