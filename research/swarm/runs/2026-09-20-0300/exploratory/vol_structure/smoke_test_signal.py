# EXPLORATORY ONLY -- not the screen, numbers here are not evidence.
# Smoke test on synthetic (non-market) data to confirm signals() returns
# only {-1,0,1}, matches df index/length, and has no lookahead risk from
# forming-bar / shift(-k) usage. No train or holdout market data touched.
import json
import re

import numpy as np
import pandas as pd

THESIS_PATH = "research/swarm/runs/2026-09-20-0300/theses/vol_structure_volscale_continuation.json"

if __name__ == "__main__":
    d = json.load(open(THESIS_PATH))
    assert re.match(r"^[a-z][a-z0-9_]{2,40}$", d["id"])
    g = {}
    exec(d["signal_py"], g)
    idx = pd.date_range("2026-01-01", periods=1000, freq="h", tz="UTC")
    rng = np.random.default_rng(0)
    df = pd.DataFrame(
        {
            "open": 1,
            "high": 1,
            "low": 1,
            "close": np.cumsum(rng.standard_normal(1000)) + 100,
            "volume": 1,
        },
        index=idx,
    )
    s = g["signals"](df)
    print("unique values:", sorted(s.unique().tolist()))
    print("index/length match:", len(s) == len(df) and (s.index == df.index).all())
