#!/usr/bin/env python3
"""5m_mean_revert PostOnly-miss counterfactual — were the misses dodged losers or missed winners?

Since ~Jun 17 the live 5m_mean_revert slot placed 13 PostOnly maker entries:
2 filled, 11 missed ("no fill (PostOnly miss)" — bot.py:2087). This script replays
each MISS as if the maker order HAD filled at the intended limit price (the price
in the immediately-preceding "[MAKER] Limit {buy|sell} ... @ px" log line), pushing
it through the SAME exit engine mean_revert_replay.py validated:

  * st2_lab.exit_replay._simulate  variant=True  (SL/TP + tiered trail + breakeven,
    matching mean_revert_replay.py's convention "durable_trail_enabled=True")
  * PARAMS  sl 1.2% / tp 1.6% / 4h hold  (flat — see mean_revert_replay.py header
    for the algebraic collapse of the ATR-adaptive geometry)
  * fees    maker 0.01% entry; exit taker 0.06% on stop/trail/catastrophe,
            maker 0.01% on TP/hold  ($100 notional = $10 margin x 10x)
  * price path: forward 1m OHLCV expanded two-points-per-bar, ADVERSE extreme
    first (pessimistic intrabar stop-vs-TP resolution)

The 2 REAL fills (WLD long 6/18, XLM short 6/24) are replayed the same way as a
sanity check against their recorded real outcomes in trading_state_5m_mean_revert.json.

ATTEMPT DATA PROVENANCE (all hand-verified from logs 2026-07-01):
  * Extraction: grep "[SLOT LIVE].*5m_mean_revert" + the paired "[MAKER] Limit"
    lines across logs/bot.log + bot.log.1..5 (full set, no .gz). Coverage:
    2026-06-17 23:48 local -> 2026-07-01 21:12 local. 13 unique attempts found
    (ANSI-colored duplicates deduped): 2 fills + 11 misses.
  * Log timestamps are LOCAL MAC TIME and the zone CHANGED mid-window (travel).
    Per-day offsets were derived by matching entry_snapshots.jsonl epoch ts to
    log ENTRY lines: Jun 18-23 = UTC-4 (ET); Jun 24 00:11 local onward = UTC-7
    (PT). Anchors: WLD fill opened_at=1781836498 (=2026-06-19 02:34:58 UTC, log
    2026-06-18 22:34:59, offset -4); XLM fill opened_at=1782332781 (=2026-06-24
    20:26:21 UTC, log 2026-06-24 13:26:22, offset -7).
  * Entry ts used = the [MAKER] Limit ORDER PLACEMENT line time (the order rested
    ~20-30s from there); entry price = the intended limit price from that line.

HONESTY CAVEATS:
  * Counterfactual assumes the resting limit WOULD have filled at the intended
    price (that is the premise of a bounded re-quote/chase) — optimistic on fill.
  * n=11 is anecdote-grade. This screens a direction, it proves nothing.
  * The two Jun 25 misses (XLM 21:45:26Z, ADA 21:45:58Z) OVERLAP; the live slot
    caps at 1 position, so at most ONE could have existed. Totals are reported
    both with and without the second (ADA) leg.
  * 1m OHLCV fetched fresh from Phemex public API (ccxt); any window the API
    cannot cover is marked UNCOVERED, never guessed.

Read-only vs live systems. Writes ONLY reports/mr_missed_fills.json.

Run from repo root:
    python scripts/slot_lab/missed_fill_counterfactual.py
    python scripts/slot_lab/missed_fill_counterfactual.py --dump-json reports/mr_missed_fills.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
_BOT_DIR = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _BOT_DIR)
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
sys.path.insert(0, _HERE)

import ccxt  # noqa: E402
import pandas as pd  # noqa: E402

# Reuse mean_revert_replay's validated conventions verbatim (no reinvention):
# _build_path (adverse-first 1m expansion), _net (fee model), PARAMS/NOTIONAL/fees.
from mean_revert_replay import (  # noqa: E402
    _build_path, _net, PARAMS, NOTIONAL, MAKER_FEE, TAKER_FEE,
)
from st2_lab.exit_replay import _simulate  # noqa: E402

ET = timezone(timedelta(hours=-4))   # log-local zone Jun 18-23 (verified, see header)
PT = timezone(timedelta(hours=-7))   # log-local zone Jun 24+   (verified, see header)


def _ep(y, mo, d, h, mi, s, tz):
    return int(datetime(y, mo, d, h, mi, s, tzinfo=tz).timestamp())


# ── The 13 live attempts (hand-verified from logs; see PROVENANCE in header) ──
# entry_ts = [MAKER] Limit placement time -> UTC epoch. price = intended limit.
MISSES = [
    # (placement local log line, symbol, side, limit px, RSI7 from signal reason or None)
    dict(sym="AVAX/USDT:USDT", side="short", px=5.962,   rsi=None,  ts=_ep(2026, 6, 19, 18, 24, 53, ET),
         src="bot.log.5: 2026-06-19 18:24:53 [MAKER] Limit sell 16.7 AVAX @ 5.962"),
    dict(sym="XRP/USDT:USDT",  side="long",  px=1.1454,  rsi=None,  ts=_ep(2026, 6, 20, 8, 56, 47, ET),
         src="bot.log.5: 2026-06-20 08:56:47 [MAKER] Limit buy 87.3 XRP @ 1.1454"),
    dict(sym="ADA/USDT:USDT",  side="short", px=0.1617,  rsi=70.9,  ts=_ep(2026, 6, 21, 5, 53, 6, ET),
         src="bot.log.4/5: 2026-06-21 05:53:06 [MAKER] Limit sell 618.42 ADA @ 0.1617"),
    dict(sym="XLM/USDT:USDT",  side="long",  px=0.21313, rsi=27.6,  ts=_ep(2026, 6, 22, 10, 23, 25, ET),
         src="bot.log.4: 2026-06-22 10:23:25 [MAKER] Limit buy 468.0 XLM @ 0.21313"),
    dict(sym="LTC/USDT:USDT",  side="long",  px=41.93,   rsi=22.2,  ts=_ep(2026, 6, 24, 3, 28, 3, PT),
         src="bot.log.3: 2026-06-24 03:28:03 [MAKER] Limit buy 2.38 LTC @ 41.93"),
    dict(sym="XLM/USDT:USDT",  side="short", px=0.17752, rsi=80.0,  ts=_ep(2026, 6, 25, 14, 44, 56, PT),
         src="bot.log.2: 2026-06-25 14:44:56 [MAKER] Limit sell 563.0 XLM @ 0.17752"),
    dict(sym="ADA/USDT:USDT",  side="short", px=0.1434,  rsi=72.0,  ts=_ep(2026, 6, 25, 14, 45, 28, PT),
         src="bot.log.2: 2026-06-25 14:45:28 [MAKER] Limit sell 697.35 ADA @ 0.1434",
         overlap="second concurrent signal; live slot max_positions=1 -> could not coexist with XLM short 32s earlier"),
    dict(sym="XLM/USDT:USDT",  side="long",  px=0.17789, rsi=26.7,  ts=_ep(2026, 6, 26, 12, 4, 3, PT),
         src="bot.log.2: 2026-06-26 12:04:03 [MAKER] Limit buy 561.0 XLM @ 0.17789"),
    dict(sym="XLM/USDT:USDT",  side="short", px=0.17611, rsi=73.6,  ts=_ep(2026, 6, 26, 21, 39, 16, PT),
         src="bot.log.2: 2026-06-26 21:39:16 [MAKER] Limit sell 567.0 XLM @ 0.17611"),
    dict(sym="LTC/USDT:USDT",  side="long",  px=42.9,    rsi=28.7,  ts=_ep(2026, 6, 28, 6, 9, 37, PT),
         src="bot.log.1: 2026-06-28 06:09:37 [MAKER] Limit buy 2.33 LTC @ 42.9"),
    dict(sym="DOGE/USDT:USDT", side="long",  px=0.07205, rsi=26.1,  ts=_ep(2026, 6, 30, 23, 14, 17, PT),
         src="bot.log.1: 2026-06-30 23:14:17 [MAKER] Limit buy 1388.0 DOGE @ 0.07205"),
]

# The 2 real fills — sanity check set. entry_ts/px from trading_state_5m_mean_revert.json.
FILLS = [
    dict(sym="WLD/USDT:USDT", side="long",  px=0.6416, rsi=27.9, ts=1781836498,
         real_net=1.5899158100000135, real_exit=0.6519, real_reason="exchange_close (TP)",
         src="trading_state_5m_mean_revert.json opened_at=1781836498.196945"),
    dict(sym="XLM/USDT:USDT", side="short", px=0.1868, rsi=82.5, ts=1782332781,
         real_net=-1.4749362599999976, real_exit=0.18946, real_reason="exchange_close (SL, exit delayed by host sleep)",
         src="trading_state_5m_mean_revert.json opened_at=1782332781.247328"),
]


def _fetch_1m(ex, sym, entry_ts):
    """1m OHLCV covering [entry_ts-2m, entry_ts+4h+30m] as a DataFrame indexed by
    UTC datetime (the shape _build_path expects). Returns None on failure."""
    since = (entry_ts - 120) * 1000
    rows = []
    cursor = since
    need_until = (entry_ts + PARAMS["hold_secs"] + 1800) * 1000
    for _ in range(5):
        try:
            batch = ex.fetch_ohlcv(sym, "1m", since=int(cursor), limit=500)
        except Exception as e:
            print(f"    fetch error {sym}: {e}")
            return None
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + 60_000
        if batch[-1][0] >= need_until:
            break
        time.sleep(ex.rateLimit / 1000)
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("ts").sort_values("ts")
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_localize(None)
    return df


def _pt_12h(ts):
    return datetime.fromtimestamp(ts, tz=PT).strftime("%b %-d %-I:%M %p PT")


def _replay_one(ex, a, cache):
    sym = a["sym"]
    if sym not in cache or cache[sym] is None or not _covers(cache[sym], a["ts"]):
        cache[sym] = _fetch_1m(ex, sym, a["ts"])
    df1m = cache[sym]
    if df1m is None:
        return dict(a, status="UNCOVERED", note="1m OHLCV unavailable")
    path = _build_path(df1m, a["ts"], PARAMS["hold_secs"], a["side"])
    if not path:
        return dict(a, status="UNCOVERED", note="no forward 1m bars in window")
    exit_px, reason, held = _simulate(sym, a["side"], a["px"], a["ts"], path,
                                      PARAMS, variant=True)
    net = _net(a["px"], exit_px, a["side"], reason, NOTIONAL, MAKER_FEE)
    return dict(a, status="OK", sim_exit=exit_px, sim_reason=reason,
                sim_held_s=held, sim_net=round(net, 4))


def _covers(df, entry_ts):
    if df is None or df.empty:
        return False
    lo = int(df.index.view("int64")[0] // 1_000_000_000)
    hi = int(df.index.view("int64")[-1] // 1_000_000_000)
    return lo <= entry_ts and hi >= entry_ts + 300  # at least some forward path


def main():
    ap = argparse.ArgumentParser(description="5m_mean_revert PostOnly-miss counterfactual")
    ap.add_argument("--dump-json", default=os.path.join(_BOT_DIR, "reports", "mr_missed_fills.json"))
    args = ap.parse_args()

    print("5m_mean_revert PostOnly-miss counterfactual (SCREENING-GRADE, n=11 — anecdote)")
    print(f"  exit model: mean_revert_replay conventions — {PARAMS}, trail+BE ON (variant=True)")
    print(f"  fees: maker {MAKER_FEE}% entry; taker {TAKER_FEE}% on stop/trail exit, maker on TP/hold; notional ${NOTIONAL:.0f}")

    ex = ccxt.phemex({"enableRateLimit": True})
    cache = {}

    print("\n--- SANITY CHECK: the 2 REAL fills, sim vs real ---")
    fill_rows = []
    for a in FILLS:
        r = _replay_one(ex, a, cache)
        fill_rows.append(r)
        if r["status"] == "OK":
            print(f"  {a['sym'].split('/')[0]:5s} {a['side']:5s} {_pt_12h(a['ts']):>22s}  "
                  f"sim ${r['sim_net']:+.2f} ({r['sim_reason']}, exit {r['sim_exit']:.5f})  "
                  f"vs real ${a['real_net']:+.2f} ({a['real_reason']}, exit {a['real_exit']})")
        else:
            print(f"  {a['sym']} UNCOVERED — {r['note']}")

    print("\n--- COUNTERFACTUAL: the 11 misses, filled at intended limit price ---")
    miss_rows = []
    for a in MISSES:
        r = _replay_one(ex, a, cache)
        miss_rows.append(r)
        if r["status"] == "OK":
            print(f"  {_pt_12h(a['ts']):>22s}  {a['sym'].split('/')[0]:5s} {a['side']:5s} "
                  f"RSI={a['rsi'] if a['rsi'] is not None else ' n/a'}  entry {a['px']:<9g} "
                  f"-> ${r['sim_net']:+.3f}  ({r['sim_reason']}, held {r['sim_held_s']//60}m)"
                  + ("  [overlap]" if a.get("overlap") else ""))
        else:
            print(f"  {_pt_12h(a['ts']):>22s}  {a['sym'].split('/')[0]:5s} UNCOVERED — {r['note']}")

    ok = [r for r in miss_rows if r["status"] == "OK"]
    ok_no_overlap = [r for r in ok if not r.get("overlap")]
    unc = [r for r in miss_rows if r["status"] != "OK"]

    def _tot(rows, label):
        nets = [r["sim_net"] for r in rows]
        w = sum(1 for x in nets if x > 0)
        print(f"  {label}: n={len(nets)}  net ${sum(nets):+.2f}  W/L {w}/{len(nets)-w}"
              f"  avg ${sum(nets)/len(nets):+.3f}/trade" if nets else f"  {label}: n=0")
        return dict(n=len(nets), net=round(sum(nets), 4), wins=w,
                    losses=len(nets) - w, avg=round(sum(nets) / len(nets), 4) if nets else 0.0)

    print("\n--- TOTALS (misses) ---")
    t_all = _tot(ok, "all covered misses")
    t_occ = _tot(ok_no_overlap, "occupancy-realistic (drop 2nd concurrent Jun 25 leg)")
    if unc:
        print(f"  UNCOVERED: {len(unc)} miss(es) not simulated")

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": {
            "exit_model": "st2_lab.exit_replay._simulate variant=True (SL/TP + trail + breakeven), "
                          "per mean_revert_replay.py conventions",
            "params": PARAMS, "notional": NOTIONAL,
            "fees_pct": {"maker": MAKER_FEE, "taker": TAKER_FEE,
                         "rule": "maker entry; taker exit on stop_loss/trailing_stop/catastrophe, maker on TP/hold"},
            "path": "1m OHLCV, two points per bar, adverse extreme first (pessimistic)",
            "entry_assumption": "miss counterfactual fills at the intended [MAKER] Limit price at placement time",
            "tz_note": "log local time Jun 18-23 = UTC-4 (ET), Jun 24+ = UTC-7 (PT); "
                       "verified via entry_snapshots.jsonl epochs vs log ENTRY lines",
            "log_coverage": "logs/bot.log + bot.log.1..5 = 2026-06-17 23:48 local -> 2026-07-01 21:12 local; no .gz; "
                            "attempts before Jun 17 23:48 (slot live since Jun 12) are lost to rotation",
        },
        "sanity_fills": fill_rows,
        "sanity_note": "WLD reproduces (sim +1.58 vs real +1.59, same TP). XLM does NOT and is NOT "
                       "expected to: the real trade held 16824s (>4h hold, from the state file) because "
                       "host sleep suspended software exits (known 2026-06-24 incident) and price blew "
                       "through the SL to 0.18946 (trigger 0.18904). Sim (bot awake): trail exit +0.19; "
                       "even with trail OFF the position was +$1.01 at the 4h hold. Not tuned to match.",
        "misses": miss_rows,
        "totals": {"all_covered": t_all, "occupancy_realistic": t_occ,
                   "uncovered": len(unc)},
        "caveat": "n=11 counterfactuals, screening-grade anecdote; fill-at-intended-price is optimistic",
    }
    os.makedirs(os.path.dirname(args.dump_json), exist_ok=True)
    with open(args.dump_json, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(f"\n  dump: {args.dump_json}")


if __name__ == "__main__":
    main()
