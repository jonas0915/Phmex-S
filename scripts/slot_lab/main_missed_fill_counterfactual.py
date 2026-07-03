#!/usr/bin/env python3
"""MAIN-BOT PostOnly-miss counterfactual — were the misses dodged losers or missed winners?

Companion to missed_fill_counterfactual.py (the 5m_mean_revert slot version, which
found 11 misses = missed winners and justified a live maker re-quote on that slot).
Same question for the MAIN bot: entries go PostOnly at the touch
(exchange.py open_long/open_short -> _try_limit_entry, 20s poll then cancel);
a miss logs "[FILL MISS]" (exchange.py:417/458/462) and the main loop logs
"[ENTRY] Order FAILED ... signal lost" (bot.py:1705).

WHAT THIS SCRIPT DOES (all at runtime — nothing hand-copied):
  1. Parses logs/bot.log + bot.log.1..5 for [MAKER] Limit attempt lines, pairs each
     with its [FILL] / [FILL MISS] outcome, and classifies MAIN-loop vs SLOT
     ([SLOT LIVE] lines — ST2.0 / 5m_mean_revert have their own path and are
     EXCLUDED here). ANSI-colored duplicate lines deduped; attempts deduped by
     exchange order id.
  2. Converts log LOCAL times to epoch. The Mac's zone flipped mid-window (travel):
     UTC-4 (ET) until the ~3h BACKWARD in-file timestamp jump in bot.log.3
     (12:13:16 -> 09:14:24 on 2026-06-23, i.e. flip at ~16:14 UTC / 9:14 AM PT),
     UTC-7 (PT) after it. The flip is detected per-file at parse time (a 2.5-3.5h
     backward jump), NOT assumed at a day boundary — a day-boundary map silently
     shifted 8 post-flip Jun-23-evening attempts by 3h during development. The
     zone assignment is RE-VERIFIED at runtime by matching trading_state.json
     opened_at epochs to [ENTRY] log lines (abort on contradiction). Rotated logs
     OVERLAP (rotation copies ranges); duplicates are removed by (ts,msg) key and
     order id, and each copy gets the same zone.
  3. For each MAIN miss, simulates the counterfactual "filled at the intended limit
     price at placement time" through the SAME validated exit engine the slot study
     used (st2_lab.exit_replay._simulate, variant=True = SL/TP + tiered trail +
     breakeven), with mean_revert_replay's conventions: flat SL 1.2% / TP 1.6% /
     4h hold, $100 notional, maker 0.01% entry fee, taker 0.06% exit on
     stop/trail/catastrophe, maker on TP/hold; 1m OHLCV path expanded
     two-points-per-bar ADVERSE EXTREME FIRST (pessimistic intrabar).
     These constants equal the live main-bot geometry: real "Position opened" lines
     in this window show SL exactly 1.2% / TP 1.6% (the ATR-adaptive formula
     collapses, same algebra as mean_revert_replay.py header) and time_exit=hard240
     (= the 4h hold).
  4. SANITY CHECK: every matched real MAIN fill in the window is replayed the same
     way and compared to its actual recorded outcome in trading_state.json.
  5. OCCUPANCY: MAX_OPEN_TRADES=3. A chronological sweep marks counterfactual
     misses that could NOT have been held because (real open positions at that
     moment + earlier counterfactual positions still open) >= 3, or because an
     earlier counterfactual position on the SAME symbol was still open (the bot
     holds max 1 position per symbol). Totals reported with and without those.

HONESTY CAVEATS:
  * Counterfactual assumes the resting limit WOULD have filled at the intended
    price — the premise of a re-quote/chase port, OPTIMISTIC on fill reality.
  * PARTIAL-TP NOT MODELED: since 6/19 the main bot scales out half at +10% ROI
    (+1.0% price) and runs the rest toward +25% ROI. The sim uses the plain full-
    size 1.6% TP + trail instead. Bias direction is AMBIGUOUS but second-order:
    banking half at +1.0% cuts giveback on reversals (sim understates those
    winners) but also caps upside on the banked half (sim overstates those).
  * Misses whose 4h forward window extends past the last available 1m data are
    tagged PARTIAL (end_of_path) and EXCLUDED from headline totals.
  * Occupancy sweep can't model the knock-on effects on cooldowns/daily caps of
    positions that never existed; it only enforces the 3-slot + 1-per-symbol caps.
  * n is small and the window ~2 weeks: SCREENING-GRADE ANECDOTE, not proof.
  * 1m OHLCV fetched fresh from Phemex public API (ccxt); anything the API can't
    cover is marked UNCOVERED, never guessed.

Read-only vs live systems. Writes ONLY the --dump-json report.

Run from repo root:
    python scripts/slot_lab/main_missed_fill_counterfactual.py
    python scripts/slot_lab/main_missed_fill_counterfactual.py --dump-json reports/main_missed_fills.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
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

# Reuse the slot study's validated conventions verbatim (no reinvention):
from mean_revert_replay import (  # noqa: E402
    _build_path, _net, PARAMS, NOTIONAL, MAKER_FEE, TAKER_FEE,
)
from st2_lab.exit_replay import _simulate  # noqa: E402

ET = timezone(timedelta(hours=-4))   # log-local zone before the in-file flip jump
PT = timezone(timedelta(hours=-7))   # log-local zone after it (runtime-verified)
TZ_FLIP_HINT = "2026-06-23 09:14:24"  # post-jump local time of the ET->PT flip (bot.log.3)
LOG_FILES = ["bot.log.5", "bot.log.4", "bot.log.3", "bot.log.2", "bot.log.1", "bot.log"]
MAX_OPEN = 3                          # .env MAX_OPEN_TRADES

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TSLINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(\w+)\] (.*)$")
_MAKER = re.compile(r"\[MAKER\] Limit (buy|sell) ([\d.]+) (\S+) @ ([\d.eE+-]+) \(id=([\w-]+)\)")
_ENTRYLN = re.compile(r"\[ENTRY\] (LONG|SHORT) (\S+) \| Fill: ([\d.]+)")
_KEYS = ("[MAKER] Limit", "[FILL]", "[FILL MISS]", "[SLOT LIVE]", "[ENTRY]",
         "[ENTRY SAFETY]", "partial fill", "Position opened")


def _pt_12h(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=PT).strftime("%b %-d %-I:%M %p PT")


# ── 1. log parsing ───────────────────────────────────────────────────────────

def _parse_events():
    """Events as (file, ts_str, epoch, msg). The local->epoch zone starts ET and
    flips to PT at the single ~3h BACKWARD in-file timestamp jump (the Mac's
    travel TZ change). Files that start after the flip begin in PT. Any OTHER
    large in-file backward jump aborts (unmodeled clock change)."""
    events, seen, flips = [], set(), []
    flip_seen = False
    for f in LOG_FILES:
        p = os.path.join(_BOT_DIR, "logs", f)
        if not os.path.exists(p):
            continue
        # File entirely after the flip? (rotated logs overlap; each file's zone
        # state is decided independently, so duplicated ranges agree.)
        zone = PT if flip_seen else ET
        prev_t = None
        with open(p, errors="replace") as fh:
            for raw in fh:
                line = _ANSI.sub("", raw.rstrip("\n"))
                m = _TSLINE.match(line)
                if not m:
                    continue
                ts_str, _level, msg = m.group(1), m.group(2), m.group(3)
                t = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                if prev_t is not None:
                    back_h = (prev_t - t).total_seconds() / 3600
                    if 2.5 <= back_h <= 3.5 and zone is ET:
                        zone, flip_seen = PT, True   # the ET->PT travel flip
                        flips.append(f"{f}: {prev_t} -> {t}")
                    elif back_h > 0.5:
                        raise SystemExit(f"UNMODELED backward clock jump in {f}: "
                                         f"{prev_t} -> {t} ({back_h:.2f}h)")
                prev_t = t
                if not any(k in msg for k in _KEYS):
                    continue
                key = (ts_str, msg)
                if key in seen:          # ANSI-colored or rotation-overlap duplicate
                    continue
                seen.add(key)
                events.append((f, ts_str, int(t.replace(tzinfo=zone).timestamp()), msg))
    if len(flips) != 1:
        raise SystemExit(f"expected exactly 1 TZ flip jump, found {len(flips)}: {flips}")
    return events, flips[0]


def _extract_attempts(events):
    """Every unique [MAKER] Limit order, paired with outcome + origin."""
    attempts, seen_ids = [], set()
    for idx, (f, ts_str, ep, msg) in enumerate(events):
        m = _MAKER.search(msg)
        if not m:
            continue
        side_word, _amt, sym, px, oid = m.groups()
        if oid in seen_ids:
            continue
        seen_ids.add(oid)
        a = dict(file=f, ts_local=ts_str, ts=ep,
                 side="long" if side_word == "buy" else "short",
                 sym=sym, px=float(px), oid=oid,
                 outcome=None, origin=None, partial_skip=False)
        # Collect all attributable marker lines up to the NEXT attempt (or +300s),
        # then decide origin by priority. First-line-wins is WRONG here: slots also
        # emit "Position opened" between [FILL] and their [SLOT LIVE] tag.
        markers = []
        for f2, ts2, ep2, m2 in events[idx + 1: idx + 40]:
            dt = ep2 - ep
            if dt > 300 or _MAKER.search(m2):
                break
            if a["outcome"] is None:
                if f"[FILL MISS] {sym}" in m2:
                    a["outcome"] = "miss"
                elif f"[FILL] {sym}" in m2 and "exit fill" not in m2:
                    a["outcome"] = "fill"
                continue
            if sym in m2:
                markers.append(m2)
        slot_m = next((m for m in markers if "[SLOT LIVE]" in m), None)
        if slot_m:
            a["origin"] = "slot:" + slot_m.split("[SLOT LIVE]")[1].strip().split()[0]
        elif any("[ENTRY] Order FAILED" in m or _ENTRYLN.search(m) for m in markers):
            a["origin"] = "main"
        elif any("partial fill" in m for m in markers):
            a["origin"], a["partial_skip"] = "main", True
        elif any("Position opened" in m for m in markers):
            a["origin"] = "main"
        if a["origin"] == "main" and any("partial fill" in m for m in markers):
            a["partial_skip"] = True
        attempts.append(a)
    return attempts


# ── 2. runtime timezone verification ─────────────────────────────────────────

def _verify_tz(events, closed_trades):
    """Match state-file opened_at epochs to [ENTRY] log lines and verify the
    parse-time zone assignment. Clean anchors = |event_epoch - opened_at| <= 120s.
    CAUTION: opened_at is NOT authoritative for restart-synced positions ([SYNC]
    rewrites it to the restart time — seen on ETH 2026-07-02), so mismatched
    price-matches are only treated as zone errors when they are ~exactly 3h off
    AND the day has no clean anchor. Returns {local_day: verified_offset}."""
    anchors, suspects = {}, {}
    for f, ts_str, ep, msg in events:
        em = _ENTRYLN.search(msg)
        if not em:
            continue
        side, sym, px = em.group(1).lower(), em.group(2), float(em.group(3))
        for t in closed_trades:
            if (t.get("symbol") == sym and t.get("side") == side
                    and abs(float(t.get("entry", 0)) - px) / px < 1e-5
                    and abs(float(t["opened_at"]) - ep) < 14400):
                delta = abs(float(t["opened_at"]) - ep)
                if delta <= 120:                     # clean anchor
                    local = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    utc = datetime.fromtimestamp(t["opened_at"], tz=timezone.utc).replace(tzinfo=None)
                    anchors[ts_str[:10]] = round((local - utc).total_seconds() / 3600)
                elif abs(delta - 10800) <= 120:      # ~exactly 3h = possible zone mistake
                    suspects[ts_str[:10]] = f"{sym} {ts_str} delta {delta:.0f}s"
                # else: ambiguous same-price match (retries/restart-sync) — not an anchor
    for day, info in suspects.items():
        if day not in anchors:
            raise SystemExit(f"TZ ANCHOR CONTRADICTION on {day} (no clean anchor): {info}")
    return anchors


# ── 3/4. counterfactual + sanity replay ─────────────────────────────────────

def _fetch_1m(ex, sym, entry_ts):
    since = (entry_ts - 120) * 1000
    rows, cursor = [], since
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


def _covers(df, entry_ts, full=True):
    """True when the cache actually has 1m bars INSIDE the needed forward window.
    Min/max-only checks are wrong here: the per-symbol cache is merged from
    disjoint fetches, so a miss can sit in a gap between two covered windows."""
    if df is None or df.empty:
        return False
    sec = df["ts"].to_numpy() // 1000
    if full:
        need = PARAMS["hold_secs"]
        n = int(((sec > entry_ts) & (sec <= entry_ts + need)).sum())
        return n >= 0.8 * need / 60
    # minimal: any forward bar soon after entry (partial paths handled downstream)
    return bool(((sec > entry_ts) & (sec <= entry_ts + 900)).any())


def _replay_one(ex, a, cache, now_ts):
    sym = a["sym"]
    if not (_covers(cache.get(sym), a["ts"])
            and _covers(cache.get(sym), a["ts"], full=False)):
        fresh = _fetch_1m(ex, sym, a["ts"])
        if fresh is not None:
            old = cache.get(sym)
            merged = pd.concat([old, fresh]) if old is not None else fresh
            merged = merged.reset_index(drop=True).drop_duplicates("ts").sort_values("ts")
            merged.index = pd.to_datetime(merged["ts"], unit="ms", utc=True).dt.tz_localize(None).rename(None)
            cache[sym] = merged
    df1m = cache.get(sym)
    if df1m is None or not _covers(df1m, a["ts"], full=False):
        return dict(a, status="UNCOVERED", note="1m OHLCV unavailable")
    path = _build_path(df1m, a["ts"], PARAMS["hold_secs"], a["side"])
    if not path:
        return dict(a, status="UNCOVERED", note="no forward 1m bars in window")
    exit_px, reason, held = _simulate(sym, a["side"], a["px"], a["ts"], path,
                                      PARAMS, variant=True)
    net = _net(a["px"], exit_px, a["side"], reason, NOTIONAL, MAKER_FEE)
    status = "OK"
    if reason == "end_of_path" and a["ts"] + PARAMS["hold_secs"] > now_ts - 300:
        status = "PARTIAL"   # window still open in real time — outcome not final
    return dict(a, status=status, sim_exit=exit_px, sim_reason=reason,
                sim_held_s=int(held), sim_net=round(net, 4))


# ── 5. occupancy sweep ───────────────────────────────────────────────────────

def _occupancy_flags(miss_rows, state):
    """Mark counterfactual misses that violate MAX_OPEN=3 or 1-per-symbol once
    earlier counterfactual positions are held. Real occupancy from the state file
    (closed trades + currently-open positions)."""
    real = []
    for t in state.get("closed_trades", []):
        if t.get("opened_at") and t.get("closed_at"):
            real.append((float(t["opened_at"]), float(t["closed_at"])))
    for p in (state.get("positions") or {}).values():
        if p.get("opened_at"):
            real.append((float(p["opened_at"]), time.time()))
    cf_open = []   # (sym, exit_ts)
    for r in sorted(miss_rows, key=lambda x: x["ts"]):
        if r["status"] not in ("OK", "PARTIAL"):
            continue
        ts = r["ts"]
        cf_open = [(s, e) for s, e in cf_open if e > ts]
        n_real = sum(1 for o, c in real if o <= ts < c)
        blocked = (n_real + len(cf_open) >= MAX_OPEN
                   or any(s == r["sym"] for s, _ in cf_open))
        r["blocked_by_occupancy"] = blocked
        r["real_open_at_ts"] = n_real
        if not blocked:
            cf_open.append((r["sym"], ts + r.get("sim_held_s", PARAMS["hold_secs"])))


# ── main ─────────────────────────────────────────────────────────────────────

def _tot(rows, label):
    nets = [r["sim_net"] for r in rows]
    if not nets:
        print(f"  {label}: n=0")
        return dict(n=0, net=0.0, wins=0, losses=0, avg=0.0)
    w = sum(1 for x in nets if x > 0)
    print(f"  {label}: n={len(nets)}  net ${sum(nets):+.2f}  W/L {w}/{len(nets) - w}"
          f"  avg ${sum(nets) / len(nets):+.3f}/trade")
    return dict(n=len(nets), net=round(sum(nets), 4), wins=w,
                losses=len(nets) - w, avg=round(sum(nets) / len(nets), 4))


def main():
    ap = argparse.ArgumentParser(description="main-bot PostOnly-miss counterfactual")
    ap.add_argument("--dump-json", default=os.path.join(_BOT_DIR, "reports", "main_missed_fills.json"))
    args = ap.parse_args()
    now_ts = int(time.time())

    print("MAIN-BOT PostOnly-miss counterfactual (SCREENING-GRADE anecdote)")
    print(f"  exit model: {PARAMS} + trail/BE (variant=True); notional ${NOTIONAL:.0f}; "
          f"fees maker {MAKER_FEE}%/taker {TAKER_FEE}% (taker on stop/trail)")
    print("  NOTE: partial-TP (+10% ROI scale-out, live since 6/19) NOT modeled — see header.")

    events, flip = _parse_events()
    state = json.load(open(os.path.join(_BOT_DIR, "trading_state.json")))
    anchors = _verify_tz(events, state.get("closed_trades", []))
    print(f"\n  TZ: ET->PT flip at in-file jump [{flip}]; zone assignment verified on "
          f"{len(anchors)} anchored days: "
          + str({d: f"UTC{o:+d}" for d, o in sorted(anchors.items())}))

    attempts = _extract_attempts(events)
    main_att = [a for a in attempts if a["origin"] == "main"]
    slot_att = [a for a in attempts if (a["origin"] or "").startswith("slot:")]
    unknown = [a for a in attempts if a["origin"] is None]
    fills = [a for a in main_att if a["outcome"] == "fill" and not a["partial_skip"]]
    partial_skips = [a for a in main_att if a["partial_skip"]]
    misses = [a for a in main_att if a["outcome"] == "miss"]
    span = (attempts[0]["ts_local"], attempts[-1]["ts_local"]) if attempts else ("-", "-")

    print(f"\n--- ATTEMPTS (logs {span[0]} -> {span[1]} local; slots excluded) ---")
    print(f"  main-loop: {len(main_att)} attempts = {len(fills)} fills + "
          f"{len(partial_skips)} partial-fill-skips (min_margin) + {len(misses)} misses")
    denom = len(main_att)
    if denom:
        print(f"  fill rate: {len(fills)}/{denom} = {100 * len(fills) / denom:.1f}% "
              f"({100 * (len(fills) + len(partial_skips)) / denom:.1f}% counting partials); "
              f"miss rate {100 * len(misses) / denom:.1f}%")
    print(f"  excluded slot attempts: {len(slot_att)}; unattributed: {len(unknown)}")
    for a in unknown:
        print(f"    UNATTRIBUTED (excluded): {a['ts_local']} {a['sym']} {a['side']} {a['outcome']}")

    ex = ccxt.phemex({"enableRateLimit": True})
    cache = {}

    # sanity: replay every matched real fill vs its recorded outcome
    print("\n--- SANITY CHECK: real main-bot fills, sim vs recorded ---")
    ct = state.get("closed_trades", [])
    sanity_rows = []
    for a in fills:
        match = None
        for t in ct:
            if (t.get("symbol") == a["sym"] and t.get("side") == a["side"]
                    and abs(float(t.get("opened_at", 0)) - a["ts"]) < 180):
                match = t
                break
        if not match:
            continue
        r = _replay_one(ex, a, cache, now_ts)
        r["real_net"] = round(float(match.get("net_pnl", 0.0)), 4)
        r["real_reason"] = match.get("exit_reason")
        r["real_exit"] = match.get("exit")
        sanity_rows.append(r)
        if r["status"] in ("OK", "PARTIAL"):
            agree = "same-sign" if (r["sim_net"] > 0) == (r["real_net"] > 0) else "SIGN-FLIP"
            print(f"  {_pt_12h(a['ts']):>19s}  {a['sym'].split('/')[0]:9s} {a['side']:5s} "
                  f"sim ${r['sim_net']:+.2f} ({r['sim_reason']:13s}) vs real ${r['real_net']:+.2f} "
                  f"({r['real_reason']}) [{agree}]")
        else:
            print(f"  {_pt_12h(a['ts']):>19s}  {a['sym'].split('/')[0]:9s} UNCOVERED — {r['note']}")
    okr = [r for r in sanity_rows if r["status"] == "OK"]
    if okr:
        same = sum(1 for r in okr if (r["sim_net"] > 0) == (r["real_net"] > 0))
        print(f"  matched {len(sanity_rows)} fills to state; sign agreement {same}/{len(okr)}; "
              f"sim total ${sum(r['sim_net'] for r in okr):+.2f} vs real ${sum(r['real_net'] for r in okr):+.2f}")

    # counterfactual misses
    print(f"\n--- COUNTERFACTUAL: {len(misses)} main-loop misses, filled at intended price ---")
    miss_rows = []
    for a in misses:
        r = _replay_one(ex, a, cache, now_ts)
        miss_rows.append(r)
        if r["status"] in ("OK", "PARTIAL"):
            tag = " [PARTIAL — window still open]" if r["status"] == "PARTIAL" else ""
            print(f"  {_pt_12h(a['ts']):>19s}  {a['sym'].split('/')[0]:9s} {a['side']:5s} "
                  f"@ {a['px']:<10g} -> ${r['sim_net']:+.3f}  ({r['sim_reason']}, "
                  f"held {r['sim_held_s'] // 60}m){tag}")
        else:
            print(f"  {_pt_12h(a['ts']):>19s}  {a['sym'].split('/')[0]:9s} UNCOVERED — {r['note']}")

    _occupancy_flags(miss_rows, state)

    ok = [r for r in miss_rows if r["status"] == "OK"]
    ok_occ = [r for r in ok if not r.get("blocked_by_occupancy")]
    partial = [r for r in miss_rows if r["status"] == "PARTIAL"]
    unc = [r for r in miss_rows if r["status"] == "UNCOVERED"]
    n_blocked = sum(1 for r in ok if r.get("blocked_by_occupancy"))

    print("\n--- TOTALS (misses) ---")
    t_all = _tot(ok, "all covered misses (occupancy ignored)")
    t_occ = _tot(ok_occ, f"occupancy-realistic (drop {n_blocked} blocked by 3-slot/1-per-symbol caps)")
    if partial:
        print(f"  PARTIAL (4h window still open, excluded): {len(partial)}")
    if unc:
        print(f"  UNCOVERED: {len(unc)}")

    print("\n--- VERDICT (screening-grade) ---")
    verdict, bias, corr_occ, corr_all = "n/a", None, None, None
    if t_occ["n"]:
        if okr:
            bias = (sum(r["sim_net"] for r in okr) - sum(r["real_net"] for r in okr)) / len(okr)
            corr_occ = round(t_occ["net"] - bias * t_occ["n"], 2)
            corr_all = round(t_all["net"] - bias * t_all["n"], 2)
        raw = t_occ["net"]
        if raw > 1.0 and (corr_occ is None or corr_occ > 1.0):
            verdict = ("MISSED WINNERS — a bounded maker re-quote/chase port is a "
                       "live-forward CANDIDATE")
        elif raw < -1.0 and (corr_occ is None or corr_occ < -1.0):
            verdict = "DODGED LOSERS — leave the 20s-cancel behavior alone"
        else:
            verdict = ("NEUTRAL/AMBIGUOUS — counterfactual is within the simulator's own "
                       "measured optimism; no clear missed edge, not enough to justify a "
                       "re-quote port on this evidence alone")
        print(f"  occupancy-realistic counterfactual: n={t_occ['n']} net ${raw:+.2f} (raw)")
        if bias is not None:
            print(f"  calibration: same sim on the {len(okr)} matched REAL fills scored "
                  f"${sum(r['sim_net'] for r in okr):+.2f} vs real ${sum(r['real_net'] for r in okr):+.2f} "
                  f"= +${bias:.3f}/trade OPTIMISTIC bias")
            print(f"  bias-corrected: occupancy-realistic ${corr_occ:+.2f}, all-covered ${corr_all:+.2f}")
        print(f"  -> {verdict}")

    out = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "question": "main-bot PostOnly entry misses: dodged losers or missed winners?",
        "method": {
            "extraction": "runtime parse of logs/bot.log(.1-.5): unique [MAKER] Limit order ids "
                          "paired with [FILL]/[FILL MISS]; origin main vs slot decided by the "
                          "attributable line after the outcome ([ENTRY]/Order FAILED/partial-fill "
                          "= main; [SLOT LIVE] = slot, excluded); ANSI duplicates deduped",
            "exit_model": "st2_lab.exit_replay._simulate variant=True (SL/TP + trail + breakeven), "
                          "mean_revert_replay conventions; matches live main-bot geometry "
                          "(flat 1.2/1.6 + hard240 verified on real Position-opened lines)",
            "params": PARAMS, "notional": NOTIONAL,
            "fees_pct": {"maker": MAKER_FEE, "taker": TAKER_FEE,
                         "rule": "maker entry; taker exit on stop_loss/trailing_stop/catastrophe, maker on TP/hold"},
            "path": "1m OHLCV two points per bar, adverse extreme first (pessimistic)",
            "entry_assumption": "miss fills at the intended [MAKER] Limit price at placement time (optimistic)",
            "partial_tp_note": "main-bot partial-TP at +10% ROI (live since 6/19) NOT modeled; "
                               "bias direction ambiguous, second-order (see script header)",
            "tz_map": f"ET (UTC-4) until the in-file ~3h backward jump [{flip}], PT (UTC-7) after; "
                      f"post-jump local {TZ_FLIP_HINT}",
            "tz_anchors_verified": {d: f"UTC{o:+d}" for d, o in sorted(anchors.items())},
            "occupancy": f"MAX_OPEN_TRADES={MAX_OPEN} + 1-per-symbol enforced in a chronological "
                         "sweep against real state-file positions + earlier counterfactuals",
            "log_coverage_local": f"{span[0]} -> {span[1]}",
        },
        "attempt_stats": {
            "main_attempts": len(main_att), "main_fills": len(fills),
            "main_partial_fill_skips": len(partial_skips), "main_misses": len(misses),
            "fill_rate_pct": round(100 * len(fills) / denom, 1) if denom else None,
            "slot_attempts_excluded": len(slot_att), "unattributed_excluded": len(unknown),
        },
        "sanity_fills": sanity_rows,
        "misses": miss_rows,
        "totals": {"all_covered": t_all, "occupancy_realistic": t_occ,
                   "blocked_by_occupancy": n_blocked,
                   "partial_excluded": len(partial), "uncovered": len(unc)},
        "sanity_calibration": {
            "matched_fills": len(sanity_rows), "covered": len(okr),
            "sign_agreement": (f"{sum(1 for r in okr if (r['sim_net'] > 0) == (r['real_net'] > 0))}"
                               f"/{len(okr)}") if okr else None,
            "sim_total": round(sum(r["sim_net"] for r in okr), 2) if okr else None,
            "real_total": round(sum(r["real_net"] for r in okr), 2) if okr else None,
            "optimism_bias_per_trade": round(bias, 4) if bias is not None else None,
            "bias_corrected_totals": {"occupancy_realistic": corr_occ, "all_covered": corr_all},
            "note": "sim runs optimistic vs recorded reality — read miss totals as upper bounds",
        },
        "verdict": verdict,
        "caveat": "screening-grade anecdote; fill-at-intended-price optimistic; partial-TP unmodeled",
    }
    os.makedirs(os.path.dirname(args.dump_json), exist_ok=True)
    with open(args.dump_json, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(f"\n  dump: {args.dump_json}")


if __name__ == "__main__":
    main()
