# SR_BOUNCE Backtest Kill-Gate Scan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the read-only backtest scan that decides whether the SR_BOUNCE strategy (spec: `docs/superpowers/specs/2026-07-28-sr-bounce-design.md`) is worth building as a paper slot.

**Architecture:** Self-contained package under `scripts/research/sr-bounce-scan/` — pure level-math module, rejection/geometry modules, a candle-replay engine with pessimistic fill realism, a data fetcher with local cache, and a runner that writes the verdict report. Zero imports from bot code; never writes bot state.

**Tech Stack:** Python 3.14, pandas, ccxt (already installed for the bot). No new dependencies — the Mann-Whitney test is implemented inline with a normal approximation.

## Global Constraints (frozen 2026-07-28 — copied from spec §2/§3)

- Pivot lookback k=3 candles each side, on 1h candles.
- Zone cluster width: pivots within 0.25 × ATR(1h, 14) merge; zone = band [min, max] of member pivots.
- Zone validated at ≥2 distinct touches; a touch = 1h candle range enters the zone and closes outside it, ≥3 candles after the previous touch.
- Entry trigger: 5m candle pierces the zone and closes back outside (support: `low <= zone_hi and close > zone_hi`).
- Regime gate: 1h ADX(14) < 30 at signal time.
- Stop: far zone edge + 0.25 × ATR(5m, 14) buffer. Target: nearest opposing validated zone, capped at 3× stop distance. Skip if room < 1× stop distance.
- Fill realism: a limit placed at candle t's close fills only if candle t+1 trades STRICTLY through it (long: `next.low < limit`). No fill → signal lost.
- Same-candle SL+TP touch → count as SL (pessimistic).
- Fees: 0.12% of notional round trip, subtracted from every closed trade.
- Data split: train = first 60 days (diagnostics only), holdout = last 30 days (verdict). NO parameter tuning anywhere.
- **DOA line (pre-registered): do NOT build the slot if holdout fee-inclusive net-per-trade ≤ $0 OR holdout total trades < 20.** All dollar figures at $5 margin × 10x = $50 notional.
- Read-only: nothing under this package writes to trading_state*.json, .env, or any bot file.

## File Structure

```
scripts/research/sr-bounce-scan/
  sr_levels.py        # pure: pivots, ATR, ADX, zone clustering, touch counting
  sr_signal.py        # pure: rejection trigger + trade geometry (stop/target/skip)
  fetch_data.py       # ccxt paginated fetch → data/<SYM>_{1h,5m}.csv cache
  engine.py           # replay loop: signals → fills → exits → trade list
  overlap.py          # bonus diagnostic vs trading_state.json (read-only)
  run_scan.py         # orchestrator: split, stats, DOA verdict, report writer
  tests/              # pytest; synthetic-candle fixtures, no network
  data/               # cached candles (gitignored)
```

---

### Task 1: Level math (`sr_levels.py`)

**Files:**
- Create: `scripts/research/sr-bounce-scan/sr_levels.py`
- Create: `scripts/research/sr-bounce-scan/tests/test_sr_levels.py`
- Create: `scripts/research/sr-bounce-scan/tests/__init__.py` (empty) and `scripts/research/sr-bounce-scan/__init__.py` (empty)

**Interfaces:**
- Produces (later tasks import these exact names from `sr_levels`):
  - `atr(df: pd.DataFrame, n: int = 14) -> pd.Series` — Wilder ATR on columns high/low/close.
  - `adx(df: pd.DataFrame, n: int = 14) -> pd.Series` — Wilder ADX.
  - `find_pivots(df: pd.DataFrame, k: int = 3) -> tuple[list[int], list[int]]` — (swing_low_idx, swing_high_idx); a swing low at i has `low[i] == min(low[i-k : i+k+1])` and is strictly lower than both neighbors' window extremes ties-excluded (use `<` against all others); indices within k of either end are never pivots.
  - `cluster_zones(prices: list[float], width: float) -> list[tuple[float, float]]` — sort prices; greedy merge while `price - cluster_min <= width`; each cluster → `(min, max)`.
  - `count_touches(df: pd.DataFrame, lo: float, hi: float, min_gap: int = 3) -> int` — count 1h candles where `low <= hi and high >= lo` (range enters zone) and (`close > hi or close < lo`) (closes outside), skipping any candle within `min_gap` candles of the previously counted touch.
  - `validated_zones(df: pd.DataFrame, k: int = 3, width_mult: float = 0.25, min_touches: int = 2) -> list[dict]` — returns `[{"lo": float, "hi": float, "side": "support"|"resistance", "touches": int}]`; side = "support" for zones built from swing lows, "resistance" from swing highs; keeps only zones with `touches >= min_touches`; ATR width = `width_mult * atr(df).iloc[-1]`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sr_levels.py
import pandas as pd
import pytest
from sr_levels import atr, adx, find_pivots, cluster_zones, count_touches, validated_zones


def _df(rows):
    """rows = list of (high, low, close); open synthesized as prev close."""
    df = pd.DataFrame(rows, columns=["high", "low", "close"])
    df["open"] = df["close"].shift(1).fillna(df["close"])
    return df


def test_find_pivots_simple_v():
    # lows: descend to index 3 then ascend — index 3 is the swing low (k=3)
    lows = [10, 9, 8, 5, 8, 9, 10]
    rows = [(l + 1, l, l + 0.5) for l in lows]
    los, his = find_pivots(_df(rows), k=3)
    assert los == [3]


def test_find_pivots_edge_indices_excluded():
    lows = [1, 9, 8, 7, 8, 9, 10]   # index 0 is lowest but within k of edge
    rows = [(l + 1, l, l + 0.5) for l in lows]
    los, _ = find_pivots(_df(rows), k=3)
    assert los == []


def test_cluster_zones_merges_within_width():
    zones = cluster_zones([100.0, 100.3, 105.0], width=0.5)
    assert zones == [(100.0, 100.3), (105.0, 105.0)]


def test_count_touches_requires_close_outside_and_gap():
    # zone [99, 100]; candles: touch+close-out, inside-close (no), too-soon touch (no), later touch (yes)
    rows = [
        (101, 99.5, 100.5),   # enters zone, closes above → touch 1
        (100.5, 99.2, 99.5),  # enters, closes INSIDE → not a touch
        (101, 99.5, 100.4),   # enters, closes out, but only 2 after touch1 → gap fail
        (102, 101, 101.5),    # never enters
        (101, 99.8, 100.6),   # enters, closes out, gap ok → touch 2
    ]
    assert count_touches(_df(rows), lo=99.0, hi=100.0, min_gap=3) == 2


def test_validated_zones_min_touches_filters():
    # Build 40 candles: repeated bounces off ~100 (support, 3 touches),
    # single spike high at 120 (resistance, 1 touch) — only support survives.
    rows = []
    for cyc in range(4):
        base = [(106, 104, 105), (104, 102, 103), (102, 99.8, 101),
                (104, 101, 103.5), (106, 103, 105), (107, 104, 106),
                (108, 105, 107), (107, 104, 105), (106, 103, 104), (105, 102, 103)]
        rows.extend(base)
    zones = validated_zones(_df(rows), k=3, width_mult=0.25, min_touches=2)
    assert any(z["side"] == "support" and z["lo"] <= 100 <= z["hi"] + 1 for z in zones)
    assert all(z["touches"] >= 2 for z in zones)


def test_atr_and_adx_shapes():
    rows = [(i + 1.0, i, i + 0.5) for i in range(40)]
    df = _df(rows)
    assert len(atr(df)) == 40 and atr(df).iloc[-1] > 0
    assert len(adx(df)) == 40
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd ~/Desktop/Phmex-S/scripts/research/sr-bounce-scan && python3 -m pytest tests/test_sr_levels.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sr_levels'`

- [ ] **Step 3: Implement `sr_levels.py`**

```python
"""Pure S/R level math for the SR_BOUNCE kill-gate scan.
Frozen parameters live in the spec (2026-07-28); no tuning here."""
import pandas as pd


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - prev_close).abs(),
                    (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = ((up > dn) & (up > 0)) * up
    minus_dm = ((dn > up) & (dn > 0)) * dn
    tr = atr(df, n)
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / tr
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def find_pivots(df: pd.DataFrame, k: int = 3) -> tuple[list[int], list[int]]:
    lows, highs = df["low"].values, df["high"].values
    lo_idx, hi_idx = [], []
    for i in range(k, len(df) - k):
        wl = lows[i - k:i + k + 1]
        if lows[i] == wl.min() and (wl < lows[i]).sum() == 0 and (wl == lows[i]).sum() == 1:
            lo_idx.append(i)
        wh = highs[i - k:i + k + 1]
        if highs[i] == wh.max() and (wh == highs[i]).sum() == 1:
            hi_idx.append(i)
    return lo_idx, hi_idx


def cluster_zones(prices: list[float], width: float) -> list[tuple[float, float]]:
    if not prices:
        return []
    prices = sorted(prices)
    zones, cur = [], [prices[0]]
    for p in prices[1:]:
        if p - cur[0] <= width:
            cur.append(p)
        else:
            zones.append((cur[0], cur[-1]))
            cur = [p]
    zones.append((cur[0], cur[-1]))
    return zones


def count_touches(df: pd.DataFrame, lo: float, hi: float, min_gap: int = 3) -> int:
    touches, last = 0, -10**9
    for i, row in df.iterrows():
        enters = row["low"] <= hi and row["high"] >= lo
        closes_out = row["close"] > hi or row["close"] < lo
        if enters and closes_out and (i - last) >= min_gap:
            touches += 1
            last = i
    return touches


def validated_zones(df: pd.DataFrame, k: int = 3, width_mult: float = 0.25,
                    min_touches: int = 2) -> list[dict]:
    width = width_mult * float(atr(df).iloc[-1])
    lo_idx, hi_idx = find_pivots(df, k)
    out = []
    for side, idxs, col in (("support", lo_idx, "low"), ("resistance", hi_idx, "high")):
        for zlo, zhi in cluster_zones([float(df[col].iloc[i]) for i in idxs], width):
            t = count_touches(df, zlo, zhi)
            if t >= min_touches:
                out.append({"lo": zlo, "hi": zhi, "side": side, "touches": t})
    return out
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/test_sr_levels.py -v` — Expected: all PASS. If `test_validated_zones_min_touches_filters` fails on the synthetic fixture, debug the FIXTURE first (print the pivots found) — the fixture must actually contain ≥2 valid touches with the gap rule; adjust the fixture candles, never the frozen parameters.

- [ ] **Step 5: Commit**

```bash
cd ~/Desktop/Phmex-S && git add scripts/research/sr-bounce-scan && git commit -m "research(sr-bounce): level math module (pivots, zones, touches) with tests"
```

---

### Task 2: Rejection trigger + trade geometry (`sr_signal.py`)

**Files:**
- Create: `scripts/research/sr-bounce-scan/sr_signal.py`
- Create: `scripts/research/sr-bounce-scan/tests/test_sr_signal.py`

**Interfaces:**
- Consumes: zone dicts from `sr_levels.validated_zones` (`{"lo","hi","side","touches"}`).
- Produces:
  - `confirmed_rejection(candle: dict, zone: dict) -> bool` — candle = `{"open","high","low","close"}`. Support: `candle["low"] <= zone["hi"] and candle["close"] > zone["hi"]`. Resistance: `candle["high"] >= zone["lo"] and candle["close"] < zone["lo"]`.
  - `plan_trade(zone: dict, all_zones: list[dict], atr5: float, entry: float) -> dict | None` — returns `{"side": "long"|"short", "sl": float, "tp": float}` or `None` (skip). Long from support: `sl = zone["lo"] - 0.25*atr5`; `risk = entry - sl`; opposing = validated resistance zones with `lo > entry`; `room = nearest_lo - entry`; skip if no opposing zone or `room < risk`; `tp = min(nearest_lo, entry + 3*risk)`. Short mirrored (opposing = support zones with `hi < entry`, `tp = max(nearest_hi, entry - 3*risk)`).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sr_signal.py
from sr_signal import confirmed_rejection, plan_trade

SUP = {"lo": 99.0, "hi": 100.0, "side": "support", "touches": 2}
RES = {"lo": 110.0, "hi": 111.0, "side": "resistance", "touches": 2}


def test_rejection_support_pierce_and_close_back():
    assert confirmed_rejection({"open": 101, "high": 101, "low": 99.5, "close": 100.4}, SUP)


def test_rejection_support_close_through_fails():
    assert not confirmed_rejection({"open": 101, "high": 101, "low": 98, "close": 99.5}, SUP)


def test_rejection_support_never_entered_fails():
    assert not confirmed_rejection({"open": 101, "high": 102, "low": 100.5, "close": 101}, SUP)


def test_plan_trade_long_basic():
    t = plan_trade(SUP, [SUP, RES], atr5=0.4, entry=100.4)
    assert t["side"] == "long"
    assert t["sl"] == 99.0 - 0.1            # zone lo - 0.25*atr5
    risk = 100.4 - t["sl"]
    assert t["tp"] == min(110.0, 100.4 + 3 * risk)


def test_plan_trade_skip_no_room():
    near_res = {"lo": 100.9, "hi": 101.2, "side": "resistance", "touches": 2}
    assert plan_trade(SUP, [SUP, near_res], atr5=0.4, entry=100.4) is None


def test_plan_trade_skip_no_opposing():
    assert plan_trade(SUP, [SUP], atr5=0.4, entry=100.4) is None
```

- [ ] **Step 2: Run, verify FAIL** — `python3 -m pytest tests/test_sr_signal.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `sr_signal.py`**

```python
"""Rejection trigger + structural trade geometry (spec §2, frozen)."""


def confirmed_rejection(candle: dict, zone: dict) -> bool:
    if zone["side"] == "support":
        return candle["low"] <= zone["hi"] and candle["close"] > zone["hi"]
    return candle["high"] >= zone["lo"] and candle["close"] < zone["lo"]


def plan_trade(zone: dict, all_zones: list[dict], atr5: float, entry: float):
    if zone["side"] == "support":
        sl = zone["lo"] - 0.25 * atr5
        risk = entry - sl
        opposing = sorted(z["lo"] for z in all_zones
                          if z["side"] == "resistance" and z["lo"] > entry)
        if risk <= 0 or not opposing or (opposing[0] - entry) < risk:
            return None
        return {"side": "long", "sl": sl, "tp": min(opposing[0], entry + 3 * risk)}
    sl = zone["hi"] + 0.25 * atr5
    risk = sl - entry
    opposing = sorted((z["hi"] for z in all_zones
                       if z["side"] == "support" and z["hi"] < entry), reverse=True)
    if risk <= 0 or not opposing or (entry - opposing[0]) < risk:
        return None
    return {"side": "short", "sl": sl, "tp": max(opposing[0], entry - 3 * risk)}
```

- [ ] **Step 4: Run, verify PASS** — `python3 -m pytest tests/test_sr_signal.py -v`

- [ ] **Step 5: Commit** — `git add -A scripts/research/sr-bounce-scan && git commit -m "research(sr-bounce): rejection trigger + structural geometry with tests"`

---

### Task 3: Data fetcher (`fetch_data.py`)

**Files:**
- Create: `scripts/research/sr-bounce-scan/fetch_data.py`
- Create: `scripts/research/sr-bounce-scan/tests/test_fetch_data.py`
- Create: `scripts/research/sr-bounce-scan/data/.gitignore` containing `*\n!.gitignore`

**Interfaces:**
- Produces:
  - `load_candles(symbol: str, timeframe: str, days: int = 90, data_dir: str = "data") -> pd.DataFrame` — columns `ts, open, high, low, close, volume` (ts = epoch ms, ascending, de-duplicated). Reads `data/<SYM>_<tf>.csv` if present; otherwise paginated `ccxt.phemex().fetch_ohlcv` (1000/page, 0.5s sleep between pages), writes the cache, returns it. `<SYM>` = symbol with `/`/`:` replaced by `_`.
  - `scan_pairs() -> list[str]` — parses `SCAN_PAIRS`-style symbols from the bot's `.env` if such a key exists; otherwise returns the fallback list frozen here: `["BTC/USDT:USDT","ETH/USDT:USDT","SOL/USDT:USDT","XRP/USDT:USDT","ADA/USDT:USDT","DOGE/USDT:USDT","LTC/USDT:USDT","1000PEPE/USDT:USDT","1000SHIB/USDT:USDT","ENA/USDT:USDT"]` (top-liquidity pairs from the current watchlist).

- [ ] **Step 1: Write failing test (offline behavior only — no network in tests)**

```python
# tests/test_fetch_data.py
import pandas as pd
from fetch_data import load_candles


def test_load_candles_uses_cache(tmp_path):
    f = tmp_path / "BTC_USDT_USDT_1h.csv"
    pd.DataFrame({"ts": [2, 1, 2], "open": [1, 1, 1], "high": [2, 2, 2],
                  "low": [0.5, 0.5, 0.5], "close": [1.5, 1.4, 1.5],
                  "volume": [10, 10, 10]}).to_csv(f, index=False)
    df = load_candles("BTC/USDT:USDT", "1h", data_dir=str(tmp_path))
    assert list(df["ts"]) == [1, 2]          # sorted + deduped (keep first of dup ts)
    assert len(df) == 2
```

- [ ] **Step 2: Run, verify FAIL** — `python3 -m pytest tests/test_fetch_data.py -v`

- [ ] **Step 3: Implement `fetch_data.py`**

```python
"""Candle cache/fetch for the scan. Cache-first; network only on miss."""
import os
import time
import pandas as pd

FALLBACK_PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
                  "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT",
                  "LTC/USDT:USDT", "1000PEPE/USDT:USDT", "1000SHIB/USDT:USDT",
                  "ENA/USDT:USDT"]
COLS = ["ts", "open", "high", "low", "close", "volume"]


def _slug(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def scan_pairs() -> list[str]:
    return list(FALLBACK_PAIRS)


def load_candles(symbol: str, timeframe: str, days: int = 90,
                 data_dir: str = "data") -> pd.DataFrame:
    path = os.path.join(data_dir, f"{_slug(symbol)}_{timeframe}.csv")
    if os.path.exists(path):
        df = pd.read_csv(path)[COLS]
    else:
        import ccxt
        ex = ccxt.phemex()
        since = ex.milliseconds() - days * 86_400_000
        rows = []
        while True:
            page = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not page:
                break
            rows.extend(page)
            if len(page) < 1000:
                break
            since = page[-1][0] + 1
            time.sleep(0.5)
        df = pd.DataFrame(rows, columns=COLS)
        os.makedirs(data_dir, exist_ok=True)
        df.to_csv(path, index=False)
    return (df.sort_values("ts").drop_duplicates("ts", keep="first")
              .reset_index(drop=True))
```

- [ ] **Step 4: Run, verify PASS** — `python3 -m pytest tests/test_fetch_data.py -v`

- [ ] **Step 5: Commit** — `git add -A scripts/research/sr-bounce-scan && git commit -m "research(sr-bounce): cached candle fetcher"`

---

### Task 4: Replay engine (`engine.py`)

**Files:**
- Create: `scripts/research/sr-bounce-scan/engine.py`
- Create: `scripts/research/sr-bounce-scan/tests/test_engine.py`

**Interfaces:**
- Consumes: `sr_levels.validated_zones/adx/atr`, `sr_signal.confirmed_rejection/plan_trade`, candle DataFrames from `fetch_data.load_candles`.
- Produces:
  - `replay(df1h: pd.DataFrame, df5m: pd.DataFrame, symbol: str, notional: float = 50.0, fee_rt: float = 0.0012) -> list[dict]` — each trade: `{"symbol","side","signal_ts","entry","sl","tp","exit_ts","exit_price","exit_reason" ("stop_loss"|"take_profit"), "net_usd","risk_pct","reward_pct"}`.
- Engine rules (all from Global Constraints):
  1. Walk 5m candles chronologically. At each candle t, build the 1h context = all 1h candles CLOSED at or before t's open (no lookahead), most recent 500.
  2. Need ≥100 1h candles; zones recomputed once per new 1h candle (cache per hour bucket); skip signal if `adx(df1h_ctx).iloc[-1] >= 30`.
  3. One open position per symbol; no new signals while open.
  4. Signal: `confirmed_rejection(candle_t, zone)` for any validated zone → `plan_trade(zone, zones, atr5, entry=candle_t.close)`; `atr5 = atr(last 100 5m candles).iloc[-1]`.
  5. Fill: candle t+1 must trade strictly through the limit (long: `low[t+1] < entry`; short: `high[t+1] > entry`). No fill → drop signal.
  6. From fill candle onward (including the fill candle itself, AFTER entry): exit when a candle's range touches SL or TP. Both in one candle → SL (pessimistic).
  7. `net_usd = notional * (signed price return) - notional * fee_rt`.

- [ ] **Step 1: Write failing tests (synthetic end-to-end)**

```python
# tests/test_engine.py
import pandas as pd
from engine import replay


def _mk(rows, start_ts, step_ms):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["ts"] = [start_ts + i * step_ms for i in range(len(df))]
    df["volume"] = 100.0
    return df[["ts", "open", "high", "low", "close", "volume"]]


def _flat_1h(n=150, lo=99.0, hi=101.0):
    """Ranging 1h series bouncing between ~99 and ~101 (low ADX by construction),
    with clean swing lows at 99 every 10 candles → validated support zone."""
    rows = []
    for i in range(n):
        ph = i % 10
        if ph < 5:
            px = 101 - 0.4 * ph
        else:
            px = 99 + 0.4 * (ph - 5)
        rows.append((px + 0.2, px + 0.5, px - 0.5, px))
    return _mk(rows, start_ts=0, step_ms=3_600_000)


def test_replay_produces_win_on_scripted_bounce():
    df1h = _flat_1h()
    ts0 = 120 * 3_600_000          # 5m stream starts after 120 closed 1h candles
    m = 300_000
    fivem = [
        (100.6, 100.7, 100.5, 100.6),   # idle
        (100.5, 100.6, 98.9, 100.3),    # pierces support (~99) and closes back → signal, limit 100.3
        (100.3, 100.4, 100.1, 100.2),   # low 100.1 < 100.3 → FILL
        (100.2, 103.5, 100.2, 103.4),   # runs up through TP → take_profit
    ]
    trades = replay(df1h, _mk(fivem, ts0, m), "TEST")
    assert len(trades) == 1
    t = trades[0]
    assert t["side"] == "long" and t["exit_reason"] == "take_profit"
    assert t["net_usd"] > 0


def test_replay_no_fill_drops_signal():
    df1h = _flat_1h()
    ts0 = 120 * 3_600_000
    m = 300_000
    fivem = [
        (100.5, 100.6, 98.9, 100.3),    # signal
        (100.4, 101.0, 100.35, 100.9),  # never trades below 100.3 → no fill
        (101.0, 101.2, 100.8, 101.1),
    ]
    assert replay(df1h, _mk(fivem, ts0, m), "TEST") == []


def test_replay_same_candle_sl_and_tp_counts_stop():
    df1h = _flat_1h()
    ts0 = 120 * 3_600_000
    m = 300_000
    fivem = [
        (100.5, 100.6, 98.9, 100.3),      # signal
        (100.3, 100.4, 100.0, 100.2),     # fill
        (100.2, 104.0, 98.0, 99.0),       # touches BOTH sl and tp → stop_loss
    ]
    trades = replay(df1h, _mk(fivem, ts0, m), "TEST")
    assert len(trades) == 1 and trades[0]["exit_reason"] == "stop_loss"
    assert trades[0]["net_usd"] < 0
```

- [ ] **Step 2: Run, verify FAIL** — `python3 -m pytest tests/test_engine.py -v`

- [ ] **Step 3: Implement `engine.py`**

```python
"""Chronological replay with pessimistic fill/exit realism (spec §3)."""
import pandas as pd
from sr_levels import atr, adx, validated_zones
from sr_signal import confirmed_rejection, plan_trade

MIN_1H = 100


def replay(df1h: pd.DataFrame, df5m: pd.DataFrame, symbol: str,
           notional: float = 50.0, fee_rt: float = 0.0012) -> list[dict]:
    trades, open_pos, pending = [], None, None
    zone_cache_key, zones, cur_adx = None, [], None

    for i in range(len(df5m)):
        c = df5m.iloc[i]
        candle = {"open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]}

        # 1h context: candles CLOSED at/before this 5m candle's open (no lookahead)
        ctx = df1h[df1h["ts"] + 3_600_000 <= c["ts"]].tail(500).reset_index(drop=True)
        if len(ctx) < MIN_1H:
            continue
        key = int(ctx["ts"].iloc[-1])
        if key != zone_cache_key:
            zone_cache_key = key
            zones = validated_zones(ctx)
            cur_adx = float(adx(ctx).iloc[-1])

        # pending fill from last candle's signal
        if pending is not None:
            filled = (candle["low"] < pending["entry"] if pending["side"] == "long"
                      else candle["high"] > pending["entry"])
            open_pos = dict(pending, fill_i=i) if filled else None
            pending = None
            if open_pos:
                # same-candle exit check happens below
                pass

        # exit check
        if open_pos is not None:
            side, sl, tp = open_pos["side"], open_pos["sl"], open_pos["tp"]
            hit_sl = candle["low"] <= sl if side == "long" else candle["high"] >= sl
            hit_tp = candle["high"] >= tp if side == "long" else candle["low"] <= tp
            if hit_sl or hit_tp:
                reason = "stop_loss" if hit_sl else "take_profit"   # both → SL
                px = sl if hit_sl else tp
                sgn = 1 if side == "long" else -1
                ret = sgn * (px - open_pos["entry"]) / open_pos["entry"]
                trades.append({
                    "symbol": symbol, "side": side, "signal_ts": open_pos["signal_ts"],
                    "entry": open_pos["entry"], "sl": sl, "tp": tp,
                    "exit_ts": int(c["ts"]), "exit_price": px, "exit_reason": reason,
                    "net_usd": notional * ret - notional * fee_rt,
                    "risk_pct": abs(open_pos["entry"] - sl) / open_pos["entry"] * 100,
                    "reward_pct": abs(tp - open_pos["entry"]) / open_pos["entry"] * 100,
                })
                open_pos = None
            continue

        # new signal (flat only, regime-gated)
        if cur_adx is None or cur_adx >= 30:
            continue
        atr5 = float(atr(df5m.iloc[max(0, i - 100):i + 1]).iloc[-1])
        for z in zones:
            if confirmed_rejection(candle, z):
                plan = plan_trade(z, zones, atr5, entry=float(candle["close"]))
                if plan is not None:
                    pending = dict(plan, entry=float(candle["close"]),
                                   signal_ts=int(c["ts"]))
                    break
    return trades
```

- [ ] **Step 4: Run, verify PASS** — `python3 -m pytest tests/test_engine.py -v`. Debug fixture-first on failure (print zones/adx from the fixture), never loosen frozen parameters.

- [ ] **Step 5: Run ALL scan tests** — `python3 -m pytest tests/ -v` — Expected: all green.

- [ ] **Step 6: Commit** — `git add -A scripts/research/sr-bounce-scan && git commit -m "research(sr-bounce): replay engine with pessimistic fill/exit realism"`

---

### Task 5: Overlap diagnostic (`overlap.py`)

**Files:**
- Create: `scripts/research/sr-bounce-scan/overlap.py`
- Create: `scripts/research/sr-bounce-scan/tests/test_overlap.py`

**Interfaces:**
- Consumes: `fetch_data.load_candles`, `sr_levels.validated_zones`, and (read-only) `~/Desktop/Phmex-S/trading_state.json`.
- Produces:
  - `mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]` — U statistic and two-sided p via normal approximation with tie-corrected variance; returns `(nan, 1.0)` when `len(a) < 5 or len(b) < 5`.
  - `zone_proximity_report(state_path: str, data_dir: str = "data") -> dict` — for each closed real trade whose symbol has cached 1h data: rebuild zones from the 500 1h candles closed before `opened_at` (no lookahead), compute `dist_atr` = distance from entry price to nearest OPPOSING validated zone edge in ATR(1h) units (opposing = resistance for longs, support for shorts; trades with no opposing zone get `dist_atr = inf` and are excluded); split winners (`net_pnl > 0`) vs losers; return `{"n_win", "n_loss", "median_win_dist", "median_loss_dist", "U", "p", "excluded"}`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_overlap.py
from overlap import mann_whitney_u


def test_mann_whitney_separated_samples_low_p():
    a = [1, 2, 3, 4, 5, 6, 7, 8]
    b = [11, 12, 13, 14, 15, 16, 17, 18]
    u, p = mann_whitney_u(a, b)
    assert p < 0.01


def test_mann_whitney_identical_samples_high_p():
    a = [1, 2, 3, 4, 5, 6, 7, 8]
    u, p = mann_whitney_u(a, list(a))
    assert p > 0.5


def test_mann_whitney_small_sample_guard():
    import math
    u, p = mann_whitney_u([1, 2], [3, 4])
    assert math.isnan(u) and p == 1.0
```

- [ ] **Step 2: Run, verify FAIL** — `python3 -m pytest tests/test_overlap.py -v`

- [ ] **Step 3: Implement `overlap.py`**

```python
"""Bonus diagnostic: were our REAL historical trades' outcomes related to
S/R zone proximity at entry? Report-only; never a verdict input (spec §3)."""
import json
import math
import pandas as pd
from fetch_data import load_candles, _slug
from sr_levels import atr, validated_zones
import os


def mann_whitney_u(a, b):
    n1, n2 = len(a), len(b)
    if n1 < 5 or n2 < 5:
        return float("nan"), 1.0
    allv = sorted((v, 0) for v in a) + sorted((v, 1) for v in b)
    allv.sort(key=lambda x: x[0])
    # midranks with ties
    ranks, i = {}, 0
    vals = [v for v, _ in allv]
    r = [0.0] * len(vals)
    while i < len(vals):
        j = i
        while j + 1 < len(vals) and vals[j + 1] == vals[i]:
            j += 1
        mid = (i + j) / 2 + 1
        for k2 in range(i, j + 1):
            r[k2] = mid
        i = j + 1
    r1 = sum(r[k] for k in range(len(allv)) if allv[k][1] == 0)
    u = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    # tie-corrected variance
    from collections import Counter
    tie = sum(c**3 - c for c in Counter(vals).values())
    n = n1 + n2
    var = n1 * n2 / 12 * ((n + 1) - tie / (n * (n - 1)))
    if var <= 0:
        return u, 1.0
    z = (u - mu) / math.sqrt(var)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return u, p


def zone_proximity_report(state_path: str, data_dir: str = "data") -> dict:
    trades = json.load(open(state_path)).get("closed_trades", [])
    win_d, loss_d, excluded = [], [], 0
    for t in trades:
        sym = t.get("symbol")
        f = os.path.join(data_dir, f"{_slug(sym)}_1h.csv") if sym else None
        if not sym or not f or not os.path.exists(f):
            excluded += 1
            continue
        df1h = load_candles(sym, "1h", data_dir=data_dir)
        opened = (t.get("opened_at") or 0) * 1000
        ctx = df1h[df1h["ts"] + 3_600_000 <= opened].tail(500).reset_index(drop=True)
        if len(ctx) < 100:
            excluded += 1
            continue
        zones = validated_zones(ctx)
        entry = t.get("entry_price") or t.get("entry") or 0
        a = float(atr(ctx).iloc[-1])
        side = t.get("side", "long")
        if side == "long":
            opp = [z["lo"] for z in zones if z["side"] == "resistance" and z["lo"] > entry]
            d = (min(opp) - entry) / a if opp and a > 0 else float("inf")
        else:
            opp = [z["hi"] for z in zones if z["side"] == "support" and z["hi"] < entry]
            d = (entry - max(opp)) / a if opp and a > 0 else float("inf")
        if math.isinf(d):
            excluded += 1
            continue
        n = t.get("net_pnl")
        n = n if n is not None else t.get("pnl_usdt", 0) or 0
        (win_d if n > 0 else loss_d).append(d)
    u, p = mann_whitney_u(win_d, loss_d)
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else float("nan")
    return {"n_win": len(win_d), "n_loss": len(loss_d),
            "median_win_dist": med(win_d), "median_loss_dist": med(loss_d),
            "U": u, "p": p, "excluded": excluded}
```

- [ ] **Step 4: Run, verify PASS** — `python3 -m pytest tests/test_overlap.py -v`

- [ ] **Step 5: Commit** — `git add -A scripts/research/sr-bounce-scan && git commit -m "research(sr-bounce): real-trade zone-proximity diagnostic"`

---

### Task 6: Runner + report (`run_scan.py`), fetch data, run the scan

**Files:**
- Create: `scripts/research/sr-bounce-scan/run_scan.py`
- Test: reuse existing suite (`python3 -m pytest tests/ -v` must be green before running)

**Interfaces:**
- Consumes: everything above.
- Produces: `reports/<YYYY-MM-DD>-sr-bounce-scan.md` (repo `reports/` dir) and prints the verdict line to stdout.

- [ ] **Step 1: Implement `run_scan.py`**

```python
"""SR_BOUNCE kill-gate scan runner. Usage:
    python3 run_scan.py            # fetch/cache data, replay, write report
DOA line (pre-registered 2026-07-28): DO NOT BUILD if holdout
net-per-trade <= $0 fee-inclusive OR holdout trades < 20 (pooled)."""
import datetime
import os
import pandas as pd
from fetch_data import load_candles, scan_pairs
from engine import replay
from overlap import zone_proximity_report

HOLDOUT_DAYS = 30
BOT_DIR = os.path.expanduser("~/Desktop/Phmex-S")


def main():
    all_rows = []
    for sym in scan_pairs():
        df1h = load_candles(sym, "1h")
        df5m = load_candles(sym, "5m")
        if df5m.empty or df1h.empty:
            print(f"skip {sym}: no data")
            continue
        trades = replay(df1h, df5m, sym)
        all_rows.extend(trades)
        print(f"{sym}: {len(trades)} trades")
    df = pd.DataFrame(all_rows)
    date = datetime.date.today().isoformat()
    out = [f"# SR_BOUNCE kill-gate scan — {date}", ""]
    if df.empty:
        out.append("ZERO trades produced across all pairs → **DO-NOT-BUILD** (< 20 holdout trades).")
        verdict = "DO-NOT-BUILD"
    else:
        cut = df["exit_ts"].max() - HOLDOUT_DAYS * 86_400_000
        hold, train = df[df["signal_ts"] >= cut], df[df["signal_ts"] < cut]
        def stats(d, label):
            if d.empty:
                return f"**{label}**: 0 trades"
            wr = (d["net_usd"] > 0).mean() * 100
            return (f"**{label}**: {len(d)} trades | WR {wr:.1f}% | "
                    f"net ${d['net_usd'].sum():+.2f} | per-trade ${d['net_usd'].mean():+.4f} | "
                    f"avg risk {d['risk_pct'].mean():.2f}% / reward {d['reward_pct'].mean():.2f}%")
        out += [stats(train, "TRAIN (diagnostics only)"), "",
                stats(hold, "HOLDOUT (the verdict)"), ""]
        doa = hold.empty or len(hold) < 20 or hold["net_usd"].mean() <= 0
        verdict = "DO-NOT-BUILD" if doa else "BUILD"
        out.append(f"## VERDICT vs pre-registered DOA line: **{verdict}**")
        out.append("- line: holdout net-per-trade <= $0 fee-incl OR holdout n < 20")
        out += ["", "## Per-pair (all trades)"]
        for sym, g in df.groupby("symbol"):
            out.append(f"- {sym}: {len(g)} trades, net ${g['net_usd'].sum():+.2f}")
    out += ["", "## Bonus: real-trade zone-proximity diagnostic (report-only)"]
    try:
        r = zone_proximity_report(os.path.join(BOT_DIR, "trading_state.json"))
        out.append(f"- winners n={r['n_win']} median dist {r['median_win_dist']:.2f} ATR | "
                   f"losers n={r['n_loss']} median {r['median_loss_dist']:.2f} ATR | "
                   f"p={r['p']:.4f} | excluded {r['excluded']}")
    except Exception as e:
        out.append(f"- diagnostic failed: {e}")
    path = os.path.join(BOT_DIR, "reports", f"{date}-sr-bounce-scan.md")
    open(path, "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nreport → {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Full test suite green** — `python3 -m pytest tests/ -v` → all PASS.

- [ ] **Step 3: Fetch data + run** — `cd scripts/research/sr-bounce-scan && python3 run_scan.py` (first run fetches ~90d × 10 pairs of 1h+5m with 0.5s page sleeps — expect 15-30 min; reruns use cache).

- [ ] **Step 4: Sanity-check the output** — open the report; verify holdout/train counts sum to total, per-pair counts sum to pooled, no pair contributed >70% of all trades (concentration flag — note it in the report by hand if so), and the diagnostic line rendered.

- [ ] **Step 5: Commit** — `git add -A scripts/research/sr-bounce-scan reports/ && git commit -m "research(sr-bounce): scan runner + first scan report"`

---

### Task 7: Record the outcome (memory + next step)

**Files:**
- Create: `~/.claude/projects/-Users-jonaspenaso-Desktop/memory/reference_sr_bounce_scan_<date>.md` (summarize verdict + receipts, link spec + report)
- Modify: memory `MEMORY.md` (one index line)

- [ ] **Step 1:** Write the memory reference file with: verdict, holdout stats, per-pair notes, diagnostic result, and the pre-registered DOA line it was judged against.
- [ ] **Step 2:** If DO-NOT-BUILD → stop; the spec's §7.2 path ends here. If BUILD → surface to Jonas for the go decision on the Stage-A slot plan (a separate plan document; do NOT start it unprompted).

## Self-Review (done at write time)

- Spec coverage: §2 signal → Tasks 1-2; §3 scan/data/DOA/report → Tasks 3, 4, 6; §3 bonus diagnostic → Task 5; §7 sequencing/memory → Task 7. No §4/§5 slot work — intentionally out of scope for this plan.
- Placeholders: none; every step has runnable content.
- Type consistency: zone dict shape (`lo/hi/side/touches`) consistent across Tasks 1-2-4-5; trade dict shape consistent between Task 4 producer and Task 6 consumer; `_slug` shared via import in Task 5.
