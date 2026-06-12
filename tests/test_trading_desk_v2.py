# tests/test_trading_desk_v2.py
import sys, json, time
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import trading_desk as td

SAMPLE = """
2026-06-12 09:52:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.3)
2026-06-12 09:53:08 [DEBUG] [HOLD] ZEC/USDT:USDT — No confluence signal (1h ADX=15.9)
2026-06-12 09:52:09 [DEBUG] [HOLD] INJ/USDT:USDT — No confluence signal (1h ADX=23.2)
""".strip().splitlines()

def test_parse_pair_adx_newest_wins():
    adx = td.parse_pair_adx(SAMPLE)
    assert adx["ZEC/USDT:USDT"] == 15.9
    assert "DOGE/USDT:USDT" not in adx          # absent stays absent

def test_slot_truth_shape():
    slots = td.build_slot_truth()
    assert isinstance(slots, list)
    for s in slots:
        assert {"id", "live", "trades", "wr", "net_pnl"} <= set(s.keys())
        if s["live"]:
            assert {"live_net", "headroom", "live_trades"} <= set(s.keys())

def test_api_response_has_truth_fields():
    r = td._build_api_response()
    assert "slots" in r and "watcher" in r and "pair_adx" in r and "top_gates" in r
    assert isinstance(r["watcher"], bool)
