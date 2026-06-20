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
from st2_lab import fills as fills_mod        # noqa: E402
from st2_lab import diagnostics               # noqa: E402
from st2_lab.evaluator import evaluate_with_trades  # noqa: E402
from st2_lab import dataset as ds               # noqa: E402
from st2_lab import real_trades                  # noqa: E402
from st2_lab import loop                          # noqa: E402
import json as _json                             # noqa: E402


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


def test_evaluator_symbol_restriction():
    # two symbols both with valid entries; restricting to ETH counts ETH only
    eth = [dict(_rec(0, 100.0), symbol="ETH/USDT:USDT"),
           dict(_rec(100, 97.0), symbol="ETH/USDT:USDT")]
    btc = [dict(_rec(0, 100.0), symbol="BTC/USDT:USDT"),
           dict(_rec(100, 97.0), symbol="BTC/USDT:USDT")]
    data = {"ETH/USDT:USDT": eth, "BTC/USDT:USDT": btc}
    allm = evaluate({"params": dict(C.DEFAULT_CHAMPION["params"]), "symbols": None},
                    data, {"min_trades_eval": 1})
    ethm = evaluate({"params": dict(C.DEFAULT_CHAMPION["params"]),
                     "symbols": ["ETH/USDT:USDT"]}, data, {"min_trades_eval": 1})
    assert allm.trades == 2 and ethm.trades == 1


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


# ── failure diagnostics ────────────────────────────────────────────────────
def _trade(net, **feat):
    base = {"imbalance": 0.4, "buy_ratio": 0.7, "trade_count": 20, "cvd_slope": 0.0,
            "large_trade_bias": 0.0, "spread_pct": 0.01, "divergence_bullish": False,
            "divergence_bearish": False, "hour": 12}
    base.update(feat)
    base["net"] = net
    return base


def test_diagnostics_finds_losing_cluster():
    # winners have low cvd_slope, losers have high cvd_slope -> propose cvd_slope <= cut
    trades = ([_trade(+1.0, cvd_slope=0.2) for _ in range(30)] +
              [_trade(-1.0, cvd_slope=0.9) for _ in range(15)])
    cands = diagnostics.analyze_failures(trades)
    assert cands, "should find a loss cluster"
    top = cands[0]
    assert top["feature"] == "cvd_slope"
    assert top["code"].startswith("cvd_slope <=")
    assert top["improvement"] > 0
    compile_filter(top["code"])  # must be safe


def test_diagnostics_finds_bool_cluster():
    trades = ([_trade(+1.0, divergence_bullish=False) for _ in range(30)] +
              [_trade(-1.0, divergence_bullish=True) for _ in range(15)])
    codes = [c["code"] for c in diagnostics.analyze_failures(trades)]
    assert "not divergence_bullish" in codes


def test_diagnostics_too_few_trades_returns_empty():
    assert diagnostics.analyze_failures([_trade(1.0) for _ in range(5)]) == []


def test_diagnostics_no_cluster_when_uniform():
    # net unrelated to features -> nothing worth vetoing
    trades = [_trade((-1.0 if i % 2 else 1.0)) for i in range(60)]
    # all features identical, so no split separates winners/losers
    assert diagnostics.analyze_failures(trades) == []


def test_evaluate_with_trades_returns_records():
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(100, 97.0)]}
    m, trades = evaluate_with_trades(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    assert m.trades == 1 and len(trades) == 1
    assert "cvd_slope" in trades[0] and "net" in trades[0]


# ── chronological train/test split ─────────────────────────────────────────
def test_chronological_split_no_lookahead():
    data = {
        "A/USDT:USDT": [_rec(0, 1), _rec(10, 1), _rec(20, 1), _rec(30, 1)],
        "B/USDT:USDT": [_rec(5, 1), _rec(15, 1)],
    }
    train, test = ds.chronological_split(data, train_frac=0.7)
    train_ts = [r["ts"] for recs in train.values() for r in recs]
    test_ts = [r["ts"] for recs in test.values() for r in recs]
    assert train_ts and test_ts
    assert max(train_ts) <= min(test_ts)        # strictly chronological, no leak
    assert len(train_ts) + len(test_ts) == 6    # no records lost


def test_chronological_split_empty():
    train, test = ds.chronological_split({}, 0.7)
    assert train == {} and test == {}


# ── real-trade ingestion ───────────────────────────────────────────────────
def _live_trade(net, **flow):
    f = {"buy_ratio": 0.7, "cvd_slope": -0.5, "divergence": "bearish",
         "large_trade_bias": -0.1, "trade_count": 100}
    f.update(flow)
    return {"mode": "live", "net_pnl": net, "pnl_usdt": net,
            "entry_snapshot": {"ob": {"imbalance": 0.4, "spread_pct": 0.01},
                               "flow": f, "ts": 1781551344}}


def test_load_real_trades_filters_live_and_shape(tmp_path):
    state = tmp_path / "trading_state_ST2.0.json"
    paper = dict(_live_trade(1.0)); paper["mode"] = "paper"
    no_snap = {"mode": "live", "net_pnl": 0.5}  # no entry_snapshot -> skipped
    state.write_text(_json.dumps({"closed_trades": [_live_trade(1.0), paper, no_snap,
                                                    _live_trade(-0.6)]}))
    recs = real_trades.load_real_trades(str(state))
    assert len(recs) == 2  # only the 2 live trades WITH entry_snapshot
    r = recs[0]
    assert r["imbalance"] == 0.4 and r["buy_ratio"] == 0.7
    assert r["divergence_bearish"] is True and r["divergence_bullish"] is False
    assert r["net"] == 1.0


def test_real_summary():
    recs = [{"net": 1.0}, {"net": -0.6}, {"net": 0.4}]
    s = real_trades.real_summary(recs)
    assert s["trades"] == 3 and s["wins"] == 2 and s["losses"] == 1
    assert s["net"] == pytest.approx(0.8, abs=1e-4)
    assert s["expectancy"] == pytest.approx(0.8 / 3, abs=1e-3)  # code rounds to 4dp


def test_load_real_trades_missing_file():
    assert real_trades.load_real_trades("/nonexistent/x.json") == []


def test_real_records_feed_diagnostics():
    # real records are the same shape diagnostics consume
    recs = ([_rec_to_diag(+1.0, cvd_slope=-0.8) for _ in range(30)] +
            [_rec_to_diag(-1.0, cvd_slope=0.8) for _ in range(15)])
    cands = diagnostics.analyze_failures(recs)
    assert cands and cands[0]["feature"] == "cvd_slope"


def _rec_to_diag(net, **f):
    base = {"imbalance": 0.4, "buy_ratio": 0.7, "trade_count": 100, "cvd_slope": 0.0,
            "large_trade_bias": 0.0, "spread_pct": 0.01, "divergence_bullish": False,
            "divergence_bearish": False, "hour": 12, "net": net}
    base.update(f)
    return base


# ── champion store ────────────────────────────────────────────────────────
# ── expectancy / fill-robust ranking ──────────────────────────────────────
def test_expectancy_computed():
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(100, 97.0)]}
    m = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    assert m.expectancy == pytest.approx(m.net / m.trades, abs=1e-6)


def test_score_is_expectancy_not_total_net():
    # A: 1 trade, net +2 -> expectancy +2.  B: 2 trades, net +3 -> expectancy +1.5.
    # Ranking by total net would prefer B; we must prefer A (higher per-trade edge).
    a = C.Metrics(trades=1, net=2.0, expectancy=2.0, rankable=True)
    b = C.Metrics(trades=2, net=3.0, expectancy=1.5, rankable=True)
    assert a.score() > b.score()


def test_fill_adjusted_net():
    m = C.Metrics(net=10.0)
    assert m.fill_adjusted_net(0.43) == pytest.approx(4.3, abs=1e-6)


# ── fill-rate analysis (real-log parsing + dedup) ──────────────────────────
def test_measured_fill_stats_dedup(tmp_path):
    log = tmp_path / "bot.log"
    fill = ("2026-06-15 04:05:59 [INFO] [SLOT LIVE] ST2.0 ENTRY SHORT ETH/USDT:USDT "
            "| Fill: 1718.88 | Margin: $6.88 | ST2.0 absorption short (imb=0.53 br=1.00 tc=10)")
    miss = ("2026-06-15 05:14:21 [INFO] [SLOT LIVE] ST2.0 ZEC/USDT:USDT short "
            "— no fill (PostOnly miss), skipping")
    fill2 = fill.replace("ETH", "BTC")
    # each event written twice (the bot's color+plain duplication)
    log.write_text("\n".join([fill, fill, miss, miss, fill2, fill2]) + "\n")
    s = fills_mod.measured_fill_stats(str(log))
    assert s["fills"] == 2 and s["misses"] == 1   # deduped
    assert s["attempts"] == 3
    assert s["rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["by_symbol"]["ETH/USDT:USDT"]["fills"] == 1
    assert len(s["fill_conditions"]) == 2
    assert s["fill_conditions"][0]["imb"] == 0.53


def test_measured_fill_stats_missing_log():
    s = fills_mod.measured_fill_stats("/nonexistent/bot.log")
    assert s["attempts"] == 0 and s["rate"] == 0.0


def test_champion_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LAB_DIR", str(tmp_path))
    monkeypatch.setattr(C, "CHAMPION_FILE", str(tmp_path / "champion.json"))
    champ = champ_store.load()           # seeds default (mirrors live baseline)
    assert champ["params"]["imb_min"] == 0.35
    champ["params"]["imb_min"] = 0.40
    champ_store.append_lineage(champ, "imb_min 0.35 -> 0.40", {"net": 1.0, "trades": 20, "wr": 0.5}, 1)
    champ_store.save(champ)
    reloaded = champ_store.load()
    assert reloaded["params"]["imb_min"] == 0.40
    assert reloaded["lineage"][-1]["change"] == "imb_min 0.35 -> 0.40"


# ── recursive learning: per-run persistence + history ───────────────────────
# Regression for the amnesiac loop: save() was only reached inside the accept
# branch, so a no-accept run (the steady state) persisted NOTHING — no history,
# no advancing counter, frozen exploration, perpetually empty lineage.
def _isolate_lab(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LAB_DIR", str(tmp_path))
    monkeypatch.setattr(C, "CHAMPION_FILE", str(tmp_path / "champion.json"))
    monkeypatch.setattr(C, "PROPOSALS_DIR", str(tmp_path / "proposals"))
    # keep the loop off real live files (deterministic, no side effects)
    monkeypatch.setattr(loop.real_trades, "load_real_trades", lambda *a, **k: [])
    monkeypatch.setattr(loop.fills_mod, "measured_fill_stats",
                        lambda *a, **k: {"rate": 0.0, "fills": 0, "misses": 0,
                                         "attempts": 0, "by_symbol": {}, "fill_conditions": []})
    monkeypatch.setattr(loop.fills_mod, "format_report", lambda *a, **k: "fill: n/a")


def test_default_champion_has_learning_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "LAB_DIR", str(tmp_path))
    monkeypatch.setattr(C, "CHAMPION_FILE", str(tmp_path / "champion.json"))
    champ = champ_store.load()  # seeds default
    assert champ["run_count"] == 0
    assert champ["history"] == []


def test_append_history_bounded():
    champ = {"history": []}
    entries = [{"run": i, "change": "x", "hash": str(i), "train_exp": 0.0,
                "test_exp": 0.0, "accepted": False} for i in range(C.HISTORY_CAP + 25)]
    champ_store.append_history(champ, entries)
    assert len(champ["history"]) == C.HISTORY_CAP
    assert champ["history"][-1]["run"] == C.HISTORY_CAP + 24   # newest retained
    assert champ["history"][0]["run"] == 25                    # oldest dropped


def test_loop_persists_run_count_and_history_without_acceptance(tmp_path, monkeypatch):
    _isolate_lab(tmp_path, monkeypatch)
    monkeypatch.setattr(loop, "_improved", lambda *a, **k: False)  # force no acceptance
    data = {"X/USDT:USDT": [_rec(i * 100, 100.0) for i in range(6)]}

    r1 = loop.run_iteration(by_symbol=data, dry_run=False)
    champ = champ_store.load()
    assert champ["run_count"] == 1, "run_count must advance even with no acceptance"
    assert champ["lineage"] == []                      # nothing accepted
    assert len(champ["history"]) >= 1                  # but attempts ARE remembered
    assert all("accepted" in h and "change" in h for h in champ["history"])
    assert r1["run_count"] == 1

    r2 = loop.run_iteration(by_symbol=data, dry_run=False)
    champ2 = champ_store.load()
    assert champ2["run_count"] == 2                    # advances again
    assert len(champ2["history"]) >= len(champ["history"])  # memory accumulates
    assert champ2["metrics"] != {}                     # current metrics refreshed each run
    assert r2["run_count"] == 2


def test_loop_dry_run_does_not_advance_state(tmp_path, monkeypatch):
    _isolate_lab(tmp_path, monkeypatch)
    monkeypatch.setattr(loop, "_improved", lambda *a, **k: False)
    data = {"X/USDT:USDT": [_rec(i * 100, 100.0) for i in range(6)]}
    loop.run_iteration(by_symbol=data, dry_run=True)
    champ = champ_store.load()  # only the load()-seed default should exist
    assert champ["run_count"] == 0 and champ["history"] == []


# ── learn-from-mistakes: skip tried dead-ends, escalate, re-explore on new data ──
from st2_lab.proposer import config_hash, _single_step_candidates  # noqa: E402


def test_config_hash_order_independent():
    from st2_lab.proposer import _filter_entry as fe
    a = {"params": {"x": 1}, "filters": [fe("cvd_slope <= 0.5"), fe("buy_ratio <= 0.85")]}
    b = {"params": {"x": 1}, "filters": [fe("buy_ratio <= 0.85"), fe("cvd_slope <= 0.5")]}
    assert config_hash(a) == config_hash(b)


def test_proposer_skips_tried_configs():
    champ = {"params": dict(C.DEFAULT_CHAMPION["params"]), "filters": []}
    tried = {config_hash(c) for c in _single_step_candidates(champ)}  # mark ALL singles tried
    cands = propose(champ, k=6, iteration=0, tried=tried)
    assert cands, "must still propose (compound) candidates, not go inert"
    assert all(config_hash(c) not in tried for c in cands)  # never re-test a dead-end


def test_proposer_escalates_to_compound_when_exhausted():
    champ = {"params": dict(C.DEFAULT_CHAMPION["params"]), "filters": []}
    tried = {config_hash(c) for c in _single_step_candidates(champ)}
    cands = propose(champ, k=4, iteration=0, tried=tried)
    assert cands
    assert any(" + " in c["_change"] for c in cands)  # two-change (compound) candidate
    # compound candidates remain valid: params in bounds, filters compile
    for c in cands:
        for name, (lo, hi, _) in C.PARAM_BOUNDS.items():
            assert lo <= c["params"][name] <= hi
        for f in c.get("filters", []):
            compile_filter(f["code"])


def test_loop_no_repeat_within_fixed_dataset(tmp_path, monkeypatch):
    _isolate_lab(tmp_path, monkeypatch)
    monkeypatch.setattr(loop, "_improved", lambda *a, **k: False)
    data = {"X/USDT:USDT": [_rec(i * 100, 100.0) for i in range(6)]}  # fixed epoch
    loop.run_iteration(by_symbol=data, dry_run=False)
    loop.run_iteration(by_symbol=data, dry_run=False)  # same epoch -> tried persists
    champ = champ_store.load()
    h0 = {e["hash"] for e in champ["history"] if e["run"] == 0}
    h1 = {e["hash"] for e in champ["history"] if e["run"] == 1}
    assert h0 and h1
    assert h0.isdisjoint(h1), "run 2 must not re-test configs already tried in run 1"
    assert len(champ["tried"]) >= len(h0 | h1)


def test_loop_resets_tried_on_data_growth(tmp_path, monkeypatch):
    _isolate_lab(tmp_path, monkeypatch)
    monkeypatch.setattr(loop, "_improved", lambda *a, **k: False)
    d1 = {"X/USDT:USDT": [_rec(i * 100, 100.0) for i in range(6)]}          # max ts 500
    loop.run_iteration(by_symbol=d1, dry_run=False)
    c1 = champ_store.load()
    assert c1["data_epoch"] == 500
    h_run0 = {e["hash"] for e in c1["history"] if e["run"] == 0}
    d2 = {"X/USDT:USDT": [_rec(10000 + i * 100, 100.0) for i in range(6)]}  # max ts 10500
    loop.run_iteration(by_symbol=d2, dry_run=False)
    c2 = champ_store.load()
    assert c2["data_epoch"] == 10500                  # epoch advanced
    h_run1 = {e["hash"] for e in c2["history"] if e["run"] == 1}
    assert h_run0 & h_run1, "growing data must reset tried so configs get re-explored"


# ── adverse-selection maker-fill model (research: arxiv 2407.16527) ────────
def test_adverse_fill_drops_favorable_unfilled_short():
    # Signal, then price immediately DROPS (favorable for a short). The naive 100%-fill
    # replay books a (fake) TP win; the adverse model DROPS it — a resting sell above a
    # falling market never gets lifted, so the favorable case is correctly never filled.
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(100, 97.0, imb=0.1),
                            _rec(200, 96.0, imb=0.1)]}
    naive = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    adv = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1},
                   adverse={"enabled": True, "fill_window_snaps": 1})
    assert naive.trades == 1 and naive.wins == 1   # naive keeps the missed favorable
    assert adv.trades == 0                          # adverse: no fill -> correctly dropped


def test_adverse_fill_keeps_adverse_selected_short():
    # Signal, then price RISES into the offer (adverse fill) and hits SL. Both models
    # take the trade; it loses — short filled into a rising market.
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(100, 103.0, imb=0.1),
                            _rec(200, 104.0, imb=0.1)]}
    adv = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1},
                   adverse={"enabled": True, "fill_window_snaps": 1})
    assert adv.trades == 1 and adv.losses == 1


def test_adverse_fill_default_off_matches_naive():
    # adverse=None (default) must be byte-identical to the naive replay (no regression).
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(100, 103.0), _rec(200, 99.0)]}
    base = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    same = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1},
                    adverse={"enabled": False})
    assert base.trades == same.trades and base.net == same.net


def test_loop_ranks_champion_on_adverse_fills_not_naive(tmp_path, monkeypatch):
    # Phase 1: the loop must rank on REALISTIC (adverse) fills, not the 100%-fill
    # fiction. On a favorable-move short, naive books a fake win while the adverse
    # model drops the unfilled signal. run_iteration's reported champion must reflect
    # the adverse evaluation (net 0, no fill), not the naive win.
    _isolate_lab(tmp_path, monkeypatch)
    data = {"X/USDT:USDT": [_rec(0, 100.0), _rec(100, 97.0, imb=0.1),
                            _rec(200, 96.0, imb=0.1)]}
    naive = evaluate(C.DEFAULT_CHAMPION, data, {"min_trades_eval": 1})
    assert naive.trades == 1 and naive.net > 0      # sanity: naive books the fake win
    r = loop.run_iteration(by_symbol=data, dry_run=True)
    assert r["champion_net"] == 0.0, "loop must rank the champion on adverse fills (dropped), not naive"
    assert r["champion_trades"] == 0                 # observable: adverse dropped the fill
