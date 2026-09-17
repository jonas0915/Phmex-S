import shutil
from pathlib import Path

from research.swarm.lib import kb_check, load_data as ld

KB = ld.REPO_ROOT / "research" / "swarm" / "kb"


def test_kb_files_exist_and_pass_integrity():
    problems = kb_check.check(KB, ld.REPO_ROOT)
    assert problems == [], "\n".join(problems)


def test_dead_list_has_at_least_the_v1_rows_and_memory_kills():
    rows = kb_check.dead_rows(KB / "DEAD_LIST.md")
    assert len(rows) >= 90                      # 76 v1 rows + ≥14 memory-reference kills
    assert len({r[0] for r in rows}) == len(rows)


def test_constraints_carry_the_p_star_table_and_capital():
    txt = (KB / "CONSTRAINTS.md").read_text()
    for needle in ("$200", "11.5", "73.0%", "61.5%", "55.8%", "51.9%", "50.6%", "77.74", "5-min"):
        assert needle in txt, needle


def test_kb_check_flags_a_malformed_dead_list_row_wedged_between_valid_rows(tmp_path):
    tmp_kb = tmp_path / "kb"
    shutil.copytree(KB, tmp_kb)
    dead_list = tmp_kb / "DEAD_LIST.md"
    lines = dead_list.read_text().splitlines()
    row1_idx = next(i for i, l in enumerate(lines) if l.startswith("| 1 |"))
    wedged_lineno = row1_idx + 2  # 1-based line number the malformed line will land on
    lines.insert(row1_idx + 1, "| this row is missing its columns")
    dead_list.write_text("\n".join(lines) + "\n")

    problems = kb_check.check(tmp_kb, ld.REPO_ROOT)
    malformed = [p for p in problems if "malformed row at line" in p]
    assert malformed, problems
    assert any(str(wedged_lineno) in p for p in malformed), malformed

    # the real, unmodified KB must still pass cleanly
    assert kb_check.check(KB, ld.REPO_ROOT) == []
