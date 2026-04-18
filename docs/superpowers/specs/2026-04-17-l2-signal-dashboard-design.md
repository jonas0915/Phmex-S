# L2 Anticipation Signal Dashboard Panel — Design Spec
**Date:** 2026-04-17
**Status:** Approved
**Scope:** New dashboard panel showing live L2/tape signal readings per watched symbol, so Jonas can see which symbols are close to firing the `htf_l2_anticipation` strategy

---

## Problem Statement

The `htf_l2_anticipation` strategy evaluates three L2/tape signals on every cycle (buy_ratio, cvd_slope, bid_depth vs ask_depth) plus three boosters. When it doesn't fire, there's no way to tell whether it's because the setup is absent, or because one L2 signal is close but not crossing threshold. Making this visible helps build trust in the strategy and surface tuning opportunities.

---

## Architecture

Two-component feature matching the existing dashboard pattern:

1. **Bot writes snapshot** — `bot.py` writes `l2_snapshot.json` each main-loop cycle after fetching flow/orderbook for a symbol. Keyed by symbol, overwritten every cycle.
2. **Dashboard reads + renders** — `web_dashboard.py` gains a new panel builder that reads `l2_snapshot.json` and renders an HTML table. No new dependencies, no API calls.

---

## Component 1: Bot Snapshot Writer

### File location
`/Users/jonaspenaso/Desktop/Phmex-S/l2_snapshot.json` (top of project, same level as `trading_state.json`).

### File format
```json
{
  "updated_at": 1713398400,
  "symbols": {
    "BTC/USDT:USDT": {
      "buy_ratio": 0.58,
      "cvd_slope": 0.31,
      "bid_depth_usdt": 1234567,
      "ask_depth_usdt": 876543,
      "large_trade_bias": 0.12,
      "trade_count": 45,
      "last_price": 66800.5,
      "updated_at": 1713398400
    },
    "ETH/USDT:USDT": { ... },
    ...
  }
}
```

Atomically written: write to `l2_snapshot.json.tmp` then `os.replace()` to final path.

### Write point in `bot.py`

After the main strategy call (~line 940 area), collect the fetched `ob` and `flow` into an in-memory dict. At the end of the symbol loop, write the accumulated dict to `l2_snapshot.json`. One write per cycle, not per symbol — keeps I/O minimal.

Fields omitted if missing (e.g., if `flow` is None, entry for that symbol uses null values).

### Failure modes
- File doesn't exist yet → dashboard panel shows "no data yet"
- Stale snapshot (updated_at > 120s old) → dashboard shows warning banner
- Write fails (disk full, permission) → log warning, skip this cycle's snapshot (silent to bot)

---

## Component 2: Dashboard Panel

### Title
**📡 L2 Anticipation Signal Monitor**
Sub-header: "Live snapshot — updated {N}s ago"

### Position
Right column, after Watchlist, before Paper Comparison.

### Columns and thresholds

| Column | Threshold for 🟢 | Notes |
|---|---|---|
| `buy_ratio` | > 0.55 (long lean) OR < 0.45 (short lean) | Shows value + indicator |
| `cvd_slope` | > 0 (long) OR < 0 (short) | Shows sign + value |
| `depth bid/ask` | > 1.0 (bid heavy, long) OR < 1.0 (ask heavy, short) | Shows ratio `bid/ask` |
| `whale bias` | \|large_trade_bias\| > 0.2 | Shows 🐋 icon when booster active |
| `READY` | Count of 3 required passing | ✅ 3/3, 🟠 N/3, 🔴 0/3 |

### Color conventions (match existing dashboard CSS)
- 🟢 = passing threshold (green `#16a34a`)
- 🔴 = failing threshold (red `#dc2626`)
- ⚫ = stale data / no tape feed / trade_count < 5 (gray `#9ca3af`)
- 🐋 = whale booster active (prominent, any color)

### No-data state
If `l2_snapshot.json` is missing or empty: render panel with message "No L2 snapshot yet — bot is starting up or no pairs are being watched."

If snapshot is > 120s stale: render header with orange warning banner "Snapshot stale (last update Xs ago)".

### Direction inference
Since the panel can't know which direction the strategy would want (depends on HTF trend which the dashboard doesn't easily compute), the panel shows BOTH interpretations:
- buy_ratio cell shows: value + 🟢 if > 0.55 (long) or < 0.45 (short), 🔴 if in 0.45–0.55 no-mans-land
- cvd_slope cell shows: value + 🟢 if !=0 (meaningful flow), 🔴 if near zero (no momentum)
- depth cell shows: the ratio + 🟢 if |ratio-1| > 0.2 (meaningful imbalance), 🔴 if near parity
- READY counts "signals that are meaningfully non-neutral" — a proxy for "strategy could fire if HTF trend agrees"

This keeps the panel useful without the dashboard needing to know HTF trend.

---

## Data Flow

```
bot.py main loop (every 60s)
   ├─ fetches ob + flow per symbol (already does this)
   ├─ accumulates into l2_snapshot_dict
   └─ writes l2_snapshot.json (atomic, once per cycle)
           ↓
web_dashboard.py (every 20s HTTP refresh)
   ├─ reads l2_snapshot.json
   └─ renders panel HTML
```

---

## Failure / Edge Cases

| Scenario | Behavior |
|---|---|
| `l2_snapshot.json` missing | Panel shows "No L2 snapshot yet" |
| Snapshot > 120s stale | Warning banner shown, data still rendered |
| Symbol has no flow (trade_count < 5) | Row shows ⚫ across signal columns, status "no feed" |
| `bid_depth_usdt` or `ask_depth_usdt` is 0 | Ratio cell shows "—" |
| JSON parse error | Panel shows "Snapshot unreadable — check bot.log" |

---

## Affected Files

| File | Change |
|---|---|
| `bot.py` | Add snapshot dict accumulation in main loop + write function. ~30 lines. |
| `web_dashboard.py` | Add `_build_l2_monitor_panel()` function + call it in `build_content()`. ~80 lines. |
| `.gitignore` | Add `l2_snapshot.json` (runtime state, not versioned). |

---

## Success Criteria

- Panel visible on dashboard within 1 cycle of bot restart
- All 8 watched symbols show up in panel (or fewer if scanner returns less)
- Values update as tape activity changes (refresh every 20s, snapshot every 60s)
- Snapshot file stays small (< 10 KB for 8 symbols)
- No new errors in `bot.log` or dashboard request handler

---

## Out of Scope

- Historical L2 signal chart (just current snapshot for v1)
- Per-symbol drilldown modal
- Configurable thresholds in UI (hardcoded to match strategy)
- Alerts/notifications on threshold crossings
- Tracking "close to firing" over time (just point-in-time view)
