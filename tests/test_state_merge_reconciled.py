"""_save_state must adopt reconciler-written ledger fields from the state FILE
before overwriting it (2026-09-07). Before this, every reconcile patch was
reverted by the next close and only re-applied inside the 7-day lookback."""
import json
import os
import time

from risk_manager import RiskManager

SYM = "ETH/USDT:USDT"


def _rm(tmp_path):
    rm = RiskManager(state_file=str(tmp_path / "trading_state_5m_mean_revert.json"))
    rm.is_paper = False
    rm._log_prefix = ""
    return rm


def _close_one(rm, exit_px=2450.0):
    rm.open_position(SYM, entry_price=2451.37, margin=15.0, side="short")
    rm.close_position(SYM, exit_price=exit_px, reason="hard_time_exit", fees_usdt=0.097074, mode="live")
    return rm.closed_trades[-1]


def _external_patch(path, **fields):
    state = json.loads(open(path).read())
    state["closed_trades"][0].update(fields)
    time.sleep(0.02)
    with open(path, "w") as f:
        json.dump(state, f)
    os.utime(path, None)


def test_save_merges_reconciled_fields_and_clears_pending(tmp_path):
    rm = _rm(tmp_path)
    row = _close_one(rm)
    row["fees_pending"] = True
    rm._save_state()
    _external_patch(rm.state_file, fees_usdt=0.10299678, fees_source="phemex_reconcile",
                    fees_reconciled_at=1, funding_usdt=-0.00175251,
                    funding_source="phemex_reconcile", funding_reconciled_at=1, net_pnl=0.123)
    # The next CLOSE is what saves (open_position does not) — this is the exact
    # path that used to clobber reconciler patches.
    rm.open_position("SOL/USDT:USDT", entry_price=100.0, margin=15.0, side="long")
    rm.close_position("SOL/USDT:USDT", exit_price=101.0, reason="take_profit", fees_usdt=0.02, mode="live")
    merged = rm.closed_trades[0]
    assert merged["fees_usdt"] == 0.10299678
    assert merged["funding_usdt"] == -0.00175251
    assert merged["net_pnl"] == 0.123
    assert merged["fees_source"] == "phemex_reconcile"
    assert "fees_pending" not in merged
    on_disk = json.loads(open(rm.state_file).read())["closed_trades"][0]
    assert on_disk["fees_usdt"] == 0.10299678 and on_disk["funding_usdt"] == -0.00175251


def test_save_skips_merge_when_file_unchanged(tmp_path, monkeypatch):
    rm = _rm(tmp_path)
    _close_one(rm)
    calls = []
    real_open = open

    def spy_open(path, *a, **kw):
        if str(path) == rm.state_file and (not a or a[0] == "r"):
            calls.append(path)
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", spy_open)
    rm._save_state()      # mtime matches what we last wrote → no read
    assert calls == []


def test_merge_does_not_touch_rows_without_source_fields(tmp_path):
    rm = _rm(tmp_path)
    _close_one(rm)
    _external_patch(rm.state_file, fees_usdt=9.99)   # no *_source → not a reconciler write
    rm._save_state()
    assert rm.closed_trades[0]["fees_usdt"] == 0.097074


def test_merge_survives_unreadable_file(tmp_path):
    rm = _rm(tmp_path)
    _close_one(rm)
    time.sleep(0.02)
    with open(rm.state_file, "w") as f:
        f.write("{not json")
    rm._save_state()   # must not raise; rewrites a valid file
    assert json.loads(open(rm.state_file).read())["closed_trades"][0]["fees_usdt"] == 0.097074
