"""Knowledge-base integrity: files present, DEAD_LIST rows well-formed and unique,
DATA.md names every dataset path and each path exists. Run before every desk run."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from . import load_data as ld

REQUIRED = ("CONSTRAINTS.md", "STANDARDS.md", "DATA.md", "DEAD_LIST.md", "LESSONS.md", "SURVIVORS.md")
_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*$")


def dead_rows(path: Path) -> list[tuple[int, str, str, str, str]]:
    rows = []
    for line in path.read_text().splitlines():
        m = _ROW.match(line)
        if m:
            rows.append((int(m.group(1)), m.group(2), m.group(3), m.group(4), m.group(5)))
    return rows


def check(kb_dir: Path, root: Path) -> list[str]:
    problems = [f"missing {f}" for f in REQUIRED if not (kb_dir / f).exists()]
    if problems:
        return problems
    rows = dead_rows(kb_dir / "DEAD_LIST.md")
    nums = [r[0] for r in rows]
    if len(set(nums)) != len(nums):
        problems.append("DEAD_LIST.md has duplicate row numbers")
    if nums != sorted(nums):
        problems.append("DEAD_LIST.md rows not ascending")
    data_txt = (kb_dir / "DATA.md").read_text()
    for name, spec in ld.DATASETS.items():
        if spec["dir"] not in data_txt:
            problems.append(f"DATA.md does not mention {spec['dir']} ({name})")
        if not (root / spec["dir"]).exists():
            problems.append(f"dataset path missing on disk: {spec['dir']}")
    return problems


if __name__ == "__main__":
    kb = ld.REPO_ROOT / "research" / "swarm" / "kb"
    probs = check(kb, ld.REPO_ROOT)
    print("\n".join(probs) if probs else "KB OK")
    sys.exit(1 if probs else 0)
