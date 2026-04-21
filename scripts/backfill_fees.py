#!/usr/bin/env python3
"""Backfill real Phemex fees/funding into trading_state.json closed_trades.

Source of truth: Phemex CSV export (TAXATION_FUND_*.csv).
Match by closed_at timestamp (within 90s) AND pnl_usdt (within $0.05).
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

CSV_PATH = "/Users/jonaspenaso/Downloads/TAXATION_FUND_2026-04-08.csv"
STATE_PATH = "/Users/jonaspenaso/Desktop/Phmex-S/trading_state.json"

TIME_TOL_S = 90
PNL_TOL = 0.05
SKEW_TIME_TOL_S = 30 * 60  # allow 30-min skew fallback for same-pnl single match


def parse_csv(path):
    """Returns list of dicts: {remark, ts (unix), gross, fee, funding}."""
    groups = defaultdict(dict)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            remark = row["Remark"]
            op = row["Operation"]
            change = float(row["Change"])
            t = datetime.strptime(row["Time (UTC)"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            g = groups[remark]
            g["remark"] = remark
            g["ts"] = t.timestamp()
            if op == "Closed PNL":
                g["gross"] = change
            elif op == "Trade Fee":
                g["fee"] = change  # negative
            elif op == "Funding Fee":
                g["funding"] = change
    trades = list(groups.values())
    # Sanity: every trade should have all 3
    for t in trades:
        for k in ("gross", "fee", "funding"):
            t.setdefault(k, 0.0)
    return trades


def main():
    phemex = parse_csv(CSV_PATH)
    print(f"Phemex trades parsed: {len(phemex)}")

    with open(STATE_PATH) as f:
        state = json.load(f)
    closed = state.get("closed_trades", [])
    print(f"Internal closed_trades: {len(closed)}")

    # CSV time window
    pmin = min(t["ts"] for t in phemex)
    pmax = max(t["ts"] for t in phemex)
    print(f"CSV window UTC: {datetime.fromtimestamp(pmin, tz=timezone.utc)} -> {datetime.fromtimestamp(pmax, tz=timezone.utc)}")

    used_phemex = set()
    matched = 0
    matched_trades = []
    unmatched_internal_in_window = []

    # Pass 1: strict (time + pnl)
    for ct in closed:
        ca = ct.get("closed_at")
        if ca is None:
            continue
        pnl = ct.get("pnl_usdt", 0.0)
        best = None
        best_dt = None
        for i, p in enumerate(phemex):
            if i in used_phemex:
                continue
            dt = abs(p["ts"] - ca)
            if dt <= TIME_TOL_S and abs(p["gross"] - pnl) <= PNL_TOL:
                if best is None or dt < best_dt:
                    best = i
                    best_dt = dt
        if best is not None:
            used_phemex.add(best)
            p = phemex[best]
            fee_abs = abs(p["fee"])
            funding = p["funding"]
            ct["fees_usdt"] = fee_abs
            ct["funding_usdt"] = funding
            ct["net_pnl"] = p["gross"] - fee_abs + funding
            matched += 1
            matched_trades.append(ct)

    # Pass 2: pnl-only fallback for any internal trade in CSV window with no match
    for ct in closed:
        if "net_pnl" in ct and ct.get("net_pnl") is not None:
            continue
        ca = ct.get("closed_at")
        if ca is None:
            continue
        if ca < pmin - SKEW_TIME_TOL_S or ca > pmax + SKEW_TIME_TOL_S:
            continue
        pnl = ct.get("pnl_usdt", 0.0)
        candidates = [
            i for i, p in enumerate(phemex)
            if i not in used_phemex and abs(p["gross"] - pnl) <= PNL_TOL
            and abs(p["ts"] - ca) <= SKEW_TIME_TOL_S
        ]
        if len(candidates) == 1:
            i = candidates[0]
            used_phemex.add(i)
            p = phemex[i]
            fee_abs = abs(p["fee"])
            funding = p["funding"]
            ct["fees_usdt"] = fee_abs
            ct["funding_usdt"] = funding
            ct["net_pnl"] = p["gross"] - fee_abs + funding
            ct["_fee_match"] = "skew_fallback"
            matched += 1
            matched_trades.append(ct)

    # Report unmatched
    for ct in closed:
        ca = ct.get("closed_at")
        if ca is None:
            continue
        if pmin - 5 <= ca <= pmax + 5 and ct.get("net_pnl") is None:
            unmatched_internal_in_window.append(ct)

    unmatched_phemex = [p for i, p in enumerate(phemex) if i not in used_phemex]

    print(f"\nMatched: {matched} / {len(phemex)} Phemex trades")
    print(f"Unmatched Phemex rows: {len(unmatched_phemex)}")
    for p in unmatched_phemex:
        print(f"  Phemex {p['remark']} {datetime.fromtimestamp(p['ts'], tz=timezone.utc)} gross={p['gross']:.4f}")
    print(f"Unmatched internal trades in CSV window: {len(unmatched_internal_in_window)}")
    for ct in unmatched_internal_in_window:
        print(f"  Internal {ct.get('symbol')} closed_at={datetime.fromtimestamp(ct['closed_at'], tz=timezone.utc)} pnl={ct.get('pnl_usdt'):.4f}")

    # Verify totals
    sum_net = sum(ct["net_pnl"] for ct in matched_trades)
    sum_gross_phemex = sum(p["gross"] for i, p in enumerate(phemex) if i in used_phemex)
    sum_fee_phemex = sum(p["fee"] for i, p in enumerate(phemex) if i in used_phemex)  # negative
    sum_fund_phemex = sum(p["funding"] for i, p in enumerate(phemex) if i in used_phemex)
    phemex_net = sum_gross_phemex + sum_fee_phemex + sum_fund_phemex
    print(f"\nSum internal net_pnl (matched): {sum_net:.4f}")
    print(f"Sum Phemex net (matched): {phemex_net:.4f}")
    print(f"Diff: {sum_net - phemex_net:.6f}")

    # Atomic write
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)
    print(f"\nWrote {STATE_PATH}")


if __name__ == "__main__":
    main()
