#!/usr/bin/env python3
"""
Phmex-S MCP Server — exposes the live trading bot's state and safe controls
to any MCP-compatible client (Claude Code, claude.ai web/mobile via HTTP).

READ-ONLY by default. Control actions require explicit `confirm=True` and are
audited to logs/mcp_audit.log. Rate-limited to 1 destructive action / 10 sec.

Transports
----------
- stdio (default)        : python3 mcp_server.py
- HTTP (streamable-http) : python3 mcp_server.py --http [--host 127.0.0.1] [--port 7878]
                           Requires MCP_API_KEY env var. Binds 127.0.0.1 by default.
"""

import argparse
import glob
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

# -- Path setup --------------------------------------------------------------
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BOT_DIR)
LOG_DIR = os.path.join(BOT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

AUDIT_LOG = os.path.join(LOG_DIR, "mcp_audit.log")
BOT_LOG = os.path.join(LOG_DIR, "bot.log")
STATE_FILE = os.path.join(BOT_DIR, "trading_state.json")
ENV_FILE = os.path.join(BOT_DIR, ".env")
PID_FILE = os.path.join(BOT_DIR, ".bot.pid")
PAUSE_SENTINEL = os.path.join(BOT_DIR, ".pause_trading")
LESSONS_FILE = os.path.join(BOT_DIR, "memory", "lessons.md")
MEMORY_DIR = os.path.join(BOT_DIR, "memory")

REDACT_KEYS = {"API_KEY", "API_SECRET", "TELEGRAM_TOKEN", "ANTHROPIC_API_KEY"}

# -- Audit logger ------------------------------------------------------------
audit_logger = logging.getLogger("mcp_audit")
audit_logger.setLevel(logging.INFO)
_h = logging.FileHandler(AUDIT_LOG)
_h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
audit_logger.addHandler(_h)


def _audit(action: str, args: dict, result: str) -> None:
    audit_logger.info(json.dumps({"action": action, "args": args, "result": result}))


# -- Rate limit (in-process, per-action category) ----------------------------
_LAST_DESTRUCTIVE = {"t": 0.0}
RATE_LIMIT_SEC = 10


def _rate_limit_destructive() -> Optional[str]:
    elapsed = time.time() - _LAST_DESTRUCTIVE["t"]
    if elapsed < RATE_LIMIT_SEC:
        return f"rate-limited: wait {RATE_LIMIT_SEC - elapsed:.0f}s"
    _LAST_DESTRUCTIVE["t"] = time.time()
    return None


# -- Helpers -----------------------------------------------------------------
def _read_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e)}


def _read_env() -> dict:
    out = {}
    if not os.path.exists(ENV_FILE):
        return out
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in REDACT_KEYS:
                    v = f"<redacted:{len(v)}chars>" if v else "<unset>"
                out[k] = v
    except Exception as e:
        out["_error"] = str(e)
    return out


def _bot_pid() -> Optional[int]:
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _last_log_time() -> Optional[str]:
    if not os.path.exists(BOT_LOG):
        return None
    try:
        # Read last ~8 KB and find last timestamp
        with open(BOT_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 8192))
            tail = f.read().decode(errors="ignore")
        ts_re = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", re.M)
        matches = ts_re.findall(tail)
        return matches[-1] if matches else None
    except Exception:
        return None


def _today_utc_start() -> float:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _period_start(period: str) -> float:
    now = datetime.now(timezone.utc)
    if period == "today":
        return _today_utc_start()
    if period == "week":
        return (now - timedelta(days=7)).timestamp()
    if period == "month":
        return (now - timedelta(days=30)).timestamp()
    if period == "all":
        return 0.0
    raise ValueError(f"period must be today|week|month|all (got {period!r})")


# -- MCP server --------------------------------------------------------------
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "ERROR: 'mcp' package not installed. Install with:\n"
        "  pip install 'mcp[cli]'\n",
        file=sys.stderr,
    )
    sys.exit(1)

mcp = FastMCP("Phmex-S")


# -- READ tools --------------------------------------------------------------

@mcp.tool()
def phmex_status() -> dict:
    """Bot health + summary. Returns running status, PID, last cycle timestamp,
    open position count, today's PnL, current balance."""
    state = _read_state()
    pid = _bot_pid()
    running = bool(pid and _pid_alive(pid))
    positions = state.get("positions", {}) or {}
    closed = state.get("closed_trades", []) or []
    today_start = _today_utc_start()
    today = [t for t in closed if (t.get("closed_at") or t.get("exit_time", 0)) >= today_start]
    pnl_today = sum((t.get("pnl_usdt") or 0) for t in today)
    return {
        "running": running,
        "pid": pid,
        "last_log_ts": _last_log_time(),
        "open_positions": len(positions),
        "trades_today": len(today),
        "pnl_today_usdt": round(pnl_today, 2),
        "peak_balance": state.get("peak_balance"),
        "paused": os.path.exists(PAUSE_SENTINEL),
    }


@mcp.tool()
def phmex_open_positions() -> list:
    """List all currently open positions with side, entry, SL, TP, age."""
    state = _read_state()
    positions = state.get("positions", {}) or {}
    out = []
    now = time.time()
    for sym, p in positions.items():
        opened = p.get("opened_at") or p.get("entry_time") or 0
        out.append({
            "symbol": sym,
            "side": p.get("side"),
            "entry_price": p.get("entry_price"),
            "amount": p.get("amount"),
            "margin": p.get("margin"),
            "stop_loss": p.get("stop_loss"),
            "take_profit": p.get("take_profit"),
            "age_minutes": round((now - opened) / 60, 1) if opened else None,
            "strategy": p.get("strategy"),
        })
    return out


@mcp.tool()
def phmex_recent_trades(limit: int = 20) -> list:
    """Last N closed trades with PnL, exit reason, duration. Newest first."""
    state = _read_state()
    closed = state.get("closed_trades", []) or []
    closed = list(reversed(closed))[: max(1, min(limit, 200))]
    out = []
    for t in closed:
        out.append({
            "symbol": t.get("symbol"),
            "side": t.get("side"),
            "entry": t.get("entry"),
            "exit": t.get("exit"),
            "pnl_usdt": round(t.get("pnl_usdt") or 0, 4),
            "pnl_pct": round(t.get("pnl_pct") or 0, 2),
            "reason": t.get("reason") or t.get("exit_reason"),
            "strategy": t.get("strategy"),
            "closed_at": t.get("closed_at"),
        })
    return out


@mcp.tool()
def phmex_pnl(period: str = "today") -> dict:
    """Aggregated PnL for period: today | week | month | all.
    Returns net PnL, win rate, trade count, avg win/loss."""
    try:
        cutoff = _period_start(period)
    except ValueError as e:
        return {"error": str(e)}
    state = _read_state()
    closed = state.get("closed_trades", []) or []
    trades = [t for t in closed if (t.get("closed_at") or t.get("exit_time", 0)) >= cutoff]
    if not trades:
        return {"period": period, "trades": 0, "pnl_usdt": 0, "win_rate": None}
    pnls = [(t.get("pnl_usdt") or 0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    return {
        "period": period,
        "trades": len(trades),
        "pnl_usdt": round(sum(pnls), 4),
        "win_rate": round(len(wins) / len(trades), 3),
        "avg_win": round(sum(wins) / len(wins), 4) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else 0,
        "best": round(max(pnls), 4),
        "worst": round(min(pnls), 4),
    }


@mcp.tool()
def phmex_lessons_search(query: str, max_results: int = 10) -> list:
    """Full-text search across memory/lessons.md. Returns matching lines with line numbers."""
    if not os.path.exists(LESSONS_FILE):
        return [{"error": f"missing {LESSONS_FILE}"}]
    q = query.lower().strip()
    if not q:
        return [{"error": "empty query"}]
    out = []
    try:
        with open(LESSONS_FILE) as f:
            for i, line in enumerate(f, 1):
                if q in line.lower():
                    out.append({"line": i, "text": line.rstrip()[:400]})
                    if len(out) >= max_results:
                        break
    except Exception as e:
        return [{"error": str(e)}]
    return out


@mcp.tool()
def phmex_memory_search(query: str, max_results: int = 15) -> list:
    """Search across all memory/*.md files. Returns file:line:text matches."""
    q = query.lower().strip()
    if not q:
        return [{"error": "empty query"}]
    out = []
    for path in sorted(glob.glob(os.path.join(MEMORY_DIR, "*.md"))):
        try:
            with open(path) as f:
                for i, line in enumerate(f, 1):
                    if q in line.lower():
                        out.append({
                            "file": os.path.basename(path),
                            "line": i,
                            "text": line.rstrip()[:300],
                        })
                        if len(out) >= max_results:
                            return out
        except Exception:
            continue
    return out


@mcp.tool()
def phmex_recent_log(lines: int = 50, level: Optional[str] = None) -> list:
    """Tail bot.log. `level` filters by INFO/WARN/ERROR (case-insensitive)."""
    lines = max(1, min(lines, 500))
    if not os.path.exists(BOT_LOG):
        return [{"error": "bot.log not found"}]
    try:
        with open(BOT_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            chunk = min(size, lines * 400)
            f.seek(max(0, size - chunk))
            tail = f.read().decode(errors="ignore").splitlines()
    except Exception as e:
        return [{"error": str(e)}]
    if level:
        lvl = level.upper()
        tail = [l for l in tail if lvl in l.upper()]
    return tail[-lines:]


@mcp.tool()
def phmex_params() -> dict:
    """Current .env config (sensitive keys redacted)."""
    return _read_env()


@mcp.tool()
def phmex_memory_list() -> list:
    """List all memory/*.md files with size + modified time."""
    out = []
    for path in sorted(glob.glob(os.path.join(MEMORY_DIR, "*.md"))):
        try:
            st = os.stat(path)
            out.append({
                "file": os.path.basename(path),
                "bytes": st.st_size,
                "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
        except OSError:
            continue
    return out


# -- CONTROL tools (require confirm=True) ------------------------------------

@mcp.tool()
def phmex_pause_bot(reason: str, confirm: bool = False) -> dict:
    """Pause the bot — stops new entries. Existing positions managed normally.
    Writes .pause_trading sentinel (same mechanism as Telegram /pause).
    REQUIRES confirm=True."""
    if not confirm:
        return {"ok": False, "error": "confirm=True required"}
    rl = _rate_limit_destructive()
    if rl:
        _audit("pause_bot", {"reason": reason}, rl)
        return {"ok": False, "error": rl}
    try:
        with open(PAUSE_SENTINEL, "w") as f:
            f.write(f"reason: {reason}\nset_by: mcp_server\nat: {datetime.now(timezone.utc).isoformat()}\n")
        _audit("pause_bot", {"reason": reason}, "ok")
        return {"ok": True, "sentinel": PAUSE_SENTINEL, "message": "Bot will stop new entries within 60s."}
    except Exception as e:
        _audit("pause_bot", {"reason": reason}, f"error:{e}")
        return {"ok": False, "error": str(e)}


@mcp.tool()
def phmex_resume_bot(confirm: bool = False) -> dict:
    """Resume the bot — clears .pause_trading sentinel.
    REQUIRES confirm=True."""
    if not confirm:
        return {"ok": False, "error": "confirm=True required"}
    rl = _rate_limit_destructive()
    if rl:
        _audit("resume_bot", {}, rl)
        return {"ok": False, "error": rl}
    if not os.path.exists(PAUSE_SENTINEL):
        _audit("resume_bot", {}, "noop:not_paused")
        return {"ok": True, "message": "Bot was not paused (no sentinel)."}
    try:
        os.remove(PAUSE_SENTINEL)
        _audit("resume_bot", {}, "ok")
        return {"ok": True, "message": "Pause sentinel removed. Bot will resume within 60s."}
    except Exception as e:
        _audit("resume_bot", {}, f"error:{e}")
        return {"ok": False, "error": str(e)}


@mcp.tool()
def phmex_kill_slot(slot_id: str, confirm: bool = False) -> dict:
    """Kill a specific paper slot — writes .kill_<slot_id> sentinel
    (same mechanism as Telegram /kill). Does NOT close live positions on exchange.
    REQUIRES confirm=True."""
    if not confirm:
        return {"ok": False, "error": "confirm=True required"}
    if not re.match(r"^[A-Za-z0-9_-]{1,40}$", slot_id):
        return {"ok": False, "error": "invalid slot_id"}
    rl = _rate_limit_destructive()
    if rl:
        _audit("kill_slot", {"slot_id": slot_id}, rl)
        return {"ok": False, "error": rl}
    sentinel = os.path.join(BOT_DIR, f".kill_{slot_id}")
    try:
        with open(sentinel, "w") as f:
            f.write(f"set_by: mcp_server\nat: {datetime.now(timezone.utc).isoformat()}\n")
        _audit("kill_slot", {"slot_id": slot_id}, "ok")
        return {"ok": True, "sentinel": sentinel, "message": f"Kill sentinel written for {slot_id}."}
    except Exception as e:
        _audit("kill_slot", {"slot_id": slot_id}, f"error:{e}")
        return {"ok": False, "error": str(e)}


@mcp.tool()
def phmex_run_backtest(strategy: str, days: int = 30, confirm: bool = False) -> dict:
    """Kick off a backtest as a detached subprocess. Returns the PID + log path.
    Backtest result lands in logs/backtest_<ts>.log.
    REQUIRES confirm=True. Compute-heavy."""
    if not confirm:
        return {"ok": False, "error": "confirm=True required"}
    if not re.match(r"^[a-z_]{1,40}$", strategy):
        return {"ok": False, "error": "invalid strategy name"}
    days = max(1, min(int(days), 365))
    backtest_script = os.path.join(BOT_DIR, "backtest.py")
    if not os.path.exists(backtest_script):
        return {"ok": False, "error": f"backtest.py not found at {backtest_script}"}
    rl = _rate_limit_destructive()
    if rl:
        _audit("run_backtest", {"strategy": strategy, "days": days}, rl)
        return {"ok": False, "error": rl}
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = os.path.join(LOG_DIR, f"backtest_{ts}.log")
    try:
        with open(log_path, "wb") as logf:
            proc = subprocess.Popen(
                [sys.executable, backtest_script, "--strategy", strategy, "--days", str(days)],
                cwd=BOT_DIR,
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        _audit("run_backtest", {"strategy": strategy, "days": days, "pid": proc.pid, "log": log_path}, "ok")
        return {"ok": True, "pid": proc.pid, "log": log_path, "message": "Backtest started. Tail log for progress."}
    except Exception as e:
        _audit("run_backtest", {"strategy": strategy, "days": days}, f"error:{e}")
        return {"ok": False, "error": str(e)}


# -- Entry point -------------------------------------------------------------

def _check_http_auth() -> None:
    """If running HTTP transport, require MCP_API_KEY env var."""
    key = os.environ.get("MCP_API_KEY", "").strip()
    if not key or len(key) < 16:
        print(
            "ERROR: HTTP transport requires MCP_API_KEY (>=16 chars) env var.\n"
            "  Generate one: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'\n"
            "  Then: export MCP_API_KEY=<value>\n",
            file=sys.stderr,
        )
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Phmex-S MCP Server")
    parser.add_argument("--http", action="store_true", help="HTTP (streamable-http) transport")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7878, help="HTTP port (default 7878)")
    args = parser.parse_args()

    _audit("server_start", {"http": args.http, "host": args.host, "port": args.port}, "ok")

    if args.http:
        _check_http_auth()
        if args.host not in ("127.0.0.1", "localhost", "::1"):
            print(
                f"WARNING: binding to {args.host} exposes the server beyond localhost.\n"
                "Make sure you understand the implications. Use bearer token + HTTPS.\n",
                file=sys.stderr,
            )
        # FastMCP streamable-http transport
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
