"""
EXPLORATORY probe (label: exploratory, NOT a screen, NOT evidence for any thesis pass/fail).
Lens: owner-record (analyst #8/8), run 2026-09-20-0300.

Reads research/swarm/kb/owner_trades/api_closed_pnl.json (819 closed positions on Phemex
COIN-MARGINED inverse contracts, 2022-03-25 -> 2023-02-15 PT) and, if present,
api_deposit_list_full.json / api_withdraw_list_full.json.

All numbers below are read directly from these files; no hand-rolled statistics are used
for anything that will be cited as evidence (bootstrap CI / p* live in research.swarm.lib and
are NOT invoked here because this is a pre-screen exploratory probe of a non-screenable
2022 inverse-contract dataset, not a train-era screen candidate).

Output written to: research/swarm/runs/2026-09-20-0300/theses/owner_record_probe.json
"""
import json
import datetime as dt
from pathlib import Path
from collections import defaultdict

KB = Path("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/kb/owner_trades")
OUT = Path("/Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-20-0300/theses/owner_record_probe.json")

pnl_path = KB / "api_closed_pnl.json"
dep_path = KB / "api_deposit_list_full.json"
wd_path = KB / "api_withdraw_list_full.json"

rows = json.loads(pnl_path.read_text())
n = len(rows)

# NOTE: despite the field name "*TimeNs", empirical check against SOURCES.md's cited
# earliest row (id 1937714, LUNAOLDUSD, documented earliest = 2022-03-26 06:11:32 UTC)
# confirms these fields are actually MILLISECOND epoch timestamps, not nanoseconds:
# 1648275092166 ms -> 2022-03-26 06:11:32.166 UTC (matches exactly); as ns it would be 1970.
def ns_to_dt(ns):
    return dt.datetime.utcfromtimestamp(int(ns) / 1e3)

# sort chronologically by openedTimeNs (per SOURCES.md field list)
rows_sorted = sorted(rows, key=lambda r: int(r["openedTimeNs"]))

# realizedPnlEv / 1e4 = USD, per SOURCES.md sec 2b (verified two independent ways there)
for r in rows_sorted:
    r["_pnl_usd"] = int(r["realizedPnlEv"]) / 1e4
    r["_opened_dt"] = ns_to_dt(r["openedTimeNs"])
    r["_closed_dt"] = ns_to_dt(r["updatedTimeNs"])
    r["_hold_s"] = (int(r["updatedTimeNs"]) - int(r["openedTimeNs"])) / 1e3

# ---- cumulative realized PnL path (fallback: true equity requires converting 112 deposit
# rows across multiple non-USD currencies (XRP, ADA, MATIC, ETH, etc, see below) to USD at
# their historical prices; no historical FX/price source for those assets/dates is available
# in this research environment (fetch_ohlcv_ccxt is committee-token gated and out of scope
# for this research stage per the mandate) -> would require fabricating conversion rates,
# which is forbidden. Falling back to cumulative realized PnL only, as instructed.
cum = 0.0
cum_path = []
for r in rows_sorted:
    cum += r["_pnl_usd"]
    cum_path.append((r["_opened_dt"].isoformat(), round(cum, 2)))

# deposit/withdraw files: present, but currency-mixed, no USD-value field in raw rows
dep_present = dep_path.exists()
wd_present = wd_path.exists()
dep_currencies = None
wd_currencies = None
if dep_present:
    deps = json.loads(dep_path.read_text())
    dep_currencies = sorted({d["currency"] for d in deps})
if wd_present:
    wds = json.loads(wd_path.read_text())
    wd_currencies = sorted({w["currency"] for w in wds})

# ---- win rate / payoff ----
wins = [r for r in rows_sorted if r["_pnl_usd"] > 0]
losses = [r for r in rows_sorted if r["_pnl_usd"] < 0]
flats = [r for r in rows_sorted if r["_pnl_usd"] == 0]
win_rate = len(wins) / n
avg_win = sum(r["_pnl_usd"] for r in wins) / len(wins) if wins else 0.0
avg_loss = sum(r["_pnl_usd"] for r in losses) / len(losses) if losses else 0.0
payoff_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else None

# ---- concentration ----
total_positive_pnl = sum(r["_pnl_usd"] for r in wins)
pnl_desc = sorted(rows_sorted, key=lambda r: r["_pnl_usd"], reverse=True)
largest_trade_pnl = pnl_desc[0]["_pnl_usd"]
top5_pnl = sum(r["_pnl_usd"] for r in pnl_desc[:5])
share_largest = largest_trade_pnl / total_positive_pnl if total_positive_pnl else None
share_top5 = top5_pnl / total_positive_pnl if total_positive_pnl else None

# ---- median hold ----
holds_s = sorted(r["_hold_s"] for r in rows_sorted)
mid = len(holds_s) // 2
if len(holds_s) % 2 == 0:
    median_hold_s = (holds_s[mid - 1] + holds_s[mid]) / 2
else:
    median_hold_s = holds_s[mid]

# ---- symbols ----
symbol_counts = defaultdict(int)
symbol_pnl = defaultdict(float)
for r in rows_sorted:
    symbol_counts[r["symbol"]] += 1
    symbol_pnl[r["symbol"]] += r["_pnl_usd"]
symbols_by_count = sorted(symbol_counts.items(), key=lambda kv: -kv[1])
symbols_by_pnl = sorted(symbol_pnl.items(), key=lambda kv: -kv[1])

# ---- side split ---- (Phemex side: "1"=Buy/Long, "2"=Sell/Short per ccxt phemex convention)
side_counts = defaultdict(int)
side_pnl = defaultdict(float)
for r in rows_sorted:
    side_counts[r["side"]] += 1
    side_pnl[r["side"]] += r["_pnl_usd"]

# ---- time of day (UTC hour of open) ----
hour_counts = defaultdict(int)
hour_pnl = defaultdict(float)
for r in rows_sorted:
    h = r["_opened_dt"].hour
    hour_counts[h] += 1
    hour_pnl[h] += r["_pnl_usd"]

# ---- behaviour after a loss: size / side / hold of the NEXT trade ----
after_loss_next_sizes = []
after_loss_next_holds = []
after_loss_side_same = 0
after_loss_side_diff = 0
after_win_next_sizes = []
for i in range(len(rows_sorted) - 1):
    cur = rows_sorted[i]
    nxt = rows_sorted[i + 1]
    if cur["_pnl_usd"] < 0:
        after_loss_next_sizes.append(float(nxt["closedSize"]))
        after_loss_next_holds.append(nxt["_hold_s"])
        if nxt["side"] == cur["side"]:
            after_loss_side_same += 1
        else:
            after_loss_side_diff += 1
    elif cur["_pnl_usd"] > 0:
        after_win_next_sizes.append(float(nxt["closedSize"]))

avg_size_after_loss = sum(after_loss_next_sizes) / len(after_loss_next_sizes) if after_loss_next_sizes else None
avg_size_after_win = sum(after_win_next_sizes) / len(after_win_next_sizes) if after_win_next_sizes else None
avg_size_all = sum(float(r["closedSize"]) for r in rows_sorted) / n

# ---- the "Nov 2022 spike" window (flagged qualitatively in SOURCES.md sec 2b) ----
nov2022 = [r for r in rows_sorted if r["_opened_dt"].year == 2022 and r["_opened_dt"].month == 11]
nov2022_pnl = sum(r["_pnl_usd"] for r in nov2022)
nov2022_n = len(nov2022)

result = {
    "_label": "EXPLORATORY PROBE — not a screen, not evidence for any thesis verdict",
    "source_file": str(pnl_path),
    "n_rows": n,
    "date_range": [rows_sorted[0]["_opened_dt"].isoformat(), rows_sorted[-1]["_opened_dt"].isoformat()],
    "equity_path_method": "cumulative_realized_pnl_only",
    "equity_path_method_reason": (
        "deposit/withdraw files ARE present (api_deposit_list_full.json 112 rows, "
        "api_withdraw_list_full.json 68 rows) but deposits/withdrawals are denominated in "
        "mixed currencies (see dep_currencies/wd_currencies below) with no USD-value field "
        "in the raw rows and no historical price source available in this research stage "
        "(fetch_ohlcv_ccxt is committee-token gated, per research/swarm/kb/DATA.md) to convert "
        "them to USD without fabricating rates. Falling back to cumulative realized PnL per "
        "the task's explicit fallback instruction."
    ),
    "dep_file_present": dep_present,
    "wd_file_present": wd_present,
    "dep_currencies": dep_currencies,
    "wd_currencies": wd_currencies,
    "cumulative_realized_pnl_final_usd": round(cum, 2),
    "cumulative_realized_pnl_path_sample_every_100th": cum_path[::100] + [cum_path[-1]],
    "win_rate": {"value": round(win_rate, 4), "n_wins": len(wins), "n_losses": len(losses), "n_flat": len(flats), "field": "realizedPnlEv/1e4 > 0, source: api_closed_pnl.json"},
    "payoff_ratio": {"value": round(payoff_ratio, 4) if payoff_ratio else None, "avg_win_usd": round(avg_win, 2), "avg_loss_usd": round(avg_loss, 2), "field": "realizedPnlEv/1e4, source: api_closed_pnl.json"},
    "concentration": {
        "total_positive_pnl_usd": round(total_positive_pnl, 2),
        "largest_trade_pnl_usd": round(largest_trade_pnl, 2),
        "largest_trade_symbol": pnl_desc[0]["symbol"],
        "largest_trade_opened": pnl_desc[0]["_opened_dt"].isoformat(),
        "share_of_total_positive_pnl_from_largest_trade": round(share_largest, 4) if share_largest else None,
        "top5_pnl_usd": round(top5_pnl, 2),
        "share_of_total_positive_pnl_from_top5_trades": round(share_top5, 4) if share_top5 else None,
        "field": "realizedPnlEv/1e4, source: api_closed_pnl.json, ranked descending",
    },
    "median_hold_seconds": round(median_hold_s, 1),
    "median_hold_human": str(dt.timedelta(seconds=round(median_hold_s))),
    "median_hold_field": "updatedTimeNs - openedTimeNs, source: api_closed_pnl.json",
    "symbols_by_trade_count_top10": symbols_by_count[:10],
    "symbols_by_pnl_top10": symbols_by_pnl[:10],
    "side_split": {"counts_by_side_code": dict(side_counts), "pnl_by_side_code_usd": {k: round(v, 2) for k, v in side_pnl.items()}, "field": "side (Phemex 1=Buy/Long, 2=Sell/Short), realizedPnlEv/1e4, source: api_closed_pnl.json"},
    "time_of_day_utc_hour": {"counts": dict(sorted(hour_counts.items())), "pnl_usd": {k: round(v, 2) for k, v in sorted(hour_pnl.items())}, "field": "openedTimeNs -> UTC hour, source: api_closed_pnl.json"},
    "behaviour_after_a_loss": {
        "n_loss_events_with_next_trade": len(after_loss_next_sizes),
        "avg_next_trade_size_after_loss": round(avg_size_after_loss, 3) if avg_size_after_loss else None,
        "avg_next_trade_size_after_win": round(avg_size_after_win, 3) if avg_size_after_win else None,
        "avg_trade_size_all": round(avg_size_all, 3),
        "avg_next_trade_hold_seconds_after_loss": round(sum(after_loss_next_holds) / len(after_loss_next_holds), 1) if after_loss_next_holds else None,
        "next_trade_same_side_as_losing_trade_count": after_loss_side_same,
        "next_trade_diff_side_from_losing_trade_count": after_loss_side_diff,
        "field": "closedSize / side / (updatedTimeNs-openedTimeNs) of the chronologically next row after each losing row, source: api_closed_pnl.json",
    },
    "nov_2022_window_note": {
        "n_trades": nov2022_n,
        "pnl_usd": round(nov2022_pnl, 2),
        "note": "SOURCES.md sec 2b flags a qualitative cumulative-PnL jump to +$5405 by Nov 2022 (single large win) coinciding with the Nov 2022 FTX-contagion crash window; this is descriptive only, not a statistical claim.",
    },
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(result, indent=2, default=str))
print(json.dumps(result, indent=2, default=str))
