"""Test that post-only orders use the correct Phemex param format.

The old `_try_limit_then_market` method was split into `_try_limit_entry`
(entries — no market fallback, exchange.py) and `_try_limit_exit` (exits —
caller falls back to market). Both legs must send timeInForce=PostOnly:
Phemex ccxt rejects {"postOnly": True} with error 39999.
"""
import inspect
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange import Exchange


def _assert_post_only(method):
    src = inspect.getsource(method)
    assert '"timeInForce": "PostOnly"' in src or "'timeInForce': 'PostOnly'" in src, \
        f"{method.__name__} must use timeInForce=PostOnly, got:\n{src}"
    # The bad form must be gone
    assert '"postOnly": True' not in src and "'postOnly': True" not in src, \
        f"{method.__name__} still uses postOnly=True (rejected by Phemex):\n{src}"


def test_limit_entry_uses_post_only_time_in_force():
    _assert_post_only(Exchange._try_limit_entry)


def test_limit_exit_uses_post_only_time_in_force():
    _assert_post_only(Exchange._try_limit_exit)


def test_limit_exit_is_reduce_only():
    """Exit limits must be reduceOnly so a raced/leftover order can never
    double-close or flip the position after the market fallback."""
    src = inspect.getsource(Exchange._try_limit_exit)
    assert '"reduceOnly": True' in src or "'reduceOnly': True" in src, \
        f"_try_limit_exit must place reduceOnly orders:\n{src}"
