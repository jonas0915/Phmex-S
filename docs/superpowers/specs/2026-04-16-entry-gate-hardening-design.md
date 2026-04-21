# Entry Gate Hardening — Design Spec
**Date:** 2026-04-16
**Status:** Approved
**Scope:** Two entry gate fixes — tape gate low-volume bypass + divergence gate cooldown

---

## Problem Statement

Today's trade audit (2026-04-16) found two structural entry gate failures:

1. **Tape gate silently inactive during low-volume windows.** The tape gate only fires when `trade_count > 20`. During early AM PT (12–3 AM), the WS feed is consistently thin. All four losing trades today entered with tape gates inactive (SKIP or no log). The gate that blocks seller-dominated entries is silent precisely when overnight markets are most manipulable.

2. **Divergence gate clears in one cycle, allowing immediate re-entry.** SUI was blocked by the divergence gate 4 consecutive cycles (02:35–02:46 AM PT), then entered one cycle later when divergence cleared. No cooldown exists after a divergence block — one clean cycle is sufficient to retry.

---

## Changes

### Change 1: Add 2 AM PT to Time Blocks

**File:** `bot.py:1091`

Add UTC 9 (= 2:00 AM PT) to `_BLOCKED_HOURS_UTC`.

```python
# Before
_BLOCKED_HOURS_UTC = {0, 1, 2, 17, 18, 19, 20}

# After
_BLOCKED_HOURS_UTC = {0, 1, 2, 9, 17, 18, 19, 20}
```

**Rationale:** 2 AM PT has the worst all-time hourly performance: 26.3% WR, -$4.22 net PnL across 19 trades. Three of today's four losses landed in this hour. The existing blocks cover 5–7 PM PT and 10 AM–1 PM PT — 2 AM PT is the clear next candidate.

**Comment update:**
```python
#   2 AM PT (26% WR/-$4.22 all-time)          → UTC 9
#   10 AM-1 PM PT (28% WR/-$12.17)            → UTC 17,18,19,20
#   5-7 PM PT (26% WR/-$16.11)                → UTC 0,1,2
# Open: 12-2 AM, 3-10 AM, 2-5 PM, 8 PM-12 AM PT
```

---

### Change 2: Soft Tape Gate at Low Volume

**File:** `bot.py` — after the existing `TAPE GATE SKIP` log line (~line 1017)

When `5 ≤ trade_count ≤ 20`, apply a single buy_ratio check with a looser threshold than the full gate (0.40/0.60 vs 0.45/0.55) to account for thin-sample noise.

```python
elif flow and 5 <= flow.get("trade_count", 0) <= 20:
    buy_ratio = flow.get("buy_ratio", 0.5)
    if direction == "long" and buy_ratio < 0.40:
        logger.info(
            f"[TAPE GATE SOFT] {symbol} LONG blocked — buy_ratio {buy_ratio:.0%} "
            f"(thin tape, {flow.get('trade_count')} trades)")
        continue
    if direction == "short" and buy_ratio > 0.60:
        logger.info(
            f"[TAPE GATE SOFT] {symbol} SHORT blocked — buy_ratio {buy_ratio:.0%} "
            f"(thin tape, {flow.get('trade_count')} trades)")
        continue
```

**Why only buy_ratio:** CVD slope and large_trade_bias require more trades to produce reliable signals. buy_ratio is the most stable metric at low counts — even 5 trades can reliably identify if 80% are sellers.

**Why not trade_count < 5:** Below 5 trades the sample is too small to trust any ratio. The existing SKIP (no gate) behavior is correct for near-zero counts.

---

### Change 3: Divergence Gate Cooldown

**File:** `bot.py`

Add per-symbol cooldown state that blocks re-entry after a divergence gate fires. Release condition: **3 consecutive clean cycles OR 10 minutes elapsed**, whichever comes first.

#### State variable (`__init__`, near line 177):
```python
self._divergence_cooldown: dict[str, dict] = {}
# {symbol: {"blocked_at": float, "clean_cycles": int}}
# blocked_at: unix timestamp when divergence gate first fired
# clean_cycles: count of cycles since block where divergence was absent
```

#### Cooldown check (before tape gate, ~line 1014):
```python
# Divergence cooldown — require 3 clean cycles OR 10 min after a divergence block
if symbol in self._divergence_cooldown:
    cd = self._divergence_cooldown[symbol]
    elapsed = time.time() - cd["blocked_at"]
    if elapsed >= 600 or cd["clean_cycles"] >= 3:
        del self._divergence_cooldown[symbol]  # expired, allow entry
    else:
        if not (flow and flow.get("divergence")):
            self._divergence_cooldown[symbol]["clean_cycles"] += 1
        logger.info(
            f"[DIVERGENCE COOLDOWN] {symbol} {direction} blocked — "
            f"{cd['clean_cycles']}/3 clean cycles, {elapsed:.0f}s elapsed")
        continue
```

#### Set cooldown when divergence gate fires (lines 1064 and 1070):
```python
self._divergence_cooldown[symbol] = {"blocked_at": time.time(), "clean_cycles": 0}
```

Add this line immediately before the `continue` in both the tape gate divergence block (inside `trade_count > 20`) and the standalone divergence gate.

**Clean cycle definition:** A cycle where `flow.get("divergence")` returns None or falsy for that symbol. This means the CVD/price divergence signal has genuinely cleared, not just that tape data is sparse.

**Why hybrid (3 cycles OR 10 min):** Pure cycle-count can get stuck if tape data is sparse (low trade_count means divergence computation may not run). The 10-minute ceiling ensures the bot eventually retries even if divergence never computes again.

---

## Affected Files

| File | Change | Lines |
|---|---|---|
| `bot.py` | Add UTC 9 to `_BLOCKED_HOURS_UTC` | ~1091 |
| `bot.py` | Update block comment | ~1088 |
| `bot.py` | Add `_divergence_cooldown` dict to `__init__` | ~177 |
| `bot.py` | Add cooldown check before tape gate | ~1014 |
| `bot.py` | Set cooldown in tape gate divergence block | ~1044–1046 |
| `bot.py` | Set cooldown in standalone divergence gate | ~1064–1067 |
| `bot.py` | Add soft tape gate block | ~1017 |

---

## Success Criteria

- No entries during 2:00–2:59 AM PT (UTC 9) — verify via `[TIME BLOCK]` log lines
- Low-volume entries with buy_ratio < 0.40 blocked — verify via `[TAPE GATE SOFT]` log lines
- After a divergence block, symbol stays blocked until 3 clean cycles or 10 min — verify via `[DIVERGENCE COOLDOWN]` log lines
- No regression: symbols with clean tape and no recent divergence block enter normally

---

## Out of Scope

- Lowering the `trade_count > 20` full-gate threshold (forensics doc notes this was deliberately kept)
- Ensemble layer correlation fix (separate architectural change)
- Kelly negative edge blocking (separate decision needed from Jonas)
- Additional overnight time blocks (12 AM, 1 AM PT — insufficient data confidence)
