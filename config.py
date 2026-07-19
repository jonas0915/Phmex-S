import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Exchange
    EXCHANGE = os.getenv("EXCHANGE", "phemex")
    API_KEY = os.getenv("API_KEY", "")
    API_SECRET = os.getenv("API_SECRET", "")

    # Trading pairs (futures format: BTC/USDT:USDT)
    TRADING_PAIRS = [s.strip() for s in os.getenv("TRADING_PAIRS", "").split(",") if s.strip()]
    BASE_CURRENCY = os.getenv("BASE_CURRENCY", "USDT")
    TIMEFRAME = os.getenv("TIMEFRAME", "1m")

    # Leverage
    LEVERAGE = int(os.getenv("LEVERAGE", "1"))

    # Position sizing — fixed USDT margin per trade
    TRADE_AMOUNT_USDT = float(os.getenv("TRADE_AMOUNT_USDT", "8.0"))
    TRADE_AMOUNT_PERCENT = float(os.getenv("TRADE_AMOUNT_PERCENT", "2.0"))  # fallback if fixed not set — not currently used by the sizing logic
    MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "3"))
    DAILY_SYMBOL_CAP = int(os.getenv("DAILY_SYMBOL_CAP", "3"))
    MAX_DRAWDOWN_PERCENT = float(os.getenv("MAX_DRAWDOWN_PERCENT", "10.0"))

    # Strategy
    STRATEGY = os.getenv("STRATEGY", "adaptive")

    # Risk management
    STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "1.2"))
    TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "1.8"))
    TRAILING_STOP = os.getenv("TRAILING_STOP", "true").lower() == "true"
    TRAILING_STOP_OFFSET = float(os.getenv("TRAILING_STOP_OFFSET", "1.0"))
    # Margin-ROI % at which the software trail arms. Was hardcoded 5.0 in
    # risk_manager.py; env-driven since 2026-07-05 for the arm-8 forward test
    # (replay: +$2.45/+20% net, avg win +29%, positive both halves — see
    # reports/trail_june_arm8.json). Revert = set 5.0 + restart.
    TRAIL_ARM_ROI = float(os.getenv("TRAIL_ARM_ROI", "5.0"))
    # Durable exchange-resting trail backstop: price % below/above peak once the
    # software trail is armed. Wide on purpose (fast-track 2026-06-11, spec range
    # 1.0-1.5) — software tiers still exit first; this caps inter-cycle reversals.
    DURABLE_TRAIL_BAND_PCT = float(os.getenv("DURABLE_TRAIL_BAND_PCT", "1.2"))

    # Partial take-profit (scale-out): when an open position reaches this margin-ROI
    # %, close half at market and let the runner half continue under normal trail/TP.
    # 0 = disabled. Rationale (2026-06-19 trade audit): winners peak at +6-10% ROI but
    # trail out at ~+2.9%, giving back ~4pts every time. Banking half near the peak
    # locks gains the trail currently surrenders. Main-bot positions only; reversible
    # by setting back to 0. See docs/2026-06-19-partial-tp-scaleout.md.
    PARTIAL_TP_ROI = float(os.getenv("PARTIAL_TP_ROI", "0.0"))

    # Runner take-profit after a partial scale-out: the remaining half aims for this
    # margin-ROI % (its existing trailing stop stays as the downside floor). 0 = the
    # runner keeps the standard TAKE_PROFIT_PERCENT target. Deployed at 25% (Jonas):
    # bank half at +PARTIAL_TP_ROI, let the runner reach for a big move. The stale
    # entry-time exchange TP is cancelled and this target is enforced software-side
    # (cycle + 1Hz watcher, patient maker close).
    PARTIAL_RUNNER_TP_ROI = float(os.getenv("PARTIAL_RUNNER_TP_ROI", "0.0"))

    # Phase 2b — Pullback regime filter flags (shadow-log by default; hard-block only when explicitly true)
    PULLBACK_SESSION_GATE = os.getenv("PULLBACK_SESSION_GATE", "false").lower() == "true"
    PULLBACK_VOLATILE_GATE = os.getenv("PULLBACK_VOLATILE_GATE", "false").lower() == "true"

    # Concurrent-entry drift gate (2026-07-12, r1 A.3 OOS-confirmed): block new
    # htf_l2 entries while any open position is underwater. Set false to revert.
    DRIFT_GATE_ENABLED = os.getenv("DRIFT_GATE_ENABLED", "true").lower() == "true"

    # F5 (2026-07-17): block htf_l2 entries in the thin-tape ∧ high-1h-ADX cell —
    # debug-verified toxic cohort (lifetime −$29.22 @ 47% WR; 99% of July 2026
    # bleed −$21.09/26t). Thin-only (+$6.86 lifetime) and high-ADX-on-active-tape
    # stay ALLOWED — this blocks only the conjunction. IN-SAMPLE evidence:
    # pre-registered forward grading required on any un-halt. Rollback:
    # HTF_THIN_ADX_BLOCK_ENABLED=false + restart.
    HTF_THIN_ADX_BLOCK_ENABLED = os.getenv("HTF_THIN_ADX_BLOCK_ENABLED", "true").lower() == "true"
    HTF_BLOCK_ADX_MIN = float(os.getenv("HTF_BLOCK_ADX_MIN", "35"))
    HTF_BLOCK_TAPE_MAX = int(os.getenv("HTF_BLOCK_TAPE_MAX", "20"))

    # HTF_L2_PAPER probe (2026-07-18): htf_l2 resurrected as a paper slot per the
    # 7/17 action plan D1. Disable = slot not registered next restart.
    HTF_L2_PAPER_ENABLED = os.getenv("HTF_L2_PAPER_ENABLED", "true").lower() == "true"
    # Optional slot-local exit geometry (unset = inherit STOP_LOSS_PERCENT/TAKE_PROFIT_PERCENT)
    HTF_L2_PAPER_SL_PCT = float(os.getenv("HTF_L2_PAPER_SL_PCT")) if os.getenv("HTF_L2_PAPER_SL_PCT") else None
    HTF_L2_PAPER_TP_PCT = float(os.getenv("HTF_L2_PAPER_TP_PCT")) if os.getenv("HTF_L2_PAPER_TP_PCT") else None

    # F2 (2026-07-17): on pause/halt activation, cancel resting NON-reduce-only
    # (entry) orders once — a resting entry that fills mid-halt creates a ghost
    # position (4/13 + 6/14 incident class). Set false for instant revert.
    CANCEL_ENTRIES_ON_PAUSE = os.getenv("CANCEL_ENTRIES_ON_PAUSE", "true").lower() == "true"

    # 5m_mean_revert RSI floor (2026-07-02): block slot LONGS when RSI(7) is
    # below this value (falling-knife cohort per reports/mr_replay_90d.json).
    # 0.0 disables the gate. Applies ONLY to the 5m_mean_revert slot.
    MEAN_REVERT_LONG_RSI_MIN = float(os.getenv("MEAN_REVERT_LONG_RSI_MIN", "0.0"))

    # Slot maker re-quote (2026-07-02): max adverse drift (percent of signal
    # price) at which a slot may re-place a missed PostOnly entry at the fresh
    # touch. Only slots with requote_attempts > 0 use this (5m_mean_revert).
    SLOT_REQUOTE_MAX_DRIFT_PCT = float(os.getenv("SLOT_REQUOTE_MAX_DRIFT_PCT", "0.15"))

    # Mode
    MODE = os.getenv("MODE", "paper")  # "live" or "paper" — default paper for safety

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")

    # Candle lookback for indicators
    CANDLE_LOOKBACK = int(os.getenv("CANDLE_LOOKBACK", "50"))

    # Scalping signal strength minimum
    SCALP_MIN_STRENGTH = float(os.getenv("SCALP_MIN_STRENGTH", "0.70"))

    # Fee & slippage accounting
    TAKER_FEE_PERCENT = float(os.getenv("TAKER_FEE_PERCENT", "0.06"))
    SLIPPAGE_PERCENT = float(os.getenv("SLIPPAGE_PERCENT", "0.05"))
    # Phemex verified base maker rate (0.01%). Used ONLY by the paper-slot fee
    # simulation: live entries are ~99% PostOnly maker, so charging paper entries
    # taker+slippage over-penalized every paper strategy ~$0.23/trade
    # (docs/overnight-2026-07-05/r2_fee_research.md). Live fees are never
    # simulated — they come from the exchange fill.
    MAKER_FEE_PERCENT = float(os.getenv("MAKER_FEE_PERCENT", "0.01"))

    # Maker exit patience (opt-in, prepared 2026-06-11 — exit maker fills were 0%
    # because the legacy limit-exit window is 4s; flow data shows ~0% touch at 4s).
    # OFF (default): _try_limit_exit keeps the legacy 4s window — behavior unchanged.
    # ON: post-only exit rests MAKER_EXIT_PATIENCE_S seconds before cancel-by-id +
    # market fallback. Exchange.py hard-clamps patience to 45s: the close call blocks
    # the main loop, and the 180s cycle watchdog (bot.py:453) raising mid-rest would
    # orphan the resting order. 3 exits x 45s = 135s is the ceiling that still fits.
    MAKER_EXIT_ENABLED = os.getenv("MAKER_EXIT_ENABLED", "false").lower() == "true"
    MAKER_EXIT_PATIENCE_S = float(os.getenv("MAKER_EXIT_PATIENCE_S", "30"))

    # Live exit watcher (tier 2, 2026-06-11): enforce software exit levels
    # (trailing/SL/TP) against live WS price at ~1s instead of the 60s cycle.
    # Enforcement-only — level ratcheting stays on the cycle (see design spec
    # docs/superpowers/specs/2026-06-11-live-exit-watcher-design.md).
    LIVE_EXIT_WATCHER = os.getenv("LIVE_EXIT_WATCHER", "true").lower() == "true"

    # Loop interval in seconds
    LOOP_INTERVAL = float(os.getenv("LOOP_INTERVAL", "60"))

    # Adverse exit — bail out of wrong-direction trades early
    ADVERSE_EXIT_CYCLES = int(os.getenv("ADVERSE_EXIT_CYCLES", "10"))
    ADVERSE_EXIT_THRESHOLD = float(os.getenv("ADVERSE_EXIT_THRESHOLD", "-3.0"))

    # Dynamic scanner
    SCANNER_ENABLED = os.getenv("SCANNER_ENABLED", "true").lower() == "true"
    SCANNER_TOP_N = int(os.getenv("SCANNER_TOP_N", "8"))            # top N symbols to trade
    SCANNER_MIN_VOLUME = float(os.getenv("SCANNER_MIN_VOLUME", "3000000"))  # min 24h USDT volume
    SCANNER_MIN_HISTORY_TRADES = int(os.getenv("SCANNER_MIN_HISTORY_TRADES", "10"))  # min trades before history score applies
    SCANNER_REFRESH_CYCLES = int(os.getenv("SCANNER_REFRESH_CYCLES", "100"))  # refresh every N cycles
    SCANNER_BLACKLIST = [s.strip() for s in os.getenv("SCANNER_BLACKLIST", "").split(",") if s.strip()]

    # Time-of-day entry block (main bot). Empty = 24-hour trading (Jonas 2026-06-30).
    # Comma-separated UTC hours to block. Old Apr-era block was: 0,1,2,9,17,18,19,20
    TRADING_BLOCKED_HOURS_UTC = {int(h.strip()) for h in os.getenv("TRADING_BLOCKED_HOURS_UTC", "").split(",") if h.strip()}

    @classmethod
    def is_live(cls):
        return cls.MODE == "live"

    @classmethod
    def validate(cls):
        if cls.is_live() and (not cls.API_KEY or not cls.API_SECRET):
            raise ValueError("API_KEY and API_SECRET required for live trading")
        if cls.TRADE_AMOUNT_PERCENT <= 0 or cls.TRADE_AMOUNT_PERCENT > 100:
            raise ValueError("TRADE_AMOUNT_PERCENT must be between 0 and 100")
        if cls.MAX_OPEN_TRADES < 1:
            raise ValueError("MAX_OPEN_TRADES must be at least 1")
