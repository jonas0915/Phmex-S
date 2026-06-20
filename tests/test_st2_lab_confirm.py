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
