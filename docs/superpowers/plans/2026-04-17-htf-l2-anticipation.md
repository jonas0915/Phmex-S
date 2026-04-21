# htf_l2_anticipation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new parallel trading strategy `htf_l2_anticipation` that uses L2 orderbook depth and tape flow signals to enter pullback setups before the candle confirms, enabling earlier entries while leaving `htf_confluence_pullback` unchanged.

**Architecture:** Three-file change — (1) new strategy function in `strategies.py` reusing the existing setup gates, (2) router integration in `confluence_strategy` + bot.py to pass the `flow` dict to strategies, (3) tagging updates across notifier/reports/dashboard. No config changes in v1 (thresholds hardcoded for initial measurement).

**Tech Stack:** Python 3.14, pandas, existing ws_feed + exchange modules

**Spec:** `docs/superpowers/specs/2026-04-17-htf-l2-anticipation-design.md`

---

### Task 1: Add `htf_l2_anticipation` function to strategies.py

**Files:**
- Modify: `strategies.py` (add function before `confluence_strategy` at line ~950)

- [ ] **Step 1: Add the new strategy function**

Insert this function right before `def confluence_strategy` (currently at line 953):

```python
def htf_l2_anticipation(
    df: pd.DataFrame,
    orderbook: dict = None,
    htf_df: pd.DataFrame = None,
    flow: dict = None,
) -> TradeSignal:
    """
    Pullback strategy that confirms entries via L2/tape signals instead of closed candle.
    Shares setup detection with htf_confluence_pullback — differs only in entry trigger.
    Requires flow dict from ws_feed. Returns HOLD if flow is None or trade_count < 5.
    """
    # Pre-checks (same as htf_confluence_pullback)
    if htf_df is None or len(htf_df) < 30:
        return TradeSignal(Signal.HOLD, "l2_anticipation: no HTF data", 0.0)
    if len(df) < 50:
        return TradeSignal(Signal.HOLD, "l2_anticipation: not enough 5m data", 0.0)
    if flow is None or flow.get("trade_count", 0) < 5:
        return TradeSignal(Signal.HOLD, "l2_anticipation: insufficient tape (flow absent or <5 trades)", 0.0)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    htf = htf_df.iloc[-1]

    close = last["close"]
    rsi = last.get("rsi", 50)
    volume = prev["volume"]
    vol_avg = df["volume"].iloc[-21:-1].mean()
    vwap = last.get("vwap", 0)
    ema_21 = last.get("ema_21", 0)
    ema_50 = last.get("ema_50", 0)

    htf_adx = htf.get("adx", 0)
    htf_ema21 = htf.get("ema_21", 0)
    htf_ema50 = htf.get("ema_50", 0)
    htf_close = htf.get("close", 0)

    if htf_adx < 25:
        return TradeSignal(Signal.HOLD, f"l2_anticipation: 1h ADX {htf_adx:.1f} < 25", 0.0)
    if vol_avg <= 0 or volume < vol_avg * 0.6:
        return TradeSignal(Signal.HOLD, f"l2_anticipation: vol {volume/max(vol_avg,1e-10):.2f}x < 0.6x", 0.0)
    if vwap <= 0 or pd.isna(vwap):
        return TradeSignal(Signal.HOLD, "l2_anticipation: no VWAP", 0.0)
    if ema_21 == 0 or ema_50 == 0:
        return TradeSignal(Signal.HOLD, "l2_anticipation: EMAs warming up", 0.0)

    direction = None

    # Setup detection (identical to htf_confluence_pullback minus bouncing/momentum)
    htf_long = htf_ema21 > htf_ema50 and htf_close > htf_ema50 and htf_adx >= 20
    vwap_long = close > vwap
    pullback_to_ema = (abs(close - ema_21) / ema_21 < 0.005) or (abs(close - ema_50) / ema_50 < 0.005)
    rsi_long = 35 <= rsi <= 60

    htf_short = htf_ema21 < htf_ema50 and htf_close < htf_ema50 and htf_adx >= 20
    vwap_short = close < vwap
    rsi_short = 40 <= rsi <= 65

    long_setup = htf_long and vwap_long and pullback_to_ema and rsi_long
    short_setup = htf_short and vwap_short and pullback_to_ema and rsi_short

    if not (long_setup or short_setup):
        if not (htf_long or htf_short):
            detail = "1h no trend"
        elif not (vwap_long or vwap_short):
            detail = f"VWAP mismatch (close={close:.4f} vwap={vwap:.4f})"
        elif not pullback_to_ema:
            dist21 = abs(close - ema_21) / ema_21 * 100
            dist50 = abs(close - ema_50) / ema_50 * 100
            detail = f"no pullback (EMA21 dist={dist21:.2f}% EMA50 dist={dist50:.2f}%)"
        else:
            detail = f"RSI {rsi:.1f} out of range"
        return TradeSignal(Signal.HOLD, f"l2_anticipation: {detail}", 0.0)

    # L2/tape confirmation (REPLACES bouncing + momentum confirmation)
    buy_ratio = flow.get("buy_ratio", 0.5)
    cvd_slope = flow.get("cvd_slope", 0.0)
    bid_depth = orderbook.get("bid_depth_usdt", 0) if orderbook else 0
    ask_depth = orderbook.get("ask_depth_usdt", 0) if orderbook else 0

    if long_setup:
        req1 = buy_ratio > 0.55
        req2 = cvd_slope > 0
        req3 = bid_depth > ask_depth
        if not (req1 and req2 and req3):
            reasons = []
            if not req1: reasons.append(f"buy_ratio {buy_ratio:.2f}<0.55")
            if not req2: reasons.append(f"cvd_slope {cvd_slope:.2f}<=0")
            if not req3: reasons.append(f"bid_depth {bid_depth:.0f}<=ask_depth {ask_depth:.0f}")
            return TradeSignal(Signal.HOLD, f"l2_anticipation: long L2 fail ({', '.join(reasons)})", 0.0)
        direction = Signal.BUY
    else:
        req1 = buy_ratio < 0.45
        req2 = cvd_slope < 0
        req3 = ask_depth > bid_depth
        if not (req1 and req2 and req3):
            reasons = []
            if not req1: reasons.append(f"buy_ratio {buy_ratio:.2f}>=0.45")
            if not req2: reasons.append(f"cvd_slope {cvd_slope:.2f}>=0")
            if not req3: reasons.append(f"ask_depth {ask_depth:.0f}<=bid_depth {bid_depth:.0f}")
            return TradeSignal(Signal.HOLD, f"l2_anticipation: short L2 fail ({', '.join(reasons)})", 0.0)
        direction = Signal.SELL

    # Strength calculation
    strength = 0.82

    # Booster 1: whale accumulation
    lt_bias = flow.get("large_trade_bias", 0.0)
    if direction == Signal.BUY and lt_bias > 0.2:
        strength += 0.03
    elif direction == Signal.SELL and lt_bias < -0.2:
        strength += 0.03

    # Booster 2: support/resistance wall within 1%
    price = close
    if orderbook:
        bid_walls = orderbook.get("bid_walls", []) or []
        ask_walls = orderbook.get("ask_walls", []) or []

        if direction == Signal.BUY and bid_walls:
            bid_dists = [(price - w[0]) / price * 100 for w in bid_walls if w[0] < price]
            if bid_dists:
                nearest = min(bid_dists)
                if 0 < nearest < 1.0:
                    strength += 0.02
        elif direction == Signal.SELL and ask_walls:
            ask_dists = [(w[0] - price) / price * 100 for w in ask_walls if w[0] > price]
            if ask_dists:
                nearest = min(ask_dists)
                if 0 < nearest < 1.0:
                    strength += 0.02

        # Booster 3: no adverse wall within 0.5%
        if direction == Signal.BUY:
            has_near_ask = any(0 < (w[0] - price) / price * 100 < 0.5 for w in ask_walls)
            if not has_near_ask:
                strength += 0.02
        else:
            has_near_bid = any(0 < (price - w[0]) / price * 100 < 0.5 for w in bid_walls)
            if not has_near_bid:
                strength += 0.02

        # OB imbalance gate (identical to htf_confluence_pullback)
        if orderbook.get("illiquid", False):
            return TradeSignal(Signal.HOLD, "l2_anticipation: illiquid", 0.0)
        imb = orderbook.get("imbalance", 0)
        if direction == Signal.BUY and imb < -0.3:
            return TradeSignal(Signal.HOLD, f"l2_anticipation: OB blocks long ({imb:.2f})", 0.0)
        if direction == Signal.SELL and imb > 0.3:
            return TradeSignal(Signal.HOLD, f"l2_anticipation: OB blocks short ({imb:.2f})", 0.0)
        if (direction == Signal.BUY and imb > 0.15) or (direction == Signal.SELL and imb < -0.15):
            strength += 0.02

    dir_str = "LONG" if direction == Signal.BUY else "SHORT"
    reason = (
        f"L2 ANTICIPATION {dir_str} | 1h ADX={htf_adx:.1f} | buy_ratio={buy_ratio:.2f}"
        f" | cvd_slope={cvd_slope:.2f} | bid/ask depth={bid_depth:.0f}/{ask_depth:.0f}"
        f" | RSI={rsi:.1f}"
    )
    return TradeSignal(direction, reason, min(strength, 0.92))
```

- [ ] **Step 2: Syntax check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile strategies.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add strategies.py && git commit -m "feat: add htf_l2_anticipation strategy function"
```

---

### Task 2: Integrate into `confluence_strategy` router + add to STRATEGIES dict

**Files:**
- Modify: `strategies.py` (confluence_strategy function ~line 953, STRATEGIES dict ~line 1304)

- [ ] **Step 1: Update `confluence_strategy` signature to accept flow**

Find this line (~line 953):
```python
def confluence_strategy(df: pd.DataFrame, orderbook: dict = None, htf_df: pd.DataFrame = None) -> TradeSignal:
```

Replace with:
```python
def confluence_strategy(df: pd.DataFrame, orderbook: dict = None, htf_df: pd.DataFrame = None, flow: dict = None) -> TradeSignal:
```

- [ ] **Step 2: Add htf_l2_anticipation to the router signal list**

Find these lines inside `confluence_strategy` (~line 971-972):
```python
    if htf_adx >= 20:
        signals.append(htf_confluence_pullback(df, orderbook, htf_df))
```

Replace with:
```python
    if htf_adx >= 20:
        signals.append(htf_confluence_pullback(df, orderbook, htf_df))
        signals.append(htf_l2_anticipation(df, orderbook, htf_df, flow))
```

- [ ] **Step 3: Add htf_l2_anticipation to STRATEGIES dict**

Find the STRATEGIES dict (~line 1304):
```python
STRATEGIES = {
    "trend_scalp":              trend_scalp_strategy,
    ...
    "funding_contrarian":       funding_rate_contrarian_strategy,
}
```

Add this entry before the closing brace:
```python
    "htf_l2_anticipation":      htf_l2_anticipation,
```

- [ ] **Step 4: Syntax check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile strategies.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add strategies.py && git commit -m "feat: wire htf_l2_anticipation into confluence router + STRATEGIES dict"
```

---

### Task 3: Update bot.py to pass `flow` to strategy_fn + update strategy name extraction

**Files:**
- Modify: `bot.py:22-43` (_extract_strategy_name)
- Modify: `bot.py:935-941` (main strategy call site — move flow fetch before)

- [ ] **Step 1: Add L2 anticipation detection to `_extract_strategy_name`**

Find this function in bot.py (starting at line 22):
```python
def _extract_strategy_name(reason: str) -> str:
    """Derive strategy key from signal reason string for time exit lookup."""
    r = reason.lower()
    if "kc squeeze" in r or "keltner" in r:
        return "keltner_squeeze"
    if "bb" in r or "mean reversion" in r:
        return "bb_mean_reversion"
    if "trend pullback" in r:
        return "trend_pullback"
    if "trend scalp" in r or "trend_scalp" in r:
        return "trend_scalp"
    if "momentum cont" in r or "momentum_continuation" in r:
        return "momentum_continuation"
    if "vwap reversion" in r or "vwap_reversion" in r:
        return "vwap_reversion"
    if "confluence pullback" in r:
        return "htf_confluence_pullback"
    if "confluence vwap" in r:
        return "htf_confluence_vwap"
    if "liq_cascade" in r:
        return "liq_cascade"
    return ""
```

Replace with (add one new check before `confluence pullback`):
```python
def _extract_strategy_name(reason: str) -> str:
    """Derive strategy key from signal reason string for time exit lookup."""
    r = reason.lower()
    if "kc squeeze" in r or "keltner" in r:
        return "keltner_squeeze"
    if "bb" in r or "mean reversion" in r:
        return "bb_mean_reversion"
    if "trend pullback" in r:
        return "trend_pullback"
    if "trend scalp" in r or "trend_scalp" in r:
        return "trend_scalp"
    if "momentum cont" in r or "momentum_continuation" in r:
        return "momentum_continuation"
    if "vwap reversion" in r or "vwap_reversion" in r:
        return "vwap_reversion"
    if "l2 anticipation" in r:
        return "htf_l2_anticipation"
    if "confluence pullback" in r:
        return "htf_confluence_pullback"
    if "confluence vwap" in r:
        return "htf_confluence_vwap"
    if "liq_cascade" in r:
        return "liq_cascade"
    return ""
```

- [ ] **Step 2: Move flow fetch before strategy call**

Find this block in bot.py (~line 935-941):
```python
            # Fetch orderbook and HTF data for strategy confirmation
            ob = self.exchange.get_order_book(symbol)
            htf_df = self._fetch_htf_data(symbol)
            try:
                signal = self.strategy_fn(df, ob, htf_df=htf_df)
            except TypeError:
                signal = self.strategy_fn(df, ob)
```

Replace with:
```python
            # Fetch orderbook, HTF data, and tape flow for strategy confirmation
            ob = self.exchange.get_order_book(symbol)
            htf_df = self._fetch_htf_data(symbol)
            flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
            try:
                signal = self.strategy_fn(df, ob, htf_df=htf_df, flow=flow)
            except TypeError:
                try:
                    signal = self.strategy_fn(df, ob, htf_df=htf_df)
                except TypeError:
                    signal = self.strategy_fn(df, ob)
```

This preserves backward compatibility with older strategies that don't accept `flow` or `htf_df`.

- [ ] **Step 3: Remove duplicate flow fetch later in the loop**

Find this line (~line 964 — was the original flow fetch):
```python
                flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None
```

Check the surrounding context first:
```bash
sed -n '960,970p' /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

If this line appears after the strategy call (now redundant since we fetch earlier), remove only this single line. If there's any logic that depends on re-fetching, leave it. Most likely: the line can simply be deleted because `flow` is already in scope from the earlier fetch.

- [ ] **Step 4: Syntax check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 5: Verify flow is passed correctly**

```bash
grep -n "strategy_fn(df, ob" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```
Expected: at least one line with `flow=flow` parameter.

- [ ] **Step 6: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add bot.py && git commit -m "feat: pass flow dict to strategy_fn + extract htf_l2_anticipation name"
```

---

### Task 4: Add htf_l2_anticipation to trend_strats and HTF cluster throttle

**Files:**
- Modify: `bot.py:284` (trend_strats set)
- Modify: `bot.py:1134` (HTF cluster throttle)

- [ ] **Step 1: Update trend_strats set**

Find this line in bot.py (~line 284):
```python
        trend_strats = {"momentum_continuation", "trend_pullback", "keltner_squeeze", "htf_confluence_pullback"}
```

Replace with:
```python
        trend_strats = {"momentum_continuation", "trend_pullback", "keltner_squeeze", "htf_confluence_pullback", "htf_l2_anticipation"}
```

- [ ] **Step 2: Update HTF cluster throttle**

Find this line in bot.py (~line 1134):
```python
                if strat_name == "htf_confluence_pullback" and time.time() - self._last_htf_entry_time < 1800:
```

Replace with:
```python
                if strat_name in ("htf_confluence_pullback", "htf_l2_anticipation") and time.time() - self._last_htf_entry_time < 1800:
```

Rationale: both strategies enter on HTF confluence setups. A 30-min throttle shared across both prevents double-entries on the same setup when one strategy fires right after the other.

- [ ] **Step 3: Syntax check + verify**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
grep -n "htf_l2_anticipation" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```
Expected: `OK` + at least 3 matches (extract_strategy_name, trend_strats, htf throttle).

- [ ] **Step 4: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add bot.py && git commit -m "feat: include htf_l2_anticipation in trend_strats + HTF cluster throttle"
```

---

### Task 5: Update reporting/tagging in notifier, daily_report, and dashboard

**Files:**
- Modify: `notifier.py` — if strategy-name display exists
- Modify: `scripts/daily_report.py` — strategy breakdown table
- Modify: `web_dashboard.py` — strategy filter

- [ ] **Step 1: Check if notifier needs changes**

```bash
grep -n "htf_confluence_pullback\|htf_confluence_vwap\|strategy.*name" /Users/jonaspenaso/Desktop/Phmex-S/notifier.py | head -20
```

If notifier references specific strategy names with custom emojis/labels (like existing patterns), add `htf_l2_anticipation` alongside. If it just uses the raw string from the trade record, no change needed.

If a custom label block exists (e.g., `if strat == "htf_confluence_pullback": emoji = "📈"`), add a new line:
```python
    elif strat == "htf_l2_anticipation": emoji = "⚡"
```

If no custom label block exists, skip this step.

- [ ] **Step 2: Check daily_report.py**

```bash
grep -n "htf_confluence_pullback\|strategy_name\|by Strategy" /Users/jonaspenaso/Desktop/Phmex-S/scripts/daily_report.py | head -20
```

The daily report's "by Strategy" section should already aggregate by whatever `strategy_name` value is in the trade records — no code change needed, the new strategy will appear automatically as trades tagged with it accumulate.

If there's a hardcoded strategy allow-list, add `"htf_l2_anticipation"` to it.

- [ ] **Step 3: Check web_dashboard.py**

```bash
grep -n "htf_confluence_pullback\|strategy.*filter\|strategy.*dropdown" /Users/jonaspenaso/Desktop/Phmex-S/web_dashboard.py | head -20
```

If there's a hardcoded dropdown of strategy names, add `"htf_l2_anticipation"`. If the dropdown is built dynamically from data, no change needed.

- [ ] **Step 4: Commit any changes made**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add -A && git diff --cached --stat
```

If there are changes:
```bash
git commit -m "feat: tag htf_l2_anticipation in reporting surfaces"
```

If no changes were needed, skip the commit.

---

### Task 6: Pre-Restart Audit + Restart

- [ ] **Step 1: Run `/pre-restart-audit` skill**

Invoke the `pre-restart-audit` skill. Do not proceed until all checks pass.

- [ ] **Step 2: Kill old bot, clear pycache, restart**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
kill $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 2
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
sleep 6
cat .bot.pid
```
Expected: new PID printed.

- [ ] **Step 3: Verify bot started cleanly**

```bash
sleep 15 && grep -i "error\|traceback\|exception" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -10
```
Expected: no new errors after restart timestamp.

- [ ] **Step 4: Verify L2 anticipation strategy is being evaluated**

```bash
grep "l2_anticipation\|L2 ANTICIPATION" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -20
```
Expected: HOLD messages from the new strategy with specific rejection reasons (insufficient tape, no pullback, L2 signals not aligned, etc.). These confirm it's being called.

- [ ] **Step 5: Verify existing strategy still fires**

```bash
grep "CONFLUENCE PULLBACK\|confluence_pullback" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -10
```
Expected: continued activity from the original strategy (either signals or HOLD messages).
