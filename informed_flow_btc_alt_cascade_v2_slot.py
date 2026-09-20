"""informed_flow_btc_alt_cascade_v2 — pre-registered PAPER slot (2026-09-20 build).

Short-only laggard fade: when BTC's trailing-3h return exceeds 150 bps and an
alt has captured less than half of that move over the same window, short the
alt at the next price; TP 250 bps / SL 150 bps of entry, time exit after
MAX_HOLD_BARS closed bars. Frozen spec (sha256
2d51f95509d209b6ebfb42cee3c5ea67b561ac0490dab46ed1d69cac019f6c41):
research/swarm/runs/2026-09-19-1451/specs/informed_flow_btc_alt_cascade_v2.frozen.json
Frozen signal (sha256 c8cf4ee13bd1d8e096966389e426f3294d007ecd32aa22f25394da881efd6d8d):
research/swarm/runs/2026-09-19-1451/screens/informed_flow_btc_alt_cascade_v2/signal.py
Pre-registration (verdict line, anti-fishing clause, holdout record — binding):
docs/superpowers/specs/2026-09-20-informed_flow_btc_alt_cascade_v2-prereg.md

Nothing here is tunable during the paper era: tp/sl/max_hold/universe/
timeframe/signal are frozen; a change is a new thesis through the desk.

This module holds the PURE parts (signal transcription, exit rule, sidecar
IO) so they are unit-testable without the bot — same split as
donchian_slot.py / tsm_slot.py. Orchestration (the once-per-cycle reference
fetch, paper fills, closes) lives in
bot.py:_evaluate_informed_flow_btc_alt_cascade_v2. No bot imports, no
network, no research.swarm.lib.load_data import.

Reference feed (owner decision 2026-09-20 1:16 PM PT, recorded in the prereg
doc's "Owner decision (reference feed)" section): the frozen signal's
`ld.load_reference("BTC", "1h", dataset="long_1h")` is transcribed as a live
`exchange.get_ohlcv(REF_SYMBOL, REF_TIMEFRAME, limit=OHLCV_LIMIT)` fetched
ONCE per cycle by the bot, reduced to CLOSED bars with the same
complete_bars() as the alt, and handed to signals(df, ref_df) as an explicit
second argument. signals() is the frozen body verbatim apart from that one
line: same K / THRESH_BPS / LAG_RATIO, same intersection, same
reindex/fillna/astype.

Exit rule: transcribed from research/swarm/lib/screen.py simulate() — each
closed bar after entry checks SL then TP against that bar's low/high (SL
wins ties), the time exit fires at the MAX_HOLD_BARS-th bar after the entry
bar at its close. Closed bars only: the forming bar is never read.

The sidecar files (informed_flow_btc_alt_cascade_v2_slot_state.json,
informed_flow_btc_alt_cascade_v2_signal_<BASE>.json) are deliberately NOT
named trading_state_* — web_dashboard.read_all_slot_states() globs that
prefix and would render them as phantom slots (same reasoning as
donchian_slot.py).
"""
import datetime as _dt
import json
import os

import pandas as pd

# ── frozen spec constants (pre-registered — no mid-test edits) ─────────────
# All from research/swarm/runs/2026-09-19-1451/specs/
# informed_flow_btc_alt_cascade_v2.frozen.json (sha256
# 2d51f95509d209b6ebfb42cee3c5ea67b561ac0490dab46ed1d69cac019f6c41), "spec".
SLOT_ID = "informed_flow_btc_alt_cascade_v2"
UNIVERSE = ["DOGE", "ADA", "XRP", "LTC", "LINK", "UNI", "NEAR", "SUI", "ONDO",
            "AAVE", "TAO", "XLM", "1000PEPE", "1000SHIB", "GIGGLE", "BNB"]  # spec.universe (16)
SYMBOLS = [f"{base}/USDT:USDT" for base in UNIVERSE]  # exchange form, evaluation order
TIMEFRAME = "1h"            # spec.timeframe
TP_BPS = 250                # spec.tp_bps
SL_BPS = 150                # spec.sl_bps
MAX_HOLD_BARS = 7           # spec.max_hold_bars
BAR = pd.Timedelta(TIMEFRAME)

# Reference series — the frozen signal's
#     btc = ld.load_reference("BTC", "1h", dataset="long_1h")
# transcribed to exchange form exactly as the universe symbols are
# ("BTC" -> "BTC/USDT:USDT", cf. tsm_slot.TSM_BTC_SYMBOL). The bot fetches it
# once per cycle via exchange.get_ohlcv(REF_SYMBOL, REF_TIMEFRAME,
# limit=OHLCV_LIMIT) — owner-authorised (see module docstring).
REF_SYMBOL = "BTC/USDT:USDT"
REF_TIMEFRAME = "1h"

# Signal constants — copied from the frozen signal.py (same names, same values).
K = 3               # trailing lookback, bars (hours on the 1h grid)
THRESH_BPS = 150.0  # BTC trailing K-bar move required to call it a "sharp pump"
LAG_RATIO = 0.5     # alt must have captured less than half of BTC's same-direction move

# Phemex fetch_ohlcv whitelist {5,10,50,100,500,1000}. The signal's longest
# lookback is K=3 closed bars (+ the bar itself + the forming bar dropped =
# 5); 50 leaves room for reference/alt index gaps in the intersection.
OHLCV_LIMIT = 50

# Paper notional: research.swarm.lib.fee_math.position_notional() =
# capital_usd 200.0 × risk_frac 0.10 × leverage 10 = 200.0 (printed 200.0 at
# build time; CONSTRAINTS.md "Design basis $200"). 1x paper convention: margin
# is recorded AS the notional, so USD PnL = notional × price move.
NOTIONAL_USDT = 200.0

_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_DIR, f"{SLOT_ID}_slot_state.json")
SIGNAL_FILES = {sym: os.path.join(_DIR, f"{SLOT_ID}_signal_{sym.split('/')[0]}.json")
                for sym in SYMBOLS}
_MAX_BAR_RECORDS = 2000  # ~83 days of hourly records per symbol; bounded file size


def utc_date_str(now_utc=None) -> str:
    return (now_utc or _dt.datetime.now(_dt.timezone.utc)).date().isoformat()


def ts_key(ts) -> str:
    """Stable string key for a bar's open timestamp (naive-UTC or tz-aware)."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def complete_bars(df, now_utc=None) -> pd.DataFrame:
    """`df` without the forming bar: a bar is closed when its open time + BAR
    <= now. Works for both index conventions — naive-UTC (exchange.get_ohlcv
    shape) and tz-aware UTC (research cache) — without converting the frame.
    None / empty -> empty frame."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    now = pd.Timestamp(now_utc or _dt.datetime.now(_dt.timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    if df.index.tz is None:
        now = now.tz_convert("UTC").tz_localize(None)
    else:
        now = now.tz_convert(df.index.tz)
    return df[(df.index + BAR) <= now]


# ── frozen signal, transcribed (ONE change: the reference is a parameter) ──

def signals(df: pd.DataFrame, ref_df: pd.DataFrame) -> pd.Series:
    """Verbatim body of the frozen signals(df); the only change is that
    `btc = ld.load_reference("BTC", "1h", dataset="long_1h")` became the
    assignment from ref_df below. Both frames must share one index
    convention (the bot passes two exchange frames, the parity test two
    research-cache frames); nothing is converted here."""
    btc = ref_df  # frozen: btc = ld.load_reference("BTC", "1h", dataset="long_1h")
    idx = df.index.intersection(btc.index)
    btc_ret = (btc["close"].pct_change(K) * 1e4).reindex(idx)
    alt_ret = (df["close"].pct_change(K) * 1e4).reindex(idx)

    laggard_pump = (btc_ret > THRESH_BPS) & (alt_ret < btc_ret * LAG_RATIO)

    sig = pd.Series(0, index=idx, dtype=int)
    sig[laggard_pump] = -1
    return sig.reindex(df.index).fillna(0).astype(int)


def last_signal(df_closed, ref_closed) -> int:
    """Signal in {-1, 0, 1} at the last CLOSED alt bar. 0 (never raises) when
    either frame is None/empty or the reference's last closed ts is older
    than the alt's (a fillna(0) at the newest bar would silently drop a
    signal — the orchestration checks that lag BEFORE calling this so the
    bar is retried; this is the belt to that suspender)."""
    try:
        if df_closed is None or len(df_closed) == 0:
            return 0
        if ref_closed is None or len(ref_closed) == 0:
            return 0
        if ref_closed.index[-1] < df_closed.index[-1]:
            return 0
        v = int(signals(df_closed, ref_closed).iloc[-1])
        return v if v in (-1, 0, 1) else 0
    except Exception:
        return 0


# ── exit rule, transcribed from research/swarm/lib/screen.py simulate() ────

def _side_int(side) -> int:
    if side in (1, -1):
        return int(side)
    if side == "long":
        return 1
    if side == "short":
        return -1
    raise ValueError(f"side must be long/short or ±1, got {side!r}")


def sl_tp_levels(side, entry: float) -> tuple:
    """(sl, tp) price levels exactly as simulate() computes them."""
    s = _side_int(side)
    tp = entry * (1 + s * TP_BPS / 1e4)
    sl = entry * (1 - s * SL_BPS / 1e4)
    return sl, tp


def exit_check(side, entry: float, bar_high: float, bar_low: float, bar_close: float,
               bars_held: int):
    """One closed bar's exit test for an open position. `bars_held` is the
    0-based index of this bar since entry (the bar the entry was filled in
    is 0). Returns (reason, price) or None:
      SL touched  -> ("stop_loss", sl)     checked first — SL wins ties
      TP touched  -> ("take_profit", tp)
      bars_held >= MAX_HOLD_BARS -> ("time_exit", bar_close)
    simulate(): bars j = entry_i .. entry_i + max_hold_bars, so the time exit
    fires on the max_hold-th bar after the entry bar, at its close."""
    s = _side_int(side)
    sl, tp = sl_tp_levels(s, entry)
    hit_sl = bar_low <= sl if s == 1 else bar_high >= sl
    hit_tp = bar_high >= tp if s == 1 else bar_low <= tp
    if hit_sl:                       # SL first on ties — conservative
        return "stop_loss", sl
    if hit_tp:
        return "take_profit", tp
    if bars_held >= MAX_HOLD_BARS:
        return "time_exit", float(bar_close)
    return None


# ── sidecar state IO (atomic, never breaks the trading cycle) ──────────────

def default_symbol_state() -> dict:
    return {
        "last_bar_ts": None,   # ts_key of the last CLOSED bar the book was synced to
        "bars_held": 0,        # closed bars evaluated since entry (entry bar = 0)
        "entry_bar_ts": None,  # ts_key of the signal bar of the open position
        "last_signal": 0,      # signal at the last evaluated bar (replica/debug)
    }


def load_state(path: str = None) -> dict:
    """{symbol: symbol_state} map; missing/corrupt file or symbols → defaults."""
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
        base = default_symbol_state()
        sub = data.get(sym)
        if isinstance(sub, dict):
            base.update(sub)
        state[sym] = base
    return state


def save_state(state: dict, path: str = None) -> None:
    """Atomic write (tmp + os.replace) — same pattern as donchian_slot."""
    path = path or STATE_FILE  # resolved at call time so tests can repoint STATE_FILE
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except OSError:
        pass  # never let sidecar IO break the trading cycle


def append_signal_bars(symbol: str, records: list, path: str = None) -> None:
    """Append pure-rule per-bar records ({ts, signal, close, ...}) to the
    per-symbol replica series — the fidelity benchmark for grading bot
    behaviour against the frozen rule. Idempotent per bar ts: a re-eval of
    the same bar replaces its record. Bounded to _MAX_BAR_RECORDS."""
    path = path or SIGNAL_FILES.get(symbol)
    if path is None or not records:
        return
    try:
        bars = []
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("bars"), list):
                bars = data["bars"]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        for record in records:
            if bars and bars[-1].get("ts") == record.get("ts"):
                bars[-1] = record
            else:
                bars.append(record)
        if len(bars) > _MAX_BAR_RECORDS:
            del bars[: len(bars) - _MAX_BAR_RECORDS]
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"bars": bars}, f)
        os.replace(tmp, path)
    except OSError:
        pass  # never let sidecar IO break the trading cycle
