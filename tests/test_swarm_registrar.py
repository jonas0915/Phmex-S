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
