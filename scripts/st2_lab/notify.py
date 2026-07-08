"""Best-effort Telegram alerts for the lab — pure stdlib (urllib), no bot.py import.

The `com.phmex.st2-lab` launchd job sets no environment variables, so credentials are
read from the project `.env` directly (a tiny stdlib KEY=VALUE parse — the lab does not
depend on python-dotenv), with `os.environ` taking precedence for interactive runs.

Sending is BEST-EFFORT: missing creds, a non-200 response, or any network error returns
False and NEVER raises. `confirm.tick`'s loop wiring depends on that — an alert failure
must not break the offline search loop.
"""
from __future__ import annotations

import json
import os
import time as _time
import urllib.request

_BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENV = os.path.join(_BOT_DIR, ".env")


def _read_env(path: str) -> dict:
    """Parse KEY=VALUE lines from a .env file (stdlib; ignores blanks/comments)."""
    out: dict = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def _creds(env_path: str = None) -> tuple[str, str]:
    """(token, chat_id) — os.environ first, then .env. Empty strings if absent."""
    env = _read_env(env_path or _ENV)
    token = os.environ.get("TELEGRAM_TOKEN") or env.get("TELEGRAM_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or env.get("TELEGRAM_CHAT_ID", "")
    return token, chat


def _post(url: str, payload: dict, timeout: int = 10) -> int:
    """POST JSON via stdlib urllib; return the HTTP status code. Isolated for testing."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def telegram_alert(message: str, env_path: str = None, poster=None,
                   attempts: int = 1, retry_waits: tuple = (15, 60, 240),
                   sleeper=None) -> bool:
    """Send `message` to the lab's Telegram chat. Returns True on HTTP 200, False if
    creds are missing or every attempt fails. NEVER raises. `poster(url, payload) -> int`
    is injectable for tests (defaults to the real urllib POST).

    Retries (2026-07-07): `attempts` > 1 re-sends on exception or non-200, sleeping
    retry_waits[i] between tries (last wait reused if attempts exceed the tuple).
    Default attempts=1 keeps the exact old single-shot behavior — confirm.tick and
    nightly_research must not stall on a dead network. The daily adjudicator digest
    and drift watchdog opt in with attempts=4: a 6 AM battery dark-wake DNS blip
    (2026-07-07) killed both sends instantly and the digest was silently lost.
    Missing creds never retry — that's a config problem, not a transient one.
    `sleeper(seconds)` is injectable for tests (defaults to time.sleep)."""
    token, chat = _creds(env_path)
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat, "text": message, "parse_mode": "HTML"}
    _sleep = sleeper or _time.sleep
    for i in range(max(1, attempts)):
        try:
            if (poster or _post)(url, payload) == 200:
                return True
        except Exception:
            pass
        if i < max(1, attempts) - 1:
            _sleep(retry_waits[min(i, len(retry_waits) - 1)])
    return False
