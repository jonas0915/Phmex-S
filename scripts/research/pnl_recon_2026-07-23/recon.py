#!/usr/bin/env python3
"""PnL reconciliation 7/20 9:56 PM PT boot -> 7/23. Read-only.

Reproduces the numbers in the 2026-07-23 forensic reconciliation:
- live closed trades per book from state files (HTF_L2 mode=='live' only;
  main book has no mode field ever -> all live; 5m_MR mode=='live')
- balance step series from '=== STATS ===' lines (exchange wallet truth)
Anchors: bot.log.1:80127 boot 40.24 | bot.log 7/22 17:55:01 32.23 | 7/23 STATS 33.95
HTF_L2 demoted to paper: bot.log:11267 (7/22 11:34:14, live loss cap -6.22).
"""
import json, datetime, re
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = "/Users/jonaspenaso/Desktop/Phmex-S"
START = datetime.datetime(2026, 7, 20, 21, 56, 46, tzinfo=PT).timestamp()

books = {"MAIN": "trading_state.json",
         "HTF_L2": "trading_state_HTF_L2.json",
         "5m_MR": "trading_state_5m_mean_revert.json"}
tot = 0.0
for b, f in books.items():
    for t in json.load(open(f"{ROOT}/{f}"))["closed_trades"]:
        if t.get("closed_at", 0) < START:
            continue
        is_live = t.get("mode") == "live" if b != "MAIN" else True
        if not is_live:
            continue
        d = datetime.datetime.fromtimestamp(t["closed_at"], PT)
        print(f"{b:6} {d:%a %m-%d %I:%M%p} {t['symbol']:20} {t['side']:5} "
              f"net={t['net_pnl']:+.3f} fees={t['fees_usdt']:.3f} {t['exit_reason']}")
        tot += t["net_pnl"]
print(f"TOTAL live net = {tot:+.3f}  | balance delta 40.24->33.95 = -6.29 "
      f"| residual = {(-6.29) - tot:+.3f} (funding + fee-estimate drift, "
      f"see STATS balance series)")
