"""EXPLORATORY sanity check of the candidate signal_py (the exact text registered in the
thesis JSON): value set, nonzero counts per symbol, screen.causality_check on every symbol,
lot_check at $200, trades/week and time_to_verdict from lib. long_1h TRAIN only."""
import sys, json
import numpy as np, pandas as pd
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm
SIG = open("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0701/exploratory/forced_flows/candidate_signal.py").read()
ns = {}; exec(SIG, ns); signals = ns["signals"]
SYMS = ["1000PEPE","1000SHIB","AAVE","ADA","BNB","BTC","DOGE","ETH","GIGGLE","LINK","LTC","NEAR","ONDO","SOL","SUI","TAO","UNI","XLM","XRP"]
out = {"per_symbol": {}, "lot_check": {}, "causality": {}}
tot = 0; t0 = None; t1 = None
for s in SYMS:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    sig = signals(df)
    vals = sorted(set(sig.dropna().unique().tolist()))
    nz = int((sig != 0).sum()); tot += nz
    out["per_symbol"][s] = {"bars": int(len(df)), "values": vals, "nonzero": nz, "span": [str(df.index.min()), str(df.index.max())]}
    t0 = df.index.min() if t0 is None else min(t0, df.index.min()); t1 = df.index.max() if t1 is None else max(t1, df.index.max())
    sc.causality_check(signals, df, symbol=s); out["causality"][s] = "PASS"
    out["lot_check"][s] = fm.lot_check(s, fm.position_notional())
weeks = (t1 - t0).total_seconds() / (7 * 86400)
out["train_span"] = [str(t0), str(t1)]; out["train_weeks"] = weeks
out["total_signal_bars"] = tot
out["signal_bars_per_week"] = tot / weeks
out["probe2_trades_k3_v2_tp300_h36"] = 576
out["probe2_trades_per_week"] = 576 / weeks
out["time_to_verdict_weeks_at_probe2_rate"] = fm.time_to_verdict_weeks(576 / weeks)
out["p_star_300"] = fm.p_star(300); out["p_star_240"] = fm.p_star(240); out["p_star_360"] = fm.p_star(360)
json.dump(out, open("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0701/exploratory/forced_flows/probe3_sanity.json", "w"), indent=2, default=str)
print(json.dumps({k: v for k, v in out.items() if k != "per_symbol"}, indent=1, default=str))
print({s: v["nonzero"] for s, v in out["per_symbol"].items()})
