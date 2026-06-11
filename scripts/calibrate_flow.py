#!/usr/bin/env python3
"""Flow-replay calibration: run the backtester with replayed flow across ALL
symbols that traded live during the sprint window, and compare the aggregate
(count / net PnL / WR) against the live htf_l2_anticipation trades.

Multi-symbol counterpart to calibrate_compare.py. Run from repo root:
    python scripts/calibrate_flow.py
"""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    f = lambda t: datetime.fromtimestamp(t, tz=timezone.utc).isoformat() if t else "n/a"
    print(f"flow: {idx.row_count} rows / {idx.symbol_count} symbols / {f(lo)} -> {f(hi)}")

    sim = run_backtest(
        pair_data,
        htf_data=htf_data,
        flow_index=idx,
        flow_replay=True,
        ae_threshold=-3.0,
        ae_cycles=10,
    )

    with open("trading_state.json") as fh:
        state = json.load(fh)
    live = [
        t for t in state.get("closed_trades", [])
        if t.get("strategy") == STRATEGY and t.get("opened_at", 0) >= lo
    ]

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
    print(f"  Window:   {f(lo)} -> {f(hi)}")
    print("  ---")
    print(f"  Live: {live_n:>3} trades | ${lv_pnl:+7.2f} net | {lv_wr:4.1f}% WR")
    print(f"  Sim:  {sim_n:>3} trades | ${sim_pnl:+7.2f} net | {sim_wr:4.1f}% WR")
    print("  ---")
    print(f"  Count delta: {count_delta:+6.1f}%  (target +/-30%)  {'PASS' if abs(count_delta)<=30 else 'FAIL'}")
    print(f"  PnL delta:   {pnl_delta:+6.1f}%  (target +/-15%)  {'PASS' if abs(pnl_delta)<=15 else 'FAIL'}")
    cal = abs(count_delta) <= 30 and abs(pnl_delta) <= 15
    print(f"  CALIBRATION: {'PASS' if cal else 'FAIL'}")

    sim_by = Counter(t.pair for t in sim)
    live_by = Counter(t["symbol"] for t in live)
    print("\n  per-symbol trade counts (live | sim):")
    for sym in SYMBOLS:
        print(f"    {sym:<18} {live_by.get(sym,0):>3} | {sim_by.get(sym,0):>3}")


if __name__ == "__main__":
    main()
