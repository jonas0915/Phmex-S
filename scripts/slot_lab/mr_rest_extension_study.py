#!/usr/bin/env python3
"""5m_mean_revert REST-EXTENSION study — would 60/90/120s maker rest (vs live 45s)
have converted the PostOnly misses into entries, and are those marginal fills toxic?

THE DEFERRED LEVER (reference_fill_rate_research_2026-07-03.md): extending rest
duration was DOWNGRADED for the main bot (starts collecting back-of-queue toxic
fills) but left OPEN for this slot, whose misses are measured winners
(reports/mr_missed_fills.json: n=11, +$3.55, 9W/2L) and whose signal is reversion.

MISS INVENTORY (15 unique misses, no fabrication — every event cited):
  * OLD cohort (11): reports/mr_missed_fills.json "misses" — hand-verified log
    extraction 2026-07-01 (raw June 18-23 lines since lost to rotation; the JSON
    is the surviving primary record). Actual rest then = 20s, no re-quote live.
  * NEW cohort (4): re-grepped this session from logs/bot.log(.1-.5)
    ("[MAKER] Limit" placement + "[FILL MISS]"/"[MR REQUOTE]" lines). July log
    local time = PT (UTC-7), anchored: XRP 7/7 fill opened_at=1783426912 =
    12:21:52 UTC = log line "2026-07-07 05:21:52".
  * 1 re-quote RESCUE (not a miss): XRP short 7/7 05:21 PT filled on re-quote,
    real net +$2.34 (trading_state_5m_mean_revert.json opened_at=1783426912).

METHOD (screening-grade, 1m OHLCV granularity — stated, not hidden):
  1. For each miss, fetch 1m OHLCV (ccxt Phemex public, limit=500 whitelist) from
     placement-2m to placement+4h30m.
  2. Fill detection at the ORIGINAL limit price under two rules:
       STRICT  = price traded THROUGH the limit (long: low < px; short: high > px)
                 -> a resting order at px MUST have filled (queue fully consumed).
       TOUCH   = price traded AT the limit (low <= px / high >= px) -> plausible
                 fill for an order with accrued queue position, not guaranteed.
     First crossing bar t_cross among bars overlapping/after placement gives a
     fill-delay BAND: delay_lo = max(t_cross - place, actual_rest) [live evidence:
     the order did NOT fill during its actual rest], delay_hi = t_cross+60 - place.
     For each rest horizon R in {60, 90, 120, 300}s:
       CERTAIN if delay_hi <= R; POSSIBLE if delay_lo <= R < delay_hi; else NO.
  3. Marginal fill = crossing NOT already captured by the live 45s config
     (delay_hi > 45). Each marginal fill is pushed through the SAME validated
     exit engine as the prior study (st2_lab.exit_replay._simulate variant=True,
     sl 1.2% / tp 1.6% / 4h hold, adverse-extreme-first 1m path, maker entry fee,
     taker exit fee on stop/trail) with entry_ts = t_cross (path starts next bar).
     Run at trail arm 5% (prior-study engine, apples-to-apples) AND 8% (live
     .env TRAIL_ARM_ROI since 7/5).
  4. Bootstrap CI on marginal-fill mean net: independent resample, 10k iters,
     2.5/97.5 percentiles (per feedback_bootstrap_diff_ci conventions).
  5. 2nd-requote variant (requote-era misses only, n=3): second chase at
     t2 = first_requote_place + 35s (observed wall-clock of the live requote
     cycle), touch PROXIED by the last completed 1m close before t2 (no
     historical L2 — coarse, flagged), drift-capped at
     Config.SLOT_REQUOTE_MAX_DRIFT_PCT=0.15% adverse vs the signal price
     (bot.py _requote_drift_pct), fill = STRICT trade-through of the proxy
     within (t2, t2+35].

HONESTY: n=15 misses is screening-grade anecdote. 1m bars cannot resolve
sub-minute timing — that is exactly why every fill carries a CERTAIN/POSSIBLE
band instead of a point claim. Backtests can only REJECT, never confirm
(reference_edge_hunt_exhaustion): a positive read = bounded live forward test.

Read-only vs live systems. Writes ONLY reports/mr_rest_extension.json.

Run from repo root:
    python scripts/slot_lab/mr_rest_extension_study.py
"""
from __future__ import annotations

import json
import os
import random
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

import backtest  # noqa: E402  (module global TRAIL_ARM_ROI drives _simulate's trail)
from mean_revert_replay import (  # noqa: E402
    _build_path, _net, PARAMS, NOTIONAL, MAKER_FEE, TAKER_FEE,
)
from st2_lab.exit_replay import _simulate  # noqa: E402

PT = timezone(timedelta(hours=-7))
HORIZONS = [60, 90, 120, 300]
LIVE_REST_S = 45.0            # bot.py:502 entry_patience_s
REQUOTE_DRIFT_CAP = 0.15      # config.py:78 SLOT_REQUOTE_MAX_DRIFT_PCT
BOOT_N = 10_000
RNG = random.Random(20260713)


def _ep(y, mo, d, h, mi, s):
    return int(datetime(y, mo, d, h, mi, s, tzinfo=PT).timestamp())


# ── NEW cohort: hand-verified from current logs (this session) ──────────────
# ts = [MAKER] Limit placement line, local PT -> epoch. rest_s = nominal patience
# the order actually rested (log "[FILL MISS] ... not filled in Xs").
NEW_MISSES = [
    dict(sym="LTC/USDT:USDT", side="short", px=42.85, rsi=75.3,
         ts=_ep(2026, 7, 2, 1, 49, 59), rest_s=20.0, rq_ts=None, rq_px=None,
         src="bot.log.3:30940 2026-07-02 01:49:59 [MAKER] Limit sell 2.33 LTC @ 42.85 "
             "(pre-45s/pre-requote era; FILL MISS 'in 20s' at 01:50:30)"),
    dict(sym="LTC/USDT:USDT", side="long", px=45.14, rsi=27.8,
         ts=_ep(2026, 7, 4, 12, 19, 30), rest_s=45.0,
         rq_ts=_ep(2026, 7, 4, 12, 20, 42), rq_px=45.15,
         src="bot.log.2:~18226 2026-07-04 12:19:30 [MAKER] Limit buy 3.32 LTC @ 45.14; "
             "requote @45.15 12:20:42 (drift +0.000%) also missed"),
    dict(sym="SOL/USDT:USDT", side="long", px=78.87, rsi=24.0,
         ts=_ep(2026, 7, 10, 6, 1, 40), rest_s=45.0,
         rq_ts=_ep(2026, 7, 10, 6, 2, 55), rq_px=78.93,
         src="bot.log.1:~89147 2026-07-10 06:01:40 [MAKER] Limit buy 1.9 SOL @ 78.87; "
             "requote @78.93 06:02:55 (drift +0.025%) also missed"),
    dict(sym="XRP/USDT:USDT", side="short", px=1.0936, rsi=70.2,
         ts=_ep(2026, 7, 12, 1, 14, 23), rest_s=45.0,
         rq_ts=_ep(2026, 7, 12, 1, 15, 36), rq_px=1.0936,
         src="bot.log:28994 2026-07-12 01:14:23 [MAKER] Limit sell 137.26 XRP @ 1.0936; "
             "requote @1.0936 01:15:36 (drift -0.073%) also missed"),
]

# The one real requote fill — context anchor, not simulated.
RESCUE = dict(sym="XRP/USDT:USDT", side="short", px=1.1293,
              ts=1783426912, real_net=2.3420681899999978,
              src="trading_state_5m_mean_revert.json opened_at=1783426912.9442282; "
                  "bot.log.2:90432 requote FILLED 2026-07-07 05:21:50")


def _load_old_misses():
    path = os.path.join(_BOT_DIR, "reports", "mr_missed_fills.json")
    with open(path) as fh:
        doc = json.load(fh)
    out = []
    for m in doc["misses"]:
        out.append(dict(sym=m["sym"], side=m["side"], px=m["px"], rsi=m.get("rsi"),
                        ts=int(m["ts"]), rest_s=20.0, rq_ts=None, rq_px=None,
                        overlap=m.get("overlap"), src=m["src"],
                        prior_sim_net=m.get("sim_net"), prior_sim_reason=m.get("sim_reason")))
    return out


def _fetch_1m(ex, sym, entry_ts):
    since = (entry_ts - 180) * 1000
    need_until = (entry_ts + PARAMS["hold_secs"] + 1800) * 1000
    rows, cursor = [], since
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


class OHLCVCache:
    def __init__(self, ex):
        self.ex = ex
        self.frames = {}  # sym -> list[df]

    def get(self, sym, entry_ts):
        for df in self.frames.get(sym, []):
            lo = int(df["ts"].iloc[0] // 1000)
            hi = int(df["ts"].iloc[-1] // 1000)
            if lo <= entry_ts - 60 and hi >= entry_ts + PARAMS["hold_secs"]:
                return df
        df = _fetch_1m(self.ex, sym, entry_ts)
        if df is not None:
            self.frames.setdefault(sym, []).append(df)
        return df


def _first_cross(df, place_ts, side, px, rule, rest_s=0.0):
    """First 1m crossing bar NOT refuted by live evidence.

    Live evidence: the order rested (place, place+rest_s] and did NOT fill. A
    strict trade-through during that window would HAVE filled it — so a crossing
    bar that ends inside the rest window proves the cross was pre-placement:
    SKIP it and keep searching. A crossing bar that extends past the rest window
    is kept; if it also covers pre-placement time (bar_start < place) the cross
    may have been before the order existed -> ambiguous=True (never CERTAIN).

    Returns (bar_start, bar_end, ambiguous) or None. Search capped +3600s."""
    for r in df.itertuples():
        bar_start = int(r.ts // 1000)
        bar_end = bar_start + 60
        if bar_end <= place_ts:              # bar entirely before placement
            continue
        if bar_start > place_ts + 3600:
            return None
        if side == "long":
            hit = (r.low < px) if rule == "strict" else (r.low <= px)
        else:
            hit = (r.high > px) if rule == "strict" else (r.high >= px)
        if not hit:
            continue
        if bar_end <= place_ts + rest_s:     # refuted: order rested through this
            continue                         # whole bar unfilled -> cross was pre-placement
        return bar_start, bar_end, bar_start < place_ts
    return None


def _classify(delay_lo, delay_hi, ambiguous, R):
    if delay_hi is None:
        return "NO"
    if delay_hi <= R and not ambiguous:
        return "CERTAIN"
    if delay_lo <= R:
        return "POSSIBLE"
    return "NO"


def _sim(sym, side, px, entry_ts, df, trail_arm):
    old = backtest.TRAIL_ARM_ROI
    backtest.TRAIL_ARM_ROI = trail_arm
    try:
        path = _build_path(df, entry_ts, PARAMS["hold_secs"], side)
        if not path:
            return None
        exit_px, reason, held = _simulate(sym, side, px, entry_ts, path, PARAMS, variant=True)
        net = _net(px, exit_px, side, reason, NOTIONAL, MAKER_FEE)
        return dict(exit=exit_px, reason=reason, held_s=int(held), net=round(net, 4))
    finally:
        backtest.TRAIL_ARM_ROI = old


def _boot_ci(nets):
    if not nets:
        return None
    means = []
    n = len(nets)
    for _ in range(BOOT_N):
        means.append(sum(RNG.choice(nets) for _ in range(n)) / n)
    means.sort()
    return [round(means[int(0.025 * BOOT_N)], 4), round(means[int(0.975 * BOOT_N)], 4)]


def _pt(ts):
    return datetime.fromtimestamp(ts, tz=PT).strftime("%b %-d %-I:%M:%S %p PT")


def main():
    ex = ccxt.phemex({"enableRateLimit": True})
    cache = OHLCVCache(ex)
    misses = _load_old_misses() + NEW_MISSES
    print(f"MR rest-extension study — {len(misses)} misses "
          f"(11 old cohort reports/mr_missed_fills.json + {len(NEW_MISSES)} new from logs)")
    print(f"engine: sl {PARAMS['sl_pct']}% / tp {PARAMS['tp_pct']}% / hold {PARAMS['hold_secs']}s, "
          f"maker {MAKER_FEE}% entry, taker {TAKER_FEE}% stop/trail exit, notional ${NOTIONAL:.0f}")

    rows = []
    for m in misses:
        df = cache.get(m["sym"], m["ts"])
        rec = dict(m)
        if df is None:
            rec["status"] = "UNCOVERED"
            rows.append(rec)
            print(f"  {m['sym']} {_pt(m['ts'])} UNCOVERED — no OHLCV")
            continue
        rec["status"] = "OK"
        for rule in ("strict", "touch"):
            hit = _first_cross(df, m["ts"], m["side"], m["px"], rule, m["rest_s"])
            if hit is None:
                rec[f"{rule}_delay"] = None
                rec[f"{rule}_class"] = {str(R): "NO" for R in HORIZONS}
                continue
            bar_start, bar_end, amb = hit
            delay_lo = max(bar_start - m["ts"], m["rest_s"])
            delay_hi = bar_end - m["ts"]
            rec[f"{rule}_delay"] = [int(delay_lo), int(delay_hi)]
            rec[f"{rule}_ambiguous_pre_placement"] = amb
            rec[f"{rule}_class"] = {str(R): _classify(delay_lo, delay_hi, amb, R)
                                    for R in HORIZONS}
            if rule == "strict":
                rec["captured_by_live_45s"] = bool(delay_hi <= LIVE_REST_S and not amb)
                for arm, key in ((5.0, "sim_arm5"), (8.0, "sim_arm8")):
                    rec[key] = _sim(m["sym"], m["side"], m["px"], bar_start, df, arm)
                rec["strict_cross_ts"] = bar_start
        rows.append(rec)
        d = rec.get("strict_delay")
        s5 = rec.get("sim_arm5")
        amb_tag = " AMB(pre-place?)" if rec.get("strict_ambiguous_pre_placement") else ""
        print(f"  {_pt(m['ts']):>24s} {m['sym'].split('/')[0]:5s} {m['side']:5s} px {m['px']:<9g} "
              f"rest {int(m['rest_s'])}s | strict-cross delay "
              f"{('%d-%ds' % tuple(d)) if d else 'NONE(<=1h)'}{amb_tag} | "
              + (f"net(arm5) ${s5['net']:+.3f} ({s5['reason']})" if s5 else "no sim"))

    ok = [r for r in rows if r["status"] == "OK"]

    # ── fill-conversion table ──
    print("\n--- FILL CONVERSION vs live 45s (strict trade-through / touch rule) ---")
    conv = {}
    for R in HORIZONS:
        sc = sum(1 for r in ok if r["strict_class"][str(R)] == "CERTAIN")
        sp = sum(1 for r in ok if r["strict_class"][str(R)] == "POSSIBLE")
        tc = sum(1 for r in ok if r["touch_class"][str(R)] == "CERTAIN")
        tp_ = sum(1 for r in ok if r["touch_class"][str(R)] == "POSSIBLE")
        conv[str(R)] = dict(strict_certain=sc, strict_possible=sp,
                            touch_certain=tc, touch_possible=tp_, n=len(ok))
        print(f"  rest {R:>3d}s: strict {sc} certain +{sp} possible | "
              f"touch {tc} certain +{tp_} possible   (of {len(ok)})")

    # ── marginal-fill expectancy per horizon ──
    print("\n--- MARGINAL FILLS (strict crossing, NOT captured by live 45s) ---")
    agg = {}
    for R in HORIZONS:
        marg = [r for r in ok
                if r["strict_class"][str(R)] in ("CERTAIN", "POSSIBLE")
                and not r.get("captured_by_live_45s")]
        res = {}
        for key in ("sim_arm5", "sim_arm8"):
            nets = [r[key]["net"] for r in marg if r.get(key)]
            wins = sum(1 for x in nets if x > 0)
            res[key] = dict(n=len(nets), net=round(sum(nets), 4),
                            wins=wins, losses=len(nets) - wins,
                            avg=round(sum(nets) / len(nets), 4) if nets else None,
                            boot_ci_mean=_boot_ci(nets))
        agg[str(R)] = dict(events=[f"{r['sym']} {_pt(r['ts'])}" for r in marg], **res)
        a5 = res["sim_arm5"]
        print(f"  rest {R:>3d}s: n={a5['n']}  net ${a5['net']:+.2f}  W/L {a5['wins']}/{a5['losses']}"
              f"  avg ${a5['avg'] if a5['avg'] is not None else 0:+.3f}  CI(mean) {a5['boot_ci_mean']}"
              f"   [arm8: net ${res['sim_arm8']['net']:+.2f}, CI {res['sim_arm8']['boot_ci_mean']}]")

    # ── 2nd requote variant ──
    print("\n--- 2nd RE-QUOTE variant (requote-era misses, touch proxied by 1m close — COARSE) ---")
    rq_rows = []
    for m in NEW_MISSES:
        if not m.get("rq_ts"):
            continue
        df = cache.get(m["sym"], m["ts"])
        if df is None:
            continue
        t2 = m["rq_ts"] + 35
        prior = df[(df["ts"] // 1000 + 60) <= t2]
        if prior.empty:
            continue
        proxy_touch = float(prior["close"].iloc[-1])
        raw = (proxy_touch - m["px"]) / m["px"] * 100
        drift = raw if m["side"] == "long" else -raw
        entry = dict(sym=m["sym"], ts_2nd=t2, proxy_touch=proxy_touch,
                     drift_vs_signal_pct=round(drift, 4))
        if drift > REQUOTE_DRIFT_CAP:
            entry["outcome"] = f"ABORT — adverse drift {drift:.3f}% > {REQUOTE_DRIFT_CAP}% cap"
        else:
            hit = _first_cross(df, t2, m["side"], proxy_touch, "strict", 0.0)
            filled = hit is not None and hit[0] <= t2 + 35
            if filled:
                sim = _sim(m["sym"], m["side"], proxy_touch, hit[0], df, 5.0)
                entry["outcome"] = "FILL (bar-overlap, coarse)"
                entry["sim_arm5"] = sim
            else:
                entry["outcome"] = "still no fill in 35s window"
        rq_rows.append(entry)
        print(f"  {m['sym'].split('/')[0]:5s} {_pt(t2)}: proxy touch {proxy_touch:g} "
              f"(drift {drift:+.3f}%) -> {entry['outcome']}"
              + (f"  net ${entry['sim_arm5']['net']:+.3f} ({entry['sim_arm5']['reason']})"
                 if entry.get("sim_arm5") else ""))
    print(f"  (context: the ONE real requote fill, XRP 7/7 5:21 AM PT, netted "
          f"${RESCUE['real_net']:+.2f} — {RESCUE['src']})")

    out = dict(
        generated_utc=datetime.now(timezone.utc).isoformat(),
        method="see script header — scripts/slot_lab/mr_rest_extension_study.py",
        horizons_s=HORIZONS, live_rest_s=LIVE_REST_S,
        requote_drift_cap_pct=REQUOTE_DRIFT_CAP,
        miss_rows=rows, fill_conversion=conv, marginal_fill_expectancy=agg,
        second_requote=rq_rows, rescue_real=RESCUE,
        caveat="n=15 misses, 1m-bar granularity (CERTAIN/POSSIBLE bands), "
               "screening-grade; positive read = forward-test candidate only",
    )
    dump = os.path.join(_BOT_DIR, "reports", "mr_rest_extension.json")
    with open(dump, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(f"\n  dump: {dump}")


if __name__ == "__main__":
    main()
