#!/usr/bin/env python3
"""ST2.0 bounded-experiment watcher — runs every 5h via launchd (com.phmex.st2-watch).

Sends a Telegram digest covering the live ST2.0 fill-data experiment:
  1. NEW live ST2.0 trades closed since the last check (deduped by closed_at)
  2. −$10 budget / auto-demote status (reads the mode sidecar + live net)
  3. Maker fill rate (from bot.log; honest "n/a" when no attempts logged)
  4. Real-trade diagnostics activation progress (needs >= 30 live trades)
  5. NEW st2-lab fix-proposals (docs/fix-proposals/st2-lab-*.md)

This is LOCAL-only: the data sources (trading_state_ST2.0*.json, logs/bot.log,
docs/fix-proposals/) are local + gitignored, so a cloud /schedule agent can't see
them — hence a launchd job on this machine.

NO FABRICATION: every number is read from a file same-run; when a section has no
data it says so explicitly ("none yet"), never invents a value.

Usage:
  python3 scripts/st2_watch.py            # compute + send Telegram, persist state
  python3 scripts/st2_watch.py --dry-run  # print the message, send nothing, no state write
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# ── BOT_DIR is immune to launchd's WorkingDirectory; lets us import bot modules ──
BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)

# Load .env BEFORE importing notifier (it reads TELEGRAM_* from the environment)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BOT_DIR, ".env"))
except Exception:
    pass

import notifier  # noqa: E402
from scripts.st2_lab import fills, real_trades  # noqa: E402

# ── paths ──────────────────────────────────────────────────────────────────
ST2_STATE = os.path.join(BOT_DIR, "trading_state_ST2.0.json")
MODE_SIDECAR = os.path.join(BOT_DIR, "trading_state_ST2.0_mode.json")
PROPOSALS_GLOB = os.path.join(BOT_DIR, "docs", "fix-proposals", "st2-lab-*.md")
WATCH_STATE = os.path.join(BOT_DIR, ".st2_watch_state.json")
LOG_FILE = os.path.join(BOT_DIR, "logs", "st2_watch.log")

# Real-trade diagnostics mine loss clusters once >= this many live trades exist
# (diagnostics.MIN_SUPPORT=20 + MIN_VETOED=10 → 30; mirrored here so the watcher
# never imports the bot/exchange. Kept in sync with scripts/st2_lab/diagnostics.py).
REAL_DIAG_THRESHOLD = 30

_PT = timezone(timedelta(hours=-7))  # PDT (June); matches st2_lab/real_trades.py

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [ST2-WATCH] %(message)s",
)
logger = logging.getLogger("st2_watch")


# ── helpers ─────────────────────────────────────────────────────────────────
def _net(t: dict) -> float:
    v = t.get("net_pnl")
    return float(v) if v is not None else float(t.get("pnl_usdt", 0) or 0)


def _pt(ts: float) -> str:
    """Unix → '3:46 PM PT' (12-hour, per house style). '?' on bad input."""
    try:
        return datetime.fromtimestamp(float(ts), tz=_PT).strftime("%-I:%M %p PT")
    except (ValueError, OverflowError, OSError, TypeError):
        return "?"


def _pt_date(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts), tz=_PT).strftime("%b %-d %-I:%M %p PT")
    except (ValueError, OverflowError, OSError, TypeError):
        return "?"


def load_watch_state() -> dict:
    if not os.path.exists(WATCH_STATE):
        return {}
    try:
        with open(WATCH_STATE) as f:
            return json.load(f) or {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"watch state unreadable, treating as empty: {e}")
        return {}


def save_watch_state(state: dict) -> None:
    try:
        with open(WATCH_STATE, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        logger.warning(f"failed to persist watch state: {e}")


def load_live_trades() -> list[dict]:
    """All closed ST2.0 trades with mode == 'live' (real money), as raw records."""
    if not os.path.exists(ST2_STATE):
        return []
    try:
        ct = json.load(open(ST2_STATE)).get("closed_trades", [])
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"ST2.0 state unreadable: {e}")
        return []
    return [t for t in ct if t.get("mode") == "live"]


def load_mode() -> dict:
    if not os.path.exists(MODE_SIDECAR):
        return {}
    try:
        return json.load(open(MODE_SIDECAR)) or {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"mode sidecar unreadable: {e}")
        return {}


# ── report sections (each returns (lines: list[str], is_news: bool)) ─────────
def section_trades(live: list[dict], prev_last_closed: float, first_run: bool):
    """New live trades since last check. On first run, baseline silently."""
    if first_run:
        n = len(live)
        return [f"<b>New trades:</b> baselined ({n} live trade(s) on record)"], False
    new = sorted((t for t in live if float(t.get("closed_at", 0) or 0) > prev_last_closed),
                 key=lambda t: float(t.get("closed_at", 0) or 0))
    if not new:
        return ["<b>New trades:</b> none since last check"], False
    lines = [f"<b>New trades:</b> {len(new)} closed"]
    for t in new:
        sym = (t.get("symbol", "?") or "?").split("/")[0]
        side = (t.get("side", "?") or "?").upper()
        net = _net(t)
        rsn = t.get("exit_reason") or t.get("reason") or ""
        lines.append(f"  • {side} {sym} {net:+.2f} @ {_pt(t.get('closed_at', 0))}"
                     + (f" ({rsn})" if rsn else ""))
    return lines, True


def section_budget(live: list[dict], mode: dict):
    """−$10 budget / demote status from the mode sidecar + live net."""
    paper = mode.get("paper_mode")
    cap = float(mode.get("loss_cap_usdt", -10.0) or -10.0)
    amt = mode.get("trade_amount_usdt", "?")
    kmin = mode.get("kelly_min_trades", "?")
    n = len(live)
    net = sum(_net(t) for t in live)
    room = net - cap  # how far above the cap (positive = still has room)
    used_pct = (abs(net) / abs(cap) * 100) if cap else 0.0

    if paper is True:
        status = "⚠️ DEMOTED → paper"
    elif paper is False:
        status = "🟢 LIVE"
    else:
        status = "❓ unknown (no sidecar)"

    lines = [f"<b>Status:</b> {status}"]
    lines.append(f"  budget: net ${net:+.2f} / cap ${cap:.2f} → "
                 f"${room:+.2f} room ({used_pct:.0f}% used)")
    lines.append(f"  rails: ${amt}/trade, neg-Kelly arms @ {kmin} live (now {n})")
    # Headline a breach even if the demote flip hasn't been written yet
    is_news = paper is True or net <= cap
    return lines, is_news


def section_fills():
    """Maker fill rate from bot.log. Honest n/a when no attempts are logged."""
    try:
        s = fills.measured_fill_stats()
    except Exception as e:
        logger.warning(f"fill stats failed: {e}")
        return ["<b>Fill rate:</b> n/a (stats error)"], False
    att = s.get("attempts", 0)
    if not att:
        return ["<b>Fill rate:</b> n/a (no entry attempts in current bot.log)"], False
    rate = s.get("rate", 0.0)
    return [f"<b>Fill rate:</b> {rate*100:.0f}% ({s.get('fills',0)}/{att} attempts)"], False


def section_real_diag(live: list[dict]):
    """Progress toward real-trade diagnostics activation (>= 30 live trades)."""
    n = len(live)
    summ = real_trades.real_summary(real_trades.load_real_trades())
    exp = summ.get("expectancy", 0.0)
    wr = summ.get("wr", 0.0)
    if n >= REAL_DIAG_THRESHOLD:
        head = f"<b>Real-diag:</b> ✅ ACTIVE ({n}/{REAL_DIAG_THRESHOLD} live)"
    else:
        head = (f"<b>Real-diag:</b> collecting — {n}/{REAL_DIAG_THRESHOLD} live "
                f"({REAL_DIAG_THRESHOLD - n} more)")
    detail = (f"  real expectancy {exp:+.3f}/trade, WR {wr*100:.0f}% "
              f"({summ.get('wins',0)}W/{summ.get('losses',0)}L)")
    # News when it crosses the activation line
    return [head, detail], n >= REAL_DIAG_THRESHOLD


def section_proposals(seen: list[str]):
    """New st2-lab fix-proposals since last check."""
    found = sorted(os.path.basename(p) for p in glob.glob(PROPOSALS_GLOB))
    new = [p for p in found if p not in set(seen)]
    if not found:
        return ["<b>Proposals:</b> none yet"], False, found
    if not new:
        return [f"<b>Proposals:</b> none new ({len(found)} total)"], False, found
    lines = [f"<b>Proposals:</b> {len(new)} NEW"]
    for p in new:
        lines.append(f"  • {p}")
    return lines, True, found


# ── main ─────────────────────────────────────────────────────────────────────
def build_report(state: dict):
    """Returns (message: str, news: bool, next_state: dict)."""
    first_run = "last_closed_at" not in state
    prev_last_closed = float(state.get("last_closed_at", 0) or 0)
    seen_props = state.get("seen_proposals", [])

    live = load_live_trades()
    mode = load_mode()

    body: list[str] = []
    news = False

    s_lines, s_news = section_trades(live, prev_last_closed, first_run)
    body += s_lines; news = news or s_news

    b_lines, b_news = section_budget(live, mode)
    body += b_lines; news = news or b_news

    f_lines, _ = section_fills()
    body += f_lines

    d_lines, d_news = section_real_diag(live)
    body += d_lines; news = news or d_news

    p_lines, p_news, found_props = section_proposals(seen_props)
    body += p_lines; news = news or p_news

    # Demote-transition headline (paper_mode flipped false → true since last run)
    prev_paper = state.get("last_paper_mode")
    cur_paper = mode.get("paper_mode")
    if prev_paper is False and cur_paper is True:
        body.insert(0, "⚠️ <b>ST2.0 AUTO-DEMOTED to paper since last check</b>")
        news = True

    header = "🆕 🔬 <b>ST2.0 Watch</b>" if news else "🔬 <b>ST2.0 Watch</b>"
    message = header + "\n" + "\n".join(body)

    next_state = {
        "last_closed_at": max((float(t.get("closed_at", 0) or 0) for t in live),
                              default=prev_last_closed),
        "seen_proposals": found_props,
        "last_paper_mode": cur_paper,
        "last_run": time.time(),
    }
    return message, news, next_state


def main() -> int:
    ap = argparse.ArgumentParser(description="ST2.0 watcher")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the message; send no Telegram, persist no state")
    args = ap.parse_args()

    try:
        state = load_watch_state()
        message, news, next_state = build_report(state)
    except Exception as e:
        logger.exception(f"watcher failed to build report: {e}")
        return 1

    if args.dry_run:
        print(message)
        logger.info(f"dry-run (news={news})")
        return 0

    try:
        notifier.send(message)
    except Exception as e:
        logger.exception(f"telegram send failed: {e}")
        return 1

    save_watch_state(next_state)
    logger.info(f"sent digest (news={news}, "
                f"live_trades={next_state['last_closed_at']!r})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
