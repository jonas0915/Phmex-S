#!/usr/bin/env python3
"""Exit-model isolation test (2026-06-11).

Replays backtest.py's live-fidelity exit engine (check_exits_live) on the
ACTUAL live entries from the 5/11-5/30 window — exact entry price, time, side,
amount, margin from trading_state.json — and compares the simulated exits
against what live actually did. This isolates EXIT fidelity from the entry-side
composition error (snapshot-staleness) that dominates the full-sim comparison.

Per trade: SL/TP = entry +/- 1.2%/1.6% (live risk_manager.py:504-512 collapses
to these for every trade in the window — verified -13%/+16% ROI clustering).

Gross PnL compares sim exit price vs live exit price directly (live pnl_usdt is
gross). Net adds each trade's ACTUAL live fee to the sim gross, so the fee
model is held constant and only exit-price fidelity is measured.

Run from repo root:
    python scripts/calibrate_exits.py
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import BTPosition, check_exits_live, LEVERAGE
from flow_replay import FlowIndex
from indicators import add_all_indicators

DATA_DIR = "backtest_data_may"
STRATEGY = "htf_l2_anticipation"
LO = 1778470812  # flow capture start
END = int(datetime(2026, 5, 30, 22, 10, tzinfo=timezone.utc).timestamp())

SL_PCT, TP_PCT = 1.2, 1.6  # live-window effective SL/TP (risk_manager.py:504-512)


def load_candles(path):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    return df[~df.index.duplicated(keep="last")]


def main():
    state = json.load(open("trading_state.json"))
    live = [
        t for t in state["closed_trades"]
        if t.get("strategy") == STRATEGY and LO <= t.get("opened_at", 0) <= END
        and t.get("exit_reason") != "min_margin_skip"
    ]
    print(f"live executed trades in window: {len(live)}")

    fidx = FlowIndex()
    dfs, htfs = {}, {}
    rows = []
    stats = {}
    for t in live:
        sym = t["symbol"]
        safe = sym.replace("/", "_").replace(":", "_")
        if sym not in dfs:
            p5 = os.path.join(DATA_DIR, f"{safe}_5m.csv")
            p1 = os.path.join(DATA_DIR, f"{safe}_1h.csv")
            if not os.path.exists(p5):
                print(f"  [skip] no candle data for {sym}")
                continue
            dfs[sym] = add_all_indicators(load_candles(p5))
            htfs[sym] = add_all_indicators(load_candles(p1)) if os.path.exists(p1) else None
        df = dfs[sym]
        entry_px = t.get("entry_price") or t.get("entry")
        side = t["side"]
        opened = t["opened_at"]
        margin = t["margin"]
        amount = t["amount"]
        notional = entry_px * amount  # live notional (margin * ~10x)

        sl = entry_px * (1 - SL_PCT / 100) if side == "long" else entry_px * (1 + SL_PCT / 100)
        tp = entry_px * (1 + TP_PCT / 100) if side == "long" else entry_px * (1 - TP_PCT / 100)
        entry_ts = pd.Timestamp(opened, unit="s", tz="UTC")
        e_idx = df.index.searchsorted(entry_ts, side="right") - 1
        if e_idx < 1:
            print(f"  [skip] {sym} entry before candle data")
            continue

        pos = BTPosition(
            pair=sym, direction=side, entry_price=entry_px, entry_candle=e_idx,
            size_usd=notional, margin=margin, sl_price=sl, tp_price=tp,
            strategy=STRATEGY, peak_price=entry_px, entry_epoch=opened,
        )
        bar_s = 300
        result = None
        for idx in range(e_idx + 1, len(df)):
            candle = df.iloc[idx]
            bar_open_ts = int(df.index[idx].timestamp())
            bar_close_ts = bar_open_ts + bar_s
            points = fidx.prices_between(sym, bar_open_ts, bar_close_ts)
            htf_w = None
            h = htfs.get(sym)
            if h is not None:
                h_idx = h.index.searchsorted(df.index[idx], side="right") - 1
                if h_idx >= 1:
                    htf_w = h.iloc[max(0, h_idx - 2):h_idx + 1]
            result = check_exits_live(pos, candle, idx, df, htf_w, points, bar_close_ts,
                                      ae_threshold=-999.0, ae_cycles=10, stats=stats)
            if result:
                break
        if result is None:
            sim_exit, sim_reason = float(df.iloc[-1]["close"]), "end_of_data"
        else:
            sim_exit, sim_reason = result

        sim_gross = (sim_exit - entry_px) * amount if side == "long" else (entry_px - sim_exit) * amount
        live_gross = t.get("pnl_usdt", 0.0)
        live_fee = t.get("fees_usdt", 0.0)
        rows.append({
            "sym": sym.split("/")[0], "side": side,
            "sim_reason": sim_reason, "live_reason": t.get("exit_reason"),
            "sim_gross": sim_gross, "live_gross": live_gross,
            "sim_net": sim_gross - live_fee, "live_net": t.get("net_pnl", live_gross - live_fee),
        })

    n = len(rows)
    sg = sum(r["sim_gross"] for r in rows)
    lg = sum(r["live_gross"] for r in rows)
    sn_ = sum(r["sim_net"] for r in rows)
    ln_ = sum(r["live_net"] for r in rows)
    match = sum(1 for r in rows if r["sim_reason"] == r["live_reason"])
    print(f"\n=== EXIT-MODEL ISOLATION ({n} live entries replayed) ===")
    print(f"  gross PnL: live ${lg:+.2f} | sim ${sg:+.2f} | delta {((sg-lg)/abs(lg)*100) if lg else 0:+.1f}%")
    print(f"  net PnL  : live ${ln_:+.2f} | sim ${sn_:+.2f} | delta {((sn_-ln_)/abs(ln_)*100) if ln_ else 0:+.1f}%")
    print(f"  exact exit-reason match: {match}/{n}")
    cm = defaultdict(int)
    for r in rows:
        cm[(r["live_reason"], r["sim_reason"])] += 1
    print("\n  live_reason -> sim_reason (count):")
    for (lr, sr), c in sorted(cm.items(), key=lambda x: -x[1]):
        print(f"    {lr:<20} -> {sr:<20} {c}")
    agg = defaultdict(lambda: [0, 0.0, 0, 0.0])
    for r in rows:
        agg[r["live_reason"]][0] += 1
        agg[r["live_reason"]][1] += r["live_net"]
        agg[r["sim_reason"]][2] += 1
        agg[r["sim_reason"]][3] += r["sim_net"]
    print("\n  per-reason (live n/net | sim n/net):")
    for k in sorted(agg):
        a = agg[k]
        print(f"    {k:<20} live {a[0]:>3} ${a[1]:+7.2f} | sim {a[2]:>3} ${a[3]:+7.2f}")
    fb, fl = stats.get("fallback_bars", 0), stats.get("flow_bars", 0)
    print(f"\n  intra-bar price source: {fl} bars flow path, {fb} bars bar-close fallback "
          f"({fb/(fb+fl)*100 if fb+fl else 0:.1f}% fallback)")


if __name__ == "__main__":
    main()
