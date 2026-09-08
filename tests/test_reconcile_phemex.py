"""Reconciler matching + funding attribution (2026-09-07 funding/fee capture).

Phemex facts these tests pin (verified read-only 9/7):
  * fetch_my_trades interleaves 8h funding settlements with fills; funding rows
    carry info.tradeType == "4" / info.action == "13"; real fills tradeType == "1".
  * fetch_funding_history[].amount is positive = PAID, negative = RECEIVED, which
    matches risk_manager's net_pnl = gross - fees - funding with funding = paid.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reconcile_phemex as rp  # noqa: E402

SYM = "ETH/USDT:USDT"


def _fill(ts_s, side, price, amount, fee, trade_type="1", fid=None):
    return {
        "id": fid or f"{ts_s}:{side}",
        "timestamp": int(ts_s * 1000),
        "side": side,
        "price": price,
        "amount": amount,
        "fee": {"currency": "USDT", "cost": fee, "rate": 0.0006},
        "fees": [{"currency": "USDT", "cost": fee, "rate": 0.0006}],
        "info": {"tradeType": trade_type, "action": "13" if trade_type == "4" else "1"},
    }


def _trade(opened, closed, symbol=SYM, **kw):
    t = {"symbol": symbol, "opened_at": opened, "closed_at": closed, "side": "short",
         "pnl_usdt": 1.0, "fees_usdt": 0.05, "funding_usdt": 0.0, "net_pnl": 0.95}
    t.update(kw)
    return t


def test_is_funding_row_by_trade_type_or_action():
    assert rp.is_funding_row({"info": {"tradeType": "4"}})
    assert rp.is_funding_row({"info": {"action": "13"}})
    assert not rp.is_funding_row({"info": {"tradeType": "1", "action": "1"}})
    assert not rp.is_funding_row({})


def test_match_skips_funding_rows_and_sums_entry_plus_exit():
    t = _trade(1000.0, 5000.0)
    fills = [
        _fill(1001, "sell", 2451.0, 0.06, 0.0147),                 # entry
        _fill(3600, "sell", 2454.0, 0.06, -0.0017, trade_type="4"),  # funding settlement
        _fill(4990, "buy", 2452.0, 0.06, 0.0883),                  # exit fill
    ]
    entry, exit_, fee = rp.match_trade_to_fills(t, fills)
    assert [f["id"] for f in entry] == ["1001:sell"]
    assert [f["id"] for f in exit_] == ["4990:buy"]
    assert fee == pytest.approx(0.0147 + 0.0883)


def test_exit_window_reaches_300s_before_closed_at():
    # exchange_close rows are recorded by the sync loop up to a few minutes
    # AFTER the real fill (cycle can stretch to the 180s watchdog).
    t = _trade(1000.0, 5000.0)
    fills = [_fill(1001, "sell", 1.0, 1, 0.01), _fill(4750, "buy", 1.0, 1, 0.09)]
    entry, exit_, fee = rp.match_trade_to_fills(t, fills)
    assert len(exit_) == 1 and fee == pytest.approx(0.10)
    # ...but not 301s+ before
    fills2 = [_fill(1001, "sell", 1.0, 1, 0.01), _fill(4699, "buy", 1.0, 1, 0.09)]
    _, exit2, _ = rp.match_trade_to_fills(t, fills2)
    assert exit2 == []


def test_fills_claimed_once_across_consecutive_trades():
    # crumb closed at 10:03:41 then a real entry at 10:06 on the same symbol
    crumb = _trade(1000.0, 1000.5, exit_reason="min_margin_skip")
    real = _trade(1140.0, 5000.0)
    fills = [
        _fill(1000.2, "sell", 1.0, 1, 0.001, fid="crumb-entry"),
        _fill(1000.4, "buy", 1.0, 1, 0.006, fid="crumb-exit"),
        _fill(1140.1, "sell", 1.0, 1, 0.015, fid="real-entry"),
        _fill(4999.0, "buy", 1.0, 1, 0.088, fid="real-exit"),
    ]
    claimed = set()
    e1, x1, f1 = rp.match_trade_to_fills(crumb, fills, claimed)
    e2, x2, f2 = rp.match_trade_to_fills(real, fills, claimed)
    assert {f["id"] for f in e1 + x1} == {"crumb-entry", "crumb-exit"}
    assert {f["id"] for f in e2 + x2} == {"real-entry", "real-exit"}
    assert f1 == pytest.approx(0.007) and f2 == pytest.approx(0.103)


def test_attribute_funding_assigns_each_payment_once_and_signs_as_paid():
    partial = _trade(1000.0, 3000.0, exit_reason="partial_tp")
    runner = _trade(1000.0, 9000.0, exit_reason="take_profit")
    other_sym = _trade(1000.0, 9000.0, symbol="SOL/USDT:USDT")
    funding = [
        {"timestamp": 2000 * 1000, "symbol": SYM, "paid": -0.0017},   # received while full size
        {"timestamp": 8000 * 1000, "symbol": SYM, "paid": 0.0024},    # paid on the runner
        {"timestamp": 500 * 1000, "symbol": SYM, "paid": 9.9},        # before open: ignored
        {"timestamp": 9000 * 1000, "symbol": SYM, "paid": 0.001},     # exactly at close: included
        {"timestamp": 2000 * 1000, "symbol": "SOL/USDT:USDT", "paid": 0.5},
    ]
    out = rp.attribute_funding([runner, partial, other_sym], funding)
    assert out[rp.trade_key(partial)] == pytest.approx(-0.0017)
    assert out[rp.trade_key(runner)] == pytest.approx(0.0024 + 0.001)
    assert out[rp.trade_key(other_sym)] == pytest.approx(0.5)


def test_constants():
    assert rp.FEE_TOLERANCE_USDT == 0.01
    assert rp.FUNDING_TOLERANCE_USDT == 1e-6
    assert rp.EXIT_MATCH_BEFORE_SEC == 300


# ---------------------------------------------------------------------------
# Task 2: ledger discovery, funding fetch, per-file apply
# ---------------------------------------------------------------------------


def test_ledger_files_excludes_sidecars_and_archives(monkeypatch, tmp_path):
    for name in ["trading_state.json", "trading_state_5m_mean_revert.json",
                 "trading_state_5m_mean_revert_mode.json", "trading_state_5m_narrow_blocked.json",
                 "trading_state_v8_245trades.json", "trading_state_SR_BOUNCE_era1.json"]:
        (tmp_path / name).write_text("{}")
    monkeypatch.setattr(rp, "ROOT", tmp_path)
    monkeypatch.setattr(rp, "MAIN_STATE_FILE", tmp_path / "trading_state.json")
    files = rp.ledger_files()
    names = [(p.name, k) for p, k in files]
    assert names == [("trading_state.json", "main"), ("trading_state_5m_mean_revert.json", "slot")]


def test_is_real_row_main_vs_slot():
    assert rp.is_real_row({}, "main")                       # historical main = real
    assert not rp.is_real_row({"mode": "paper"}, "main")
    assert rp.is_real_row({"mode": "live"}, "slot")
    assert not rp.is_real_row({}, "slot")                   # slot rows w/o mode = paper era
    assert not rp.is_real_row({"mode": "paper"}, "slot")


def test_build_patches_fees_funding_and_unmatched():
    t_ok = _trade(1000.0, 5000.0, fees_usdt=0.0059, funding_usdt=0.0, pnl_usdt=1.0, net_pnl=0.9941)
    t_same = _trade(6000.0, 7000.0, fees_usdt=0.103, funding_usdt=0.0, funding_source="phemex_reconcile")
    t_none = _trade(8000.0, 9000.0)
    fills = {SYM: [
        _fill(1001, "sell", 1.0, 1, 0.0147), _fill(4990, "buy", 1.0, 1, 0.0883),
        _fill(6001, "sell", 1.0, 1, 0.015), _fill(6999, "buy", 1.0, 1, 0.088),
    ]}
    funding = {rp.trade_key(t_ok): -0.0017, rp.trade_key(t_same): 0.0, rp.trade_key(t_none): 0.0}
    patches, unmatched = rp.build_patches([t_ok, t_same, t_none], fills, funding)
    assert unmatched == [t_none]
    by_key = {p["key"]: p for p in patches}
    p = by_key[rp.trade_key(t_ok)]
    assert p["fees_usdt"] == pytest.approx(0.103)          # 0.0059 → 0.103, drift > 0.01
    assert p["funding_usdt"] == pytest.approx(-0.0017)      # received
    # t_same: fees within tolerance, funding unchanged and already stamped → no patch
    assert rp.trade_key(t_same) not in by_key
    # unmatched rows never get funding stamped
    assert rp.trade_key(t_none) not in by_key


def test_build_patches_stamps_funding_zero_once():
    t = _trade(1000.0, 5000.0, fees_usdt=0.103, funding_usdt=0.0)   # no funding_source yet
    fills = {SYM: [_fill(1001, "sell", 1.0, 1, 0.015), _fill(4990, "buy", 1.0, 1, 0.088)]}
    patches, _ = rp.build_patches([t], fills, {rp.trade_key(t): 0.0})
    assert len(patches) == 1
    assert patches[0]["fees_usdt"] is None and patches[0]["funding_usdt"] == 0.0


def test_apply_patches_writes_fields_recomputes_net_and_clears_pending(tmp_path):
    path = tmp_path / "trading_state_5m_mean_revert.json"
    row = _trade(1000.0, 5000.0, mode="live", fees_usdt=0.105, fees_pending=True,
                 pnl_usdt=2.0, funding_usdt=0.0, net_pnl=1.895)
    path.write_text(json.dumps({"peak_balance": 1.0, "closed_trades": [row],
                                "trade_results": [], "positions": {"X": {"keep": 1}}}))
    n = rp.apply_patches(path, [{"key": rp.trade_key(row), "fees_usdt": 0.021,
                                 "funding_usdt": 0.0031, "local_fee": 0.105, "local_funding": 0.0}])
    assert n == 1
    got = json.loads(path.read_text())
    t = got["closed_trades"][0]
    assert t["fees_usdt"] == pytest.approx(0.021)
    assert t["funding_usdt"] == pytest.approx(0.0031)
    assert t["net_pnl"] == pytest.approx(2.0 - 0.021 - 0.0031)
    assert t["fees_source"] == "phemex_reconcile" and t["funding_source"] == "phemex_reconcile"
    assert "fees_pending" not in t
    assert got["positions"] == {"X": {"keep": 1}}           # untouched


def test_apply_patches_funding_only_keeps_fees(tmp_path):
    path = tmp_path / "trading_state.json"
    row = _trade(1000.0, 5000.0, fees_usdt=0.05, pnl_usdt=1.0, net_pnl=0.95)
    path.write_text(json.dumps({"closed_trades": [row]}))
    rp.apply_patches(path, [{"key": rp.trade_key(row), "fees_usdt": None,
                             "funding_usdt": 0.002, "local_fee": 0.05, "local_funding": 0.0}])
    t = json.loads(path.read_text())["closed_trades"][0]
    assert t["fees_usdt"] == 0.05 and "fees_source" not in t
    assert t["funding_usdt"] == pytest.approx(0.002) and t["net_pnl"] == pytest.approx(0.948)


class _FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_funding_history(self, symbol, since=None, limit=None, params=None):
        self.calls.append((symbol, limit, dict(params or {})))
        off = int((params or {}).get("offset", 0))
        return self.pages.get(off, [])


class _FakeExchange:
    def __init__(self, pages):
        self.client = _FakeClient(pages)


def test_fetch_funding_rows_pages_by_offset_and_filters_since():
    page0 = [{"timestamp": 9_000_000, "amount": -0.5, "symbol": "ETHUSDT"} for _ in range(200)]
    page1 = [{"timestamp": 5_000_000, "amount": 0.25, "symbol": "ETHUSDT"},
             {"timestamp": 1_000, "amount": 9.0, "symbol": "ETHUSDT"}]   # too old
    ex = _FakeExchange({0: page0, 200: page1})
    rows = rp.fetch_funding_rows(ex, SYM, since_ms=2_000_000)
    assert len(rows) == 201
    assert rows[-1] == {"timestamp": 5_000_000, "symbol": SYM, "paid": 0.25}
    assert ex.client.calls[0][1] == 200 and ex.client.calls[1][2] == {"offset": 200}


# ---------------------------------------------------------------------------
# Matching defects found in the 9/7 100d dry run (real fills, read-only)
# ---------------------------------------------------------------------------


def test_exit_window_is_side_aware_and_ignores_next_entry():
    # PUMP 8/10 8:21 PM long: exit sell 8:51:14 PM, then the NEXT long's entry
    # buys land 8:51:25-32 PM -- inside the exit window but the wrong side.
    t = _trade(1000.0, 5000.0, side="long")
    fills = [
        _fill(1001, "buy", 1.0, 1, 0.015, fid="entry"),
        _fill(4996, "sell", 1.0, 1, 0.090, fid="exit"),
        _fill(5007, "buy", 1.0, 1, 0.004, fid="next-entry-1"),
        _fill(5012, "buy", 1.0, 1, 0.011, fid="next-entry-2"),
    ]
    entry, exit_, fee = rp.match_trade_to_fills(t, fills)
    assert [f["id"] for f in entry] == ["entry"]
    assert [f["id"] for f in exit_] == ["exit"]
    assert fee == pytest.approx(0.105)


def test_entry_window_reaches_300s_before_opened_at():
    # MR slot stamps opened_at 60-80s AFTER the maker fill (ADA 8/9: 63s,
    # 1000SHIB 8/24: 67s, 1000PEPE 8/28: 69s, BTC 8/30: 79s).
    t = _trade(1000.0, 5000.0)
    fills = [_fill(921, "sell", 1.0, 1, 0.03, fid="entry"), _fill(4998, "buy", 1.0, 1, 0.18, fid="exit")]
    entry, exit_, fee = rp.match_trade_to_fills(t, fills)
    assert [f["id"] for f in entry] == ["entry"] and fee == pytest.approx(0.21)
    fills2 = [_fill(699, "sell", 1.0, 1, 0.03, fid="too-early"), _fill(4998, "buy", 1.0, 1, 0.18, fid="exit")]
    entry2, _, _ = rp.match_trade_to_fills(t, fills2)
    assert entry2 == []
    assert rp.ENTRY_MATCH_BEFORE_SEC == 300


def test_build_patches_exit_only_match_is_partial_funding_only():
    # LTC 7/29: entry fill older than Phemex's fill-history horizon. The row is
    # real (exit matched) so funding is stamped, but fees must NOT be patched
    # down to the exit leg alone.
    t = _trade(1000.0, 5000.0, fees_usdt=0.198, funding_usdt=0.0)
    fills = {SYM: [_fill(4998, "buy", 1.0, 1, 0.179, fid="exit")]}
    patches, unmatched = rp.build_patches([t], fills, {rp.trade_key(t): -0.0217})
    assert unmatched == []
    assert len(patches) == 1
    p = patches[0]
    assert p["fees_usdt"] is None and p["partial"] is True
    assert p["funding_usdt"] == pytest.approx(-0.0217)


def test_build_patches_runner_row_gets_exit_only_fee():
    # partial_tp row and its runner share opened_at; the entry fill is claimed
    # by the partial (closes first), the runner's complete fee is its own exit.
    # (ONDO 8/2: the bot stamps the same full-position estimate on both rows.)
    partial = _trade(1000.0, 3000.0, exit_reason="partial_tp", fees_usdt=0.0493)
    runner = _trade(1000.0, 4000.0, exit_reason="trailing_stop", fees_usdt=0.0593)
    fills = {SYM: [
        _fill(1001, "sell", 1.0, 2, 0.015, fid="entry"),
        _fill(2999, "buy", 1.0, 1, 0.0444, fid="exit-1"),
        _fill(3999, "buy", 1.0, 1, 0.0443, fid="exit-2"),
    ]}
    funding = {rp.trade_key(partial): 0.0, rp.trade_key(runner): 0.0}
    patches, unmatched = rp.build_patches([runner, partial], fills, funding)
    assert unmatched == []
    by_key = {p["key"]: p for p in patches}
    assert by_key[rp.trade_key(partial)]["fees_usdt"] == pytest.approx(0.0594)
    assert by_key[rp.trade_key(runner)]["fees_usdt"] == pytest.approx(0.0443)
    assert by_key[rp.trade_key(runner)]["partial"] is False


# ---------------------------------------------------------------------------
# 9/7 code-review findings on 48a243d
# ---------------------------------------------------------------------------


def test_reconcile_ledgers_claims_fills_and_funding_once_across_ledgers(tmp_path):
    # FINDING 1: a main-book row and a slot row on the same symbol, minutes
    # apart, both overlap the same exit fill and the same funding settlement.
    # Per-ledger matching let BOTH absorb them; the global pass must give each
    # to exactly one row (the earlier-closing one) and leave the other partial.
    main_row = _trade(1000.0, 5000.0, fees_usdt=0.05, amount=1.0)
    slot_row = _trade(1100.0, 5100.0, fees_usdt=0.05, amount=1.0, mode="live")
    fills = {SYM: [
        _fill(1001, "sell", 1.0, 1.0, 0.015, fid="main-entry"),
        _fill(1101, "sell", 1.0, 1.0, 0.016, fid="slot-entry"),
        _fill(4990, "buy", 1.0, 1.0, 0.088, fid="only-exit"),
    ]}
    funding = [{"timestamp": 3000 * 1000, "symbol": SYM, "paid": 0.01}]
    main_p = tmp_path / "trading_state.json"
    slot_p = tmp_path / "trading_state_5m_mean_revert.json"
    out = rp.reconcile_ledgers([(main_p, "main", [main_row]), (slot_p, "slot", [slot_row])], fills, funding)
    main_patches, main_unmatched = out[main_p]
    slot_patches, slot_unmatched = out[slot_p]
    assert main_unmatched == [] and slot_unmatched == []
    assert [p["key"] for p in main_patches] == [rp.trade_key(main_row)]
    assert [p["key"] for p in slot_patches] == [rp.trade_key(slot_row)]
    mp, sp = main_patches[0], slot_patches[0]
    # earlier-closing main row owns the exit fill and the settlement
    assert mp["partial"] is False and mp["legs"] == "1e/1x"
    assert mp["fees_usdt"] == pytest.approx(0.015 + 0.088)
    assert mp["funding_usdt"] == pytest.approx(0.01)
    # slot row keeps only its own entry: partial, fee untouched, funding 0 (not double-counted)
    assert sp["partial"] is True and sp["legs"] == "1e/0x"
    assert sp["fees_usdt"] is None
    assert sp["funding_usdt"] == 0.0


def test_reversal_entry_fill_not_stolen_by_prior_exit():
    # FINDING 2: A long exits with a sell at 4990; B short ENTERS with a sell
    # at 5031 — inside A's exit window (closed_at-300..+60) and the same side.
    # The quantity cap (matched qty < amount*1.001, fills in time order) stops
    # A after its 1.0 is covered so B keeps its entry.
    a = _trade(1000.0, 5000.0, side="long", amount=1.0, fees_usdt=0.05)
    b = _trade(5030.0, 9000.0, side="short", amount=1.0, fees_usdt=0.05)
    fills = [
        _fill(5031, "sell", 1.0, 1.0, 0.015, fid="b-entry"),   # listed first: order in the list must not matter
        _fill(1001, "buy", 1.0, 1.0, 0.014, fid="a-entry"),
        _fill(4990, "sell", 1.0, 1.0, 0.088, fid="a-exit"),
        _fill(8999, "buy", 1.0, 1.0, 0.090, fid="b-exit"),
    ]
    claimed = set()
    ea, xa, fa = rp.match_trade_to_fills(a, fills, claimed)
    eb, xb, fb = rp.match_trade_to_fills(b, fills, claimed)
    assert [f["id"] for f in ea] == ["a-entry"] and [f["id"] for f in xa] == ["a-exit"]
    assert fa == pytest.approx(0.014 + 0.088)
    assert [f["id"] for f in eb] == ["b-entry"] and [f["id"] for f in xb] == ["b-exit"]
    assert fb == pytest.approx(0.015 + 0.090)
    assert claimed == {"a-entry", "a-exit", "b-entry", "b-exit"}
    # end to end: both rows complete, B's fee is its own round trip
    funding = {rp.trade_key(a): 0.0, rp.trade_key(b): 0.0}
    patches, unmatched = rp.build_patches([a, b], {SYM: fills}, funding)
    assert unmatched == []
    by_key = {p["key"]: p for p in patches}
    assert by_key[rp.trade_key(a)]["partial"] is False and by_key[rp.trade_key(a)]["fees_usdt"] == pytest.approx(0.102)
    assert by_key[rp.trade_key(b)]["partial"] is False and by_key[rp.trade_key(b)]["fees_usdt"] == pytest.approx(0.105)


def test_qty_cap_only_applies_with_usable_amount():
    # Rows without a usable amount (None / 0) keep today's behavior: every
    # side-matching fill in the window is taken.
    fills = [
        _fill(1001, "buy", 1.0, 1.0, 0.014, fid="a-entry"),
        _fill(4990, "sell", 1.0, 1.0, 0.088, fid="a-exit"),
        _fill(5031, "sell", 1.0, 1.0, 0.015, fid="stray-sell"),
    ]
    for amt in (None, 0, 0.0):
        a = _trade(1000.0, 5000.0, side="long", amount=amt)
        _, xa, _ = rp.match_trade_to_fills(a, fills)
        assert [f["id"] for f in xa] == ["a-exit", "stray-sell"]
    # crumb rows carry the INTENDED amount (larger than what filled): cap never binds
    crumb = _trade(1000.0, 1000.5, exit_reason="min_margin_skip", amount=5.0)
    cfills = [_fill(1000.2, "sell", 1.0, 0.5, 0.001, fid="ce"), _fill(1000.4, "buy", 1.0, 0.5, 0.006, fid="cx")]
    e, x, fee = rp.match_trade_to_fills(crumb, cfills)
    assert {f["id"] for f in e + x} == {"ce", "cx"} and fee == pytest.approx(0.007)
    # lot rounding: a 103.8 fill covers a 103.84 row (0.1% slack), so a later
    # same-side fill inside the window is left for the next trade
    xrp = _trade(1000.0, 5000.0, side="long", symbol="XRP/USDT:USDT", amount=103.84)
    xfills = [_fill(1001, "buy", 1.44, 103.8, 0.089, fid="x-entry"),
              _fill(4990, "sell", 1.45, 103.8, 0.090, fid="x-exit"),
              _fill(5020, "sell", 1.45, 103.8, 0.090, fid="next-short-entry")]
    e, x, _ = rp.match_trade_to_fills(xrp, xfills)
    assert [f["id"] for f in e] == ["x-entry"] and [f["id"] for f in x] == ["x-exit"]
    assert rp.QTY_COVERED_FRAC == 0.999


def test_apply_patches_writes_positions_from_the_final_read(tmp_path, monkeypatch):
    # FINDING 3: the bot rewrites `positions` every cycle (trailing stops).
    # Whatever positions dict the LAST read saw must be what lands on disk —
    # the patch may only be applied to the freshest state.
    path = tmp_path / "trading_state.json"
    row = _trade(1000.0, 5000.0, fees_usdt=0.05, pnl_usdt=1.0, net_pnl=0.95)

    def _state(v):
        return json.dumps({"closed_trades": [row], "positions": {"ETH": {"trailing_stop_price": v}}})

    path.write_text(_state(0))
    calls = {"n": 0}
    real_read_text = Path.read_text

    def fake_read_text(self, *a, **kw):
        if self == path:
            calls["n"] += 1
            return _state(calls["n"])          # each read sees a newer positions dict
        return real_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    n = rp.apply_patches(path, [{"key": rp.trade_key(row), "fees_usdt": 0.1, "funding_usdt": None,
                                 "local_fee": 0.05, "local_funding": 0.0}])
    got = json.loads(real_read_text(path))
    assert n == 1 and calls["n"] >= 1
    assert got["positions"]["ETH"]["trailing_stop_price"] == calls["n"]   # last read wins
    assert got["closed_trades"][0]["fees_usdt"] == pytest.approx(0.1)


def test_apply_patches_retries_when_bot_writes_between_read_and_replace(tmp_path, monkeypatch):
    # A bot _save_state (in-place open("w")) landing after our read but before
    # os.replace must be detected; the retry re-reads and preserves its positions.
    path = tmp_path / "trading_state.json"
    row = _trade(1000.0, 5000.0, fees_usdt=0.05, pnl_usdt=1.0, net_pnl=0.95)
    path.write_text(json.dumps({"closed_trades": [row], "positions": {}}))
    bot_state = {"closed_trades": [row], "positions": {"ETH": {"trailing_stop_price": 7}}}
    real_write_text = Path.write_text
    fired = {"done": False}

    def fake_write_text(self, data, *a, **kw):
        if self.name.endswith(".reconcile.tmp") and not fired["done"]:
            fired["done"] = True
            with open(path, "w") as f:            # the bot's write, mid-window
                json.dump(bot_state, f)
        return real_write_text(self, data, *a, **kw)

    monkeypatch.setattr(Path, "write_text", fake_write_text)
    n = rp.apply_patches(path, [{"key": rp.trade_key(row), "fees_usdt": 0.1, "funding_usdt": None,
                                 "local_fee": 0.05, "local_funding": 0.0}])
    got = json.loads(path.read_text())
    assert n == 1
    assert got["positions"] == {"ETH": {"trailing_stop_price": 7}}      # bot's write survived
    assert got["closed_trades"][0]["fees_usdt"] == pytest.approx(0.1)
    assert not path.with_suffix(".json.reconcile.tmp").exists()
