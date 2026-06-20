"""TDD for the Phase-1 walk-forward + deflated-Sharpe acceptance gate (loop._robustness_ok).

This is the guard that would have killed the documented vol-fade artifact ("looked
OOS +0.26% on ONE split; full-sample -0.187%"): a candidate must win across a
MAJORITY of walk-forward windows AND clear a deflated-Sharpe bar that accounts for
how many candidates were tried.
"""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import loop  # noqa: E402
from st2_lab import config as C  # noqa: E402


def _rec(ts, price, imb=0.40, br=0.70, tc=20, **kw):
    base = {"ts": ts, "symbol": "X/USDT:USDT", "price": price, "imbalance": imb,
            "buy_ratio": br, "trade_count": tc, "cvd_slope": 0.0,
            "large_trade_bias": 0.0, "divergence_bullish": False,
            "divergence_bearish": False, "hour": 12, "spread_pct": 0.01}
    base.update(kw)
    return base


def test_wf_eval_returns_window_exps_sharpe_nobs():
    # 80 snapshots over the timeline; the champion fires repeatedly so several
    # walk-forward windows accumulate trades.
    recs = [_rec(i * 100, 100.0 + (i % 7) * 0.3) for i in range(80)]
    data = {"X/USDT:USDT": recs}
    window_exps, sharpe, n_obs = loop._wf_eval(
        C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1}, n_windows=4, embargo_secs=0)
    assert len(window_exps) == 4
    assert isinstance(sharpe, float)
    assert isinstance(n_obs, int) and n_obs >= 0
    # at least one window should have produced a rankable expectancy on this data
    assert any(e is not None for e in window_exps)


def test_rejects_regime_luck_one_winning_window():
    # Wins big on one window, negative on the other three → not robust.
    ok = loop._robustness_ok([0.6, -0.3, -0.2, -0.1], champ_mean_oos=0.0,
                             cand_sharpe=0.5, n_obs=300, n_trials=5,
                             var_trial_sharpes=0.02)
    assert ok is False


def test_accepts_consistent_winner_with_few_trials():
    ok = loop._robustness_ok([0.20, 0.30, 0.25, 0.40], champ_mean_oos=0.0,
                             cand_sharpe=0.5, n_obs=300, n_trials=5,
                             var_trial_sharpes=0.02)
    assert ok is True


def test_rejected_by_deflated_sharpe_under_many_trials():
    # Same consistently-positive windows, but 5000 trials + wide trial-Sharpe spread
    # raise the selection bar above the candidate's Sharpe → deflated-Sharpe fails.
    ok = loop._robustness_ok([0.20, 0.30, 0.25, 0.40], champ_mean_oos=0.0,
                             cand_sharpe=0.5, n_obs=300, n_trials=5000,
                             var_trial_sharpes=0.25)
    assert ok is False


def test_rejects_when_not_beating_champion_by_margin():
    # Mean OOS ~0.05 barely ties the champion's 0.05 — inside the noise floor.
    ok = loop._robustness_ok([0.05, 0.06, 0.05, 0.04], champ_mean_oos=0.05,
                             cand_sharpe=0.5, n_obs=300, n_trials=5,
                             var_trial_sharpes=0.02)
    assert ok is False


def test_rejects_unrankable_all_none():
    ok = loop._robustness_ok([None, None, None], champ_mean_oos=0.0,
                             cand_sharpe=0.5, n_obs=300, n_trials=5,
                             var_trial_sharpes=0.02)
    assert ok is False
