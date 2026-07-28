from sr_signal import confirmed_rejection, plan_trade

SUP = {"lo": 99.0, "hi": 100.0, "side": "support", "touches": 2}
RES = {"lo": 110.0, "hi": 111.0, "side": "resistance", "touches": 2}


def test_rejection_support_pierce_and_close_back():
    assert confirmed_rejection({"open": 101, "high": 101, "low": 99.5, "close": 100.4}, SUP)


def test_rejection_support_close_through_fails():
    assert not confirmed_rejection({"open": 101, "high": 101, "low": 98, "close": 99.5}, SUP)


def test_rejection_support_never_entered_fails():
    assert not confirmed_rejection({"open": 101, "high": 102, "low": 100.5, "close": 101}, SUP)


def test_plan_trade_long_basic():
    t = plan_trade(SUP, [SUP, RES], atr5=0.4, entry=100.4)
    assert t["side"] == "long"
    assert t["sl"] == 99.0 - 0.1            # zone lo - 0.25*atr5
    risk = 100.4 - t["sl"]
    assert t["tp"] == min(110.0, 100.4 + 3 * risk)


def test_plan_trade_skip_no_room():
    near_res = {"lo": 100.9, "hi": 101.2, "side": "resistance", "touches": 2}
    assert plan_trade(SUP, [SUP, near_res], atr5=0.4, entry=100.4) is None


def test_plan_trade_skip_no_opposing():
    assert plan_trade(SUP, [SUP], atr5=0.4, entry=100.4) is None
