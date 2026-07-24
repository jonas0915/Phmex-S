#!/usr/bin/env python3
"""Old/new-geometry counterfactual scans from cached L2 tick files (best bid/ask mid).
READ-ONLY. Windows in UTC ms."""
import gzip, json, datetime, os
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = "/Users/jonaspenaso/Desktop/Phmex-S/logs/l2_ticks"

def load(sym, dates):
    rows = []
    for d in dates:
        for name in (f"{d}.jsonl.gz", f"{d}.jsonl"):
            p = os.path.join(ROOT, sym, name)
            if os.path.exists(p):
                op = gzip.open(p, "rt") if name.endswith(".gz") else open(p)
                with op as f:
                    for line in f:
                        try:
                            r = json.loads(line)
                        except Exception:
                            continue
                        if r.get("b") and r.get("a"):
                            rows.append((r["ts"], (r["b"][0][0] + r["a"][0][0]) / 2))
                break
    rows.sort()
    return rows

def scan(name, sym, dates, t0_ms, entry, side, levels, t1_ms=None):
    """levels: dict label->price. Report first touch time of each, plus MFE/MAE in window [t0,t1]."""
    rows = [r for r in load(sym, dates) if r[0] >= t0_ms]
    if not rows:
        print(f"{name}: NO TICK DATA")
        return
    d = 1 if side == "long" else -1
    win = [r for r in rows if t1_ms is None or r[0] <= t1_ms]
    print(f"\n{name}: ticks from {datetime.datetime.fromtimestamp(rows[0][0]/1000, PT).strftime('%m/%d %I:%M:%S %p')} "
          f"to {datetime.datetime.fromtimestamp(rows[-1][0]/1000, PT).strftime('%m/%d %I:%M:%S %p')} PT, n={len(rows)}"
          + (f" (hold-window n={len(win)})" if t1_ms else ""))
    if win:
        mfe = max((p - entry) / entry * 100 * d for _, p in win)
        mae = min((p - entry) / entry * 100 * d for _, p in win)
        print(f"  hold-window MFE={mfe:+.3f}% MAE={mae:+.3f}% (oriented)")
    for lbl, lvl in levels.items():
        hit = None
        for ts, p in rows:
            if (side == "long" and lbl.startswith(("SL", "sl")) and p <= lvl) or \
               (side == "long" and not lbl.startswith(("SL", "sl")) and p >= lvl) or \
               (side == "short" and lbl.startswith(("SL", "sl")) and p >= lvl) or \
               (side == "short" and not lbl.startswith(("SL", "sl")) and p <= lvl):
                hit = ts
                break
        if hit:
            print(f"  {lbl} @{lvl:.6g}: FIRST TOUCH {datetime.datetime.fromtimestamp(hit/1000, PT).strftime('%m/%d %I:%M:%S %p')} PT")
        else:
            print(f"  {lbl} @{lvl:.6g}: never touched in tick coverage")

def ms(y, m, d, hh, mm, ss=0):
    return int(datetime.datetime(y, m, d, hh, mm, ss, tzinfo=PT).timestamp() * 1000)

# (b) slot ETH loser #2: long 1946.97, 7/22 10:12:51 AM PT, actual SL trigger 1927.5 hit 11:34 AM
scan("SLOT ETH loser (7/22 10:12 AM long @1946.97)", "ETH_USDT_USDT",
     ["2026-07-22", "2026-07-23"], ms(2026, 7, 22, 10, 12, 51), 1946.97, "long",
     {"SL_old(-1.2%)": 1946.97 * 0.988, "TP_old(+1.6%)": 1946.97 * 1.016,
      "partial_old(+1.0%)": 1946.97 * 1.01, "SL_new(-1.0%)": 1946.97 * 0.99},
     t1_ms=ms(2026, 7, 22, 11, 34, 14))

# (a) slot ETH loser #1: long 1930.69, 7/21 4:33:05 AM PT, hard_time_exit 9:51:48 AM @1925.59
scan("SLOT ETH loser (7/21 4:33 AM long @1930.69)", "ETH_USDT_USDT",
     ["2026-07-21"], ms(2026, 7, 21, 4, 33, 5), 1930.69, "long",
     {"SL_old(-1.2%)": 1930.69 * 0.988, "TP_old(+1.6%)": 1930.69 * 1.016,
      "partial_old(+1.0%)": 1930.69 * 1.01, "SL_new(-1.0%)": 1930.69 * 0.99},
     t1_ms=ms(2026, 7, 21, 9, 51, 48))

# (c) main ETH winner under NEW geometry: long 1929.56, 7/22 7:23:20 AM PT
scan("MAIN ETH winner counterfactual NEW geometry (7/22 7:23 AM long @1929.56)", "ETH_USDT_USDT",
     ["2026-07-22", "2026-07-23"], ms(2026, 7, 22, 7, 23, 20), 1929.56, "long",
     {"SL_new(-1.0%)": 1929.56 * 0.99, "TP_new(+2.0%)": 1929.56 * 1.02,
      "TP_old(+1.6%)": 1929.56 * 1.016},
     t1_ms=ms(2026, 7, 22, 11, 34, 14))  # cap at slot-demote time for the hold-window stats; touches scan full tape

# (d) main BTC loser (old geometry, actual): short 64698.2, 7/23 11:06:43 AM PT, hard_time_exit 4:38 PM @65176
scan("MAIN BTC loser (7/23 11:06 AM short @64698.2, actual old geometry)", "BTC_USDT_USDT",
     ["2026-07-23", "2026-07-24"], ms(2026, 7, 23, 11, 6, 43), 64698.2, "short",
     {"SL_old(+1.2%)": 64698.2 * 1.012, "TP_old(-1.6%)": 64698.2 * 0.984,
      "partial_old(-1.0%)": 64698.2 * 0.99},
     t1_ms=ms(2026, 7, 23, 16, 38, 48))
