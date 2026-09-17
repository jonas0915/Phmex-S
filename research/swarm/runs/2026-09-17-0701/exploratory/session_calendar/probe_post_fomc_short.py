"""EXPLORATORY probe (NOT the screen; numbers are not evidence).
Post-FOMC 48h short on long_1h TRAIN era only. Signal bar = the 1h bar containing the
FOMC statement release (14:00 America/New_York on decision day); enter at next bar open,
short, TP/SL 200/200, max 48 bars. FOMC dates from federalreserve.gov calendar (fetched this run).
"""
import json, sys
import pandas as pd
from research.swarm.lib import load_data as ld, screen as sc, bootstrap_ci as bc, fee_math as fm

FOMC_DECISION_DAYS = ["2025-01-29","2025-03-19","2025-05-07","2025-06-18","2025-07-30","2025-09-17","2025-10-29","2025-12-10",
                      "2026-01-28","2026-03-18","2026-04-29","2026-06-17","2026-07-29","2026-09-16","2026-10-28","2026-12-09",
                      "2027-01-27","2027-03-17","2027-04-28","2027-06-09","2027-07-28","2027-09-15","2027-10-27","2027-12-08"]
STAMPS = set(pd.Timestamp(d + " 14:00", tz="America/New_York").tz_convert("UTC").floor("h") for d in FOMC_DECISION_DAYS)

def signals(df):
    s = pd.Series(0, index=df.index, dtype=int)
    s[df.index.isin(list(STAMPS))] = -1
    return s

rows = []
syms = ld.list_symbols("long_1h")
lo, hi = None, None
for sym in syms:
    df = ld.load_ohlcv(sym, "1h", era="train", dataset="long_1h")
    lo = df.index.min() if lo is None else min(lo, df.index.min()); hi = df.index.max() if hi is None else max(hi, df.index.max())
    tr = sc.simulate(df, signals(df), 200, 200, 48); tr.insert(0, "symbol", sym); rows.append(tr)
t = pd.concat(rows, ignore_index=True)
weeks = (hi - lo).total_seconds()/(7*86400)
out = {"label": "EXPLORATORY probe, not evidence", "n": int(len(t)),
       "net_bps_mean": float(t.net_bps.mean()), "ci95": list(bc.mean_ci(t.net_bps.to_numpy())),
       "wr": float((t.net_bps > 0).mean()), "p_star_200": fm.p_star(200),
       "trades_per_week_in_train": len(t)/weeks, "ttv_weeks_at_train_rate": fm.time_to_verdict_weeks(len(t)/weeks),
       "ttv_weeks_at_8x19_per_year": fm.time_to_verdict_weeks(8*19/52),
       "per_event": {str(k.date()): {"n": int(len(g)), "net": float(g.net_bps.mean())} for k, g in t.groupby(t.entry_ts.dt.floor("D"))},
       "exit_reasons": t.exit_reason.value_counts().to_dict()}
print(json.dumps(out, indent=1)); json.dump(out, open(sys.argv[1], "w"), indent=1)
