"""WATCHER badge must survive log rotation (2026-08-09 truth-audit).

Bug: _watcher_enabled grepped only the current bot.log for the boot markers;
after logrotate the markers live in bot.log.1 and the badge showed a false
red OFF on a running watcher (it enforced 3 real stops that same day).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import web_dashboard as wd


def _setup(tmp_path, monkeypatch, current: str, rotated: str = None):
    log = tmp_path / "bot.log"
    log.write_text(current)
    if rotated is not None:
        (tmp_path / "bot.log.1").write_text(rotated)
    monkeypatch.setattr(wd, "LOG_FILE", str(log))
    wd._watcher_cache.update({"ts": 0, "v": None})  # bust the 30s cache


def test_watcher_on_when_markers_rotated_away(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch,
           current="2026-08-09 [INFO] [LIVE EXIT] TAO stop_loss @ 206.19\n",
           rotated=("2026-08-05 [INFO] Volume scanner ON\n"
                    "2026-08-05 [INFO] [LIVE EXIT] watcher enabled\n"))
    assert wd._watcher_enabled() is True


def test_watcher_off_when_rotated_shows_no_enable_after_boot(tmp_path, monkeypatch):
    # Last boot (scanner ON) came AFTER the last watcher-enabled line.
    _setup(tmp_path, monkeypatch,
           current="2026-08-09 [INFO] Cycle #5000 | Positions: 0\n",
           rotated=("2026-08-05 [INFO] [LIVE EXIT] watcher enabled\n"
                    "2026-08-06 [INFO] Volume scanner ON\n"))
    assert wd._watcher_enabled() is False


def test_watcher_off_when_no_markers_anywhere(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, current="2026-08-09 [INFO] Cycle #1\n")
    assert wd._watcher_enabled() is False
