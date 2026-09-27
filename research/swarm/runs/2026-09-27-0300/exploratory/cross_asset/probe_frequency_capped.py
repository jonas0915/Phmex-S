"""EXPLORATORY frequency probe (long_1h TRAIN only): events per Monday, capped at
fee_math.max_concurrent(150), and time_to_verdict at that rate. Not the screen."""
import importlib.util, sys
import pandas as pd
from research.swarm.lib import load_data as ld, fee_math as f
sp = importlib.util.spec_from_file_location("s", sys.argv[1]); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
cnt = pd.Series(dtype=int); span = None
for s in ["BTC", "ETH", "SOL", "XRP", "DOGE"]:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h"); sig = m.signals(df)
    ev = sig[sig != 0]; cnt = cnt.add(pd.Series(1, index=ev.index), fill_value=0)
    span = (df.index.max() - df.index.min()).total_seconds() / (7 * 86400)
k = f.max_concurrent(150)
capped = cnt.clip(upper=k).sum()
rate = capped / span
print("max_concurrent(150)=", k, "p_star(150)=", f.p_star(150))
print("mondays_with_event", len(cnt), "events_per_monday_distribution", cnt.value_counts().sort_index().to_dict())
print("capped_events", int(capped), "train_weeks", span, "capped_rate_per_week", rate, "time_to_verdict_weeks", f.time_to_verdict_weeks(rate))
