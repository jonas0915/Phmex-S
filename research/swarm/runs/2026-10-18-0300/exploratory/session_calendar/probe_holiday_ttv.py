# EXPLORATORY — session_calendar lens, run 2026-10-18-0300. Not evidence. No market data read.
# Frequency ceiling for a US-federal-holiday event trade. ASSUMED CEILING (not measured):
# ~11 US federal holidays/yr x max_concurrent(sl) admitted names per event, i.e. every holiday fills every slot.
from research.swarm.lib import fee_math as f
for sl in (100, 150, 200, 300):
    mc = f.max_concurrent(sl)
    per_week_ceiling = 11 * mc / 52.0  # ASSUMED CEILING, labelled per LESSONS 2026-10-04
    print(f"sl={sl} max_concurrent={mc} per_week_ASSUMED_CEILING={per_week_ceiling:.3f} "
          f"time_to_verdict_weeks(n=50)={f.time_to_verdict_weeks(per_week_ceiling, 50):.2f}")
