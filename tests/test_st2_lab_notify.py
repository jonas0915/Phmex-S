"""TDD for scripts/st2_lab/notify.py — best-effort Telegram alerts for the lab.

Pure stdlib (urllib). Creds read from .env directly (the lab launchd job sets no env
vars) with os.environ taking precedence. Sending must NEVER raise — confirm.tick relies
on that to never break the search loop.
"""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import notify as N  # noqa: E402


def _write_env(tmp_path, token="", chat=""):
    p = tmp_path / ".env"
    lines = ["# comment line", "EXCHANGE=phemex"]
    if token:
        lines.append(f"TELEGRAM_TOKEN={token}")
    if chat:
        lines.append(f"TELEGRAM_CHAT_ID={chat}")
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_read_env_parses_keyvalue(tmp_path):
    p = _write_env(tmp_path, token="abc123", chat="999")
    env = N._read_env(p)
    assert env["TELEGRAM_TOKEN"] == "abc123"
    assert env["TELEGRAM_CHAT_ID"] == "999"
    assert env["EXCHANGE"] == "phemex"


def test_creds_prefers_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "envtok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "envchat")
    p = _write_env(tmp_path, token="filetok", chat="filechat")
    assert N._creds(p) == ("envtok", "envchat")


def test_creds_falls_back_to_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path, token="filetok", chat="filechat")
    assert N._creds(p) == ("filetok", "filechat")


def test_alert_no_creds_returns_false_without_posting(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path)  # no creds
    called = []
    assert N.telegram_alert("hi", env_path=p, poster=lambda u, pl: called.append(1) or 200) is False
    assert called == []  # never attempted a network call


def test_alert_success_builds_correct_request(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path, token="T0K", chat="C1D")
    seen = {}

    def fake_post(url, payload):
        seen["url"] = url
        seen["payload"] = payload
        return 200

    assert N.telegram_alert("danger", env_path=p, poster=fake_post) is True
    assert "/botT0K/sendMessage" in seen["url"]
    assert seen["payload"]["chat_id"] == "C1D"
    assert seen["payload"]["text"] == "danger"
    assert seen["payload"]["parse_mode"] == "HTML"


def test_alert_non_200_returns_false(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path, token="T", chat="C")
    assert N.telegram_alert("x", env_path=p, poster=lambda u, pl: 500) is False


def test_alert_swallows_errors_never_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path, token="T", chat="C")

    def boom(u, pl):
        raise RuntimeError("network down")

    assert N.telegram_alert("x", env_path=p, poster=boom) is False  # no exception propagates

# ── Retry support (2026-07-07) ────────────────────────────────────────────
# Root cause: the 6 AM adjudicator digest fired during a battery dark-wake
# with DNS down — both sends failed instantly and Jonas never got the digest.
# telegram_alert grows attempts/retry_waits (default attempts=1 = exact old
# behavior for the lab loop callers); adjudicate.py + drift_watchdog.py opt in.

def test_alert_retries_after_exception_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path, token="T", chat="C")
    calls, naps = [], []

    def flaky(u, pl):
        calls.append(1)
        if len(calls) < 3:
            raise OSError("DNS down")
        return 200

    ok = N.telegram_alert("x", env_path=p, poster=flaky,
                          attempts=4, sleeper=naps.append)
    assert ok is True
    assert len(calls) == 3          # failed, failed, succeeded
    assert len(naps) == 2           # slept between attempts only
    assert naps == sorted(naps)     # backoff never shrinks


def test_alert_retries_after_non_200_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path, token="T", chat="C")
    codes = iter([502, 200])
    naps = []
    ok = N.telegram_alert("x", env_path=p, poster=lambda u, pl: next(codes),
                          attempts=3, sleeper=naps.append)
    assert ok is True
    assert len(naps) == 1


def test_alert_default_is_single_attempt(tmp_path, monkeypatch):
    # confirm.tick / nightly_research callers keep exact old behavior
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path, token="T", chat="C")
    calls = []

    def boom(u, pl):
        calls.append(1)
        raise OSError("down")

    assert N.telegram_alert("x", env_path=p, poster=boom) is False
    assert len(calls) == 1          # no retry unless asked


def test_alert_no_creds_never_retries(tmp_path, monkeypatch):
    # missing creds is a config problem, not transient — fail fast
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path)
    naps = []
    assert N.telegram_alert("x", env_path=p, poster=lambda u, pl: 200,
                            attempts=4, sleeper=naps.append) is False
    assert naps == []


def test_alert_exhausted_retries_returns_false_never_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    p = _write_env(tmp_path, token="T", chat="C")
    calls, naps = [], []

    def boom(u, pl):
        calls.append(1)
        raise OSError("still down")

    assert N.telegram_alert("x", env_path=p, poster=boom,
                            attempts=3, sleeper=naps.append) is False
    assert len(calls) == 3
    assert len(naps) == 2
