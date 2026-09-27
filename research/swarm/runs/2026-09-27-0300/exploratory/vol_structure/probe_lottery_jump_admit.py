"""EXPLORATORY probe (not the screen). long_1h TRAIN only. Applies screen.admit_trades
under fee_math.max_concurrent(sl) to the lottery-jump fade, and reports date clustering."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld, screen, fee_math as fm, bootstrap_ci as bc
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-27-0300/exploratory/vol_structure")
from probe_lottery_jump import SYMS, sig_jump

frames = {s: ld.load_ohlcv(s, "1h", era="train", dataset="long_1h") for s in SYMS}
for k, fl in [(2.5, 0.06), (2.0, 0.05)]:
    sigs = {s: sig_jump(frames[s], k, fl) for s in SYMS}
    fires = pd.concat([v[v != 0] for v in sigs.values()])
    days = fires.index.normalize().value_counts()
    print(f"k={k}: fire-days={len(days)} fires={len(fires)} max fires/day={days.max()} top days={days.head(5).to_dict()}")
    for tp, sl, hold in [(200, 200, 72), (200, 200, 168), (300, 300, 168), (300, 300, 72)]:
        ts = []
        for s in SYMS:
            t = screen.simulate(frames[s], sigs[s], tp, sl, hold); t["symbol"] = s; ts.append(t)
        t = pd.concat(ts)
        mc = fm.max_concurrent(sl)
        a = screen.admit_trades(t, mc, SYMS)
        weeks = (frames["BTC"].index.max() - frames["BTC"].index.min()).days / 7
        lo, hi = bc.mean_ci(a.net_bps.values) if len(a) > 1 else (None, None)
        print(f"  tp{tp}/sl{sl}/h{hold} mc={mc}: raw n={len(t)} mean={t.net_bps.mean():.1f} | admitted n={len(a)} mean={a.net_bps.mean():.1f} ci=[{lo:.1f},{hi:.1f}] WR={(a.net_bps>0).mean():.3f} p*={fm.p_star(tp):.4f} tpw={len(a)/weeks:.2f} ttv={fm.time_to_verdict_weeks(len(a)/weeks):.1f}")
