#!/usr/bin/env python3
"""5m_mean_revert edge search — Phase D screen (train read, then ONE holdout read per family).

Reads the Phase C signal table (reports/mr_edge_2026/signals.json) and screens the five
pre-registered families against the frozen criteria in
docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md:

  H1  exit geometry   — every grid cell in net_by_cell minus the live twin, vs the live cell
  H2  1h-ADX cap      — keep entries with adx1h <= {35, 40, 50}      (null adx1h: out of both cohorts)
  H3  short tape      — skip SHORTS when buy_ratio >= {0.80, 0.90, 0.95} and trade_count > 20
                        (null flow: kept; longs untouched)
  H4  funding context — skip shorts when funding <= -X, longs when funding >= +X,
                        X in {0.0001, 0.0003, 0.0005}                 (null funding: kept)
  H5  sub-populations — the single-dimension buckets of mean_revert_filters._buckets (kept = in bucket)

The live cell is the baseline for every family; H2-H5 are FILTERS on the live cell.

Anti-artifact stack (all from scripts/st2_lab): one pooled Benjamini-Hochberg (alpha 0.10)
across ALL trial p-values, deflated Sharpe charged for the total trial count, 3-fold
chronological walk-forward sign check, bootstrap_diff_ci with INDEPENDENT resampling
(conservative for the paired H1 comparison and for kept-vs-all — accepted, printed), min-n floors.

Selection (train) is mechanical, <=1 winner per family. Holdout evaluates train winners only,
refuses to run unless train_results.json exists AND sha256(prereg) == meta.prereg_sha AND no
holdout_read_<family>.lock exists; it writes the lock on read (one read per family, ever).

Isolation: research-only. Never imports bot.py / exchange.py / config.py / risk_manager.py;
never touches trading_state*.json or .env. Reads signals.json, writes only under --out.

Run:
  python3 scripts/slot_lab/mr_edge_screen.py --phase train   --signals reports/mr_edge_2026/signals.json \
      --prereg docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md --out reports/mr_edge_2026/
  python3 scripts/slot_lab/mr_edge_screen.py --phase holdout ... (same args)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from datetime import datetime, timezone

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts"))
sys.path.insert(0, os.path.join(_BOT_DIR, "scripts", "slot_lab"))
from st2_lab import stats as ST  # noqa: E402
from st2_lab.walkforward import walk_forward_splits  # noqa: E402
from mean_revert_filters import _buckets as _mrf_buckets  # noqa: E402

# ---------------------------------------------------------------------------
# frozen parameters (prereg 2026-09-03) — do not tune
# ---------------------------------------------------------------------------
FAMILIES = ("H1", "H2", "H3", "H4", "H5")
FILTER_FAMILIES = ("H2", "H3", "H4", "H5")
LIVE_CELL = "live"
LIVE_TWIN = "tp1.6_sl1.2_t4h"          # H1 grid cell identical to the live geometry
H2_CAPS = (35, 40, 50)
H3_BUY_RATIOS = (0.80, 0.90, 0.95)
H3_MIN_TRADES = 20                     # tape filter only counts when trade_count > this
H4_X = (0.0001, 0.0003, 0.0005)

N_BOOT_DEFAULT = 2000
SEED_DEFAULT = 0
BH_ALPHA = 0.10
DSR_BAR = 0.95
STRONG_MEAN = 0.50                     # $/trade at $15 margin
MIN_KEPT_TRAIN = 40
MIN_KEPT_HOLDOUT = 20
MIN_REMOVED = 15
MIN_H5 = 25
WF_FOLDS = 3
WF_FOLD_MIN_N = 3                      # a fold with fewer rows cannot register a sign

BB_BUCKETS = ("bbwidth low", "bbwidth mid", "bbwidth high")


def _utc(y, m, d, H=0, M=0, S=0):
    return int(datetime(y, m, d, H, M, S, tzinfo=timezone.utc).timestamp())


TRAIN_START = _utc(2026, 6, 1)                       # inclusive
TRAIN_END = _utc(2026, 8, 3, 23, 59, 59)             # inclusive
EMBARGO_S = 8 * 3600
HOLDOUT_START = _utc(2026, 8, 4) + EMBARGO_S         # inclusive
HOLDOUT_END = _utc(2026, 9, 3)                       # exclusive

CAVEATS = [
    "bootstrap_diff_ci resamples the two sides INDEPENDENTLY (house rule). For H1 the cell and "
    "live series come from the SAME rows (paired) and for filters kept is a subset of all-signal; "
    "independent resampling ignores that positive dependence, so every diff CI here is CONSERVATIVE "
    "(wider than a paired CI). A diff CI that excludes 0 under this treatment is the stronger claim.",
    "Fill-all at the signal bar close (real maker fill ~27%, adverse selection not modeled): every "
    "dollar is an UPPER BOUND. Only relative comparisons (cell vs live, kept vs removed/all) are "
    "decision metrics.",
    "OB/tape gates are not replayed (no historical L2) except where flow_capture supplies H3 inputs.",
]


class GuardError(RuntimeError):
    """Refusal by a pre-registration guard (prereg sha, train prerequisite, holdout lock)."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def split_rows(rows):
    """(train, holdout, dropped) by ts against the frozen window + 8 h embargo."""
    train, holdout, dropped = [], [], []
    for r in rows:
        ts = r.get("ts", 0)
        if TRAIN_START <= ts <= TRAIN_END:
            train.append(r)
        elif HOLDOUT_START <= ts < HOLDOUT_END:
            holdout.append(r)
        else:
            dropped.append(r)
    return train, holdout, dropped


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _sharpe(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    mu = _mean(xs)
    var = sum((x - mu) ** 2 for x in xs) / (n - 1)
    sd = math.sqrt(var)
    return mu / sd if sd > 0 else 0.0


def _boot_mean_ci_p(xs, n_boot, seed):
    """One-sample percentile bootstrap: (lo, hi, p) with p = P(bootstrap mean <= 0)."""
    n = len(xs)
    if n < 2:
        return (None, None, 1.0)
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choices(xs, k=n)) / n for _ in range(n_boot))
    lo = means[int(0.025 * n_boot)]
    hi = means[min(int(0.975 * n_boot), n_boot - 1)]
    p = sum(1 for m in means if m <= 0) / n_boot
    return (lo, hi, p)


def _boot_diff_p(a, b, n_boot, seed):
    """One-sided p for mean(a) - mean(b) <= 0 with INDEPENDENT resampling of a and b
    (the draw-order means are differenced; nothing is sorted before differencing)."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 1.0
    rnd = random.Random(seed)
    le = 0
    for _ in range(n_boot):
        d = sum(rnd.choices(a, k=na)) / na - sum(rnd.choices(b, k=nb)) / nb
        if d <= 0:
            le += 1
    return le / n_boot


def _wf_signs(pairs):
    """3-fold chronological walk-forward sign list via walk_forward_splits on ts.
    pairs = [(ts, value)]. Returns [bool|None]*3 (None = fold too thin) or None."""
    if len(pairs) < WF_FOLDS * WF_FOLD_MIN_N:
        return None
    recs = [{"ts": t, "v": v} for t, v in pairs]
    try:
        splits = walk_forward_splits({"all": recs}, WF_FOLDS, embargo_secs=0)
    except ValueError:
        return None
    out = []
    for s in splits:
        vals = [r["v"] for r in s["test"].get("all", [])]
        out.append(_mean(vals) > 0 if len(vals) >= WF_FOLD_MIN_N else None)
    return out


def _wf_ok(signs):
    return bool(signs) and len(signs) == WF_FOLDS and all(s is True for s in signs)


def _series(rows, idx, cell):
    return [rows[i]["net_by_cell"][cell] for i in idx]


def _stat_block(vals, n_boot, seed):
    lo, hi, p = _boot_mean_ci_p(vals, n_boot, seed)
    return {"n": len(vals), "mean": _mean(vals) if vals else None, "ci": [lo, hi], "p": p,
            "sharpe": _sharpe(vals), "win_rate": (sum(1 for v in vals if v > 0) / len(vals))
            if vals else None}


# ---------------------------------------------------------------------------
# families
# ---------------------------------------------------------------------------

def h1_cells(cells):
    """Grid cells to test: everything except the live cell and its twin."""
    return [c for c in cells if c not in (LIVE_CELL, LIVE_TWIN)]


def apply_h2(rows, cap):
    kept, removed, null = [], [], []
    for i, r in enumerate(rows):
        a = r.get("adx1h")
        if a is None:
            null.append(i)
        elif a <= cap:
            kept.append(i)
        else:
            removed.append(i)
    return kept, removed, null


def apply_h3(rows, ratio):
    kept, removed, null = [], [], []
    for i, r in enumerate(rows):
        f = r.get("flow")
        skip = (r.get("side") == "short" and f is not None
                and f.get("buy_ratio") is not None and f.get("trade_count") is not None
                and f["buy_ratio"] >= ratio and f["trade_count"] > H3_MIN_TRADES)
        (removed if skip else kept).append(i)
    return kept, removed, null


def apply_h4(rows, x):
    kept, removed, null = [], [], []
    for i, r in enumerate(rows):
        fr = r.get("funding_rate")
        side = r.get("side")
        skip = fr is not None and ((side == "short" and fr <= -x) or (side == "long" and fr >= x))
        (removed if skip else kept).append(i)
    return kept, removed, null


_H5_FEATURES = ("rsi_fast", "vol_ratio", "adx5m", "bb_width_pct", "hour_pt", "side")


def _h5_shim(r, i):
    """Adapter: signal-table row -> the keys mean_revert_filters._buckets reads.
    rsi_fast (the RSI(7) the signal fires on) -> rsi, vol_ratio -> vol_mult, adx5m -> adx.
    Returns None when any feature is null (row excluded from the H5 universe)."""
    if any(r.get(k) is None for k in _H5_FEATURES):
        return None
    return {"_i": i, "side": r["side"], "rsi": r["rsi_fast"], "vol_mult": r["vol_ratio"],
            "adx": r["adx5m"], "bb_width_pct": r["bb_width_pct"], "hour_pt": r["hour_pt"]}


def h5_bb_thresholds(rows):
    """BB-width tercile cut points exactly as _buckets computes them (frozen from train)."""
    widths = sorted(s["bb_width_pct"] for s in (_h5_shim(r, i) for i, r in enumerate(rows)) if s)
    if not widths:
        return None
    return [widths[len(widths) // 3], widths[2 * len(widths) // 3]]


def h5_buckets(rows, bb_thresholds=None):
    """label -> list of shim rows, via mean_revert_filters._buckets. When bb_thresholds
    (from train) are given the three bbwidth terciles are re-cut with them so the holdout
    tests the SAME bucket definition instead of re-deriving terciles on holdout data."""
    shim = [s for s in (_h5_shim(r, i) for i, r in enumerate(rows)) if s is not None]
    b = _mrf_buckets(shim)
    if bb_thresholds and shim:
        t1, t2 = bb_thresholds
        b["bbwidth low"] = [s for s in shim if s["bb_width_pct"] <= t1]
        b["bbwidth mid"] = [s for s in shim if t1 < s["bb_width_pct"] <= t2]
        b["bbwidth high"] = [s for s in shim if s["bb_width_pct"] > t2]
    return b


def apply_h5(rows, label, buckets):
    in_bucket = {s["_i"] for s in buckets.get(label, [])}
    kept, removed, null = [], [], []
    for i, r in enumerate(rows):
        if _h5_shim(r, i) is None:
            null.append(i)
        elif i in in_bucket:
            kept.append(i)
        else:
            removed.append(i)
    return kept, removed, null


def trial_total(cells, rows):
    return len(h1_cells(cells)) + len(H2_CAPS) + len(H3_BUY_RATIOS) + len(H4_X) + len(h5_buckets(rows))


def _filter_specs(rows, bb_thresholds=None):
    """Ordered list of (family, label, (kept, removed, null)) for H2-H5."""
    out = []
    for cap in H2_CAPS:
        out.append(("H2", f"adx1h<={cap}", apply_h2(rows, cap)))
    for x in H3_BUY_RATIOS:
        out.append(("H3", f"short_skip_buy_ratio>={x:.2f}", apply_h3(rows, x)))
    for x in H4_X:
        out.append(("H4", f"funding_skip_X={x:.4f}", apply_h4(rows, x)))
    buckets = h5_buckets(rows, bb_thresholds)
    for label in buckets:
        out.append(("H5", label, apply_h5(rows, label, buckets)))
    return out


# ---------------------------------------------------------------------------
# per-trial evaluation
# ---------------------------------------------------------------------------

def _eval_h1(rows, cell, live, n_boot, seed, min_kept):
    vals = [r["net_by_cell"][cell] for r in rows]
    kept = _stat_block(vals, n_boot, seed)
    diff_ci = ST.bootstrap_diff_ci(vals, live, n_boot=n_boot, alpha=0.05, seed=seed)
    p = _boot_diff_p(vals, live, n_boot, seed + 1)
    wf = _wf_signs([(r["ts"], r["net_by_cell"][cell] - r["net_by_cell"][LIVE_CELL]) for r in rows])
    return {
        "family": "H1", "label": cell,
        "kept": kept, "removed": None, "n_null": 0,
        "diff": {"vs": LIVE_CELL, "mean": kept["mean"] - _mean(live), "ci": list(diff_ci)},
        "p": p,                      # H0: mean(cell) - mean(live) <= 0
        "sharpe": kept["sharpe"],
        "wf_signs": wf, "min_n_ok": kept["n"] >= min_kept,
        "exit_mix": _exit_mix(rows, cell),
    }


def _exit_mix(rows, cell):
    mix = {}
    for r in rows:
        e = (r.get("exit_by_cell") or {}).get(cell)
        if e is not None:
            mix[e] = mix.get(e, 0) + 1
    return mix


def _eval_filter(rows, family, label, cohorts, live_all, n_boot, seed, min_kept, min_removed):
    kept_i, removed_i, null_i = cohorts
    kv = _series(rows, kept_i, LIVE_CELL)
    rv = _series(rows, removed_i, LIVE_CELL)
    kept = _stat_block(kv, n_boot, seed)
    removed = _stat_block(rv, n_boot, seed)
    diff_ci = (ST.bootstrap_diff_ci(kv, live_all, n_boot=n_boot, alpha=0.05, seed=seed)
               if len(kv) >= 2 and len(live_all) >= 2 else (None, None))
    wf = _wf_signs([(rows[i]["ts"], rows[i]["net_by_cell"][LIVE_CELL]) for i in kept_i])
    return {
        "family": family, "label": label,
        "kept": kept, "removed": removed, "n_null": len(null_i),
        "diff": {"vs": "all_signal", "mean": (kept["mean"] - _mean(live_all)) if kv else None,
                 "ci": list(diff_ci)},
        "p": kept["p"],              # H0: kept mean <= 0
        "sharpe": kept["sharpe"],
        "wf_signs": wf,
        "min_n_ok": kept["n"] >= min_kept and removed["n"] >= min_removed,
    }


def _attach_bh_dsr(trials, n_trials, var_trial_sharpes=None):
    """Pooled BH over ALL trial p-values + DSR per trial charged for n_trials."""
    mask = ST.benjamini_hochberg([t["p"] for t in trials], alpha=BH_ALPHA)
    sharpes = [t["sharpe"] for t in trials]
    if var_trial_sharpes is None:
        mu = _mean(sharpes)
        var_trial_sharpes = (sum((s - mu) ** 2 for s in sharpes) / (len(sharpes) - 1)
                             if len(sharpes) > 1 else 0.0)
    for t, ok in zip(trials, mask):
        t["bh_pass"] = bool(ok)
        t["dsr"] = ST.deflated_sharpe_ratio(t["sharpe"], t["kept"]["n"], n_trials, var_trial_sharpes)
    return var_trial_sharpes


def _passes_train(t, baseline_mean):
    reasons = []
    if not t["min_n_ok"]:
        reasons.append("min_n")
    if not t["bh_pass"]:
        reasons.append("bh")
    if not (t["dsr"] > DSR_BAR):
        reasons.append("dsr")
    if not _wf_ok(t["wf_signs"]):
        reasons.append("wf")
    if t["family"] == "H1":
        lo = t["diff"]["ci"][0]
        if lo is None or not (lo > 0):
            reasons.append("diff_vs_live_ci")
    else:
        rhi = t["removed"]["ci"][1]
        if t["removed"]["mean"] is None or rhi is None or not (t["removed"]["mean"] < 0 and rhi < 0):
            reasons.append("removed_ci")
        if t["kept"]["mean"] is None or not (t["kept"]["mean"] > baseline_mean):
            reasons.append("kept_vs_all")
    return reasons


def _min_kept(family, phase):
    if phase == "train":
        return MIN_H5 if family == "H5" else MIN_KEPT_TRAIN
    return MIN_KEPT_HOLDOUT


def _load(signals_path):
    with open(signals_path) as f:
        d = json.load(f)
    rows = d["rows"]
    for r in rows:
        if LIVE_CELL not in (r.get("net_by_cell") or {}):
            raise ValueError(f"row without a '{LIVE_CELL}' cell: {r.get('symbol')} @ {r.get('ts')}")
    cells = d["meta"].get("cells") or list(rows[0]["net_by_cell"].keys())
    return d["meta"], rows, cells


def _check_prereg(meta, prereg_path):
    actual = sha256_file(prereg_path)
    registered = meta.get("prereg_sha")
    if not registered or registered != actual:
        raise GuardError(f"prereg sha mismatch: meta.prereg_sha={registered!r} vs "
                         f"sha256({os.path.basename(prereg_path)})={actual}")
    return actual


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# train phase
# ---------------------------------------------------------------------------

def run_train(signals_path, prereg_path, out_dir, n_boot=N_BOOT_DEFAULT, seed=SEED_DEFAULT):
    meta, all_rows, cells = _load(signals_path)
    sha = _check_prereg(meta, prereg_path)
    rows, holdout_rows, dropped = split_rows(all_rows)
    rows.sort(key=lambda r: r["ts"])
    live = [r["net_by_cell"][LIVE_CELL] for r in rows]
    baseline = _stat_block(live, n_boot, seed)
    bb_thr = h5_bb_thresholds(rows)

    trials = []
    for cell in h1_cells(cells):
        trials.append(_eval_h1(rows, cell, live, n_boot, seed, _min_kept("H1", "train")))
    for fam, label, cohorts in _filter_specs(rows, bb_thr):
        trials.append(_eval_filter(rows, fam, label, cohorts, live, n_boot, seed,
                                   _min_kept(fam, "train"), MIN_REMOVED))
    n_trials = len(trials)
    var_ts = _attach_bh_dsr(trials, n_trials)

    families, winners = {}, {}
    for fam in FAMILIES:
        fam_trials = [t for t in trials if t["family"] == fam]
        passing = []
        for t in fam_trials:
            t["fail_reasons"] = _passes_train(t, baseline["mean"])
            t["selected"] = False
            if not t["fail_reasons"]:
                passing.append(t)
        win = None
        if passing:
            # tie-break: highest DSR, then highest kept mean, then label (deterministic)
            win = max(passing, key=lambda t: (t["dsr"], t["kept"]["mean"], t["label"]))
            win["selected"] = True
        winners[fam] = ({"label": win["label"], "dsr": win["dsr"], "kept_mean": win["kept"]["mean"]}
                        if win else None)
        families[fam] = {"n_trials": len(fam_trials), "n_passing": len(passing), "trials": fam_trials}

    result = {
        "phase": "train", "generated_at": _now(), "signals": os.path.abspath(signals_path),
        "prereg": os.path.abspath(prereg_path), "prereg_sha": sha,
        "signals_meta": {k: meta.get(k) for k in ("window", "margin", "notional", "maker_fee",
                                                  "taker_fee", "trail_arm", "generated_at")},
        "split": {"train_start": TRAIN_START, "train_end": TRAIN_END, "embargo_s": EMBARGO_S,
                  "holdout_start": HOLDOUT_START, "holdout_end": HOLDOUT_END,
                  "n_train": len(rows), "n_holdout": len(holdout_rows), "n_dropped": len(dropped)},
        "params": {"n_boot": n_boot, "seed": seed, "bh_alpha": BH_ALPHA, "dsr_bar": DSR_BAR,
                   "min_kept": MIN_KEPT_TRAIN, "min_removed": MIN_REMOVED, "min_h5": MIN_H5,
                   "wf_folds": WF_FOLDS, "live_twin_excluded": LIVE_TWIN},
        "trial_total": n_trials, "var_trial_sharpes": var_ts,
        "h5_bb_thresholds": bb_thr,
        "baseline": baseline, "families": families, "winners": winners,
        "caveats": CAVEATS + list(meta.get("caveats") or []),
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "train_results.json"), "w") as f:
        json.dump(result, f, indent=1)
    with open(os.path.join(out_dir, "train_report.md"), "w") as f:
        f.write(_train_report_md(result))
    _print_train(result)
    return result


# ---------------------------------------------------------------------------
# holdout phase
# ---------------------------------------------------------------------------

def lock_path(out_dir, family):
    return os.path.join(out_dir, f"holdout_read_{family}.lock")


def _verdict(t, family):
    """STRONG / WEAK / NULL per the frozen definition; returns (verdict, reasons)."""
    k = t["kept"]
    reasons = []
    if not t["min_n_ok"]:
        return "NULL", ["min_n"]
    ci_excl = k["ci"][0] is not None and k["ci"][0] > 0
    if not ci_excl:
        return "NULL", ["kept_ci_incl_0"]
    if k["mean"] < STRONG_MEAN:
        return "WEAK", ["mean_below_0.50"]
    if family == "H1" and not (t["diff"]["ci"][0] is not None and t["diff"]["ci"][0] > 0):
        reasons.append("diff_vs_live_ci")
    if not _wf_ok(t["wf_full_signs"]):
        reasons.append("wf_full_window")
    return ("STRONG", []) if not reasons else ("NULL", reasons)


def run_holdout(signals_path, prereg_path, out_dir, n_boot=N_BOOT_DEFAULT, seed=SEED_DEFAULT):
    tr_path = os.path.join(out_dir, "train_results.json")
    if not os.path.exists(tr_path):
        raise GuardError(f"holdout refused: train_results.json not found at {tr_path}")
    with open(tr_path) as f:
        train = json.load(f)
    meta, all_rows, cells = _load(signals_path)
    sha = _check_prereg(meta, prereg_path)
    if train.get("prereg_sha") != sha:
        raise GuardError(f"prereg sha mismatch: train_results.json was produced under "
                         f"{train.get('prereg_sha')!r}, current sha={sha}")
    winners = {f: w for f, w in train["winners"].items() if w}
    locked = [f for f in winners if os.path.exists(lock_path(out_dir, f))]
    if locked:
        raise GuardError("holdout refused: lock file(s) exist — one read per family, ever: "
                         + ", ".join(lock_path(out_dir, f) for f in locked))

    train_rows, rows, dropped = split_rows(all_rows)
    rows.sort(key=lambda r: r["ts"])
    full_rows = sorted(train_rows + rows, key=lambda r: r["ts"])
    live = [r["net_by_cell"][LIVE_CELL] for r in rows]
    baseline = _stat_block(live, n_boot, seed)
    bb_thr = train.get("h5_bb_thresholds")
    n_trials = train["trial_total"]
    var_ts = train.get("var_trial_sharpes")

    # create the locks BEFORE reading (a crash mid-read still burns the read)
    for fam, w in winners.items():
        with open(lock_path(out_dir, fam), "w") as f:
            f.write(f"{_now()} holdout read {fam} winner={w['label']} prereg_sha={sha}\n")

    evaluated = {}
    for fam, w in winners.items():
        label = w["label"]
        if fam == "H1":
            t = _eval_h1(rows, label, live, n_boot, seed, MIN_KEPT_HOLDOUT)
            full_live = [r["net_by_cell"][LIVE_CELL] for r in full_rows]
            t["wf_full_signs"] = _wf_signs([(r["ts"], r["net_by_cell"][label] - r["net_by_cell"][LIVE_CELL])
                                            for r in full_rows])
            t["full_window"] = {"n": len(full_rows), "cell_mean": _mean([r["net_by_cell"][label] for r in full_rows]),
                                "live_mean": _mean(full_live)}
        else:
            spec = {(f, l): c for f, l, c in _filter_specs(rows, bb_thr)}
            full_spec = {(f, l): c for f, l, c in _filter_specs(full_rows, bb_thr)}
            if (fam, label) not in spec:
                raise GuardError(f"train winner {fam}/{label!r} has no holdout trial definition")
            t = _eval_filter(rows, fam, label, spec[(fam, label)], live, n_boot, seed,
                             MIN_KEPT_HOLDOUT, MIN_REMOVED)
            fk = full_spec[(fam, label)][0]
            t["wf_full_signs"] = _wf_signs([(full_rows[i]["ts"], full_rows[i]["net_by_cell"][LIVE_CELL])
                                            for i in fk])
            t["full_window"] = {"n": len(full_rows), "n_kept": len(fk),
                                "kept_mean": _mean(_series(full_rows, fk, LIVE_CELL))}
        t["train_winner"] = w
        evaluated[fam] = t
    # informational only (not part of the verdict): DSR charged for the TRAIN trial count
    if evaluated:
        _attach_bh_dsr(list(evaluated.values()), n_trials, var_ts)
    for fam, t in evaluated.items():
        t["verdict"], t["verdict_reasons"] = _verdict(t, fam)

    result = {
        "phase": "holdout", "generated_at": _now(), "signals": os.path.abspath(signals_path),
        "prereg": os.path.abspath(prereg_path), "prereg_sha": sha,
        "train_results": os.path.abspath(tr_path), "train_generated_at": train.get("generated_at"),
        "split": dict(train["split"], n_holdout=len(rows), n_train=len(train_rows), n_dropped=len(dropped)),
        "params": {"n_boot": n_boot, "seed": seed, "min_kept": MIN_KEPT_HOLDOUT,
                   "min_removed": MIN_REMOVED, "strong_mean": STRONG_MEAN, "wf_folds": WF_FOLDS,
                   "n_trials_charged": n_trials},
        "baseline": baseline, "h5_bb_thresholds": bb_thr,
        "evaluated": evaluated,
        "not_evaluated": {f: "no train winner" for f in FAMILIES if f not in winners},
        "locks": {f: lock_path(out_dir, f) for f in winners},
        "caveats": CAVEATS + list(meta.get("caveats") or []),
    }
    with open(os.path.join(out_dir, "holdout_results.json"), "w") as f:
        json.dump(result, f, indent=1)
    with open(os.path.join(out_dir, "holdout_report.md"), "w") as f:
        f.write(_holdout_report_md(result))
    _print_holdout(result)
    return result


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------

def _f(x, nd=3, sign=True):
    if x is None:
        return "n/a"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def _ci(ci):
    if not ci or ci[0] is None:
        return "n/a"
    return f"[{ci[0]:+.3f}, {ci[1]:+.3f}]"


def _wf_str(signs):
    if not signs:
        return "n/a"
    return "".join("+" if s is True else ("-" if s is False else "?") for s in signs)


def _ts_str(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _header(res):
    s = res["split"]
    return (f"- signals: `{res['signals']}`\n- prereg: `{res['prereg']}` sha256 `{res['prereg_sha']}`\n"
            f"- generated: {res['generated_at']}\n"
            f"- train {_ts_str(s['train_start'])} → {_ts_str(s['train_end'])} (n={s['n_train']}); "
            f"holdout {_ts_str(s['holdout_start'])} → {_ts_str(s['holdout_end'])} excl. "
            f"({s['embargo_s'] // 3600} h embargo, n={s['n_holdout']}); dropped {s['n_dropped']}\n")


def _train_report_md(res):
    b = res["baseline"]
    L = [f"# MR edge screen — TRAIN read\n", _header(res),
         f"- baseline (live cell, all train signals): n={b['n']} mean ${_f(b['mean'])} CI {_ci(b['ci'])} "
         f"sharpe {_f(b['sharpe'])}\n",
         f"- trials: {res['trial_total']} total (H1 {res['families']['H1']['n_trials']} cells, live twin "
         f"`{LIVE_TWIN}` excluded; H2 {res['families']['H2']['n_trials']}; H3 {res['families']['H3']['n_trials']}; "
         f"H4 {res['families']['H4']['n_trials']}; H5 {res['families']['H5']['n_trials']} buckets)\n",
         f"- guards: pooled BH α={BH_ALPHA} over all {res['trial_total']} p-values; DSR n_trials={res['trial_total']} "
         f"(var of trial Sharpes {res['var_trial_sharpes']:.5f}); WF {WF_FOLDS}-fold; min-n kept≥{MIN_KEPT_TRAIN} "
         f"(H5 ≥{MIN_H5}), removed≥{MIN_REMOVED}; bootstrap {res['params']['n_boot']} reps seed {res['params']['seed']}\n",
         "\n## Caveats\n"] + [f"- {c}\n" for c in res["caveats"]]
    L.append("\n## Winners (mechanical, ≤1 per family)\n")
    for fam in FAMILIES:
        w = res["winners"][fam]
        L.append(f"- {fam}: " + (f"**{w['label']}** (DSR {w['dsr']:.3f}, kept mean ${_f(w['kept_mean'])})"
                                 if w else "none") + "\n")
    for fam in FAMILIES:
        f = res["families"][fam]
        L.append(f"\n## {fam} — {f['n_trials']} trials, {f['n_passing']} passing\n\n")
        if fam == "H1":
            L.append("| cell | n | mean | CI | diff vs live | diff CI | sharpe | p | BH | DSR | WF | min-n | exits | result |\n")
            L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
            for t in f["trials"]:
                ex = ",".join(f"{k}:{v}" for k, v in sorted(t["exit_mix"].items()))
                L.append(f"| {t['label']} | {t['kept']['n']} | {_f(t['kept']['mean'])} | {_ci(t['kept']['ci'])} | "
                         f"{_f(t['diff']['mean'])} | {_ci(t['diff']['ci'])} | {_f(t['sharpe'])} | {t['p']:.3f} | "
                         f"{'Y' if t['bh_pass'] else 'n'} | {t['dsr']:.3f} | {_wf_str(t['wf_signs'])} | "
                         f"{'Y' if t['min_n_ok'] else 'n'} | {ex} | "
                         f"{'**SELECTED**' if t['selected'] else ('pass' if not t['fail_reasons'] else 'fail: ' + ','.join(t['fail_reasons']))} |\n")
        else:
            L.append("| trial | n kept | n removed | n null | kept mean | kept CI | removed mean | removed CI | "
                     "kept−all | diff CI | sharpe | p | BH | DSR | WF | min-n | result |\n")
            L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
            for t in f["trials"]:
                L.append(f"| {t['label']} | {t['kept']['n']} | {t['removed']['n']} | {t['n_null']} | "
                         f"{_f(t['kept']['mean'])} | {_ci(t['kept']['ci'])} | {_f(t['removed']['mean'])} | "
                         f"{_ci(t['removed']['ci'])} | {_f(t['diff']['mean'])} | {_ci(t['diff']['ci'])} | "
                         f"{_f(t['sharpe'])} | {t['p']:.3f} | {'Y' if t['bh_pass'] else 'n'} | {t['dsr']:.3f} | "
                         f"{_wf_str(t['wf_signs'])} | {'Y' if t['min_n_ok'] else 'n'} | "
                         f"{'**SELECTED**' if t['selected'] else ('pass' if not t['fail_reasons'] else 'fail: ' + ','.join(t['fail_reasons']))} |\n")
    L.append("\nSelection rule (frozen): filters need removed mean < 0 with CI excl 0 AND kept mean > all-signal mean "
             "AND BH AND DSR > 0.95 AND WF 3/3 AND min-n; H1 cells need diff-vs-live CI > 0 AND BH AND DSR > 0.95 "
             "AND WF 3/3 AND min-n. Tie-break: highest DSR. p for filters = P(bootstrap kept mean ≤ 0); p for H1 = "
             "P(independent-resample diff cell−live ≤ 0). WF sign: filters = kept fold mean > 0; H1 = fold mean of "
             "(cell − live) > 0.\n")
    return "".join(L)


def _holdout_report_md(res):
    b = res["baseline"]
    L = [f"# MR edge screen — HOLDOUT read (one per family)\n", _header(res),
         f"- train results: `{res['train_results']}` ({res['train_generated_at']})\n",
         f"- baseline (live cell, all holdout signals): n={b['n']} mean ${_f(b['mean'])} CI {_ci(b['ci'])}\n",
         "\n## Caveats\n"] + [f"- {c}\n" for c in res["caveats"]]
    L.append("\n## Verdicts\n\n| family | train winner | n kept | kept mean | kept CI | n removed | removed mean | "
             "removed CI | diff | diff CI | WF holdout | WF full window | DSR (info) | verdict | reasons |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for fam in FAMILIES:
        t = res["evaluated"].get(fam)
        if not t:
            L.append(f"| {fam} | — | | | | | | | | | | | | not read | {res['not_evaluated'].get(fam, '')} |\n")
            continue
        rm = t["removed"] or {"n": "—", "mean": None, "ci": None}
        L.append(f"| {fam} | {t['label']} | {t['kept']['n']} | {_f(t['kept']['mean'])} | {_ci(t['kept']['ci'])} | "
                 f"{rm['n']} | {_f(rm['mean'])} | {_ci(rm['ci'])} | {_f(t['diff']['mean'])} ({t['diff']['vs']}) | "
                 f"{_ci(t['diff']['ci'])} | {_wf_str(t['wf_signs'])} | {_wf_str(t['wf_full_signs'])} | "
                 f"{t['dsr']:.3f} | **{t['verdict']}** | {','.join(t['verdict_reasons']) or '—'} |\n")
    L.append(f"\nVerdict rule (frozen): STRONG = kept/cell mean ≥ +${STRONG_MEAN:.2f} AND one-sample CI excl 0 AND "
             "(H1) diff-vs-live CI > 0 AND full-window WF 3/3; WEAK = CI excl 0 but mean < $0.50; NULL = anything else "
             f"(incl. n kept < {MIN_KEPT_HOLDOUT}). Locks written: " + ", ".join(res["locks"].values()) + "\n")
    return "".join(L)


def _print_train(res):
    print(f"MR EDGE SCREEN — TRAIN  n={res['split']['n_train']} signals, {res['trial_total']} trials, "
          f"baseline ${_f(res['baseline']['mean'])}/trade")
    for c in CAVEATS[:1]:
        print("  NOTE:", c)
    for fam in FAMILIES:
        w = res["winners"][fam]
        f = res["families"][fam]
        print(f"  {fam}: {f['n_trials']} trials, {f['n_passing']} passing -> "
              + (f"WINNER {w['label']} (DSR {w['dsr']:.3f})" if w else "no winner"))
    print(f"  wrote train_results.json + train_report.md")


def _print_holdout(res):
    print(f"MR EDGE SCREEN — HOLDOUT  n={res['split']['n_holdout']} signals, "
          f"baseline ${_f(res['baseline']['mean'])}/trade")
    for fam in FAMILIES:
        t = res["evaluated"].get(fam)
        if t:
            print(f"  {fam}: {t['label']} -> {t['verdict']} (kept n={t['kept']['n']} mean ${_f(t['kept']['mean'])} "
                  f"CI {_ci(t['kept']['ci'])}, WF full {_wf_str(t['wf_full_signs'])})"
                  + (f" reasons: {','.join(t['verdict_reasons'])}" if t['verdict_reasons'] else ""))
        else:
            print(f"  {fam}: not read ({res['not_evaluated'].get(fam)})")
    print(f"  wrote holdout_results.json + holdout_report.md; locks: {', '.join(res['locks'].values()) or 'none'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", required=True, choices=("train", "holdout"))
    ap.add_argument("--signals", default="reports/mr_edge_2026/signals.json")
    ap.add_argument("--prereg", default="docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md")
    ap.add_argument("--out", default="reports/mr_edge_2026/")
    ap.add_argument("--n-boot", type=int, default=N_BOOT_DEFAULT)
    ap.add_argument("--seed", type=int, default=SEED_DEFAULT)
    a = ap.parse_args(argv)
    fn = run_train if a.phase == "train" else run_holdout
    try:
        fn(a.signals, a.prereg, a.out, n_boot=a.n_boot, seed=a.seed)
    except GuardError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
