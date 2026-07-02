#!/usr/bin/env python3
"""5m_mean_revert bounded maker RE-QUOTE counterfactual.

Companion to scripts/slot_lab/missed_fill_counterfactual.py (same 11 PostOnly
misses, same exit engine). That script assumed the miss filled at the INTENDED
limit price. This one asks: if instead we re-quote at the new touch 60-120s
later, (a) how many bps worse is the entry, and (b) does the trade still win?

For each miss:
  * drift at +60s / +120s / +300s after the [MAKER] Limit placement time,
    expressed in bps ADVERSE for entry (long: how far ABOVE intended; short:
    how far BELOW intended; positive = worse fill for us).
  * PRICE-AT-+Ns CONVENTION (1m granularity — stated, not hidden): the CLOSE of
    the 1m bar whose [open, open+60s) interval contains attempt_ts+N. With 1m
    bars this is the price up to ~59s after the exact instant; we cannot do
    better without tick data. Reported per this convention, no cherry-picking.
  * touch-back note: if the +120s bar's range crosses the intended price
    (long: low <= intended; short: high >= intended), a resting re-quote might
    have filled at/near the intended price — noted, but the sim still uses the
    convention price.
  * re-quote sim: SAME exit model as the original (st2_lab.exit_replay._simulate
    variant=True, PARAMS sl 1.2 / tp 1.6 / 4h hold, _build_path adverse-first,
    _net maker 0.01% entry / taker 0.06% on stop-trail exits, $100 notional)
    with entry_price = the +120s convention price and entry_ts = attempt_ts+120.

Reads scripts/slot_lab (imports) and reports/mr_missed_fills.json (original sim
nets). Fetches 1m OHLCV fresh from Phemex public API via ccxt (same as the
original; no cached klines exist in the repo). Writes ONLY
reports/mr_requote_counterfactual.json. Touches nothing live.

Run from repo root:
    python reports/mr_requote_counterfactual.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_BOT_DIR = os.path.dirname(_HERE)
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts", "slot_lab"))

import ccxt  # noqa: E402
import pandas as pd  # noqa: E402

from mean_revert_replay import (  # noqa: E402
    _build_path, _net, PARAMS, NOTIONAL, MAKER_FEE, TAKER_FEE,
)
from st2_lab.exit_replay import _simulate  # noqa: E402
from missed_fill_counterfactual import MISSES, _pt_12h  # noqa: E402

HORIZONS = (60, 120, 300)
REQUOTE_DELAY_S = 120  # the sim horizon: re-quote entry at the +120s price


def _fetch_1m(ex, sym, entry_ts):
    """1m OHLCV covering [entry_ts-2m, entry_ts+delay+4h+30m]. None on failure."""
    since = (entry_ts - 120) * 1000
    rows, cursor = [], since
    need_until = (entry_ts + REQUOTE_DELAY_S + PARAMS["hold_secs"] + 1800) * 1000
    for _ in range(6):
        try:
            batch = ex.fetch_ohlcv(sym, "1m", since=int(cursor), limit=500)
        except Exception as e:  # noqa: BLE001
            print(f"    fetch error {sym}: {e}")
            return None
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + 60_000
        if batch[-1][0] >= need_until:
            break
        import time as _t
        _t.sleep(ex.rateLimit / 1000)
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("ts").sort_values("ts")
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_localize(None)
    return df


def _bar_at(df, t):
    """The 1m bar (row) whose [open, open+60s) contains epoch t, else None."""
    bar_open = (t // 60) * 60
    epochs = df.index.view("int64") // 1_000_000_000
    hit = df[epochs == bar_open]
    return hit.iloc[0] if len(hit) else None


def _adverse_bps(intended, p, side):
    """bps AWAY from intended in the adverse-for-entry direction (positive = worse)."""
    if side == "long":
        return (p - intended) / intended * 1e4
    return (intended - p) / intended * 1e4


def main():
    misses_json = json.load(open(os.path.join(_HERE, "mr_missed_fills.json")))
    orig_by_key = {(m["sym"], m["ts"]): m for m in misses_json["misses"]}

    ex = ccxt.phemex({"enableRateLimit": True})
    cache = {}
    rows = []

    print("5m_mean_revert RE-QUOTE counterfactual (entry = +120s convention price)")
    print(f"  exit model unchanged: {PARAMS}, trail+BE ON, maker {MAKER_FEE}% entry / "
          f"taker {TAKER_FEE}% stop-trail exit, notional ${NOTIONAL:.0f}")
    print("  +Ns price = CLOSE of the 1m bar containing attempt_ts+N (1m granularity)\n")

    for a in MISSES:
        sym, side, px, ts = a["sym"], a["side"], a["px"], a["ts"]
        orig = orig_by_key.get((sym, ts), {})
        key = (sym, ts)
        if sym not in cache or cache[sym] is None:
            cache[sym] = _fetch_1m(ex, sym, ts)
        else:
            # per-symbol cache may not cover a later attempt; refetch if not
            ep = cache[sym].index.view("int64") // 1_000_000_000
            if not (ep[0] <= ts - 60 and ep[-1] >= ts + 300):
                cache[sym] = _fetch_1m(ex, sym, ts)
        df = cache[sym]
        row = dict(sym=sym, side=side, intended_px=px, ts=ts,
                   attempt_pt=_pt_12h(ts), orig_sim_net=orig.get("sim_net"),
                   orig_sim_reason=orig.get("sim_reason"))
        if df is None:
            rows.append(dict(row, status="UNCOVERED", note="1m OHLCV unavailable"))
            print(f"  {sym} UNCOVERED — no 1m data")
            continue

        drift, uncovered = {}, False
        for n in HORIZONS:
            bar = _bar_at(df, ts + n)
            if bar is None:
                uncovered = True
                drift[f"p{n}"] = None
                drift[f"bps{n}"] = None
                continue
            p = float(bar["close"])
            drift[f"p{n}"] = p
            drift[f"bps{n}"] = round(_adverse_bps(px, p, side), 2)
        bar120 = _bar_at(df, ts + REQUOTE_DELAY_S)
        if uncovered or bar120 is None:
            rows.append(dict(row, status="UNCOVERED", note="missing 1m bar in horizon window", **drift))
            print(f"  {sym} UNCOVERED — missing bar at a horizon")
            continue

        touch_back = (float(bar120["low"]) <= px) if side == "long" else (float(bar120["high"]) >= px)
        entry2_px = float(bar120["close"])
        entry2_ts = ts + REQUOTE_DELAY_S
        path = _build_path(df, entry2_ts, PARAMS["hold_secs"], side)
        if not path:
            rows.append(dict(row, status="UNCOVERED", note="no forward path after re-quote", **drift))
            print(f"  {sym} UNCOVERED — no forward path")
            continue
        exit_px, reason, held = _simulate(sym, side, entry2_px, entry2_ts, path, PARAMS, variant=True)
        net = _net(entry2_px, exit_px, side, reason, NOTIONAL, MAKER_FEE)
        rows.append(dict(row, status="OK", **drift,
                         touch_back_at_120s_bar=bool(touch_back),
                         requote_entry_px=entry2_px, requote_sim_exit=exit_px,
                         requote_sim_reason=reason, requote_sim_held_s=int(held),
                         requote_sim_net=round(net, 4),
                         overlap=a.get("overlap")))
        print(f"  {row['attempt_pt']:>22s}  {sym.split('/')[0]:5s} {side:5s} "
              f"intended {px:<9g} drift bps +60/+120/+300 = "
              f"{drift['bps60']:+7.1f} {drift['bps120']:+7.1f} {drift['bps300']:+7.1f}  "
              f"requote entry {entry2_px:<9g} -> ${net:+.3f} ({reason})"
              + ("  [touch-back]" if touch_back else "")
              + ("  [overlap]" if a.get("overlap") else ""))

    ok = [r for r in rows if r["status"] == "OK"]
    unc = [r for r in rows if r["status"] != "OK"]

    def _avg(key):
        vals = [r[key] for r in ok if r.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    orig_nets = [r["orig_sim_net"] for r in ok]
    req_nets = [r["requote_sim_net"] for r in ok]
    totals = {
        "n_covered": len(ok),
        "n_uncovered": len(unc),
        "orig_sim": {"net": round(sum(orig_nets), 4),
                     "wins": sum(1 for x in orig_nets if x > 0),
                     "losses": sum(1 for x in orig_nets if x <= 0)},
        "requote_sim_120s": {"net": round(sum(req_nets), 4),
                             "wins": sum(1 for x in req_nets if x > 0),
                             "losses": sum(1 for x in req_nets if x <= 0)},
        "avg_adverse_drift_bps": {"h60": _avg("bps60"), "h120": _avg("bps120"),
                                  "h300": _avg("bps300")},
        "touch_back_count_120s": sum(1 for r in ok if r.get("touch_back_at_120s_bar")),
    }
    print("\n--- TOTALS (covered misses) ---")
    print(f"  original sim (fill at intended): net ${totals['orig_sim']['net']:+.2f}  "
          f"W/L {totals['orig_sim']['wins']}/{totals['orig_sim']['losses']}")
    print(f"  re-quote sim (+120s entry):      net ${totals['requote_sim_120s']['net']:+.2f}  "
          f"W/L {totals['requote_sim_120s']['wins']}/{totals['requote_sim_120s']['losses']}")
    print(f"  avg adverse drift bps: +60s {totals['avg_adverse_drift_bps']['h60']}  "
          f"+120s {totals['avg_adverse_drift_bps']['h120']}  +300s {totals['avg_adverse_drift_bps']['h300']}")
    print(f"  +120s bar touched intended price on {totals['touch_back_count_120s']}/{len(ok)} misses")

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": {
            "base": "same 11 misses + same exit model as reports/mr_missed_fills.json "
                    "(st2_lab.exit_replay._simulate variant=True, mean_revert_replay conventions)",
            "params": PARAMS, "notional": NOTIONAL,
            "fees_pct": {"maker": MAKER_FEE, "taker": TAKER_FEE,
                         "rule": "maker entry (re-quote is still PostOnly); taker exit on "
                                 "stop_loss/trailing_stop/catastrophe, maker on TP/hold"},
            "price_at_N_convention": "CLOSE of the 1m bar whose [open, open+60s) contains "
                                     "attempt_ts+N; 1m granularity, up to ~59s late vs exact instant",
            "drift_convention": "bps adverse-for-entry: long=(p-intended)/intended*1e4, "
                                "short=(intended-p)/intended*1e4; positive = worse fill",
            "requote_entry": "entry_price = +120s convention price, entry_ts = attempt_ts+120",
            "touch_back_flag": "+120s bar range crossed intended price -> a resting re-quote "
                               "might have filled at/near intended; sim still uses convention price",
            "data": "1m OHLCV fetched fresh from Phemex public API (ccxt), this run",
        },
        "rows": rows,
        "totals": totals,
        "caveat": "n=11 screening-grade; 1m bars cannot resolve sub-minute touch dynamics; "
                  "re-quote fill at the +120s close is itself an assumption (maker at new touch)",
    }
    out_path = os.path.join(_HERE, "mr_requote_counterfactual.json")
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(f"\n  dump: {out_path}")


if __name__ == "__main__":
    main()
