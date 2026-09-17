"""EXPLORATORY probe (NOT the screen; numbers are not evidence). long_1h train era only.
Runs signal_shock_drift on every long_1h symbol, simulates with lib.screen.simulate at
the candidate geometry, and reports lib-computed stats. No mr_edge data is touched."""
import json, sys, importlib.util
from pathlib import Path
import pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, fee_math as fm, bootstrap_ci as bc

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("sig", HERE / "signal_shock_drift.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

TP, SL, HOLD = float(sys.argv[1]) if len(sys.argv) > 1 else 200.0, float(sys.argv[2]) if len(sys.argv) > 2 else 200.0, int(sys.argv[3]) if len(sys.argv) > 3 else 72
syms = ld.list_symbols("long_1h")
rows, fires = [], {}
for s in syms:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    sig = mod.signals(df)
    assert set(sig.unique()) <= {-1, 0, 1}
    sc.causality_check(mod.signals, df, symbol=s)
    fires[s] = int((sig != 0).sum())
    tr = sc.simulate(df, sig, TP, SL, HOLD)
    tr.insert(0, "symbol", s)
    rows.append(tr)
trades = pd.concat(rows, ignore_index=True)
span = (df.index.max() - df.index.min()).total_seconds() / (7 * 86400)
n = len(trades)
out = {
    "label": "EXPLORATORY — not evidence", "dataset": "long_1h", "era": "train", "tp": TP, "sl": SL, "hold": HOLD,
    "n": n, "fires_per_symbol": fires,
    "net_bps_mean": float(trades.net_bps.mean()), "ci95": list(bc.mean_ci(trades.net_bps.to_numpy())),
    "wr": float((trades.net_bps > 0).mean()), "p_star": fm.p_star(TP),
    "trades_per_week": n / span, "time_to_verdict_weeks": fm.time_to_verdict_weeks(n / span),
    "by_side": {int(k): {"n": int(len(g)), "net": float(g.net_bps.mean())} for k, g in trades.groupby("side")},
    "exit_reasons": trades.exit_reason.value_counts().to_dict(),
    "causality": "PASS",
}
tag = f"{int(TP)}_{int(SL)}_{HOLD}"
trades.to_csv(HERE / f"probe_shock_drift_trades_{tag}.csv", index=False)
(HERE / f"probe_shock_drift_out_{tag}.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
