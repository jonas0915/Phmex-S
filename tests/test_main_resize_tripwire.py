"""$15-era tripwire (owner-registered 2026-08-10).

After the n=42 PASS verdict, main resized $5 -> $15 on 8/9 8:47 PM PT while
the era was mid-slump (8 of 11 losses). Pre-registered rail: at n>=10
$15-era trades with net <= -$3.00, OR net <= -$6.00 at any n, the
adjudicator TRIPs — touches .halt_main_entries (runtime sentinel: blocks
main entries, exits unaffected) pending owner review. Report-only otherwise.
"""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from lab_adjudicator import adjudicate as adj  # noqa: E402

CFG = {"deployed_ts": 1_786_333_620.0,  # 8/9/2026 8:47 PM PT
       "trip_n": 10, "trip_net": -3.0, "hard_net": -6.0, "min_margin": 10.0}


def _t(net, margin=14.0, opened_off=100):
    return {"strategy": "htf_l2_anticipation", "exit_reason": "stop_loss",
            "opened_at": CFG["deployed_ts"] + opened_off,
            "closed_at": CFG["deployed_ts"] + opened_off + 60,
            "net_pnl": net, "margin": margin}


def test_watch_below_thresholds(tmp_path):
    r = adj.grade_main_resize15([_t(-1.0), _t(-0.7)], CFG, bot_dir=str(tmp_path))
    assert r["status"] == adj.WATCH
    assert not os.path.exists(tmp_path / ".halt_main_entries")


def test_trip_at_n10_net_below_line(tmp_path):
    trades = [_t(-0.5, opened_off=i * 10) for i in range(9)] + [_t(0.5)]
    # net = -4.0 at n=10
    r = adj.grade_main_resize15(trades, CFG, bot_dir=str(tmp_path))
    assert r["status"] == "TRIP"
    assert os.path.exists(tmp_path / ".halt_main_entries")


def test_no_trip_at_n10_just_inside_line(tmp_path):
    trades = [_t(-0.299, opened_off=i * 10) for i in range(10)]  # net -2.99
    r = adj.grade_main_resize15(trades, CFG, bot_dir=str(tmp_path))
    assert r["status"] == adj.WATCH
    assert not os.path.exists(tmp_path / ".halt_main_entries")


def test_hard_line_trips_early(tmp_path):
    trades = [_t(-2.2, opened_off=i * 10) for i in range(3)]  # net -6.6 at n=3
    r = adj.grade_main_resize15(trades, CFG, bot_dir=str(tmp_path))
    assert r["status"] == "TRIP"
    assert os.path.exists(tmp_path / ".halt_main_entries")


def test_five_dollar_era_trades_excluded(tmp_path):
    # Old $5-era stragglers (margin ~5) must not count toward the $15 era.
    trades = ([_t(-2.0, margin=5.0, opened_off=i * 10) for i in range(10)]
              + [_t(-1.0)])
    r = adj.grade_main_resize15(trades, CFG, bot_dir=str(tmp_path))
    assert r["status"] == adj.WATCH
    assert r["n_trades"] == 1


def test_trip_is_idempotent_preserves_existing_sentinel(tmp_path):
    sentinel = tmp_path / ".halt_main_entries"
    sentinel.write_text("owner halt 2026-07-31\n")
    trades = [_t(-1.0, opened_off=i * 10) for i in range(10)]  # net -10
    r = adj.grade_main_resize15(trades, CFG, bot_dir=str(tmp_path))
    assert r["status"] == "TRIP"
    assert sentinel.read_text() == "owner halt 2026-07-31\n"  # not clobbered


# ── main-book PAPER mode (.paper_main demotion, 2026-08-26) ────────────────
def test_paper_rows_never_trip(tmp_path):
    # Simulated fills (mode="paper") must never advance the registered
    # real-money tripwire — even a deep sim loss writes NO sentinel.
    trades = [dict(_t(-1.0, opened_off=i * 10), mode="paper")
              for i in range(12)]  # sim net -12, would hard-trip if counted
    r = adj.grade_main_resize15(trades, CFG, bot_dir=str(tmp_path))
    assert r["status"] == adj.WATCH
    assert r["n_trades"] == 0  # line holds at last real-money state
    assert not os.path.exists(tmp_path / ".halt_main_entries")


def test_paper_rows_excluded_real_rows_still_group(tmp_path):
    # Mixed ledger: a real partial-TP pair (no mode field, shared
    # symbol+opened_at — the 8/17 re-registered counting) still groups into
    # ONE trade; paper rows drop BEFORE grouping and never contribute.
    half_a = dict(_t(1.0, margin=7.5, opened_off=100), symbol="BTC/USDT")
    half_b = dict(_t(0.5, margin=7.5, opened_off=100), symbol="BTC/USDT")
    sims = [dict(_t(-2.0, opened_off=200 + i * 10), mode="paper")
            for i in range(5)]  # sim net -10
    r = adj.grade_main_resize15([half_a, half_b] + sims, CFG,
                                bot_dir=str(tmp_path))
    assert r["n_trades"] == 1                # one grouped real trade
    assert abs(r["net_usd"] - 1.5) < 1e-9    # sim -10 never entered
    assert r["status"] == adj.WATCH
    assert not os.path.exists(tmp_path / ".halt_main_entries")
