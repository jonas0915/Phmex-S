#!/usr/bin/env python3
"""Trend-day fuse replay for 5m_mean_revert (read-only).

Frozen rule (pre-stated, no tuning): after N full-stop losses
(exit_reason in {stop_loss, exchange_close} AND net < 0) on the SAME side
within the same PT day (day of the stop's CLOSE), the slot stands down on
that side until the next PT midnight. A trade is PREVENTED if its ENTRY
(opened_at, PT) falls inside an active same-side fuse window.
Primary variant N=2; N=1 and N=3 reported as sensitivity only.

Pure subtraction replay: prevented trades' actual net PnL is summed.
Negative sum => fuse saves money; positive sum => fuse costs money.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
STATE = "/Users/jonaspenaso/Desktop/Phmex-S/trading_state_5m_mean_revert.json"
FULL_STOP_REASONS = {"stop_loss", "exchange_close"}


def pt(ts):
    return datetime.fromtimestamp(ts, tz=PT)


def fmt(ts):
    return pt(ts).strftime("%Y-%m-%d %I:%M:%S %p PT")


def net_of(t):
    # net_pnl is fee-inclusive where present; fall back to pnl_usdt (gross)
    if "net_pnl" in t:
        return t["net_pnl"], "net_pnl"
    return t["pnl_usdt"], "pnl_usdt(gross,no fee fields)"


def replay(trades, n_stops, verbose=False):
    """Walk chronologically by event time. Stops counted at CLOSE time;
    entries checked at OPEN time against fuse state live at that moment."""
    # Build event list: each trade contributes an entry event and a close event.
    events = []
    for t in trades:
        events.append((t["opened_at"], 0, "entry", t))   # entry before close at same ts
        events.append((t["closed_at"], 1, "close", t))
    events.sort(key=lambda e: (e[0], e[1]))

    # fuse state: side -> expiry datetime (next PT midnight) or None
    fuse_until = {"long": None, "short": None}
    # per (PT date, side) stop counter
    day_stops = {}
    prevented, trips = [], []

    for ts, _, kind, t in events:
        now = pt(ts)
        side = t["side"]
        if kind == "entry":
            exp = fuse_until.get(side)
            if exp is not None and now < exp:
                prevented.append(t)
        else:  # close
            net, _src = net_of(t)
            if t.get("exit_reason") in FULL_STOP_REASONS and net < 0:
                key = (now.date(), side)
                day_stops[key] = day_stops.get(key, 0) + 1
                if day_stops[key] == n_stops:
                    midnight = (now + timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0)
                    fuse_until[side] = midnight
                    trips.append((t, now, midnight))

    # NOTE: prevented trades would themselves not close/stop, so strictly the
    # replay should drop them from later stop counting. Since a prevented trade
    # never contributes a stop that ARMS an earlier fuse (causality), the only
    # effect is possible over-arming later the same day; with this ledger's
    # density that is checked manually in the report. Second pass to be exact:
    if prevented:
        kept = [t for t in trades if t not in prevented]
        # recompute with prevented trades removed until fixpoint
        p2, tr2 = replay(kept, n_stops)
        # merge: trades prevented in pass1 stay prevented; add any new (rare)
        seen = {id(x) for x in prevented}
        for x in p2:
            if id(x) not in seen:
                prevented.append(x)
        trips = tr2 if tr2 else trips
    return prevented, trips


def summarize(label, trades):
    print(f"\n{'='*70}\n{label}: {len(trades)} closed trades")
    tot = sum(net_of(t)[0] for t in trades)
    stops = [t for t in trades
             if t.get("exit_reason") in FULL_STOP_REASONS and net_of(t)[0] < 0]
    print(f"  total net {tot:+.4f} | full-stop losses: {len(stops)}")
    for t in stops:
        print(f"    STOP {fmt(t['closed_at'])} {t['symbol']:<18} {t['side']:<5} "
              f"{t['exit_reason']:<14} net {net_of(t)[0]:+.4f}")
    for n in (1, 2, 3):
        prevented, trips = replay(trades, n)
        saving = sum(net_of(t)[0] for t in prevented)
        tag = " <== PRIMARY" if n == 2 else " (sensitivity)"
        print(f"  [{n}-stop fuse]{tag} trips={len(trips)} "
              f"prevented={len(prevented)} sum(prevented net)={saving:+.4f} "
              f"=> {'fuse SAVES' if saving < 0 else ('fuse COSTS' if saving > 0 else 'NO EFFECT')}")
        for t, when, until in trips:
            print(f"      TRIP at {fmt(t['closed_at'])} side={t['side']} "
                  f"(stand down {t['side']} until {until.strftime('%m/%d %I:%M %p PT')})")
        for t in prevented:
            print(f"      PREVENTED entry {fmt(t['opened_at'])} {t['symbol']} "
                  f"{t['side']} actual net {net_of(t)[0]:+.4f} ({t.get('exit_reason')})")


def main():
    d = json.load(open(STATE))
    ct = d["closed_trades"]
    ct.sort(key=lambda t: t["opened_at"])
    live = [t for t in ct if t.get("mode") == "live"]
    pre = [t for t in ct if t.get("mode") != "live"]
    summarize("LIVE ERA (mode=live, closes 6/18 onward; slot promoted 6/12)", live)
    summarize("PRE-PROMOTION ERA (no mode field, closes 3/28-6/11) [labeled separately]", pre)
    summarize("FULL LEDGER (both eras walked as one sequence)", ct)

    # Per-day sequences for any PT day containing >=1 full stop (mechanism inspection)
    print(f"\n{'='*70}\nPer-day sequences for days with >=1 full-stop loss (full ledger):")
    from collections import defaultdict
    by_day = defaultdict(list)
    for t in ct:
        by_day[pt(t["closed_at"]).date()].append(t)
    stop_days = sorted(day for day, ts in by_day.items()
                       if any(t.get("exit_reason") in FULL_STOP_REASONS
                              and net_of(t)[0] < 0 for t in ts))
    for day in stop_days:
        print(f"  {day}:")
        for t in sorted(by_day[day], key=lambda x: x["closed_at"]):
            mark = "*STOP*" if (t.get("exit_reason") in FULL_STOP_REASONS
                                and net_of(t)[0] < 0) else "      "
            print(f"    {mark} open {fmt(t['opened_at'])} -> close {fmt(t['closed_at'])} "
                  f"{t['symbol']:<18} {t['side']:<5} {t.get('exit_reason'):<14} "
                  f"net {net_of(t)[0]:+.4f} mode={t.get('mode','pre')}")


if __name__ == "__main__":
    main()
