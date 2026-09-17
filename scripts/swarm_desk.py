#!/usr/bin/env python3
"""Edge Swarm v2 — scheduled desk runner + daily no-LLM paper maintenance.

    python3 scripts/swarm_desk.py --mode maint   # daily 6:30 AM PT (com.phmex.desk-maint), no LLM
    python3 scripts/swarm_desk.py --mode desk    # Sunday 3:00 AM PT (com.phmex.desk-weekly), full desk
    python3 scripts/swarm_desk.py --mode test    # headless-Workflow feasibility: desk with the dry-run args

Common to every mode: refuse when scripts/.halt_swarm_desk exists (log, exit 0);
refuse when another `swarm_desk.py --mode desk|test` process is alive (run-alone
guard — the desk never runs concurrently with another workflow); `git pull
--ff-only` first (the knowledge base lives in git; a failed pull is logged and the
run continues on the local copy).

maint (no LLM): reads every registered paper slot's trading_state_<id>.json plus
the adjudicator's latest digest (parsed from ~/Library/Logs/Phmex-S/lab_adjudicator.log
— adjudicate.py writes its grades only there, to stdout and to Telegram; there is
no JSON grades file) and rewrites research/swarm/kb/PAPER_STATUS.md. Appends ONE
dated LESSONS line only when a slot crossed its registered kill line or reached
verdict_n since the previous maint run (tracked in kb/.maint_state.json, gitignored;
the first run is a baseline and announces nothing). Telegram only on such an alert.
Commits (pathspec, no push) PAPER_STATUS.md / LESSONS.md when they changed so the
daily pull never conflicts on them.

Branch: desk/test refuse (Telegram + exit 1) unless HEAD == env SWARM_BRANCH
(default "main"; both plists set it); maint only logs the branch.

desk: maint first, then a headless `claude -p` whose prompt invokes the Workflow
tool on research/swarm/workflows/desk.js with the args written to
runs/<run_id>/launch_args.json. Afterwards: git add kb + the run dir (never .env,
never data), commit, push, Telegram (first 3 lines of REPORT.md + result code +
counts + maint alerts). WEB_BUDGET_EXHAUSTED, a timeout, a claude failure, or a
missing Workflow tool all say so on Telegram with the manual one-liner.

This script never starts, stops or restarts the bot, never invokes build.js,
never touches launchd, and never promotes anything. Logs: ~/Library/Logs/Phmex-S/
(launchd + TCC: never log under ~/Desktop — memory/feedback_launchd_tcc.md).
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

_HERE = Path(__file__).resolve().parent
BOT_DIR = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

PT = ZoneInfo("America/Los_Angeles")
DAY = 86400.0
CLAUDE_BIN = os.path.expanduser("~/.local/bin/claude")
LOG_DIR = Path.home() / "Library" / "Logs" / "Phmex-S"
ADJUDICATOR_LOG = LOG_DIR / "lab_adjudicator.log"

DESK_TIMEOUT_S = 75 * 60
DESK_TOOLS = ("Workflow", "WebSearch", "WebFetch", "Read", "Write", "Bash", "Glob", "Grep")
DESK_SCRIPT = "research/swarm/workflows/desk.js"
DESK_CODES = ("SURVIVORS", "NO_SURVIVORS", "ALL_REJECTED_AT_GATE", "GATE_FAILED", "NO_THESES",
              "WEB_BUDGET_EXHAUSTED")                      # desk.js result codes (verbatim)
# Artifacts only desk.js's closing seats write; required for every code except the
# pre-gate abort (WEB_BUDGET_EXHAUSTED writes one LESSONS line and nothing else).
DESK_ARTIFACTS = ("REPORT.md", "CRITIC.md")
DEFAULT_BRANCH = "main"                                  # env SWARM_BRANCH overrides
RESULT_MARKER = "DESK_RESULT_JSON:"
UNAVAILABLE_MARKER = "WORKFLOW_TOOL_UNAVAILABLE"
COMMIT_TRAILER = "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
MANUAL_LAUNCH_ONE_LINER = (
    'cd ~/Desktop/Phmex-S && claude — then paste: "Run the desk alone per research/swarm/README.md '
    '(Running the desk): confirm /workflows shows nothing live, Read kb/CONSTRAINTS.md + kb/STANDARDS.md, '
    'and invoke Workflow research/swarm/workflows/desk.js with run_id <YYYY-MM-DD-HHMM PT>, now <ISO UTC>, '
    'judge_model null, max_analysts 8, max_screens 5, dry_run false, constraints_md/standards_md = those '
    'file contents; then python3 -m research.swarm.lib.kb_check && git add research/swarm && git commit && git push."')

EXIT_OK, EXIT_FAIL, EXIT_BUSY = 0, 1, 3

# The main book's label in bot.py's slot list ("5m_scalp" is NOT an independent
# trader — bot.py:677-687); it is never a paper slot for PAPER_STATUS.
MAIN_BOOK_LABELS = frozenset({"5m_scalp"})
# adjudicator EXPERIMENTS keys → slot ids (legacy names; build.js slots use key == slot_id)
# (mr_bundle is NOT mapped: it grades the live MR fills, not the paper row)
ADJ_KEY_TO_SLOT = {"sr_bounce_v2": "SR_BOUNCE", "sr_bounce": "SR_BOUNCE_era1", "eth_tsm_28": "ETH_TSM_28",
                   "htf_l2": "HTF_L2", "vwap_cross": "VWAP_CROSS"}
# Kill lines that live outside the adjudicator registry (read from the cited files).
LEGACY_LINES = {
    # docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md "Kill criteria":
    # "Paper net ≤ −$15 on $100-base (≈ −15% = beyond replay MDD) → kill."
    "DONCHIAN_BTC": {"verdict_n": None, "kill_net_usd": -15.0, "since_ts": None, "since_field": "closed_at",
                     "inconclusive_hard_n": None,
                     "rule": "KILL if paper net <= $-15.00 (spec; fidelity line graded separately)",
                     "source": "docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md"},
    "DONCHIAN_ETH": {"verdict_n": None, "kill_net_usd": -15.0, "since_ts": None, "since_field": "closed_at",
                     "inconclusive_hard_n": None,
                     "rule": "KILL if paper net <= $-15.00 (spec; fidelity line graded separately)",
                     "source": "docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md"},
    # adjudicate.py EXPERIMENTS["vwap_cross"]: "kill lines are OWNER-SET pending; nothing here auto-trips"
    "VWAP_CROSS": {"verdict_n": None, "kill_net_usd": None, "since_ts": None, "since_field": "closed_at",
                   "inconclusive_hard_n": None,
                   "rule": "none registered (owner-set pending; adjudicator REPORT-ONLY)",
                   "source": "scripts/lab_adjudicator/adjudicate.py EXPERIMENTS[\"vwap_cross\"]"},
}

log = logging.getLogger("swarm_desk")


# ── injectable context ────────────────────────────────────────────────────────
@dataclass
class Launch:
    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool


@dataclass
class Ctx:
    """Every path and side effect the runner uses. Tests build one on tmp_path;
    `Ctx.real()` wires the repo, pgrep, git, subprocess and Telegram."""
    bot_dir: Path
    log_dir: Path = LOG_DIR
    registered_ids: Optional[list] = None          # None → parsed from bot.py
    experiments: Optional[dict] = None             # None → lab_adjudicator.adjudicate.EXPERIMENTS
    pgrep: Callable[[], list] = field(default=lambda: [])
    bot_alive: Callable[[], Optional[bool]] = field(default=lambda: None)
    git: Callable[[list], tuple] = field(default=lambda args: (1, "git not wired"))
    launcher: Callable[..., Launch] = field(default=lambda *a, **k: Launch(1, "", "launcher not wired", False))
    telegram: Callable[[str], bool] = field(default=lambda msg: False)
    adjudicator_log: Path = ADJUDICATOR_LOG
    now: Callable[[], float] = field(default=lambda: datetime.now(tz=timezone.utc).timestamp())
    pid: int = field(default_factory=os.getpid)
    claude_bin: str = CLAUDE_BIN

    @property
    def swarm_dir(self) -> Path:
        return self.bot_dir / "research" / "swarm"

    @property
    def kb_dir(self) -> Path:
        return self.swarm_dir / "kb"

    @property
    def runs_dir(self) -> Path:
        return self.swarm_dir / "runs"

    @property
    def halt_path(self) -> Path:
        return self.bot_dir / "scripts" / ".halt_swarm_desk"

    @property
    def paper_status_path(self) -> Path:
        return self.kb_dir / "PAPER_STATUS.md"

    @property
    def maint_state_path(self) -> Path:
        return self.kb_dir / ".maint_state.json"

    @property
    def lessons_path(self) -> Path:
        return self.kb_dir / "LESSONS.md"

    @classmethod
    def real(cls) -> "Ctx":
        return cls(bot_dir=BOT_DIR, pgrep=_real_pgrep, bot_alive=_real_bot_alive, git=_real_git,
                   launcher=_real_launch, telegram=_real_telegram)


# ── real side effects (never called by the unit tests) ────────────────────────
def _real_pgrep() -> list:
    """Lines "pid full-argv" for every process whose argv mentions swarm_desk.py."""
    try:
        r = subprocess.run(["pgrep", "-fl", "swarm_desk.py"], capture_output=True, text=True, timeout=20)
        return [l for l in (r.stdout or "").splitlines() if l.strip()]
    except Exception as e:  # pragma: no cover
        log.warning("pgrep failed: %s", e)
        return []


def _real_bot_alive() -> Optional[bool]:
    """True when a `Python ... main.py` process (the bot) is alive; None if pgrep failed."""
    try:
        r = subprocess.run(["pgrep", "-fl", "main.py"], capture_output=True, text=True, timeout=20)
        return any(re.search(r"Python\S* .*main\.py\b", l) for l in (r.stdout or "").splitlines())
    except Exception as e:  # pragma: no cover
        log.warning("bot pgrep failed: %s", e)
        return None


def _real_git(args: list) -> tuple:
    try:
        r = subprocess.run(["git", *args], cwd=str(BOT_DIR), capture_output=True, text=True, timeout=300)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:  # pragma: no cover
        return 1, str(e)


def _real_launch(cmd: list, cwd: str, timeout: int) -> Launch:
    """The ONE place that spawns claude. Unit tests never call it."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return Launch(r.returncode, r.stdout or "", r.stderr or "", False)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return Launch(None, out, err, True)
    except Exception as e:
        return Launch(1, "", f"launch failed: {e}", False)


def _real_telegram(msg: str) -> bool:
    """Best-effort; HTML-escaped because notify sends parse_mode=HTML ("<ISO UTC>" would be rejected)."""
    try:
        from st2_lab import notify
        return notify.telegram_alert(html.escape(msg), attempts=4)
    except Exception as e:
        log.error("telegram failed: %s", e)
        return False


# ── common guards ─────────────────────────────────────────────────────────────
_PGREP_LINE = re.compile(r"^\s*(\d+)\s+(.*)$")


def other_desk_processes(pgrep_lines: list, my_pid: int) -> list:
    """PIDs (not mine) running `swarm_desk.py --mode desk` or `--mode test` — the
    two modes that launch claude. A maint process never blocks anything."""
    out = []
    for line in pgrep_lines:
        m = _PGREP_LINE.match(line)
        if not m:
            continue
        pid, cmd = int(m.group(1)), m.group(2)
        if pid == my_pid or "swarm_desk.py" not in cmd:
            continue
        if re.search(r"--mode[ =](desk|test)\b", cmd):
            out.append(pid)
    return out


def expected_branch() -> str:
    return os.environ.get("SWARM_BRANCH") or DEFAULT_BRANCH


def current_branch(ctx: Ctx) -> str:
    rc, out = ctx.git(["rev-parse", "--abbrev-ref", "HEAD"])
    return out.strip().splitlines()[0].strip() if rc == 0 and out.strip() else "?"


def git_commit_paths(ctx: Ctx, msg: str, paths: list) -> tuple:
    """`git add <paths>` (rc checked) then a PATHSPEC commit — never sweeps whatever
    else happens to be staged. Returns (rc, output) of the commit."""
    rc, out = ctx.git(["add", *paths])
    if rc != 0:
        log.error("git add %s failed (rc=%s): %s", paths, rc, out.strip()[:300])
        return rc, out
    return ctx.git(["commit", "-m", msg, "--", *paths])


def git_pull(ctx: Ctx) -> bool:
    rc, out = ctx.git(["pull", "--ff-only"])
    if rc != 0:
        log.warning("git pull --ff-only failed (rc=%s): %s — continuing on the local copy", rc, out.strip()[:300])
        return False
    log.info("git pull --ff-only: %s", (out.strip().splitlines() or ["ok"])[-1][:120])
    return True


# ── maint: slots, lines, digest ───────────────────────────────────────────────
def registered_slot_ids(bot_py: Path) -> list:
    """slot_id="..." (and slot_id=CONSTANT resolved from top-level *.py) inside bot.py's
    StrategySlot(...) entries, minus the main-book label."""
    src = bot_py.read_text()
    ids = []
    for lit, ident in re.findall(r'slot_id=(?:"([^"]+)"|([A-Z_][A-Z0-9_]*))', src):
        if lit:
            ids.append(lit)
        elif ident:
            for p in bot_py.parent.glob("*.py"):
                m = re.search(rf'^{ident}\s*=\s*"([^"]+)"', p.read_text(), re.M)
                if m:
                    ids.append(m.group(1))
                    break
    seen, out = set(), []
    for i in ids:
        if i not in seen and i not in MAIN_BOOK_LABELS:
            seen.add(i)
            out.append(i)
    return out


def kill_lines(experiments: dict) -> dict:
    """slot_id → registered kill line. build.js entries (verdict_n + kill_net_usd +
    registered_ts) are picked up under their own id; the legacy adjudicator entries
    are mapped by ADJ_KEY_TO_SLOT; LEGACY_LINES covers spec-tracked slots."""
    lines = {k: dict(v) for k, v in LEGACY_LINES.items()}
    for key, cfg in (experiments or {}).items():
        if not isinstance(cfg, dict):
            continue
        if {"verdict_n", "kill_net_usd", "registered_ts"} <= set(cfg):       # build.js shape
            vn, kn, hard = cfg["verdict_n"], float(cfg["kill_net_usd"]), cfg.get("inconclusive_hard_n")
            lines[key] = {"verdict_n": vn, "kill_net_usd": kn, "since_ts": float(cfg["registered_ts"]),
                          "since_field": "closed_at", "inconclusive_hard_n": hard,
                          "rule": f"KILL if n>={vn} & net<=0; KILL if net <= ${kn:.2f} at any n"
                                  + (f"; INCONCLUSIVE hard stop n={hard}" if hard else ""),
                          "source": cfg.get("prereg") or "scripts/lab_adjudicator/adjudicate.py"}
        elif key == "sr_bounce_v2":
            lines["SR_BOUNCE"] = {"verdict_n": cfg.get("verdict_n"), "kill_net_usd": None,
                                  "since_ts": float(cfg["honest_since"]) if cfg.get("honest_since") else None,
                                  "since_field": "opened_at", "inconclusive_hard_n": None,
                                  "rule": f"KILL if n>={cfg.get('verdict_n')} & net<=0 (honest era: opened_at >= 8/5 fix)",
                                  "source": "scripts/lab_adjudicator/adjudicate.py EXPERIMENTS[\"sr_bounce_v2\"]"}
        elif key == "eth_tsm_28":
            lines["ETH_TSM_28"] = {"verdict_n": None, "kill_net_usd": float(cfg["kill_net_usd"]), "since_ts": None,
                                   "since_field": "closed_at", "inconclusive_hard_n": None,
                                   "rule": f"KILL if net <= ${float(cfg['kill_net_usd']):.2f}; also >= "
                                           f"{cfg.get('kill_disaster_stops')} disaster stops / tracking drift (adjudicator)",
                                   "source": "scripts/lab_adjudicator/adjudicate.py EXPERIMENTS[\"eth_tsm_28\"]"}
    return lines


def _load_experiments() -> dict:
    try:
        from lab_adjudicator import adjudicate  # noqa: WPS433 — import only; build_digest is never called (it writes sentinels)
        return adjudicate.EXPERIMENTS
    except Exception as e:
        log.warning("adjudicator EXPERIMENTS unavailable (%s) — legacy lines only", e)
        return {}


def _net(t: dict) -> Optional[float]:
    v = t.get("net_pnl")
    if v is None:
        v = t.get("pnl_usdt")
    return float(v) if v is not None else None


def bot_kill_switch(trades: list) -> Optional[float]:
    """Replica of strategy_slot.is_killed: negative raw Kelly (risk_manager.calculate_kelly_raw,
    mode=="paper" rows excluded) after 50+ closed trades disables the slot every cycle.
    Returns the Kelly value when the switch is tripped, else None."""
    rows = [t for t in trades if t.get("mode") != "paper"]
    if len(rows) < 50:
        return None
    nets = [(_net(t) or 0.0) for t in rows]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    if not wins or not losses:
        return None
    wr = len(wins) / len(nets)
    avg_win = sum(wins) / len(wins)
    avg_loss = abs(sum(losses) / len(losses))
    if avg_win == 0:
        return None
    kelly = (wr * avg_win - (1 - wr) * avg_loss) / avg_win
    return kelly if kelly < 0 else None


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text()) or default
    except (OSError, ValueError):
        return default


@dataclass
class SlotStatus:
    slot_id: str
    mode: str
    n: int
    net: float
    wins: int
    start_ts: Optional[float]
    last_close_ts: Optional[float]
    end_ts: float
    killed: Optional[str]            # None when active, else why
    line: Optional[dict]             # registered kill line (drives crossings); None = none registered
    rule_text: str                   # what the kill-line column prints
    adjudicator: Optional[str]

    @property
    def wr(self) -> Optional[float]:
        return self.wins / self.n if self.n else None

    @property
    def days(self) -> Optional[int]:
        return int(round((self.end_ts - self.start_ts) / DAY)) if self.start_ts else None

    @property
    def crossed(self) -> bool:
        if not self.line:
            return False
        kn, vn = self.line.get("kill_net_usd"), self.line.get("verdict_n")
        return (kn is not None and self.net <= kn) or (bool(vn) and self.n >= vn and self.net <= 0)

    @property
    def verdict_reached(self) -> bool:
        vn = (self.line or {}).get("verdict_n")
        return bool(vn) and self.n >= vn and self.net > 0

    def distance(self) -> str:
        if not self.line:
            return "—"
        if self.crossed:
            return "CROSSED"
        kn, vn = self.line.get("kill_net_usd"), self.line.get("verdict_n")
        parts = []
        if kn is not None:
            parts.append(f"{self.net - kn:.2f} above ${kn:.2f}")
        if vn:
            parts.append(f"{self.net:+.2f} vs $0 with {max(vn - self.n, 0)} to go")
        return "; ".join(parts) or "—"

    def progress(self) -> str:
        vn = (self.line or {}).get("verdict_n")
        return f"{self.n}/{vn}" if vn else "—"


def collect_slots(ctx: Ctx, lines: dict, grades: dict) -> list:
    now = ctx.now()
    out = []
    for sid in ctx.registered_ids or []:
        state_path = ctx.bot_dir / f"trading_state_{sid}.json"
        trades = list(_load_json(state_path, {}).get("closed_trades") or [])
        sidecar = _load_json(ctx.bot_dir / f"trading_state_{sid}_mode.json", {})
        line = lines.get(sid)
        if line is not None and line.get("kill_net_usd") is None and not line.get("verdict_n"):
            rule_text, line = f"{line['rule']} ({line['source']})", None          # informational only
        elif line is not None:
            rule_text = f"{line['rule']} ({line['source']})"
        else:
            cap = sidecar.get("loss_cap_usdt")
            rule_text = (f"live rail only: auto-demote at ${float(cap):.2f} (sidecar loss_cap_usdt); no paper kill line registered"
                         if isinstance(cap, (int, float)) and cap > -999 else "none registered")
        era = trades
        if line and line.get("since_ts"):
            era = [t for t in trades if (t.get(line.get("since_field", "closed_at")) or 0) >= line["since_ts"]]
        nets = [n for t in era for n in [_net(t)] if n is not None]
        net = sum(nets)
        wins = sum(1 for n in nets if n > 0)
        killed = None
        killed_at = sidecar.get("killed_at")
        kelly = bot_kill_switch(trades)
        if (ctx.bot_dir / f".kill_{sid}").exists():
            killed = f"sentinel .kill_{sid} present"
        elif killed_at:
            killed = f"killed {datetime.fromtimestamp(float(killed_at), tz=PT):%Y-%m-%d} (sidecar killed_at)"
        elif kelly is not None:
            killed = f"bot kill switch: negative Kelly ({kelly:.3f}) after {len(trades)} trades"
        start = (line or {}).get("since_ts") or (min((t.get("opened_at") or t.get("closed_at") or 0) for t in era) if era else None)
        last_close = max((t.get("closed_at") or 0) for t in trades) if trades else None
        end = float(killed_at) if killed_at else (last_close if (killed and last_close) else now)
        mode = "paper" if sidecar.get("paper_mode", True) else "LIVE"
        out.append(SlotStatus(sid, mode, len(era), net, wins, start or None, last_close or None, end,
                              killed, line, rule_text, grades.get(sid)))
    return out


_DIGEST_HEAD = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \[ADJUDICATOR\] digest:\s*$")
_LOG_LINE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ ")
_GRADE = re.compile(r"^\[([^\]]+)\]\s+(.*)$")
_STAMP = re.compile(r"\((.*?)\)\s*$")


def latest_adjudicator_digest(path: Path) -> Optional[dict]:
    """The last `digest:` block of lab_adjudicator.log → {"ts", "stamp", "grades": {slot_id: "STATUS — note"}}.
    Keys are mapped through ADJ_KEY_TO_SLOT so legacy experiment names land on their slot ids."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    heads = [i for i, l in enumerate(lines) if _DIGEST_HEAD.match(l)]
    if not heads:
        return None
    i = heads[-1]
    ts = datetime.strptime(_DIGEST_HEAD.match(lines[i]).group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=PT).timestamp()
    block = []
    for l in lines[i + 1:]:
        if _LOG_LINE.match(l):
            break
        block.append(l)
    stamp = None
    if block and block[0].startswith("LAB ADJUDICATOR"):
        m = _STAMP.search(block[0])
        stamp = m.group(1) if m else None
    grades = {}
    for l in block:
        m = _GRADE.match(l)
        if m and m.group(1) != "main book":
            grades[ADJ_KEY_TO_SLOT.get(m.group(1), m.group(1))] = m.group(2).strip()
    return {"ts": ts, "stamp": stamp, "grades": grades}


def _fmt_day(ts: Optional[float]) -> str:
    return datetime.fromtimestamp(ts, tz=PT).strftime("%Y-%m-%d") if ts else "—"


def render_paper_status(slots: list, digest: Optional[dict], bot_alive: Optional[bool], now: float) -> str:
    stamp = datetime.fromtimestamp(now, tz=PT).strftime("%Y-%m-%d %I:%M %p PT")
    bot = {True: "RUNNING", False: "STOPPED — no state file advances until an audited restart",
           None: "unknown (pgrep failed)"}[bot_alive]
    if digest is None:
        adj = ("no adjudicator digest found in ~/Library/Logs/Phmex-S/lab_adjudicator.log — kill lines are "
               "not being graded automatically (com.phmex.lab-adjudicator is re-enabled with the bot; README Cadence, Gate B)")
    else:
        age_d = (now - digest["ts"]) / DAY
        adj = f"Adjudicator digest: {digest['stamp'] or _fmt_day(digest['ts'])} ({age_d:.1f} d old)"
        if age_d > 2:
            adj += (" — kill lines are not being graded automatically (com.phmex.lab-adjudicator is unloaded "
                    "until the bot restart; README Cadence, Gate B)")
    head = [
        "# PAPER_STATUS — paper-slot forward tests (auto-written by `scripts/swarm_desk.py --mode maint`; do not edit — regenerated daily)",
        "",
        f"Written {stamp}. Bot process: {bot}. {adj}.",
        "",
        "Per slot: n and net USD are the registered era's closed trades (no registered era → every closed trade in the file; net_pnl as-is, fee-inclusive at the source); "
        "WR = share of era trades with net > 0; days = era start (registration, else first trade) → now, or → kill. "
        "Distance = USD above the kill line. Nothing here promotes or restarts anything.",
        "",
    ]
    active = [s for s in slots if s.killed is None]
    killed = [s for s in slots if s.killed is not None]
    out = list(head)
    out.append("## Active slots (registered in bot.py, not killed)")
    out.append("")
    if active:
        out.append("| slot | mode | n | net USD | WR | days | last close | kill line | distance | verdict_n | adjudicator (latest digest) |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for s in active:
            wr = f"{s.wr:.0%}" if s.wr is not None else "—"
            days = s.days if s.days is not None else "—"
            out.append(f"| {s.slot_id} | {s.mode} | {s.n} | {s.net:+.2f} | {wr} | {days} | {_fmt_day(s.last_close_ts)} | "
                       f"{s.rule_text} | {s.distance()} | {s.progress()} | {s.adjudicator or '—'} |")
    else:
        out.append("(none)")
    out.append("")
    out.append("## Killed / retired")
    out.append("")
    if killed:
        out.append("| slot | n | net USD | WR | days | last close | killed | line | adjudicator (latest digest) |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for s in killed:
            wr = f"{s.wr:.0%}" if s.wr is not None else "—"
            days = s.days if s.days is not None else "—"
            out.append(f"| {s.slot_id} | {s.n} | {s.net:+.2f} | {wr} | {days} | {_fmt_day(s.last_close_ts)} | "
                       f"{s.killed} | {s.rule_text} | {s.adjudicator or '—'} |")
    else:
        out.append("(none)")
    out.append("")
    if not active:
        out.append("no paper slots running")
    return "\n".join(out).rstrip() + "\n"


def detect_events(prev: Optional[dict], slots: list) -> tuple:
    """(events, new_state). Events fire only on a False→True transition since the
    previous maint run; with no previous state (first run) the flags are recorded
    silently as the baseline."""
    new = {"slots": {}}
    events = []
    for s in slots:
        if s.killed is not None or s.line is None:
            continue
        flags = {"crossed": s.crossed, "verdict_reached": s.verdict_reached}
        new["slots"][s.slot_id] = flags
        if prev is None:
            continue
        old = (prev.get("slots") or {}).get(s.slot_id) or {"crossed": False, "verdict_reached": False}
        if flags["crossed"] and not old.get("crossed"):
            events.append(f"{s.slot_id} crossed its registered kill line (n={s.n}, net ${s.net:+.2f}; "
                          f"line: {s.line['rule']}; source {s.line['source']})")
        elif flags["verdict_reached"] and not old.get("verdict_reached"):
            events.append(f"{s.slot_id} reached verdict_n ({s.progress()}, net ${s.net:+.2f}) — PASS is never a promotion; "
                          f"the adjudicator's CI95 read decides PASS/INCONCLUSIVE and the owner decides anything further")
    return events, new


def run_maint(ctx: Ctx) -> list:
    """Returns the list of alert strings (empty = silent)."""
    if ctx.registered_ids is None:
        ctx.registered_ids = registered_slot_ids(ctx.bot_dir / "bot.py")
    if ctx.experiments is None:
        ctx.experiments = _load_experiments()
    lines = kill_lines(ctx.experiments)
    digest = latest_adjudicator_digest(ctx.adjudicator_log)
    slots = collect_slots(ctx, lines, (digest or {}).get("grades", {}))
    now = ctx.now()
    text = render_paper_status(slots, digest, ctx.bot_alive(), now)
    ctx.kb_dir.mkdir(parents=True, exist_ok=True)
    old_text = ctx.paper_status_path.read_text() if ctx.paper_status_path.exists() else None
    ctx.paper_status_path.write_text(text)
    status_changed = text != old_text
    active = [s.slot_id for s in slots if s.killed is None]
    log.info("maint: %d registered slots, %d active (%s), %d killed; PAPER_STATUS.md written",
             len(slots), len(active), ", ".join(active) or "none", len(slots) - len(active))
    prev = _load_json(ctx.maint_state_path, None) if ctx.maint_state_path.exists() else None
    events, new_state = detect_events(prev, slots)
    if prev is None:
        log.info("maint: first run — baseline recorded, nothing announced")
    new_state["last_run"] = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    ctx.maint_state_path.write_text(json.dumps(new_state, indent=1, sort_keys=True) + "\n")
    if events:
        today = datetime.fromtimestamp(now, tz=PT).strftime("%Y-%m-%d")
        line = (f"- {today} — maint: " + "; ".join(events) +
                ". Rule: a crossed or decided paper line is evidence, not an action — the next desk run's reconciler "
                "writes the kb row; maint promotes, kills and restarts nothing.")
        with ctx.lessons_path.open("a") as f:
            if not ctx.lessons_path.read_text().endswith("\n"):
                f.write("\n")
            f.write(line + "\n")
        log.info("maint: LESSONS line appended: %s", line[:200])
        ctx.telegram(f"🧪 swarm maint {today}\n" + "\n".join(events) + "\nsee research/swarm/kb/PAPER_STATUS.md")
    # Commit (pathspec, NO push) what maint wrote so the daily `pull --ff-only` never
    # trips on a dirty PAPER_STATUS.md / LESSONS.md; the weekly desk run pushes.
    paths = (["research/swarm/kb/PAPER_STATUS.md"] if status_changed else []) + \
            (["research/swarm/kb/LESSONS.md"] if events else [])
    if paths:
        stamp = datetime.fromtimestamp(now, tz=PT).strftime("%Y-%m-%d %I:%M %p PT")
        rc, out = git_commit_paths(ctx, f"swarm: maint {stamp} — PAPER_STATUS{' + LESSONS' if events else ''}\n\n{COMMIT_TRAILER}", paths)
        log.info("maint: commit %s → rc=%s %s", paths, rc, (out.strip().splitlines() or [""])[-1][:120])
    return events


# ── desk: args, command line, result ──────────────────────────────────────────
def build_desk_args(when_utc: datetime, kb_dir: Path, test: bool) -> dict:
    """The exact `args` object for desk.js (README "Running the desk"). Timestamps are
    the launch time: run_id in PT wall time, now in ISO UTC."""
    when_utc = when_utc.astimezone(timezone.utc)
    pt = when_utc.astimezone(PT)
    run_id = pt.strftime("%Y-%m-%d-%H%M")
    return {
        "run_id": ("dryrun-" + run_id) if test else run_id,
        "now": when_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "today": pt.strftime("%Y-%m-%d"),
        "judge_model": os.environ.get("SWARM_JUDGE_MODEL") or None,
        "max_analysts": 1 if test else 8,
        "max_screens": 1 if test else 5,
        "dry_run": bool(test),
        "constraints_md": (kb_dir / "CONSTRAINTS.md").read_text(),
        "standards_md": (kb_dir / "STANDARDS.md").read_text(),
    }


def desk_prompt(launch_args_rel: str, run_id: str) -> str:
    return (
        f"You are the launch controller for the Phmex-S edge-research desk (research/swarm/README.md, "
        f"section 'Running the desk'). Do exactly this and nothing else:\n"
        f"1. Read the file {launch_args_rel} and parse it as JSON. It is the complete `args` object for run {run_id}.\n"
        f"2. Invoke the Workflow tool once: Workflow({{ scriptPath: \"{DESK_SCRIPT}\", args: <that object, every field verbatim, "
        f"nothing added, nothing changed> }}). Run it alone — do not start any other workflow or agent.\n"
        f"3. When the workflow returns, reply with exactly one line: `{RESULT_MARKER} <the returned object as compact JSON, "
        f"plus two extra top-level fields constraints_len and standards_len = the character lengths (.length) of the "
        f"constraints_md and standards_md strings you actually passed to Workflow>` and nothing else. If the workflow "
        f"throws, reply `{RESULT_MARKER} {{\"run_id\": \"{run_id}\", \"result\": \"WORKFLOW_ERROR\", "
        f"\"error\": \"<message>\", \"constraints_len\": <n>, \"standards_len\": <n>}}`.\n"
        f"Rules: if you do not have a Workflow tool, reply with exactly `{UNAVAILABLE_MARKER}` and stop. Never edit bot code, "
        f".env, any trading_state file or sentinel; never run launchctl, main.py or anything that places an order; never "
        f"resume or relaunch the workflow yourself; do not commit or push (the runner does that)."
    )


def build_claude_cmd(launch_args_rel: str, run_id: str, claude_bin: str = CLAUDE_BIN) -> list:
    """Pure: the headless `claude -p` argv (pattern: scripts/nightly_research.py). Model from
    SWARM_DESK_MODEL (unset → omitted → account default). Tests assert on this list; the
    spawn itself lives in _real_launch."""
    cmd = [claude_bin, "-p", desk_prompt(launch_args_rel, run_id),
           "--allowedTools", *DESK_TOOLS,
           "--permission-mode", "acceptEdits",
           "--max-turns", "40",
           "--output-format", "text"]
    model = os.environ.get("SWARM_DESK_MODEL")
    if model:
        cmd += ["--model", model]
    return cmd


def parse_desk_result(stdout: str) -> Optional[dict]:
    lines = [l.strip() for l in (stdout or "").splitlines() if l.strip()]
    for l in reversed(lines):
        if l.startswith(RESULT_MARKER):
            try:
                obj = json.loads(l[len(RESULT_MARKER):].strip())
                return obj if isinstance(obj, dict) else None
            except ValueError:
                return None
    if any(l == UNAVAILABLE_MARKER or l.endswith(UNAVAILABLE_MARKER) for l in lines):
        return {"result": UNAVAILABLE_MARKER}
    return None


def _counts(res: dict) -> str:
    theses = sum((l.get("theses") or 0) for l in (res.get("lenses") or []) if isinstance(l, dict))
    return (f"theses {theses} · gate rejected {len(res.get('gate_rejected') or [])} · "
            f"screened {len(res.get('results') or [])} · passed {len(res.get('passed') or [])}")


def _commit_run(ctx: Ctx, run_id: str, code: str) -> str:
    paths = ["research/swarm/kb", f"research/swarm/runs/{run_id}"]   # never .env, never data; pathspec commit
    rc, out = git_commit_paths(ctx, f"swarm: desk run {run_id} — {code}\n\n{COMMIT_TRAILER}", paths)
    if rc != 0:
        log.info("git commit: nothing committed (rc=%s): %s", rc, out.strip()[:200])
        return "nothing to commit" if "nothing to commit" in out else f"commit FAILED (rc={rc}, see log)"
    rc, out = ctx.git(["push"])
    if rc != 0:
        log.warning("git push failed (rc=%s): %s", rc, out.strip()[:300])
        return "committed; PUSH FAILED (push by hand)"
    return "committed + pushed"


def check_passthrough(res: dict, args: dict) -> bool:
    """One-time fidelity read: the headless session re-emits launch_args.json fields
    verbatim, which cannot be verified from outside — it reports the lengths of the
    two strings it passed and we compare them to the file contents. WARNING on
    mismatch or when the fields are missing; True only on an exact match."""
    ok = True
    for key, fld in (("constraints_len", "constraints_md"), ("standards_len", "standards_md")):
        got, want = res.get(key), len(args[fld])
        if got is None:
            log.warning("pass-through fidelity: %s not reported by the session (expected %d)", key, want)
            ok = False
        elif int(got) != want:
            log.warning("pass-through fidelity MISMATCH: %s=%s but %s is %d chars — the session did not pass the file verbatim",
                        key, got, fld, want)
            ok = False
    if ok:
        log.info("pass-through fidelity OK: constraints_len=%d standards_len=%d match launch_args.json",
                 len(args["constraints_md"]), len(args["standards_md"]))
    return ok


def missing_artifacts(run_dir: Path) -> list:
    return [a for a in DESK_ARTIFACTS if not (run_dir / a).exists()]


def run_desk(ctx: Ctx, test: bool = False) -> int:
    tag = " [TEST — dry-run args]" if test else ""
    try:
        alerts = run_maint(ctx)
    except Exception as e:
        log.error("maint failed before the desk launch: %s", traceback.format_exc())
        alerts = [f"maint FAILED: {e}"]
    missing = [n for n in ("CONSTRAINTS.md", "STANDARDS.md") if not (ctx.kb_dir / n).exists()]
    if missing:
        msg = f"⚠️ swarm desk{tag}: not launched — kb/{', kb/'.join(missing)} missing (desk.js requires their contents)"
        log.error(msg)
        ctx.telegram(msg)
        return EXIT_FAIL
    when = datetime.fromtimestamp(ctx.now(), tz=timezone.utc)
    args = build_desk_args(when, ctx.kb_dir, test)
    run_id = args["run_id"]
    run_dir = ctx.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "launch_args.json").write_text(json.dumps(args, indent=1) + "\n")
    rel = f"research/swarm/runs/{run_id}/launch_args.json"
    cmd = build_claude_cmd(rel, run_id, claude_bin=ctx.claude_bin)
    log.info("desk%s: launching run %s (model=%s judge=%s timeout=%ds)", tag, run_id,
             os.environ.get("SWARM_DESK_MODEL") or "account default", args["judge_model"] or "inherit", DESK_TIMEOUT_S)
    launch = ctx.launcher(cmd, cwd=str(ctx.bot_dir), timeout=DESK_TIMEOUT_S)

    res: dict = {}
    if launch.timed_out:
        code = "TIMEOUT"
    elif launch.returncode != 0:
        code = "CLAUDE_FAILED"
        log.error("claude rc=%s stderr=%s", launch.returncode, (launch.stderr or "")[:500])
    else:
        parsed = parse_desk_result(launch.stdout)
        if parsed is None:
            code = "NO_RESULT"
            log.error("no %s line in claude output (last 400 chars): %s", RESULT_MARKER, (launch.stdout or "")[-400:])
        elif parsed.get("result") == UNAVAILABLE_MARKER:
            code = "WORKFLOW_UNAVAILABLE"
        else:
            res = parsed
            code = str(parsed.get("result") or "NO_RESULT")
            check_passthrough(res, args)
            if code in DESK_CODES and code != "WEB_BUDGET_EXHAUSTED" and missing_artifacts(run_dir):
                log.error("desk%s: result %s but %s missing in %s — treating as NO_ARTIFACTS",
                          tag, code, ", ".join(missing_artifacts(run_dir)), run_dir)
                code = "NO_ARTIFACTS"
    log.info("desk%s: run %s → %s", tag, run_id, code)

    git_note = _commit_run(ctx, run_id, code)
    report = run_dir / "REPORT.md"
    if report.exists():
        head = "\n".join(report.read_text().splitlines()[:3])
    else:
        head = f"REPORT.md missing (research/swarm/runs/{run_id}/REPORT.md was not written)"
    lines = [f"🧠 swarm desk {run_id}{tag}", f"result: {code}", head]
    if res:
        lines.append("counts: " + _counts(res))
    if code == "SURVIVORS":
        lines.append(f"committee PASS: {', '.join(res.get('passed') or [])} — Gate A: owner decision required; "
                     "build.js is never invoked by the scheduler. STOP.")
    if alerts:
        lines.append("maint alerts: " + " | ".join(alerts))
    if code == "WORKFLOW_UNAVAILABLE":
        lines.append("desk run due — paste this into a fresh Claude Code session:")
        lines.append(MANUAL_LAUNCH_ONE_LINER)
    elif code == "TIMEOUT":
        lines.append(f"desk TIMED OUT after {DESK_TIMEOUT_S // 60} min — manual launch: {MANUAL_LAUNCH_ONE_LINER}")
    elif code in ("WEB_BUDGET_EXHAUSTED", "CLAUDE_FAILED", "NO_RESULT", "NO_ARTIFACTS", "WORKFLOW_ERROR"):
        lines.append(f"{'FAILED' if code != 'WEB_BUDGET_EXHAUSTED' else 'analysts could not search'} — "
                     f"manual launch from a fresh session: {MANUAL_LAUNCH_ONE_LINER}")
    lines.append(f"git: {git_note} · log ~/Library/Logs/Phmex-S/swarm_desk.log")
    ctx.telegram("\n".join(lines))

    if test:
        if code in DESK_CODES and not missing_artifacts(run_dir):
            print(f"HEADLESS WORKFLOW: OK — result {code}; REPORT.md + CRITIC.md present in research/swarm/runs/{run_id}")
        elif code == "WORKFLOW_UNAVAILABLE":
            print("HEADLESS WORKFLOW: UNAVAILABLE — `claude -p` has no Workflow tool; desk mode will fall back to the "
                  "Telegram paste instruction (README Cadence)")
        else:
            print(f"HEADLESS WORKFLOW: FAILED — {code} (stderr: {(launch.stderr or '')[:300]!r})")
    return EXIT_OK if code in DESK_CODES else EXIT_FAIL


# ── entry point ───────────────────────────────────────────────────────────────
def _setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    for h in list(log.handlers):
        log.removeHandler(h)
        h.close()
    fmt = logging.Formatter("%(asctime)s [SWARM-DESK] %(message)s")
    fh = logging.FileHandler(log_dir / "swarm_desk.log")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
    log.setLevel(logging.INFO)
    log.propagate = False


def main(argv=None, ctx: Optional[Ctx] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", choices=("desk", "maint", "test"), required=True)
    a = ap.parse_args(argv)
    ctx = ctx or Ctx.real()
    _setup_logging(ctx.log_dir)
    if ctx.halt_path.exists():
        log.info("halt sentinel present (scripts/.halt_swarm_desk) — skipping --mode %s", a.mode)
        return EXIT_OK
    busy = other_desk_processes(ctx.pgrep(), ctx.pid)
    if busy:
        log.warning("run-alone guard: another swarm_desk desk/test process is alive (pid %s) — refusing --mode %s",
                    ", ".join(map(str, busy)), a.mode)
        return EXIT_BUSY
    branch, want = current_branch(ctx), expected_branch()
    log.info("branch: %s (SWARM_BRANCH=%s)", branch, want)
    if a.mode != "maint" and branch != want:
        msg = f"⚠️ swarm desk refused: on branch {branch}, expected {want} (set SWARM_BRANCH or check out {want})"
        log.error(msg)
        ctx.telegram(msg)
        return EXIT_FAIL
    git_pull(ctx)
    try:
        if a.mode == "maint":
            run_maint(ctx)
            return EXIT_OK
        return run_desk(ctx, test=(a.mode == "test"))
    except Exception as e:
        log.error("--mode %s crashed: %s", a.mode, traceback.format_exc())
        ctx.telegram(f"⚠️ swarm {a.mode} crashed: {str(e)[:200]} — see ~/Library/Logs/Phmex-S/swarm_desk.log")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
