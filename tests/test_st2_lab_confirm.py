"""TDD for scripts/st2_lab/confirm.py — self-closing forward adjudication."""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import confirm as CF      # noqa: E402

LIVE = {"params": {"imb_min": 0.30, "br_min": 0.60, "min_trades": 15,
                   "hold_secs": 900, "sl_pct": 1.2, "tp_pct": 1.6}, "filters": []}


def _cfg(imb=0.30, br=0.60, mt=15, sl=1.2, tp=1.6, hold=900, filters=None):
    return {"params": {"imb_min": imb, "br_min": br, "min_trades": mt,
                       "hold_secs": hold, "sl_pct": sl, "tp_pct": tp},
            "filters": filters or [], "symbols": None}


def test_truth_eligible_stricter_entry_same_exits_rawfilter():
    cfg = _cfg(imb=0.35, filters=[{"code": "cvd_slope <= -0.3"}])  # stricter + raw filter
    assert CF.truth_eligible(cfg, LIVE) is True
    assert CF.classify_kind(cfg, LIVE) == "filter"


def test_truth_ineligible_when_entry_looser():
    cfg = _cfg(imb=0.25)               # looser than live 0.30 -> admits setups not in real data
    assert CF.truth_eligible(cfg, LIVE) is False
    assert CF.classify_kind(cfg, LIVE) == "base"


def test_truth_ineligible_when_exits_differ():
    cfg = _cfg(tp=2.0)                 # different exit -> realized net can't be reused
    assert CF.truth_eligible(cfg, LIVE) is False


def test_truth_ineligible_engineered_feature_filter():
    cfg = _cfg(filters=[{"code": "imb_mean >= 0.4"}])  # engineered feature absent on real recs
    assert CF.truth_eligible(cfg, LIVE) is False


def test_truth_ineligible_without_live_config():
    cfg = _cfg(imb=0.35)
    assert CF.truth_eligible(cfg, None) is False
    assert CF.classify_kind(cfg, None) == "base"


def test_register_if_survivor_adds_and_dedups():
    champ = {"live_config": LIVE}
    cfg = _cfg(imb=0.35)
    assert CF.register_if_survivor(champ, cfg, registered_ts=1000, run_count=3) is True
    assert CF.register_if_survivor(champ, cfg, registered_ts=2000, run_count=4) is False  # dup hash
    reg = champ["confirm_registry"]
    assert len(reg) == 1
    h = reg[0]
    assert h["kind"] == "filter"
    assert h["registered_ts"] == 1000 and h["registered_run"] == 3
    assert h["verdict"] == "accruing"
    assert h["screen"]["status"] == "accruing" and h["truth"]["status"] == "accruing"


def test_ensure_live_entry_idempotent():
    champ = {"live_config": LIVE}
    CF.ensure_live_entry(champ, registered_ts=500)
    CF.ensure_live_entry(champ, registered_ts=999)
    live = [h for h in champ["confirm_registry"] if h["id"] == "LIVE"]
    assert len(live) == 1
    assert live[0]["truth"]["applicable"] is True   # LIVE is always TRUTH-applicable


def _stream(symbol, n, start_ts, price0=100.0, drift=0.0, imb=0.4, br=0.7, tc=20):
    return {symbol: [{"ts": start_ts + i * 75, "symbol": symbol,
                      "price": price0 + drift * i, "imbalance": imb, "spread_pct": 0.05,
                      "buy_ratio": br, "trade_count": tc, "cvd_slope": -0.5,
                      "large_trade_bias": 0.0, "divergence_bullish": False,
                      "divergence_bearish": False, "hour": 12} for i in range(n)]}


def _loop_cfg(**kw):
    base = {"wf_windows": 3, "wf_embargo_secs": 0, "wf_min_trades": 1,
            "dsr_min": 0.0, "screen_min_trades": 3, "confirm_sample": 5}
    base.update(kw); return base


def test_screen_uses_only_forward_rows():
    # registered_ts at 5000: rows before are search data and must be ignored
    by = _stream("ETH/USDT:USDT", 200, start_ts=0)
    hyp = CF._new_hypothesis("h1", {"params": {"imb_min": 0.30, "br_min": 0.60,
        "min_trades": 15, "hold_secs": 900, "sl_pct": 1.2, "tp_pct": 1.6},
        "filters": [], "symbols": None}, "filter", registered_ts=5000, run_count=1,
        truth_applicable=True)
    s = CF.screen_verdict(hyp, by, _loop_cfg())
    # every trade the screen scored must come from ts > 5000 (no leakage from search window)
    assert s["status"] in ("accruing", "pass", "fail")
    assert s["updated_ts"] >= 5000
    assert s["updated_ts"] == 200 * 75 - 75    # last forward row's ts (14925) — boundary pinned
    assert s["trades"] > 0                       # post-registration rows produced evaluable signal


def test_screen_accruing_below_threshold():
    by = _stream("ETH/USDT:USDT", 6, start_ts=0)   # too few forward trades
    hyp = CF._new_hypothesis("h2", {"params": {"imb_min": 0.30, "br_min": 0.60,
        "min_trades": 15, "hold_secs": 900, "sl_pct": 1.2, "tp_pct": 1.6},
        "filters": [], "symbols": None}, "filter", registered_ts=0, run_count=1,
        truth_applicable=True)
    s = CF.screen_verdict(hyp, by, _loop_cfg(screen_min_trades=999))
    assert s["status"] == "accruing"


def _real(imb, br, net, tc=20, cvd=-0.5):
    return {"imbalance": imb, "spread_pct": 0.05, "buy_ratio": br, "trade_count": tc,
            "cvd_slope": cvd, "large_trade_bias": 0.0, "divergence_bullish": False,
            "divergence_bearish": False, "hour": 12, "net": net}


def test_truth_live_uses_all_real_trades():
    champ = {"live_config": LIVE}
    CF.ensure_live_entry(champ, registered_ts=0)
    hyp = champ["confirm_registry"][0]
    reals = [_real(0.4, 0.7, +1.0), _real(0.4, 0.7, -0.5), _real(0.4, 0.7, +2.0)]
    t = CF.truth_verdict(hyp, reals, LIVE, _loop_cfg(confirm_sample=2))
    assert t["applicable"] is True
    assert t["kept"] == 3 and t["dropped"] == 0
    assert abs(t["expectancy"] - (1.0 - 0.5 + 2.0) / 3) < 1e-9


def test_truth_filter_judges_kept_subset_only():
    # candidate adds a raw filter cvd_slope <= -0.4; only trades passing it are kept
    cfg = _cfg(imb=0.35, filters=[{"code": "cvd_slope <= -0.4"}])
    hyp = CF._new_hypothesis(CF.proposer.config_hash(cfg), cfg, "filter",
                             registered_ts=0, run_count=1, truth_applicable=True)
    reals = [_real(0.4, 0.7, +3.0, cvd=-0.5),   # kept (cvd -0.5 <= -0.4)
             _real(0.4, 0.7, -9.0, cvd=-0.1),   # dropped (cvd -0.1 > -0.4)
             _real(0.4, 0.7, +1.0, cvd=-0.6)]   # kept
    t = CF.truth_verdict(hyp, reals, LIVE, _loop_cfg(confirm_sample=2))
    assert t["kept"] == 2 and t["dropped"] == 1
    assert abs(t["expectancy"] - (3.0 + 1.0) / 2) < 1e-9   # the -9.0 loser is excluded


def test_truth_accruing_below_confirm_sample():
    champ = {"live_config": LIVE}; CF.ensure_live_entry(champ, 0)
    hyp = champ["confirm_registry"][0]
    t = CF.truth_verdict(hyp, [_real(0.4, 0.7, +1.0)], LIVE, _loop_cfg(confirm_sample=5))
    assert t["status"] == "accruing"


def test_truth_confirm_when_ci_above_zero():
    champ = {"live_config": LIVE}; CF.ensure_live_entry(champ, 0)
    hyp = champ["confirm_registry"][0]
    reals = [_real(0.4, 0.7, +1.0) for _ in range(40)]   # all winners -> CI lower bound > 0
    t = CF.truth_verdict(hyp, reals, LIVE, _loop_cfg(confirm_sample=10))
    assert t["status"] == "confirm"
    assert t["ci"][0] > 0


def test_truth_reject_when_ci_below_zero():
    champ = {"live_config": LIVE}; CF.ensure_live_entry(champ, 0)
    hyp = champ["confirm_registry"][0]
    reals = [_real(0.4, 0.7, -1.0) for _ in range(40)]   # all losers -> CI upper bound < 0
    t = CF.truth_verdict(hyp, reals, LIVE, _loop_cfg(confirm_sample=10))
    assert t["status"] == "reject"
    assert t["ci"][1] < 0


def test_truth_inapplicable_for_base_candidate():
    cfg = _cfg(imb=0.25)   # looser -> base -> not TRUTH-judgeable
    hyp = CF._new_hypothesis("b1", cfg, "base", registered_ts=0, run_count=1,
                             truth_applicable=False)
    t = CF.truth_verdict(hyp, [_real(0.4, 0.7, +1.0) for _ in range(40)], LIVE, _loop_cfg())
    assert t["applicable"] is False
    assert t["status"] == "accruing"   # never closes on real fills


def test_tick_sets_verdict_and_returns_transition_once():
    champ = {"live_config": LIVE, "run_count": 1, "loop": _loop_cfg(confirm_sample=10)}
    CF.ensure_live_entry(champ, registered_ts=0)
    reals = [_real(0.4, 0.7, -1.0) for _ in range(40)]   # LIVE failing real confirmation
    by = {}                                              # no forward snapshots this fixture
    trans = CF.tick(champ, by, reals)
    live = [h for h in champ["confirm_registry"] if h["id"] == "LIVE"][0]
    assert live["verdict"] == "truth_reject"
    assert len(trans) == 1 and trans[0]["id"] == "LIVE" and trans[0]["alert"] is True
    # second identical tick emits NO new transition (dedup on unchanged verdict)
    assert CF.tick(champ, by, reals) == []


def test_tick_truth_authoritative_over_screen():
    champ = {"live_config": LIVE, "run_count": 1, "loop": _loop_cfg(confirm_sample=10)}
    CF.ensure_live_entry(champ, 0)
    reals = [_real(0.4, 0.7, +1.0) for _ in range(40)]
    CF.tick(champ, {}, reals)
    live = [h for h in champ["confirm_registry"] if h["id"] == "LIVE"][0]
    assert live["verdict"] == "truth_confirm"   # real-fill verdict wins
