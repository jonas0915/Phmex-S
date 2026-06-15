"""Tests for the ST2.0 recursive improvement lab (scripts/st2_lab)."""
import os
import sys

import pytest

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import config as C            # noqa: E402
from st2_lab.safe_exec import compile_filter, Rejection  # noqa: E402
from st2_lab.evaluator import evaluate     # noqa: E402
from st2_lab.proposer import propose, FILTER_LIBRARY  # noqa: E402
from st2_lab import champion as champ_store  # noqa: E402


# ── safe_exec ────────────────────────────────────────────────────────────
def test_safe_exec_accepts_valid_filter():
    f = compile_filter("imbalance >= 0.35 and not divergence_bullish")
    assert f({"imbalance": 0.4, "divergence_bullish": False}) is True
    assert f({"imbalance": 0.2, "divergence_bullish": False}) is False
    assert f({"imbalance": 0.4, "divergence_bullish": True}) is False


def test_safe_exec_arithmetic_and_compare():
    f = compile_filter("buy_ratio - 0.1 >= 0.6")
    assert f({"buy_ratio": 0.75}) is True
    assert f({"buy_ratio": 0.65}) is False


@pytest.mark.parametrize("bad", [
    "__import__('os').system('echo hi')",   # call + dunder
    "open('x')",                             # call
    "imbalance.__class__",                   # attribute
    "ctx['imbalance']",                      # subscript + unknown name
    "[x for x in range(3)]",                 # comprehension/call
    "lambda: 1",                             # lambda
    "unknown_name > 1",                      # unknown name
    "'string'",                              # non-numeric constant
    "",                                      # empty
])
def test_safe_exec_rejects_unsafe(bad):
    with pytest.raises(Rejection):
        compile_filter(bad)


def test_safe_exec_no_builtins_reachable():
    # division by zero must not raise out of the filter (defanged to 0)
    f = compile_filter("imbalance / 0 >= 1")
    assert f({"imbalance": 5}) is False


# ── evaluator ─────────────────────────────────────────────────────────────
def _rec(ts, price, imb=0.40, br=0.70, tc=20, **kw):
    base = {"ts": ts, "symbol": "X/USDT:USDT", "price": price, "imbalance": imb,
            "buy_ratio": br, "trade_count": tc, "cvd_slope": 0.0,
            "large_trade_bias": 0.0, "divergence_bullish": False,
            "divergence_bearish": False, "hour": 12, "spread_pct": 0.01}
    base.update(kw)
    return base


def test_evaluator_take_profit_win():
    # entry at 100; price drops to 97 (< tp 98.4) -> TP win
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(100, 97.0)]}
    m = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    assert m.trades == 1 and m.wins == 1
    # short move to tp 98.4 = 1.6% * notional(100) - fee(0.04) = 1.56
    assert m.net == pytest.approx(1.56, abs=0.01)


def test_evaluator_stop_loss_loss():
    # entry at 100; price rises to 103 (>= sl 101.2) -> SL loss
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(100, 103.0)]}
    m = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    assert m.trades == 1 and m.losses == 1
    assert m.net == pytest.approx(-1.24, abs=0.01)  # -1.2% * 100 - 0.04


def test_evaluator_time_hold_exit():
    # price stays in band; exit at hold_secs (900) at the then-current price
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(500, 100.1), _rec(901, 99.5)]}
    m = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    assert m.trades == 1
    assert m.net == pytest.approx(0.5 - 0.04, abs=0.01)  # (100-99.5)/100*100 - fee


def test_evaluator_no_entry_when_gates_fail():
    # every record fails the imbalance gate -> never enters
    data = {"X/USDT:USDT": [_rec(0, 100.0, imb=0.1), _rec(100, 97.0, imb=0.1)]}
    m = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    assert m.trades == 0


def test_evaluator_filter_vetoes_entry():
    cfg = {"params": dict(C.DEFAULT_CHAMPION["params"]),
           "filters": [{"id": "t", "code": "not divergence_bullish", "hash": "t"}]}
    # filter vetoes on every record -> never enters
    data = {"X/USDT:USDT": [_rec(0, 100.0, divergence_bullish=True),
                            _rec(100, 97.0, divergence_bullish=True)]}
    m = evaluate(cfg, data, {"min_trades_eval": 1})
    assert m.trades == 0  # filter blocked the entry


# ── proposer ────────────────────────────────────────────────────────────
def test_proposer_candidates_valid_and_bounded():
    champ = {"params": dict(C.DEFAULT_CHAMPION["params"]), "filters": []}
    cands = propose(champ, k=6, iteration=0)
    assert 0 < len(cands) <= 6
    for c in cands:
        assert "_change" in c
        for name, (lo, hi, _) in C.PARAM_BOUNDS.items():
            assert lo <= c["params"][name] <= hi
        for f in c.get("filters", []):
            compile_filter(f["code"])  # every proposed filter must compile


def test_proposer_rotation_differs_by_iteration():
    champ = {"params": dict(C.DEFAULT_CHAMPION["params"]), "filters": []}
    a = [c["_change"] for c in propose(champ, 3, iteration=0)]
    b = [c["_change"] for c in propose(champ, 3, iteration=5)]
    assert a != b


def test_filter_library_all_compile():
    for code in FILTER_LIBRARY:
        compile_filter(code)


# ── champion store ────────────────────────────────────────────────────────
def test_champion_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LAB_DIR", str(tmp_path))
    monkeypatch.setattr(C, "CHAMPION_FILE", str(tmp_path / "champion.json"))
    champ = champ_store.load()           # seeds default
    assert champ["params"]["imb_min"] == 0.30
    champ["params"]["imb_min"] = 0.35
    champ_store.append_lineage(champ, "imb_min 0.30 -> 0.35", {"net": 1.0, "trades": 20, "wr": 0.5}, 1)
    champ_store.save(champ)
    reloaded = champ_store.load()
    assert reloaded["params"]["imb_min"] == 0.35
    assert reloaded["lineage"][-1]["change"] == "imb_min 0.30 -> 0.35"
