import sys, pandas as pd
sys.path.insert(0, 'research/swarm/runs/2026-09-17-0732/exploratory/session_calendar')
from signal_weekend_thinbook_fade import signals
from research.swarm.lib import load_data as ld, screen, fee_math as fm
syms = [s for s in ld.list_symbols('long_1h') if s != 'GIGGLE']
tot = 0
for s in syms:
    df = ld.load_ohlcv(s, '1h', era='train', dataset='long_1h')
    sig = signals(df)
    vals = sorted(set(sig.unique().tolist()))
    screen.causality_check(signals, df, symbol=s)
    nz = int((sig != 0).sum()); tot += nz
    print(f"{s}: bars={len(df)} span={df.index.min()}..{df.index.max()} values={vals} nonzero={nz} causality=PASS lot_check={fm.lot_check(s, fm.position_notional())}")
weeks = 43  # distinct Sunday-23:00 bars in the shared train window (probe_weekend_gap.out.txt)
print("total nonzero signals (train):", tot)
print("p_star(200) =", fm.p_star(200))
print("expected_trades_per_week (train count / 43 weeks) =", tot / weeks)
print("time_to_verdict_weeks at that rate =", fm.time_to_verdict_weeks(tot / weeks))
print("time_to_verdict_weeks at registered 3.0/wk =", fm.time_to_verdict_weeks(3.0))
print("C_BPS =", fm.C_BPS)
