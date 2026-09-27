"""EXPLORATORY probe (not the screen). long_1h TRAIN only (load_reference outside a
screen context = plain train load). Idiosyncratic (BTC-relative) upside-jump fade."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld, screen, fee_math as fm, bootstrap_ci as bc

ALTS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","DOGE","ETH","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]

def sig_idio(df, k=2.5, floor=0.05, look=60):
    ref = ld.load_reference("BTC", "1h", "long_1h")["close"]
    ref = ref.reindex(df.index).ffill()
    c = df["close"]
    ex = np.log(c / c.shift(24)) - np.log(ref / ref.shift(24))
    daily = ex[df.index.hour == 0]
    sd = daily.rolling(look, min_periods=30).std().shift(1)
    jump = (daily >= k * sd) & (daily >= floor)
    fire = jump.shift(1, fill_value=False)
    out = pd.Series(0, index=df.index)
    out.loc[fire[fire].index] = -1
    return out

frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in ALTS}
weeks = (frames["ETH"].index.max() - frames["ETH"].index.min()).days / 7
for k, fl in [(2.5, 0.05), (2.0, 0.04), (2.0, 0.05)]:
    sigs = {s: sig_idio(frames[s], k, fl) for s in ALTS}
    fires = pd.concat([v[v != 0] for v in sigs.values()])
    days = fires.index.normalize().value_counts()
    print(f"k={k} fl={fl}: fires={len(fires)} fire-days={len(days)} max/day={days.max()} top={days.head(4).to_dict()}")
    for tp, sl, hold in [(200, 200, 72), (150, 150, 48), (300, 300, 168)]:
        ts = []
        for s in ALTS:
            t = screen.simulate(frames[s], sigs[s], tp, sl, hold); t["symbol"] = s; ts.append(t)
        t = pd.concat(ts)
        mc = fm.max_concurrent(sl)
        a = screen.admit_trades(t, mc, ALTS)
        lo, hi = bc.mean_ci(a.net_bps.values) if len(a) > 1 else (np.nan, np.nan)
        print(f"  tp{tp}/sl{sl}/h{hold} mc={mc}: raw n={len(t)} mean={t.net_bps.mean():.1f} | adm n={len(a)} mean={a.net_bps.mean():.1f} ci=[{lo:.1f},{hi:.1f}] WR={(a.net_bps>0).mean():.3f} p*={fm.p_star(tp):.4f} tpw={len(a)/weeks:.2f} ttv={fm.time_to_verdict_weeks(len(a)/weeks):.1f} exits={a.exit_reason.value_counts().to_dict()}")
