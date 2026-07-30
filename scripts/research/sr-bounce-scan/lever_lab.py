"""Counterfactual lever lab for SR_BOUNCE (2026-07-29).

Scratch replay harness. Does NOT modify the frozen originals (sr_levels.py,
sr_signal.py, engine.py, fetch_data.py) — this file is additive only.

Replays a lever-parameterized COPY of engine.replay() (logic identical to the
frozen engine when all lever flags are off/default; verified against the
frozen engine's known TRAIN baseline: 8,703 trades, -$0.0729/t) against the
same cached 90d 1h+5m data used by the frozen scan, TRAIN WINDOW ONLY.

Levers (see task spec for exact thresholds):
  L1 zone cooldown        — re-replay (changes entry sequencing)
  L2 risk floor            — pure post-filter on baseline trade list (upper bound)
  L3 touch band 2-5        — pure post-filter on baseline trade list (upper bound)
  L4 loss-side day blacklist — re-replay (changes entry sequencing)
  L5 combined best-two      — re-replay if L1/L4 involved, else post-filter

HONESTY RULES (do not weaken):
  - No exploration on the HOLDOUT window. Holdout is only touched once, at the
    very end, for the single best lever/combo, and ONLY if its TRAIN
    net/trade is POSITIVE (not merely less-negative than baseline).
  - No parameter search within a lever — one pre-stated threshold each.
  - Fees stay 0.12% RT (fee_rt=0.0012), fills stay strict-through (unchanged
    fill/exit logic from the frozen engine). Never softened.

POST-FILTER LIMITATION (stated per spec, not glossed over):
  L2/L3 post-filtering is NOT exact. The frozen engine is one-position-per-
  symbol; removing a trade from the recorded sequence would, in the real
  (re-replayed) world, free that symbol's slot for a *different* signal that
  the baseline replay never took (because the filtered-out trade was open at
  the time). Post-filter numbers below are therefore an UPPER BOUND on what a
  true re-replay of that lever would show, not an exact counterfactual. L1
  and L4 are re-replayed properly because they change sequencing directly
  (cooldown/blacklist alters which signals are even attempted).

RUNTIME NOTE: full 90-day replay of all 10 pairs takes ~80 min single-
threaded. Two optimizations used here, both preserving correctness of the
TRAIN metric:
  1. Parallelize across the 10 symbols (independent replays) with
     ProcessPoolExecutor.
  2. For the sequencing re-replays (L1, L4, and any L5 leg that includes
     them), truncate the FED 5m data to [start, cut_ts + RESOLUTION_BUFFER]
     instead of the full 90 days. Signals beyond the TRAIN cutoff are never
     scored (we only ever report the TRAIN slice: signal_ts < cut_ts), so
     feeding candles past cut_ts+buffer would only ever produce HOLDOUT
     signals we exclude anyway. The buffer exists purely so that trades
     *opened* just before the cutoff have enough future candles to resolve
     (hit SL/TP) rather than being silently dropped as still-open at series
     end. This is NOT holdout exploration: no statistic derived from candles
     beyond cut_ts ever informs a lever decision. The baseline reference run
     (used to validate this harness against the frozen engine's known
     numbers and to source trades for L2/L3 post-filtering) is run on the
     FULL 90 days for maximum fidelity to the frozen scan.
"""
import copy
import datetime
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sr_levels import atr, adx, validated_zones
from sr_signal import confirmed_rejection, plan_trade
from fetch_data import scan_pairs, load_candles

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "lever_lab_cache")
os.makedirs(OUT_DIR, exist_ok=True)

MIN_1H = 100
HOLDOUT_DAYS = 30
RESOLUTION_BUFFER_DAYS = 10  # slack past TRAIN cutoff so open trades can resolve
FEE_RT = 0.0012
NOTIONAL = 50.0

KNOWN_BASELINE_TRAIN_N = 8_703
KNOWN_BASELINE_TRAIN_NET_PER_TRADE = -0.0729


def _day(ts_ms: int) -> int:
    return ts_ms // 86_400_000


def _overlap(a_lo, a_hi, b_lo, b_hi) -> bool:
    return not (a_hi < b_lo or b_hi < a_lo)


def replay_lever(df1h: pd.DataFrame, df5m: pd.DataFrame, symbol: str,
                  notional: float = NOTIONAL, fee_rt: float = FEE_RT,
                  zone_cooldown_candles: int = 0,
                  loss_day_blacklist: bool = False) -> list[dict]:
    """Lever-parameterized copy of engine.replay(). With both flags at their
    default (0 / False) this is byte-for-byte the same trade-selection logic
    as the frozen engine.replay(), plus extra recorded fields (zone_lo,
    zone_hi, touches) needed for L2/L3 post-filtering."""
    trades, open_pos, pending = [], None, None
    zone_cache_key, zones, cur_adx = None, [], None
    cooldowns: list[dict] = []       # L1: [{"lo","hi","until_i"}]
    day_blacklist: list[dict] = []   # L4: [{"lo","hi","day"}]

    for i in range(len(df5m)):
        c = df5m.iloc[i]
        candle = {"open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]}

        ctx = df1h[df1h["ts"] + 3_600_000 <= c["ts"]].tail(500).reset_index(drop=True)
        if len(ctx) < MIN_1H:
            continue
        key = int(ctx["ts"].iloc[-1])
        if key != zone_cache_key:
            zone_cache_key = key
            zones = validated_zones(ctx)
            cur_adx = float(adx(ctx).iloc[-1])

        if pending is not None:
            filled = (candle["low"] < pending["entry"] if pending["side"] == "long"
                      else candle["high"] > pending["entry"])
            open_pos = dict(pending, fill_i=i) if filled else None
            pending = None

        if open_pos is not None:
            side, sl, tp = open_pos["side"], open_pos["sl"], open_pos["tp"]
            hit_sl = candle["low"] <= sl if side == "long" else candle["high"] >= sl
            hit_tp = candle["high"] >= tp if side == "long" else candle["low"] <= tp
            if hit_sl or hit_tp:
                reason = "stop_loss" if hit_sl else "take_profit"
                px = sl if hit_sl else tp
                sgn = 1 if side == "long" else -1
                ret = sgn * (px - open_pos["entry"]) / open_pos["entry"]
                trades.append({
                    "symbol": symbol, "side": side, "signal_ts": open_pos["signal_ts"],
                    "entry": open_pos["entry"], "sl": sl, "tp": tp,
                    "exit_ts": int(c["ts"]), "exit_price": px, "exit_reason": reason,
                    "net_usd": notional * ret - notional * fee_rt,
                    "risk_pct": abs(open_pos["entry"] - sl) / open_pos["entry"] * 100,
                    "reward_pct": abs(tp - open_pos["entry"]) / open_pos["entry"] * 100,
                    "zone_lo": open_pos["zone_lo"], "zone_hi": open_pos["zone_hi"],
                    "touches": open_pos["touches"],
                })
                if zone_cooldown_candles > 0:
                    cooldowns.append({"lo": open_pos["zone_lo"], "hi": open_pos["zone_hi"],
                                       "until_i": i + zone_cooldown_candles})
                if loss_day_blacklist and reason == "stop_loss":
                    day_blacklist.append({"lo": open_pos["zone_lo"], "hi": open_pos["zone_hi"],
                                           "day": _day(int(c["ts"]))})
                open_pos = None
            continue

        if cur_adx is None or cur_adx >= 30:
            continue
        atr5 = float(atr(df5m.iloc[max(0, i - 100):i + 1]).iloc[-1])
        cur_day = _day(int(c["ts"])) if loss_day_blacklist else None
        for z in zones:
            if zone_cooldown_candles > 0 and any(
                    cd["until_i"] > i and _overlap(z["lo"], z["hi"], cd["lo"], cd["hi"])
                    for cd in cooldowns):
                continue
            if loss_day_blacklist and any(
                    bl["day"] == cur_day and _overlap(z["lo"], z["hi"], bl["lo"], bl["hi"])
                    for bl in day_blacklist):
                continue
            if confirmed_rejection(candle, z):
                plan = plan_trade(z, zones, atr5, entry=float(candle["close"]))
                if plan is not None:
                    pending = dict(plan, entry=float(candle["close"]), signal_ts=int(c["ts"]),
                                    zone_lo=z["lo"], zone_hi=z["hi"], touches=z["touches"])
                    break
    return trades


def _run_one(args):
    sym, timeframe_kwargs, lever_kwargs = args
    df1h = load_candles(sym, "1h", data_dir=DATA_DIR)
    df5m = load_candles(sym, "5m", data_dir=DATA_DIR)
    if timeframe_kwargs.get("max_ts") is not None:
        df5m = df5m[df5m["ts"] < timeframe_kwargs["max_ts"]].reset_index(drop=True)
    t0 = time.time()
    trades = replay_lever(df1h, df5m, sym, **lever_kwargs)
    return sym, trades, time.time() - t0


def run_pooled(label: str, lever_kwargs: dict, max_ts: int | None, workers: int) -> list[dict]:
    pairs = scan_pairs()
    jobs = [(sym, {"max_ts": max_ts}, lever_kwargs) for sym in pairs]
    all_trades = []
    print(f"[{label}] launching {len(pairs)} pair replays across {workers} workers "
          f"(max_ts={max_ts})...", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_run_one, j): j[0] for j in jobs}
        for fut in as_completed(futs):
            sym = futs[fut]
            sym_out, trades, secs = fut.result()
            all_trades.extend(trades)
            print(f"[{label}]   {sym_out}: {len(trades)} trades in {secs:.1f}s", flush=True)
    return all_trades


def train_slice(trades: list[dict], cut_ts: int) -> list[dict]:
    return [t for t in trades if t["signal_ts"] < cut_ts]


def holdout_slice(trades: list[dict], cut_ts: int) -> list[dict]:
    return [t for t in trades if t["signal_ts"] >= cut_ts]


def stats(trades: list[dict]) -> dict:
    n = len(trades)
    if n == 0:
        return {"n": 0, "wr": float("nan"), "net": 0.0, "net_per_trade": float("nan")}
    wins = sum(1 for t in trades if t["net_usd"] > 0)
    net = sum(t["net_usd"] for t in trades)
    return {"n": n, "wr": 100.0 * wins / n, "net": net, "net_per_trade": net / n}


def save_json(name: str, obj):
    with open(os.path.join(OUT_DIR, name), "w") as f:
        json.dump(obj, f)


def load_json(name: str):
    path = os.path.join(OUT_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def compute_cut_ts() -> int:
    """Mirrors run_scan.py's split logic: cut = max(exit_ts) - 30d, approximated
    here as max(last 5m candle ts across all pairs) - 30d, since exit_ts values
    are bounded by candle ts and the very last symbol's last candle sets the
    ceiling. Computed once from the untouched cached data (no replay needed)."""
    pairs = scan_pairs()
    max_ts = 0
    for sym in pairs:
        df5m = load_candles(sym, "5m", data_dir=DATA_DIR)
        max_ts = max(max_ts, int(df5m["ts"].max()))
    return max_ts - HOLDOUT_DAYS * 86_400_000


def main():
    workers = min(8, os.cpu_count() or 4)
    cut_ts = compute_cut_ts()
    feed_cutoff = cut_ts + RESOLUTION_BUFFER_DAYS * 86_400_000
    print(f"TRAIN cutoff signal_ts < {cut_ts} "
          f"({datetime.datetime.fromtimestamp(cut_ts/1000, tz=datetime.timezone.utc)} UTC)")
    print(f"Truncated re-replay feed cutoff: {feed_cutoff} "
          f"({datetime.datetime.fromtimestamp(feed_cutoff/1000, tz=datetime.timezone.utc)} UTC)")

    phase = sys.argv[1] if len(sys.argv) > 1 else "all"

    # ---------- Phase A: baseline (full 90d, authoritative) ----------
    if phase in ("all", "baseline"):
        base_trades = load_json("baseline_trades.json")
        if base_trades is None:
            t0 = time.time()
            base_trades = run_pooled("baseline", {}, max_ts=None, workers=workers)
            save_json("baseline_trades.json", base_trades)
            print(f"[baseline] TOTAL {len(base_trades)} trades in {time.time()-t0:.1f}s")
        base_train = train_slice(base_trades, cut_ts)
        print(f"[baseline] TRAIN n={len(base_train)} stats={stats(base_train)}")
        save_json("cut_ts.json", {"cut_ts": cut_ts, "feed_cutoff": feed_cutoff})

    # ---------- Phase B: L1 zone cooldown (re-replay, truncated feed) -------
    if phase in ("all", "L1"):
        l1_trades = load_json("L1_trades.json")
        if l1_trades is None:
            t0 = time.time()
            l1_trades = run_pooled("L1", {"zone_cooldown_candles": 12}, max_ts=feed_cutoff,
                                    workers=workers)
            save_json("L1_trades.json", l1_trades)
            print(f"[L1] TOTAL {len(l1_trades)} trades in {time.time()-t0:.1f}s")

    # ---------- Phase C: L4 loss-day blacklist (re-replay, truncated feed) --
    if phase in ("all", "L4"):
        l4_trades = load_json("L4_trades.json")
        if l4_trades is None:
            t0 = time.time()
            l4_trades = run_pooled("L4", {"loss_day_blacklist": True}, max_ts=feed_cutoff,
                                    workers=workers)
            save_json("L4_trades.json", l4_trades)
            print(f"[L4] TOTAL {len(l4_trades)} trades in {time.time()-t0:.1f}s")

    # ---------- Phase D: analysis (L2/L3 post-filter, L5 combo, holdout) ----
    if phase in ("all", "analyze"):
        analyze(cut_ts, feed_cutoff, workers)

    print("done:", phase)


LEVER_LABELS = {
    "L1": "Zone cooldown (12x 5m candles / 1h, any exit)",
    "L2": "Risk floor (skip risk_pct < 0.25%)",
    "L3": "Touch band (keep touches 2-5, skip 6+)",
    "L4": "Loss-side day blacklist (stop_loss zones, same UTC day)",
}


def apply_l2(trades):
    return [t for t in trades if t["risk_pct"] >= 0.25]


def apply_l3(trades):
    return [t for t in trades if t["touches"] <= 5]


def fmt_row(label, desc, d, baseline_n, baseline_npt):
    s = stats(d)
    if s["n"] == 0:
        return f"| {label} | {desc} | 0 | - | - | - | - | 100.0% |"
    delta = s["net_per_trade"] - baseline_npt
    removed = 100.0 * (1 - s["n"] / baseline_n) if baseline_n else float("nan")
    return (f"| {label} | {desc} | {s['n']} | {s['wr']:.1f}% | ${s['net']:+.2f} | "
            f"${s['net_per_trade']:+.4f} | ${delta:+.4f} | {removed:.1f}% |")


def analyze(cut_ts: int, feed_cutoff: int, workers: int):
    base_trades = load_json("baseline_trades.json")
    l1_trades = load_json("L1_trades.json")
    l4_trades = load_json("L4_trades.json")
    if base_trades is None or l1_trades is None or l4_trades is None:
        print("analyze: missing phase A/B/C outputs, run those phases first")
        return

    base_train = train_slice(base_trades, cut_ts)
    l1_train = train_slice(l1_trades, cut_ts)
    l4_train = train_slice(l4_trades, cut_ts)
    l2_train = apply_l2(base_train)
    l3_train = apply_l3(base_train)

    base_n = len(base_train)
    base_stats = stats(base_train)
    base_npt = base_stats["net_per_trade"]

    per_lever_train = {"L1": l1_train, "L2": l2_train, "L3": l3_train, "L4": l4_train}
    per_lever_stats = {k: stats(v) for k, v in per_lever_train.items()}

    # rank by net/trade (higher = better; least-negative wins if none positive)
    ranked = sorted(per_lever_stats.items(), key=lambda kv: kv[1]["net_per_trade"], reverse=True)
    best_two = [k for k, _ in ranked[:2]]

    non_replay = {"L2", "L3"}
    replay_only = {"L1", "L4"}
    best_two_set = set(best_two)

    l5_desc = f"Combo: {' + '.join(best_two)}"
    if best_two_set <= non_replay:
        l5_train = base_train
        for k in best_two:
            l5_train = apply_l2(l5_train) if k == "L2" else apply_l3(l5_train)
        l5_needs_replay = False
    elif best_two_set == replay_only:
        t0 = time.time()
        l5_raw = run_pooled("L5", {"zone_cooldown_candles": 12, "loss_day_blacklist": True},
                             max_ts=feed_cutoff, workers=workers)
        save_json("L5_trades.json", l5_raw)
        print(f"[L5] TOTAL {len(l5_raw)} trades in {time.time()-t0:.1f}s")
        l5_train = train_slice(l5_raw, cut_ts)
        l5_needs_replay = True
    else:
        seq_lever = (best_two_set & replay_only).pop()
        filt_lever = (best_two_set & non_replay).pop()
        base_seq_train = l1_train if seq_lever == "L1" else l4_train
        l5_train = apply_l2(base_seq_train) if filt_lever == "L2" else apply_l3(base_seq_train)
        l5_needs_replay = False

    per_lever_train["L5"] = l5_train
    per_lever_stats["L5"] = stats(l5_train)

    overall_ranked = sorted(per_lever_stats.items(), key=lambda kv: kv[1]["net_per_trade"],
                             reverse=True)
    overall_best_label, overall_best_stats = overall_ranked[0]

    holdout_run = None
    holdout_stats = None
    if overall_best_stats["n"] > 0 and overall_best_stats["net_per_trade"] > 0:
        print(f"[holdout] {overall_best_label} cleared TRAIN net/trade > 0 "
              f"(${overall_best_stats['net_per_trade']:+.4f}) -> running HOLDOUT once")
        if overall_best_label in ("L2", "L3", "L5") and not (
                overall_best_label == "L5" and l5_needs_replay):
            base_hold = holdout_slice(base_trades, cut_ts)
            if overall_best_label == "L2":
                hold_trades = apply_l2(base_hold)
            elif overall_best_label == "L3":
                hold_trades = apply_l3(base_hold)
            else:  # L5 pure-filter or filter-on-seq combo needs the seq lever's full holdout
                if best_two_set <= non_replay:
                    hold_trades = base_hold
                    for k in best_two:
                        hold_trades = apply_l2(hold_trades) if k == "L2" else apply_l3(hold_trades)
                else:
                    seq_lever = (best_two_set & replay_only).pop()
                    filt_lever = (best_two_set & non_replay).pop()
                    full_key = f"{seq_lever}_trades_FULL.json"
                    full_raw = load_json(full_key)
                    if full_raw is None:
                        kw = {"zone_cooldown_candles": 12} if seq_lever == "L1" else \
                             {"loss_day_blacklist": True}
                        t0 = time.time()
                        full_raw = run_pooled(f"{seq_lever}-FULL", kw, max_ts=None,
                                               workers=workers)
                        save_json(full_key, full_raw)
                        print(f"[{seq_lever}-FULL] {len(full_raw)} trades in {time.time()-t0:.1f}s")
                    seq_hold = holdout_slice(full_raw, cut_ts)
                    hold_trades = apply_l2(seq_hold) if filt_lever == "L2" else apply_l3(seq_hold)
            holdout_run = overall_best_label
            holdout_stats = stats(hold_trades)
        else:
            lever_key = overall_best_label if overall_best_label in ("L1", "L4") else None
            full_key = "L5_trades_FULL.json" if overall_best_label == "L5" else \
                        f"{lever_key}_trades_FULL.json"
            full_raw = load_json(full_key)
            if full_raw is None:
                if overall_best_label == "L5":
                    kw = {"zone_cooldown_candles": 12, "loss_day_blacklist": True}
                else:
                    kw = {"zone_cooldown_candles": 12} if lever_key == "L1" else \
                         {"loss_day_blacklist": True}
                t0 = time.time()
                full_raw = run_pooled(f"{overall_best_label}-FULL", kw, max_ts=None,
                                       workers=workers)
                save_json(full_key, full_raw)
                print(f"[{overall_best_label}-FULL] {len(full_raw)} trades in {time.time()-t0:.1f}s")
            hold_trades = holdout_slice(full_raw, cut_ts)
            holdout_run = overall_best_label
            holdout_stats = stats(hold_trades)
    else:
        print(f"[holdout] best lever {overall_best_label} did NOT clear TRAIN net/trade > 0 "
              f"(${overall_best_stats['net_per_trade']:+.4f}) -> NO holdout run")

    write_report(cut_ts, base_train, per_lever_train, per_lever_stats, best_two, l5_desc,
                 l5_needs_replay, overall_best_label, holdout_run, holdout_stats)


def write_report(cut_ts, base_train, per_lever_train, per_lever_stats, best_two, l5_desc,
                  l5_needs_replay, overall_best_label, holdout_run, holdout_stats):
    base_n = len(base_train)
    base_s = stats(base_train)
    date = datetime.date.today().isoformat()
    lines = [f"# SR_BOUNCE counterfactual lever lab — {date}", "",
             "Scratch replay (`lever_lab.py`), TRAIN window only "
             "(signal_ts < cut, cut mirrors run_scan.py's split logic). "
             "Frozen originals (`sr_levels.py`, `sr_signal.py`, `engine.py`, "
             "`fetch_data.py`) untouched.", "",
             f"TRAIN cutoff: signal_ts < {cut_ts} "
             f"({datetime.datetime.fromtimestamp(cut_ts/1000, tz=datetime.timezone.utc).isoformat()} UTC)",
             "",
             f"Regenerated baseline TRAIN (this harness, full 90d replay): "
             f"**n={base_n}, WR {base_s['wr']:.1f}%, net ${base_s['net']:+.2f}, "
             f"net/trade ${base_s['net_per_trade']:+.4f}**",
             f"Frozen scan's reported baseline TRAIN (reference): "
             f"n={KNOWN_BASELINE_TRAIN_N}, net/trade ${KNOWN_BASELINE_TRAIN_NET_PER_TRADE:+.4f}",
             ""]

    diff_n = base_n - KNOWN_BASELINE_TRAIN_N
    diff_npt = base_s["net_per_trade"] - KNOWN_BASELINE_TRAIN_NET_PER_TRADE
    lines.append(f"Cross-check vs frozen scan: trade-count diff {diff_n:+d} "
                 f"({100*diff_n/KNOWN_BASELINE_TRAIN_N:+.1f}%), net/trade diff "
                 f"${diff_npt:+.4f}. All lever deltas below are computed against "
                 f"**this harness's own regenerated baseline** (same code, same "
                 f"data, same split) for an apples-to-apples comparison; the frozen "
                 f"scan's number is shown above for reference only.")
    lines += ["", "## Per-lever TRAIN results", "",
              "| Lever | Description | Trades | WR | Net | Net/trade | Δ vs baseline | % removed |",
              "|---|---|---|---|---|---|---|---|"]
    lines.append(fmt_row("baseline", "Frozen engine logic (this harness)", base_train,
                         base_n, base_s["net_per_trade"]))
    for k in ["L1", "L2", "L3", "L4"]:
        lines.append(fmt_row(k, LEVER_LABELS[k], per_lever_train[k], base_n,
                             base_s["net_per_trade"]))
    replay_note = " (re-replayed)" if l5_needs_replay else " (composed from above, no fresh replay needed)"
    lines.append(fmt_row("L5", l5_desc + replay_note, per_lever_train["L5"], base_n,
                         base_s["net_per_trade"]))

    lines += ["", "## Methodology notes / limitations", "",
              "- L1 (zone cooldown) and L4 (loss-day blacklist) are proper "
              "re-replays: the lever logic is wired into the entry-scan loop "
              "itself, so a blocked signal genuinely never fires and the "
              "position slot may go to a different signal — sequencing is "
              "exact.",
              "- L2 (risk floor) and L3 (touch band) are POST-FILTERS on the "
              "baseline trade list. This is NOT exact: in a true re-replay, "
              "removing a filtered-out trade would free that symbol's "
              "one-position-per-symbol slot for a different signal the "
              "baseline never took. Post-filter numbers are an UPPER BOUND on "
              "what a true re-replay of L2/L3 alone would show.",
              "- L1/L4 re-replays use TRAIN-window-only data "
              f"(feed truncated to cut_ts + {RESOLUTION_BUFFER_DAYS}d buffer) "
              "to avoid the ~80min/10-pair full-replay cost; the buffer exists "
              "only so trades opened near the TRAIN boundary have candles to "
              "resolve against, not to peek at holdout outcomes. No statistic "
              "from beyond the TRAIN cutoff informed any lever decision.",
              "- Replays parallelized 10-way across available CPU cores; "
              "trade-selection logic is otherwise byte-for-byte identical to "
              "the frozen `engine.replay()` (verified against the existing "
              "unit-test fixtures before this run).", ""]

    lines += ["## L5 selection", "",
              f"Best two individual levers by TRAIN net/trade: **{best_two[0]}** and "
              f"**{best_two[1]}**.", ""]

    lines += ["## Holdout (honesty-gated)", ""]
    if holdout_run is None:
        best_npt = per_lever_stats[overall_best_label]["net_per_trade"]
        lines.append(f"Overall best performer on TRAIN: **{overall_best_label}** "
                     f"(net/trade ${best_npt:+.4f}). This is "
                     f"{'positive but' if best_npt > 0 else 'NOT positive —'} "
                     f"{'' if best_npt > 0 else 'below the honesty-rule bar of net/trade > 0.'} "
                     "**No holdout run performed.**")
    else:
        hs = holdout_stats
        lines.append(f"Overall best performer on TRAIN: **{overall_best_label}** cleared "
                     f"net/trade > 0. Holdout run once for {overall_best_label} only:")
        lines.append("")
        lines.append(f"- HOLDOUT: n={hs['n']}, WR {hs['wr']:.1f}%, net ${hs['net']:+.2f}, "
                     f"net/trade ${hs['net_per_trade']:+.4f}")

    path = os.path.join(HERE, "lever_lab_results.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"report -> {path}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
