#!/usr/bin/env python3
"""Durable archive of 5m_mean_revert OB/TAPE gate blocks (H0 data sink, 2026-09-03).

Why: the OB-imbalance gate counterfactual registered 7/14 needs n>=10 imbalance
episodes, but bot.log rotates at 10 MB (~10 days) and the episodes vanish with
it. This script scans bot.log + its rotations for
    [OB GATE] 5m_mean_revert <sym> <SIDE> blocked — <reason>
    [TAPE GATE] 5m_mean_revert <sym> <SIDE> blocked — <reason>
and appends NEW ones (dedupe key ts+symbol+gate+reason) to
logs/mr_gate_blocks.jsonl. Read-only vs the bot; no bot imports; idempotent.

Run from repo root (launchd com.phmex.mr-gate-archiver every 6 h):
    python3 scripts/slot_lab/mr_gate_block_archiver.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

_RX = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) .*?\[(?P<gate>OB|TAPE) GATE\] "
    r"5m_mean_revert (?P<symbol>[A-Z0-9]+/USDT:USDT) (?P<side>LONG|SHORT) blocked — (?P<reason>.+?)\s*$"
)


def parse_line(line: str) -> dict | None:
    m = _RX.match(line)
    if not m:
        return None
    d = m.groupdict()
    return {"ts": d["ts"], "gate": d["gate"], "symbol": d["symbol"],
            "side": d["side"], "reason": d["reason"]}


def _key(r: dict) -> str:
    return f'{r["ts"]}|{r["symbol"]}|{r["gate"]}|{r["reason"]}'


def archive(log_paths: list[str], out_path: str) -> int:
    seen = set()
    if os.path.exists(out_path):
        with open(out_path) as fh:
            for line in fh:
                try:
                    seen.add(_key(json.loads(line)))
                except Exception:
                    continue
    new = []
    for p in log_paths:
        if not os.path.exists(p):
            continue
        with open(p, errors="replace") as fh:
            for line in fh:
                r = parse_line(line.rstrip("\n"))
                if r is None:
                    continue
                k = _key(r)
                if k in seen:
                    continue
                seen.add(k)
                new.append(r)
    if new:
        new.sort(key=lambda r: r["ts"])
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "a") as fh:
            for r in new:
                fh.write(json.dumps(r) + "\n")
    return len(new)


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    logs = sorted(glob.glob(os.path.join(root, "logs", "bot.log*")))
    out = os.path.join(root, "logs", "mr_gate_blocks.jsonl")
    n = archive(logs, out)
    total = sum(1 for _ in open(out)) if os.path.exists(out) else 0
    print(f"mr_gate_block_archiver: +{n} new, {total} total in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
