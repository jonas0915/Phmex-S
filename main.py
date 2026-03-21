#!/usr/bin/env python3
"""
Phmex-S - Scalp Futures Trading Bot
"""
import os
import sys
import atexit
import argparse
from bot import Phmex2Bot
from logger import setup_logger

logger = setup_logger()

PIDFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bot.pid")


def _check_pidfile():
    """Prevent duplicate bot instances — zombie processes caused $490+ in losses."""
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                old_pid = int(f.read().strip())
            # Check if process is still alive
            os.kill(old_pid, 0)
            logger.error(f"Another bot instance is already running (PID {old_pid}). Exiting.")
            logger.error(f"If stale, remove {PIDFILE} manually.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            # Process is dead — stale pidfile, safe to overwrite
            pass
        except PermissionError:
            # Process exists but we can't signal it — still alive
            logger.error(f"Another bot instance is running (PID in {PIDFILE}). Exiting.")
            sys.exit(1)
    # Write our PID
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(_cleanup_pidfile)


def _cleanup_pidfile():
    try:
        os.remove(PIDFILE)
    except OSError:
        pass


def parse_args():
    parser = argparse.ArgumentParser(description="Phmex-S Scalp Futures Trading Bot")
    parser.add_argument("--mode", choices=["live", "paper"], help="Override trading mode")
    parser.add_argument("--strategy", choices=["momentum", "mean_reversion", "breakout", "combined"],
                        help="Override strategy")
    parser.add_argument("--pairs", help="Comma-separated trading pairs, e.g. BTC/USDT,ETH/USDT")
    parser.add_argument("--timeframe", help="Candlestick timeframe, e.g. 15m")
    return parser.parse_args()


def main():
    _check_pidfile()
    args = parse_args()

    # Apply CLI overrides
    from config import Config
    if args.mode:
        Config.MODE = args.mode
    if args.strategy:
        Config.STRATEGY = args.strategy
    if args.pairs:
        Config.TRADING_PAIRS = args.pairs.split(",")
    if args.timeframe:
        Config.TIMEFRAME = args.timeframe

    logger.info("=" * 60)
    logger.info("   Phmex-S - Scalp Futures Trading Bot")
    logger.info("=" * 60)

    try:
        bot = Phmex2Bot()
        bot.start()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
