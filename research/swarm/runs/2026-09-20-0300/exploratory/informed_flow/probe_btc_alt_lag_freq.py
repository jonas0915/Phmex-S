"""EXPLORATORY ONLY -- not the screen, not evidence. Shapes the informed_flow_btc_alt_lag
thesis's expected_trades_per_week spec field by counting how often the raw signal fires
on TRAIN-era long_1h data. Does not touch holdout, does not use mr_edge data >= 2026-04-23
(cross-dataset holdout caveat, STANDARDS #6) -- uses only long_1h train.
"""
import importlib.util

from research.swarm.lib import load_data as ld

spec = importlib.util.spec_from_file_location(
    "sig", "research/swarm/runs/2026-09-20-0300/screens/informed_flow_btc_alt_lag/signal.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

UNIVERSE = ["1000PEPE", "1000SHIB", "AAVE", "ADA", "DOGE", "GIGGLE", "LINK", "LTC",
            "NEAR", "ONDO", "SUI", "TAO", "UNI", "XLM", "XRP"]

if __name__ == "__main__":
    total_bars = 0
    total_fires = 0
    for sym in UNIVERSE:
        try:
            df = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
        except FileNotFoundError:
            print(sym, "no cache file, skipped")
            continue
        s = mod.signals(df)
        fires = int((s != 0).sum())
        total_bars += len(df)
        total_fires += fires
        print(f"{sym}: bars={len(df)} fires={fires} fire_rate={fires/len(df):.4f}")
    weeks = total_bars / len(UNIVERSE) / 24 / 7 if UNIVERSE else 0
    print(f"TOTAL: bars/symbol_avg_weeks={weeks:.1f} total_fires={total_fires} "
          f"raw_fires_per_week={total_fires/weeks:.2f} (raw signal-on bar-count, NOT trade count -- "
          f"screen.simulate's actual entries depend on signal-change/re-entry rules)")
