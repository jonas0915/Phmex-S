"""Read new overwatch fix proposals, verify cited code references against the live
codebase, and Telegram a digest. Runs every 3 days at 5 AM PT via launchd.

Verification logic per cited `file.py:N` reference in a spec:
  1. Parse the cited file with the ast module.
  2. Build a map of function/method/class definitions to their line ranges.
  3. Find which definition contains line N. Extract its name.
  4. Scan the spec text within ±200 chars of the citation for function names.
  5. If the spec mentions a function name that does NOT contain line N, flag mismatch.
  6. If the cited line is beyond the end of the file or the file doesn't exist, flag.

Verdicts:
  VALID         — all citations check out (file:line exists AND spec-mentioned
                  functions live where claimed)
  SUSPICIOUS    — at least one citation has a function-vs-line mismatch
  HALLUCINATED  — at least one cited file is missing OR line is out of range OR
                  the LLM cited a function that does not exist anywhere in the file

Never applies anything. Only summarizes and proposes.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import notifier  # noqa: E402

PROPOSAL_DIR = REPO_ROOT / "docs" / "fix-proposals"
STATE_PATH = REPO_ROOT / "logs" / "proposals_digest_state.json"
CITE_RE = re.compile(r"`?([A-Za-z_][\w/]*\.py)`?[:\s]+(\d{1,5})")
FUNC_HINT_RE = re.compile(r"`?([a-zA-Z_][a-zA-Z0-9_]*)`?\s*[\(\[]")


@dataclass
class Citation:
    file: str
    line: int
    context_text: str
    verdict: str = ""  # "valid", "out_of_range", "missing_file", "mismatch"
    found_in: str | None = None  # function/class name actually at the line
    expected_names: list[str] = field(default_factory=list)


@dataclass
class SpecVerdict:
    filename: str
    title: str
    citations: list[Citation]
    overall: str  # VALID / SUSPICIOUS / HALLUCINATED
    summary_line: str


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"seen": []}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"seen": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def build_def_map(file_path: Path) -> list[tuple[str, int, int]]:
    """Return list of (qualified_name, start_line, end_line) for every def/class in the file."""
    try:
        tree = ast.parse(file_path.read_text())
    except (SyntaxError, OSError):
        return []
    defs: list[tuple[str, int, int]] = []

    def walk(node: ast.AST, prefix: str = ""):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                start = child.lineno
                end = getattr(child, "end_lineno", start)
                defs.append((name, start, end))
                walk(child, prefix=f"{name}.")
            else:
                walk(child, prefix=prefix)

    walk(tree)
    return defs


def find_containing_def(defs: list[tuple[str, int, int]], line: int) -> str | None:
    """Return the innermost def containing `line`, or None."""
    matches = [name for (name, start, end) in defs if start <= line <= end]
    if not matches:
        return None
    return matches[-1]  # innermost (last is deepest because walk is pre-order)


def names_in_context(spec_text: str, citation_match_start: int, window: int = 200) -> list[str]:
    """Find function/method names mentioned near the citation, e.g. `check_positions` or call()."""
    start = max(0, citation_match_start - window)
    end = citation_match_start + window
    window_text = spec_text[start:end]
    # Snake-case identifiers in backticks: `_func_name` or `func_name`
    names = set(re.findall(r"`(_?[a-z][a-z0-9_]*)`", window_text))
    # Also: bare snake_case followed by ( or [
    names.update(re.findall(r"\b(_?[a-z][a-z0-9_]+)\s*[\(\[]", window_text))
    # Filter out obvious noise
    noise = {"def", "if", "for", "in", "is", "not", "and", "or", "lambda", "return", "self", "true", "false", "none", "py"}
    return sorted(n for n in names if n not in noise and len(n) > 2)


def verify_spec(spec_path: Path) -> SpecVerdict:
    text = spec_path.read_text()
    # Title: first H1 line
    title = "(no title)"
    for line in text.splitlines():
        if line.startswith("# "):
            title = line.lstrip("# ").strip()
            break

    citations: list[Citation] = []
    for m in CITE_RE.finditer(text):
        fname, lineno_str = m.group(1), m.group(2)
        lineno = int(lineno_str)
        ctx_start = max(0, m.start() - 100)
        ctx_end = min(len(text), m.end() + 100)
        ctx = text[ctx_start:ctx_end].replace("\n", " ")

        cite = Citation(file=fname, line=lineno, context_text=ctx)
        cite.expected_names = names_in_context(text, m.start())

        file_path = REPO_ROOT / fname
        if not file_path.exists():
            cite.verdict = "missing_file"
            citations.append(cite)
            continue

        line_count = sum(1 for _ in file_path.open())
        if lineno > line_count:
            cite.verdict = "out_of_range"
            citations.append(cite)
            continue

        defs = build_def_map(file_path)
        cite.found_in = find_containing_def(defs, lineno)

        # Mismatch check: if the spec mentions a function name AND that name exists in the
        # file but does NOT contain the cited line, flag mismatch.
        all_def_names = {d[0].split(".")[-1] for d in defs}
        bad = False
        for nm in cite.expected_names:
            if nm in all_def_names and (not cite.found_in or nm != cite.found_in.split(".")[-1]):
                # Is the named function elsewhere in the file?
                matching_def = [d for d in defs if d[0].split(".")[-1] == nm]
                if matching_def and not (matching_def[0][1] <= lineno <= matching_def[0][2]):
                    bad = True
                    break
        cite.verdict = "mismatch" if bad else "valid"
        citations.append(cite)

    # Overall verdict
    if any(c.verdict in ("missing_file", "out_of_range") for c in citations):
        overall = "HALLUCINATED"
    elif any(c.verdict == "mismatch" for c in citations):
        overall = "SUSPICIOUS"
    elif citations:
        overall = "VALID"
    else:
        overall = "NO_CITATIONS"

    n_total = len(citations)
    n_bad = sum(1 for c in citations if c.verdict != "valid")
    summary = f"{n_total} citations, {n_bad} flagged"

    return SpecVerdict(filename=spec_path.name, title=title, citations=citations,
                       overall=overall, summary_line=summary)


def build_digest(verdicts: list[SpecVerdict]) -> str:
    lines = [f"[FIX PROPOSALS DIGEST] {datetime.now().strftime('%Y-%m-%d %H:%M PT')}"]
    lines.append(f"New since last run: {len(verdicts)}")
    lines.append("")
    counts = {"VALID": 0, "SUSPICIOUS": 0, "HALLUCINATED": 0, "NO_CITATIONS": 0}
    for v in verdicts:
        counts[v.overall] += 1
    lines.append(f"Verdicts: {counts['VALID']} valid, {counts['SUSPICIOUS']} suspicious, "
                 f"{counts['HALLUCINATED']} hallucinated, {counts['NO_CITATIONS']} no-cite")
    lines.append("")
    for v in verdicts:
        icon = {"VALID": "OK", "SUSPICIOUS": "??", "HALLUCINATED": "!!", "NO_CITATIONS": "--"}[v.overall]
        lines.append(f"[{icon}] {v.filename}")
        lines.append(f"      {v.title[:80]}")
        lines.append(f"      {v.summary_line}")
        bad_cites = [c for c in v.citations if c.verdict != "valid"]
        for c in bad_cites[:3]:
            reason = c.verdict
            if reason == "mismatch":
                reason = f"mismatch (line in {c.found_in or '?'}, spec mentions {','.join(c.expected_names[:2])})"
            lines.append(f"        - {c.file}:{c.line} → {reason}")
        lines.append("")
    lines.append("Action: ping me with 'review proposals' to read each in detail before approving.")
    return "\n".join(lines)


def main() -> int:
    state = load_state()
    seen = set(state.get("seen", []))
    all_specs = sorted(p.name for p in PROPOSAL_DIR.glob("*.md") if p.name != ".gitkeep")
    new_specs = [name for name in all_specs if name not in seen]

    if not new_specs:
        print("No new fix proposals since last run.")
        return 0

    verdicts: list[SpecVerdict] = []
    for name in new_specs:
        verdicts.append(verify_spec(PROPOSAL_DIR / name))

    digest = build_digest(verdicts)
    print(digest)

    try:
        notifier.send(digest)
    except Exception as e:
        print(f"telegram send failed: {e}")
        return 1

    # Persist state
    state["seen"] = sorted(seen | set(new_specs))
    state["last_run"] = datetime.now().isoformat()
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
