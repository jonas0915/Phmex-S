import logging
import logging.handlers
import os
import sys
import colorlog
from config import Config


def setup_logger(name: str = "DegenCryt") -> logging.Logger:
    # PHMEX_LOG_FILE override exists so test runs don't write mocked-order lines
    # into the live bot.log — they read like real fills in forensics (2026-06-11:
    # a pytest run's "BTC @ 99.0 amend rejected" lines were nearly mistaken for a
    # live SL-move failure). tests/conftest.py sets it; live default unchanged.
    log_file = os.environ.get("PHMEX_LOG_FILE", Config.LOG_FILE)
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))

    if logger.handlers:
        return logger

    # Console handler with colors — ONLY when stderr is an interactive TTY.
    # Under launchd / `python main.py >> logs/bot.log 2>&1`, stderr is the redirected
    # bot.log, so adding this handler wrote every line into bot.log TWICE (one ANSI
    # copy here + one clean copy from the file handler) — ~2x log bloat and inflated
    # monitor grep counts (2026-06-23 audit). isatty() keeps colored output for
    # interactive runs while avoiding the double-write headless.
    if sys.stderr.isatty():
        console = colorlog.StreamHandler()
        console.setFormatter(colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s] %(message)s%(reset)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            }
        ))
        logger.addHandler(console)

    # File handler with rotation (10MB max, keep 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    logger.addHandler(file_handler)
    return logger
