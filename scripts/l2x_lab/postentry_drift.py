#!/usr/bin/env python3
"""Post-entry drift measurement for htf_l2_anticipation REAL closed trades. v2.

THE L2X CRUX QUESTION (2026-07-01 research): after an htf_l2 entry, does price
CONTINUE in the trade's direction or REVERT? And conditional on being underwater
at time t, would cutting the loser have beaten holding to the actual exit?

v2 incorporates the 2026-07-01 four-agent verification pass:
- EXCLUDES 18 `min_margin_skip` phantom rows (orders never held; net_pnl==0,
  duration<60s) -> n=148 real fills.
- Cache windows are length-validated and refetched if truncated (a truncated
  ETH window from the v1 run was permanently cached); forming candles dropped.
- NULL BASE RATE added: %-recover-to-entry alone is a base-rate illusion (any
  checkpoint price gets touched again 78-93% of the time from volatility);
  recovery must be read AGAINST the unconditional favorable-excursion rate.
- HOLD-vs-CUT counterfactual added (the exit-design instrument): actual
  realized net_pnl vs cutting at the checkpoint price with taker fees, on
  trades still open at the checkpoint.
- Conditional cells report median + %>0 (means are outlier-dominated at 240m);
  9 nested uncorrected cells -> no single-cell CI is citable on its own.
- Cluster (per-UTC-day block) bootstrap CI added beside the iid CI: entries
  cluster in time and 240m windows overlap, so iid CIs are too narrow.

READ-ONLY vs the bot: reads trading_state.json, fetches public 1m OHLCV windows
from Phemex via ccxt (cached in reports/cache_l2x_drift/), writes report JSON to
reports/. No bot files touched, no restart needed.

Measurement notes:
- Drift is measured on the MARKET price path from the actual fill price
  (entry_price), independent of when the trade closed. Signed: + = moves WITH
  the trade (continuation), - = moves against (reversion).
- Price at horizon h = open of the 1m candle containing (entry_ts + h); timing
  precision +/-60s, fine for horizons >= 5m, coarse-ish at 1-2m.
- Bootstrap CIs (percentile, 10k resamples, fixed seed). SCREENING-GRADE per
  edge-hunt-exhaustion rules — can kill or motivate a hypothesis, not confirm
  an edge.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
STATE_FILE = REPO / "trading_state.json"
CACHE_DIR = REPO / "reports" / "cache_l2x_drift"
OUT_FILE = REPO / "reports" / "l2x_postentry_drift.json"

HORIZONS_MIN = [1, 2, 5, 15, 30, 60, 120, 240]
CHECKPOINTS_MIN = [5, 15, 30]          # "underwater at t" checkpoints
ADVERSE_BPS = [10, 20, 30]             # underwater-by-at-least thresholds
FINAL_MIN = 240                        # forward horizon for conditionals
PRE_PAD_MIN = 3                        # candles fetched before entry
POST_PAD_MIN = FINAL_MIN + 6
FETCH_LIMIT = PRE_PAD_MIN + POST_PAD_MIN + 2
TAKER_FEE = 0.0006                     # Phemex taker, per side
BOOT_N = 10_000
SEED = 42


def load_trades():
    state = json.loads(STATE_FILE.read_text())
    out, phantoms = [], 0
    for t in state.get("closed_trades", []):
        if t.get("strategy") != "htf_l2_anticipation":
            continue
        if not t.get("opened_at") or not t.get("entry_price"):
            continue
        if t.get("side") not in ("long", "short"):
            continue
        if (t.get("exit_reason") or t.get("reason")) == "min_margin_skip":
            phantoms += 1          # order skipped, position never held
            continue
        out.append(t)
    return out, phantoms


def cache_path(symbol, entry_min_ts):
    sym = symbol.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{sym}_{entry_min_ts}.json"


def window_complete(candles, entry_min_ts):
    """Full window = last candle start reaches entry_min + (POST_PAD+1) min."""
    if not candles:
        return False
    last_start = int(candles[-1][0] // 1000)
    return last_start >= entry_min_ts + (POST_PAD_MIN + 1) * 60


def fetch_window(exchange, symbol, entry_ts):
    """1m candles from PRE_PAD before entry to POST_PAD after. Cached.

    Truncated cache entries are refetched once more candles can exist;
    the forming (incomplete) candle is never cached.
    """
    entry_min_ts = int(entry_ts // 60) * 60
    cp = cache_path(symbol, entry_min_ts)
    now = time.time()
    if cp.exists():
        candles = json.loads(cp.read_text())
        more_may_exist = (candles and
                          now - 120 > int(candles[-1][0] // 1000))
        if window_complete(candles, entry_min_ts) or not more_may_exist:
            return candles
        if exchange is None:
            return candles
    if exchange is None:
        return None
    since_ms = (entry_min_ts - PRE_PAD_MIN * 60) * 1000
    candles = exchange.fetch_ohlcv(symbol, "1m", since=since_ms,
                                   limit=FETCH_LIMIT)
    candles = [c for c in candles if c[0] // 1000 <= now - 60]  # drop forming
    cp.write_text(json.dumps(candles))
    return candles


def index_candles(candles):
    return {int(c[0] // 1000): c for c in candles if c and c[1] is not None}


def signed_bps(entry_price, price, side):
    raw = (price - entry_price) / entry_price * 1e4
    return raw if side == "long" else -raw


def price_at(by_min, entry_ts, minutes):
    """Open of the 1m candle containing entry_ts + minutes. None if missing."""
    target = entry_ts + minutes * 60
    key = int(target // 60) * 60
    c = by_min.get(key)
    return c[1] if c else None


def extremes_between(by_min, entry_ts, t0_min, t1_min):
    """(max_high, min_low) over candles covering (entry+t0, entry+t1]."""
    k0 = int((entry_ts + t0_min * 60) // 60) * 60
    k1 = int((entry_ts + t1_min * 60) // 60) * 60
    highs, lows = [], []
    for k in range(k0 + 60, k1 + 60, 60):
        c = by_min.get(k)
        if c:
            highs.append(c[2])
            lows.append(c[3])
    if not highs:
        return None, None
    return max(highs), min(lows)


def boot_ci(values, n_boot=BOOT_N, seed=SEED):
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n_boot, len(arr)))
    means = arr[idx].mean(axis=1)
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def cluster_boot_ci(values, clusters, n_boot=BOOT_N, seed=SEED):
    """Block bootstrap: resample whole clusters (UTC days) with replacement."""
    groups = defaultdict(list)
    for v, c in zip(values, clusters):
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            groups[c].append(v)
    keys = sorted(groups)
    if len(keys) < 3:
        return None
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), size=len(keys))
        sample = [v for i in pick for v in groups[keys[i]]]
        means.append(float(np.mean(sample)))
    return [float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true",
                    help="cache-only; skip trades without cached windows")
    args = ap.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    trades, phantoms = load_trades()
    print(f"htf_l2 closed trades usable: {len(trades)} "
          f"(excluded {phantoms} min_margin_skip phantoms)")

    exchange = None
    if not args.no_fetch:
        import ccxt
        exchange = ccxt.phemex({"enableRateLimit": True})

    rows, uncovered = [], []
    windows = {}                       # row index -> by_min candle index
    now = time.time()
    for i, t in enumerate(trades):
        sym, side = t["symbol"], t["side"]
        entry_ts = float(t["opened_at"])
        entry_price = float(t["entry_price"])
        try:
            candles = fetch_window(exchange, sym, entry_ts)
        except Exception as e:
            uncovered.append((sym, entry_ts, f"fetch error: {e}"))
            continue
        if not candles:
            uncovered.append((sym, entry_ts, "no cache"))
            continue
        by_min = index_candles(candles)
        entry_key = int(entry_ts // 60) * 60
        ec = by_min.get(entry_key)
        if ec is None:
            uncovered.append((sym, entry_ts, "no entry candle"))
            continue

        join_bps = abs(entry_price - ec[1]) / entry_price * 1e4
        in_range = ec[3] * 0.999 <= entry_price <= ec[2] * 1.001

        row = {
            "symbol": sym, "side": side, "entry_ts": entry_ts,
            "entry_price": entry_price, "amount": t.get("amount"),
            "net_pnl": t.get("net_pnl"), "pnl_usdt": t.get("pnl_usdt"),
            "fees_usdt": t.get("fees_usdt"),
            "exit_reason": t.get("exit_reason") or t.get("reason"),
            "duration_s": t.get("duration_s"),
            "day": time.strftime("%Y-%m-%d", time.gmtime(entry_ts)),
            "join_bps": round(join_bps, 2), "entry_in_candle_range": in_range,
            "drift": {}, "mae": {}, "mfe": {},
        }
        for h in HORIZONS_MIN:
            if entry_ts + h * 60 > now - 60:
                row["drift"][str(h)] = None
                continue
            p = price_at(by_min, entry_ts, h)
            row["drift"][str(h)] = (
                round(signed_bps(entry_price, p, side), 2) if p else None)
        for h in CHECKPOINTS_MIN + [FINAL_MIN]:
            hi, lo = extremes_between(by_min, entry_ts, 0, h)
            if hi is None or entry_ts + h * 60 > now - 60:
                row["mae"][str(h)] = row["mfe"][str(h)] = None
                continue
            worst = lo if side == "long" else hi
            best = hi if side == "long" else lo
            row["mae"][str(h)] = round(signed_bps(entry_price, worst, side), 2)
            row["mfe"][str(h)] = round(signed_bps(entry_price, best, side), 2)
        windows[len(rows)] = by_min
        rows.append(row)
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(trades)} processed")

    print(f"covered: {len(rows)}   uncovered: {len(uncovered)}")
    if uncovered:
        reasons = {}
        for _, _, r in uncovered:
            reasons[r.split(":")[0]] = reasons.get(r.split(":")[0], 0) + 1
        print(f"  uncovered reasons: {reasons}")

    joins = [r["join_bps"] for r in rows]
    print(f"\nJOIN SANITY: median |entry - candle open| = "
          f"{np.median(joins):.1f} bps, p90 = {np.percentile(joins, 90):.1f} bps, "
          f"in-range: {sum(r['entry_in_candle_range'] for r in rows)}/{len(rows)}")

    # ---- unconditional drift curve (iid CI + per-day cluster CI) ----
    summary = {"n_trades": len(rows), "phantoms_excluded": phantoms,
               "horizons": {}}
    print("\nUNCONDITIONAL POST-ENTRY DRIFT (+ = with trade / continuation)")
    print(f"{'h':>5} {'n':>4} {'mean':>8} {'median':>8} {'%>0':>6}"
          f"  {'iid 95% CI':>18}  {'day-cluster 95% CI':>20}")
    for h in HORIZONS_MIN:
        pairs = [(r["drift"][str(h)], r["day"]) for r in rows
                 if r["drift"][str(h)] is not None]
        if len(pairs) < 3:
            continue
        vals = [p[0] for p in pairs]
        ci = boot_ci(vals)
        cci = cluster_boot_ci(vals, [p[1] for p in pairs])
        arr = np.asarray(vals)
        summary["horizons"][str(h)] = {
            "n": len(vals), "mean_bps": round(float(arr.mean()), 2),
            "median_bps": round(float(np.median(arr)), 2),
            "pct_positive": round(float((arr > 0).mean() * 100), 1),
            "ci95_iid": [round(ci[0], 2), round(ci[1], 2)] if ci else None,
            "ci95_cluster": ([round(cci[0], 2), round(cci[1], 2)]
                             if cci else None),
        }
        s = summary["horizons"][str(h)]
        print(f"{h:>4}m {s['n']:>4} {s['mean_bps']:>8.2f} "
              f"{s['median_bps']:>8.2f} {s['pct_positive']:>5.1f}%"
              f"  [{s['ci95_iid'][0]:>7.2f},{s['ci95_iid'][1]:>7.2f}]"
              f"   [{s['ci95_cluster'][0]:>7.2f},{s['ci95_cluster'][1]:>7.2f}]")

    # ---- conditional: underwater at t -> subsequent path, vs NULL base rate --
    print("\nCONDITIONAL: trades adverse >= k bps at checkpoint t")
    print("  subsequent = drift(240m) - drift(t); + = back toward entry.")
    print("  %recover = touched entry again in (t,240]. base_rate = "
          "unconditional %% of ALL trades with a >=k bps favorable excursion "
          "from their OWN price at t (volatility null).")
    print(f"{'t':>5} {'k':>4} {'n':>4} {'med subs':>9} {'%subs>0':>8} "
          f"{'%recover':>9} {'base_rate':>10}")
    summary["conditional"] = []
    for t_min in CHECKPOINTS_MIN:
        # null: favorable excursion >= k bps from price at t, all trades
        null_hits = {k: [] for k in ADVERSE_BPS}
        for ridx, r in enumerate(rows):
            by_min = windows[ridx]
            p_t = price_at(by_min, r["entry_ts"], t_min)
            d_f = r["drift"].get(str(FINAL_MIN))
            if p_t is None or d_f is None:
                continue
            hi, lo = extremes_between(by_min, r["entry_ts"], t_min, FINAL_MIN)
            if hi is None:
                continue
            best = hi if r["side"] == "long" else lo
            exc = signed_bps(p_t, best, r["side"])
            for k in ADVERSE_BPS:
                null_hits[k].append(1.0 if exc >= k else 0.0)

        for k in ADVERSE_BPS:
            subs, recov = [], []
            for ridx, r in enumerate(rows):
                d_t = r["drift"].get(str(t_min))
                d_f = r["drift"].get(str(FINAL_MIN))
                if d_t is None or d_f is None or d_t > -k:
                    continue
                subs.append(d_f - d_t)
                hi, lo = extremes_between(windows[ridx], r["entry_ts"],
                                          t_min, FINAL_MIN)
                if hi is None:
                    recov.append(np.nan)
                else:
                    best = hi if r["side"] == "long" else lo
                    recov.append(
                        1.0 if signed_bps(r["entry_price"], best,
                                          r["side"]) >= 0 else 0.0)
            base = (float(np.mean(null_hits[k])) * 100
                    if null_hits[k] else float("nan"))
            if len(subs) < 3:
                summary["conditional"].append(
                    {"t_min": t_min, "k_bps": k, "n": len(subs),
                     "note": "n too small"})
                continue
            arr = np.asarray(subs)
            rec = float(np.nanmean(recov)) * 100 if recov else float("nan")
            entry = {"t_min": t_min, "k_bps": k, "n": len(subs),
                     "subsequent_median_bps": round(float(np.median(arr)), 2),
                     "subsequent_mean_bps": round(float(arr.mean()), 2),
                     "pct_subsequent_positive":
                         round(float((arr > 0).mean() * 100), 1),
                     "pct_recover_to_entry": round(rec, 1),
                     "null_base_rate_pct": round(base, 1)}
            summary["conditional"].append(entry)
            print(f"{t_min:>4}m {k:>4} {len(subs):>4} "
                  f"{entry['subsequent_median_bps']:>9.2f} "
                  f"{entry['pct_subsequent_positive']:>7.1f}% "
                  f"{entry['pct_recover_to_entry']:>8.1f}% "
                  f"{entry['null_base_rate_pct']:>9.1f}%")

    # ---- HOLD vs CUT counterfactual (the exit-design instrument) ----
    # For trades still OPEN at checkpoint t and adverse >= k bps: compare
    # actual realized net_pnl (hold) vs closing at the checkpoint price with a
    # taker exit. Cut branch: gross at checkpoint - entry fee (approximated as
    # fees_usdt/2 when recorded, else taker) - taker exit fee.
    print("\nHOLD vs CUT counterfactual (trades still open at t, adverse >= k)")
    print(f"{'t':>5} {'k':>4} {'n':>4} {'hold mean $':>12} {'cut mean $':>11} "
          f"{'hold-cut $':>11}  winner")
    summary["hold_vs_cut"] = []
    for t_min in CHECKPOINTS_MIN:
        for k in ADVERSE_BPS:
            holds, cuts = [], []
            for r in rows:
                d_t = r["drift"].get(str(t_min))
                if (d_t is None or d_t > -k or r.get("net_pnl") is None
                        or not r.get("amount")
                        or (r.get("duration_s") or 0) <= t_min * 60):
                    continue
                notional = float(r["amount"]) * r["entry_price"]
                gross_cut = d_t / 1e4 * notional
                fees = r.get("fees_usdt")
                entry_fee = (fees / 2 if fees else TAKER_FEE * notional)
                cut_net = gross_cut - entry_fee - TAKER_FEE * notional
                holds.append(float(r["net_pnl"]))
                cuts.append(cut_net)
            if len(holds) < 3:
                summary["hold_vs_cut"].append(
                    {"t_min": t_min, "k_bps": k, "n": len(holds),
                     "note": "n too small"})
                continue
            hm, cm = float(np.mean(holds)), float(np.mean(cuts))
            diff = [h - c for h, c in zip(holds, cuts)]
            ci = boot_ci(diff)          # paired within-trade difference
            entry = {"t_min": t_min, "k_bps": k, "n": len(holds),
                     "hold_mean_usd": round(hm, 3),
                     "cut_mean_usd": round(cm, 3),
                     "hold_minus_cut_usd": round(hm - cm, 3),
                     "diff_ci95": ([round(ci[0], 3), round(ci[1], 3)]
                                   if ci else None)}
            summary["hold_vs_cut"].append(entry)
            print(f"{t_min:>4}m {k:>4} {len(holds):>4} {hm:>12.3f} "
                  f"{cm:>11.3f} {hm - cm:>11.3f}  "
                  f"{'HOLD' if hm > cm else 'CUT'}")

    # ---- winners vs losers drift (descriptive; outcome-conditioning caveat) --
    print("\nWINNERS vs LOSERS early drift (net_pnl sign; descriptive only — "
          "partly circular, net_pnl carries the known fee-ledger bug)")
    summary["w_vs_l"] = {}
    for h in [5, 15, 30, 60]:
        w = [r["drift"][str(h)] for r in rows
             if r["drift"][str(h)] is not None and (r.get("net_pnl") or 0) > 0]
        l = [r["drift"][str(h)] for r in rows
             if r["drift"][str(h)] is not None and (r.get("net_pnl") or 0) <= 0]
        if len(w) >= 3 and len(l) >= 3:
            summary["w_vs_l"][str(h)] = {
                "winners_mean": round(float(np.mean(w)), 2), "n_w": len(w),
                "losers_mean": round(float(np.mean(l)), 2), "n_l": len(l)}
            s = summary["w_vs_l"][str(h)]
            print(f"{h:>4}m  winners {s['winners_mean']:>8.2f} (n={s['n_w']})   "
                  f"losers {s['losers_mean']:>8.2f} (n={s['n_l']})")

    OUT_FILE.write_text(json.dumps(
        {"summary": summary, "trades": rows,
         "uncovered": [{"symbol": s, "entry_ts": ts, "reason": r}
                       for s, ts, r in uncovered]}, indent=1))
    print(f"\nwrote {OUT_FILE}")


if __name__ == "__main__":
    sys.exit(main())
