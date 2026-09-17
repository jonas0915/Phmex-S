import pandas as pd
import numpy as np


def signals(df: pd.DataFrame) -> pd.Series:
    """session_calendar_weekend_thinbook_fade — closed 1h bars only.
    At the bar stamped Sunday 23:00 UTC (the last bar of the weekend, closing Monday 00:00 UTC),
    measure the weekend move as close(Sun 23:00) / close(Fri 20:00) - 1, where the Fri 20:00 bar
    (closing 21:00 UTC = CME close) sits exactly 51 hourly bars earlier. If the move is >= +5%
    emit -1 (fade the thin-book weekend rally); if <= -5% emit +1 (fade the weekend dump).
    Entry is at Monday 00:00 UTC open. Uses only shift(+51) and the bar's own index; no future bars.
    A missing/irregular 51-bar gap (data hole) disables the bar."""
    c = df["close"].astype(float)
    idx = df.index
    is_sun23 = (idx.dayofweek == 6) & (idx.hour == 23)
    gap_ok = (idx.to_series().diff(51) == pd.Timedelta(hours=51)).to_numpy()
    wk = (c / c.shift(51) - 1.0).to_numpy()
    sig = pd.Series(0, index=idx, dtype="int64")
    ok = is_sun23 & gap_ok & ~np.isnan(wk)
    sig[ok & (wk >= 0.05)] = -1
    sig[ok & (wk <= -0.05)] = 1
    return sig
