"""EXPLORATORY (not the screen). long_1h TRAIN. Frequency check of the idio-jump fade at h168."""
import sys
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S"); sys.path.insert(0, ".")
import pandas as pd, numpy as np
from research.swarm.lib import load_data as ld, screen, fee_math as fm, bootstrap_ci as bc
import importlib.util
spec = importlib.util.spec_from_file_location("p", "probe_idio_jump.py")
src = open("probe_idio_jump.py").read().split("frames = ")[0]
ns = {}; exec(src, ns)
ALTS, sig_idio = ns["ALTS"], ns["sig_idio"]
frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in ALTS}
weeks = (frames["ETH"].index.max() - frames["ETH"].index.min()).days / 7
ts = []
for s in ALTS:
    t = screen.simulate(frames[s], sig_idio(frames[s], 2.0, 0.04), 200, 200, 168); t["symbol"] = s; ts.append(t)
a = screen.admit_trades(pd.concat(ts), fm.max_concurrent(200), ALTS)
lo, hi = bc.mean_ci(a.net_bps.values)
print(f"k2.0 fl0.04 tp200/sl200/h168 mc={fm.max_concurrent(200)} adm n={len(a)} mean={a.net_bps.mean():.1f} ci=[{lo:.1f},{hi:.1f}] WR={(a.net_bps>0).mean():.3f} tpw={len(a)/weeks:.2f} ttv={fm.time_to_verdict_weeks(len(a)/weeks):.1f} exits={a.exit_reason.value_counts().to_dict()}")
print("p*(200)=", fm.p_star(200), "lot_check:", {s: fm.lot_check(s, fm.position_notional())['ok'] for s in ALTS})
