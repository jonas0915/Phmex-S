"""Donchian ensemble (BTC + ETH) — Concretum 'Catching Crypto Trends' replica.

Pre-registered spec: docs/superpowers/specs/2026-07-16-donchian-ensemble-slot-design.md
(FROZEN — no tuning without a new replay). Golden reference: the validated
replay implementation (scratchpad donchian_ensemble.py, receipts in
reports/2026-07-16-wake-report.md §0.4). run_history/advance_day below MUST
reproduce that reference's daily executed-weight series exactly — verified to
1e-9 on BTC 2024-01-01→2025-06-01 at build time. Fix THIS file, never the
reference, if they ever diverge.

The rule, per coin, on COMPLETE daily closes (UTC):
- 9 Donchian sub-models, lookbacks {5,10,20,30,60,90,150,250,360}, closes only.
- Sub-model entry: today's close == the N-day close-high (>= the window max).
- Sub-model exit: close <= trailing stop; stop initialized at the Donchian
  midline (mean of N-day close-high and close-low) on entry, then ratcheted
  daily to max(prev stop, midline) — NEVER down. The stop is close-only,
  evaluated at the daily eval — no resting orders, no intraday checks.
- Combo weight w_target = mean(9 sub-model positions ∈ {0,1}) × vol_scalar;
  vol_scalar = min(0.25 / σ, 2.0), σ = √365-annualized std (ddof=1) of the
  last 90 daily simple returns (the reference seeds return[0]=0.0, so the
  very first vol window of a series includes one artificial zero — replicated
  here for exactness; irrelevant at production history depth).
- Executed weight w: take w_target immediately on any sub-model flip or from
  flat; on vol-only drift only when |w_target − w| > 0.20·|w| (relative 20%
  threshold); else hold. Long/flat only, no leverage in paper (notional =
  BASE_NOTIONAL_USDT × w).

This module holds the PURE parts (signal math, state advance, sidecar IO) so
they are unit-testable without the bot — same split as tsm_slot.py.
Orchestration (paper fills, position sizing) lives in bot.py:_evaluate_donchian.
Paper-book expression of a resize is close-and-reopen at the new notional (the
simplest faithful expression of a weight change; the realized PnL slice at each
rebalance is a paper-book artifact, not a strategy PnL event — the sidecar w
series is the fidelity benchmark, per the spec's kill criteria).

The sidecar files (donchian_slot_state.json, donchian_signal_{BTC,ETH}.json)
are deliberately NOT named trading_state_* — web_dashboard.read_all_slot_states()
globs that prefix and would render them as phantom slots (same reasoning as
eth_tsm_28_signal.json).
"""
import json
import os
import datetime as _dt

import numpy as np

# ── frozen spec constants (pre-registered — no mid-test edits) ─────────────
SLOT_IDS = {
    "BTC/USDT:USDT": "DONCHIAN_BTC",
    "ETH/USDT:USDT": "DONCHIAN_ETH",
}
SYMBOLS = list(SLOT_IDS)             # evaluation order: BTC, ETH
BASE_NOTIONAL_USDT = 100.0           # paper notional at w=1.0 (spec: $100/coin base)
LOOKBACKS = (5, 10, 20, 30, 60, 90, 150, 250, 360)  # frozen 9-model ensemble
VOL_WINDOW = 90                      # daily returns in the vol estimate
VOL_TARGET = 0.25                    # 25% annualized target
VOL_CAP = 2.0                        # vol_scalar ceiling
REBALANCE_THRESHOLD = 0.20           # relative 20% on vol-only drift
ANNUALIZATION = 365.0                # crypto trades every day
OHLCV_LIMIT = 500                    # Phemex whitelist {5,10,50,100,500,1000}
MIN_BARS = LOOKBACKS[-1] + VOL_WINDOW  # 450 complete closes = fully warm ensemble

_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_DIR, "donchian_slot_state.json")
SIGNAL_FILES = {sym: os.path.join(_DIR, f"donchian_signal_{sym.split('/')[0]}.json")
                for sym in SYMBOLS}
_MAX_DAY_RECORDS = 800  # ~2.2y of daily records; bounded file size


def utc_date_str(now_utc=None) -> str:
    return (now_utc or _dt.datetime.now(_dt.timezone.utc)).date().isoformat()


def complete_daily_bars(df, now_utc=None) -> tuple:
    """(ISO-date list, close list) of COMPLETE daily candles only. Phemex
    includes the in-progress UTC day as the last row of a 1d fetch — evaluating
    on it would leak the partial candle into the signal, so any row dated today
    (UTC) is dropped (same rule as tsm_slot.complete_daily_closes).
    df: DataFrame indexed by naive-UTC timestamps (exchange.get_ohlcv shape)."""
    if df is None or len(df) == 0:
        return [], []
    today = (now_utc or _dt.datetime.now(_dt.timezone.utc)).date()
    dates, closes = [], []
    for ts, close in zip(df.index, df["close"]):
        if ts.date() < today:
            dates.append(ts.date().isoformat())
            closes.append(float(close))
    return dates, closes


# ── pure signal math (exact reference parity — see module docstring) ───────

def default_coin_state() -> dict:
    return {
        "submodel_pos": [0] * len(LOOKBACKS),      # end-of-day position per model
        "submodel_stops": [None] * len(LOOKBACKS),  # ratcheting midline stop (None = flat)
        "w": 0.0,                                   # executed combo weight
        "last_close_date": None,                    # last COMPLETE close folded into state
        "last_eval_utc_date": None,                 # once-per-UTC-day eval guard
        "stop_fired_pending": False,                # a folded close fired a sub-model stop
                                                    # and the book hasn't synced yet (keeps
                                                    # the donchian_stop exit tag across a
                                                    # failed-cycle retry, when advance_state
                                                    # returns no new days)
    }


def _vol_scalar(closes: list):
    """min(VOL_TARGET/σ, VOL_CAP) on the last VOL_WINDOW daily simple returns,
    or None when there is no valid estimate (short history / zero σ) — the
    reference maps that to a flat combo weight (fail CLOSED)."""
    m = len(closes)
    if m < VOL_WINDOW:
        return None
    if m == VOL_WINDOW:
        # Reference seeds return[0]=0.0; the first full window carries it.
        tail = np.asarray(closes, dtype=float)
        rets = np.empty(VOL_WINDOW)
        rets[0] = 0.0
        rets[1:] = tail[1:] / tail[:-1] - 1.0
    else:
        tail = np.asarray(closes[-(VOL_WINDOW + 1):], dtype=float)
        rets = tail[1:] / tail[:-1] - 1.0
    sigma = float(np.std(rets, ddof=1)) * np.sqrt(ANNUALIZATION)
    if not sigma > 0:
        return None
    # float() cast is value-preserving (same IEEE double) — keeps the sidecar
    # JSON-serializable without touching reference parity.
    return float(min(VOL_TARGET / sigma, VOL_CAP))


def advance_day(pos: list, stops: list, w_prev: float, closes: list) -> tuple:
    """Advance the ensemble one day. `closes` is the FULL complete-close prefix
    (oldest → newest, today's completed close last); pos/stops/w_prev are
    yesterday's end-of-day state. Returns (new_pos, new_stops, w_new, info).
    Pure — no I/O, no clocks."""
    c = closes
    new_pos, new_stops = [], []
    sig_event = False   # any sub-model flipped today → rebalance immediately
    stop_fired = False  # any sub-model exited via its ratcheting stop today
    for j, lb in enumerate(LOOKBACKS):
        p, stop = pos[j], stops[j]
        if len(c) >= lb:  # reference evaluates a model only once its window is full
            window = c[-lb:]
            up = max(window)
            dn = min(window)
            mid = 0.5 * (up + dn)
            if p == 0:
                if c[-1] >= up:  # close IS the N-day close-high (>= handles float ties)
                    p, stop = 1, mid
            else:
                if c[-1] <= stop:
                    p, stop = 0, None
                    stop_fired = True
                else:
                    stop = max(stop, mid)  # ratchet: never down
        if p != pos[j]:
            sig_event = True
        new_pos.append(p)
        new_stops.append(stop)

    size = _vol_scalar(c)
    if size is None:
        w_target = 0.0
    else:
        # Exact reference arithmetic: per-model weight vector, then np.mean.
        w_model = np.where(np.asarray(new_pos, dtype=float) > 0, size, 0.0)
        w_target = float(np.mean(w_model))

    # Executed weight: rebalance on any sub-model flip or from flat; vol-only
    # drift rebalances only past the relative 20% threshold.
    if sig_event or w_prev == 0.0:
        w_new = w_target
    elif abs(w_target - w_prev) > REBALANCE_THRESHOLD * abs(w_prev):
        w_new = w_target
    else:
        w_new = w_prev

    info = {
        "w": w_new,
        "w_target": w_target,
        "submodel_pos": list(new_pos),
        "n_long": int(sum(new_pos)),
        "vol_scalar": size,
        "close": float(c[-1]),
        "sig_event": sig_event,
        "stop_fired": stop_fired,
    }
    return new_pos, new_stops, w_new, info


def run_history(closes: list) -> tuple:
    """From-scratch fold of advance_day over every prefix of `closes` (starts
    flat, exactly like the reference replay starts at its data start). Returns
    (pos, stops, w, infos) — infos[i]['w'] is the day-i executed weight, the
    series the golden check compares against the reference. Also the bootstrap
    path for a fresh/reseeded production state."""
    c = [float(x) for x in closes]
    pos = [0] * len(LOOKBACKS)
    stops = [None] * len(LOOKBACKS)
    w = 0.0
    infos = []
    for t in range(len(c)):
        pos, stops, w, info = advance_day(pos, stops, w, c[:t + 1])
        infos.append(info)
    return pos, stops, w, infos


def advance_state(st: dict, dates: list, closes: list) -> list:
    """Fold all complete closes strictly newer than st['last_close_date'] into
    the persisted per-coin state (mutated in place). Bootstraps from scratch
    over the whole window when the state is fresh, or reseeds when the gap
    since the last processed close can't be bridged inside the fetched window
    (downtime deeper than the longest lookback — the frozen sub-model state
    would otherwise skip its stop ratchet across the gap). Idempotent: closes
    already folded in are never re-processed. Returns the per-day info dicts
    for newly processed days (bootstrap returns only the final day, flagged)."""
    if not closes:
        return []
    last = st.get("last_close_date")
    if last is not None and last >= dates[-1]:
        return []  # nothing new (retry cycle after a downstream failure)

    reseed = None
    if last is None:
        reseed = f"bootstrap over {len(closes)} bars"
    elif last < dates[0]:
        reseed = (f"state gap unbridgeable (last close {last} predates window "
                  f"start {dates[0]}) — reseeded over {len(closes)} bars")
    else:
        start = next(i for i, d in enumerate(dates) if d > last)
        if start < LOOKBACKS[-1]:
            reseed = (f"catch-up too deep ({len(dates) - start} missed days, "
                      f"prefix {start} < {LOOKBACKS[-1]}) — reseeded over "
                      f"{len(closes)} bars")

    if reseed is not None:
        pos, stops, w, infos = run_history(closes)
        st["submodel_pos"], st["submodel_stops"], st["w"] = pos, stops, w
        st["last_close_date"] = dates[-1]
        final = dict(infos[-1])
        final["date"] = dates[-1]
        final["note"] = reseed
        return [final]

    pos, stops, w = st["submodel_pos"], st["submodel_stops"], st["w"]
    out = []
    for i in range(start, len(closes)):
        pos, stops, w, info = advance_day(pos, stops, w, closes[:i + 1])
        info["date"] = dates[i]
        out.append(info)
    st["submodel_pos"], st["submodel_stops"], st["w"] = pos, stops, w
    st["last_close_date"] = dates[-1]
    return out


# ── sidecar state IO (atomic, never breaks the trading cycle) ──────────────

def load_state(path: str = None) -> dict:
    """{symbol: coin_state} map; missing/corrupt file or coins → defaults."""
    path = path or STATE_FILE  # resolved at call time so tests can repoint STATE_FILE
    data = {}
    try:
        with open(path) as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data = raw
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    state = {}
    for sym in SYMBOLS:
        base = default_coin_state()
        coin = data.get(sym)
        if isinstance(coin, dict):
            base.update(coin)
        state[sym] = base
    return state


def save_state(state: dict, path: str = None) -> None:
    """Atomic write (tmp + os.replace) — same pattern as tsm_slot/mode sidecars."""
    path = path or STATE_FILE  # resolved at call time so tests can repoint STATE_FILE
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except OSError:
        pass  # never let sidecar IO break the trading cycle


def append_signal_days(symbol: str, records: list, path: str = None) -> None:
    """Append pure-rule daily records ({date, w, submodel_pos, ...}) to the
    per-coin replica series — the fidelity benchmark the spec's kill criteria
    grade bot behavior against (like eth_tsm_28_signal.json's day records).
    Idempotent per date: a re-eval replaces the same day's record."""
    path = path or SIGNAL_FILES.get(symbol)
    if path is None or not records:
        return
    try:
        days = []
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("days"), list):
                days = data["days"]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        for record in records:
            if days and days[-1].get("date") == record.get("date"):
                days[-1] = record
            else:
                days.append(record)
        if len(days) > _MAX_DAY_RECORDS:
            del days[: len(days) - _MAX_DAY_RECORDS]
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"days": days}, f)
        os.replace(tmp, path)
    except OSError:
        pass  # never let sidecar IO break the trading cycle
