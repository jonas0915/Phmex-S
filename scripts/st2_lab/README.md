# ST2.0 Recursive Improvement Lab

Standalone, **isolated** loop that autonomously evolves the ST2.0 strategy
(book×tape absorption short) by replaying recorded market data through candidate
configs, ranking them relatively, and carrying the winner forward.

Spec: `docs/superpowers/specs/2026-06-15-st2-recursive-improvement-lab-design.md`

## Hard invariants
- **Never imports `bot.py`**, never mutates live state, never restarts the bot.
- Reads `logs/flow_capture.jsonl` (recorded stream) read-only.
- Autonomy ends where generated code would enter the live process: nothing reaches
  live without human audit (`/pre-restart-audit`) + paper-confirm + your approval.
- **Sandbox metrics are an optimistic upper bound** — the replay fills every signal,
  but live maker fill rate is ~43%, so positive sandbox PnL routinely contradicts
  live. The sandbox ranks A-vs-B only; **paper-confirm is the truth gate.**

## Run
```bash
cd scripts
python3 -m st2_lab.loop --iterations 5                 # persisted recursion
python3 -m st2_lab.loop --iterations 3 --limit 40000 --dry-run   # fast, no writes
touch st2_lab/.halt                                    # kill switch
```

## Pieces
| File | Role |
|------|------|
| `config.py` | paths, constants, `Metrics`, default champion + param bounds |
| `dataset.py` | load `flow_capture.jsonl` → per-symbol time-ordered records |
| `safe_exec.py` | AST-interpreted filter compiler (no eval/exec; whitelist only) |
| `evaluator.py` | replay a config → relative metrics (net/WR/Kelly) |
| `proposer.py` | deterministic param + curated-filter mutations |
| `champion.py` | recursive state store (`champion.json` + lineage) |
| `loop.py` | orchestrator: propose → eval → rank → accept → paper-confirm proposal |

## Output
- `champion.json` — current best config + lineage (recursive state).
- `logs/st2_lab.log` — per-iteration digest.
- `docs/fix-proposals/st2-lab-paper-confirm-*.md` — when a champion qualifies, a
  human-gated PAPER-CONFIRM candidate (picked up by the existing proposals-digest).

## Scheduling
`com.phmex.st2-lab.plist` runs it daily. It is safe to run continuously — it only
reads recorded data and writes proposals; it cannot touch live trading.

## Phase 2 (filter codegen)
`safe_exec` + the proposer's filter path are built and tested. The curated
`FILTER_LIBRARY` keeps the loop fully autonomous without an external call; an LLM
proposer can later be layered behind `proposer.propose()` using the same interface.
Filter-bearing champions still require human audit before running as a real paper slot.
