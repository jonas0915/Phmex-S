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
