"""bb_mean_reversion dispatch hygiene (2026-08-12, closes the 8/1 open flag).

The shared slot signal path calls strategy_fn(df, ob, htf_df=...) and falls
back on TypeError. bb_mean_reversion has no htf_df param, so every symbol
every cycle raised/caught TypeError and a misleading once-per-boot warning
("htf_df is being silently dropped") fired even though nothing is dropped.
Fix: registered signature dispatch, like ST2.0 / htf_l2 / sr_bounce.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_bb_mean_reversion_signature_has_no_htf_df():
    # The premise of the special-case: if this ever grows an htf_df param,
    # the registered dispatch below would start silently starving it.
    from strategies import bb_mean_reversion_strategy
    params = inspect.signature(bb_mean_reversion_strategy).parameters
    assert "htf_df" not in params


def test_bb_mean_reversion_registered_in_dispatch():
    # Registered BEFORE the generic TypeError-fallback else-branch.
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "bot.py")).read()
    marker = 'elif slot.strategy_name == "bb_mean_reversion":'
    fallback = "falling back to strategy_fn(df, ob)"
    assert marker in src
    assert src.index(marker) < src.index(fallback)
