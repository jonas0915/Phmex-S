# Performance-Weighted Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the pure volume-sort scanner with a composite score (historical win rate × current market conditions) to surface profitable symbols like RENDER/INJ, expand universe to 8 symbols, and remove the redundant daily symbol cap.

**Architecture:** `scanner.py` gets a new `_compute_history_scores()` helper and a rewritten `volatility_scan()`. `bot.py` removes the daily cap gate and adds a RATE WATCH log. Config and `.env` update three parameters.

**Tech Stack:** Python 3.14, ccxt, trading_state.json (existing), math.exp (stdlib)

**Spec:** `docs/superpowers/specs/2026-04-16-performance-weighted-scanner-design.md`

---

### Task 1: Add `_compute_history_scores()` to scanner.py + config additions

**Files:**
- Modify: `scanner.py:6` (add `import math`, `import json`)
- Modify: `scanner.py` (add helper function after line 12)
- Modify: `config.py:63-64` (add `SCANNER_MIN_HISTORY_TRADES`, remove validation for `DAILY_SYMBOL_CAP`)

- [ ] **Step 1: Add imports to scanner.py**

At the top of `scanner.py`, the current imports are:
```python
import time
import threading
import ccxt
from config import Config
from logger import setup_logger
```

Replace with:
```python
import json
import math
import time
import threading
import ccxt
from config import Config
from logger import setup_logger
```

- [ ] **Step 2: Add `_compute_history_scores()` helper to scanner.py**

After line 12 (`logger = setup_logger()`), add:

```python

def _compute_history_scores(state_path: str = "trading_state.json",
                             min_trades: int = None) -> dict[str, float]:
    """
    Load trading_state.json and compute a history score per symbol.
    Returns {symbol: score} only for symbols with >= min_trades closed live trades.
    Score = sigmoid(avg_net_pnl_per_trade * 10), maps to [0,1] with 0.5 at breakeven.
    Symbols with < min_trades are absent — caller uses 0.5 (neutral) as default.
    """
    if min_trades is None:
        min_trades = Config.SCANNER_MIN_HISTORY_TRADES
    try:
        with open(state_path) as f:
            state = json.load(f)
    except Exception as e:
        logger.warning(f"[SCANNER] Could not load {state_path} for history scores: {e}")
        return {}

    # Accumulate per-symbol net PnL from closed live trades only
    symbol_pnl: dict[str, list[float]] = {}
    for t in state.get("closed_trades", []):
        if t.get("is_paper"):
            continue
        sym = t.get("symbol")
        if not sym:
            continue
        net = (t.get("pnl_usdt") or 0.0) - (t.get("fee_usdt") or 0.0)
        symbol_pnl.setdefault(sym, []).append(net)

    scores: dict[str, float] = {}
    for sym, pnl_list in symbol_pnl.items():
        if len(pnl_list) < min_trades:
            continue
        avg = sum(pnl_list) / len(pnl_list)
        scores[sym] = 1.0 / (1.0 + math.exp(-10.0 * avg))

    return scores
```

- [ ] **Step 3: Add `SCANNER_MIN_HISTORY_TRADES` to config.py**

Find these lines in `config.py` (~line 63):
```python
    SCANNER_TOP_N = int(os.getenv("SCANNER_TOP_N", "5"))           # top N gainers to trade
    SCANNER_MIN_VOLUME = float(os.getenv("SCANNER_MIN_VOLUME", "5000000"))  # min 24h USDT volume
```

Replace with:
```python
    SCANNER_TOP_N = int(os.getenv("SCANNER_TOP_N", "8"))            # top N symbols to trade
    SCANNER_MIN_VOLUME = float(os.getenv("SCANNER_MIN_VOLUME", "3000000"))  # min 24h USDT volume
    SCANNER_MIN_HISTORY_TRADES = int(os.getenv("SCANNER_MIN_HISTORY_TRADES", "10"))  # min trades before history score applies
```

- [ ] **Step 4: Remove `DAILY_SYMBOL_CAP` validation from config.py**

Find and remove these lines from config.py validation block (~line 80):
```python
        if cls.DAILY_SYMBOL_CAP < 1:
            raise ValueError("DAILY_SYMBOL_CAP must be at least 1")
```

Leave the `DAILY_SYMBOL_CAP` field declaration in place (bot.py still reads `daily_trades` for RATE WATCH logging — it just doesn't gate on it).

- [ ] **Step 5: Verify syntax**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile scanner.py && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile config.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 6: Verify `_compute_history_scores` returns sensible values**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -c "
from scanner import _compute_history_scores
scores = _compute_history_scores()
print(f'Symbols scored: {len(scores)}')
for sym, score in sorted(scores.items(), key=lambda x: -x[1]):
    print(f'  {sym:<30} {score:.3f}')
"
```
Expected: several symbols printed with scores between 0 and 1. Best symbols (RENDER, INJ) should be near 0.7+. Worst symbols (TRUMP, TIA, NEAR) should be near 0.1-0.3. If those are still in the blacklist they won't appear.

- [ ] **Step 7: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add scanner.py config.py && git commit -m "feat: add _compute_history_scores() + scanner config updates"
```

---

### Task 2: Rewrite `volatility_scan()` with performance-weighted scoring

**Files:**
- Modify: `scanner.py:81-154` (replace `volatility_scan()` body)

- [ ] **Step 1: Replace `volatility_scan()` in scanner.py**

Find the entire `volatility_scan` function (lines 81–154) and replace it with:

```python
def volatility_scan(client, top_n: int = None, min_volume: float = None) -> list[str]:
    """
    Performance-weighted scan — ranks USDT perpetuals by composite score.
    composite = history_score x market_score
    history_score: sigmoid(avg_net_pnl) from trading_state.json (neutral 0.5 if < min_trades)
    market_score:  abs(change_24h)/15 x (symbol_volume/max_volume) — movement x liquidity
    Fallback: if all market scores are 0, uses history_score x vol_rank only.
    """
    top_n = top_n or Config.SCANNER_TOP_N
    min_volume = min_volume or Config.SCANNER_MIN_VOLUME
    pool_size = top_n * 4  # wider candidate pool for scoring (up to 40 if top_n=8 → 32)

    # Step 1: Fetch all tickers
    try:
        tickers = client.fetch_tickers()
    except Exception as e:
        logger.error(f"[SCALPSCAN] Failed to fetch tickers: {e}")
        return None  # signal failure so caller keeps current pairs

    # Step 2: Build universe — USDT perps above volume floor, not blacklisted
    universe = []
    for symbol, t in tickers.items():
        if not symbol.endswith("/USDT:USDT"):
            continue
        info = t.get("info", {})
        try:
            close  = float(info.get("closeRp") or 0)
            open_  = float(info.get("openRp")  or 0)
            volume = float(info.get("turnoverRv") or 0)
            if close > 0 and open_ > 0 and volume >= min_volume:
                change_24h = (close - open_) / open_ * 100
                universe.append({"symbol": symbol, "price": close,
                                  "change_24h": change_24h, "volume": volume})
        except Exception:
            continue

    universe = [x for x in universe if x["symbol"] not in Config.SCANNER_BLACKLIST]
    if not universe:
        logger.warning("[SCALPSCAN] No qualifying pairs found, keeping current pairs.")
        return None

    # Step 3: Take top pool_size candidates by volume
    universe.sort(key=lambda x: x["volume"], reverse=True)
    candidates = universe[:pool_size]

    # Step 4: Load history scores from trading_state.json
    history_scores = _compute_history_scores()

    # Step 5: Compute composite score for each candidate
    max_vol = max(c["volume"] for c in candidates) if candidates else 1.0
    for c in candidates:
        hist  = history_scores.get(c["symbol"], 0.5)
        change_norm = min(abs(c["change_24h"]) / 15.0, 1.0)
        vol_rank    = c["volume"] / max_vol
        mkt   = change_norm * vol_rank
        c["history_score"] = hist
        c["market_score"]  = mkt
        c["composite"]     = hist * mkt

    # Fallback: if all market scores are 0, use history x vol_rank
    if all(c["composite"] == 0 for c in candidates):
        logger.warning("[SCALPSCAN] All market scores zero — falling back to history x vol_rank")
        for c in candidates:
            c["composite"] = c["history_score"] * (c["volume"] / max_vol)

    # Step 6: Sort by composite score descending
    candidates.sort(key=lambda x: x["composite"], reverse=True)

    # Step 7: Spread-filter top candidates, stop at top_n passes
    filtered = []
    for item in candidates[:top_n * 2]:
        symbol = item["symbol"]
        try:
            ob = client.fetch_order_book(symbol, limit=5)
            if ob and ob.get("bids") and ob.get("asks"):
                best_bid = ob["bids"][0][0]
                best_ask = ob["asks"][0][0]
                spread_pct = (best_ask - best_bid) / best_bid * 100
                if spread_pct > 0.15:
                    logger.debug(f"[SCANNER] {symbol} spread too wide ({spread_pct:.3f}%), skipping")
                    continue
            filtered.append(item)
            time.sleep(1)
        except Exception:
            filtered.append(item)  # if OB fetch fails, keep the pair
        if len(filtered) >= top_n:
            break

    top = filtered[:top_n]

    if top:
        logger.info(f"[SCALPSCAN] Top {len(top)} by composite score:")
        for c in top:
            logger.info(
                f"  {c['symbol']:<25} score={c['composite']:.3f}"
                f" (hist={c['history_score']:.2f} x mkt={c['market_score']:.2f})"
                f" | vol=${c['volume']:,.0f} | 24h={c['change_24h']:>+5.1f}%"
            )
    else:
        logger.warning("[SCALPSCAN] No results after spread filter, keeping current pairs.")
        return None

    return [c["symbol"] for c in top]
```

- [ ] **Step 2: Verify syntax**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile scanner.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 3: Smoke-test the scan (dry run)**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -c "
import ccxt
from config import Config
from scanner import volatility_scan

exchange_class = getattr(ccxt, Config.EXCHANGE)
client = exchange_class({'enableRateLimit': True, 'timeout': 10000, 'options': {'defaultType': 'swap'}})
client.load_markets()
result = volatility_scan(client, top_n=8, min_volume=3000000)
print('Result:', result)
"
```
Expected: list of 8 symbols including symbols beyond BTC/ETH/XRP/SUI/LINK. Should see composite score log lines. Should NOT crash.

- [ ] **Step 4: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add scanner.py && git commit -m "feat: rewrite volatility_scan() with composite history x market scoring"
```

---

### Task 3: Remove daily cap gate from bot.py, add RATE WATCH log

**Files:**
- Modify: `bot.py:894-901`

- [ ] **Step 1: Replace the daily cap gate with RATE WATCH log**

Find this block in `bot.py` (~lines 894–901):
```python
            # Per-symbol daily trade cap: max 3 trades per symbol per day
            day_start = time.time() - (time.time() % 86400)  # midnight UTC
            daily_trades = sum(1 for t in self.risk.closed_trades
                               if t.get("symbol") == symbol and t.get("opened_at", 0) > day_start)
            daily_trades += 1 if symbol in self.risk.positions else 0  # count open positions too
            if daily_trades >= Config.DAILY_SYMBOL_CAP:
                logger.debug(f"[RATE GATE] {symbol} — daily cap reached ({daily_trades}/{Config.DAILY_SYMBOL_CAP} trades today)")
                continue
```

Replace with:
```python
            # Daily trade counter — no hard cap, but log when a symbol trades frequently
            day_start = time.time() - (time.time() % 86400)  # midnight UTC
            daily_trades = sum(1 for t in self.risk.closed_trades
                               if t.get("symbol") == symbol and t.get("opened_at", 0) > day_start)
            daily_trades += 1 if symbol in self.risk.positions else 0  # count open positions too
            if daily_trades >= 4:
                logger.info(f"[RATE WATCH] {symbol} — {daily_trades + 1}th entry today (no cap, monitoring)")
```

- [ ] **Step 2: Verify syntax**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 3: Verify RATE GATE is gone, RATE WATCH is present**

```bash
grep -n "RATE GATE\|RATE WATCH\|DAILY_SYMBOL_CAP\|daily cap" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```
Expected: no `RATE GATE` lines (removed), one `RATE WATCH` line present, no `DAILY_SYMBOL_CAP` reference in the gate logic.

- [ ] **Step 4: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add bot.py && git commit -m "feat: remove daily symbol cap gate, add RATE WATCH monitoring log"
```

---

### Task 4: Update `.env` parameters

**Files:**
- Modify: `.env`

- [ ] **Step 1: Update `.env`**

Find and update these lines in `.env`:
```
DAILY_SYMBOL_CAP=3
SCANNER_TOP_N=5
SCANNER_MIN_VOLUME=10000000
```

Replace with:
```
DAILY_SYMBOL_CAP=3
SCANNER_TOP_N=8
SCANNER_MIN_VOLUME=3000000
SCANNER_MIN_HISTORY_TRADES=10
```

Note: `DAILY_SYMBOL_CAP` stays in `.env` so config.py doesn't break — but the gate that reads it has been replaced by RATE WATCH logging. It can be removed from `.env` in a future cleanup.

- [ ] **Step 2: Verify config loads cleanly**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -c "
from config import Config
Config.validate()
print(f'SCANNER_TOP_N={Config.SCANNER_TOP_N}')
print(f'SCANNER_MIN_VOLUME={Config.SCANNER_MIN_VOLUME}')
print(f'SCANNER_MIN_HISTORY_TRADES={Config.SCANNER_MIN_HISTORY_TRADES}')
"
```
Expected:
```
SCANNER_TOP_N=8
SCANNER_MIN_VOLUME=3000000.0
SCANNER_MIN_HISTORY_TRADES=10
```

- [ ] **Step 3: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add .env && git commit -m "config: scanner top_n 5→8, min_volume 10M→3M, add min_history_trades=10"
```

---

### Task 5: Pre-Restart Audit + Restart

- [ ] **Step 1: Run `/pre-restart-audit` skill**

Invoke the `pre-restart-audit` skill. Do not proceed until audit passes.

- [ ] **Step 2: Kill old bot, clear cache, restart**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
kill $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 2
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
sleep 5
cat .bot.pid
```
Expected: new PID printed.

- [ ] **Step 3: Verify scanner used composite scoring**

```bash
sleep 10 && grep "SCALPSCAN\|composite\|hist=" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -20
```
Expected: log lines showing `score=X.XXX (hist=X.XX x mkt=X.XX)` format. New symbols beyond the old 5 may appear if their composite score qualifies.

- [ ] **Step 4: Verify RATE GATE is gone from logs**

```bash
grep "RATE GATE" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -5
```
Expected: no output (gate removed). Any `[RATE WATCH]` lines are the new monitoring log — those are expected.

- [ ] **Step 5: Verify no Python errors in first cycle**

```bash
grep -i "error\|traceback\|exception" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -10
```
Expected: no new errors after restart timestamp.
