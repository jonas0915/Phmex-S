#!/usr/bin/env python3
"""Nightly adverse-selection watchdog on main-bot htf_l2 fills.

Reuses the verified scripts/l2x_lab/postentry_drift.py machinery (loaded via
importlib — l2x_lab is not a package) to compute post-entry drift at 1 minute
for REAL htf_l2_anticipation fills opened in the trailing 14 days, then grades
it against the measured baseline:

  baseline  −4.5 bps @ 1m  (148-fill measurement, 2026-07-01, cluster-robust)
  ALERT if  mean(1m drift) < −6.0 bps          (absolute floor)
        or  mean(1m drift) < baseline − 2.0    (= −6.5 bps, deterioration)

Drift sign: + = market moved WITH the trade after entry, − = against
(adverse selection). More negative = worse. n < 3 → "no verdict", no alert.

READ-ONLY vs the bot: reads trading_state.json, fetches public 1m OHLCV via
ccxt into the shared reports/cache_l2x_drift/ cache. Logs to
~/Library/Logs/Phmex-S/drift_watchdog.log (never a ~/Desktop path — launchd
jobs cannot rely on Desktop TCC access).

Usage:
  python3 scripts/lab_adjudicator/drift_watchdog.py               # print status
  python3 scripts/lab_adjudicator/drift_watchdog.py --no-fetch    # cache-only
  python3 scripts/lab_adjudicator/drift_watchdog.py --telegram    # ... and send
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from st2_lab.notify import telegram_alert  # noqa: E402  (stdlib, best-effort)

BOT_DIR = Path(_SCRIPTS_DIR).parent
PD_PATH = Path(_SCRIPTS_DIR) / "l2x_lab" / "postentry_drift.py"
LOG_DIR = Path.home() / "Library" / "Logs" / "Phmex-S"
LOG_FILE = LOG_DIR / "drift_watchdog.log"
PT = ZoneInfo("America/Los_Angeles")

WINDOW_DAYS = 14
BASELINE_BPS = -4.5          # 2026-07-01 measurement (148 fills, cluster CI)
ABS_ALERT_BPS = -6.0         # alert floor
DETERIORATION_BPS = 2.0      # alert if baseline - 2.0 breached (= -6.5)
MIN_N = 3


def classify(mean_1m_bps: float | None, n: int,
             baseline: float = BASELINE_BPS,
             abs_alert: float = ABS_ALERT_BPS,
             deterioration: float = DETERIORATION_BPS) -> tuple[str, str]:
    """(status, reason) for a rolling mean 1m drift. Pure — unit-tested."""
    if mean_1m_bps is None or n < MIN_N:
        return "NO-DATA", f"n={n} < {MIN_N} — no verdict"
    reasons = []
    if mean_1m_bps < abs_alert:
        reasons.append(f"{mean_1m_bps:+.2f} bps < {abs_alert:+.1f} floor")
    if mean_1m_bps < baseline - deterioration:
        reasons.append(f"{mean_1m_bps:+.2f} bps is >{deterioration:.0f} bps "
                       f"worse than {baseline:+.1f} baseline")
    if reasons:
        return "ALERT", "; ".join(reasons)
    return "OK", (f"{mean_1m_bps:+.2f} bps @1m vs {baseline:+.1f} baseline "
                  f"(floor {abs_alert:+.1f})")


def _load_pd():
    """Import scripts/l2x_lab/postentry_drift.py by path (not a package)."""
    spec = importlib.util.spec_from_file_location("l2x_postentry_drift", PD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def measure(window_days: int = WINDOW_DAYS, fetch: bool = True) -> dict:
    """Rolling-window mean 1m post-entry drift on real htf_l2 fills."""
    pd = _load_pd()
    pd.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    trades, phantoms = pd.load_trades()
    now = time.time()
    cutoff = now - window_days * 86400
    recent = [t for t in trades if float(t["opened_at"]) >= cutoff]

    exchange = None
    if fetch:
        import ccxt
        exchange = ccxt.phemex({"enableRateLimit": True})

    drifts, days, uncovered = [], [], 0
    for t in recent:
        entry_ts = float(t["opened_at"])
        if entry_ts + 60 > now - 60:      # 1m horizon not elapsed yet
            continue
        try:
            candles = pd.fetch_window(exchange, t["symbol"], entry_ts)
        except Exception:
            uncovered += 1
            continue
        if not candles:
            uncovered += 1
            continue
        by_min = pd.index_candles(candles)
        price = pd.price_at(by_min, entry_ts, 1)
        if price is None:
            uncovered += 1
            continue
        drifts.append(pd.signed_bps(float(t["entry_price"]), price, t["side"]))
        days.append(time.strftime("%Y-%m-%d", time.gmtime(entry_ts)))

    mean = sum(drifts) / len(drifts) if drifts else None
    ci = pd.boot_ci(drifts) if len(drifts) >= 3 else None
    cci = pd.cluster_boot_ci(drifts, days) if len(drifts) >= 3 else None
    return {"window_days": window_days, "n_recent_trades": len(recent),
            "n_measured": len(drifts), "n_uncovered": uncovered,
            "phantoms_excluded": phantoms,
            "mean_1m_bps": round(mean, 2) if mean is not None else None,
            "ci95_iid": [round(c, 2) for c in ci] if ci else None,
            "ci95_cluster": [round(c, 2) for c in cci] if cci else None}


def build_status(m: dict, now: float | None = None) -> str:
    status, reason = classify(m["mean_1m_bps"], m["n_measured"])
    stamp = datetime.fromtimestamp(now or time.time(),
                                   tz=PT).strftime("%b %-d %-I:%M %p PT")
    ci = (f" iidCI[{m['ci95_iid'][0]:+.1f},{m['ci95_iid'][1]:+.1f}]"
          f" dayCI[{m['ci95_cluster'][0]:+.1f},{m['ci95_cluster'][1]:+.1f}]"
          if m["ci95_iid"] and m["ci95_cluster"] else "")
    return (f"DRIFT WATCHDOG ({stamp}) — {status}: {reason} | "
            f"rolling {m['window_days']}d htf_l2 fills n={m['n_measured']}"
            f" (of {m['n_recent_trades']} recent, {m['n_uncovered']} uncovered)"
            f"{ci}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-fetch", action="store_true",
                    help="cache-only; skip fills without cached candle windows")
    ap.add_argument("--telegram", action="store_true",
                    help="send the status line via the project Telegram bot")
    ap.add_argument("--window-days", type=int, default=WINDOW_DAYS)
    args = ap.parse_args(argv)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(LOG_FILE), level=logging.INFO,
                        format="%(asctime)s [DRIFT-WD] %(message)s")
    log = logging.getLogger("drift_watchdog")

    m = measure(window_days=args.window_days, fetch=not args.no_fetch)
    line = build_status(m)
    print(line)
    log.info(line)

    if args.telegram:
        # attempts=4: survive a dark-wake/DNS blip at 6 AM (waits 15/60/240s)
        ok = telegram_alert("📉 " + line, attempts=4)
        log.info("telegram send: %s", "ok" if ok else "FAILED")
        print(f"(telegram: {'sent' if ok else 'FAILED'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
