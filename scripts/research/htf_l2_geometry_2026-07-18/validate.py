#!/usr/bin/env python3
"""Rig fidelity check: simulate the LIVE geometry (SL12/TP16/partial-on/arm8)
and compare per-position vs the actual ledger. Also reproduce the round-2
SL@-8 gross measurement direction (memory: -$3.19 gross @-8 vs -$12.48 @-12 on the
June-era 5m rig; ours is 1m, fee-inclusive, 205 merged positions)."""
import json, os
import numpy as np
import sim_geometry as S

HERE = os.path.dirname(os.path.abspath(__file__))
positions = S.positions
CANDLES = [S.load_candles(i) for i in range(len(positions))]

live = (12.0, 16.0, True, 8.0)
rows = []
for i, p in enumerate(positions):
    if not CANDLES[i]:
        continue
    net, reason, _ = S.simulate(p, CANDLES[i], *live)
    rows.append((i, p["symbol"], p["exit_reason"], p["actual_net"], net, reason))

sim_net = sum(r[4] for r in rows)
act_net = sum(r[3] for r in rows)
print(f"n={len(rows)}  actual net ${act_net:.2f}  sim(live-geom) net ${sim_net:.2f}")
geom = [r for r in rows if r[2] in S.GEOM]
print(f"geometry-exit trades n={len(geom)}: actual ${sum(r[3] for r in geom):.2f} sim ${sum(r[4] for r in geom):.2f}")
sgn_agree = sum(1 for r in geom if (r[3] > 0) == (r[4] > 0))
print(f"sign agreement on geometry-exit trades: {sgn_agree}/{len(geom)}")
corr = np.corrcoef([r[3] for r in geom], [r[4] for r in geom])[0, 1]
print(f"per-trade $ correlation (geometry-exit): {corr:.3f}")

# gross SL comparison (trail off, partial off, no TP cap changes): SL-only counterfactual grid
for sl in (8.0, 12.0):
    tot = 0.0
    for i, p in enumerate(positions):
        if not CANDLES[i]:
            continue
        net, reason, _ = S.simulate(p, CANDLES[i], sl, 16.0, True, 8.0)
        tot += net
    print(f"SL@-{sl:.0f} (TP16/partial/arm8, fee-incl) net: ${tot:.2f}")
