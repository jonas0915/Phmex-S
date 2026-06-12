#!/usr/bin/env python3
"""
Standalone L2 order-book tick recorder for Phemex (research data collection).

Completely decoupled from the live bot: no project imports, no API keys,
public WebSocket only (ccxt.pro watch_order_book). Records one JSON line per
order-book update to logs/l2_ticks/<symbol_sanitized>/<YYYY-MM-DD>.jsonl (UTC
dates), gzip-rotates at day end, purges compressed files older than
RETENTION_DAYS, and pauses recording (without crashing) if the tick directory
exceeds MAX_DIR_BYTES.

Purpose: tick-level data to test whether early whale accumulation is
detectable at our latency (see docs/2026-06-01-imbalance-reversion-edge-findings.md
and docs/2026-06-11-l2-recorder.md).

Run:  python scripts/l2_tick_recorder.py        (foreground)
      launchd: com.phmex.l2-recorder            (KeepAlive daemon)
"""

import asyncio
import gzip
import json
import logging
import logging.handlers
import os
import shutil
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt.pro as ccxtpro

# ── Configuration ─────────────────────────────────────────────────────────────

SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "INJ/USDT:USDT",
    "ARB/USDT:USDT",
]
DEPTH = 5                           # top-N levels per side recorded
                                    # (depth 10 measured ~1.05 GB/day on 2026-06-11 — over budget)
RETENTION_DAYS = 14                 # delete .jsonl.gz older than this
MAX_DIR_BYTES = 5 * 1024**3        # 5 GB hard cap on logs/l2_ticks/
RESUME_BYTES = int(MAX_DIR_BYTES * 0.90)  # resume below 90% of cap
FLUSH_SECONDS = 5.0                 # max seconds between fsync-less flushes
DISK_CHECK_SECONDS = 60             # how often to check dir size / retention
STATS_SECONDS = 60                  # how often to log per-symbol update rates

BASE_DIR = Path(__file__).resolve().parent.parent       # project root
TICK_DIR = BASE_DIR / "logs" / "l2_ticks"
LOG_FILE = BASE_DIR / "logs" / "l2_recorder.log"

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("l2_recorder")
logger.setLevel(logging.INFO)
_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024**2, backupCount=3)
_handler.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_handler)
# Mirror to stdout when run in foreground / under launchd
_console = logging.StreamHandler()
_console.setFormatter(_handler.formatter)
logger.addHandler(_console)


def sanitize(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Per-symbol JSONL writer with daily gzip rotation ──────────────────────────

class SymbolWriter:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.dir = TICK_DIR / sanitize(symbol)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._fh = None
        self._date = None
        self._last_flush = time.monotonic()
        self.lines = 0          # total lines written (lifetime)
        self.bytes = 0          # total bytes written (lifetime)

    def write(self, line: str):
        today = utc_date()
        if self._date != today:
            self._rotate(today)
        self._fh.write(line)
        self.lines += 1
        self.bytes += len(line)
        now = time.monotonic()
        if now - self._last_flush >= FLUSH_SECONDS:
            self._fh.flush()
            self._last_flush = now

    def _rotate(self, today: str):
        old_path = None
        if self._fh:
            old_path = self.dir / f"{self._date}.jsonl"
            self._fh.flush()
            self._fh.close()
        self._date = today
        self._fh = open(self.dir / f"{today}.jsonl", "a", encoding="utf-8")
        self._last_flush = time.monotonic()
        if old_path and old_path.exists():
            gzip_file(old_path)

    def close(self):
        if self._fh:
            try:
                self._fh.flush()
                self._fh.close()
            except Exception:
                pass
            self._fh = None


def gzip_file(path: Path):
    """Compress path -> path.gz and remove the original. Never raises."""
    try:
        gz_path = path.with_suffix(path.suffix + ".gz")
        with open(path, "rb") as src, gzip.open(gz_path, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst, length=1024 * 256)
        path.unlink()
        logger.info(f"Rotated {path.name} -> {gz_path.name} "
                    f"({gz_path.stat().st_size / 1024:.0f} KB)")
    except Exception as e:
        logger.error(f"gzip rotation failed for {path}: {e}")


def compress_stale_jsonl():
    """At startup: gzip any leftover .jsonl files from previous UTC days."""
    today = utc_date()
    for path in TICK_DIR.glob("*/*.jsonl"):
        if path.stem != today:
            gzip_file(path)


def purge_old_archives():
    """Delete .jsonl.gz older than RETENTION_DAYS (by filename date)."""
    cutoff = time.time() - RETENTION_DAYS * 86400
    for path in TICK_DIR.glob("*/*.jsonl.gz"):
        try:
            file_date = datetime.strptime(path.name[:10], "%Y-%m-%d") \
                .replace(tzinfo=timezone.utc)
            if file_date.timestamp() < cutoff:
                path.unlink()
                logger.info(f"Purged old archive {path.name} ({path.parent.name})")
        except ValueError:
            continue  # unexpected filename, leave it alone


def dir_size_bytes() -> int:
    total = 0
    for root, _dirs, files in os.walk(TICK_DIR):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


# ── Recorder ──────────────────────────────────────────────────────────────────

class L2Recorder:
    def __init__(self):
        self.exchange = None
        self.writers = {s: SymbolWriter(s) for s in SYMBOLS}
        self.stop_event = asyncio.Event()
        self.paused = False

    async def watch_symbol(self, symbol: str):
        """Stream order-book updates for one symbol with reconnect backoff.
        ccxt.pro maintains the full book from Phemex incremental (book_p)
        messages and handles ping/pong keepalive internally; each await
        resolves once per update pushed by the exchange."""
        writer = self.writers[symbol]
        backoff = 2
        while not self.stop_event.is_set():
            try:
                ob = await self.exchange.watch_order_book(symbol)
                backoff = 2
                if self.paused:
                    continue
                line = json.dumps({
                    "ts": int(time.time() * 1000),       # local receive time
                    "et": ob.get("timestamp"),            # exchange timestamp (may be None)
                    "n": ob.get("nonce"),                 # book sequence number
                    "sym": symbol,
                    "b": ob["bids"][:DEPTH],
                    "a": ob["asks"][:DEPTH],
                }, separators=(",", ":")) + "\n"
                writer.write(line)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.stop_event.is_set():
                    break
                logger.warning(f"{symbol} stream error, retry in {backoff}s: "
                               f"{str(e)[:150]}")
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 60)

    async def disk_guard(self):
        """Enforce retention and the hard size cap; pause instead of crash."""
        while not self.stop_event.is_set():
            try:
                purge_old_archives()
                size = await asyncio.to_thread(dir_size_bytes)
                if not self.paused and size > MAX_DIR_BYTES:
                    self.paused = True
                    logger.warning(
                        f"l2_ticks at {size / 1024**3:.2f} GB exceeds "
                        f"{MAX_DIR_BYTES / 1024**3:.0f} GB cap — RECORDING PAUSED. "
                        f"Free space or raise MAX_DIR_BYTES to resume.")
                elif self.paused and size < RESUME_BYTES:
                    self.paused = False
                    logger.warning(
                        f"l2_ticks down to {size / 1024**3:.2f} GB — recording resumed.")
            except Exception as e:
                logger.error(f"disk guard error: {e}")
            try:
                await asyncio.wait_for(self.stop_event.wait(),
                                       timeout=DISK_CHECK_SECONDS)
            except asyncio.TimeoutError:
                pass

    async def stats_reporter(self):
        """Log per-symbol update rates so health is visible in the log."""
        prev = {s: 0 for s in SYMBOLS}
        prev_t = time.monotonic()
        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=STATS_SECONDS)
                break
            except asyncio.TimeoutError:
                pass
            now = time.monotonic()
            dt = now - prev_t
            parts = []
            for s in SYMBOLS:
                w = self.writers[s]
                rate = (w.lines - prev[s]) / dt if dt > 0 else 0
                parts.append(f"{s.split('/')[0]}={rate:.1f}/s")
                prev[s] = w.lines
            prev_t = now
            total_mb = sum(w.bytes for w in self.writers.values()) / 1024**2
            state = "PAUSED" if self.paused else "recording"
            logger.info(f"[stats] {state} | " + " ".join(parts) +
                        f" | session total {total_mb:.1f} MB")

    async def run(self):
        TICK_DIR.mkdir(parents=True, exist_ok=True)
        compress_stale_jsonl()
        purge_old_archives()

        self.exchange = ccxtpro.phemex({
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })  # public channels only — deliberately NO apiKey/secret
        logger.info(f"L2 tick recorder starting — {len(SYMBOLS)} symbols, "
                    f"depth {DEPTH}, dir cap {MAX_DIR_BYTES / 1024**3:.0f} GB, "
                    f"retention {RETENTION_DAYS}d")
        try:
            tasks = [asyncio.create_task(self.watch_symbol(s)) for s in SYMBOLS]
            tasks.append(asyncio.create_task(self.disk_guard()))
            tasks.append(asyncio.create_task(self.stats_reporter()))
            await self.stop_event.wait()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            try:
                await self.exchange.close()
            except Exception:
                pass
            for w in self.writers.values():
                w.close()
            total = sum(w.lines for w in self.writers.values())
            logger.info(f"Shut down cleanly — {total} updates recorded this session.")

    def request_stop(self, signame: str):
        logger.info(f"Received {signame} — shutting down...")
        self.stop_event.set()


def main():
    recorder = L2Recorder()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, recorder.request_stop, sig.name)
    try:
        loop.run_until_complete(recorder.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
