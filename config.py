import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Exchange
    EXCHANGE = os.getenv("EXCHANGE", "binance")
    API_KEY = os.getenv("API_KEY", "")
    API_SECRET = os.getenv("API_SECRET", "")

    # Trading pairs (futures format: BTC/USDT:USDT)
    TRADING_PAIRS = os.getenv("TRADING_PAIRS", "BTC/USDT:USDT,ETH/USDT:USDT").split(",")
    BASE_CURRENCY = os.getenv("BASE_CURRENCY", "USDT")
    TIMEFRAME = os.getenv("TIMEFRAME", "15m")

    # Leverage
    LEVERAGE = int(os.getenv("LEVERAGE", "1"))

    # Position sizing — fixed USDT margin per trade
    TRADE_AMOUNT_USDT = float(os.getenv("TRADE_AMOUNT_USDT", "70.0"))
    TRADE_AMOUNT_PERCENT = float(os.getenv("TRADE_AMOUNT_PERCENT", "2.0"))  # fallback if fixed not set
    MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "3"))
    MAX_DRAWDOWN_PERCENT = float(os.getenv("MAX_DRAWDOWN_PERCENT", "10.0"))

    # Strategy
    STRATEGY = os.getenv("STRATEGY", "combined")

    # Risk management
    STOP_LOSS_PERCENT = float(os.getenv("STOP_LOSS_PERCENT", "2.0"))
    TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "4.0"))
    TRAILING_STOP = os.getenv("TRAILING_STOP", "true").lower() == "true"
    TRAILING_STOP_OFFSET = float(os.getenv("TRAILING_STOP_OFFSET", "1.0"))

    # Mode
    MODE = os.getenv("MODE", "paper")  # "live" or "paper"

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")

    # Candle lookback for indicators
    CANDLE_LOOKBACK = 100

    # Loop interval in seconds
    LOOP_INTERVAL = int(os.getenv("LOOP_INTERVAL", "10"))

    # Dynamic scanner
    SCANNER_ENABLED = os.getenv("SCANNER_ENABLED", "true").lower() == "true"
    SCANNER_TOP_N = int(os.getenv("SCANNER_TOP_N", "5"))           # top N gainers to trade
    SCANNER_MIN_VOLUME = float(os.getenv("SCANNER_MIN_VOLUME", "500000"))  # min 24h USDT volume
    SCANNER_REFRESH_CYCLES = int(os.getenv("SCANNER_REFRESH_CYCLES", "10"))  # refresh every N cycles

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
