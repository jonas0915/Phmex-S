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

Exit-rule A/B knobs (2026-06-12 Phase 1) mirror backtest.py's CLI; defaults are
live parity, so a no-flag run reproduces the documented baseline (sim net -$9.31,
-24.6% vs live net). AE stays hardcoded at -999/10 (live parity for the window).
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backtest
from backtest import BTPosition, check_exits_live, LEVERAGE
from flow_replay import FlowIndex
from indicators import add_all_indicators

DATA_DIR = "backtest_data_may"
STRATEGY = "htf_l2_anticipation"
LO = 1778470812  # flow capture start
END = int(datetime(2026, 5, 30, 22, 10, tzinfo=timezone.utc).timestamp())
MID = (LO + END) // 2  # half-split boundary for the period-stability check

SL_PCT, TP_PCT = 1.2, 1.6  # live-window effective SL/TP (risk_manager.py:504-512)


def parse_cli():
    ap = argparse.ArgumentParser(description="Exit-model isolation rig (45 live entries)")
    ap.add_argument("--sl-floor-pct", type=float, default=None,
                    help="SL distance %% of entry (live 1.2). Also applied to the rig's per-trade SL.")
    ap.add_argument("--tp-cap-pct", type=float, default=None,
                    help="TP distance %% of entry (live 1.6).")
    ap.add_argument("--early-exit-min-roi", type=float, default=None,
                    help="Min ROI %% for early_exit (live 3.0).")
    ap.add_argument("--trail-arm-roi", type=float, default=None,
                    help="Trail arm ROI %% (live 5.0).")
    ap.add_argument("--trail-tier1-lock", type=float, default=None,
                    help="Tier-1 lock-in %% (live 2.0; -999 removes the lock floor).")
    ap.add_argument("--sl-ratchet", type=str, default=None,
                    help='Time-ratchet resting SL, e.g. "60:0.8,120:0.6". Off by default.')
    ap.add_argument("--deep-red-roi", type=float, default=None,
                    help="Deep-red cut ROI %% (off by default; A/B 3: -6.0).")
    ap.add_argument("--deep-red-cycles", type=float, default=None,
                    help="Cycles before deep-red cut can fire (default 120).")
    ap.add_argument("--partial-tp-roi", type=float, default=None,
                    help="Bank half at this margin-ROI %% (live 10.0; bot.py:859). "
                         "Off by default — baseline rig behavior preserved exactly.")
    ap.add_argument("--runner-tp-roi", type=float, default=None,
                    help="Runner-half TP margin-ROI %% after scale-out (live 25.0; "
                         "risk_manager.py:823). Software-enforced, stale exchange TP cancelled.")
    ap.add_argument("--partial-tp-fraction", type=float, default=None,
                    help="Fraction banked at the first threshold (live 0.5 = half; "
                         "round-2 arXiv variant 0.75). Default None keeps 0.5.")
    ap.add_argument("--dump-json", type=str, default=None,
                    help="Write per-trade rows to PATH (for variant-vs-baseline diffing).")
    ap.add_argument("--window-start", type=str, default=None,
                    help="Entry-window start, YYYY-MM-DD (UTC) or epoch secs. "
                         "Default: the documented 5/11-5/30 rig window.")
    ap.add_argument("--window-end", type=str, default=None,
                    help="Entry-window end, YYYY-MM-DD (UTC) or epoch secs.")
    ap.add_argument("--data-dir", type=str, default=None,
                    help=f"Candle CSV dir (default {DATA_DIR}).")
    return ap.parse_args()


def _parse_when(s: str) -> int:
    if s.isdigit():
        return int(s)
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def load_candles(path):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    return df[~df.index.duplicated(keep="last")]


def main():
    args = parse_cli()
    backtest.apply_exit_overrides(args)  # sets module knobs used by check_exits_live
    sl_pct = args.sl_floor_pct if args.sl_floor_pct is not None else SL_PCT
    tp_pct = args.tp_cap_pct if args.tp_cap_pct is not None else TP_PCT
    lo = _parse_when(args.window_start) if args.window_start else LO
    end = _parse_when(args.window_end) if args.window_end else END
    mid = (lo + end) // 2
    data_dir = args.data_dir or DATA_DIR
    knobs = {k: v for k, v in vars(args).items() if v is not None and k != "dump_json"}
    print(f"knobs: {knobs if knobs else 'BASELINE (live parity)'}")

    state = json.load(open("trading_state.json"))
    live = [
        t for t in state["closed_trades"]
        if t.get("strategy") == STRATEGY and lo <= t.get("opened_at", 0) <= end
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
            p5 = os.path.join(data_dir, f"{safe}_5m.csv")
            p1 = os.path.join(data_dir, f"{safe}_1h.csv")
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

        sl = entry_px * (1 - sl_pct / 100) if side == "long" else entry_px * (1 + sl_pct / 100)
        tp = entry_px * (1 + tp_pct / 100) if side == "long" else entry_px * (1 - tp_pct / 100)
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

        if pos.scaled_out and pos.partial_exit_price is not None:
            # Partial-TP knob fired: `frac` of the size banked at partial_exit_price,
            # the runner remainder exits at sim_exit. PnL is linear in size, so live
            # positions that were themselves scaled out (two half-size rows sharing
            # one entry) aggregate exactly like one full position.
            frac = pos.partial_exit_fraction
            banked = amount * frac
            runner = amount * (1 - frac)
            if side == "long":
                sim_gross = ((pos.partial_exit_price - entry_px) * banked
                             + (sim_exit - entry_px) * runner)
            else:
                sim_gross = ((entry_px - pos.partial_exit_price) * banked
                             + (entry_px - sim_exit) * runner)
        else:
            sim_gross = (sim_exit - entry_px) * amount if side == "long" else (entry_px - sim_exit) * amount
        live_gross = t.get("pnl_usdt", 0.0)
        live_fee = t.get("fees_usdt", 0.0)
        rows.append({
            "sym": sym.split("/")[0], "side": side, "opened_at": opened,
            "sim_reason": sim_reason, "live_reason": t.get("exit_reason"),
            "sim_gross": sim_gross, "live_gross": live_gross,
            "sim_net": sim_gross - live_fee, "live_net": t.get("net_pnl", live_gross - live_fee),
            "sim_scaled_out": bool(pos.scaled_out),
            "sim_partial_px": pos.partial_exit_price,
            "sim_partial_frac": pos.partial_exit_fraction if pos.scaled_out else None,
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

    # --- A/B summary stats (sim side, net of live fees) ---
    wins = [r["sim_net"] for r in rows if r["sim_net"] > 0]
    losses = [r["sim_net"] for r in rows if r["sim_net"] <= 0]
    print(f"\n  sim WR: {len(wins)}/{n} ({len(wins)/n*100 if n else 0:.1f}%) | "
          f"avg win ${sum(wins)/len(wins) if wins else 0:+.3f} | "
          f"avg loss ${sum(losses)/len(losses) if losses else 0:+.3f}")
    for label, half in [("first half", [r for r in rows if r["opened_at"] < mid]),
                        ("second half", [r for r in rows if r["opened_at"] >= mid])]:
        hs = sum(r["sim_net"] for r in half)
        hl = sum(r["live_net"] for r in half)
        hw = sum(1 for r in half if r["sim_net"] > 0)
        print(f"  {label:<11}: n={len(half):>2} sim net ${hs:+.2f} (live ${hl:+.2f}) "
              f"sim WR {hw/len(half)*100 if half else 0:.0f}%")

    if args.dump_json:
        with open(args.dump_json, "w") as fh:
            json.dump({"knobs": knobs, "rows": rows,
                       "totals": {"n": n, "sim_gross": sg, "sim_net": sn_,
                                  "live_gross": lg, "live_net": ln_}}, fh, indent=1)
        print(f"\n  per-trade dump: {args.dump_json}")


if __name__ == "__main__":
    main()
