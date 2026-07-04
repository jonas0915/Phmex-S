#!/usr/bin/env python3
"""5m_mean_revert fill-experiment watcher — every 5h via launchd (com.phmex.mr-watch).

Replaces the retired ST2.0 watcher (com.phmex.st2-watch, unloaded 2026-07-03)
as the digest for the ACTIVE experiment: the 3-leg fill bundle on the LIVE
5m_mean_revert slot (deployed 7/1-7/3):
  leg 1  RSI floor        — blocks longs when RSI(7) < 22   (counter mr_rsi_floor)
  leg 2  maker re-quote   — one retry at the fresh touch    (requote_fill/miss/abort_*)
  leg 3  45s entry patience — was 20s; waits for the comeback

Digest sections (only sends when something is NEW since the last run):
  1. NEW live trades closed since last check (deduped by closed_at)
  2. Counter deltas from the blocked/counters sidecar (the experiment scoreboard)
  3. Entry attempts / fills / misses seen in bot.log since last run
  4. Demote-headroom status (mode sidecar loss cap vs live net)

NO FABRICATION: every number read from a file same-run; empty sections say so.

Usage:
  python3 scripts/mr_watch.py            # compute + send Telegram, persist state
  python3 scripts/mr_watch.py --dry-run  # print message, send nothing, no state write
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BOT_DIR, ".env"))
except Exception:
    pass

import notifier  # noqa: E402

SLOT_STATE = os.path.join(BOT_DIR, "trading_state_5m_mean_revert.json")
MODE_SIDECAR = os.path.join(BOT_DIR, "trading_state_5m_mean_revert_mode.json")
COUNTERS_SIDECAR = os.path.join(BOT_DIR, "trading_state_5m_mean_revert_blocked.json")
WATCH_STATE = os.path.join(BOT_DIR, ".mr_watch_state.json")
LOG_FILE = os.path.join(BOT_DIR, "logs", "mr_watch.log")
BOT_LOG = os.path.join(BOT_DIR, "logs", "bot.log")

_PT = ZoneInfo("America/Los_Angeles")

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s [MR-WATCH] %(message)s")
logger = logging.getLogger("mr_watch")


def _net(t: dict) -> float:
    v = t.get("net_pnl")
    return float(v) if v is not None else float(t.get("pnl_usdt", 0) or 0)


def _pt_date(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=_PT).strftime("%b %-d %-I:%M %p PT")
    except (ValueError, OverflowError, OSError, TypeError):
        return "?"


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f) or default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def live_trades() -> list[dict]:
    state = _load(SLOT_STATE, {})
    return [t for t in state.get("closed_trades", []) or []
            if t.get("mode") == "live"]


def tail_bot_log(max_bytes: int = 4_000_000) -> str:
    try:
        with open(BOT_LOG, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode(errors="replace")
    except OSError:
        return ""


def build_digest(watch_state: dict) -> tuple[str | None, dict]:
    """Returns (message or None-if-nothing-new, new_watch_state)."""
    now = time.time()
    last_closed = float(watch_state.get("last_closed_at") or 0)
    last_counters = watch_state.get("counters") or {}
    last_run = float(watch_state.get("last_run") or 0)

    lt = live_trades()
    new_trades = sorted((t for t in lt if (t.get("closed_at") or 0) > last_closed),
                        key=lambda t: t.get("closed_at") or 0)
    counters = _load(COUNTERS_SIDECAR, {})
    counter_deltas = {k: counters.get(k, 0) - last_counters.get(k, 0)
                      for k in set(counters) | set(last_counters)
                      if counters.get(k, 0) != last_counters.get(k, 0)}

    # entry activity since last run, from the bot log tail
    log_txt = tail_bot_log()
    attempts = fills = misses = requotes = 0
    ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    for line in log_txt.splitlines():
        if "5m_mean_revert" not in line:
            continue
        m = ts_re.match(line)
        if m:
            try:  # log clock is Mac-local; treat as PT (host home zone)
                lts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=_PT).timestamp()
                if last_run and lts < last_run:
                    continue
            except ValueError:
                pass
        if "[MAKER] Limit" in line:
            attempts += 1
        if "[SLOT LIVE] 5m_mean_revert" in line and "ENTRY" in line:
            fills += 1
        if "no fill (PostOnly miss)" in line:
            misses += 1
        if "[MR REQUOTE]" in line:
            requotes += 1

    nothing_new = (not new_trades and not counter_deltas
                   and attempts == 0 and requotes == 0)
    new_state = {
        "last_closed_at": max([last_closed] + [t.get("closed_at") or 0 for t in lt]),
        "counters": counters,
        "last_run": now,
    }
    if nothing_new:
        return None, new_state

    mode = _load(MODE_SIDECAR, {})
    cap = abs(float(mode.get("loss_cap_usdt") or -5.0))
    live_net = sum(_net(t) for t in lt)
    n_live = len(lt)
    wins = sum(1 for t in lt if _net(t) > 0)

    lines = ["🧪 <b>MR FILL EXPERIMENT</b> (5m_mean_revert, 3-leg)"]
    if new_trades:
        lines.append(f"\n<b>New live trades ({len(new_trades)}):</b>")
        for t in new_trades:
            sym = str(t.get("symbol", "?")).split("/")[0]
            lines.append(f"  {sym} {t.get('side','?')} {_net(t):+.2f} "
                         f"({t.get('exit_reason') or t.get('reason')}, "
                         f"{_pt_date(t.get('closed_at') or 0)})")
    if counter_deltas:
        lines.append("\n<b>Scoreboard deltas:</b> "
                     + " ".join(f"{k}+{v}" if v > 0 else f"{k}{v}"
                                for k, v in sorted(counter_deltas.items())))
    if attempts or requotes or misses or fills:
        lines.append(f"\n<b>Entry activity since last digest:</b> "
                     f"{attempts} attempts · {fills} fills · {misses} misses · "
                     f"{requotes} re-quote events")
    lines.append(f"\n<b>Record:</b> {n_live} live trades, {wins}W · net ${live_net:+.2f}"
                 f" · headroom ${cap + live_net:.2f} of ${cap:.2f} to auto-demote")
    lines.append("Legs: RSI&lt;22 floor · re-quote (15bps cap) · 45s patience")
    return "\n".join(lines), new_state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    watch_state = _load(WATCH_STATE, {})
    msg, new_state = build_digest(watch_state)

    if msg is None:
        logger.info("nothing new — no digest sent")
        if not args.dry_run:
            with open(WATCH_STATE, "w") as f:
                json.dump(new_state, f, indent=2)
        if args.dry_run:
            print("(nothing new — no digest would be sent)")
        return 0

    if args.dry_run:
        print(msg)
        return 0

    notifier.send(msg)
    logger.info("digest sent (%d chars)", len(msg))
    with open(WATCH_STATE, "w") as f:
        json.dump(new_state, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
