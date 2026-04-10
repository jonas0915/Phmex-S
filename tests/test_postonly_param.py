"""Test that post-only entry orders use the correct Phemex param format."""
import inspect
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exchange import Exchange


def test_try_limit_then_market_uses_post_only_time_in_force():
    """Verify exchange._try_limit_then_market sends timeInForce=PostOnly.

    Phemex ccxt rejects {"postOnly": True} with error 39999. It expects
    {"timeInForce": "PostOnly"}. This test reads the source of the method
    to verify the correct literal is present.
    """
    src = inspect.getsource(Exchange._try_limit_then_market)
    assert '"timeInForce": "PostOnly"' in src or "'timeInForce': 'PostOnly'" in src, \
        f"_try_limit_then_market must use timeInForce=PostOnly, got:\n{src}"
    # The bad form must be gone
    assert '"postOnly": True' not in src and "'postOnly': True" not in src, \
        f"_try_limit_then_market still uses postOnly=True (rejected by Phemex):\n{src}"
