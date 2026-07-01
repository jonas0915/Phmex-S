"""Test the configurable time-of-day entry block (empty = 24-hour trading)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_trading_blocked_hours_default_is_empty_24h():
    """With TRADING_BLOCKED_HOURS_UTC empty in .env, the bot trades 24h (no blocked hours)."""
    from config import Config
    assert isinstance(Config.TRADING_BLOCKED_HOURS_UTC, set)
    assert Config.TRADING_BLOCKED_HOURS_UTC == set()


def test_trading_blocked_hours_parse_rule():
    """The parse rule: comma-separated UTC hours, whitespace-tolerant, empty -> empty set."""
    parse = lambda s: {int(h.strip()) for h in s.split(",") if h.strip()}
    assert parse("") == set()
    assert parse("0,1,2,9,17,18,19,20") == {0, 1, 2, 9, 17, 18, 19, 20}
    assert parse(" 5 , 8 ") == {5, 8}
