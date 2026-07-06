#!/usr/bin/env python3
"""Nightly launchd entry point: run adjudicate + drift_watchdog sequentially.

One process for launchd so a single plist covers both; each half is isolated so
a crash in one still lets the other run and report. Exit code is the max of the
two (0 = both clean) so `launchctl print` surfaces partial failures.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 3)[0])           # repo root
sys.path.insert(0, __file__.rsplit("/", 2)[0])           # scripts/

from lab_adjudicator import adjudicate, drift_watchdog   # noqa: E402


def run() -> int:
    codes = []
    for name, mod in (("adjudicate", adjudicate), ("drift_watchdog", drift_watchdog)):
        try:
            codes.append(mod.main(["--telegram"]))
        except Exception as exc:  # one half failing must not silence the other
            print(f"[NIGHTLY] {name} crashed: {exc}", file=sys.stderr)
            codes.append(1)
    return max(codes)


if __name__ == "__main__":
    sys.exit(run())
