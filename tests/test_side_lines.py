"""Long-side verdict lines (owner-registered 2026-08-10 ~8:45 PM PT).

Evidence: main gated-era longs −$3.37 @58% vs shorts +$4.05 @82% (diff CI
excludes 0); MR live longs −$1.07 vs shorts +$15.15 (8/1 research, CI barely
excludes 0). Registered forward lines — NO lookback:
  - main_long_side: next 10 main-era longs (htf_l2_anticipation) opened
    after registration; net <= $0 -> KILL_SIDE -> touch .block_longs_main
  - mr_long_side: next 8 LIVE 5m_mean_revert longs; net <= $0 ->
    KILL_SIDE -> touch .block_longs_5m_mean_revert
Sentinels are dormant until a line trips; bot-side gate skips long entries
for a book whose sentinel exists (shorts unaffected).
"""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))
sys.path.insert(0, BOT_DIR)

from lab_adjudicator import adjudicate as adj  # noqa: E402

REG = 1_786_418_700.0  # registration epoch (fixture)

MAIN_CFG = {"registered_ts": REG, "verdict_n": 10, "side": "long",
            "strategy": "htf_l2_anticipation", "require_live_mode": False,
            "sentinel": ".block_longs_main"}
MR_CFG = {"registered_ts": REG, "verdict_n": 8, "side": "long",
          "strategy": None, "require_live_mode": True,
          "sentinel": ".block_longs_5m_mean_revert"}


def _t(net, side="long", opened_off=100, strategy="htf_l2_anticipation",
       mode=None, reason="stop_loss"):
    t = {"strategy": strategy, "side": side, "exit_reason": reason,
         "opened_at": REG + opened_off, "closed_at": REG + opened_off + 60,
         "net_pnl": net, "margin": 14.0}
    if mode:
        t["mode"] = mode
    return t


def test_watch_before_verdict_n(tmp_path):
    r = adj.grade_side_line([_t(-1.0), _t(-0.5)], MAIN_CFG, bot_dir=str(tmp_path))
    assert r["status"] == adj.WATCH
    assert not os.path.exists(tmp_path / ".block_longs_main")


def test_kill_side_at_n_net_negative(tmp_path):
    trades = [_t(-0.4, opened_off=i * 10) for i in range(10)]
    r = adj.grade_side_line(trades, MAIN_CFG, bot_dir=str(tmp_path))
    assert r["status"] == "KILL_SIDE"
    assert os.path.exists(tmp_path / ".block_longs_main")


def test_pass_at_n_net_positive_no_sentinel(tmp_path):
    trades = [_t(0.5, opened_off=i * 10) for i in range(10)]
    r = adj.grade_side_line(trades, MAIN_CFG, bot_dir=str(tmp_path))
    assert r["status"] == adj.PASS
    assert not os.path.exists(tmp_path / ".block_longs_main")


def test_only_registered_side_counts(tmp_path):
    trades = ([_t(-1.0, side="short", opened_off=i * 10) for i in range(10)]
              + [_t(-0.5)])
    r = adj.grade_side_line(trades, MAIN_CFG, bot_dir=str(tmp_path))
    assert r["n_trades"] == 1
    assert r["status"] == adj.WATCH


def test_pre_registration_trades_excluded(tmp_path):
    old = [_t(-1.0, opened_off=-500 - i * 10) for i in range(10)]
    r = adj.grade_side_line(old + [_t(-0.5)], MAIN_CFG, bot_dir=str(tmp_path))
    assert r["n_trades"] == 1


def test_mr_line_counts_live_mode_only(tmp_path):
    trades = ([_t(-1.0, strategy="bb_mean_reversion", mode="paper",
                  opened_off=i * 10) for i in range(8)]
              + [_t(-1.0, strategy="bb_mean_reversion", mode="live")])
    r = adj.grade_side_line(trades, MR_CFG, bot_dir=str(tmp_path))
    assert r["n_trades"] == 1
    assert r["status"] == adj.WATCH


def test_kill_sentinel_idempotent(tmp_path):
    sentinel = tmp_path / ".block_longs_main"
    sentinel.write_text("existing\n")
    trades = [_t(-0.4, opened_off=i * 10) for i in range(10)]
    r = adj.grade_side_line(trades, MAIN_CFG, bot_dir=str(tmp_path))
    assert r["status"] == "KILL_SIDE"
    assert sentinel.read_text() == "existing\n"


# ── main-book PAPER mode (.paper_main demotion, 2026-08-26) ────────────

def test_main_paper_rows_excluded(tmp_path):
    # Simulated main fills (mode="paper") never advance a registered side
    # line; no-mode rows are real money and still count.
    sims = [_t(-1.0, mode="paper", opened_off=i * 10) for i in range(10)]
    r = adj.grade_side_line(sims + [_t(-0.5, opened_off=200)], MAIN_CFG,
                            bot_dir=str(tmp_path))
    assert r["n_trades"] == 1
    assert r["status"] == adj.WATCH
    assert not os.path.exists(tmp_path / ".block_longs_main")


def test_main_short_watch_line_excludes_paper(tmp_path):
    # The 8/12 watch-only short half-book: sim rows excluded there too.
    cfg = dict(MAIN_CFG, side="short", verdict_n=None, watch_only=True,
               sentinel=".block_shorts_main")
    sims = [_t(2.0, side="short", mode="paper", opened_off=i * 10)
            for i in range(5)]
    r = adj.grade_side_line(sims + [_t(1.0, side="short")], cfg,
                            bot_dir=str(tmp_path))
    assert r["n_trades"] == 1
    assert r["status"] == adj.WATCH


# ── Bot-side dormant gate ──────────────────────────────────────────────

def test_bot_longs_blocked_helper(tmp_path):
    from bot import _longs_blocked
    assert _longs_blocked("main", bot_dir=str(tmp_path)) is False
    (tmp_path / ".block_longs_main").write_text("x\n")
    assert _longs_blocked("main", bot_dir=str(tmp_path)) is True
    assert _longs_blocked("5m_mean_revert", bot_dir=str(tmp_path)) is False
