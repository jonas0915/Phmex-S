"""ETH-TSM-28 — slow-horizon, long-only time-series momentum (Han/Kang/Ryu 28/5).

Pre-registered spec: docs/overnight-2026-07-05/r5_slow_horizon_research.md §7.
Build doc:          docs/overnight-2026-07-05/r6_eth_tsm_build.md.

This module holds the PURE parts (signal math, date math, sidecar state IO) so
they are unit-testable without the bot. Orchestration (orders, leverage,
ownership vs the main bot) lives in bot.py:_evaluate_eth_tsm.

TERCILE INTERPRETATION (declared, per the research doc's rule "buys the market
when its look-back period return falls within the top third of the historical
returns", expanding window):
  signal ON  <=>  the CURRENT 28-day return >= the 66.667th percentile
  (numpy linear interpolation) of the history of PRIOR 28-day returns —
  the current observation is EXCLUDED from the history it is ranked against
  (at time t the paper's trader only knows past realizations). Boundary ties
  count as top-tercile (>=): "falls within the top third" is inclusive.
Window: expanding up to the API cap. Phemex whitelists OHLCV limits
{5,10,50,100,500,1000} (memory/lessons.md); we fetch limit=500 daily candles
=> up to 471 historical 28-day returns (~1.3y). The spec asks for >=2y of
history — deviation declared in the build doc; TSM_OHLCV_LIMIT=1000 is the
one-line extension when wanted.

The sidecar file eth_tsm_28_signal.json is deliberately NOT named
trading_state_* — web_dashboard.read_all_slot_states() globs that prefix and
would render the sidecar as a phantom slot.
"""
import json
import os
import datetime as _dt

import numpy as np

# ── frozen spec constants (pre-registered — no mid-test edits) ─────────────
TSM_SLOT_ID = "ETH_TSM_28"
TSM_SYMBOL = "ETH/USDT:USDT"
TSM_BTC_SYMBOL = "BTC/USDT:USDT"   # parallel-logged signal, never traded (spec §7.1)
TSM_AMOUNT_ETH = 0.01              # ONE min-step, fixed — no Kelly, no pyramiding
TSM_LEVERAGE = 3                   # isolated 3x (positive leverageRr = isolated on Phemex USDT perps)
TSM_STOP_PCT = 8.0                 # disaster stop: resting exchange SL at −8% from entry
TSM_LOOKBACK_DAYS = 28
TSM_MIN_HOLD_DAYS = 5
TSM_TERCILE_PCTL = 100.0 * 2.0 / 3.0
TSM_OHLCV_LIMIT = 500              # Phemex whitelist {5,10,50,100,500,1000}
TSM_MIN_HISTORY = 90               # min prior 28d-returns before terciles are meaningful
TSM_TAKER_FALLBACK_S = 1800.0      # maker attempts for 30 min, then take (spec §7.2)

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "eth_tsm_28_signal.json")
_MAX_DAY_RECORDS = 800  # ~2.2y of daily records; bounded file size


def complete_daily_closes(df, now_utc=None) -> list:
    """Closes of COMPLETE daily candles only. Phemex includes the in-progress
    UTC day as the last row of a 1d fetch — evaluating on it would leak the
    partial candle into the signal, so any row dated today (UTC) is dropped.
    df: DataFrame indexed by naive-UTC timestamps (exchange.get_ohlcv shape)."""
    if df is None or len(df) == 0:
        return []
    today = (now_utc or _dt.datetime.now(_dt.timezone.utc)).date()
    closes = []
    for ts, close in zip(df.index, df["close"]):
        if ts.date() < today:
            closes.append(float(close))
    return closes


def lookback_returns(closes: list, lookback: int = TSM_LOOKBACK_DAYS) -> list:
    """r[i] = close[i]/close[i-28] − 1 for every day with a full lookback."""
    return [closes[i] / closes[i - lookback] - 1.0
            for i in range(lookback, len(closes))]


def compute_signal(closes: list, lookback: int = TSM_LOOKBACK_DAYS,
                   pctl: float = TSM_TERCILE_PCTL,
                   min_history: int = TSM_MIN_HISTORY):
    """Evaluate the tercile rule on complete daily closes.

    Returns {"signal_on", "ret_28d", "threshold", "n_history", "close"} or
    None when there is not enough history (fail CLOSED: no signal, no trade).
    """
    rets = lookback_returns(closes, lookback)
    if len(rets) < min_history + 1:
        return None
    current = rets[-1]
    history = rets[:-1]  # current obs excluded — ranked against the PAST only
    threshold = float(np.percentile(history, pctl))
    return {
        "signal_on": bool(current >= threshold),  # boundary tie => top tercile
        "ret_28d": float(current),
        "threshold": threshold,
        "n_history": len(history),
        "close": float(closes[-1]),
    }


def utc_date_str(now_utc=None) -> str:
    return (now_utc or _dt.datetime.now(_dt.timezone.utc)).date().isoformat()


def held_days(entry_date: str, today: str) -> int:
    """Whole UTC-calendar days held. Entry day counts as day 0, so the
    min-hold gate `held_days >= 5` first opens on the 5th daily eval after
    entry — matching the paper's 5-day holding period."""
    return (_dt.date.fromisoformat(today) - _dt.date.fromisoformat(entry_date)).days


def min_hold_met(entry_date, today: str) -> bool:
    if not entry_date:
        return True  # no recorded entry date — never trap a position open forever
    return held_days(entry_date, today) >= TSM_MIN_HOLD_DAYS


def advance_replica(state: dict, signal_on, today: str) -> dict:
    """Paper-replica of the PURE rule (no skip-days, no fills, no disaster
    stop): long while top-tercile, min-hold 5d, exit to flat when the signal
    leaves the tercile. This is the tracking-error benchmark the adjudicator
    compares live behavior against (spec believability bar (b))."""
    rep = state.setdefault("replica", {"position": False, "entry_date": None})
    if signal_on is None:
        return rep  # no data today — replica holds its state
    if rep.get("position"):
        if min_hold_met(rep.get("entry_date"), today) and not signal_on:
            rep["position"] = False
            rep["entry_date"] = None
    elif signal_on:
        rep["position"] = True
        rep["entry_date"] = today
    return rep


def default_state() -> dict:
    return {
        "last_eval_date": None,
        "signal_on": None, "ret_28d": None, "threshold": None,
        "entry_pending_date": None, "entry_first_attempt_ts": None,
        "exit_pending": False,
        "entry_date": None,          # actual slot-book entry date (min-hold anchor)
        "leverage_3x_set": False,    # ETH flipped to 3x isolated; main bot stays off ETH until restored
        "replica": {"position": False, "entry_date": None},
        "days": [],
    }


def load_state(path: str = None) -> dict:
    path = path or STATE_FILE  # resolved at call time so tests can repoint STATE_FILE
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            base = default_state()
            base.update(data)
            return base
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return default_state()


def save_state(state: dict, path: str = None) -> None:
    """Atomic write (tmp + replace) — same pattern as the mode sidecars."""
    path = path or STATE_FILE  # resolved at call time so tests can repoint STATE_FILE
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except OSError:
        pass  # never let sidecar IO break the trading cycle


def append_day(state: dict, record: dict) -> None:
    days = state.setdefault("days", [])
    # idempotent per date: a re-eval (e.g. retry after a failed fetch) replaces
    # the same day's record instead of duplicating it
    if days and days[-1].get("date") == record.get("date"):
        days[-1] = record
    else:
        days.append(record)
    if len(days) > _MAX_DAY_RECORDS:
        del days[: len(days) - _MAX_DAY_RECORDS]
