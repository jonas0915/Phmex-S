"""Phase 0 (2026-06-19): slot entry snapshots must record the orderbook block.

A hardcoded `None` for the `ob` arg at the slot entry call (bot.py:2038) caused
every real ST2.0 trade to record `entry_snapshot.ob = null`, blinding the lab to
half its feature vector. These tests pin the contract: a populated ob arg produces
a populated ob block; ob=None degrades to null (no crash); and the slot entry call
site actually passes `ob` (not None) so it can't silently regress.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import Phmex2Bot

BOT_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot.py")


def _bot():
    return Phmex2Bot.__new__(Phmex2Bot)  # no __init__ / network


def test_snapshot_records_ob_block_when_present():
    bot = _bot()
    ob = {"imbalance": 0.42, "spread_pct": 0.051,
          "bid_walls": [1, 2], "ask_walls": [3]}
    flow = {"buy_ratio": 0.61, "cvd_slope": -0.4, "divergence": None,
            "large_trade_bias": 0.1, "trade_count": 30}
    snap = bot._log_entry_snapshot("BTC/USDT:USDT", "short", "ST2.0", "st2", 0.85,
                                   100.0, 0, ob, flow)
    assert snap["ob"] is not None, "ob block must be populated when ob is present"
    assert snap["ob"]["imbalance"] == 0.42
    assert snap["ob"]["spread_pct"] == 0.051
    assert snap["ob"]["bid_walls"] == 2
    assert snap["ob"]["ask_walls"] == 1
    assert snap["flow"]["buy_ratio"] == 0.61


def test_snapshot_ob_null_when_absent_no_crash():
    bot = _bot()
    flow = {"buy_ratio": 0.61, "cvd_slope": -0.4, "divergence": None,
            "large_trade_bias": 0.1, "trade_count": 30}
    snap = bot._log_entry_snapshot("BTC/USDT:USDT", "short", "ST2.0", "st2", 0.85,
                                   100.0, 0, None, flow)
    assert snap["ob"] is None  # graceful degradation preserved (API-failure path)
    assert snap["flow"] is not None


def test_slot_entry_call_passes_ob_not_none():
    """Static guard: the slot shared-tail snapshot call must pass `ob`, not None.
    Prevents a regression back to the ob:null bug."""
    with open(BOT_PY) as f:
        src = f.read()
    # The slot entry call is the _log_entry_snapshot invocation that uses slot.slot_id.
    m = re.search(r"_log_entry_snapshot\(\s*symbol,\s*direction,\s*slot\.slot_id[^\)]*\)",
                  src, re.DOTALL)
    assert m, "could not locate the slot entry _log_entry_snapshot call"
    call = m.group(0)
    # The positional args end with `... strength, entry_px, <conf>, <ob>, flow,`
    # (<conf> was a literal 0 until the 2026-07-18 telemetry-parity fix passed
    # the computed _conf through; this guard only pins the ob arg).
    assert re.search(r"entry_px,\s*_conf,\s*ob,\s*flow", call), \
        "slot entry must pass `ob` (not None) as the orderbook arg — ob:null regression"
