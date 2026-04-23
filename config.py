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

    # Phase 2b — Pullback regime filter flags (shadow-log by default; hard-block only when explicitly true)
    PULLBACK_SESSION_GATE = os.getenv("PULLBACK_SESSION_GATE", "false").lower() == "true"
    PULLBACK_VOLATILE_GATE = os.getenv("PULLBACK_VOLATILE_GATE", "false").lower() == "true"

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
