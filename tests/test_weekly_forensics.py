"""Test weekly forensics pattern detector."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.weekly_forensics import find_significant_patterns


def test_finds_bucket_with_low_win_rate():
    """A bucket with 10+ trades and less than 30% WR should be flagged."""
    now = time.time()
    trades = []
    # SOL longs: 12 trades, 2 wins = 16.7% WR
    for i in range(12):
        trades.append({
            "symbol": "SOL/USDT:USDT", "side": "long",
            "opened_at": now - 86400 * (i % 7),
            "closed_at": now - 86400 * (i % 7),
            "net_pnl": 1.0 if i < 2 else -1.0,
        })
    # ETH shorts: 20 trades, 18 wins = 90% WR (should flag as significant positive)
    for i in range(20):
        trades.append({
            "symbol": "ETH/USDT:USDT", "side": "short",
            "opened_at": now - 86400 * (i % 7),
            "closed_at": now - 86400 * (i % 7),
            "net_pnl": 1.0 if i < 18 else -1.0,
        })
    patterns = find_significant_patterns(trades, min_n=10, min_deviation=0.2)
    labels = [p["label"] for p in patterns]
    assert any("SOL" in l and "long" in l for l in labels), f"Expected SOL long pattern, got: {labels}"
    assert any("ETH" in l and "short" in l for l in labels), f"Expected ETH short pattern, got: {labels}"


def test_ignores_small_samples():
    """Fewer than min_n trades = not significant even if WR is extreme."""
    trades = [
        {"symbol": "BTC/USDT:USDT", "side": "long", "closed_at": time.time(), "net_pnl": 1.0}
        for _ in range(5)
    ]
    patterns = find_significant_patterns(trades, min_n=10)
    assert patterns == []
