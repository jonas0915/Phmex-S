"""Knowledge-base integrity: files present, DEAD_LIST rows well-formed and unique,
DATA.md names every dataset path and each path exists. Run before every desk run."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from . import load_data as ld

REQUIRED = ("CONSTRAINTS.md", "STANDARDS.md", "DATA.md", "DEAD_LIST.md", "LESSONS.md", "SURVIVORS.md")
_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*$")
_SEP_CELL = re.compile(r"^:?-+:?$")


def dead_rows(path: Path) -> list[tuple[int, str, str, str, str]]:
    rows = []
    for line in path.read_text().splitlines():
        m = _ROW.match(line)
        if m:
            rows.append((int(m.group(1)), m.group(2), m.group(3), m.group(4), m.group(5)))
    return rows


def _table_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_header_or_separator(line: str) -> bool:
    cells = _table_cells(line)
    if not cells:
        return False
    if cells[0].lower() == "n":                       # our header: "| n | family | ... |"
        return True
    return all(_SEP_CELL.match(c) for c in cells)      # markdown separator: "|---|---|...|"


def malformed_dead_rows(path: Path) -> list[tuple[int, str]]:
    """Lines in the DEAD_LIST table region that look like a row (start with '|') but
    don't parse as a valid 5-column row, header, or markdown separator — e.g. wrong
    column count, missing/malformed date, or a stray pipe inside a cell."""
    bad = []
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        if _ROW.match(line) or _is_header_or_separator(line):
            continue
        bad.append((i, line.strip()))
    return bad


def check(kb_dir: Path, root: Path) -> list[str]:
    problems = [f"missing {f}" for f in REQUIRED if not (kb_dir / f).exists()]
    if problems:
        return problems
    dead_list_path = kb_dir / "DEAD_LIST.md"
    rows = dead_rows(dead_list_path)
    nums = [r[0] for r in rows]
    if len(set(nums)) != len(nums):
        problems.append("DEAD_LIST.md has duplicate row numbers")
    if nums != sorted(nums):
        problems.append("DEAD_LIST.md rows not ascending")
    for lineno, line in malformed_dead_rows(dead_list_path):
        problems.append(f"DEAD_LIST.md: malformed row at line {lineno}: {line[:60]}")
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
