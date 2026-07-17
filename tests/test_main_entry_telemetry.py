"""F6 (2026-07-17): main-path entry telemetry.

Debug findings: (a) ensemble-confidence blocks were never logged to
gotAway.jsonl — invisible to every gate analysis (they also never fired, but
if the threshold is ever raised, blocks must be measurable); (b) gate_tags was
None on ALL main-path entered trades (only slot paths wrote it), making
entered-trade gate forensics impossible — round-1 finding, all 235 htf_l2
trades untagged.
"""
import inspect

import bot as botmod


def test_ensemble_skip_logs_gotaway():
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    skip_idx = src.find("[ENSEMBLE SKIP]")
    assert skip_idx != -1
    region = src[skip_idx - 600:skip_idx + 600]
    assert '_log_gotaway("ensemble_confidence"' in region, (
        "ensemble blocks must be gotAway-logged"
    )


def test_main_path_entries_get_gate_tags():
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    assert "pos.gate_tags = " in src, (
        "main-path entries must write gate_tags (was None on all 235 htf_l2 trades)"
    )
    # The assignment must produce 'none' rather than None when no tags are active,
    # so future forensics can distinguish 'no tags' from 'telemetry missing'.
    tag_idx = src.find("pos.gate_tags = ")
    region = src[tag_idx:tag_idx + 300]
    assert '"none"' in region


def test_shadow_axes_included():
    src = inspect.getsource(botmod.Phmex2Bot._run_cycle)
    assert "sg_htf_adx_hi" in src and "sg_thin_tape" in src, (
        "the two debug-identified toxic axes must be tagged on entered trades"
    )
