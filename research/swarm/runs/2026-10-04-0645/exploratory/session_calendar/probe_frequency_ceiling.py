"""EXPLORATORY ONLY. Frequency ceiling for a month-end rebalancing thesis: at most
max_concurrent(sl) admitted trades per month-end event (one event per month)."""
from research.swarm.lib import fee_math as f
for sl in (100, 150, 200):
    mc = f.max_concurrent(sl)
    per_week = mc * 12 / 52
    print(f"sl={sl} max_concurrent={mc} trades_per_week_ceiling={per_week} time_to_verdict_weeks={f.time_to_verdict_weeks(per_week)}")
