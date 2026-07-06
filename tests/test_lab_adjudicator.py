"""Unit tests for scripts/lab_adjudicator/ — the live-experiment adjudicator.

Fixture-based: fake state files / trade dicts / log text, no network, no live
files. Covers the giveback counter, CI computation, revert-trip logic, the
n=0 honesty rule, MR log parsing, and the drift watchdog thresholds.
"""
import json
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from lab_adjudicator import adjudicate as adj  # noqa: E402
from lab_adjudicator import drift_watchdog as dw  # noqa: E402

DEP = 1_783_310_460.0  # trail_arm_8 deploy epoch (2026-07-05 9:01 PM PT)

TRAIL_CFG = {
    "deployed_ts": DEP,
    "giveback_peak_roi_pct": 5.0,
    "full_sl_reasons": ("stop_loss", "exchange_close"),
    "win_reasons": ("trailing_stop", "early_exit"),
    "baseline_avg_win_usd": 0.46,
    "revert_giveback_count": 3,
    "revert_window_trades": 20,
    "min_wins_for_avg_verdict": 10,
}


def _trade(opened_off=10, entry=100.0, peak=100.0, exit_reason="stop_loss",
           net=-1.0, side="long", closed_off=None):
    return {"opened_at": DEP + opened_off, "closed_at": DEP + (closed_off or opened_off + 60),
            "entry_price": entry, "peak_price": peak, "side": side,
            "exit_reason": exit_reason, "net_pnl": net, "margin": 10.0}


def _giveback(off):
    # peak +0.6% price = +6% ROI at 10x, then full SL
    return _trade(opened_off=off, peak=100.6, exit_reason="stop_loss", net=-1.2)


# ── peak ROI ──────────────────────────────────────────────────────────────
def test_peak_roi_long():
    t = _trade(peak=100.5)  # +0.5% price * 10x = +5% ROI
    assert abs(adj.peak_roi_pct(t) - 5.0) < 1e-9


def test_peak_roi_short_uses_favorable_direction():
    t = _trade(peak=99.0, side="short")  # price fell 1% -> +10% ROI for a short
    assert abs(adj.peak_roi_pct(t) - 10.0) < 1e-9


def test_peak_roi_none_when_untracked():
    assert adj.peak_roi_pct({"entry_price": 100.0, "side": "long"}) is None


# ── giveback counter ──────────────────────────────────────────────────────
def test_giveback_counted_only_when_peaked_then_full_sl():
    trades = [
        _giveback(10),                                        # counted
        _trade(opened_off=20, peak=100.2, net=-1.2),          # peaked only +2% ROI
        _trade(opened_off=30, peak=100.9, exit_reason="trailing_stop",
               net=0.5),                                      # win exit, not giveback
        _trade(opened_off=-9999, peak=100.9, net=-1.2),       # pre-deploy: excluded
    ]
    r = adj.grade_trail_arm(trades, TRAIL_CFG)
    assert r["givebacks_in_window"] == 1
    assert r["n_post_deploy"] == 3


def test_giveback_requires_negative_net():
    # peaked >=5% and reason exchange_close but net > 0 (partial-TP salvage)
    trades = [_trade(peak=100.8, exit_reason="exchange_close", net=0.10)]
    r = adj.grade_trail_arm(trades, TRAIL_CFG)
    assert r["givebacks_in_window"] == 0


# ── revert-trip logic ─────────────────────────────────────────────────────
def test_zero_trades_is_no_verdict():
    r = adj.grade_trail_arm([], TRAIL_CFG)
    assert r["status"] == adj.WATCH
    assert "n=0" in r["note"] and "no verdict" in r["note"]
    assert r["avg_win_usd"] is None


def test_two_givebacks_watch_three_trips():
    two = [_giveback(i * 100) for i in range(2)]
    r2 = adj.grade_trail_arm(two, TRAIL_CFG)
    assert r2["status"] == adj.WATCH
    three = [_giveback(i * 100) for i in range(3)]
    r3 = adj.grade_trail_arm(three, TRAIL_CFG)
    assert r3["status"] == adj.REVERT
    assert r3["givebacks_in_window"] == 3


def test_givebacks_beyond_first_20_relevant_do_not_trip():
    # 20 clean trail-relevant wins first, THEN 3 givebacks -> outside the window
    wins = [_trade(opened_off=i * 100, peak=101.0, exit_reason="trailing_stop",
                   net=1.0) for i in range(20)]
    late = [_giveback(3000 + i * 100) for i in range(3)]
    r = adj.grade_trail_arm(wins + late, TRAIL_CFG)
    assert r["givebacks_in_window"] == 0
    assert r["status"] != adj.REVERT


def test_avg_win_below_baseline_trips_only_at_min_n():
    # 9 wins below baseline: not enough n for a verdict
    small = [_trade(opened_off=i * 100, peak=101.0, exit_reason="trailing_stop",
                    net=0.30) for i in range(9)]
    r = adj.grade_trail_arm(small, TRAIL_CFG)
    assert r["status"] == adj.WATCH
    # 10th win, still below $0.46 baseline: trips
    big = small + [_trade(opened_off=999_9, peak=101.0,
                          exit_reason="early_exit", net=0.30)]
    r2 = adj.grade_trail_arm(big, TRAIL_CFG)
    assert r2["status"] == adj.REVERT
    assert abs(r2["avg_win_usd"] - 0.30) < 1e-9


def test_pass_when_window_complete_and_clean():
    wins = [_trade(opened_off=i * 100, peak=101.0, exit_reason="trailing_stop",
                   net=1.0) for i in range(20)]
    r = adj.grade_trail_arm(wins, TRAIL_CFG)
    assert r["status"] == adj.PASS


# ── CI computation ────────────────────────────────────────────────────────
def test_ci_vs_constant_centers_on_mean_minus_constant():
    sample = [1.0, 2.0, 3.0, 2.0, 2.0, 2.0, 1.5, 2.5] * 5  # mean 2.0
    lo, hi = adj.ci_vs_constant(sample, 0.46)
    assert lo <= 2.0 - 0.46 <= hi
    assert lo < hi
    # a clearly-above-baseline sample must have a CI excluding zero
    assert lo > 0


def test_ci_vs_constant_needs_n3():
    assert adj.ci_vs_constant([1.0, 2.0], 0.5) is None


def test_ci_deterministic_across_runs():
    s = [0.1, 0.9, 0.4, 0.7, 0.2, 0.8]
    assert adj.ci_vs_constant(s, 0.15) == adj.ci_vs_constant(s, 0.15)


# ── sizing grader (fake state file on disk) ───────────────────────────────
def test_sizing_from_fake_state_file(tmp_path):
    dep = adj.EXPERIMENTS["sizing_15"]["deployed_ts"]
    trades = ([{"opened_at": dep - 1000 - i, "margin": 9.0} for i in range(10)]
              + [{"opened_at": dep + 10 + i, "margin": 14.0} for i in range(10)])
    p = tmp_path / "trading_state.json"
    p.write_text(json.dumps({"closed_trades": trades}))
    loaded = adj.load_closed_trades(p)
    assert len(loaded) == 20
    log = ("2026-07-06 01:00:00 [WARNING] [KILL SWITCH] DAILY LOSS HALT: "
           "today net $-2.16 exceeds -3% of $57.40\n"
           "2026-07-05 06:07:55 [WARNING] [KILL SWITCH] DAILY LOSS HALT: pre-deploy\n")
    r = adj.grade_sizing(loaded, log, adj.EXPERIMENTS["sizing_15"],
                         now=dep + 2 * 86400)
    assert r["n_post_deploy"] == 10 and r["n_pre_baseline"] == 10
    assert abs(r["margin_diff_usd"] - 5.0) < 1e-9
    lo, hi = r["margin_diff_ci95"]
    assert lo <= 5.0 <= hi
    assert r["halt_days"] == ["2026-07-06"]  # pre-deploy halt excluded


def test_sizing_no_post_trades_is_no_verdict():
    dep = adj.EXPERIMENTS["sizing_15"]["deployed_ts"]
    pre = [{"opened_at": dep - 100 - i, "margin": 10.0} for i in range(5)]
    r = adj.grade_sizing(pre, "", adj.EXPERIMENTS["sizing_15"], now=dep + 86400)
    assert "no verdict" in r["note"]


# ── MR bundle: log parsing + grading ──────────────────────────────────────
# Real line shapes from bot.log (2026-07-04 12:19-12:21): the [MAKER] order
# line has no slot tag, so attempts are inferred as fills + final-miss lines.
MR_LOG = """\
2026-07-04 12:19:30 [INFO] [MAKER] Limit buy 3.32 LTC/USDT:USDT @ 45.14 (id=x)
2026-07-04 12:20:41 [INFO] [SLOT LIVE] [MR REQUOTE] 5m_mean_revert LTC/USDT:USDT long attempt 1/1 @ 45.15 (drift +0.000%)
2026-07-04 12:21:15 [INFO] [SLOT LIVE] 5m_mean_revert LTC/USDT:USDT long — no fill (PostOnly miss), skipping | BB mean reversion LONG
2026-07-04 13:00:30 [INFO] [SLOT LIVE] 5m_mean_revert ENTRY DOGE long filled
2026-07-01 09:00:00 [INFO] [SLOT LIVE] 5m_mean_revert OLD/USDT:USDT long — no fill (PostOnly miss), skipping
2026-07-04 14:00:00 [INFO] [SLOT LIVE] other_slot ENTRY BTC long filled
"""


def test_parse_mr_log_counts_and_since_filter():
    since = 1_783_000_000.0  # 2026-07-02 6:46 AM PT — excludes the 7/01 miss
    act = adj.parse_mr_log(MR_LOG, since)
    assert act == {"attempts": 2, "fills": 1, "misses": 1, "requotes": 1}


def test_parse_mr_log_requoted_miss_is_one_attempt():
    # a requote retry that still misses ends in ONE final miss line -> 1 attempt
    txt = ("2026-07-04 12:20:41 [INFO] [SLOT LIVE] [MR REQUOTE] 5m_mean_revert "
           "LTC/USDT:USDT long attempt 1/1 @ 45.15 (drift +0.000%)\n"
           "2026-07-04 12:21:15 [INFO] [SLOT LIVE] 5m_mean_revert LTC/USDT:USDT "
           "long — no fill (PostOnly miss), skipping\n")
    act = adj.parse_mr_log(txt, 0.0)
    assert act == {"attempts": 1, "fills": 0, "misses": 1, "requotes": 1}


def test_grade_mr_bundle_small_n_is_watch():
    cfg = adj.EXPERIMENTS["mr_bundle"]
    slot = {"closed_trades": [{"mode": "live", "closed_at": cfg["deployed_ts"] + 5,
                               "net_pnl": 0.5}]}
    r = adj.grade_mr_bundle(slot, {"requote_miss": 1}, MR_LOG, cfg)
    assert r["status"] == adj.WATCH
    assert r["n_live_trades"] == 1 and r["live_wins"] == 1
    assert r["sidecar_counters"] == {"requote_miss": 1}


def test_grade_mr_bundle_zero_activity_no_verdict():
    cfg = adj.EXPERIMENTS["mr_bundle"]
    r = adj.grade_mr_bundle({}, {}, "", cfg)
    assert "n=0" in r["note"]


# ── drift watchdog thresholds (pure function) ─────────────────────────────
def test_drift_classify_ok():
    status, _ = dw.classify(-4.5, n=50)
    assert status == "OK"


def test_drift_classify_absolute_floor():
    status, reason = dw.classify(-6.2, n=50)
    assert status == "ALERT" and "floor" in reason


def test_drift_classify_deterioration_and_floor():
    status, reason = dw.classify(-6.6, n=50)
    assert status == "ALERT"
    assert "floor" in reason and "worse than" in reason


def test_drift_classify_boundary_not_alert():
    # exactly at the floor is not "worse than" the floor
    status, _ = dw.classify(-6.0, n=50)
    assert status == "OK"


def test_drift_classify_tiny_n_no_verdict():
    status, reason = dw.classify(-9.9, n=2)
    assert status == "NO-DATA" and "no verdict" in reason
    status2, _ = dw.classify(None, n=0)
    assert status2 == "NO-DATA"
