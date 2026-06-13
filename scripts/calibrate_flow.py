#!/usr/bin/env python3
"""Flow-replay calibration: run the backtester with replayed flow across ALL
symbols that traded live during the sprint window, and compare the aggregate
(count / net PnL / WR) against the live htf_l2_anticipation trades.

Multi-symbol counterpart to calibrate_compare.py. Run from repo root:
    python scripts/calibrate_flow.py [--ae-threshold -999.0] [--ae-cycles 10] [--fee-rt 0.22]

2026-06-11: exit-model recalibration —
  - AE default now -999.0 (LIVE PARITY: adverse exit was DISABLED live for the
    whole 5/11-5/30 window; the 5/30 run wrongly passed -3.0).
  - Live window is now bounded ABOVE by the last 5m candle in backtest_data_may,
    so re-runs after 5/30 still compare the same 53-trade live set.
  - Live baseline split into EXECUTED trades vs zero-PnL min_margin_skip ghosts
    (8 of the 53 "trades" are $0 partial-fill skips the sim can never produce).
  - Per-exit-reason live-vs-sim table added.
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

import backtest
from backtest import run_backtest
from flow_replay import FlowIndex


def load_candles(path):
    """Load a backtest_data CSV into a UTC-indexed OHLCV frame.
    run_backtest() applies add_all_indicators() itself, so return raw."""
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df

DATA_DIR = "backtest_data_may"
STRATEGY = "htf_l2_anticipation"
SYMBOLS = [
    "ETH/USDT:USDT", "INJ/USDT:USDT", "TON/USDT:USDT", "ONDO/USDT:USDT",
    "WLD/USDT:USDT", "DOGE/USDT:USDT", "XLM/USDT:USDT", "ENA/USDT:USDT",
    "ARB/USDT:USDT", "XRP/USDT:USDT", "BTC/USDT:USDT", "RENDER/USDT:USDT",
    "TAO/USDT:USDT", "CFX/USDT:USDT", "ZEC/USDT:USDT", "BCH/USDT:USDT",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ae-threshold", type=float, default=-999.0,
                    help="Adverse-exit ROI threshold. LIVE PARITY for 5/11-5/30 window "
                         "is -999.0 (disabled since 2026-05-07).")
    ap.add_argument("--ae-cycles", type=int, default=10)
    ap.add_argument("--fee-rt", type=float, default=0.22,
                    help="Round-trip fee+slippage %% of notional (risk_manager paper model).")
    # Exit-rule A/B knobs (2026-06-12 Phase 1) — mirror backtest.py's CLI.
    # Defaults None = live-parity module constants in backtest.py.
    ap.add_argument("--sl-floor-pct", type=float, default=None)
    ap.add_argument("--tp-cap-pct", type=float, default=None)
    ap.add_argument("--early-exit-min-roi", type=float, default=None)
    ap.add_argument("--trail-arm-roi", type=float, default=None)
    ap.add_argument("--trail-tier1-lock", type=float, default=None)
    ap.add_argument("--sl-ratchet", type=str, default=None)
    ap.add_argument("--deep-red-roi", type=float, default=None)
    ap.add_argument("--deep-red-cycles", type=float, default=None)
    args = ap.parse_args()
    backtest.apply_exit_overrides(args)
    knobs = {k: v for k, v in vars(args).items()
             if v is not None and k not in ("ae_threshold", "ae_cycles", "fee_rt")}
    if knobs:
        print(f"exit knobs: {knobs}")

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

    # Upper bound of the calibration window = end of the May candle archive.
    # (flow_capture.jsonl keeps growing live; without this bound, re-runs after
    # 5/30 would silently pull post-window live trades into the baseline.)
    data_end = max(int(df.index[-1].timestamp()) for df in pair_data.values()) + 300

    idx = FlowIndex()
    lo, hi = idx.coverage_window()
    f = lambda t: datetime.fromtimestamp(t, tz=timezone.utc).isoformat() if t else "n/a"
    print(f"flow: {idx.row_count} rows / {idx.symbol_count} symbols / {f(lo)} -> {f(hi)}")
    print(f"calibration window: {f(lo)} -> {f(data_end)} (candle archive end)")
    print(f"adverse exit: threshold={args.ae_threshold} cycles={args.ae_cycles} | fee RT: {args.fee_rt}%")

    sim = run_backtest(
        pair_data,
        htf_data=htf_data,
        flow_index=idx,
        flow_replay=True,
        ae_threshold=args.ae_threshold,
        ae_cycles=args.ae_cycles,
        fee_rt_pct=args.fee_rt,
    )

    with open("trading_state.json") as fh:
        state = json.load(fh)
    live_all = [
        t for t in state.get("closed_trades", [])
        if t.get("strategy") == STRATEGY and lo <= t.get("opened_at", 0) <= data_end
    ]
    live = [t for t in live_all if t.get("exit_reason") != "min_margin_skip"]
    skips = len(live_all) - len(live)

    def live_pnl(t):
        return t.get("net_pnl", t.get("pnl_usdt", 0))

    sim_n, live_n = len(sim), len(live)
    sim_pnl = sum(t.pnl_usd for t in sim)
    lv_pnl = sum(live_pnl(t) for t in live)
    sim_wr = sum(1 for t in sim if t.pnl_usd > 0) / max(sim_n, 1) * 100
    lv_wr = sum(1 for t in live if live_pnl(t) > 0) / max(live_n, 1) * 100

    count_delta = (sim_n - live_n) / max(live_n, 1) * 100
    pnl_delta = (sim_pnl - lv_pnl) / abs(lv_pnl) * 100 if lv_pnl else 0

    print("\n=== FLOW-REPLAY CALIBRATION (aggregate, all symbols) ===")
    print(f"  Strategy: {STRATEGY}")
    print(f"  Window:   {f(lo)} -> {f(data_end)}")
    print(f"  Live records in window: {len(live_all)} ({live_n} executed + {skips} zero-PnL min_margin_skip)")
    print("  ---")
    print(f"  Live (executed): {live_n:>3} trades | ${lv_pnl:+7.2f} net | {lv_wr:4.1f}% WR")
    print(f"  Sim:             {sim_n:>3} trades | ${sim_pnl:+7.2f} net | {sim_wr:4.1f}% WR")
    print("  ---")
    print(f"  Count delta: {count_delta:+6.1f}%  (target +/-30%)  {'PASS' if abs(count_delta)<=30 else 'FAIL'}")
    print(f"  PnL delta:   {pnl_delta:+6.1f}%  (target +/-15%)  {'PASS' if abs(pnl_delta)<=15 else 'FAIL'}")
    cal = abs(count_delta) <= 30 and abs(pnl_delta) <= 15
    print(f"  CALIBRATION: {'PASS' if cal else 'FAIL'}")

    # Per-exit-reason comparison (live exchange_close == resting SL/TP fills
    # detected between 60s cycles; sim tags intra-bar resting fills the same way)
    lv_r = defaultdict(lambda: [0, 0.0, 0])
    for t in live:
        r = t.get("exit_reason") or t.get("reason") or "?"
        lv_r[r][0] += 1
        lv_r[r][1] += live_pnl(t)
        lv_r[r][2] += 1 if live_pnl(t) > 0 else 0
    sm_r = defaultdict(lambda: [0, 0.0, 0])
    for t in sim:
        sm_r[t.exit_reason][0] += 1
        sm_r[t.exit_reason][1] += t.pnl_usd
        sm_r[t.exit_reason][2] += 1 if t.pnl_usd > 0 else 0
    print("\n  per-exit-reason (live n/pnl/wins | sim n/pnl/wins):")
    for r in sorted(set(lv_r) | set(sm_r)):
        ln, lp, lw = lv_r.get(r, [0, 0.0, 0])
        sn, sp, sw = sm_r.get(r, [0, 0.0, 0])
        print(f"    {r:<20} live {ln:>3} ${lp:+7.2f} w{lw:<3} | sim {sn:>3} ${sp:+7.2f} w{sw}")

    # Dump sim trades for forensics (ZEC overfire investigation etc.)
    dump = [{
        "pair": t.pair, "dir": t.direction, "entry": t.entry_price, "exit": t.exit_price,
        "entry_time": str(t.entry_time), "exit_time": str(t.exit_time),
        "pnl": round(t.pnl_usd, 4), "roi": round(t.roi_pct, 2), "reason": t.exit_reason,
    } for t in sim]
    with open("logs/calibrate_flow_trades.json", "w") as fh:
        json.dump(dump, fh, indent=1)
    print(f"\n  sim trades dumped: logs/calibrate_flow_trades.json ({len(dump)})")

    sim_by = Counter(t.pair for t in sim)
    live_by = Counter(t["symbol"] for t in live)
    print("\n  per-symbol trade counts (live | sim):")
    for sym in SYMBOLS:
        print(f"    {sym:<18} {live_by.get(sym,0):>3} | {sim_by.get(sym,0):>3}")


if __name__ == "__main__":
    main()
