"""EXPLORATORY (not the screen, not evidence). Trade-count only (PnL deliberately NOT printed) for the
draft signal at the intended spec (tp=sl=150, max_hold 24 x 1h) on long_1h TRAIN for the 5 lot-verified
symbols, under the fee_math.max_concurrent(150) cap, plus screen.causality_check on each symbol, plus
confirmation that those 5 symbols exist in mr_edge at 1h (index bounds of mr_edge train only)."""
from pathlib import Path
import pandas as pd
from research.swarm.lib import load_data, screen, fee_math
D = Path(__file__).parent
sig = screen.load_signal_fn(D / "sweep_signal_draft.py")
U = ["BTC", "ETH", "SOL", "XRP", "DOGE"]
mc = fee_math.max_concurrent(150); print("max_concurrent(150) =", mc)
tr = []
for s in U:
    df = load_data.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    screen.causality_check(sig, df, symbol=s)
    v = sig(df); assert set(v.unique()) <= {-1, 0, 1}
    t = screen.simulate(df, v, 150, 150, 24); t["symbol"] = s; tr.append(t)
    print(s, "long_1h train signals nonzero:", int((v != 0).sum()), "trades:", len(t), "causality OK")
t = pd.concat(tr); adm = screen.admit_trades(t, mc, U)
weeks = (t.entry_ts.max() - t.entry_ts.min()).days / 7
print("raw trades", len(t), "admitted", len(adm), "weeks", round(weeks, 2), "admitted/week", round(len(adm) / weeks, 2))
print("time_to_verdict_weeks(admitted/week) =", fee_math.time_to_verdict_weeks(len(adm) / weeks))
for s in U:
    m = load_data.load_ohlcv(s, "1h", era="train", dataset="mr_edge")
    print("mr_edge train", s, m.index.min(), m.index.max(), len(m), "bars")
print("p_star(150) =", fee_math.p_star(150), "p_star(120) =", fee_math.p_star(120), "p_star(180) =", fee_math.p_star(180))
print("lot_check:", {s: fee_math.lot_check(s, fee_math.position_notional()) for s in U})
