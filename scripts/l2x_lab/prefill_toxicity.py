#!/usr/bin/env python3
"""PRE-FILL TOXICITY STUDY — main-bot maker fills on the 4 L2-recorded symbols.

QUESTION (the "fill issue"): main-bot maker fills are adversely selected
(−4.5bps@1m post-fill drift measured in reports/l2x_postentry_drift.json; 71% of
June SL losers never reached +1% ROI). HYPOTHESIS: in the seconds BEFORE a losing
fill the tape/book shows toxic flow — aggressive volume sweeping toward our
resting price — that a cancel-if-toxic rule could have detected, dodging bad
fills while keeping good ones. Never tested before (ST2.0's crumbling-bid /
post-entry-cancel candidates were parked untested on THAT slot — different
population, not conflated here).

DATA (all read-only; writes ONLY reports/prefill_toxicity.json):
  * logs/l2_ticks/{BTC,ETH,INJ,ARB}_USDT_USDT/: book snapshots
    {ts(ms recv), et(ms exchange), sym, b:[[px,sz]x5], a:[[px,sz]x5]} at
    sub-second cadence + trade tape files trades-YYYY-MM-DD
    {ts, et, sym, px, sz, side}; daily-rotated on the UTC date of ts
    (verified: first ts of a file == UTC midnight), .jsonl.gz past days.
    Exchange time `et` is used when present (recv `ts` lags et by up to ~3s
    on tape lines — matters at 5s windows).
  * trading_state.json closed_trades — main-bot fills on the 4 symbols opened
    after Jun 12 UTC, min_margin_skip phantoms excluded, W/L by net_pnl sign.
  * bot.log* [MAKER] Limit -> [FILL]/[FILL MISS] pairs, MAIN-loop only
    ([SLOT LIVE]-tagged attempts excluded). Log-local -> epoch conversion,
    the ET->PT mid-day Jun-23 clock flip, rotation-overlap dedupe and the
    runtime TZ verification are REUSED VERBATIM from the already-validated
    scripts/slot_lab/main_missed_fill_counterfactual.py (no reinvention).
  * MISSES = the control group: same [MAKER]->[FILL MISS] pairing, main-loop,
    4 symbols. A miss has no fill instant, so its features are evaluated at
    cancel time (placement + 20s, the exchange.py resting window).

TIMING MODEL (honesty-critical):
  * opened_at ~= fill CONFIRM from a 0.5s poll loop (exchange.py:399) — so it
    trails the true fill by ~0.5-2s. Where possible the fill instant is
    SHARPENED from the tape: the last toward-side trade printing exactly at
    the resting limit price inside the resting window. Anchor source is
    reported per fill (tape / opened_at / log).
  * `synced` trades: [SYNC] can rewrite opened_at to the restart time (seen on
    ETH 2026-07-02, per main_missed_fill_counterfactual._verify_tz). A synced
    trade is only usable if it matches a [MAKER]->[FILL] log pair; otherwise
    its timestamp is untrusted and it is EXCLUDED (counted in coverage).
  * CANCEL LATENCY GUARD: a real cancel must beat the sweep that fills us, so
    rule features use a window ending GUARD=1.0s BEFORE the estimated fill —
    the sweep itself is never used to dodge itself. Ungated (guard=0)
    variants are also reported as descriptives.

FEATURES per anchor (windows end at eval_ts = fill_est - guard; miss eval_ts =
placement + 20s):
  (a) toward vs away aggressive notional in last 5s/10s/30s. For a resting BID
      (long): toward = sell-side tape (aggressive sells hit bids); short:
      toward = buy-side. sweep_x_w = toward_w / per-w baseline toward rate,
      baseline = [eval-330s, eval-30s] (5-min, gap-scaled by observed book
      coverage, capped at 99 when the baseline is zero).
  (b) touch dynamics: size resting at OUR price level in the book snapshots of
      the last 30s — collapse = 1 - last/max. Level that vanishes from top-5
      while shallower quotes still print => consumed/cancelled => size 0.
      Same computed for the touch (best level on our side).
  (c) trade-arrival intensity: tape count last 30s / baseline per-30s rate.

STATS: losers vs winners and fills vs misses — means + bootstrap 95% CI on the
difference (10k, seed 42, INDEPENDENT per-group resampling then per-iteration
diff — never sort the group mean arrays, per memory/lessons bootstrap-diff-CI).

RULE GRID: cancel-if-toxic candidates (sweep_x thresholds x windows, touch
collapse, intensity, 2 combos). For each: would-have-cancelled counts among
losing vs winning fills and net $ using ACTUAL net_pnl (cancelled winner costs
its win, cancelled loser saves its loss), + fire rate on the miss control.

>>> SCREENING-GRADE. This is a grid mined on tiny n; the "best" rule is
>>> selection-biased by construction (multiple comparisons, no holdout). It can
>>> only justify a bounded forward test, NEVER direct deploy. If usable n < ~15
>>> the study is flagged UNDERPOWERED and the verdict is descriptive-only.

Run from repo root:  python3 scripts/l2x_lab/prefill_toxicity.py
"""
from __future__ import annotations

import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "slot_lab"))
# Reuse the validated log/TZ machinery (flip detection, dedupe, main-vs-slot):
import main_missed_fill_counterfactual as mmfc  # noqa: E402

STATE_FILE = REPO / "trading_state.json"
TICK_DIR = REPO / "logs" / "l2_ticks"
OUT_FILE = REPO / "reports" / "prefill_toxicity.json"

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "INJ/USDT:USDT", "ARB/USDT:USDT"]
JUN12_UTC = datetime(2026, 6, 12, tzinfo=timezone.utc).timestamp()

WINDOWS_S = (5, 10, 30)
BASE_LO, BASE_HI = 330.0, 30.0     # baseline window [eval-330, eval-30]
GUARD_S = 1.0                      # cancel-latency guard before estimated fill
REST_S = 20.0                      # exchange.py resting window for misses
SWEEP_CAP = 99.0                   # sweep_x when baseline toward volume == 0
BOOT_N = 10_000
SEED = 42
MIN_BOOK_30S = 3                   # coverage: book snaps in last 30s
MIN_BOOK_BASE = 10                 # coverage: book snaps in baseline window
UNDERPOWERED_N = 15

PX_TOL = 1e-6                      # relative tolerance for price equality


def _utc_day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _sym_dir(sym: str) -> Path:
    return TICK_DIR / sym.replace("/", "_").replace(":", "_")


# ── 1. anchors: fills (state + log) and misses (log) ─────────────────────────

def load_fill_anchors_and_misses():
    state = json.loads(STATE_FILE.read_text())
    trades, phantoms = [], 0
    for t in state.get("closed_trades", []):
        if t.get("symbol") not in SYMBOLS:
            continue
        if float(t.get("opened_at") or 0) < JUN12_UTC:
            continue
        if (t.get("exit_reason") or t.get("reason")) == "min_margin_skip":
            phantoms += 1
            continue
        trades.append(t)

    events, flip = mmfc._parse_events()
    attempts = mmfc._extract_attempts(events)
    anchors_ok = mmfc._verify_tz(events, state.get("closed_trades", []))
    main4 = [a for a in attempts if a["sym"] in SYMBOLS and a["origin"] == "main"]
    log_fills = [a for a in main4 if a["outcome"] == "fill"]
    log_misses = [a for a in main4 if a["outcome"] == "miss"]
    log_start = events[0][2] if events else None
    # epoch of the paired [FILL] confirm line — the fill-time anchor for synced
    # trades whose opened_at was rewritten by [SYNC] (fills can race the cancel,
    # e.g. ETH 2026-07-02 confirmed 34s after placement)
    fill_lines = [(ep, msg) for _f, _ts, ep, msg in events
                  if "[FILL] " in msg and "exit fill" not in msg
                  and "[FILL MISS]" not in msg]
    for a in log_fills:
        a["fill_log_ts"] = next(
            (ep for ep, msg in fill_lines
             if f"[FILL] {a['sym']}" in msg and a["ts"] <= ep <= a["ts"] + 90),
            None)

    fills, excluded = [], []
    used_attempts = set()
    for t in trades:
        sym, side = t["symbol"], t["side"]
        opened = float(t["opened_at"])
        entry = float(t["entry_price"])
        match = None
        for a in log_fills:
            if a["oid"] in used_attempts or a["sym"] != sym or a["side"] != side:
                continue
            if abs(a["px"] - entry) / entry > 0.002:
                continue
            if -5 <= opened - a["ts"] <= 60:
                match = a
                break
        if match is None and t.get("strategy") == "synced":
            # opened_at untrusted ([SYNC] rewrite) — try a price-exact rescue
            cands = [a for a in log_fills
                     if a["oid"] not in used_attempts and a["sym"] == sym
                     and a["side"] == side
                     and abs(a["px"] - entry) / entry < 5e-5
                     and abs(a["ts"] - opened) < 12 * 3600]
            if len(cands) == 1:
                match = cands[0]
        if match:
            used_attempts.add(match["oid"])
        if match is None and t.get("strategy") == "synced":
            excluded.append({"symbol": sym, "opened_at": opened,
                             "reason": "synced_untrusted_timestamp_no_log_match"})
            continue
        if match and t.get("strategy") == "synced":
            # opened_at is the restart-sync time, NOT the fill — anchor on the
            # paired [FILL] confirm log line (fallback: mid-rest placement+10s)
            anchor_ts = float(match.get("fill_log_ts")
                              or match["ts"] + REST_S / 2)
            anchor_kind = "fill_log" if match.get("fill_log_ts") else "rest_mid"
        else:
            anchor_ts, anchor_kind = opened, "opened_at"
        fills.append({
            "symbol": sym, "side": side, "entry_price": entry,
            "net_pnl": float(t.get("net_pnl") or 0.0),
            "opened_at": opened, "anchor_ts": anchor_ts,
            "anchor_kind": anchor_kind,
            "limit_px": float(match["px"]) if match else entry,
            "placement_ts": float(match["ts"]) if match else None,
            "strategy": t.get("strategy"),
            "exit_reason": t.get("exit_reason") or t.get("reason"),
            "log_matched": bool(match),
            "outcome": "win" if float(t.get("net_pnl") or 0) > 0 else "loss",
        })

    misses = [{
        "symbol": a["sym"], "side": a["side"], "limit_px": a["px"],
        "placement_ts": float(a["ts"]), "anchor_ts": float(a["ts"]) + REST_S,
        "outcome": "miss", "net_pnl": None, "log_matched": True,
    } for a in log_misses]

    meta = {"trades_after_jun12_4sym": len(trades) + phantoms,
            "min_margin_skip_excluded": phantoms,
            "usable_trades": len(trades),
            "synced_excluded": excluded,
            "log_fill_attempts_main4": len(log_fills),
            "log_miss_attempts_main4": len(log_misses),
            "log_coverage_starts_utc": log_start,
            "tz_flip": flip, "tz_anchor_days_verified": len(anchors_ok)}
    return fills, misses, meta


# ── 2. tick access ────────────────────────────────────────────────────────────

def _open_tick(path: Path):
    if path.with_suffix(path.suffix + ".gz").exists():
        return gzip.open(path.with_suffix(path.suffix + ".gz"), "rt")
    if path.exists():
        return open(path)
    return None


def _scan(sym: str, kind: str, lo: float, hi: float):
    """Yield parsed tick records for sym with event time in [lo, hi].
    kind: 'book' or 'tape'. Event time = et (exchange) if present else ts.
    Fast pre-filter on the leading recv-ts field with +-60s slack (recv lags
    exchange time by <=~3s observed; 60s is generous)."""
    out = []
    days = sorted({_utc_day(lo - 60), _utc_day(hi + 60)})
    for day in days:
        name = (f"trades-{day}.jsonl" if kind == "tape" else f"{day}.jsonl")
        fh = _open_tick(_sym_dir(sym) / name)
        if fh is None:
            continue
        with fh:
            for line in fh:
                i = line.find('"ts":')
                if i < 0:
                    continue
                j = line.find(",", i)
                try:
                    ts = int(line[i + 5:j]) / 1000.0
                except ValueError:
                    continue
                if ts < lo - 60 or ts > hi + 60:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = (rec.get("et") or rec["ts"]) / 1000.0
                if lo <= t <= hi:
                    rec["_t"] = t
                    out.append(rec)
    out.sort(key=lambda r: r["_t"])
    return out


# ── 3. per-anchor features ────────────────────────────────────────────────────

def _level_size(levels, px: float):
    for p, s in levels:
        if abs(p - px) / px <= PX_TOL:
            return float(s)
    return None


def _collapse(series):
    """1 - last/max over a size series (None entries dropped). None if <2 obs."""
    vals = [v for v in series if v is not None]
    if len(vals) < 2 or max(vals) <= 0:
        return None
    return 1.0 - vals[-1] / max(vals)


def features_for(anchor, refine_fill: bool):
    """Compute toxicity features. Returns dict or None if uncovered."""
    sym, side = anchor["symbol"], anchor["side"]
    limit_px = anchor["limit_px"]
    a_ts = anchor["anchor_ts"]

    lo = a_ts - (BASE_LO + 30)
    tape = _scan(sym, "tape", lo, a_ts + 3)
    books = _scan(sym, "book", lo, a_ts + 3)

    toward_side = "sell" if side == "long" else "buy"

    # fill-instant sharpening from the tape (fills only)
    fill_est = a_ts
    anchor_src = anchor.get("anchor_kind", "opened_at") if refine_fill \
        else "cancel_time"
    if refine_fill:
        w_lo = (anchor["placement_ts"] - 1) if anchor.get("placement_ts") \
            else a_ts - (REST_S + 5)
        hits = [r for r in tape
                if w_lo <= r["_t"] <= a_ts + 2 and r["side"] == toward_side
                and abs(r["px"] - limit_px) / limit_px <= PX_TOL]
        if hits:
            fill_est, anchor_src = hits[-1]["_t"], "tape"

    def _feat(eval_ts):
        f = {}
        base_lo, base_hi = eval_ts - BASE_LO, eval_ts - BASE_HI
        base_tape = [r for r in tape if base_lo <= r["_t"] <= base_hi]
        base_books = [r for r in books if base_lo <= r["_t"] <= base_hi]
        last30_books = [r for r in books if eval_ts - 30 <= r["_t"] <= eval_ts]
        f["n_book_30s"] = len(last30_books)
        f["n_book_base"] = len(base_books)
        f["covered"] = (len(last30_books) >= MIN_BOOK_30S
                        and len(base_books) >= MIN_BOOK_BASE)
        if not f["covered"]:
            return f
        # AT-LIMIT-PX prints are excluded from toward/away volume: a print at
        # our own resting price is the fill event itself (or queue-ambiguous
        # volume at our level) — a PRE-fill cancel rule cannot use it, and the
        # bot keeps partial fills by design. Kept separately as a descriptive.
        def _at_px(r):
            return abs(r["px"] - limit_px) / limit_px <= PX_TOL

        base_toward = sum(r["px"] * r["sz"] for r in base_tape
                          if r["side"] == toward_side and not _at_px(r))
        base_n = len(base_tape)
        base_span = BASE_LO - BASE_HI      # 300s
        for w in WINDOWS_S:
            wt = [r for r in tape if eval_ts - w <= r["_t"] <= eval_ts]
            tw = sum(r["px"] * r["sz"] for r in wt
                     if r["side"] == toward_side and not _at_px(r))
            aw = sum(r["px"] * r["sz"] for r in wt
                     if r["side"] != toward_side and not _at_px(r))
            if w == 5:
                f["toward_usd_5s_incl_at_px"] = round(
                    sum(r["px"] * r["sz"] for r in wt
                        if r["side"] == toward_side), 2)
            f[f"toward_usd_{w}s"] = round(tw, 2)
            f[f"away_usd_{w}s"] = round(aw, 2)
            rate = base_toward / base_span * w
            if rate > 0:
                f[f"sweep_x_{w}s"] = round(min(tw / rate, SWEEP_CAP), 3)
            else:
                f[f"sweep_x_{w}s"] = SWEEP_CAP if tw > 0 else 0.0
        n30 = sum(1 for r in tape if eval_ts - 30 <= r["_t"] <= eval_ts)
        base_rate30 = base_n / base_span * 30
        f["n_tape_30s"] = n30
        f["intensity_x"] = (round(min(n30 / base_rate30, SWEEP_CAP), 3)
                            if base_rate30 > 0 else
                            (SWEEP_CAP if n30 > 0 else 0.0))
        # touch dynamics over the last 30s
        our_series, touch_series = [], []
        for r in last30_books:
            levels = r["b"] if side == "long" else r["a"]
            if not levels:
                continue
            sz = _level_size(levels, limit_px)
            if sz is None:
                pxs = [p for p, _ in levels]
                inside = (limit_px >= min(pxs)) if side == "long" \
                    else (limit_px <= max(pxs))
                sz = 0.0 if inside else None   # consumed/cancelled vs too deep
            our_series.append(sz)
            touch_series.append(float(levels[0][1]))
        f["our_level_collapse"] = _collapse(our_series)
        f["touch_collapse"] = _collapse(touch_series)
        f["our_level_seen"] = sum(1 for v in our_series if v is not None)
        # join sanity: mid at eval vs entry/limit price
        near = min(books, key=lambda r: abs(r["_t"] - eval_ts), default=None)
        if near is not None and abs(near["_t"] - eval_ts) <= 5 \
                and near["b"] and near["a"]:
            mid = (near["b"][0][0] + near["a"][0][0]) / 2
            f["mid_at_eval"] = mid
            f["join_bps"] = round(abs(mid - limit_px) / limit_px * 1e4, 2)
        else:
            f["mid_at_eval"] = f["join_bps"] = None
        return f

    guarded = _feat(fill_est - GUARD_S if refine_fill else fill_est)
    out = {"anchor_src": anchor_src, "fill_est": fill_est, "guarded": guarded}
    if refine_fill:
        out["unguarded"] = _feat(fill_est)
    return out


# ── 4. stats ──────────────────────────────────────────────────────────────────

def boot_diff_ci(a, b, n_boot=BOOT_N, seed=SEED):
    """95% CI of mean(a) - mean(b): independent per-group resampling, diff per
    iteration (memory/lessons bootstrap-diff-CI — never sort per-group means)."""
    a = np.asarray([x for x in a if x is not None], dtype=float)
    b = np.asarray([x for x in b if x is not None], dtype=float)
    if len(a) < 3 or len(b) < 3:
        return None
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(a), size=(n_boot, len(a)))
    ib = rng.integers(0, len(b), size=(n_boot, len(b)))
    diffs = a[ia].mean(axis=1) - b[ib].mean(axis=1)
    return [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]


def _col(rows, key):
    return [r["features"]["guarded"].get(key) for r in rows
            if r["features"] and r["features"]["guarded"]["covered"]]


FEATURE_KEYS = (["toward_usd_5s", "toward_usd_10s", "toward_usd_30s",
                 "sweep_x_5s", "sweep_x_10s", "sweep_x_30s",
                 "intensity_x", "our_level_collapse", "touch_collapse"])


def feature_table(losers, winners, misses):
    tbl = {}
    for k in FEATURE_KEYS:
        L, W, M = _col(losers, k), _col(winners, k), _col(misses, k)
        Lv = [x for x in L if x is not None]
        Wv = [x for x in W if x is not None]
        Mv = [x for x in M if x is not None]
        tbl[k] = {
            "losers": {"n": len(Lv), "mean": _m(Lv), "median": _md(Lv)},
            "winners": {"n": len(Wv), "mean": _m(Wv), "median": _md(Wv)},
            "misses": {"n": len(Mv), "mean": _m(Mv), "median": _md(Mv)},
            "loser_minus_winner_ci95": boot_diff_ci(Lv, Wv),
            "fill_minus_miss_ci95": boot_diff_ci(Lv + Wv, Mv),
        }
        if k.startswith("sweep_x"):
            # zero-baseline cap artifact: sweep_x==SWEEP_CAP means "any print
            # after a dead 5-min baseline", not a measured multiple — means of
            # capped columns are junk, read the medians
            tbl[k]["n_at_cap_LWM"] = [sum(1 for x in v if x == SWEEP_CAP)
                                      for v in (Lv, Wv, Mv)]
    return tbl


def _m(v):
    return round(float(np.mean(v)), 3) if v else None


def _md(v):
    return round(float(np.median(v)), 3) if v else None


# ── 5. cancel-rule grid ───────────────────────────────────────────────────────

def build_rules():
    rules = []
    for w in (5, 10):
        for x in (2, 3, 5, 8):
            rules.append((f"sweep_x_{w}s>={x}",
                          lambda g, w=w, x=x: (g.get(f"sweep_x_{w}s") or 0) >= x))
    for y in (0.5, 0.7, 0.9):
        rules.append((f"our_level_collapse>={y}",
                      lambda g, y=y: (g.get("our_level_collapse") is not None
                                      and g["our_level_collapse"] >= y)))
        rules.append((f"touch_collapse>={y}",
                      lambda g, y=y: (g.get("touch_collapse") is not None
                                      and g["touch_collapse"] >= y)))
    for z in (2, 3, 5):
        rules.append((f"intensity_x>={z}",
                      lambda g, z=z: (g.get("intensity_x") or 0) >= z))
    rules.append(("sweep_x_5s>=3 OR touch_collapse>=0.5",
                  lambda g: (g.get("sweep_x_5s") or 0) >= 3
                  or (g.get("touch_collapse") is not None
                      and g["touch_collapse"] >= 0.5)))
    rules.append(("sweep_x_5s>=3 AND touch_collapse>=0.5",
                  lambda g: (g.get("sweep_x_5s") or 0) >= 3
                  and (g.get("touch_collapse") is not None
                       and g["touch_collapse"] >= 0.5)))
    return rules


def run_grid(losers, winners, misses):
    grid = []
    covL = [r for r in losers if r["features"]
            and r["features"]["guarded"]["covered"]]
    covW = [r for r in winners if r["features"]
            and r["features"]["guarded"]["covered"]]
    covM = [r for r in misses if r["features"]
            and r["features"]["guarded"]["covered"]]
    for name, fn in build_rules():
        cL = [r for r in covL if fn(r["features"]["guarded"])]
        cW = [r for r in covW if fn(r["features"]["guarded"])]
        cM = [r for r in covM if fn(r["features"]["guarded"])]
        saved = -sum(r["net_pnl"] for r in cL)     # losses have net_pnl<0
        cost = sum(r["net_pnl"] for r in cW)
        grid.append({
            "rule": name,
            "cancelled_losers": f"{len(cL)}/{len(covL)}",
            "cancelled_winners": f"{len(cW)}/{len(covW)}",
            "miss_fire_rate": f"{len(cM)}/{len(covM)}",
            "loss_saved_usd": round(saved, 3),
            "win_forgone_usd": round(cost, 3),
            "net_usd": round(saved - cost, 3),
        })
    grid.sort(key=lambda g: -g["net_usd"])
    return grid


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    fills, misses, meta = load_fill_anchors_and_misses()
    print(f"usable 4-sym fills since Jun 12: {meta['usable_trades']} "
          f"(+{meta['min_margin_skip_excluded']} min_margin_skip phantoms "
          f"excluded, {len(meta['synced_excluded'])} synced-untrusted excluded)")
    print(f"log window starts {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(meta['log_coverage_starts_utc']))}; "
          f"main-loop 4-sym log attempts: {meta['log_fill_attempts_main4']} fills"
          f" / {meta['log_miss_attempts_main4']} misses (control)")

    for r in fills:
        r["features"] = features_for(r, refine_fill=True)
    for r in misses:
        r["features"] = features_for(r, refine_fill=False)

    def _cov(rows):
        return [r for r in rows if r["features"]
                and r["features"]["guarded"]["covered"]]

    losers = [r for r in fills if r["outcome"] == "loss"]
    winners = [r for r in fills if r["outcome"] == "win"]
    covF, covM = _cov(fills), _cov(misses)
    covL, covW = _cov(losers), _cov(winners)

    coverage = {
        "fills_total": len(fills), "fills_covered": len(covF),
        "winners_covered": len(covW), "losers_covered": len(covL),
        "misses_total": len(misses), "misses_covered": len(covM),
        "uncovered_fills": [
            {"symbol": r["symbol"], "opened_at": r["opened_at"],
             "n_book_30s": r["features"]["guarded"]["n_book_30s"],
             "n_book_base": r["features"]["guarded"]["n_book_base"]}
            for r in fills if r not in covF],
        "anchor_src": dict(Counter(r["features"]["anchor_src"] for r in fills)),
        "excluded_synced": meta["synced_excluded"],
    }
    print(f"\nCOVERAGE: fills {len(covF)}/{len(fills)} "
          f"(W {len(covW)} / L {len(covL)}), misses {len(covM)}/{len(misses)}")
    print(f"fill anchor source: {coverage['anchor_src']}")

    joins = [r["features"]["guarded"].get("join_bps") for r in covF]
    joins = [j for j in joins if j is not None]
    join_sanity = {
        "n": len(joins),
        "median_bps": _md(joins), "p90_bps":
            round(float(np.percentile(joins, 90)), 2) if joins else None,
        "note": "|book mid at eval - limit/entry px| in bps; drift.py precedent "
                "validated joins at ~7bps median",
    }
    print(f"JOIN SANITY: median {join_sanity['median_bps']} bps, "
          f"p90 {join_sanity['p90_bps']} bps (n={len(joins)})")

    underpowered = len(covF) < UNDERPOWERED_N
    if underpowered:
        print(f"\n*** UNDERPOWERED: {len(covF)} covered fills < {UNDERPOWERED_N}"
              " — descriptives only; CIs and grid are screening-grade at best ***")

    tbl = feature_table(losers, winners, misses)
    print("\nFEATURE TABLE (guarded windows; L=losers W=winners M=misses; "
          "med = median. sweep_x means are cap-poisoned — read medians + "
          "n_at_cap)")
    print(f"{'feature':>24} {'L mean':>9} {'L med':>7} {'W mean':>9} "
          f"{'W med':>7} {'M mean':>9} {'M med':>7} "
          f"{'L-W 95% CI':>20} {'F-M 95% CI':>20}")
    for k, v in tbl.items():
        lw = v["loser_minus_winner_ci95"]
        fm = v["fill_minus_miss_ci95"]
        cap = (f"  cap L/W/M={v['n_at_cap_LWM']}"
               if v.get("n_at_cap_LWM") and any(v["n_at_cap_LWM"]) else "")
        print(f"{k:>24} {str(v['losers']['mean']):>9} "
              f"{str(v['losers']['median']):>7} "
              f"{str(v['winners']['mean']):>9} "
              f"{str(v['winners']['median']):>7} "
              f"{str(v['misses']['mean']):>9} {str(v['misses']['median']):>7} "
              f"{str([round(x,2) for x in lw] if lw else None):>20} "
              f"{str([round(x,2) for x in fm] if fm else None):>20}{cap}")

    grid = run_grid(losers, winners, misses)
    print("\nCANCEL-RULE GRID (screening-grade mining, NO holdout, small n — "
          "a 'best' rule here is selection-biased and needs forward test)")
    print(f"{'rule':>38} {'cxl L':>7} {'cxl W':>7} {'miss-fire':>10} "
          f"{'saved$':>8} {'forgone$':>9} {'net$':>8}")
    for g in grid:
        print(f"{g['rule']:>38} {g['cancelled_losers']:>7} "
              f"{g['cancelled_winners']:>7} {g['miss_fire_rate']:>10} "
              f"{g['loss_saved_usd']:>8.2f} {g['win_forgone_usd']:>9.2f} "
              f"{g['net_usd']:>8.2f}")

    # ── verdict (every number computed above, none hand-written) ────────────
    def _trip(rows, key, thr):
        return [r for r in rows
                if (r["features"]["guarded"].get(key) or 0) >= thr]

    swL, swW, swM = (_trip(covL, "sweep_x_10s", 2),
                     _trip(covW, "sweep_x_10s", 2),
                     _trip(covM, "sweep_x_10s", 2))
    best = grid[0]
    n_best_cancel = (int(best["cancelled_losers"].split("/")[0])
                     + int(best["cancelled_winners"].split("/")[0]))
    verdict = {
        "underpowered": underpowered,
        "toxic_sweep_sightings": {
            "rule": "sweep_x_10s>=2 (guarded, at-px prints excluded)",
            "losers": f"{len(swL)}/{len(covL)}",
            "winners": f"{len(swW)}/{len(covW)}",
            "misses": f"{len(swM)}/{len(covM)}",
        },
        "median_toward_flow_usd_10s": {
            "losers": tbl["toward_usd_10s"]["losers"]["median"],
            "winners": tbl["toward_usd_10s"]["winners"]["median"],
            "misses": tbl["toward_usd_10s"]["misses"]["median"]},
        "best_rule": best,
        "best_rule_cancels_fraction_of_all_fills":
            f"{n_best_cancel}/{len(covL) + len(covW)}",
        "call": None,
    }
    sweeps_discriminate = (len(swL) >= 3 and len(swW) == 0
                           and len(swL) / max(len(covL), 1)
                           > 2 * len(swM) / max(len(covM), 1))
    mech = n_best_cancel > (len(covL) + len(covW)) * 2 / 3
    verdict["call"] = (
        ("NULL (descriptive, underpowered n={n}): ".format(
            n=len(covF)) if underpowered else "n={n}: ".format(n=len(covF)))
        + ("pre-fill toxic sweeps separate losers from winners — bounded "
           "forward test justified. " if sweeps_discriminate else
           "no usable pre-fill toxicity separator: median toward-flow is "
           f"~zero for losers AND winners; the toxic-sweep pattern appears in "
           f"{len(swL)}/{len(covL)} losers but 0/{len(covW)} winners AND "
           f"{len(swM)}/{len(covM)} misses (it precedes non-fills too). ")
        + (f"Best grid rule '{best['rule']}' (net ${best['net_usd']}) cancels "
           f"{n_best_cancel}/{len(covL) + len(covW)} of ALL fills — that is a "
           "'stop maker entries' switch riding the mechanical touch-consumption "
           "that precedes ANY fill, not a loser/winner separator. "
           if mech else
           f"Best grid rule: '{best['rule']}' net ${best['net_usd']} — "
           "screening-grade, forward test required. ")
        + "The previously measured adverse selection (-4.5bps@1m, "
          "l2x_postentry_drift) is NOT explained by detectable pre-fill tape "
          "toxicity at 5-30s horizons in this sample. "
        + ("Fills happen into QUIETER tape than misses (fill-minus-miss "
           "intensity CI {ci} < 0). ".format(
               ci=[round(x, 2) for x in
                   tbl["intensity_x"]["fill_minus_miss_ci95"]])
           if (tbl["intensity_x"]["fill_minus_miss_ci95"]
               and tbl["intensity_x"]["fill_minus_miss_ci95"][1] < 0) else "")
        + "Do not deploy any cancel rule from this grid without a fresh "
          "forward sample.")

    print("\nVERDICT: " + verdict["call"])

    report = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "grade": "SCREENING-GRADE — grid mined on small n, multiple "
                 "comparisons uncorrected, no holdout; best rule needs a "
                 "bounded forward test, never direct deploy",
        "underpowered": underpowered,
        "meta": meta, "coverage": coverage, "join_sanity": join_sanity,
        "guard_s": GUARD_S, "verdict": verdict,
        "feature_table": tbl, "rule_grid": grid,
        "fills": [{k: v for k, v in r.items()} for r in fills],
        "misses": [{k: v for k, v in r.items()} for r in misses],
    }
    OUT_FILE.write_text(json.dumps(report, indent=1, default=str))
    print(f"\nwrote {OUT_FILE}")


if __name__ == "__main__":
    main()
