import pandas as pd
from fetch_data import load_candles


def test_load_candles_uses_cache(tmp_path):
    f = tmp_path / "BTC_USDT_USDT_1h.csv"
    pd.DataFrame({"ts": [2, 1, 2], "open": [1, 1, 1], "high": [2, 2, 2],
                  "low": [0.5, 0.5, 0.5], "close": [1.5, 1.4, 1.5],
                  "volume": [10, 10, 10]}).to_csv(f, index=False)
    df = load_candles("BTC/USDT:USDT", "1h", data_dir=str(tmp_path))
    assert list(df["ts"]) == [1, 2]          # sorted + deduped (keep first of dup ts)
    assert len(df) == 2
