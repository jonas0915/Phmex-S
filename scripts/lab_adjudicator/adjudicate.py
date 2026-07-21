#!/usr/bin/env python3
"""Nightly adjudicator for the LIVE forward tests (2026-07-05 build).

Grades each experiment in EXPERIMENTS against its own revert criteria and
prints one status line per experiment: PASS / WATCH / REVERT-TRIPPED.
With tiny n the honest output is "n=0 — no verdict"; nothing is extrapolated.

Experiments graded (registry below is the single source of truth):
  trail_arm_8  TRAIL_ARM_ROI 5.0 -> 8.0, restart 2026-07-05 9:01 PM PT.
               Metrics: avg win of trailing_stop+early_exit exits vs the $0.46
               June baseline; givebacks = trades whose peak ROI reached >= +5%
               (bot-tracked peak_price, 60s sampling — conservative proxy for
               candle-MFE) yet closed at full SL (stop_loss/exchange_close, net<0).
               REVERT-TRIPPED: >= 3 givebacks within the first ~20 trail-relevant
               trades, or avg win < baseline once >= 10 wins exist.
  sizing_15    $15 sizing EFFECTIVE via MIN_TRADE_MARGIN 10 -> 15, restart
               2026-07-05 8:34 PM PT (the 7/4 TRADE_AMOUNT raise never bound).
               Metrics: realized margin/trade (post vs pre, bootstrap diff CI)
               and daily-halt frequency ("DAILY LOSS HALT" lines in bot.log).
               Report-only: no revert criterion was defined for this one.
  mr_bundle    3-leg fill bundle on the 5m_mean_revert slot, 2026-07-03
               7:48 PM PT (PID 61576). Metrics: entry attempts/fills/misses and
               [MR REQUOTE] events from bot.log since deploy, requote/RSI-floor
               counters from the blocked sidecar, live-slot record; fill rate
               vs the 15% baseline with a bootstrap CI.
  eth_tsm_28   ETH-TSM-28 slow-horizon slot (2026-07-06 build, ships paper).
               Kill criteria (pre-registered, spec §9) are graded HERE — the
               slot's own rails are opted out: net vs the −$10 kill line,
               disaster-stop count (2 = revert), replica-tracking error from
               eth_tsm_28_signal.json (>0.1%/day over a full 14d window).
  htf_l2       HTF_L2 slot (2026-07-18, action plan D1; born HTF_L2_PAPER,
               renamed at the 7/20 go-live): htf_l2 as a slot with the F5
               thin∧ADX gate ACTIVE. REPORT-ONLY —
               n, WR vs the 58.8% breakeven, net slot $, thin_adx blocks.
               Kill lines are OWNER-SET pending (go-gate); never auto-trips.
  vwap_cross   VWAP_CROSS slot (2026-07-20): owner-designed 9/15 SMA cross +
               dual session-VWAP filter, PAPER forward test. REPORT-ONLY —
               n, WR vs the 32.9% geometry breakeven, net slot $, blocked
               counters. Kill lines are OWNER-SET pending; never auto-trips.

Statistics reuse scripts/st2_lab/stats.py: bootstrap_diff_ci resamples the two
sides INDEPENDENTLY and sorts the diffs (house lesson — sorting per-side means
first shrinks the CI ~2.4x). One-sample-vs-constant CIs are expressed as
bootstrap_diff_ci(sample, [constant]).

READ-ONLY vs the bot. Logs to ~/Library/Logs/Phmex-S/lab_adjudicator.log
(never a ~/Desktop path — launchd jobs cannot rely on Desktop TCC access).

Usage:
  python3 scripts/lab_adjudicator/adjudicate.py             # print digest
  python3 scripts/lab_adjudicator/adjudicate.py --telegram  # ... and send it
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from st2_lab import stats  # noqa: E402  (bootstrap_diff_ci — house-lesson-safe)
from st2_lab.notify import telegram_alert  # noqa: E402  (stdlib, best-effort)

BOT_DIR = Path(_SCRIPTS_DIR).parent
STATE_FILE = BOT_DIR / "trading_state.json"
MR_STATE_FILE = BOT_DIR / "trading_state_5m_mean_revert.json"
MR_COUNTERS_FILE = BOT_DIR / "trading_state_5m_mean_revert_blocked.json"
BOT_LOG = BOT_DIR / "logs" / "bot.log"

LOG_DIR = Path.home() / "Library" / "Logs" / "Phmex-S"
LOG_FILE = LOG_DIR / "lab_adjudicator.log"

PT = ZoneInfo("America/Los_Angeles")
LEVERAGE = 10.0          # .env LEVERAGE=10; margin-ROI = price move % x leverage
BOOT_SEED = 7            # deterministic CIs run-to-run

PASS, WATCH, REVERT = "PASS", "WATCH", "REVERT-TRIPPED"


def _pt_ts(y, mo, d, h, mi) -> float:
    return datetime(y, mo, d, h, mi, tzinfo=PT).timestamp()


# ── experiments registry ──────────────────────────────────────────────────
# Deploy timestamps verified against logs/bot.log "Bot starting" restarts
# (sizing_15: line 15650; trail_arm_8: line 53105) and the MR memory record.
EXPERIMENTS = {
    "trail_arm_8": {
        "deployed_ts": _pt_ts(2026, 7, 5, 21, 1),
        "giveback_peak_roi_pct": 5.0,
        "full_sl_reasons": ("stop_loss", "exchange_close"),
        "win_reasons": ("trailing_stop", "early_exit"),
        "baseline_avg_win_usd": 0.46,
        "revert_giveback_count": 3,
        "revert_window_trades": 20,
        "min_wins_for_avg_verdict": 10,
    },
    "sizing_15": {
        "deployed_ts": _pt_ts(2026, 7, 5, 20, 34),  # MIN_TRADE_MARGIN 15 restart —
        # the 7/4 10:48 AM TRADE_AMOUNT raise alone never reached trades (Kelly floor)
        "baseline_lookback_trades": 50,
    },
    "mr_bundle": {
        "deployed_ts": _pt_ts(2026, 7, 3, 19, 48),
        "baseline_fill_rate": 0.15,
        "pass_min_attempts": 20,
    },
    # ETH-TSM-28 slow-horizon slot (2026-07-06 build; pre-registered spec
    # docs/overnight-2026-07-05/r5_slow_horizon_research.md §7 + §9 kill criteria).
    # Kill criteria live HERE, not in the slot (rails deliberately opted out):
    #   - cumulative live net <= −$10
    #   - >= 2 disaster-stop exits (stop doing the exiting = not this strategy)
    #   - replica tracking error > 0.1%/day over the trailing 14 days
    #     (approximation of the spec's "2 consecutive weeks" — daily records in
    #     eth_tsm_28_signal.json carry replica vs actual position + close).
    # exchange_close on THIS slot = the −8% disaster stop by construction: the
    # only exchange-resting order it ever places is the stop (no TP, no trail).
    "eth_tsm_28": {
        "deployed_ts": _pt_ts(2026, 7, 6, 4, 0),  # build shipped paper-first; live
        # trades are additionally filtered by mode=="live" so this ts is a window anchor only
        "kill_net_usd": -10.0,
        "kill_disaster_stops": 2,
        "disaster_reasons": ("exchange_close", "disaster_stop", "stop_loss"),
        "tracking_err_daily": 0.001,   # 0.1%/day, spec §9
        "tracking_window_days": 14,
    },
    # HTF_L2 slot (2026-07-18, born HTF_L2_PAPER; renamed at the 7/20
    # go-live): htf_l2_anticipation resurrected as a slot per the 7/17 action
    # plan D1 while the main path stays HALTED.
    # REPORT-ONLY: kill lines are OWNER-SET pending — the owner sets them at
    # the go-gate; nothing here auto-trips, and no threshold is invented.
    # breakeven_wr 58.8% = the fee-inclusive breakeven WR from the 7/16
    # diagnosis (reference_htf_l2_diagnosis_2026-07-16).
    "htf_l2": {
        "deployed_ts": _pt_ts(2026, 7, 18, 0, 0),  # window anchor only — the
        # state file is born at the first post-registration restart, so every
        # trade in it belongs to the probe (no ts filtering needed)
        "breakeven_wr": 0.588,
    },
    # VWAP_CROSS slot (2026-07-20): owner-designed strategy, PAPER forward
    # test. REPORT-ONLY — kill lines are OWNER-SET pending; nothing here
    # auto-trips, and no threshold is invented.
    # breakeven_wr 0.329 is COMPUTED from the slot's own registered geometry,
    # not copied from htf_l2's 58.8% (that number is main-path exit-mix
    # specific). Derivation: SL 1.0% price / TP 2.4% price (config defaults,
    # fixed-% branch — paper slot, no live fill path) and the 0.12%-of-
    # notional round-trip paper fee model (maker 0.01% + taker 0.06% +
    # slippage 0.05% — _close_slot_position / test_paper_fee_model):
    #   win  = +2.40% − 0.12% = +2.28% of notional
    #   loss = −1.00% − 0.12% = −1.12% of notional  (winners ≈ 2.04x losers)
    #   breakeven p: p·2.28 = (1−p)·1.12 → p = 1.12/3.40 = 0.3294 → 0.329
    "vwap_cross": {
        "deployed_ts": _pt_ts(2026, 7, 20, 0, 0),  # window anchor only — the
        # state file is born at the first post-registration restart, so every
        # trade in it belongs to this test (no ts filtering needed)
        "breakeven_wr": 0.329,
    },
}

TSM_STATE_FILE = BOT_DIR / "trading_state_ETH_TSM_28.json"
TSM_SIGNAL_FILE = BOT_DIR / "eth_tsm_28_signal.json"
HTF_L2_STATE_FILE = BOT_DIR / "trading_state_HTF_L2.json"
HTF_L2_COUNTERS_FILE = BOT_DIR / "trading_state_HTF_L2_blocked.json"
VWAP_CROSS_STATE_FILE = BOT_DIR / "trading_state_VWAP_CROSS.json"
VWAP_CROSS_COUNTERS_FILE = BOT_DIR / "trading_state_VWAP_CROSS_blocked.json"


# ── shared helpers ────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f) or default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def load_closed_trades(path=STATE_FILE) -> list[dict]:
    return load_json(path, {}).get("closed_trades", []) or []


def tail_bot_log(path=BOT_LOG, max_bytes: int = 16_000_000) -> str:
    """bot.log PLUS the newest rotated file (bot.log.1) — rotation happens
    ~every 3 days, so a since-deploy window routinely spans the boundary
    (verified 2026-07-05: bot.log.1 = 7/01-7/04, bot.log = 7/04-now)."""
    chunks = []
    for p in (Path(str(path) + ".1"), Path(path)):
        try:
            with open(p, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - max_bytes))
                chunks.append(f.read().decode(errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _line_ts(line: str) -> float | None:
    """bot.log clock is Mac-local; treated as PT (host home zone — house rule)."""
    m = _TS_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=PT).timestamp()
    except ValueError:
        return None


def _net(t: dict) -> float | None:
    v = t.get("net_pnl")
    if v is None:
        v = t.get("pnl_usdt")
    return float(v) if v is not None else None


def peak_roi_pct(trade: dict, leverage: float = LEVERAGE) -> float | None:
    """Margin-ROI at the bot-tracked favorable extreme (risk_manager peak_price
    semantics: max price for longs, min for shorts). None if untracked."""
    entry, peak = trade.get("entry_price"), trade.get("peak_price")
    if not entry or not peak:
        return None
    move = (peak - entry) / entry
    if trade.get("side") == "short":
        move = -move
    return move * leverage * 100.0


def ci_vs_constant(sample, constant, seed=BOOT_SEED):
    """95% bootstrap CI for mean(sample) - constant, via the house
    bootstrap_diff_ci (b=[constant] resamples to itself). None if n < 3."""
    if len(sample) < 3:
        return None
    lo, hi = stats.bootstrap_diff_ci(list(sample), [constant], seed=seed)
    return (round(lo, 4), round(hi, 4))


def _fmt_ci(ci) -> str:
    return f"CI[{ci[0]:+.2f},{ci[1]:+.2f}]" if ci else "CI n/a (n<3)"


# ── experiment graders (pure: data in, verdict dict out) ──────────────────
def grade_trail_arm(trades: list[dict], cfg: dict) -> dict:
    dep = cfg["deployed_ts"]
    post = sorted((t for t in trades if (t.get("opened_at") or 0) >= dep),
                  key=lambda t: t.get("closed_at") or 0)

    def _is_win_exit(t):
        return (t.get("exit_reason") or t.get("reason")) in cfg["win_reasons"]

    def _is_giveback(t):
        roi = peak_roi_pct(t)
        n = _net(t)
        return (roi is not None and roi >= cfg["giveback_peak_roi_pct"]
                and (t.get("exit_reason") or t.get("reason")) in cfg["full_sl_reasons"]
                and n is not None and n < 0)

    relevant = [t for t in post
                if _is_win_exit(t)
                or (peak_roi_pct(t) or 0) >= cfg["giveback_peak_roi_pct"]]
    window = relevant[:cfg["revert_window_trades"]]
    givebacks = sum(1 for t in window if _is_giveback(t))

    wins = [n for t in post if _is_win_exit(t)
            for n in [_net(t)] if n is not None and n > 0]
    avg_win = sum(wins) / len(wins) if wins else None
    ci = ci_vs_constant(wins, cfg["baseline_avg_win_usd"]) if wins else None

    if not post:
        status, note = WATCH, "n=0 — no verdict"
    elif givebacks >= cfg["revert_giveback_count"]:
        status = REVERT
        note = (f"{givebacks} givebacks in first {len(window)} "
                f"trail-relevant trades (limit {cfg['revert_giveback_count']})")
    elif (avg_win is not None and len(wins) >= cfg["min_wins_for_avg_verdict"]
          and avg_win < cfg["baseline_avg_win_usd"]):
        status = REVERT
        note = (f"avg win ${avg_win:.2f} < ${cfg['baseline_avg_win_usd']:.2f} "
                f"baseline at n={len(wins)} wins")
    elif len(relevant) < cfg["revert_window_trades"]:
        status = WATCH
        note = (f"only {len(relevant)}/{cfg['revert_window_trades']} "
                f"trail-relevant trades — no verdict yet")
    else:
        status, note = PASS, f"clean through {len(relevant)} trail-relevant trades"

    return {"experiment": "trail_arm_8", "status": status, "note": note,
            "n_post_deploy": len(post), "n_trail_relevant": len(relevant),
            "givebacks_in_window": givebacks, "n_wins": len(wins),
            "avg_win_usd": round(avg_win, 4) if avg_win is not None else None,
            "avg_win_minus_baseline_ci95": ci,
            "baseline_avg_win_usd": cfg["baseline_avg_win_usd"]}


def grade_sizing(trades: list[dict], log_text: str, cfg: dict,
                 now: float | None = None) -> dict:
    dep = cfg["deployed_ts"]
    now = now or time.time()
    ordered = sorted(trades, key=lambda t: t.get("opened_at") or 0)
    post = [t for t in ordered if (t.get("opened_at") or 0) >= dep]
    pre = [t for t in ordered if (t.get("opened_at") or 0) < dep]
    post_m = [float(t["margin"]) for t in post if t.get("margin")]
    pre_m = [float(t["margin"]) for t in
             pre[-cfg["baseline_lookback_trades"]:] if t.get("margin")]

    diff = ci = None
    if post_m and pre_m:
        diff = sum(post_m) / len(post_m) - sum(pre_m) / len(pre_m)
        if len(post_m) >= 3 and len(pre_m) >= 3:
            lo, hi = stats.bootstrap_diff_ci(post_m, pre_m, seed=BOOT_SEED)
            ci = (round(lo, 4), round(hi, 4))

    # daily halts, deduped per PT date, since deploy
    halt_dates = set()
    for line in log_text.splitlines():
        if "DAILY LOSS HALT" not in line:
            continue
        ts = _line_ts(line)
        if ts is not None and ts >= dep:
            halt_dates.add(datetime.fromtimestamp(ts, tz=PT).date().isoformat())
    days = max((now - dep) / 86400.0, 1e-9)

    if not post_m:
        status, note = WATCH, "n=0 — no verdict"
    else:
        status = WATCH  # report-only: no revert criterion defined for sizing
        binding = diff is not None and ci is not None and ci[0] > 0
        note = ("$15 sizing confirmed in prints" if binding else
                "margins still below $15 — UNEXPECTED after the 7/5 8:34 PM "
                "MIN_TRADE_MARGIN=15 fix; check calculate_kelly_margin clamp")
        if halt_dates:
            note += f"; {len(halt_dates)} daily-halt day(s) since deploy"

    return {"experiment": "sizing_15", "status": status, "note": note,
            "n_post_deploy": len(post_m), "n_pre_baseline": len(pre_m),
            "avg_margin_post": round(sum(post_m) / len(post_m), 3) if post_m else None,
            "avg_margin_pre": round(sum(pre_m) / len(pre_m), 3) if pre_m else None,
            "margin_diff_usd": round(diff, 3) if diff is not None else None,
            "margin_diff_ci95": ci,
            "halt_days": sorted(halt_dates),
            "halts_per_day": round(len(halt_dates) / days, 3)}


def parse_mr_log(log_text: str, since_ts: float) -> dict:
    """Entry activity for the 5m_mean_revert slot since `since_ts`.

    Only slot-tagged lines are countable: the raw `[MAKER] Limit` order line
    carries NO slot name (verified bot.log 2026-07-04 12:19:30), so each
    signal-level attempt is inferred from its terminal outcome instead —
    exactly one `[SLOT LIVE] ... ENTRY` (fill) or one final
    `no fill (PostOnly miss)` line per signal. attempts = fills + misses.
    Re-quote retries ([MR REQUOTE]) are counted separately; a re-quoted miss
    still produces a single final miss line. Lines without a parseable
    timestamp are skipped (can't be attributed to the experiment window)."""
    fills = misses = requotes = 0
    for line in log_text.splitlines():
        if "5m_mean_revert" not in line:
            continue
        ts = _line_ts(line)
        if ts is None or ts < since_ts:
            continue
        if "[SLOT LIVE] 5m_mean_revert" in line and "ENTRY" in line:
            fills += 1
        if "no fill (PostOnly miss)" in line:
            misses += 1
        # only the retry-PLACEMENT line is a re-quote event; the FILLED
        # confirmation, abort, zombie-check and still-resting lines share the
        # [MR REQUOTE] tag (a filled re-quote emits 2 tagged lines — counting
        # per line reported "3 re-quotes" for 2 events on 2026-07-07).
        if "[MR REQUOTE]" in line and " attempt " in line:
            requotes += 1
    return {"attempts": fills + misses, "fills": fills,
            "misses": misses, "requotes": requotes}


def grade_mr_bundle(slot_state: dict, counters: dict, log_text: str,
                    cfg: dict) -> dict:
    dep = cfg["deployed_ts"]
    act = parse_mr_log(log_text, dep)
    live = [t for t in slot_state.get("closed_trades", []) or []
            if t.get("mode") == "live" and (t.get("closed_at") or 0) >= dep]
    nets = [n for t in live for n in [_net(t)] if n is not None]

    rate = ci = None
    if act["attempts"] > 0:
        outcomes = [1.0] * act["fills"] + [0.0] * max(
            act["attempts"] - act["fills"], 0)
        rate = act["fills"] / act["attempts"]
        ci = ci_vs_constant(outcomes, cfg["baseline_fill_rate"])

    if act["attempts"] == 0 and not live:
        status, note = WATCH, "n=0 — no verdict"
    elif act["attempts"] < cfg["pass_min_attempts"]:
        status = WATCH
        note = (f"{act['attempts']}/{cfg['pass_min_attempts']} attempts — "
                f"no verdict yet")
    elif ci is not None and ci[0] > 0:
        status, note = PASS, (f"fill rate {rate:.0%} beats "
                              f"{cfg['baseline_fill_rate']:.0%} baseline (CI>0)")
    else:
        status = WATCH
        note = f"fill rate not yet distinguishable from {cfg['baseline_fill_rate']:.0%}"

    return {"experiment": "mr_bundle", "status": status, "note": note,
            **act,
            "fill_rate": round(rate, 4) if rate is not None else None,
            "fill_rate_minus_baseline_ci95": ci,
            "baseline_fill_rate": cfg["baseline_fill_rate"],
            "sidecar_counters": {k: v for k, v in (counters or {}).items()},
            "n_live_trades": len(live), "live_wins": sum(1 for n in nets if n > 0),
            "live_net_usd": round(sum(nets), 4) if nets else 0.0}


def grade_eth_tsm(slot_state: dict, signal_state: dict, cfg: dict) -> dict:
    """ETH-TSM-28 kill-criteria grader (spec §9, pre-registered):
      REVERT: live net <= kill_net_usd; OR disaster-stop exits >= 2; OR mean
      |live − replica| daily return > 0.1%/day over a FULL trailing 14-day
      window. Otherwise WATCH (a 6-month process-validation test has no early
      PASS). Disaster stops = losing exits whose reason is exchange_close /
      disaster_stop / stop_loss — the −8% stop is the only exchange-resting
      order this slot ever places, so exchange_close on it IS the stop."""
    trades = slot_state.get("closed_trades", []) or []
    live = [t for t in trades if t.get("mode") == "live"]
    nets = [n for t in live for n in [_net(t)] if n is not None]
    net = sum(nets) if nets else 0.0
    disasters = [t for t in live
                 if (t.get("exit_reason") or t.get("reason")) in cfg["disaster_reasons"]
                 and (_net(t) or 0) < 0]

    # Replica-vs-actual daily-return tracking from the signal sidecar. Day t's
    # position earns close[t]/close[t-1]−1 (fees/fills excluded — this measures
    # BEHAVIORAL fidelity, believability bar (b), not cost drag).
    days = (signal_state or {}).get("days", []) or []
    window = cfg["tracking_window_days"]
    recent = days[-(window + 1):]
    diffs, div_days = [], 0
    for prev, cur in zip(recent, recent[1:]):
        try:
            r = float(cur["close"]) / float(prev["close"]) - 1.0
        except (KeyError, TypeError, ZeroDivisionError, ValueError):
            continue
        live_r = r if prev.get("actual_position") else 0.0
        rep_r = r if prev.get("replica_position") else 0.0
        diffs.append(abs(live_r - rep_r))
        if bool(prev.get("actual_position")) != bool(prev.get("replica_position")):
            div_days += 1
    track_err = (sum(diffs) / len(diffs)) if diffs else None
    window_full = len(diffs) >= window

    if not live and not days:
        status, note = WATCH, "n=0 — no verdict"
    elif net <= cfg["kill_net_usd"]:
        status = REVERT
        note = f"net ${net:+.2f} breached the ${cfg['kill_net_usd']:.0f} kill line"
    elif len(disasters) >= cfg["kill_disaster_stops"]:
        status = REVERT
        note = (f"{len(disasters)} disaster-stop exits (limit "
                f"{cfg['kill_disaster_stops']}) — the stop is doing the exiting")
    elif window_full and track_err is not None and track_err > cfg["tracking_err_daily"]:
        status = REVERT
        note = (f"tracking error {track_err*100:.3f}%/day > "
                f"{cfg['tracking_err_daily']*100:.1f}%/day over {len(diffs)}d")
    else:
        status = WATCH  # 6-month process test: no early PASS defined
        note = (f"within kill lines ({len(days)} signal days logged)"
                if days else "no signal days logged yet")

    return {"experiment": "eth_tsm_28", "status": status, "note": note,
            "n_live_trades": len(live),
            "live_net_usd": round(net, 4),
            "kill_net_usd": cfg["kill_net_usd"],
            "disaster_stops": len(disasters),
            "signal_days": len(days),
            "divergence_days_window": div_days,
            "tracking_err_daily": (round(track_err, 6)
                                   if track_err is not None else None),
            "tracking_window_full": window_full,
            "last_day": (days[-1] if days else None)}


def grade_htf_l2(slot_state: dict, counters: dict, cfg: dict) -> dict:
    """HTF_L2 slot grader — REPORT-ONLY (follows grade_eth_tsm's shape).
    Reports n accrued, WR vs the 58.8% fee-inclusive breakeven, net slot $,
    and the thin_adx blocked-counter accrual (the F5 gate firing in the slot).
    Kill lines are OWNER-SET pending: no REVERT/PASS is ever emitted here —
    inventing a threshold the owner never set is exactly the failure mode the
    registry comment forbids."""
    trades = slot_state.get("closed_trades", []) or []
    nets = [n for t in trades for n in [_net(t)] if n is not None]
    wins = sum(1 for n in nets if n > 0)
    wr = (wins / len(nets)) if nets else None
    net = sum(nets) if nets else 0.0
    thin_blocked = int((counters or {}).get("thin_adx", 0) or 0)
    conf_blocked = int((counters or {}).get("ensemble_confidence", 0) or 0)

    if not trades and not thin_blocked and not conf_blocked:
        status, note = WATCH, "n=0 — no verdict"
    else:
        status = WATCH  # report-only: kill lines OWNER-SET pending (go-gate)
        note = "accruing — kill lines OWNER-SET pending, no auto-trip"

    return {"experiment": "htf_l2", "status": status, "note": note,
            "n_trades": len(trades), "wins": wins,
            "wr": round(wr, 4) if wr is not None else None,
            "breakeven_wr": cfg["breakeven_wr"],
            "net_usd": round(net, 4),
            "thin_adx_blocked": thin_blocked,
            "ensemble_blocked": conf_blocked}


def grade_vwap_cross(slot_state: dict, counters: dict, cfg: dict) -> dict:
    """VWAP_CROSS slot grader — REPORT-ONLY (follows grade_htf_l2's shape).
    Reports n accrued, WR vs the 32.9% geometry breakeven (derived in the
    EXPERIMENTS registry comment — NOT invented), net slot $, and the total
    blocked-counter accrual (this slot has no slot-specific gates, so any
    counters are the generic slot gates). Kill lines are OWNER-SET pending:
    no REVERT/PASS is ever emitted here."""
    trades = slot_state.get("closed_trades", []) or []
    nets = [n for t in trades for n in [_net(t)] if n is not None]
    wins = sum(1 for n in nets if n > 0)
    wr = (wins / len(nets)) if nets else None
    net = sum(nets) if nets else 0.0
    blocked_total = sum(int(v or 0) for v in (counters or {}).values())

    if not trades and not blocked_total:
        status, note = WATCH, "n=0 — no verdict"
    else:
        status = WATCH  # report-only: kill lines OWNER-SET pending
        note = "accruing — kill lines OWNER-SET pending, no auto-trip"

    return {"experiment": "vwap_cross", "status": status, "note": note,
            "n_trades": len(trades), "wins": wins,
            "wr": round(wr, 4) if wr is not None else None,
            "breakeven_wr": cfg["breakeven_wr"],
            "net_usd": round(net, 4),
            "blocked_total": blocked_total}


# ── digest ────────────────────────────────────────────────────────────────
def _line_trail(r) -> str:
    avg = (f"avg win ${r['avg_win_usd']:.2f} vs ${r['baseline_avg_win_usd']:.2f} "
           f"base {_fmt_ci(r['avg_win_minus_baseline_ci95'])}"
           if r["avg_win_usd"] is not None
           else f"avg win n/a (0 wins) vs ${r['baseline_avg_win_usd']:.2f} base")
    return (f"[trail_arm_8]  {r['status']} — {r['note']} | "
            f"n={r['n_post_deploy']} post-deploy, "
            f"{r['n_trail_relevant']} trail-relevant, "
            f"{r['givebacks_in_window']} givebacks | {avg}")


def _line_sizing(r) -> str:
    if r["avg_margin_post"] is None:
        m = "margin n/a"
    else:
        d = (f"{r['margin_diff_usd']:+.2f} {_fmt_ci(r['margin_diff_ci95'])}"
             if r["margin_diff_usd"] is not None else "diff n/a")
        m = (f"margin ${r['avg_margin_post']:.2f}/trade post "
             f"(n={r['n_post_deploy']}) vs ${r['avg_margin_pre']:.2f} pre "
             f"(n={r['n_pre_baseline']}), diff {d}")
    return (f"[sizing_15]    {r['status']} — {r['note']} | {m} | "
            f"halts {len(r['halt_days'])} day(s) "
            f"({r['halts_per_day']:.2f}/day)")


def _line_mr(r) -> str:
    rate = (f"{r['fill_rate']:.0%} vs {r['baseline_fill_rate']:.0%} base "
            f"{_fmt_ci(r['fill_rate_minus_baseline_ci95'])}"
            if r["fill_rate"] is not None else "rate n/a")
    side = " ".join(f"{k}={v}" for k, v in sorted(r["sidecar_counters"].items()))
    return (f"[mr_bundle]    {r['status']} — {r['note']} | "
            f"{r['attempts']} attempts · {r['fills']} fills · "
            f"{r['misses']} misses · {r['requotes']} re-quotes | fill {rate} | "
            f"live {r['n_live_trades']} trades {r['live_wins']}W "
            f"${r['live_net_usd']:+.2f} | counters: {side or 'none'}")


def _line_tsm(r) -> str:
    err = (f"track {r['tracking_err_daily']*100:.3f}%/day"
           f"{'' if r['tracking_window_full'] else ' (window not full)'}"
           if r["tracking_err_daily"] is not None else "track n/a")
    last = r.get("last_day") or {}
    sig = ("sig " + ("ON" if last.get("signal_on") else "OFF")
           + (" · pos" if last.get("actual_position") else " · flat")
           if last else "no days yet")
    return (f"[eth_tsm_28]   {r['status']} — {r['note']} | "
            f"live {r['n_live_trades']} trades ${r['live_net_usd']:+.2f} "
            f"(kill {r['kill_net_usd']:.0f}) · {r['disaster_stops']} disaster-stops | "
            f"{r['signal_days']} days · {r['divergence_days_window']} div | {err} | {sig}")


def _line_htf_l2(r) -> str:
    wr = (f"WR {r['wr']*100:.1f}% vs {r['breakeven_wr']*100:.1f}% BE"
          if r["wr"] is not None else f"WR n/a vs {r['breakeven_wr']*100:.1f}% BE")
    return (f"[htf_l2]       {r['status']} — {r['note']} | "
            f"slot {r['n_trades']} trades {r['wins']}W ${r['net_usd']:+.2f} | "
            f"{wr} | thin_adx blocked {r['thin_adx_blocked']} · "
            f"conf<4 blocked {r['ensemble_blocked']}")


def _line_vwap_cross(r) -> str:
    wr = (f"WR {r['wr']*100:.1f}% vs {r['breakeven_wr']*100:.1f}% BE"
          if r["wr"] is not None else f"WR n/a vs {r['breakeven_wr']*100:.1f}% BE")
    return (f"[vwap_cross]   {r['status']} — {r['note']} | "
            f"slot {r['n_trades']} trades {r['wins']}W ${r['net_usd']:+.2f} | "
            f"{wr} | blocked {r['blocked_total']}")


def build_digest(now: float | None = None) -> tuple[str, list[dict]]:
    now = now or time.time()
    trades = load_closed_trades()
    log_text = tail_bot_log()
    results = [
        grade_trail_arm(trades, EXPERIMENTS["trail_arm_8"]),
        grade_sizing(trades, log_text, EXPERIMENTS["sizing_15"], now=now),
        grade_mr_bundle(load_json(MR_STATE_FILE, {}),
                        load_json(MR_COUNTERS_FILE, {}),
                        log_text, EXPERIMENTS["mr_bundle"]),
        grade_eth_tsm(load_json(TSM_STATE_FILE, {}),
                      load_json(TSM_SIGNAL_FILE, {}),
                      EXPERIMENTS["eth_tsm_28"]),
        grade_htf_l2(load_json(HTF_L2_STATE_FILE, {}),
                     load_json(HTF_L2_COUNTERS_FILE, {}),
                     EXPERIMENTS["htf_l2"]),
        grade_vwap_cross(load_json(VWAP_CROSS_STATE_FILE, {}),
                         load_json(VWAP_CROSS_COUNTERS_FILE, {}),
                         EXPERIMENTS["vwap_cross"]),
    ]
    stamp = datetime.fromtimestamp(now, tz=PT).strftime("%b %-d %-I:%M %p PT")
    lines = [f"LAB ADJUDICATOR — live forward tests ({stamp})"]
    lines.append(_line_trail(results[0]))
    lines.append(_line_sizing(results[1]))
    lines.append(_line_mr(results[2]))
    lines.append(_line_tsm(results[3]))
    lines.append(_line_htf_l2(results[4]))
    lines.append(_line_vwap_cross(results[5]))
    return "\n".join(lines), results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--telegram", action="store_true",
                    help="send the digest via the project Telegram bot")
    args = ap.parse_args(argv)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(LOG_FILE), level=logging.INFO,
                        format="%(asctime)s [ADJUDICATOR] %(message)s")
    log = logging.getLogger("lab_adjudicator")

    digest, results = build_digest()
    print(digest)
    for r in results:
        log.info("%s status=%s note=%s", r["experiment"], r["status"], r["note"])
    log.info("digest:\n%s", digest)

    if args.telegram:
        # notify.telegram_alert sends parse_mode=HTML — raw '<' (e.g. "n<3")
        # makes Telegram reject the message, so escape the whole digest.
        # attempts=4: survive a dark-wake/DNS blip at 6 AM (waits 15/60/240s)
        ok = telegram_alert("🧾 " + html.escape(digest), attempts=4)
        log.info("telegram send: %s", "ok" if ok else "FAILED")
        print(f"(telegram: {'sent' if ok else 'FAILED'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
