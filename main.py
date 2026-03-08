#!/usr/bin/env python3
"""
Phmex2 - Active Cryptocurrency Futures Trading Bot
"""
import sys
import argparse
from bot import Phmex2Bot
from logger import setup_logger

logger = setup_logger()


def parse_args():
    parser = argparse.ArgumentParser(description="Phmex2 Active Futures Trading Bot")
    parser.add_argument("--mode", choices=["live", "paper"], help="Override trading mode")
    parser.add_argument("--strategy", choices=["momentum", "mean_reversion", "breakout", "combined"],
                        help="Override strategy")
    parser.add_argument("--pairs", help="Comma-separated trading pairs, e.g. BTC/USDT,ETH/USDT")
    parser.add_argument("--timeframe", help="Candlestick timeframe, e.g. 15m")
    return parser.parse_args()


def main():
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
    logger.info("   Phmex2 - Active Crypto Futures Trading Bot")
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
