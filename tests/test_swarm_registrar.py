import json
from pathlib import Path

import pytest

from research.swarm.lib import registrar as rg

GOOD = {
    "id": "demo_thesis", "lens": "literature", "mechanism": "m", "counterparty": "c", "prediction": "p",
    "nearest_dead_rows": [{"row": 1, "why_different": "x"}],
    "spec": {"dataset": "mr_edge", "universe": ["ETH"], "timeframe": "1h", "tp_bps": 100, "sl_bps": 100,
             "max_hold_bars": 24, "expected_trades_per_week": 5, "doa_line": "train CI95 upper < 0 → dead"},
    "signal_py": "import pandas as pd\ndef signals(df):\n    return pd.Series(0, index=df.index)\n",
}


def test_validate_good_thesis_has_no_errors():
    assert rg.validate(GOOD) == []


def test_validate_reports_missing_keys_and_bad_id():
    bad = {**GOOD, "id": "Bad Id!", "spec": {k: v for k, v in GOOD["spec"].items() if k != "doa_line"}}
    errs = rg.validate(bad)
    assert any("doa_line" in e for e in errs) and any("id" in e for e in errs)


def test_freeze_writes_spec_and_signal_and_verifies(tmp_path: Path):
    p = rg.freeze(GOOD, tmp_path, "2026-09-16T20:00:00Z")
    frozen = json.loads(p.read_text())
    assert frozen["sha256"] and frozen["frozen_at"] == "2026-09-16T20:00:00Z"
    assert (tmp_path / "screens" / "demo_thesis" / "signal.py").read_text() == GOOD["signal_py"]
    assert rg.verify(p) is True


def test_freeze_is_deterministic_and_tamper_evident(tmp_path: Path):
    p1 = rg.freeze(GOOD, tmp_path / "a", "t")
    p2 = rg.freeze(GOOD, tmp_path / "b", "t")
    assert json.loads(p1.read_text())["sha256"] == json.loads(p2.read_text())["sha256"]
    d = json.loads(p1.read_text()); d["thesis"]["spec"]["tp_bps"] = 999
    p1.write_text(json.dumps(d))
    assert rg.verify(p1) is False


def test_freeze_refuses_invalid_thesis(tmp_path: Path):
    with pytest.raises(ValueError):
        rg.freeze({**GOOD, "signal_py": ""}, tmp_path, "t")


def test_verify_detects_signal_py_tampering(tmp_path: Path):
    p = rg.freeze(GOOD, tmp_path, "2026-09-16T20:00:00Z")
    signal_file = tmp_path / "screens" / "demo_thesis" / "signal.py"
    signal_file.write_text("corrupted code")
    assert rg.verify(p) is False


def test_verify_detects_signal_py_deletion(tmp_path: Path):
    p = rg.freeze(GOOD, tmp_path, "2026-09-16T20:00:00Z")
    signal_file = tmp_path / "screens" / "demo_thesis" / "signal.py"
    signal_file.unlink()
    assert rg.verify(p) is False


def test_verify_handles_nonexistent_frozen_file(tmp_path: Path):
    assert rg.verify(tmp_path / "nonexistent.frozen.json") is False


def test_verify_handles_invalid_json(tmp_path: Path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {")
    assert rg.verify(bad_file) is False


def test_verify_handles_missing_thesis_key(tmp_path: Path):
    bad_file = tmp_path / "missing_thesis.json"
    bad_file.write_text(json.dumps({"sha256": "abc123", "frozen_at": "t"}))
    assert rg.verify(bad_file) is False


# ---------------------------------------------------------------------------
# max_concurrent at freeze time (2026-09-21, STANDARDS #17): a spec without the key gets
# fee_math.max_concurrent(sl_bps) filled in BEFORE canonicalising/hashing, so the frozen
# file carries it and verify() recomputes the same sha.
# ---------------------------------------------------------------------------
from research.swarm.lib import fee_math as fm


def test_freeze_fills_max_concurrent_from_fee_math_and_verifies(tmp_path: Path):
    assert "max_concurrent" not in GOOD["spec"]
    p = rg.freeze(GOOD, tmp_path, "t")
    frozen = json.loads(p.read_text())
    assert frozen["thesis"]["spec"]["max_concurrent"] == fm.max_concurrent(GOOD["spec"]["sl_bps"])
    assert isinstance(frozen["thesis"]["spec"]["max_concurrent"], int)
    assert rg.verify(p) is True
    # the sha covers the filled key: stripping it must break verification
    d = json.loads(p.read_text()); del d["thesis"]["spec"]["max_concurrent"]
    p.write_text(json.dumps(d))
    assert rg.verify(p) is False


def test_freeze_does_not_mutate_the_caller_thesis(tmp_path: Path):
    thesis = json.loads(json.dumps(GOOD))
    rg.freeze(thesis, tmp_path, "t")
    assert "max_concurrent" not in thesis["spec"]


def test_freeze_keeps_an_explicit_max_concurrent(tmp_path: Path):
    thesis = {**GOOD, "spec": {**GOOD["spec"], "max_concurrent": 1}}
    p = rg.freeze(thesis, tmp_path, "t")
    assert json.loads(p.read_text())["thesis"]["spec"]["max_concurrent"] == 1
    assert rg.verify(p) is True


def test_legacy_frozen_spec_without_max_concurrent_still_verifies(tmp_path: Path):
    """Frozen files under research/swarm/runs/ predate the key; verify() must still be True."""
    import hashlib
    run = tmp_path; (run / "specs").mkdir(); (run / "screens" / GOOD["id"]).mkdir(parents=True)
    (run / "screens" / GOOD["id"] / "signal.py").write_text(GOOD["signal_py"])
    sha = hashlib.sha256(rg._canonical(GOOD).encode()).hexdigest()
    p = run / "specs" / f"{GOOD['id']}.frozen.json"
    p.write_text(json.dumps({"thesis": GOOD, "sha256": sha, "frozen_at": "t"}, indent=2, sort_keys=True))
    assert rg.verify(p) is True
    assert rg.validate(GOOD) == []                       # absent key is valid (legacy)


@pytest.mark.parametrize("bad", [0, -1, "3", 1.5, True, None])
def test_validate_rejects_non_positive_int_max_concurrent(bad):
    thesis = {**GOOD, "spec": {**GOOD["spec"], "max_concurrent": bad}}
    assert any("max_concurrent" in e for e in rg.validate(thesis))


def test_validate_accepts_positive_int_max_concurrent():
    thesis = {**GOOD, "spec": {**GOOD["spec"], "max_concurrent": 1}}
    assert rg.validate(thesis) == []
