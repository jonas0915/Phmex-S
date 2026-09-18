"""EXPLORATORY probe (not the screen, not evidence). Estimates trigger frequency of
the liq-cascade-continuation proxy signal on TRAIN-era mr_edge 5m data, for
sizing expected_trades_per_week in the thesis spec. Labeled exploratory per
run instructions; numbers here are not a viable/pass claim.
"""
from research.swarm.lib import load_data

SYMS = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
W = 288  # 24h trailing window at 5m

results = {}
for sym in SYMS:
    df = load_data.load_ohlcv(sym, "5m", era="train", dataset="mr_edge")
    ret = df["close"].pct_change()
    abs_ret = ret.abs()
    vol_ref = abs_ret.rolling(W, min_periods=W).median().shift(1)
    vol_spike_ref = df["volume"].rolling(W, min_periods=W).median().shift(1)
    trigger = (abs_ret > 4 * vol_ref) & (df["volume"] > 2 * vol_spike_ref)
    n_trigger = int(trigger.sum())
    n_bars = len(df)
    weeks = n_bars * 5 / (60 * 24 * 7)
    results[sym] = {
        "n_trigger": n_trigger,
        "n_bars": n_bars,
        "weeks": round(weeks, 2),
        "trades_per_week": round(n_trigger / weeks, 3) if weeks else None,
    }

for sym, r in results.items():
    print(sym, r)

total_trig = sum(r["n_trigger"] for r in results.values())
weeks0 = list(results.values())[0]["weeks"]
print("TOTAL across 5 symbols:", total_trig, "per week (combined):", round(total_trig / weeks0, 3))
