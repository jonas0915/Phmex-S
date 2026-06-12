#!/usr/bin/env python3
"""Phase-3 cohort-gate simulation sweep (2026-06-11, edge plan §6 Phase 3).

Runs the flow-replay backtester (new exit engine, 2026-06-11) on the May
validation window (same data/window as scripts/calibrate_flow.py) once per
candidate entry-gate config and reports deltas vs baseline:

  A  --block-ltbias X        skip entry when aligned large_trade_bias >= X
  B  --block-adx5m X         skip entry when 5m ADX at entry >= X
  C  --min-conf N            raise ensemble floor (live 4/7; replay caps 6/7)
  D  --extra-blocked-hours   append UTC hours to BLOCKED_HOURS_UTC
  A' --no-whale-boost        reverse the aligned-whale +0.03 strength boost

All configs run in ONE process (candles + FlowIndex loaded once). Fee model:
measured live round trip 0.0663% of notional (docs/2026-06-11-fee-ground-truth.md)
unless a config overrides it. A 0.22% baseline is included as a regression check
against the 2026-06-11 addendum numbers (45 trades / -$22.46 / 44.4% WR).

HONESTY NOTE: the window (5/11-5/30) overlaps the 60d data that motivated these
gates — this is IN-SAMPLE. The value here is interaction effects + entry-
composition shifts (freed MAX_OPEN_TRADES slots, cooldown chains), not
independent confirmation.

Run from repo root:
    python scripts/cohort_gate_sweep.py [--only base,A_0.35,...]
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import run_backtest
from flow_replay import FlowIndex

DATA_DIR = "backtest_data_may"
STRATEGY = "htf_l2_anticipation"
FEE_RT_MEASURED = 0.0663  # % of notional, measured live RT (fee ground truth doc)
SYMBOLS = [
    "ETH/USDT:USDT", "INJ/USDT:USDT", "TON/USDT:USDT", "ONDO/USDT:USDT",
    "WLD/USDT:USDT", "DOGE/USDT:USDT", "XLM/USDT:USDT", "ENA/USDT:USDT",
    "ARB/USDT:USDT", "XRP/USDT:USDT", "BTC/USDT:USDT", "RENDER/USDT:USDT",
    "TAO/USDT:USDT", "CFX/USDT:USDT", "ZEC/USDT:USDT", "BCH/USDT:USDT",
]

# config name -> run_backtest kwargs (beyond the common flow-replay set)
CONFIGS = {
    "base_fee022":  {"fee_rt_pct": 0.22},          # regression check vs addendum
    "base":         {},                             # baseline @ measured fee
    "A_0.35":       {"block_ltbias": 0.35},
    "A_0.25":       {"block_ltbias": 0.25},         # tighter variant
    "B_25":         {"block_adx5m": 25.0},
    "B_20":         {"block_adx5m": 20.0},          # tighter variant
    "C_5":          {"min_conf": 5},
    "C_6":          {"min_conf": 6},                # tighter variant (= 6/6 in replay)
    "D_21-23":      {"extra_blocked_hours": {21, 22, 23}},
    "D_21-23+14":   {"extra_blocked_hours": {14, 21, 22, 23}},  # +7 AM PT variant
    "Aprime_noboost": {"no_whale_boost": True},
    "combo_ABCD":   {"block_ltbias": 0.35, "block_adx5m": 25.0, "min_conf": 5,
                     "extra_blocked_hours": {21, 22, 23}},
    "combo_ABCD+Ap": {"block_ltbias": 0.35, "block_adx5m": 25.0, "min_conf": 5,
                      "extra_blocked_hours": {21, 22, 23}, "no_whale_boost": True},
}


def load_candles(path):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    return df[~df.index.duplicated(keep="last")]


def summarize(trades):
    n = len(trades)
    pnl = sum(t.pnl_usd for t in trades)
    wins = sum(1 for t in trades if t.pnl_usd > 0)
    wr = wins / n * 100 if n else 0.0
    reasons = defaultdict(lambda: [0, 0.0])
    for t in trades:
        reasons[t.exit_reason][0] += 1
        reasons[t.exit_reason][1] += t.pnl_usd
    longs = sum(1 for t in trades if t.direction == "long")
    return {
        "n": n, "pnl": round(pnl, 2), "wr": round(wr, 1), "wins": wins,
        "longs": longs, "shorts": n - longs,
        "reasons": {k: [v[0], round(v[1], 2)] for k, v in sorted(reasons.items())},
    }


def trade_keys(trades):
    return {(t.pair, str(t.entry_time)) for t in trades}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None,
                    help="comma list of config names to run (default: all)")
    args = ap.parse_args()
    selected = set(args.only.split(",")) if args.only else set(CONFIGS)

    pair_data, htf_data = {}, {}
    for sym in SYMBOLS:
        safe = sym.replace("/", "_").replace(":", "_")
        p5 = os.path.join(DATA_DIR, f"{safe}_5m.csv")
        p1 = os.path.join(DATA_DIR, f"{safe}_1h.csv")
        if os.path.exists(p5):
            pair_data[sym] = load_candles(p5)
        if os.path.exists(p1):
            htf_data[sym] = load_candles(p1)
    print(f"loaded candles for {len(pair_data)} symbols")

    idx = FlowIndex()
    lo, hi = idx.coverage_window()
    fmt = lambda t: datetime.fromtimestamp(t, tz=timezone.utc).isoformat() if t else "n/a"
    data_end = max(int(df.index[-1].timestamp()) for df in pair_data.values()) + 300
    print(f"flow: {idx.row_count} rows / {idx.symbol_count} symbols")
    print(f"window: {fmt(lo)} -> {fmt(data_end)}")

    results = {}
    base_trades = None
    out = {"window": [fmt(lo), fmt(data_end)], "fee_rt_default": FEE_RT_MEASURED,
           "configs": {}}

    for name, extra in CONFIGS.items():
        if name not in selected:
            continue
        kw = dict(
            htf_data=htf_data, flow_index=idx, flow_replay=True,
            ae_threshold=-999.0, ae_cycles=10, fee_rt_pct=FEE_RT_MEASURED,
        )
        kw.update(extra)
        print(f"\n##### RUN {name}  extra={extra}")
        trades = run_backtest(pair_data, **kw)
        s = summarize(trades)
        results[name] = (trades, s)
        if name == "base":
            base_trades = trades
        out["configs"][name] = {
            "kwargs": {k: (sorted(v) if isinstance(v, set) else v) for k, v in extra.items()},
            "summary": s,
            "trades": [{
                "pair": t.pair, "dir": t.direction, "entry_time": str(t.entry_time),
                "exit_time": str(t.exit_time), "pnl": round(t.pnl_usd, 4),
                "reason": t.exit_reason, "meta": t.entry_meta,
            } for t in trades],
        }
        print(f"  -> {s['n']} trades | ${s['pnl']:+.2f} | {s['wr']}% WR | "
              f"L/S {s['longs']}/{s['shorts']}")
        for r, (c, p) in s["reasons"].items():
            print(f"     {r:<20} {c:>3} ${p:+7.2f}")

    # ---- comparison table vs base ----
    if base_trades is not None:
        bs = results["base"][1]
        bkeys = trade_keys(base_trades)
        print("\n\n===== COHORT-GATE SWEEP vs BASELINE "
              f"(base: {bs['n']} trades, ${bs['pnl']:+.2f}, {bs['wr']}% WR) =====")
        print(f"{'config':<16} {'n':>4} {'PnL':>9} {'WR%':>6} | {'dN':>5} {'dPnL':>8} "
              f"{'dWR':>6} | {'removed':>7} {'new':>4}")
        for name, (trades, s) in results.items():
            if name == "base":
                continue
            keys = trade_keys(trades)
            removed = len(bkeys - keys)
            new = len(keys - bkeys)
            print(f"{name:<16} {s['n']:>4} {s['pnl']:>+9.2f} {s['wr']:>6.1f} | "
                  f"{s['n']-bs['n']:>+5} {s['pnl']-bs['pnl']:>+8.2f} "
                  f"{s['wr']-bs['wr']:>+6.1f} | {removed:>7} {new:>4}")
            out["configs"][name]["vs_base"] = {
                "d_n": s["n"] - bs["n"], "d_pnl": round(s["pnl"] - bs["pnl"], 2),
                "d_wr": round(s["wr"] - bs["wr"], 1),
                "base_entries_removed": removed, "new_entries": new,
            }

        # ---- entry-time flow coverage (baseline) ----
        metas = [t.entry_meta for t in base_trades if t.entry_meta]
        with_lt = [m for m in metas if m.get("lt_bias") is not None]
        ages = sorted(m["flow_age_s"] for m in metas if m.get("flow_age_s") is not None)
        confs = Counter(m.get("conf") for m in metas)
        adx_ok = sum(1 for m in metas if m.get("adx5m") is not None)
        print(f"\nbaseline entry-time coverage: {len(metas)}/{len(base_trades)} entries have meta")
        print(f"  lt_bias present: {len(with_lt)}/{len(metas)}")
        if ages:
            med = ages[len(ages) // 2]
            p90 = ages[min(int(len(ages) * 0.9), len(ages) - 1)]
            print(f"  flow snapshot age at entry: median {med}s | p90 {p90}s | max {ages[-1]}s")
        print(f"  adx5m present: {adx_ok}/{len(metas)}")
        print(f"  conf distribution: {dict(sorted(confs.items(), key=lambda x: str(x[0])))}")
        out["baseline_coverage"] = {
            "entries_with_meta": len(metas), "lt_bias_present": len(with_lt),
            "age_median_s": ages[len(ages) // 2] if ages else None,
            "age_max_s": ages[-1] if ages else None,
            "conf_dist": {str(k): v for k, v in confs.items()},
        }

    os.makedirs("logs", exist_ok=True)
    with open("logs/cohort_gate_sweep.json", "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print("\ndumped: logs/cohort_gate_sweep.json")


if __name__ == "__main__":
    main()
