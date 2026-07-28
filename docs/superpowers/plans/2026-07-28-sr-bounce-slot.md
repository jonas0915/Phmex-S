# SR_BOUNCE Paper Slot (Stage A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship SR_BOUNCE as a paper forward-test slot (owner order 2026-07-28, overriding the spec §4 "only if scan survives" gate — the scan's DO-NOT-BUILD verdict stays on record as the prior; the slot's job is to measure what the scan could not: real fill selection on live tape).

**Architecture:** Pure signal module `sr_bounce.py` at repo root (ports the scan's frozen level/geometry math — house pattern of `donchian_slot.py`/`tsm_slot.py`), registered as a real `STRATEGIES` key so the generic slot loop runs it with full gate parity. Structural per-trade exits ride a small backward-compatible `TradeSignal` extension (`sl_price`/`tp_price`, default None). Adjudicator gets a pre-registered `[sr_bounce]` verdict line. Dashboard tombstone card becomes a live state-driven card that keeps the scan verdict in its caption.

**Tech Stack:** Python 3.14, pandas; existing bot frameworks only. No new dependencies.

## Global Constraints (frozen — spec 2026-07-28 §2, identical to the scan)

- Signal params: k=3 pivots on 1h, 0.25×ATR(1h,14) cluster width, ≥2 touches (gap ≥3 candles), 1h ADX(14) < 30 regime gate, confirmed rejection on 5m (support: `low <= zone_hi and close > zone_hi`).
- Geometry: SL = far zone edge ∓ 0.25×ATR(5m,14); TP = nearest opposing validated zone capped at 3× risk; skip if room < 1× risk or risk ≤ 0.
- Slot: `paper_mode=True`, `trade_amount_usdt=5.0`, `max_positions=1`, `entry_patience_s=45.0`, no re-quote, standard OB/tape slot gates (NO carve-outs), signal strength 0.82 (clears the 0.80 slot floor, matches vwap_sma_cross precedent).
- Pre-registered adjudicator lines (owner 2026-07-28): KILL at n=50 paper trades if fee-adjusted net ≤ $0; no early PASS; WATCH before n=50. The digest line must cite the scan prior ("scan predicted −$0.07/t; forward test measures fill selection").
- `TradeSignal` extension MUST be backward compatible: new fields default None; zero existing callers change behavior; full suite (597) must stay green.
- Never touch: live sizing, halts, main-book logic, any .env value. Commit scope: only the files each task names.
- Time-format rule: any user-facing timestamps in 12-hour AM/PM PT.

## File Structure

```
sr_bounce.py                 # pure signal math + sr_bounce() strategy fn (NEW)
strategies.py                # TradeSignal +2 optional fields; STRATEGIES registers "sr_bounce"
bot.py                       # SR_BOUNCE StrategySlot; slot entry paths honor signal.sl_price/tp_price
scripts/lab_adjudicator/adjudicate.py   # EXPERIMENTS["sr_bounce"] + grade_sr_bounce + digest line
web_dashboard.py             # tombstone card → live card (scan verdict kept in caption)
tests/test_sr_bounce.py      # signal math + wiring (NEW)
tests/test_sr_bounce_slot.py # slot entry structural-exit plumbing (NEW)
tests/test_lab_adjudicator.py# +sr_bounce grader tests; digest count 7→8
tests/test_dashboard_v2.py   # SR_BOUNCE box assertion update
```

---

### Task 1: Pure signal module (`sr_bounce.py`)

**Files:**
- Create: `sr_bounce.py` (repo root)
- Create: `tests/test_sr_bounce.py`

**Interfaces:**
- Produces (consumed by Task 2's STRATEGIES wrapper and Task 3's tests):
  - All pure functions ported VERBATIM from `scripts/research/sr-bounce-scan/`: `atr`, `adx`, `find_pivots`, `cluster_zones`, `count_touches`, `validated_zones` (from `sr_levels.py`), `confirmed_rejection`, `plan_trade` (from `sr_signal.py`). Same signatures, same frozen constants. Add a module docstring: "Ported 2026-07-28 from the kill-gate scan (reports/2026-07-28-sr-bounce-scan.md) — scan verdict DO-NOT-BUILD; this module powers the owner-ordered paper forward test. Parameters FROZEN; edit only with a new spec."
  - `sr_bounce(df, orderbook=None, htf_df=None)` → returns a `strategies.TradeSignal`. Logic:
    1. `htf_df is None or len(htf_df) < 100` → HOLD "sr_bounce: no/short 1h context".
    2. `adx(htf_df).iloc[-1] >= 30` → HOLD "sr_bounce: 1h ADX {x:.1f} >= 30 (trending)".
    3. `zones = validated_zones(htf_df)`; empty → HOLD "sr_bounce: no validated zones".
    4. Last CLOSED 5m candle = `df.iloc[-2]` (mirror the scan's completed-candle discipline; `df.iloc[-1]` is the forming candle). Build `candle = {"open","high","low","close"}` from it.
    5. First zone with `confirmed_rejection(candle, zone)` → `plan = plan_trade(zone, zones, atr5, entry=candle["close"])` where `atr5 = float(atr(df.tail(100)).iloc[-1])`. `plan is None` → HOLD "sr_bounce: rejection at zone but no room (skip rule)".
    6. Return `TradeSignal(BUY|SELL, reason, 0.82, sl_price=plan["sl"], tp_price=plan["tp"])` with reason `f"SR BOUNCE {side} | zone {zone['lo']:.6g}-{zone['hi']:.6g} ({zone['touches']} touches) | SL {plan['sl']:.6g} TP {plan['tp']:.6g}"`.
    7. No rejection anywhere → HOLD "sr_bounce: no rejection at validated zones".
  - NOTE: this task writes `sr_bounce()` returning a plain dict `{"signal": "buy"|"sell"|"hold", "reason": str, "strength": float, "sl_price": float|None, "tp_price": float|None}` ONLY IF importing TradeSignal creates a circular import (strategies.py will import sr_bounce). Check first: `strategies.py` must import `sr_bounce` module; `sr_bounce.py` importing `from strategies import TradeSignal, Signal` is circular. RESOLUTION (required design): `sr_bounce.py` stays TradeSignal-free — it exposes `evaluate(df, orderbook, htf_df) -> dict` with the shape above, and Task 2's thin wrapper in strategies.py converts dict → TradeSignal. Tests in this task assert on the dict.

- [ ] **Step 1: Write failing tests** — port the scan's proven fixtures:

```python
# tests/test_sr_bounce.py
import sys
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import pandas as pd
import sr_bounce as sb


def _mk(rows, start_ts=0, step_ms=3_600_000):
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df["ts"] = [start_ts + i * step_ms for i in range(len(df))]
    df["volume"] = 100.0
    return df[["ts", "open", "high", "low", "close", "volume"]]


def _flat_1h(n=150):
    """Scan's proven fixture: triangle wave 99-101, zero-width zones at
    98.5 (support) / 101.5 (resistance), low ADX by construction."""
    rows = []
    for i in range(n):
        ph = i % 10
        px = 101 - 0.4 * ph if ph < 5 else 99 + 0.4 * (ph - 5)
        rows.append((px + 0.2, px + 0.5, px - 0.5, px))
    return _mk(rows)


def _5m(rows):
    return _mk(rows, start_ts=120 * 3_600_000, step_ms=300_000)


def test_ported_math_matches_scan():
    df1h = _flat_1h()
    zones = sb.validated_zones(df1h)
    assert any(z["side"] == "support" and abs(z["lo"] - 98.5) < 1e-9 for z in zones)
    assert any(z["side"] == "resistance" and abs(z["hi"] - 101.5) < 1e-9 for z in zones)


def test_evaluate_fires_long_on_confirmed_rejection():
    df1h = _flat_1h()
    # last CLOSED candle (iloc[-2]) is the rejection; iloc[-1] is forming
    fivem = _5m([(100.6, 100.7, 100.5, 100.6),
                 (100.5, 100.6, 98.3, 98.6),     # pierce 98.5, close back above
                 (98.6, 98.7, 98.5, 98.65)])     # forming candle — ignored
    r = sb.evaluate(fivem, None, df1h)
    assert r["signal"] == "buy"
    assert r["sl_price"] < 98.5 < r["tp_price"]
    assert r["strength"] == 0.82


def test_evaluate_holds_without_rejection():
    df1h = _flat_1h()
    fivem = _5m([(100.6, 100.7, 100.5, 100.6),
                 (100.5, 100.6, 100.4, 100.5),
                 (100.5, 100.6, 100.4, 100.45)])
    assert sb.evaluate(fivem, None, df1h)["signal"] == "hold"


def test_evaluate_holds_on_trending_adx(monkeypatch):
    df1h = _flat_1h()
    monkeypatch.setattr(sb, "adx", lambda df, n=14: pd.Series([35.0] * len(df)))
    fivem = _5m([(100.5, 100.6, 98.3, 98.6), (98.6, 98.7, 98.5, 98.65),
                 (98.6, 98.7, 98.5, 98.6)])
    r = sb.evaluate(fivem, None, df1h)
    assert r["signal"] == "hold" and "ADX" in r["reason"]


def test_evaluate_holds_without_htf():
    fivem = _5m([(1, 1, 1, 1)] * 3)
    assert sb.evaluate(fivem, None, None)["signal"] == "hold"
```

- [ ] **Step 2: Run, verify FAIL** — `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_sr_bounce.py -v` → ModuleNotFoundError.
- [ ] **Step 3: Implement `sr_bounce.py`** — copy the eight pure functions byte-for-byte from `scripts/research/sr-bounce-scan/sr_levels.py` and `sr_signal.py`, then add `evaluate()` per the interface above (completed-candle `df.iloc[-2]`, dict return).
- [ ] **Step 4: Run, verify PASS**, then full suite: `python3 -m pytest tests/ -q` — 597 prior must stay green.
- [ ] **Step 5: Commit** — `git add sr_bounce.py tests/test_sr_bounce.py && git commit -m "feat(sr-bounce): pure signal module for paper forward test (owner order; scan prior on record)"`

---

### Task 2: TradeSignal extension + STRATEGIES registration

**Files:**
- Modify: `strategies.py` (TradeSignal dataclass ~line 18; STRATEGIES dict ~line 1032; new wrapper fn near vwap_sma_cross)
- Test: extend `tests/test_sr_bounce.py`

**Interfaces:**
- `TradeSignal` gains `sl_price: float = None` and `tp_price: float = None` (AFTER existing fields — positional callers unaffected).
- New `def sr_bounce(df, orderbook=None, htf_df=None) -> TradeSignal:` wrapper in strategies.py: `import sr_bounce as _sr_bounce_mod` at module top; wrapper calls `_sr_bounce_mod.evaluate(df, orderbook, htf_df)` and maps dict → `TradeSignal(Signal.BUY/SELL/HOLD, reason, strength, sl_price=..., tp_price=...)`.
- `STRATEGIES["sr_bounce"] = sr_bounce`.

- [ ] **Step 1: Failing tests** (append to tests/test_sr_bounce.py):

```python
def test_tradesignal_backward_compatible():
    from strategies import TradeSignal, Signal
    s = TradeSignal(Signal.HOLD, "x", 0.0)          # old positional form
    assert s.sl_price is None and s.tp_price is None


def test_strategies_registers_sr_bounce():
    from strategies import STRATEGIES, Signal
    fn = STRATEGIES["sr_bounce"]
    df1h = _flat_1h()
    fivem = _5m([(100.6, 100.7, 100.5, 100.6),
                 (100.5, 100.6, 98.3, 98.6),
                 (98.6, 98.7, 98.5, 98.65)])
    sig = fn(fivem, None, htf_df=df1h)
    assert sig.signal == Signal.BUY
    assert sig.sl_price is not None and sig.tp_price is not None
```

- [ ] **Step 2: FAIL** → **Step 3: implement** → **Step 4: PASS + full suite green (597 + new).**
- [ ] **Step 5: Commit** — `git add strategies.py tests/test_sr_bounce.py && git commit -m "feat(sr-bounce): TradeSignal sl/tp_price fields + STRATEGIES registration"`

---

### Task 3: Slot registration + structural-exit plumbing (bot.py)

**Files:**
- Modify: `bot.py` — slots list (after VWAP_CROSS block ~line 760); paper entry call site (~line 3060) and live call site (~line 3167)
- Create: `tests/test_sr_bounce_slot.py`

**Interfaces:**
- New slot: `StrategySlot(slot_id="SR_BOUNCE", strategy_name="sr_bounce", timeframe="5m", max_positions=1, capital_pct=0.0, trade_amount_usdt=5.0, paper_mode=True, entry_patience_s=45.0)` with a comment block citing the owner order + scan prior.
- Both slot entry call sites gain, immediately before their `open_position` call:

```python
_sl_pct, _tp_pct = slot.sl_percent, slot.tp_percent
_sig_sl = getattr(signal, "sl_price", None)
_sig_tp = getattr(signal, "tp_price", None)
if _sig_sl is not None and _sig_tp is not None and price > 0:
    # Structural per-trade exits (SR_BOUNCE 2026-07-28): strategy-supplied
    # absolute levels convert to pct-of-entry; open_position's None-default
    # keeps every other slot on its existing geometry.
    _sl_pct = abs(price - _sig_sl) / price * 100.0
    _tp_pct = abs(_sig_tp - price) / price * 100.0
```
then pass `sl_pct=_sl_pct, tp_pct=_tp_pct` instead of the current direct slot constants. (Use each call site's actual entry-price variable — `price` at the paper site, `fill_price` at the live site; read both call sites on disk before editing — they have shifted since the line numbers above.)

- [ ] **Step 1: Failing tests:**

```python
# tests/test_sr_bounce_slot.py
import sys
sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")
import inspect


def test_sr_bounce_slot_registered():
    import bot as botmod
    src = inspect.getsource(botmod.Phmex2Bot.__init__)
    assert 'slot_id="SR_BOUNCE"' in src
    assert '"sr_bounce"' in src        # strategy_name is a real STRATEGIES key


def test_sr_bounce_slot_is_paper_5_dollars():
    import bot as botmod
    src = inspect.getsource(botmod.Phmex2Bot.__init__)
    block = src[src.index('slot_id="SR_BOUNCE"'):src.index('slot_id="SR_BOUNCE"') + 900]
    assert "trade_amount_usdt=5.0" in block
    assert "paper_mode=True" in block
    assert "max_positions=1" in block


def test_slot_entry_paths_honor_structural_levels():
    import bot as botmod
    src = inspect.getsource(botmod.Phmex2Bot._evaluate_slots)
    assert src.count('getattr(signal, "sl_price", None)') >= 2  # paper + live sites
```

- [ ] **Step 2: FAIL** → **Step 3: implement (read both call sites first; keep edits minimal)** → **Step 4: PASS + FULL suite green.**
- [ ] **Step 5: Commit** — `git add bot.py tests/test_sr_bounce_slot.py && git commit -m "feat(sr-bounce): paper slot + structural per-trade exit plumbing"`

---

### Task 4: Adjudicator registration

**Files:**
- Modify: `scripts/lab_adjudicator/adjudicate.py` (EXPERIMENTS, new grader, results list, digest line)
- Modify: `tests/test_lab_adjudicator.py` (digest count 7→8 + grader tests)

**Interfaces:**
- `EXPERIMENTS["sr_bounce"] = {"deployed_ts": <_pt_ts of ship day>, "verdict_n": 50, "scan_prior_per_trade": -0.0705}` with a comment citing the scan report and the owner-order context.
- `grade_sr_bounce(slot_state, cfg)` (shape of grade_vwap_cross): all paper trades count; at `n >= 50`: KILL if fee-adjusted net ≤ 0 else PASS-eligible → status "PASS-ELIGIBLE" with note "owner decision required" (promotion is never automatic); before: WATCH `f"paper accruing (n={n}/50, net ${net:+.2f}; scan prior -$0.07/t)"`. Fee-adjust each trade like the dashboard: `net_pnl − fees_usdt` when `mode != "live"`.
- Digest: append result + `_line_sr_bounce` (follow `_line_vwap_cross` shape); state file `trading_state_SR_BOUNCE.json` via `load_json`.
- Update `test_htf_l2_wired_into_digest`: `len(results) == 8`, `results[7]["experiment"] == "sr_bounce"`, `"[sr_bounce]" in digest`.

- [ ] **Step 1: failing grader tests** (WATCH under n=50 on synthetic state; KILL at n=50 net<0; PASS-ELIGIBLE at n=50 net>0; fee-adjustment actually subtracts fees_usdt) → **Step 2: FAIL** → **Step 3: implement** → **Step 4: PASS + dry-run `python3 -m scripts.lab_adjudicator.adjudicate` shows `[sr_bounce] WATCH — paper accruing (n=0/50 ...)`** → **Step 5: Commit.**

---

### Task 5: Dashboard card + final checks

**Files:**
- Modify: `web_dashboard.py` — remove the SR_BOUNCE static-tombstone branch in the render loop; update its `_SIGNAL_BOXES` entry to a live-capable card whose description KEEPS the scan verdict: title `"SR_BOUNCE &mdash; PAPER FORWARD TEST (SCAN SAID NO)"`, desc = design summary + "Backtest kill-gate said DO-NOT-BUILD (−$0.07/t holdout, worse than coin flip — reports/2026-07-28-sr-bounce-scan.md). Owner-ordered paper forward test anyway: measuring the one thing the scan couldn't — real fill selection. KILL at n=50 net ≤ $0 (adjudicator-graded)."
- Modify: `tests/test_dashboard_v2.py` — add `assert "SR_BOUNCE" in boxes` + title/desc assertions replacing any tombstone-era expectations.

- [ ] **Step 1: adjust tests** → **Step 2: FAIL** → **Step 3: implement (generic `_build_signal_card` now handles it — reads `trading_state_SR_BOUNCE.json`, shows PAPER badge + size row appears only if ever live)** → **Step 4: full suite green; restart the dashboard process and curl-verify the card renders with PAPER status** → **Step 5: Commit.**

---

### Task 6: Pre-restart audit gate (controller-run, not a subagent task)

- [ ] Full suite green; `python3 -m py_compile` on bot.py, strategies.py, sr_bounce.py, web_dashboard.py, adjudicate.py.
- [ ] Pre-restart audit per house skill (diff review, param crosscheck vs lessons.md, review agent) on the cumulative slot-build diff.
- [ ] Present checklist to Jonas; restart ONLY on his explicit go. After restart: verify `[SLOT] SR_BOUNCE (PAPER/ACTIVE)` on the slot board, `[sr_bounce]` in an adjudicator dry run, and the dashboard card live.

## Self-Review (done at write time)

- Spec coverage: §2 signal (Task 1), §4 slot+registry+reporting (Tasks 3-5), TDD (§5) throughout; §4's "only if scan survives" explicitly overridden by owner order — recorded in Goal and in every user-facing surface (module docstring, dashboard card, adjudicator note).
- Placeholders: none; all steps carry runnable content or exact edit specs with read-before-edit guards where line numbers may drift.
- Type consistency: `evaluate()` dict shape fixed in Task 1 and consumed identically in Task 2; `sl_price/tp_price` names consistent across Tasks 2-4; slot id "SR_BOUNCE" and state file `trading_state_SR_BOUNCE.json` consistent across Tasks 3-5.
