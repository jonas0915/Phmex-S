"""Freeze a thesis (spec + signal code) with a sha256 BEFORE any data is read (spec §5 step 4).
Deterministic: canonical JSON, sorted keys. Tamper-evident: verify() recomputes the hash."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED_SPEC_KEYS = ("id", "lens", "mechanism", "counterparty", "prediction", "nearest_dead_rows", "spec", "signal_py")
SPEC_KEYS_INNER = ("dataset", "universe", "timeframe", "tp_bps", "sl_bps", "max_hold_bars", "expected_trades_per_week", "doa_line")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


def validate(thesis: dict) -> list[str]:
    errs = [f"missing key {k!r}" for k in REQUIRED_SPEC_KEYS if k not in thesis]
    if "id" in thesis and not _ID_RE.match(str(thesis["id"])):
        errs.append("id must be snake_case [a-z0-9_], 3-41 chars")
    spec = thesis.get("spec") or {}
    errs += [f"spec missing {k!r}" for k in SPEC_KEYS_INNER if k not in spec]
    if not str(thesis.get("signal_py", "")).strip() or "def signals(" not in str(thesis.get("signal_py", "")):
        errs.append("signal_py must define signals(df)")
    if isinstance(spec.get("universe"), list) and not spec["universe"]:
        errs.append("spec.universe is empty")
    return errs


def _canonical(thesis: dict) -> str:
    return json.dumps(thesis, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def freeze(thesis: dict, run_dir: Path, frozen_at: str) -> Path:
    errs = validate(thesis)
    if errs:
        raise ValueError("; ".join(errs))
    run_dir = Path(run_dir)
    sha = hashlib.sha256(_canonical(thesis).encode()).hexdigest()
    specs, screen = run_dir / "specs", run_dir / "screens" / thesis["id"]
    specs.mkdir(parents=True, exist_ok=True); screen.mkdir(parents=True, exist_ok=True)
    (screen / "signal.py").write_text(thesis["signal_py"])
    out = specs / f"{thesis['id']}.frozen.json"
    out.write_text(json.dumps({"thesis": thesis, "sha256": sha, "frozen_at": frozen_at}, indent=2, sort_keys=True))
    return out


def verify(frozen_path: Path) -> bool:
    try:
        frozen_path = Path(frozen_path)
        d = json.loads(frozen_path.read_text())
        thesis = d["thesis"]
        # Verify thesis integrity via SHA256
        if hashlib.sha256(_canonical(thesis).encode()).hexdigest() != d.get("sha256"):
            return False
        # Verify signal.py file exists and matches
        run_dir = frozen_path.parent.parent
        signal_file = run_dir / "screens" / thesis["id"] / "signal.py"
        if not signal_file.exists():
            return False
        if signal_file.read_text() != thesis["signal_py"]:
            return False
        return True
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError):
        return False


if __name__ == "__main__":
    thesis_path, run_dir, frozen_at = sys.argv[1], sys.argv[2], sys.argv[3]
    print(freeze(json.loads(Path(thesis_path).read_text()), Path(run_dir), frozen_at))
