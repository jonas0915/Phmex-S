# Shadow Logging Time Filter — Design Spec

**Date:** 2026-03-27
**Status:** Approved
**Approach:** Log-only shadow tagging (Approach 1)

## Purpose

Tag every trade that opens outside the profitable time window so we can measure — without any risk — how much PnL would be saved by a time filter. The bot continues trading 24/7. Nothing is blocked.

## Background

V10 Pipeline data (59 trades, verified by 3 independent agents) shows:
- Early AM (12-6 AM PT): 69.2% WR, +$2.34
- Afternoon (12-8 PM PT): 27.3% WR, -$3.39
- If bot only traded during profitable hours, v10 would be +$9.47 instead of -$0.21

Amberdata institutional data confirms: 21:00 UTC (2 PM PT) has 42% less orderbook depth than 11:00 UTC peak. Losses correlate with liquidity trough.

However, 59 trades is too small to validate (need 1,000+ per bucket per Lopez de Prado). Shadow logging collects the proof before making any real changes.

## Profitable Window

**PT hours that stay "in window":** 23, 0, 1, 2, 3, 6, 9
**UTC equivalent:** 6, 7, 8, 9, 10, 13, 16

Everything else = shadow zone (trade executes but gets tagged).

## Implementation

### 1. bot.py — Shadow flag at entry (~10 lines)

**Where:** After candle boundary check (line 776), before weekend check (line 782).

```python
# Shadow logging: tag trades outside profitable window
_PROFITABLE_HOURS_UTC = {6, 7, 8, 9, 10, 13, 16}
shadow_skip = datetime.datetime.utcnow().hour not in _PROFITABLE_HOURS_UTC
if shadow_skip:
    pt_hour = (datetime.datetime.utcnow().hour - 7) % 24
    logger.info(f"[SHADOW] {symbol} {direction} entry at {pt_hour}:00 PT — outside profitable window")
```

**Where:** At `risk.open_position()` call (line 808), pass the flag:

```python
self.risk.open_position(symbol, fill_price, margin, side=direction, atr=atr_val,
    regime=regime, cycle=self.cycle_count, strategy=strat_name,
    shadow_skip=shadow_skip)
```

### 2. risk_manager.py — Store shadow fields (~5 lines)

**open_position() signature (line 419):** Add `shadow_skip: bool = False` parameter.

**Position creation (line 458-471):** Store on position object:
```python
position.shadow_skip = shadow_skip
position.shadow_hour_pt = (int(time.time()) // 3600 - 7) % 24 if shadow_skip else None
```

**_save_state() (line 258-276):** Add to pos_data dict:
```python
"shadow_skip": getattr(pos, 'shadow_skip', False),
"shadow_hour_pt": getattr(pos, 'shadow_hour_pt', None),
```

**close_position() trade dict (line 529-546):** Add to trade dict:
```python
"shadow_skip": getattr(pos, 'shadow_skip', False),
"shadow_hour_pt": getattr(pos, 'shadow_hour_pt', None),
```

### 3. scripts/daily_report.py — Shadow summary (~20 lines)

**Where:** After paper slot section (line 369), before Telegram send (line 371).

```python
# Shadow filter results
shadow_trades = [t for t in today_trades if t.get("shadow_skip")]
shadow_all = [t for t in all_trades if t.get("shadow_skip")]
if shadow_trades or shadow_all:
    s_today_pnl = sum(t.get("pnl_usdt", 0) for t in shadow_trades)
    s_all_pnl = sum(t.get("pnl_usdt", 0) for t in shadow_all)
    s_sign_t = "+" if s_today_pnl >= 0 else ""
    s_sign_a = "+" if s_all_pnl >= 0 else ""
    msg += (
        f"\n🕐 <b>Shadow Filter (time-of-day)</b>\n"
        f"Today: {len(shadow_trades)} would-skip trades | {s_sign_t}${s_today_pnl:.2f} PnL\n"
        f"Total: {len(shadow_all)} would-skip trades | {s_sign_a}${s_all_pnl:.2f} PnL\n"
        f"(Negative = money saved by filtering)\n"
    )
```

### 4. notifier.py — Shadow tag on entry/exit notifications

Add `[SHADOW]` label to Telegram entry/exit messages when trade is in shadow zone:
- `notify_entry()`: if shadow_skip, prepend `⏳` and add "SHADOW ZONE" to message
- `notify_exit()`: if shadow_skip, add "(shadow zone trade)" to PnL line

### 5. web_dashboard.py — Shadow filter card

Add a "Shadow Filter" stats card showing:
- Total shadow-tagged trades, WR, PnL
- Today's shadow trades, WR, PnL
- "Estimated savings" = negative of shadow PnL (if shadow trades are losing money, that's what you'd save)

## What Does NOT Change

- Entry logic — trades still execute normally
- Exit logic — untouched
- Position sizing — untouched
- Strategy parameters — untouched
- API calls — zero additional
- Performance — one datetime.utcnow().hour call (nanoseconds)

## Data Stored Per Trade

```json
{
  "shadow_skip": true,
  "shadow_hour_pt": 14,
  ...existing fields...
}
```

## Success Criteria

After 4+ weeks (100+ shadow-tagged trades):
1. Compute: total PnL of shadow-tagged trades
2. If negative (money lost on shadow-zone trades): time filter is validated
3. If positive (money made on shadow-zone trades): time filter would hurt, don't implement
4. Check if any big winners would have been missed

## Files Changed

| File | Lines Added | Risk |
|------|-------------|------|
| bot.py | ~10 | Zero — only adds a boolean flag |
| risk_manager.py | ~8 | Zero — only stores two extra fields |
| scripts/daily_report.py | ~15 | Zero — only reads existing data |
| notifier.py | ~10 | Zero — only adds labels to existing messages |
| web_dashboard.py | ~40 | Zero — only reads existing data |

## DST Note

PT = UTC-7 (PDT, current). When clocks change to PST (UTC-8) in November, the profitable window UTC hours shift by 1. For now we hardcode UTC hours. If the shadow log validates the filter, we'll add proper timezone handling in the production version.
