"""EXPLORATORY ONLY (cross_asset lens). Frequency of the candidate signal on long_1h TRAIN (no PnL).
Also prints fee_math values used in the thesis."""
import pandas as pd, numpy as np
from research.swarm.lib import load_data as ld, fee_math as fm
U = ["BTC","ETH","SOL","XRP","DOGE","LINK","LTC","ADA","BNB","AAVE","UNI","SUI","NEAR","XLM","TAO","ONDO","1000PEPE","1000SHIB"]
ev = []
span = None
for s in U:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    span = (df.index[0], df.index[-1])
    r = np.log(df.close/df.open); ny = df.index.tz_convert("America/New_York")
    rr = r[(ny.hour == 15) & (ny.dayofweek < 5)]
    z = rr / rr.rolling(40, min_periods=20).std().shift(1)
    for t in z[z.abs() > 1.5].index: ev.append((s, t))
e = pd.DataFrame(ev, columns=["sym","ts"])
weeks = (span[1]-span[0]).days/7
mc = fm.max_concurrent(150)
days = e.groupby("ts").size()
admitted_upper = days.clip(upper=mc).sum()
print("train span", span, "weeks", round(weeks,1))
print("events", len(e), "event_days", len(days), "events/wk", round(len(e)/weeks,2))
print("max_concurrent(150)", mc, "admitted upper bound", admitted_upper, "per wk", round(admitted_upper/weeks,2))
print("p_star(150)", fm.p_star(150), "ttv(adm/wk)", fm.time_to_verdict_weeks(admitted_upper/weeks))
print({s: fm.lot_check(s, fm.position_notional()) for s in U})
