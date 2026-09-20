screens/informed_flow_btc_alt_lag/signal.py (see file; reproduced): """informed_flow_btc_alt_lag -- BTC-led momentum propagation into slower-liquidity alts.

Mechanism: informed flow trades the deepest, most-watched book (BTC) first. Lower-
liquidity alt books are re-priced / arbed less continuously, so a large BTC move
propagates into alt prices with a measurable delay -- documented in the literature at
sub-hour granularity for small-cap names (see thesis source_urls). This signal tests
whether that propagation survives as an exploitable move at hourly-bar resolution, net
of Phemex's 11.5bp round-trip cost.

Rule (closed bars only, no lookahead):
- At each closed alt bar t, compute BTC's trailing BTC_LOOKBACK_BARS-bar (3h) return in
  bps, using only BTC bars with timestamp <= t (forward-filled onto the alt's own index --
  never a future BTC value).
- If BTC's trailing return > +LAG_THRESH_BPS  -> long the alt (bet on catch-up).
- If BTC's trailing return < -LAG_THRESH_BPS  -> short the alt.
- Otherwise flat.

Causality: btc_close.reindex(df.index, method='ffill') only ever pulls BTC values at or
before each timestamp in the (possibly truncated) df passed in; pct_change() looks
backward only. Re-running signals() on any prefix of df therefore reproduces identical
values at every shared timestamp -> passes screen.causality_check's whole-prefix
exact-equality test.
"""
from __future__ import annotations

import pandas as pd

from research.swarm.lib import load_data as ld

BTC_LOOKBACK_BARS = 3       # BTC trailing-return window, in 1h bars (3h)
LAG_THRESH_BPS = 150.0      # BTC move (bps) required to trigger a propagation bet
DATASET = 'long_1h'
TIMEFRAME = '1h'


def signals(df: pd.DataFrame) -> pd.Series:
    btc = ld.load_ohlcv('BTC', TIMEFRAME, era='train', dataset=DATASET)
    btc_close = btc['close']

    # Causal alignment: only BTC values at-or-before each alt bar's own timestamp.
    btc_aligned = btc_close.reindex(df.index, method='ffill')
    btc_ret_bps = btc_aligned.pct_change(BTC_LOOKBACK_BARS) * 10000.0

    sig = pd.Series(0, index=df.index, dtype=int)
    sig[btc_ret_bps > LAG_THRESH_BPS] = 1
    sig[btc_ret_bps < -LAG_THRESH_BPS] = -1
    sig = sig.fillna(0).astype(int)
    return sig
