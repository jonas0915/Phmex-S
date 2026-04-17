# Performance-Weighted Scanner — Design Spec
**Date:** 2026-04-16
**Status:** Approved
**Scope:** Redesign scanner to rank symbols by composite score (historical performance × current market conditions), expand universe, remove daily symbol cap

---

## Problem Statement

The current scanner returns the top 5 symbols by volume with a $10M minimum. This consistently produces BTC/ETH/XRP/SUI/LINK. Three of those five (XRP/SUI/LINK) burn their daily cap of 3 trades in the overnight session (12–3 AM PT), leaving the bot with only BTC and ETH for the entire daytime — both of which rarely generate signals (ADX 13–20 all day). Result: zero daytime trades, as observed on 2026-04-16.

Additionally, the daily symbol cap (3/symbol/day) is redundant with existing protections (10-min per-pair cooldown, 4-hr blacklist after 3 consecutive losses, max 3 concurrent positions) and causes unnecessary lockouts.

---

## Changes

### Change 1: Performance-Weighted Scoring in `scanner.py`

Replace the pure volume-sort with a composite score.

#### Composite Score
```
composite_score = history_score × market_score
```

#### History Score
Computed from `trading_state.json` (loaded once per scan call):

```python
def _compute_history_scores(state_path: str, min_trades: int = 10) -> dict[str, float]:
    """Returns {symbol: history_score} for symbols with >= min_trades closed non-paper trades.
    Symbols with < min_trades are absent — caller uses 0.5 (neutral) as default."""
```

- Filter: closed trades only, `is_paper != True`
- Group by `symbol`
- If `count < min_trades`: symbol absent from dict (caller defaults to 0.5)
- If `count >= min_trades`: `avg_net_pnl = mean(pnl_usdt - fee_usdt)`
  - `history_score = 1 / (1 + exp(-10 * avg_net_pnl))`
  - sigmoid maps avg PnL to [0, 1] with 0.5 at breakeven
  - +$0.10/trade → ~0.73 | -$0.10/trade → ~0.27 | +$0.20/trade → ~0.88

#### Market Score
Computed from ticker data already fetched in `fetch_tickers()` — no extra API calls:

```python
change_norm = min(abs(ticker["percentage"]) / 15.0, 1.0)  # cap at 15% move
vol_rank    = ticker["quoteVolume"] / max_volume_in_pool   # relative to candidates
market_score = change_norm * vol_rank
```

A symbol needs both price movement AND liquidity to score well. A flat symbol with high volume scores low. A moving symbol with low liquidity also scores low.

#### Full Scan Flow (replacing `volatility_scan()`)
```
1. fetch_tickers() → all Phemex USDT perps
2. Filter: quoteVolume >= SCANNER_MIN_VOLUME ($3M), not blacklisted
3. Take top 20 candidates by volume (wider pool)
4. Load trading_state.json → compute history_scores dict
5. For each candidate:
     history = history_scores.get(symbol, 0.5)
     market  = change_norm × vol_rank
     score   = history × market
     fallback: if all market scores == 0, score = history × vol_rank
6. Sort by composite score descending
7. Spread-check top SCANNER_TOP_N×2 candidates, stop at SCANNER_TOP_N passes
8. Return list (held positions merged in bot.py — unchanged)
```

#### Scoring Log (INFO level per candidate)
```
[SCALPSCAN] RENDER/USDT:USDT  score=0.71 (hist=0.88 × mkt=0.81) | vol=$4.2M | 24h=+3.2%
[SCALPSCAN] XRP/USDT:USDT     score=0.44 (hist=0.55 × mkt=0.80) | vol=$21M  | 24h=+2.0%
```

---

### Change 2: Expand Universe Parameters (`.env` + `config.py`)

| Parameter | Old | New | Reason |
|---|---|---|---|
| `SCANNER_MIN_VOLUME` | $10,000,000 | $3,000,000 | Lets RENDER/INJ/DOGE qualify |
| `SCANNER_TOP_N` | 5 | 8 | More diversity, room for daytime rotation |
| `SCANNER_MIN_HISTORY_TRADES` | N/A | 10 (new) | Min trades before history score applies |

`config.py` additions:
```python
SCANNER_MIN_HISTORY_TRADES = int(os.getenv("SCANNER_MIN_HISTORY_TRADES", "10"))
```

---

### Change 3: Remove Daily Symbol Cap

Remove the `DAILY_SYMBOL_CAP` gate from `bot.py`.

**Existing protections that make the cap redundant:**
- Per-pair cooldown: 10 min lockout after any loss
- Streak blacklist: 4-hr lockout after 3 consecutive losses on same symbol
- Max open trades: 3 concurrent positions max (hard ceiling on exposure)

**Monitoring replacement:** log when a symbol is entered 4+ times in a UTC day:
```python
if daily_trades >= 4:
    logger.info(f"[RATE WATCH] {symbol} — {daily_trades+1}th entry today (monitoring)")
```
This preserves the daily counter and alerting without blocking trades.

---

## Affected Files

| File | Change |
|---|---|
| `scanner.py` | Replace `volatility_scan()` with performance-weighted version; add `_compute_history_scores()` helper |
| `config.py` | Add `SCANNER_MIN_HISTORY_TRADES` |
| `.env` | Update `SCANNER_MIN_VOLUME`, `SCANNER_TOP_N`; add `SCANNER_MIN_HISTORY_TRADES` |
| `bot.py` | Remove `DAILY_SYMBOL_CAP` gate block; add `[RATE WATCH]` log when daily_trades >= 4 |

---

## Fallback Behavior

| Failure | Behavior |
|---|---|
| `trading_state.json` missing/unreadable | All symbols get `history_score = 0.5` — graceful degradation to market-only scoring |
| Fewer than 8 candidates pass spread filter | Return however many passed — same as today |
| All market scores = 0 (dead market) | Fall back to `history_score × vol_rank` — prevents empty list |

---

## Success Criteria

- Scanner log shows composite scores with history and market components
- RENDER/INJ/DOGE appear in scan results when their volume qualifies ($3M+)
- Symbol rotation happens across the day — not the same 5 symbols locked in
- No `[RATE GATE] daily cap reached` log lines (gate removed)
- `[RATE WATCH]` lines appear when a symbol is entered 4+ times in a day
- Bot takes daytime trades when signals exist

---

## Out of Scope

- Time-of-day aware scoring (day vs night watchlists)
- Backtesting the scoring formula
- Performance-weighted blacklisting (auto-remove symbols below threshold)
- Kelly-based position sizing per symbol
