#!/usr/bin/env python3
"""Nightly LEAN deep-research on optimizing ST2.0 maker execution.

Runs `claude -p` headless to do a focused, verified web-research pass (deliberately
NOT the 3M-token deep-research workflow, which hit a session limit) on improving
ST2.0's passive (maker) fill quality / reducing adverse selection. Writes a dated
report to docs/research/ and Telegrams a short phone summary.

Best-effort: never raises uncaught; logs everything to ~/Library/Logs/Phmex-S/.
Kill switch: create scripts/.halt_nightly_research to skip runs.
Scheduled via com.phmex.nightly-research (launchd, 3:00 AM local).

Run manually:  python3 scripts/nightly_research.py            (full run)
               python3 scripts/nightly_research.py --test     (cheap plumbing check)
"""
from __future__ import annotations

import datetime
import logging
import os
import subprocess
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))
CLAUDE = os.path.expanduser("~/.local/bin/claude")
HALT = os.path.join(BOT_DIR, "scripts", ".halt_nightly_research")
_LOG_DIR = os.path.expanduser("~/Library/Logs/Phmex-S")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(filename=os.path.join(_LOG_DIR, "nightly_research.log"),
                    level=logging.INFO,
                    format="%(asctime)s [NIGHTLY-RESEARCH] %(message)s")
logger = logging.getLogger(__name__)


def _telegram(msg: str) -> bool:
    try:
        from st2_lab import notify
        return notify.telegram_alert(msg)
    except Exception as e:  # never let a notify failure crash the job
        logger.error(f"telegram failed: {e}")
        return False


def _prompt(date_str: str, test: bool) -> str:
    if test:
        return (f"Write a file docs/research/{date_str}-nightly-research-TEST.md containing the single "
                f"line 'plumbing test ok'. Then reply with exactly the token TEST_OK and nothing else.")
    report = f"docs/research/{date_str}-st2-optimize-nightly.md"
    return f"""You are a quant research assistant for the Phmex-S crypto trading bot. Your ONE task tonight is focused web research on optimizing ST2.0's MAKER EXECUTION. You start with zero context — everything you need is below.

CONTEXT: ST2.0 is a book×tape absorption SHORT on crypto perpetual futures (Phemex). It posts a passive POST-ONLY limit SELL into a bid-heavy order book being aggressively bought, expecting a ~15-minute reversion down. Prior research (READ docs/research/2026-06-20-st2-execution-research-synthesis.md) established: the SIGNAL is real, but real maker fills are ~43%, adversely selected, and the BINDING CONSTRAINT is EXECUTION — the bot has no speed, no queue-position, and no maker-rebate edge (Phemex rebate = 0).

HARD RULES:
- Focus ONLY on EXECUTION: improving passive fill quality / reducing adverse selection for a short-reversion maker order at small size with no rebate. Do NOT hunt for new alpha or signals.
- Do NOT state any statistic, paper title, or claim as fact unless you actually fetched the primary source and can quote it. Fabricated citations are the #1 failure mode — if you cannot verify something, label it "unverified". Less-but-verified beats more-but-fabricated.
- Don't repeat prior reports: FIRST read the 2-3 most recent docs/research/*optimize-nightly*.md, skip anything already covered, focus on NEW material.

STEPS:
1. Glob + Read recent docs/research/*optimize-nightly*.md and the 2026-06-20 synthesis to know what's already covered.
2. WebSearch 3-4 execution angles (queue-position tactics, post-only repricing/chasing, OFI / micro-price placement timing, adverse-selection mitigation, crypto-perp maker fill optimization).
3. WebFetch the 4-6 best PRIMARY sources; extract verifiable claims with source URL + a quote.
4. Write a concise report to {report}: (a) what's NEW vs prior reports, (b) 2-4 concrete, forward-testable EXECUTION tweaks for ST2.0 (each tied to a verified source), (c) honest caveats + anything you could not verify.
5. Keep it LEAN — a handful of high-quality verified findings, not an exhaustive crawl. Aim to finish well within your turn budget.

FINALLY: end your reply with a SHORT plain-text summary (under 6 lines, no markdown, no angle brackets) suitable for a phone notification — lead with the single most actionable execution tweak found tonight, or exactly 'No new actionable findings tonight (literature repeats prior reports).' if nothing new."""


def main() -> None:
    test = "--test" in sys.argv
    if os.path.exists(HALT):
        logger.info("halt flag present (scripts/.halt_nightly_research) — skipping run")
        return
    date_str = datetime.date.today().isoformat()
    cmd = [CLAUDE, "-p", _prompt(date_str, test),
           "--model", "claude-sonnet-4-6",
           "--allowedTools", "WebSearch", "WebFetch", "Read", "Write", "Glob", "Grep",
           "--permission-mode", "acceptEdits",
           "--max-turns", "8" if test else "60",
           "--output-format", "text"]
    logger.info(f"starting {'TEST' if test else 'nightly'} research run (date={date_str})")
    try:
        r = subprocess.run(cmd, cwd=BOT_DIR, capture_output=True, text=True,
                           timeout=300 if test else 2400)
    except subprocess.TimeoutExpired:
        logger.error("claude run timed out")
        _telegram("⚠️ ST2.0 nightly research TIMED OUT — see logs/nightly_research.log")
        return
    except Exception as e:
        logger.error(f"claude run failed to launch: {e}")
        _telegram(f"⚠️ ST2.0 nightly research could not start: {str(e)[:160]}")
        return

    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    logger.info(f"exit={r.returncode} stdout_len={len(out)} stderr_len={len(err)}")
    if r.returncode != 0 or not out:
        logger.error(f"claude failed rc={r.returncode}: {err[:500]}")
        _telegram(f"⚠️ ST2.0 nightly research FAILED (rc={r.returncode}) — see logs/nightly_research.log")
        return

    summary = "\n".join(out.splitlines()[-8:]).strip()
    logger.info(f"summary: {summary[:400]}")
    sent = _telegram(f"🔬 ST2.0 nightly research ({date_str})\n{summary}")
    logger.info(f"telegram sent={sent}; full output {len(out)} chars (report in docs/research/)")


if __name__ == "__main__":
    main()
