"""scripts/swarm_desk.py — scheduled desk runner + daily no-LLM paper maintenance.

Nothing here spawns `claude`, touches launchctl, or reads the real state files:
every path goes through a `swarm_desk.Ctx` built on tmp_path, and every side
effect (pgrep, git, the claude launch, Telegram) is an injected recorder.
"""
from __future__ import annotations

import json
import plistlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

BOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BOT_DIR / "scripts"))

import swarm_desk as sd  # noqa: E402

DAY = 86400.0
NOW_TS = 1789000000.0          # 2026-09-09 5:26 PM PT (2026-09-10 00:26 UTC) — fixed clock for every test


# ── fixtures ─────────────────────────────────────────────────────────────────
def _trade(net: float, closed_at: float, opened_at: float | None = None) -> dict:
    return {"symbol": "ETH/USDT:USDT", "side": "long", "entry": 1.0, "exit": 1.0,
            "margin": 5.0, "pnl_usdt": net, "fees_usdt": 0.0, "net_pnl": net,
            "reason": "take_profit", "exit_reason": "take_profit", "strategy": "x",
            "opened_at": opened_at if opened_at is not None else closed_at - 600,
            "closed_at": closed_at}


def _write_state(bot_dir: Path, slot_id: str, nets: list[float], start_ts: float,
                 mode: dict | None = None) -> None:
    trades = [_trade(n, start_ts + i * 3600) for i, n in enumerate(nets)]
    (bot_dir / f"trading_state_{slot_id}.json").write_text(json.dumps(
        {"peak_balance": 0, "closed_trades": trades, "trade_results": [], "positions": {}}))
    if mode is not None:
        (bot_dir / f"trading_state_{slot_id}_mode.json").write_text(json.dumps(mode))


def fake_git(branch="main", pull=(0, "Already up to date.")):
    """git recorder answering rev-parse with `branch`; every other command succeeds."""
    def _git(args):
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            return 0, branch + "\n"
        if args[:2] == ["pull", "--ff-only"]:
            return pull
        return 0, ""
    return _git


class Recorder:
    def __init__(self, result=None):
        self.calls: list = []
        self.result = result

    def __call__(self, *a, **kw):
        self.calls.append((a, kw))
        return self.result(*a, **kw) if callable(self.result) else self.result


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    bot_dir = tmp_path / "repo"
    kb = bot_dir / "research" / "swarm" / "kb"
    runs = bot_dir / "research" / "swarm" / "runs"
    kb.mkdir(parents=True)
    runs.mkdir(parents=True)
    (bot_dir / "scripts").mkdir()
    (kb / "CONSTRAINTS.md").write_text("# CONSTRAINTS\nc = 11.5 bps\n")
    (kb / "STANDARDS.md").write_text("# STANDARDS\n1. no fabrication\n")
    (kb / "LESSONS.md").write_text("# LESSONS — the desk's own process failures (append-only, dated)\n\n"
                                   "- 2026-09-16 — v1 ran two workflows concurrently. Rule: one workflow at a time.\n")
    (bot_dir / "trading_state.json").write_text(json.dumps(
        {"closed_trades": [_trade(99.0, NOW_TS - DAY)], "positions": {}}))   # main book: never a slot
    monkeypatch.delenv("SWARM_DESK_MODEL", raising=False)
    monkeypatch.delenv("SWARM_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("SWARM_BRANCH", raising=False)
    c = sd.Ctx(
        bot_dir=bot_dir,
        log_dir=tmp_path / "logs",
        registered_ids=["ALPHA", "BETA", "GAMMA"],
        experiments={
            # build.js shape: verdict_n / kill_net_usd / inconclusive_hard_n / registered_ts
            "ALPHA": {"registered_ts": NOW_TS - 10 * DAY, "verdict_n": 50, "kill_net_usd": -10.0,
                      "inconclusive_hard_n": 100, "prereg": "docs/x.md"},
            "BETA": {"registered_ts": NOW_TS - 30 * DAY, "verdict_n": 50, "kill_net_usd": -10.0,
                     "inconclusive_hard_n": 100, "prereg": "docs/y.md"},
        },
        pgrep=Recorder(result=[]),
        bot_alive=Recorder(result=False),
        git=Recorder(result=fake_git()),
        launcher=Recorder(result=sd.Launch(returncode=0, stdout="", stderr="", timed_out=False)),
        telegram=Recorder(result=True),
        adjudicator_log=tmp_path / "lab_adjudicator.log",
        now=lambda: NOW_TS,
        pid=4242,
    )
    return c


# ── halt sentinel + run-alone guard ───────────────────────────────────────────
@pytest.mark.parametrize("mode", ["desk", "maint", "test"])
def test_halt_sentinel_exits_zero_and_does_nothing_in_every_mode(ctx, mode):
    ctx.halt_path.write_text("owner halt")
    rc = sd.main(["--mode", mode], ctx=ctx)
    assert rc == 0
    assert ctx.launcher.calls == []
    assert ctx.telegram.calls == []
    assert ctx.git.calls == []
    assert not ctx.paper_status_path.exists()


def test_other_desk_processes_filters_self_and_maint():
    lines = ["4242 python3 scripts/swarm_desk.py --mode desk",      # me
             "5001 python3 scripts/swarm_desk.py --mode maint",     # maint never blocks
             "5002 /usr/bin/python3 /x/scripts/swarm_desk.py --mode desk",
             "5003 python3 scripts/swarm_desk.py --mode test"]
    assert sd.other_desk_processes(lines, my_pid=4242) == [5002, 5003]
    assert sd.other_desk_processes(["4242 python3 scripts/swarm_desk.py --mode desk"], my_pid=4242) == []
    assert sd.other_desk_processes([], my_pid=1) == []


@pytest.mark.parametrize("mode", ["desk", "maint", "test"])
def test_run_alone_guard_refuses_a_duplicate(ctx, mode):
    ctx.pgrep = Recorder(result=["7777 python3 scripts/swarm_desk.py --mode desk"])
    rc = sd.main(["--mode", mode], ctx=ctx)
    assert rc == sd.EXIT_BUSY and rc != 0
    assert ctx.launcher.calls == []
    assert ctx.git.calls == []          # not even the pull
    assert not ctx.paper_status_path.exists()


def test_git_pull_failure_is_logged_and_the_run_continues(ctx):
    ctx.git = Recorder(result=fake_git(pull=(1, "fatal: no network")))
    rc = sd.main(["--mode", "maint"], ctx=ctx)
    assert rc == 0
    assert ["pull", "--ff-only"] in [c[0][0] for c in ctx.git.calls]
    assert ctx.paper_status_path.exists()


# ── branch awareness ──────────────────────────────────────────────────────────
def _log_text(ctx):
    return (ctx.log_dir / "swarm_desk.log").read_text()


@pytest.mark.parametrize("mode", ["desk", "test"])
def test_desk_and_test_refuse_on_the_wrong_branch_before_maint_or_launch(ctx, mode):
    ctx.git = Recorder(result=fake_git(branch="edge-swarm-v2"))
    rc = sd.main(["--mode", mode], ctx=ctx)
    assert rc == 1
    assert ctx.launcher.calls == []
    assert not ctx.paper_status_path.exists()                    # maint did not run
    assert ["pull", "--ff-only"] not in [c[0][0] for c in ctx.git.calls]
    tg = ctx.telegram.calls[0][0][0]
    assert "desk refused: on branch edge-swarm-v2, expected main" in tg
    assert "branch: edge-swarm-v2 (SWARM_BRANCH=main)" in _log_text(ctx)


def test_swarm_branch_env_overrides_the_default(ctx, monkeypatch):
    monkeypatch.setenv("SWARM_BRANCH", "edge-swarm-v2")
    ctx.git = Recorder(result=fake_git(branch="edge-swarm-v2"))
    _desk_ok(ctx)
    assert sd.main(["--mode", "desk"], ctx=ctx) == 0
    assert len(ctx.launcher.calls) == 1


def test_maint_only_logs_the_branch_and_never_refuses(ctx):
    ctx.git = Recorder(result=fake_git(branch="edge-swarm-v2"))
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    assert sd.main(["--mode", "maint"], ctx=ctx) == 0
    assert ctx.paper_status_path.exists()
    assert "branch: edge-swarm-v2 (SWARM_BRANCH=main)" in _log_text(ctx)
    assert ctx.telegram.calls == []


# ── maint ─────────────────────────────────────────────────────────────────────
def test_maint_writes_paper_status_for_fixture_slots(ctx):
    bd = ctx.bot_dir
    _write_state(bd, "ALPHA", [0.5, -0.2, 0.9], NOW_TS - 9 * DAY)                     # active, above line
    _write_state(bd, "BETA", [0.3] * 20 + [-0.1] * 10, NOW_TS - 29 * DAY)              # active, n=30/50
    _write_state(bd, "GAMMA", [-1.0, -2.0], NOW_TS - 40 * DAY,
                 mode={"paper_mode": True, "killed_at": NOW_TS - 20 * DAY, "loss_cap_usdt": -5.0})
    _write_state(bd, "OLD_era1", [-9.0] * 5, NOW_TS - 90 * DAY)                        # unregistered archive
    rc = sd.main(["--mode", "maint"], ctx=ctx)
    assert rc == 0
    txt = ctx.paper_status_path.read_text()
    assert txt.startswith("# PAPER_STATUS")
    assert "swarm_desk.py --mode maint" in txt and "do not edit" in txt
    # header honesty: bot process + adjudicator digest state
    assert "Bot process: STOPPED" in txt
    assert "no adjudicator digest found" in txt
    # ALPHA: n=3, net +1.20, WR 2/3, 10 days since registration, kill line −$10 → distance 11.20
    alpha = next(l for l in txt.splitlines() if l.startswith("| ALPHA "))
    for cell in ("| 3 |", "| +1.20 |", "| 67% |", "| 10 |", "3/50", "11.20 above"):
        assert cell in alpha, (cell, alpha)
    assert "net <= $-10.00 at any n" in alpha
    # BETA: n=30, net +5.00, WR 67%, 30 days, 30/50
    beta = next(l for l in txt.splitlines() if l.startswith("| BETA "))
    for cell in ("| 30 |", "| +5.00 |", "| 67% |", "| 30 |", "30/50"):
        assert cell in beta, (cell, beta)
    # GAMMA killed: listed under killed, not active; rail from sidecar
    assert "## Killed / retired" in txt
    gamma = next(l for l in txt.splitlines() if l.startswith("| GAMMA "))
    assert "| 2 |" in gamma and "| -3.00 |" in gamma and "killed" in gamma
    active_section = txt.split("## Killed / retired")[0]
    assert "| GAMMA " not in active_section
    # unregistered archive and the main book never appear
    assert "OLD_era1" not in txt and "trading_state.json" not in txt.split("\n", 3)[3]
    assert "no paper slots running" not in txt
    # first run = baseline: state written, LESSONS untouched, Telegram silent
    st = json.loads(ctx.maint_state_path.read_text())
    assert st["schema"] == sd.MAINT_SCHEMA
    assert set(st["slots"]) == {"ALPHA", "BETA", "GAMMA"}          # killed slots are tracked too (killed flag)
    assert st["slots"]["ALPHA"] == {"crossed": False, "verdict_reached": False, "killed": False}
    assert st["slots"]["GAMMA"]["killed"] is True
    assert ctx.lessons_path.read_text().count("\n- ") == 1
    assert ctx.telegram.calls == []


def test_maint_reads_the_latest_adjudicator_digest_from_its_log(ctx):
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    ctx.adjudicator_log.write_text(
        "2026-09-08 06:00:03,307 [ADJUDICATOR] digest:\n"
        "LAB ADJUDICATOR — live forward tests (Sep 8 6:00 AM PT)\n"
        "[ALPHA] WATCH — old note\n"
        "2026-09-08 06:00:14,417 [ADJUDICATOR] telegram send: ok\n"
        "2026-09-01 06:00:03,307 [ADJUDICATOR] digest:\n"
        "LAB ADJUDICATOR — live forward tests (Sep 1 6:00 AM PT)\n"
        "[main book]    PAPER — .paper_main present\n"
        "[ALPHA]        WATCH — accruing (n=1/50) | 1 trades 1W $+0.50\n"
        "[sr_bounce_v2] KILL — registered verdict: n=117, net $-4.89 <= 0\n"
        "2026-09-01 06:00:14,417 [ADJUDICATOR] telegram send: ok\n")
    digest = sd.latest_adjudicator_digest(ctx.adjudicator_log)
    assert digest["stamp"] == "Sep 1 6:00 AM PT"
    assert digest["grades"]["ALPHA"] == "WATCH — accruing (n=1/50) | 1 trades 1W $+0.50"
    assert digest["grades"]["SR_BOUNCE"].startswith("KILL — registered verdict")   # legacy key mapped to the slot id
    assert "main book" not in digest["grades"]
    sd.main(["--mode", "maint"], ctx=ctx)
    txt = ctx.paper_status_path.read_text()
    assert "Adjudicator digest: Sep 1 6:00 AM PT (8.5 d old)" in txt
    alpha = next(l for l in txt.splitlines() if l.startswith("| ALPHA "))
    assert "WATCH — accruing (n=1/50)" in alpha
    assert "not being graded" in txt        # digest > 2 days old → the job is unloaded, no automatic kill lines


def test_maint_says_no_paper_slots_running_when_none_are_active(ctx):
    ctx.registered_ids = ["GAMMA"]
    _write_state(ctx.bot_dir, "GAMMA", [-1.0], NOW_TS - 5 * DAY,
                 mode={"paper_mode": True, "killed_at": NOW_TS - DAY})
    sd.main(["--mode", "maint"], ctx=ctx)
    txt = ctx.paper_status_path.read_text()
    assert txt.rstrip().endswith("no paper slots running")
    assert ctx.telegram.calls == []


def test_maint_kill_sentinel_file_marks_a_slot_killed(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    (ctx.bot_dir / ".kill_ALPHA").write_text("")
    sd.main(["--mode", "maint"], ctx=ctx)
    txt = ctx.paper_status_path.read_text()
    assert txt.rstrip().endswith("no paper slots running")
    assert ".kill_ALPHA" in txt


def test_maint_appends_one_lessons_line_only_on_a_crossing(ctx):
    bd = ctx.bot_dir
    ctx.registered_ids = ["ALPHA", "BETA"]
    _write_state(bd, "ALPHA", [0.5, 0.5], NOW_TS - 9 * DAY)
    _write_state(bd, "BETA", [-0.1] * 55, NOW_TS - 29 * DAY)     # already crossed (n>=50, net<=0)
    before = ctx.lessons_path.read_text()
    # run 1: baseline — BETA's crossing is recorded, not announced
    sd.main(["--mode", "maint"], ctx=ctx)
    assert ctx.lessons_path.read_text() == before
    assert ctx.telegram.calls == []
    st = json.loads(ctx.maint_state_path.read_text())
    assert st["slots"]["BETA"]["crossed"] is True
    # run 2: nothing changed — still silent
    sd.main(["--mode", "maint"], ctx=ctx)
    assert ctx.lessons_path.read_text() == before
    assert ctx.telegram.calls == []
    # run 3: ALPHA falls through its −$10 line → exactly ONE dated line + one Telegram
    _write_state(bd, "ALPHA", [0.5, -6.0, -5.0], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    after = ctx.lessons_path.read_text()
    new_lines = [l for l in after[len(before):].splitlines() if l.strip()]
    assert len(new_lines) == 1
    line = new_lines[0]
    assert line.startswith("- 2026-09-09 — maint: ALPHA crossed its registered kill line")
    assert "net $-10.50" in line and "Rule:" in line
    assert "BETA" not in line
    assert len(ctx.telegram.calls) == 1
    assert "ALPHA crossed" in ctx.telegram.calls[0][0][0]
    # run 4: same state → no second line, no second Telegram
    sd.main(["--mode", "maint"], ctx=ctx)
    assert ctx.lessons_path.read_text() == after
    assert len(ctx.telegram.calls) == 1


def test_maint_alerts_once_when_a_slot_reaches_verdict_n_with_positive_net(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.2] * 49, NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)                       # baseline at n=49
    before = ctx.lessons_path.read_text()
    _write_state(ctx.bot_dir, "ALPHA", [0.2] * 50, NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    new = [l for l in ctx.lessons_path.read_text()[len(before):].splitlines() if l.strip()]
    assert len(new) == 1 and "reached verdict_n" in new[0] and "50/50" in new[0]
    assert "PASS is never a promotion" in new[0]
    assert len(ctx.telegram.calls) == 1
    assert "reached verdict_n" in ctx.telegram.calls[0][0][0]


def test_maint_only_writes_paper_status_and_the_state_file(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    snapshot = {p: p.read_bytes() for p in ctx.bot_dir.rglob("*") if p.is_file()}
    sd.main(["--mode", "maint"], ctx=ctx)
    after = {p: p.read_bytes() for p in ctx.bot_dir.rglob("*") if p.is_file()}
    changed = {p for p in after if snapshot.get(p) != after[p]}
    assert changed == {ctx.paper_status_path, ctx.maint_state_path}
    assert ctx.launcher.calls == []


def test_maint_commits_paper_status_by_pathspec_without_push_and_only_when_changed(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    calls = [c[0][0] for c in ctx.git.calls]
    assert ["add", "research/swarm/kb/PAPER_STATUS.md"] in calls
    commit = next(c for c in calls if c[0] == "commit")
    assert commit[-2:] == ["--", "research/swarm/kb/PAPER_STATUS.md"]
    assert "Co-Authored-By: Claude" in commit[commit.index("-m") + 1]
    assert ["push"] not in calls
    # unchanged body → no second commit, even though the "Written <stamp>" header moved an hour
    ctx.git.calls.clear()
    ctx.now = lambda: NOW_TS + 3600
    sd.main(["--mode", "maint"], ctx=ctx)
    assert not any(c[0][0][0] in ("add", "commit") for c in ctx.git.calls)
    assert "Written 2026-09-09 06:26 PM PT" in ctx.paper_status_path.read_text()   # the stamp itself is still refreshed
    ctx.now = lambda: NOW_TS
    # a real flip on the header line (bot process STOPPED → RUNNING) is NOT masked by the stamp handling
    ctx.git.calls.clear()
    ctx.bot_alive = Recorder(result=True)
    sd.main(["--mode", "maint"], ctx=ctx)
    assert ["add", "research/swarm/kb/PAPER_STATUS.md"] in [c[0][0] for c in ctx.git.calls]
    assert "Bot process: RUNNING" in ctx.paper_status_path.read_text()
    ctx.bot_alive = Recorder(result=False)
    # a crossing → LESSONS.md joins the pathspec, still no push
    _write_state(ctx.bot_dir, "ALPHA", [0.5, -11.0], NOW_TS - 9 * DAY)
    ctx.git.calls.clear()
    sd.main(["--mode", "maint"], ctx=ctx)
    commit = next(c[0][0] for c in ctx.git.calls if c[0][0][0] == "commit")
    assert commit[commit.index("--") + 1:] == ["research/swarm/kb/PAPER_STATUS.md", "research/swarm/kb/LESSONS.md"]
    assert ["push"] not in [c[0][0] for c in ctx.git.calls]


def test_status_body_neutralises_only_the_clock_tokens():
    a = "# PAPER_STATUS\n\nWritten 2026-09-09 05:26 PM PT. Bot process: STOPPED — x. Adjudicator digest: Sep 1 (7.8 d old) — not being graded.\n"
    b = "# PAPER_STATUS\n\nWritten 2026-09-10 05:26 PM PT. Bot process: STOPPED — x. Adjudicator digest: Sep 1 (8.8 d old) — not being graded.\n"
    c = "# PAPER_STATUS\n\nWritten 2026-09-10 05:26 PM PT. Bot process: RUNNING. Adjudicator digest: Sep 1 (8.8 d old) — not being graded.\n"
    d = "# PAPER_STATUS\n\nWritten 2026-09-10 05:26 PM PT. Bot process: STOPPED — x. Adjudicator digest: Sep 1 (1.8 d old).\n"
    assert sd._status_body(a) == sd._status_body(b)           # stamp + age ticked, nothing else → no change
    assert sd._status_body(a) != sd._status_body(c)           # bot flip → change
    assert sd._status_body(a) != sd._status_body(d)           # stale-flag flip → change
    assert "STOPPED" in sd._status_body(a) and "not being graded" in sd._status_body(a)


def test_git_add_failure_is_reported_and_skips_the_commit(ctx):
    def git(args):
        if args[0] == "add":
            return 128, "fatal: index.lock"
        return fake_git()(args)
    ctx.git = Recorder(result=git)
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    assert not any(c[0][0][0] == "commit" for c in ctx.git.calls)
    assert "git add" in _log_text(ctx) and "failed" in _log_text(ctx)


def test_adjudicator_key_map_never_puts_a_live_grade_on_the_paper_mr_row():
    assert "mr_bundle" not in sd.ADJ_KEY_TO_SLOT
    assert sd.ADJ_KEY_TO_SLOT["sr_bounce_v2"] == "SR_BOUNCE"


def test_legacy_kill_lines_are_registered_for_the_known_slots():
    from lab_adjudicator import adjudicate
    lines = sd.kill_lines(adjudicate.EXPERIMENTS)
    assert lines["SR_BOUNCE"]["verdict_n"] == 50 and lines["SR_BOUNCE"]["since_ts"] == 1785991620
    assert lines["ETH_TSM_28"]["kill_net_usd"] == -10.0
    assert lines["DONCHIAN_BTC"]["kill_net_usd"] == -15.0 and "2026-07-16-donchian" in lines["DONCHIAN_BTC"]["source"]
    assert lines["VWAP_CROSS"]["kill_net_usd"] is None and lines["VWAP_CROSS"]["verdict_n"] is None
    # a build.js-shaped entry is picked up under its own id
    lines = sd.kill_lines({"zeta_flow": {"registered_ts": 1.0, "verdict_n": 50, "kill_net_usd": -10.0,
                                         "inconclusive_hard_n": 100, "prereg": "docs/z.md"}})
    assert lines["zeta_flow"]["verdict_n"] == 50 and lines["zeta_flow"]["since_ts"] == 1.0
    assert lines["zeta_flow"]["source"] == "docs/z.md"


def test_registered_slot_ids_are_parsed_from_bot_py():
    ids = sd.registered_slot_ids(BOT_DIR / "bot.py")
    for want in ("5m_mean_revert", "SR_BOUNCE", "DONCHIAN_BTC", "DONCHIAN_ETH", "ETH_TSM_28", "HTF_L2", "VWAP_CROSS"):
        assert want in ids, want
    assert "5m_scalp" not in ids          # the main book's label, not a slot


# ── desk args + claude command line ───────────────────────────────────────────
def test_build_desk_args_full_and_test_shapes(ctx, monkeypatch):
    when = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)      # 3:00 AM PT (PDT)
    args = sd.build_desk_args(when, ctx.kb_dir, test=False)
    assert args["run_id"] == "2026-09-20-0300"
    assert args["now"] == "2026-09-20T10:00:00Z"
    assert args["today"] == "2026-09-20"
    assert args["judge_model"] is None
    assert args["max_analysts"] == 8 and args["max_screens"] == 5 and args["dry_run"] is False
    assert args["constraints_md"] == (ctx.kb_dir / "CONSTRAINTS.md").read_text()
    assert args["standards_md"] == (ctx.kb_dir / "STANDARDS.md").read_text()
    monkeypatch.setenv("SWARM_JUDGE_MODEL", "claude-opus-4-1")
    t = sd.build_desk_args(when, ctx.kb_dir, test=True)
    assert t["run_id"] == "dryrun-2026-09-20-0300"
    assert t["max_analysts"] == 1 and t["max_screens"] == 1 and t["dry_run"] is True
    assert t["judge_model"] == "claude-opus-4-1"


def test_build_claude_cmd_carries_required_tools_and_flags(monkeypatch):
    monkeypatch.delenv("SWARM_DESK_MODEL", raising=False)
    cmd = sd.build_claude_cmd("research/swarm/runs/2026-09-20-0300/launch_args.json",
                              run_id="2026-09-20-0300", claude_bin="/x/claude")
    assert cmd[0] == "/x/claude" and cmd[1] == "-p"
    prompt = cmd[2]
    assert "research/swarm/workflows/desk.js" in prompt
    assert "research/swarm/runs/2026-09-20-0300/launch_args.json" in prompt
    assert sd.RESULT_MARKER in prompt and sd.UNAVAILABLE_MARKER in prompt
    assert "build.js" not in prompt
    i = cmd.index("--allowedTools")
    tools = []
    for tok in cmd[i + 1:]:
        if tok.startswith("--"):
            break
        tools.append(tok)
    for t in ("Workflow", "WebSearch", "WebFetch", "Read", "Write", "Bash", "Glob", "Grep"):
        assert t in tools, t
    k = cmd.index("--disallowedTools")
    disallowed = []
    for tok in cmd[k + 1:]:
        if tok.startswith("--"):
            break
        disallowed.append(tok)
    for d in ("Bash(launchctl:*)", "Bash(*main.py*)", "Bash(git push:*)",
              "Bash(kill:*)", "Bash(pkill:*)", "Bash(rm -rf:*)"):
        assert d in disallowed, d
    j = cmd.index("--permission-mode")
    assert cmd[j + 1] == "acceptEdits"
    assert "--model" not in cmd
    assert sd.DESK_TIMEOUT_S == 75 * 60


def test_build_claude_cmd_model_from_env(monkeypatch):
    monkeypatch.setenv("SWARM_DESK_MODEL", "claude-opus-4-1")
    cmd = sd.build_claude_cmd("a.json", run_id="r", claude_bin="/x/claude")
    assert cmd[cmd.index("--model") + 1] == "claude-opus-4-1"


def test_parse_desk_result():
    out = ("some chatter\n" + sd.RESULT_MARKER + ' {"run_id": "r", "result": "NO_SURVIVORS", "passed": []}\n')
    assert sd.parse_desk_result(out) == {"run_id": "r", "result": "NO_SURVIVORS", "passed": []}
    assert sd.parse_desk_result("nothing here") is None
    assert sd.parse_desk_result(sd.RESULT_MARKER + " not json") is None
    assert sd.parse_desk_result("blah\n" + sd.UNAVAILABLE_MARKER + "\n") == {"result": sd.UNAVAILABLE_MARKER}


# ── desk mode end to end (fake launcher) ──────────────────────────────────────
def _desk_ok(ctx, result_code="NO_SURVIVORS", report=True, critic=True, extra=None, lengths=True):
    def launch(cmd, cwd, timeout):
        # the "workflow" writes REPORT.md / CRITIC.md the way desk.js's closing seats do
        run_id = [t for t in cmd[2].split() if t.startswith("research/swarm/runs/")][0].split("/")[3]
        rd = ctx.runs_dir / run_id
        rd.mkdir(parents=True, exist_ok=True)
        if report:
            (rd / "REPORT.md").write_text(f"# REPORT — run {run_id}\n\nWritten now.\n\n## Verdict\nNothing survived.\n")
        if critic:
            (rd / "CRITIC.md").write_text("# CRITIC\n")
        la = json.loads((rd / "launch_args.json").read_text())
        payload = {"run_id": run_id, "result": result_code, "passed": [], "gate_rejected": [{"id": "a"}],
                   "results": [{"id": "b"}], "lenses": [{"lens": "forced_flows", "theses": 2}]}
        if lengths:
            payload.update({"constraints_len": len(la["constraints_md"]), "standards_len": len(la["standards_md"])})
        payload.update(extra or {})
        return sd.Launch(returncode=0, stdout="ok\n" + sd.RESULT_MARKER + " " + json.dumps(payload) + "\n",
                         stderr="", timed_out=False)
    ctx.launcher = Recorder(result=launch)
    return ctx


def _git_calls(ctx):
    return [c[0][0] for c in ctx.git.calls]


def test_desk_mode_runs_maint_then_launches_commits_pushes_and_telegrams(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    _desk_ok(ctx)
    rc = sd.main(["--mode", "desk"], ctx=ctx)
    assert rc == 0
    assert ctx.paper_status_path.exists()                      # maint ran first
    assert len(ctx.launcher.calls) == 1
    (cmd,), kw = ctx.launcher.calls[0]
    assert kw["timeout"] == sd.DESK_TIMEOUT_S and kw["cwd"] == str(ctx.bot_dir)
    run_id = json.loads((ctx.runs_dir).glob("*/launch_args.json").__next__().read_text())["run_id"]
    assert run_id == datetime.fromtimestamp(NOW_TS, tz=sd.PT).strftime("%Y-%m-%d-%H%M")
    la = json.loads((ctx.runs_dir / run_id / "launch_args.json").read_text())
    assert la["dry_run"] is False and la["max_analysts"] == 8 and la["constraints_md"].startswith("# CONSTRAINTS")
    assert "build.js" not in cmd[2]
    calls = _git_calls(ctx)
    assert calls[0] == ["rev-parse", "--abbrev-ref", "HEAD"] and calls[1] == ["pull", "--ff-only"]
    add = next(c for c in calls if c[0] == "add" and "research/swarm/kb" in c)
    assert add[1:] == ["research/swarm/kb", f"research/swarm/runs/{run_id}"]
    commit = next(c for c in calls if c[0] == "commit" and "desk run" in c[2])
    msg = commit[commit.index("-m") + 1]
    assert run_id in msg and "NO_SURVIVORS" in msg and "Co-Authored-By: Claude" in msg
    assert commit[commit.index("-m") + 2:] == ["--", "research/swarm/kb", f"research/swarm/runs/{run_id}"]   # pathspec commit
    assert ["push"] in calls
    assert "pass-through fidelity OK" in _log_text(ctx)
    assert len(ctx.telegram.calls) == 1
    tg = ctx.telegram.calls[0][0][0]
    assert f"# REPORT — run {run_id}" in tg and "Written now." in tg
    assert "NO_SURVIVORS" in tg
    assert "theses 2" in tg and "gate rejected 1" in tg and "screened 1" in tg and "passed 0" in tg
    assert sd.MANUAL_LAUNCH_ONE_LINER not in tg


def test_desk_mode_never_stages_env_or_data(ctx):
    _desk_ok(ctx)
    sd.main(["--mode", "desk"], ctx=ctx)
    for c in _git_calls(ctx):
        if c[0] == "add":
            assert all(not p.endswith(".env") and "data" not in p for p in c[1:])
            assert "-A" not in c and "." not in c


def test_desk_mode_survivors_is_gate_a_stop_not_a_build(ctx):
    _desk_ok(ctx, result_code="SURVIVORS", extra={"passed": ["zeta_flow"]})
    sd.main(["--mode", "desk"], ctx=ctx)
    tg = ctx.telegram.calls[0][0][0]
    assert "SURVIVORS" in tg and "zeta_flow" in tg
    assert "Gate A" in tg and "build.js" in tg and "STOP" in tg
    assert all("build.js" not in " ".join(c[0][0]) for c in ctx.launcher.calls)


def test_desk_mode_web_budget_exhausted_sends_the_manual_one_liner(ctx):
    _desk_ok(ctx, result_code="WEB_BUDGET_EXHAUSTED", report=False, critic=False)
    rc = sd.main(["--mode", "desk"], ctx=ctx)
    assert rc == 0                      # the pre-gate abort writes no REPORT/CRITIC by design — not NO_ARTIFACTS
    tg = ctx.telegram.calls[0][0][0]
    assert "WEB_BUDGET_EXHAUSTED" in tg and sd.MANUAL_LAUNCH_ONE_LINER in tg
    assert "REPORT.md" in tg          # says the report is missing rather than fabricating lines


def test_desk_mode_timeout_sends_the_manual_one_liner(ctx):
    ctx.launcher = Recorder(result=sd.Launch(returncode=None, stdout="", stderr="", timed_out=True))
    rc = sd.main(["--mode", "desk"], ctx=ctx)
    assert rc != 0
    tg = ctx.telegram.calls[0][0][0]
    assert "TIMED OUT" in tg and "75" in tg and sd.MANUAL_LAUNCH_ONE_LINER in tg


def test_desk_mode_workflow_unavailable_falls_back_to_paste_instruction(ctx):
    ctx.launcher = Recorder(result=sd.Launch(returncode=0, stdout=sd.UNAVAILABLE_MARKER + "\n", stderr="", timed_out=False))
    rc = sd.main(["--mode", "desk"], ctx=ctx)
    assert rc != 0
    tg = ctx.telegram.calls[0][0][0]
    assert "desk run due — paste this into a fresh Claude Code session:" in tg
    assert sd.MANUAL_LAUNCH_ONE_LINER in tg


def test_desk_mode_claude_failure_is_reported(ctx):
    ctx.launcher = Recorder(result=sd.Launch(returncode=1, stdout="", stderr="boom", timed_out=False))
    rc = sd.main(["--mode", "desk"], ctx=ctx)
    assert rc != 0
    tg = ctx.telegram.calls[0][0][0]
    assert "FAILED" in tg and sd.MANUAL_LAUNCH_ONE_LINER in tg


@pytest.mark.parametrize("report,critic", [(True, False), (False, True), (False, False)])
def test_desk_mode_requires_report_and_critic_else_no_artifacts(ctx, report, critic):
    _desk_ok(ctx, result_code="NO_SURVIVORS", report=report, critic=critic)
    rc = sd.main(["--mode", "desk"], ctx=ctx)
    assert rc != 0
    tg = ctx.telegram.calls[0][0][0]
    assert "result: NO_ARTIFACTS" in tg and sd.MANUAL_LAUNCH_ONE_LINER in tg
    assert "NO_ARTIFACTS" in _log_text(ctx)


def test_pass_through_fidelity_warning_on_mismatch_or_missing(ctx):
    _desk_ok(ctx, lengths=False, extra={"constraints_len": 3, "standards_len": 999999})
    sd.main(["--mode", "desk"], ctx=ctx)
    txt = _log_text(ctx)
    assert "pass-through fidelity MISMATCH: constraints_len=3" in txt
    assert "fidelity OK" not in txt
    ctx2_log = ctx.log_dir / "swarm_desk.log"
    ctx2_log.write_text("")
    _desk_ok(ctx, lengths=False)
    sd.main(["--mode", "desk"], ctx=ctx)
    assert "constraints_len not reported" in _log_text(ctx)


@pytest.mark.parametrize("bad", ["4523.0", "~4500", [1, 2], None, True, float("inf")])
def test_pass_through_non_integer_length_never_blocks_the_commit_and_push(ctx, bad):
    _desk_ok(ctx, lengths=False, extra={"constraints_len": bad, "standards_len": bad})
    rc = sd.main(["--mode", "desk"], ctx=ctx)
    assert rc == 0
    calls = _git_calls(ctx)
    assert any(c[0] == "commit" and "desk run" in c[2] for c in calls)
    assert ["push"] in calls
    txt = _log_text(ctx)
    assert "not reported as an integer" in txt and "crashed" not in txt
    assert "fidelity OK" not in txt


def test_test_mode_web_budget_exhausted_is_ok_without_artifacts(ctx, capsys):
    _desk_ok(ctx, result_code="WEB_BUDGET_EXHAUSTED", report=False, critic=False)
    rc = sd.main(["--mode", "test"], ctx=ctx)
    assert rc == 0
    out = capsys.readouterr().out
    assert "HEADLESS WORKFLOW: OK (budget exhausted" in out and "FAILED" not in out


def test_desk_mode_includes_maint_alerts_in_its_telegram(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)                          # baseline
    _write_state(ctx.bot_dir, "ALPHA", [0.5, -11.0], NOW_TS - 9 * DAY)
    _desk_ok(ctx)
    sd.main(["--mode", "desk"], ctx=ctx)
    # the maint alert went out on its own AND is echoed in the desk summary
    assert len(ctx.telegram.calls) == 2
    assert "ALPHA crossed" in ctx.telegram.calls[0][0][0]
    assert "ALPHA crossed" in ctx.telegram.calls[1][0][0]


def test_desk_mode_no_kb_documents_is_a_hard_stop_before_launch(ctx):
    (ctx.kb_dir / "STANDARDS.md").unlink()
    rc = sd.main(["--mode", "desk"], ctx=ctx)
    assert rc != 0 and ctx.launcher.calls == []
    assert "STANDARDS.md" in ctx.telegram.calls[0][0][0]


# ── test mode (headless-workflow feasibility) ─────────────────────────────────
def test_test_mode_uses_dry_run_args_and_reports_ok(ctx, capsys):
    _desk_ok(ctx, result_code="ALL_REJECTED_AT_GATE")
    rc = sd.main(["--mode", "test"], ctx=ctx)
    assert rc == 0
    la = json.loads(next(ctx.runs_dir.glob("dryrun-*/launch_args.json")).read_text())
    assert la["dry_run"] is True and la["max_analysts"] == 1 and la["max_screens"] == 1
    out = capsys.readouterr().out
    assert "HEADLESS WORKFLOW: OK" in out and "ALL_REJECTED_AT_GATE" in out
    assert "TEST" in ctx.telegram.calls[0][0][0]
    calls = [c[0][0] for c in ctx.git.calls]
    assert ["push"] in calls                       # test mode commits + pushes the dryrun dir like a real run


def test_test_mode_ok_is_not_vacuous_without_desk_artifacts(ctx, capsys):
    _desk_ok(ctx, result_code="ALL_REJECTED_AT_GATE", report=True, critic=False)
    rc = sd.main(["--mode", "test"], ctx=ctx)
    assert rc != 0
    out = capsys.readouterr().out
    assert "HEADLESS WORKFLOW: FAILED" in out and "NO_ARTIFACTS" in out


def test_test_mode_reports_unavailable_clearly(ctx, capsys):
    ctx.launcher = Recorder(result=sd.Launch(returncode=0, stdout="I do not have a Workflow tool.\n" + sd.UNAVAILABLE_MARKER,
                                             stderr="", timed_out=False))
    rc = sd.main(["--mode", "test"], ctx=ctx)
    assert rc != 0
    out = capsys.readouterr().out
    assert "HEADLESS WORKFLOW: UNAVAILABLE" in out


def test_test_mode_fails_when_no_result_code_or_run_dir(ctx, capsys):
    ctx.launcher = Recorder(result=sd.Launch(returncode=0, stdout="done, no marker", stderr="", timed_out=False))
    rc = sd.main(["--mode", "test"], ctx=ctx)
    assert rc != 0
    assert "HEADLESS WORKFLOW: FAILED" in capsys.readouterr().out


# ── plists + README ───────────────────────────────────────────────────────────
PLIST_DIR = BOT_DIR / "research" / "swarm" / "launchd"


@pytest.mark.parametrize("name,mode,cal", [
    ("com.phmex.desk-weekly", "desk", {"Weekday": 0, "Hour": 3, "Minute": 0}),
    ("com.phmex.desk-maint", "maint", {"Hour": 6, "Minute": 30}),
])
def test_plist_files_are_versioned_and_shaped_like_the_existing_jobs(name, mode, cal):
    p = PLIST_DIR / f"{name}.plist"
    assert p.exists(), p
    d = plistlib.loads(p.read_bytes())
    assert d["Label"] == name
    assert d["RunAtLoad"] is False
    assert d["ProgramArguments"] == ["/Library/Frameworks/Python.framework/Versions/3.14/bin/python3",
                                     "/Users/jonaspenaso/Desktop/Phmex-S/scripts/swarm_desk.py", "--mode", mode]
    assert d["WorkingDirectory"] == "/Users/jonaspenaso/Desktop/Phmex-S"
    assert d["StartCalendarInterval"] == cal
    for k in ("StandardOutPath", "StandardErrorPath"):
        assert d[k].startswith("/Users/jonaspenaso/Library/Logs/Phmex-S/"), d[k]
        assert "Desktop" not in d[k]
    assert d["EnvironmentVariables"] == {
        "SWARM_BRANCH": "main",
        "PATH": "/Library/Frameworks/Python.framework/Versions/3.14/bin:/Users/jonaspenaso/.local/bin:/usr/local/bin:/usr/bin:/bin",
    }
    assert d["StandardOutPath"].endswith(f"{name.split('.')[-1]}.out.log")
    assert d["StandardErrorPath"].endswith(f"{name.split('.')[-1]}.err.log")


def test_readme_cadence_section_is_complete():
    txt = (BOT_DIR / "research" / "swarm" / "README.md").read_text()
    assert "## Cadence" in txt
    cadence = txt.split("## Cadence", 1)[1]
    for needle in ("com.phmex.desk-weekly", "com.phmex.desk-maint", "Sunday 3:00 AM PT", "6:30 AM PT",
                   "launchctl bootout", "launchctl bootstrap", "scripts/.halt_swarm_desk",
                   "~/Library/Logs/Phmex-S/", "swarm_desk.log", "PAPER_STATUS.md",
                   "Gate A", "Gate B", "build.js is never invoked", "com.phmex.lab-adjudicator",
                   "WEB_BUDGET_EXHAUSTED", "--mode test", "SWARM_DESK_MODEL", "SWARM_JUDGE_MODEL",
                   sd.MANUAL_LAUNCH_ONE_LINER, "research/swarm/launchd/", "SWARM_BRANCH", "desk refused",
                   "Known limit", "constraints_len", "NO_ARTIFACTS", "CRITIC.md", "pathspec", "NO push",
                   "`--mode test` commits and pushes"):
        assert needle in cadence, needle


def test_maint_state_file_and_halt_sentinel_are_gitignored():
    gi = (BOT_DIR / ".gitignore").read_text()
    assert "research/swarm/kb/.maint_state.json" in gi
    assert "scripts/.halt_swarm_desk" in gi


def test_informed_flow_btc_alt_cascade_v2_is_picked_up_generically():
    """2026-09-20 paper slot: its adjudicator entry has the build.js shape
    (verdict_n + kill_net_usd + registered_ts + prereg) so kill_lines() lands
    it under its own id with no ADJ_KEY_TO_SLOT entry, and registered_slot_ids
    sees the bot.py StrategySlot literal. The digest line key == slot id, so
    latest_adjudicator_digest maps it 1:1 as well."""
    from lab_adjudicator import adjudicate
    sid = "informed_flow_btc_alt_cascade_v2"
    assert sid not in sd.ADJ_KEY_TO_SLOT          # generic path, no legacy alias
    lines = sd.kill_lines(adjudicate.EXPERIMENTS)
    assert lines[sid]["verdict_n"] == 50 and lines[sid]["kill_net_usd"] == -10.0
    assert lines[sid]["since_ts"] == 1789933835.0 and lines[sid]["inconclusive_hard_n"] == 100
    assert lines[sid]["source"].endswith("2026-09-20-informed_flow_btc_alt_cascade_v2-prereg.md")
    assert "n>=50" in lines[sid]["rule"] and "$-10.00" in lines[sid]["rule"] and "n=100" in lines[sid]["rule"]
    assert sid in sd.registered_slot_ids(BOT_DIR / "bot.py")


def test_digest_line_for_informed_flow_maps_to_its_slot_id(ctx):
    ctx.adjudicator_log.write_text(
        "2026-09-21 06:00:03,307 [ADJUDICATOR] digest:\n"
        "LAB ADJUDICATOR — live forward tests (Sep 21 6:00 AM PT)\n"
        "[informed_flow_btc_alt_cascade_v2] WATCH — accruing (n=2/50, net $+1.52; KILL if net <= $-10.00 at any n or net <= 0 at n=50) | 2 trades 1W $+1.52 | WR 50.0% | CI95 lo -6.480\n"
        "2026-09-21 06:00:14,417 [ADJUDICATOR] telegram send: ok\n")
    digest = sd.latest_adjudicator_digest(ctx.adjudicator_log)
    assert digest["grades"]["informed_flow_btc_alt_cascade_v2"].startswith("WATCH — accruing (n=2/50")


# ── maint: kill events + same-day kb reconciliation ───────────────────────────
KB_REAL = BOT_DIR / "research" / "swarm" / "kb"
V2 = "informed_flow_btc_alt_cascade_v2"
V2_KILL_GRADE = ("KILL — registered verdict: net $-16.20 <= $-10.00 dollar loss cap at n=5 — KILL; touched "
                 ".kill_informed_flow_btc_alt_cascade_v2 (bot's .kill_* loop closes the paper book) | 5 trades 0W "
                 "$-16.20 | WR 0.0% | CI95 lo -3.240")


def _digest(ctx, grades: dict, stamp="Sep 21 6:00 AM PT", ts="2026-09-21 06:00:02,354"):
    body = "".join(f"[{k}] {v}\n" for k, v in grades.items())
    ctx.adjudicator_log.write_text(f"{ts} [ADJUDICATOR] digest:\nLAB ADJUDICATOR — live forward tests ({stamp})\n"
                                   f"{body}2026-09-21 06:00:03,079 [ADJUDICATOR] telegram send: ok\n")


def _swarm_kb(ctx, ids=("ALPHA", "DELTA"), dead_rows=3):
    """SURVIVORS.md with one row per id (ALPHA carries a prereg doc) + a DEAD_LIST.md with `dead_rows` rows."""
    head = ("# SURVIVORS — theses that passed the risk committee (append-only)\n\n"
            "| run | id | train n | net bps | CI95 | WR | p* | prereg doc | status |\n|---|---|---|---|---|---|---|---|---|\n")
    rows = "".join(f"| 2026-09-19-1451 | {i} | 246 | +34.07 | [12.27, 56.30] | 52.44% | 52.3% | docs/{i}-prereg.md | "
                   f"committee pass — built + papered 2026-09-20 |\n" for i in ids)
    (ctx.kb_dir / "SURVIVORS.md").write_text(head + rows)
    dl = ("# DEAD_LIST — killed / null / do-not-build (append-only, cite by row)\n\n"
          "| n | family | one-line why dead | source | date |\n|---|---|---|---|---|\n")
    dl += "".join(f"| {k} | family_{k} | dead because {k} | memory/x.md | 2026-09-0{k} |\n" for k in range(1, dead_rows + 1))
    dl += "\nProse after the table.\n"
    (ctx.kb_dir / "DEAD_LIST.md").write_text(dl)


def _killed(ctx, sid, nets, killed_at, start=NOW_TS - 9 * DAY):
    _write_state(ctx.bot_dir, sid, nets, start, mode={"paper_mode": True, "killed_at": killed_at, "loss_cap_usdt": -999.0})


def _new_lessons(ctx, before):
    return [l for l in ctx.lessons_path.read_text()[len(before):].splitlines() if l.strip()]


def test_none_to_killed_fires_one_event_once_across_runs(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5, -6.0], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)                                    # baseline: alive
    st = json.loads(ctx.maint_state_path.read_text())
    assert st["schema"] == sd.MAINT_SCHEMA and st["slots"]["ALPHA"]["killed"] is False
    before = ctx.lessons_path.read_text()
    _digest(ctx, {"ALPHA": "KILL — registered verdict: net $-11.50 <= $-10.00 dollar loss cap at n=3 — KILL; "
                           "touched .kill_ALPHA | 3 trades 1W $-11.50 | WR 33.3% | CI95 lo -9.100"})
    _killed(ctx, "ALPHA", [0.5, -6.0, -6.0], NOW_TS - 3600)
    sd.main(["--mode", "maint"], ctx=ctx)                                    # None→killed
    new = _new_lessons(ctx, before)
    assert len(new) == 1
    assert new[0].startswith("- 2026-09-09 — maint: ALPHA KILLED 2026-09-09 (KILL — registered verdict: net $-11.50 <= "
                             "$-10.00 dollar loss cap at n=3 — KILL; touched .kill_ALPHA; n=3, net $-11.50)"), new[0]
    assert "Rule: maint writes the DEAD_LIST/SURVIVORS rows the same day; the desk reconciler never duplicates them; " \
           "maint promotes, kills and restarts nothing." in new[0]
    assert "next desk run's reconciler" not in new[0]
    assert len(ctx.telegram.calls) == 1 and "ALPHA KILLED 2026-09-09" in ctx.telegram.calls[0][0][0]
    assert json.loads(ctx.maint_state_path.read_text())["slots"]["ALPHA"]["killed"] is True
    after = ctx.lessons_path.read_text()
    sd.main(["--mode", "maint"], ctx=ctx)                                    # still killed → silent
    assert ctx.lessons_path.read_text() == after and len(ctx.telegram.calls) == 1


def test_killed_without_a_kill_grade_cites_the_sidecar(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    _digest(ctx, {"ALPHA": "WATCH — accruing (n=1/50, net $+0.50) | 1 trades 1W $+0.50"})   # stale, not a KILL
    _killed(ctx, "ALPHA", [0.5], NOW_TS - 2 * DAY)
    alerts = sd.run_maint(ctx)
    assert alerts == ["ALPHA KILLED 2026-09-07 (sidecar killed_at; n=1, net $+0.50)"]


def test_crossed_and_killed_in_the_same_interval_is_one_event_killed_wins(ctx):
    ctx.registered_ids = ["ALPHA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    before = ctx.lessons_path.read_text()
    _killed(ctx, "ALPHA", [0.5, -11.0], NOW_TS - 60)                         # crossed the −$10 line AND killed
    alerts = sd.run_maint(ctx)
    assert len(alerts) == 1 and alerts[0].startswith("ALPHA KILLED 2026-09-09")
    assert "crossed" not in alerts[0]
    assert len(_new_lessons(ctx, before)) == 1 and len(ctx.telegram.calls) == 1
    st = json.loads(ctx.maint_state_path.read_text())["slots"]["ALPHA"]
    assert st == {"crossed": True, "verdict_reached": False, "killed": True}
    # the crossing was recorded with the kill: a later run never re-fires it
    assert sd.run_maint(ctx) == []


def test_first_run_and_old_schema_state_baseline_killed_slots_silently(ctx):
    ctx.registered_ids = ["ALPHA", "GAMMA"]
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    _killed(ctx, "GAMMA", [-1.0], NOW_TS - 20 * DAY, start=NOW_TS - 40 * DAY)
    assert sd.run_maint(ctx) == []                                           # first run: baseline
    assert json.loads(ctx.maint_state_path.read_text())["slots"]["GAMMA"]["killed"] is True
    # a pre-schema state file (today's real .maint_state.json shape: killed slots absent) upgrades silently —
    # the legacy killed slots (SR_BOUNCE, ETH_TSM_28, ...) must not all fire on the first run after the upgrade
    ctx.maint_state_path.write_text(json.dumps({"last_run": "x", "slots": {"ALPHA": {"crossed": False, "verdict_reached": False}}}))
    assert sd.run_maint(ctx) == []
    assert json.loads(ctx.maint_state_path.read_text())["schema"] == sd.MAINT_SCHEMA
    assert ctx.telegram.calls == []
    # …but crossed/verdict transitions still compare across the upgrade
    ctx.maint_state_path.write_text(json.dumps({"last_run": "x", "slots": {"ALPHA": {"crossed": False, "verdict_reached": False}}}))
    _write_state(ctx.bot_dir, "ALPHA", [0.5, -11.0], NOW_TS - 9 * DAY)
    alerts = sd.run_maint(ctx)
    assert len(alerts) == 1 and alerts[0].startswith("ALPHA crossed its registered kill line")


def test_survivors_rows_parses_the_real_file():
    rows = sd.survivors_rows((KB_REAL / "SURVIVORS.md").read_text())
    assert [r["id"] for r in rows] == ["informed_flow_btc_alt_cascade", V2]
    v2 = rows[1]
    assert v2["run"] == "2026-09-19-1451" and v2["train n"] == "246"
    assert v2["prereg doc"].endswith(f"specs/{V2}.frozen.json")
    assert "PAPER KILLED 2026-09-21" in v2["status"] and "DEAD_LIST row 112" in v2["status"]
    assert sd.survivors_rows("# nothing\n\nprose only\n") == []


def test_swarm_kill_appends_dead_row_and_marks_the_one_survivors_row(ctx):
    from research.swarm.lib import kb_check
    ctx.registered_ids = ["ALPHA"]
    _swarm_kb(ctx)
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    surv_before = (ctx.kb_dir / "SURVIVORS.md").read_text()
    _digest(ctx, {"ALPHA": "KILL — registered verdict: net $-11.50 <= $-10.00 dollar loss cap at n=3 — KILL; "
                           "touched .kill_ALPHA | 3 trades 1W $-11.50 | WR 33.3% | CI95 lo -9.100"})
    _killed(ctx, "ALPHA", [0.5, -6.0, -6.0], NOW_TS - 3600)
    ctx.git.calls.clear()
    alerts = sd.run_maint(ctx)
    # DEAD_LIST: one new row, n = max + 1, five cells, machine-checkable
    dl = ctx.kb_dir / "DEAD_LIST.md"
    rows = kb_check.dead_rows(dl)
    assert [r[0] for r in rows] == [1, 2, 3, 4]
    assert kb_check.malformed_dead_rows(dl) == []
    n, family, why, source, date = rows[-1]
    assert family == "ALPHA" and date == "2026-09-09"
    assert why.startswith("PAPER KILL 2026-09-09 ")
    assert ("PT on the registered line: n=3 1W net $-11.50 (KILL — registered verdict: net $-11.50 <= $-10.00 dollar "
            "loss cap at n=3 — KILL; touched .kill_ALPHA)") in why
    assert why.endswith("Paper only, $0 real. Do not re-propose without a new mechanism.")
    assert source == ("trading_state_ALPHA.json closed_trades; ~/Library/Logs/Phmex-S/lab_adjudicator.log; "
                      "docs/ALPHA-prereg.md")
    assert dl.read_text().count("| ALPHA |") == 1
    # SURVIVORS: only ALPHA's status cell changed, DELTA's row byte-identical, header/separator intact
    surv = (ctx.kb_dir / "SURVIVORS.md").read_text()
    b, a = surv_before.splitlines(), surv.splitlines()
    assert len(a) == len(b)
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    assert len(diff) == 1 and a[diff[0]].startswith("| 2026-09-19-1451 | ALPHA |")
    row = next(r for r in sd.survivors_rows(surv) if r["id"] == "ALPHA")
    assert row["status"] == ("committee pass — built + papered 2026-09-20 — PAPER KILLED 2026-09-09 "
                             "(n=3, net $-11.50) — DEAD_LIST row 4")
    assert row["prereg doc"] == "docs/ALPHA-prereg.md"
    assert alerts[0].startswith("ALPHA KILLED 2026-09-09") and "DEAD_LIST row 4" in alerts[0]
    # committed by pathspec with the kb files, still no push
    commit = next(c[0][0] for c in ctx.git.calls if c[0][0][0] == "commit")
    assert set(commit[commit.index("--") + 1:]) >= {"research/swarm/kb/LESSONS.md", "research/swarm/kb/DEAD_LIST.md",
                                                    "research/swarm/kb/SURVIVORS.md"}
    assert ["push"] not in [c[0][0] for c in ctx.git.calls]
    # kb_check ran on the temp kb (its dataset paths are absent here) and was logged, never raised
    assert "kb_check" in _log_text(ctx)
    # rerun: nothing duplicated
    dl_txt, surv_txt = dl.read_text(), surv
    sd.run_maint(ctx)
    assert dl.read_text() == dl_txt and (ctx.kb_dir / "SURVIVORS.md").read_text() == surv_txt


def test_pass_grade_marks_the_survivors_row_once_and_alerts(ctx):
    ctx.registered_ids = ["ALPHA"]
    _swarm_kb(ctx)
    _write_state(ctx.bot_dir, "ALPHA", [0.2] * 50, NOW_TS - 9 * DAY)
    _digest(ctx, {"ALPHA": "PASS — n=50 >= 50, net $+10.00, CI95 lower +0.1234 > 0 — PASS-ELIGIBLE: owner decision "
                           "required (never a promotion; no .promote_* written) | 50 trades 50W $+10.00 | WR 100.0% | CI95 lo +0.123"})
    before = ctx.lessons_path.read_text()
    alerts = sd.run_maint(ctx)                     # first run: verdict flags baseline, but the PASS mark is a kb fact
    row = next(r for r in sd.survivors_rows((ctx.kb_dir / "SURVIVORS.md").read_text()) if r["id"] == "ALPHA")
    assert row["status"].endswith("— PAPER PASS 2026-09-09 (n=50, net $+10.00, CI95 lo +0.1234) — awaiting owner "
                                  "decision (never auto-promoted)")
    assert row["status"].count("PAPER PASS") == 1
    assert len(alerts) == 1 and "ALPHA PAPER PASS" in alerts[0] and "never auto-promoted" in alerts[0]
    assert len(_new_lessons(ctx, before)) == 1 and len(ctx.telegram.calls) == 1
    assert not (ctx.kb_dir / "DEAD_LIST.md").read_text().count("| ALPHA |")
    surv = (ctx.kb_dir / "SURVIVORS.md").read_text()
    assert sd.run_maint(ctx) == []
    assert (ctx.kb_dir / "SURVIVORS.md").read_text() == surv and len(ctx.telegram.calls) == 1


def test_reconciliation_is_idempotent_against_the_real_hand_written_rows(ctx):
    """Copies of the real DEAD_LIST.md (row 112) and SURVIVORS.md (status already 'PAPER KILLED … DEAD_LIST row 112')
    go into the temp kb; the v2 slot is killed with the real 9/21 digest line; a schema-2 state says it was alive
    last run, so the KILLED event fires — and the two files must come back byte-identical."""
    import shutil
    from research.swarm.lib import kb_check
    for name in ("DEAD_LIST.md", "SURVIVORS.md"):
        shutil.copy(KB_REAL / name, ctx.kb_dir / name)
    dl_before = (ctx.kb_dir / "DEAD_LIST.md").read_text()
    surv_before = (ctx.kb_dir / "SURVIVORS.md").read_text()
    assert "| 112 | informed_flow_btc_alt_cascade_v2 | PAPER KILL 2026-09-21" in dl_before
    ctx.registered_ids = [V2]
    ctx.experiments = {V2: {"registered_ts": NOW_TS - 2 * DAY, "verdict_n": 50, "kill_net_usd": -10.0,
                            "inconclusive_hard_n": 100, "prereg": "docs/superpowers/specs/2026-09-20-informed_flow_btc_alt_cascade_v2-prereg.md"}}
    _killed(ctx, V2, [-3.24] * 5 + [4.76], NOW_TS - 3600, start=NOW_TS - DAY)
    _digest(ctx, {V2: V2_KILL_GRADE})
    ctx.maint_state_path.write_text(json.dumps({"schema": sd.MAINT_SCHEMA, "last_run": "x",
                                                "slots": {V2: {"crossed": False, "verdict_reached": False, "killed": False}}}))
    before = ctx.lessons_path.read_text()
    alerts = sd.run_maint(ctx)
    assert len(alerts) == 1 and alerts[0].startswith(f"{V2} KILLED 2026-09-09 (KILL — registered verdict: net $-16.20")
    assert "DEAD_LIST row 112" in alerts[0]
    assert (ctx.kb_dir / "DEAD_LIST.md").read_text() == dl_before
    assert (ctx.kb_dir / "SURVIVORS.md").read_text() == surv_before
    assert len(_new_lessons(ctx, before)) == 1 and len(ctx.telegram.calls) == 1
    assert kb_check.malformed_dead_rows(ctx.kb_dir / "DEAD_LIST.md") == []
    commit = next(c[0][0] for c in ctx.git.calls if c[0][0][0] == "commit")
    paths = commit[commit.index("--") + 1:]
    assert "research/swarm/kb/LESSONS.md" in paths
    assert "research/swarm/kb/DEAD_LIST.md" not in paths and "research/swarm/kb/SURVIVORS.md" not in paths


def test_non_swarm_slot_kill_writes_no_kb_rows(ctx):
    ctx.registered_ids = ["ALPHA"]
    _swarm_kb(ctx, ids=("DELTA",))                                 # ALPHA has no SURVIVORS row → legacy slot
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    dl, surv = (ctx.kb_dir / "DEAD_LIST.md").read_text(), (ctx.kb_dir / "SURVIVORS.md").read_text()
    before = ctx.lessons_path.read_text()
    _killed(ctx, "ALPHA", [0.5, -11.0], NOW_TS - 60)
    ctx.git.calls.clear()
    alerts = sd.run_maint(ctx)
    assert len(alerts) == 1 and alerts[0].startswith("ALPHA KILLED") and "DEAD_LIST" not in alerts[0]
    assert (ctx.kb_dir / "DEAD_LIST.md").read_text() == dl and (ctx.kb_dir / "SURVIVORS.md").read_text() == surv
    assert len(_new_lessons(ctx, before)) == 1 and len(ctx.telegram.calls) == 1
    commit = next(c[0][0] for c in ctx.git.calls if c[0][0][0] == "commit")
    assert commit[commit.index("--") + 1:] == ["research/swarm/kb/PAPER_STATUS.md", "research/swarm/kb/LESSONS.md"]
    # no SURVIVORS.md at all → same outcome, no crash
    (ctx.kb_dir / "SURVIVORS.md").unlink()
    ctx.maint_state_path.write_text(json.dumps({"schema": sd.MAINT_SCHEMA, "last_run": "x",
                                                "slots": {"ALPHA": {"crossed": False, "verdict_reached": False, "killed": False}}}))
    assert len(sd.run_maint(ctx)) == 1


def test_dead_row_cells_are_pipe_sanitised(ctx):
    from research.swarm.lib import kb_check
    ctx.registered_ids = ["ALPHA"]
    _swarm_kb(ctx)
    _write_state(ctx.bot_dir, "ALPHA", [0.5], NOW_TS - 9 * DAY)
    sd.main(["--mode", "maint"], ctx=ctx)
    _digest(ctx, {"ALPHA": "KILL — net<=cap|hard stop | 3 trades 1W $-11.50"})     # a pipe INSIDE the note
    _killed(ctx, "ALPHA", [0.5, -6.0, -6.0], NOW_TS - 3600)
    sd.run_maint(ctx)
    dl = ctx.kb_dir / "DEAD_LIST.md"
    assert kb_check.malformed_dead_rows(dl) == []
    n, family, why, source, date = kb_check.dead_rows(dl)[-1]
    assert n == 4 and "|" not in why and "|" not in source
    assert "(KILL — net<=cap/hard stop)" in why
    # the row writer itself scrubs pipes and newlines in every cell it is handed
    n2, appended = sd.append_dead_row(dl, "ZETA|x", "why|with\npipes", "src|a\nb", "2026-09-09")
    assert (n2, appended) == (5, True)
    assert kb_check.malformed_dead_rows(dl) == []
    assert kb_check.dead_rows(dl)[-1] == (5, "ZETA/x", "why/with pipes", "src/a b", "2026-09-09")
    assert sd._cell("a|b\nc") == "a/b c"
    lessons = ctx.lessons_path.read_text().splitlines()[-1]
    assert lessons.startswith("- 2026-09-09 — maint: ALPHA KILLED") and "net<=cap/hard stop" in lessons
