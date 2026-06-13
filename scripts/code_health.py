#!/usr/bin/env python3
"""Code Health — daily code-rot + momentum guard for Phmex-S (launchd: com.phmex.code-health).

Fills the gaps the existing monitors DON'T cover (verified 2026-06-12):
  - overwatch.py runs py_compile but NEVER the test suite → a logic regression
    that still compiles passes silently. This runs pytest.
  - py_compile does not catch ImportError/ModuleNotFoundError. This imports
    every bot module in a subprocess to surface runtime import breakage.
  - nothing lints for dead code / unused imports. This runs pyflakes + vulture.
  - monitor_daemon catches a FROZEN bot but not "alive, cycling, yet entries
    are erroring out" — the silent momentum-killer. This checks entry health.

Deliberately does NOT re-implement: process-alive/auto-restart (overwatch.py:170,
monitor_daemon.py:58), py_compile (overwatch.py:376), stale-pycache
(overwatch.py:398), frozen-cycle (monitor_daemon.py:179), dirty-git-tree
(overwatch.py:426). All checks here are offline-safe and read-only.

Severity → action:
  CRITICAL  tests fail / import breaks / compile error / entries throwing  → Telegram
  WARNING   no successful entry in 48h while cycling, or dead-code growth   → Telegram
  OK/INFO   logged only
"""

import os
import re
import sys
import json
import time
import subprocess
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BOT_DIR, ".env"))

import requests

LOG_FILE = os.path.join(BOT_DIR, "logs", "bot.log")
STATE_FILE = os.path.join(BOT_DIR, "trading_state.json")
DEADCODE_BASELINE = os.path.join(BOT_DIR, "logs", "code_health_deadcode.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CODE-HEALTH] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BOT_DIR, "logs", "code_health.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("code_health")

# Modules main.py pulls in directly + transitively. Each is import-safe without
# .env / API keys (config.py defaults every getenv); verified 2026-06-12.
BOT_MODULES = [
    "config", "logger", "indicators", "strategies", "risk_manager",
    "exchange", "ws_feed", "strategy_slot", "scanner", "notifier",
    "bot", "web_dashboard", "war_room", "main",
]

# How long the bot may legitimately go without a FILLED entry before we flag it.
# The bot runs radical selectivity + maker-only entries (PostOnly misses are
# normal), so this is generous and only a WARNING — it means "look, the funnel
# has produced nothing in two days", not "broken".
NO_ENTRY_WARN_HOURS = 48
PYTEST_TIMEOUT_S = 180

TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def tg_send(message: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        logger.warning("Telegram NOT sent — TELEGRAM_TOKEN/TELEGRAM_CHAT_ID missing")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Telegram alert sent ({len(message)} chars)")
            return True
        logger.error(f"Telegram HTTP {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


class CheckResult:
    def __init__(self, name, severity, message, diagnostics=""):
        self.name = name
        self.severity = severity   # OK | INFO | WARNING | CRITICAL
        self.message = message
        self.diagnostics = diagnostics


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def _recent_log_lines(hours: int) -> list[str]:
    """bot.log lines from the last N hours (ANSI-stripped). Timestamps are local."""
    if not os.path.exists(LOG_FILE):
        return []
    cutoff = datetime.now() - timedelta(hours=hours)
    out = []
    with open(LOG_FILE, encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = _strip_ansi(raw).rstrip("\n")
            m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if ts >= cutoff:
                out.append(line)
    return out


# ── checks ───────────────────────────────────────────────────────────────
def check_tests() -> CheckResult:
    """Run the (offline, mocked) test suite. A logic regression that still
    compiles is invisible to py_compile but caught here."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header"],
            cwd=BOT_DIR, capture_output=True, text=True, timeout=PYTEST_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("tests", "CRITICAL", f"pytest exceeded {PYTEST_TIMEOUT_S}s — likely hung")
    tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "(no output)"
    if r.returncode == 0:
        return CheckResult("tests", "OK", tail)
    # surface the FAILED lines for the alert
    fails = [l for l in r.stdout.splitlines() if l.startswith("FAILED") or " failed" in l]
    return CheckResult("tests", "CRITICAL", f"pytest FAILED: {tail}", "\n".join(fails[-12:]))


def check_imports() -> CheckResult:
    """Import every bot module in a clean subprocess — catches ImportError /
    ModuleNotFoundError / import-time crashes that py_compile cannot see."""
    code = "import importlib,sys\n" + \
           f"mods={BOT_MODULES!r}\n" + \
           "bad=[]\n" + \
           "for m in mods:\n" + \
           "    try: importlib.import_module(m)\n" + \
           "    except Exception as e: bad.append(f'{m}: {type(e).__name__}: {e}')\n" + \
           "print('BAD:'+'||'.join(bad)) if bad else print('ALL_OK')\n"
    r = subprocess.run([sys.executable, "-c", code], cwd=BOT_DIR,
                       capture_output=True, text=True, timeout=60)
    out = r.stdout.strip()
    if out == "ALL_OK" and r.returncode == 0:
        return CheckResult("imports", "OK", f"{len(BOT_MODULES)} modules import clean")
    diag = out.replace("BAD:", "").replace("||", "\n") or r.stderr.strip()[-500:]
    return CheckResult("imports", "CRITICAL", "module import FAILED", diag)


def check_compile() -> CheckResult:
    """compileall every root .py — complements overwatch's py_compile of the 11
    core files by covering scripts/helpers too. Cheap, stdlib."""
    r = subprocess.run([sys.executable, "-m", "compileall", "-q", BOT_DIR],
                       cwd=BOT_DIR, capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        return CheckResult("compile", "OK", "all .py compile")
    return CheckResult("compile", "CRITICAL", "compile error", (r.stdout + r.stderr).strip()[-500:])


def check_dead_code() -> CheckResult:
    """pyflakes (unused imports / undefined names — high signal, ~0 false positives
    on first-party code) + vulture (unused functions/vars — noisier, tracked as a
    trend so only NEW dead code is flagged). Degrades to INFO if tools absent."""
    core = [os.path.join(BOT_DIR, f) for f in (
        "bot.py", "exchange.py", "strategies.py", "risk_manager.py",
        "ws_feed.py", "strategy_slot.py", "config.py", "notifier.py",
        "scanner.py", "indicators.py", "main.py")]

    # pyflakes — unused imports / undefined names. Undefined names are real bugs.
    pf_issues, pf_undefined = [], []
    try:
        r = subprocess.run([sys.executable, "-m", "pyflakes", *core],
                           cwd=BOT_DIR, capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            if not line.strip():
                continue
            pf_issues.append(line)
            if "undefined name" in line:
                pf_undefined.append(line)
    except Exception as e:
        return CheckResult("dead_code", "INFO", f"pyflakes unavailable: {e}")

    # undefined name == latent NameError == momentum risk → CRITICAL
    if pf_undefined:
        return CheckResult("dead_code", "CRITICAL",
                           f"pyflakes: {len(pf_undefined)} undefined name(s) — latent crash",
                           "\n".join(pf_undefined[:12]))

    # vulture — unused funcs/vars. Trend-tracked: only alert when the count GROWS,
    # so pre-existing intentional dead code doesn't cry wolf every day.
    vult_count, vult_sample = 0, []
    try:
        r = subprocess.run([sys.executable, "-m", "vulture", *core,
                            "--min-confidence", "80"],
                           cwd=BOT_DIR, capture_output=True, text=True, timeout=60)
        vlines = [l for l in r.stdout.splitlines() if l.strip()]
        vult_count = len(vlines)
        vult_sample = vlines[:10]
    except Exception:
        pass

    # Growth detection: baseline the known dead-code set, then only WARN when it
    # GROWS — i.e. a change introduced NEW rot. Pre-existing dead code is reported
    # at INFO (and was surfaced in full on the first run), per the project rule
    # not to remove pre-existing dead code unprompted. This makes the daily check
    # a "did we deprecate something today" guard, which is the actual goal.
    prev_v, prev_p = 0, 0
    first_run = not os.path.exists(DEADCODE_BASELINE)
    if not first_run:
        try:
            b = json.load(open(DEADCODE_BASELINE))
            prev_v = b.get("vulture_count", 0)
            prev_p = b.get("pyflakes_unused", 0)
        except Exception:
            pass
    try:
        json.dump({"vulture_count": vult_count, "pyflakes_unused": len(pf_issues),
                   "updated": datetime.now(timezone.utc).isoformat()},
                  open(DEADCODE_BASELINE, "w"), indent=2)
    except Exception:
        pass

    msg = f"pyflakes {len(pf_issues)} unused-import (was {prev_p}), vulture {vult_count} dead (was {prev_v})"
    grew = vult_count > prev_v or len(pf_issues) > prev_p
    if first_run or grew:
        # first run: surface the full existing set once. after that: only on growth.
        sev = "WARNING" if grew else "INFO"
        return CheckResult("dead_code", sev, msg, "\n".join(pf_issues[:8] + vult_sample[:6]))
    return CheckResult("dead_code", "OK", msg)


def check_entry_health() -> CheckResult:
    """Momentum guard: is the bot cycling AND not throwing on entries?
    Distinguishes a healthy-but-quiet funnel (PostOnly 'signal lost' misses are
    NORMAL) from real breakage (exceptions in the entry path, or a long dry spell)."""
    lines = _recent_log_lines(NO_ENTRY_WARN_HOURS)
    if not lines:
        return CheckResult("entry_health", "WARNING", "no parseable bot.log lines in window")

    cycling = any("Cycle #" in l for l in lines)
    if not cycling:
        # monitor_daemon owns frozen-cycle alerts; note it but don't duplicate severity
        return CheckResult("entry_health", "INFO", "no Cycle# lines in window (frozen-cycle is monitor_daemon's job)")

    # entry-path EXCEPTIONS = real bug (not the benign 'signal lost' maker miss)
    entry_exceptions = [l for l in lines
                        if ("Traceback" in l or "entry sequence error" in l
                            or "entry sequence failed" in l
                            or ("[ENTRY]" in l and "Exception" in l))]
    if entry_exceptions:
        return CheckResult("entry_health", "CRITICAL",
                           f"{len(entry_exceptions)} entry-path exception(s) in {NO_ENTRY_WARN_HOURS}h",
                           "\n".join(entry_exceptions[-8:]))

    # last successful filled entry, from state (authoritative) — opened_at is epoch UTC
    last_entry_age_h = None
    try:
        st = json.load(open(STATE_FILE))
        ct = st.get("closed_trades", [])
        opens = [t.get("opened_at") for t in ct if t.get("opened_at")]
        # also count an open position as a live entry
        if st.get("positions"):
            last_entry_age_h = 0.0
        elif opens:
            last_entry_age_h = (time.time() - max(opens)) / 3600.0
    except Exception:
        pass

    if last_entry_age_h is not None and last_entry_age_h >= NO_ENTRY_WARN_HOURS:
        return CheckResult("entry_health", "WARNING",
                           f"cycling but no filled entry in {last_entry_age_h:.0f}h "
                           f"(≥{NO_ENTRY_WARN_HOURS}h) — funnel may be over-gated or execution stuck")
    age_txt = f"{last_entry_age_h:.1f}h ago" if last_entry_age_h is not None else "unknown"
    return CheckResult("entry_health", "OK", f"cycling, no entry exceptions; last filled entry {age_txt}")


# ── runner ───────────────────────────────────────────────────────────────
CHECKS = [check_compile, check_imports, check_tests, check_dead_code, check_entry_health]


def main():
    logger.info("=== code-health run start ===")
    results = []
    for fn in CHECKS:
        try:
            res = fn()
        except Exception as e:
            res = CheckResult(fn.__name__, "CRITICAL", f"check crashed: {e}")
        results.append(res)
        logger.info(f"[{res.severity}] {res.name}: {res.message}")
        if res.diagnostics:
            logger.info(f"    {res.diagnostics.replace(chr(10), ' | ')}")

    crit = [r for r in results if r.severity == "CRITICAL"]
    warn = [r for r in results if r.severity == "WARNING"]

    if crit or warn:
        emoji = "\U0001F6A8" if crit else "⚠️"
        head = "CODE HEALTH — ACTION NEEDED" if crit else "CODE HEALTH — warnings"
        body = [f"{emoji} <b>{head}</b>  [Phmex-S]"]
        for r in crit + warn:
            tag = "\U0001F534" if r.severity == "CRITICAL" else "\U0001F7E1"
            body.append(f"{tag} <b>{r.name}</b>: {r.message}")
            if r.diagnostics:
                snippet = r.diagnostics.strip().splitlines()[:6]
                body.append("<pre>" + "\n".join(s[:120] for s in snippet) + "</pre>")
        tg_send("\n".join(body))
    else:
        logger.info("All code-health checks passed — no alert sent")

    logger.info("=== code-health run end ===")
    return 1 if crit else 0


if __name__ == "__main__":
    raise SystemExit(main())
