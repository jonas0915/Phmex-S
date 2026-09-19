import pandas as pd
from research.swarm.lib import load_data as ld


def signals(df: pd.DataFrame) -> pd.Series:
    """Long-only: fires 1 when BTC's own PRIOR closed 1h bar returned > 60 bps, on the
    theory that this alt (ETH/ADA/XRP/SOL) reprices the shock with a multi-hour lag.
    Uses only BTC bars with ts <= the current alt bar's ts (merge_asof backward) so no
    future information ever enters the signal at any truncation point.
    """
    btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
    btc_ret_prior = btc["close"].pct_change().shift(1)

    b = btc_ret_prior.rename("btc_ret_prior").reset_index()
    b.columns = ["ts", "btc_ret_prior"]
    b = b.sort_values("ts")

    alt_ts = pd.DataFrame({"ts": df.index}).sort_values("ts")
    merged = pd.merge_asof(alt_ts, b, on="ts", direction="backward")
    merged = merged.set_index("ts").reindex(df.index)

    thresh = 0.006
    sig = pd.Series(0, index=df.index, dtype=int)
    sig[merged["btc_ret_prior"] > thresh] = 1
    return sig
