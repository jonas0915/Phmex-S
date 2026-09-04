"""H0 data sink (2026-09-03 MR edge search): durable archive of 5m_mean_revert
OB/TAPE gate blocks so the registered OB-imbalance counterfactual (n>=10
episodes, 7/14) becomes readable despite bot.log's ~10-day rotation."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "slot_lab"))

import mr_gate_block_archiver as A  # noqa: E402

L1 = "2026-08-30 13:46:53 [DEBUG] [PAPER] [OB GATE] 5m_mean_revert ETH/USDT:USDT LONG blocked — unmatched ask wall"
L2 = "2026-09-03 03:49:35 [DEBUG] [PAPER] [TAPE GATE] 5m_mean_revert DOGE/USDT:USDT LONG blocked — buy_ratio 4%"
L3 = "2026-09-03 03:02:36 [DEBUG] [PAPER] [OB GATE] 5m_mean_revert ADA/USDT:USDT SHORT blocked — bid imbalance -0.31"
NOISE = "2026-09-03 03:02:36 [DEBUG] [PAPER] [OB GATE] SR_BOUNCE ADA/USDT:USDT LONG blocked — unmatched ask wall"


def test_parse_ob_gate_line():
    r = A.parse_line(L1)
    assert r == {"ts": "2026-08-30 13:46:53", "gate": "OB", "symbol": "ETH/USDT:USDT",
                 "side": "LONG", "reason": "unmatched ask wall"}


def test_parse_tape_gate_line_and_short():
    assert A.parse_line(L2)["gate"] == "TAPE"
    assert A.parse_line(L2)["reason"] == "buy_ratio 4%"
    assert A.parse_line(L3)["side"] == "SHORT"


def test_parse_ignores_other_slots_and_unrelated():
    assert A.parse_line(NOISE) is None
    assert A.parse_line("2026-09-03 03:02:36 [INFO] Cycle #1 | Positions: 0") is None


def test_archive_appends_new_and_dedupes(tmp_path):
    log = tmp_path / "bot.log"
    log.write_text("\n".join([L1, NOISE, L2]) + "\n")
    out = tmp_path / "mr_gate_blocks.jsonl"
    n = A.archive([str(log)], str(out))
    assert n == 2
    # second run over the same log + one new line adds only the new one
    log.write_text("\n".join([L1, L2, L3]) + "\n")
    n = A.archive([str(log)], str(out))
    assert n == 1
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert len(rows) == 3
    assert {r["symbol"] for r in rows} == {"ETH/USDT:USDT", "DOGE/USDT:USDT", "ADA/USDT:USDT"}


def test_archive_missing_log_is_skipped(tmp_path):
    out = tmp_path / "o.jsonl"
    assert A.archive([str(tmp_path / "nope.log")], str(out)) == 0
