"""EXPLORATORY ONLY — not the screen. Runs screen.simulate with the candidate signal on
long_1h TRAIN to choose tp/sl/hold within the 100-300 bps band. Also reports date-clustering
of events (distinct UTC days, top-day share). No mr_edge data touched."""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld, screen as sc, bootstrap_ci as bc, fee_math as fm
SYMS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","BTC","DOGE","ETH","GIGGLE","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]

def make_sig(k, v):
    def signals(df):
        r = df["close"].pct_change()
        sd = r.rolling(168, min_periods=100).std().shift(1)
        vm = df["volume"].rolling(168, min_periods=100).median().shift(1)
        down = (r <= -k * sd) & (df["volume"] >= v * vm)
        return pd.Series(np.where(down, -1, 0), index=df.index).astype(int)
    return signals

frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in SYMS}
res = {}
for k, v in ((4.0, 2.0), (3.0, 2.0)):
    sig = make_sig(k, v)
    for tp, sl, hold in ((200, 200, 24), (150, 150, 24), (250, 250, 24), (200, 200, 12), (300, 300, 36)):
        trs = []
        for s, df in frames.items():
            t = sc.simulate(df, sig(df), tp, sl, hold); t.insert(0, "symbol", s); trs.append(t)
        T = pd.concat(trs, ignore_index=True)
        n = len(T); x = T.net_bps.to_numpy()
        days = pd.to_datetime(T.entry_ts).dt.floor("D")
        top = days.value_counts()
        key = f"k{k}_v{v}_tp{tp}_sl{sl}_h{hold}"
        res[key] = {"n": n, "net_mean": float(x.mean()), "ci95": list(bc.mean_ci(x)), "wr": float((x > 0).mean()),
                    "p_star": fm.p_star(tp), "distinct_days": int(days.nunique()), "top_day": str(top.index[0].date()), "top_day_n": int(top.iloc[0]),
                    "net_ex_top_day_mean": float(T[days != top.index[0]].net_bps.mean()),
                    "exit_mix": T.exit_reason.value_counts().to_dict()}
        print(key, json.dumps({a: (round(b, 3) if isinstance(b, float) else b) for a, b in res[key].items()}, default=str))
json.dump(res, open("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0701/exploratory/forced_flows/probe2_summary.json", "w"), indent=2, default=str)
