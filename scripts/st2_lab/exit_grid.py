#!/usr/bin/env python3
"""ST2.0 exit-geometry DEEP GRID on n=35 real live trades.

Builds on exit_replay.py. Reconstructs each real trade's forward price path from
flow_capture.jsonl and:
  (1) computes MFE/MAE distribution + 'ever positive intraday' count,
  (2) grids exit variants (trailing / breakeven / partial / time-stop /
      tighter-or-wider fixed SL+TP) and reports net delta vs reconstructed
      baseline AND projected-to-actual,
  (3) isolates the tighter-stop symmetric tradeoff (caps winners vs saves losers).

HONESTY: flow_capture samples ~80s apart, so MAE/MFE are LOWER BOUNDS (true
intra-sample excursions are missed) and the reconstructed baseline (SL detection)
differs from realized. The robust quantity is the per-trade DELTA on identical
paths. We also project deltas onto the ACTUAL realized total as a sanity anchor.
peak_price is uninitialized for ST2.0 (==entry for all 7 present) -> unusable.
"""
from __future__ import annotations
import bisect, json, os, sys, statistics
from collections import Counter

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BOT_DIR); sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
from st2_lab import config as C
from st2_lab import dataset as DS

LEV = 10
MAKER = 0.02   # % per side
TAKER = 0.06   # % per side (stops)
PATH_LOOKAHEAD = 120  # records after entry (~120*80s ~ 2.6h >> any hold tested)


def load_live():
    d = json.load(open(os.path.join(C.BOT_DIR, "trading_state_ST2.0.json")))
    out = []
    for t in d.get("closed_trades", []):
        if t.get("mode") != "live":
            continue
        e = t.get("entry_price") or t.get("entry")
        if not e:
            continue
        out.append(t)
    return out


def fwd_path(recs, ts_list, entry_ts):
    i = bisect.bisect_right(ts_list, entry_ts)
    return recs[i:i + PATH_LOOKAHEAD]


def build():
    by_sym = DS.load_dataset()
    ts_idx = {s: [r["ts"] for r in recs] for s, recs in by_sym.items()}
    live = load_live()
    trades = []
    no_path = 0
    for t in live:
        sym = t["symbol"]; recs = by_sym.get(sym)
        e = t.get("entry_price") or t.get("entry")
        ets = int(t.get("opened_at") or 0)
        amt = float(t.get("amount", 0) or 0)
        margin = float(t.get("margin", 0) or 0) or C.MARGIN_USDT
        notional = (amt * e) if amt else margin * LEV
        path = fwd_path(recs, ts_idx[sym], ets) if recs else []
        trades.append({
            "sym": sym.split("/")[0], "side": t.get("side", "short"),
            "entry": e, "exit": t.get("exit_price"), "ets": ets,
            "dur": float(t.get("duration_s") or 0), "notional": notional,
            "margin": margin, "net": float(t.get("net_pnl") or 0),
            "roi": float(t.get("pnl_pct") or 0), "reason": t.get("exit_reason"),
            "path": path,
        })
        if not path:
            no_path += 1
    return trades, no_path


def mfe_mae(tr):
    """Reconstructed favorable/adverse extremes (price% and ROI%) within actual hold."""
    e = tr["entry"]; side = tr["side"]; ets = tr["ets"]
    end = ets + max(tr["dur"], 1)
    pts = [(r["ts"], r["price"]) for r in tr["path"] if r["ts"] <= end]
    if not pts:
        return None
    lo = min(p for _, p in pts); hi = max(p for _, p in pts)
    if side == "short":
        fav = (e - lo) / e * 100      # favorable: price below entry
        adv = (e - hi) / e * 100      # adverse: price above entry (negative)
    else:
        fav = (hi - e) / e * 100
        adv = (lo - e) / e * 100
    return {"fav_px": fav, "adv_px": adv, "fav_roi": fav * LEV, "adv_roi": adv * LEV,
            "n_pts": len(pts), "ever_pos": fav > 0}


def net_pnl(entry, exit_px, side, notional, taker_exit):
    if side == "short":
        gross = (entry - exit_px) / entry * notional
    else:
        gross = (exit_px - entry) / entry * notional
    fee = notional * (MAKER + (TAKER if taker_exit else MAKER)) / 100.0
    return gross - fee


def sim_variant(tr, sl_pct, tp_pct, hold, trail_arm=None, trail_lock=None,
                be_arm=None, partial_at=None, partial_frac=0.5):
    """Walk forward path; return (net, reason). All ROI thresholds in ROI% (lev-scaled)."""
    e = tr["entry"]; side = tr["side"]; ets = tr["ets"]; notional = tr["notional"]
    sl = e * (1 + sl_pct / 100) if side == "short" else e * (1 - sl_pct / 100)
    tp = e * (1 - tp_pct / 100) if side == "short" else e * (1 + tp_pct / 100)
    cur_sl = sl
    realized = 0.0
    rem = 1.0  # remaining fraction
    best_roi = 0.0
    armed_trail = False
    for r in tr["path"]:
        ts, px = r["ts"], r["price"]
        held = ts - ets
        # current ROI on margin (favorable positive)
        if side == "short":
            move = (e - px) / e
        else:
            move = (px - e) / e
        roi = move * LEV * 100
        best_roi = max(best_roi, roi)
        # breakeven ratchet
        if be_arm is not None and roi >= be_arm:
            be = e  # move stop to entry (price terms)
            if side == "short":
                cur_sl = min(cur_sl, be)
            else:
                cur_sl = max(cur_sl, be)
        # trailing: once armed (roi>=trail_arm), lock trail_lock ROI behind best
        if trail_arm is not None and roi >= trail_arm:
            armed_trail = True
        if armed_trail and trail_lock is not None:
            lock_move = (best_roi - trail_lock) / LEV / 100  # price-move fraction locked
            if side == "short":
                tstop = e * (1 - lock_move)
                cur_sl = min(cur_sl, tstop)
            else:
                tstop = e * (1 + lock_move)
                cur_sl = max(cur_sl, tstop)
        # partial scale-out
        if partial_at is not None and rem == 1.0 and roi >= partial_at:
            realized += net_pnl(e, px, side, notional * partial_frac, taker_exit=False)
            rem -= partial_frac
        # stop / tp checks
        if side == "short":
            sl_hit, tp_hit = px >= cur_sl, px <= tp
        else:
            sl_hit, tp_hit = px <= cur_sl, px >= tp
        if sl_hit:
            taker = (cur_sl == sl)  # original hard stop = taker; trailed/be ~ maker-ish but treat stop as taker conservatively
            realized += net_pnl(e, cur_sl, side, notional * rem, taker_exit=True)
            rsn = "trail_stop" if armed_trail and cur_sl != sl else ("be_stop" if cur_sl == e else "stop_loss")
            return realized, rsn
        if tp_hit:
            realized += net_pnl(e, tp, side, notional * rem, taker_exit=False)
            return realized, "take_profit"
        if held >= hold:
            realized += net_pnl(e, px, side, notional * rem, taker_exit=False)
            return realized, "hold"
    if tr["path"]:
        last = tr["path"][-1]["price"]
        realized += net_pnl(e, last, side, notional * rem, taker_exit=False)
        return realized, "end_path"
    return 0.0, "no_path"


def summarize(trades, variant_fn, label, base_nets):
    nets, reasons = [], []
    for tr in trades:
        n, rsn = variant_fn(tr)
        nets.append(n); reasons.append(rsn)
    tot = sum(nets)
    deltas = [n - b for n, b in zip(nets, base_nets)]
    saved = sum(d for d, b in zip(deltas, base_nets) if b <= 0)
    clipped = sum(d for d, b in zip(deltas, base_nets) if b > 0)
    actual_proj = ACTUAL_TOTAL + sum(deltas)
    wr = sum(1 for n in nets if n > 0)
    return {"label": label, "recon_net": tot, "delta": sum(deltas),
            "saved": saved, "clipped": clipped, "actual_proj": actual_proj,
            "wr": wr, "reasons": Counter(reasons)}


ACTUAL_TOTAL = 0.0


def main():
    global ACTUAL_TOTAL
    trades, no_path = build()
    covered = [t for t in trades if t["path"]]
    ACTUAL_TOTAL = sum(t["net"] for t in trades)
    print(f"=== ST2.0 exit-geometry deep grid ===")
    print(f"live trades: {len(trades)} | with flow path: {len(covered)} | no path: {no_path}")
    print(f"ACTUAL realized net (all 35): ${ACTUAL_TOTAL:+.4f}")
    print(f"ACTUAL realized net (path-covered {len(covered)}): ${sum(t['net'] for t in covered):+.4f}")

    # ---- 1. MFE / MAE ----
    print("\n--- 1. MFE/MAE (reconstructed from flow path within actual hold; LOWER BOUNDS) ---")
    rows = []
    ever_pos = 0
    for t in covered:
        m = mfe_mae(t)
        if not m:
            continue
        rows.append((t, m))
        if m["ever_pos"]:
            ever_pos += 1
    favs = [m["fav_roi"] for _, m in rows]
    advs = [m["adv_roi"] for _, m in rows]
    print(f"trades with usable path points: {len(rows)}")
    print(f"EVER positive intraday (price moved in our favor at all): {ever_pos}/{len(rows)} ({ever_pos/len(rows)*100:.0f}%)")
    print(f"MFE ROI%  min/med/mean/max: {min(favs):.2f} / {statistics.median(favs):.2f} / {statistics.mean(favs):.2f} / {max(favs):.2f}")
    print(f"MAE ROI%  min/med/mean/max: {min(advs):.2f} / {statistics.median(advs):.2f} / {statistics.mean(advs):.2f} / {max(advs):.2f}")
    # how many reached various favorable ROI thresholds
    for thr in [2, 4, 5, 8, 10, 16]:
        c = sum(1 for f in favs if f >= thr)
        print(f"  reached +{thr:>2}% ROI favorable: {c}/{len(rows)}")
    # winners vs losers MFE/MAE split (by actual outcome)
    win_fav = [m["fav_roi"] for t, m in rows if t["net"] > 0]
    los_fav = [m["fav_roi"] for t, m in rows if t["net"] <= 0]
    win_adv = [m["adv_roi"] for t, m in rows if t["net"] > 0]
    los_adv = [m["adv_roi"] for t, m in rows if t["net"] <= 0]
    if win_fav and los_fav:
        print(f"  winners(n={len(win_fav)}) MFE mean {statistics.mean(win_fav):.2f}% | MAE mean {statistics.mean(win_adv):.2f}%")
        print(f"  losers (n={len(los_fav)}) MFE mean {statistics.mean(los_fav):.2f}% | MAE mean {statistics.mean(los_adv):.2f}%")

    # ---- baseline (live config) on reconstructed paths ----
    base_nets = [sim_variant(t, 1.2, 1.6, 900)[0] for t in covered]
    base_reasons = Counter(sim_variant(t, 1.2, 1.6, 900)[1] for t in covered)
    base_recon = sum(base_nets)
    print(f"\n--- baseline (SL1.2/TP1.6/hold900) reconstructed ---")
    print(f"recon net ${base_recon:+.4f} | reasons {dict(base_reasons)}")
    print(f"(vs ACTUAL path-covered ${sum(t['net'] for t in covered):+.4f} — gap = flow-cadence fidelity)")

    # ---- 2 + 3 + 4. variant grid ----
    variants = []
    # time-stop grid (hold)
    for h in [120, 300, 600, 900, 1200, 1800, 3600]:
        variants.append((f"time-stop hold={h}s", lambda t, h=h: sim_variant(t, 1.2, 1.6, h)))
    # tighter / wider fixed SL (TP fixed 1.6)
    for sl in [0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0]:
        variants.append((f"SL={sl}% (TP1.6,hold900)", lambda t, sl=sl: sim_variant(t, sl, 1.6, 900)))
    # tighter / wider TP (SL fixed 1.2)
    for tp in [0.6, 0.8, 1.0, 1.2, 1.6, 2.0, 3.0]:
        variants.append((f"TP={tp}% (SL1.2,hold900)", lambda t, tp=tp: sim_variant(t, 1.2, tp, 900)))
    # breakeven ratchet
    for ba in [4, 6, 8, 10]:
        variants.append((f"breakeven@+{ba}%ROI", lambda t, ba=ba: sim_variant(t, 1.2, 1.6, 900, be_arm=ba)))
    # trailing
    for arm, lock in [(5, 2), (4, 2), (8, 3), (6, 4), (10, 5), (4, 1)]:
        variants.append((f"trail arm{arm}/lock{lock}", lambda t, a=arm, l=lock: sim_variant(t, 1.2, 1.6, 900, trail_arm=a, trail_lock=l)))
    # partial scale-out
    for pa in [4, 6, 8, 10]:
        variants.append((f"partial 50%@+{pa}%ROI", lambda t, pa=pa: sim_variant(t, 1.2, 1.6, 900, partial_at=pa)))

    results = [summarize(covered, fn, lab, base_nets) for lab, fn in variants]
    results.sort(key=lambda r: -r["delta"])
    print("\n--- 2/3/4. EXIT VARIANT GRID (ranked by net delta vs reconstructed baseline) ---")
    print(f"{'variant':<28}{'recon_net':>11}{'delta':>9}{'saved':>9}{'clipped':>9}{'proj_actual':>13}{'wr':>6}")
    for r in results:
        print(f"{r['label']:<28}{r['recon_net']:>+11.3f}{r['delta']:>+9.3f}{r['saved']:>+9.3f}{r['clipped']:>+9.3f}{r['actual_proj']:>+13.3f}{r['wr']:>4}/{len(covered)}")
    print(f"\n{'BASELINE':<28}{base_recon:>+11.3f}{0.0:>+9.3f}{'':>9}{'':>9}{ACTUAL_TOTAL:>+13.3f}")


if __name__ == "__main__":
    main()
