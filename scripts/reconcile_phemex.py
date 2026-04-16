#!/usr/bin/env python3
"""Reconcile bot's closed_trades vs Phemex fills by time+PnL matching.

For each local closed_trade in the lookback window:
  1. Fetch Phemex fills for that symbol near opened_at and closed_at
  2. Sum real fees from matching fills (entry + exit)
  3. Compare Phemex fees to local fees_usdt
  4. Flag any trade with no Phemex match, or fee delta > tolerance

By default this is a print-only desync detector.

Run with ``--apply`` to also patch ``trading_state.json`` in place:
overwrites ``fees_usdt`` and recomputes ``net_pnl = pnl_usdt - fees_usdt -
funding_usdt`` for every trade whose fees drifted beyond tolerance. The
write is atomic (temp file + ``os.replace``) and aborts if the state file
grew in between (to avoid clobbering a trade the bot just closed).
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402
from exchange import Exchange  # noqa: E402

LOOKBACK_DAYS = 7
FILL_MATCH_WINDOW_SEC = 60          # fills within 60s of opened_at/closed_at count as match
FEE_TOLERANCE_USDT = 0.05            # drift if |local_fee - phemex_fee| > this
STATE_FILE = ROOT / "trading_state.json"


def load_closed_trades(since_ms: int) -> list[dict]:
    if not STATE_FILE.exists():
        print(f"[WARN] {STATE_FILE} not found")
        return []
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception as e:
        print(f"[ERROR] failed to read {STATE_FILE}: {e}")
        return []
    closed = data.get("closed_trades", []) or []
    return [t for t in closed if (t.get("closed_at") or 0) * 1000 >= since_ms]


def fetch_phemex_fills(exchange: Exchange, symbols: list[str], since_ms: int) -> dict[str, list[dict]]:
    """Fetch all fills per symbol since since_ms. Returns {symbol: [fills]}."""
    if not Config.is_live():
        print("[WARN] Not in live mode — cannot reconcile against Phemex")
        return {}
    out: dict[str, list[dict]] = {}
    for sym in symbols:
        try:
            fills = exchange.client.fetch_my_trades(sym, since=since_ms, limit=500) or []
            out[sym] = fills
        except Exception as e:
            print(f"[WARN] fetch_my_trades({sym}) failed: {e}")
            out[sym] = []
    return out


def _fill_fee(fill: dict) -> float:
    """Extract fee cost from a ccxt fill record, summing fees list if needed."""
    fee = fill.get("fee") or {}
    if fee.get("cost") is not None:
        try:
            return abs(float(fee.get("cost") or 0))
        except Exception:
            pass
    total = 0.0
    for f in fill.get("fees") or []:
        try:
            if f.get("cost") is not None:
                total += abs(float(f.get("cost") or 0))
        except Exception:
            pass
    return total


def match_trade_to_fills(trade: dict, fills: list[dict]) -> tuple[list[dict], list[dict], float]:
    """Return (entry_fills, exit_fills, total_fee) matching this trade by timestamp proximity."""
    opened_at = trade.get("opened_at") or 0
    closed_at = trade.get("closed_at") or 0
    entry_fills = []
    exit_fills = []
    for f in fills:
        f_ts = (f.get("timestamp") or 0) / 1000
        if opened_at and abs(f_ts - opened_at) <= FILL_MATCH_WINDOW_SEC:
            entry_fills.append(f)
        elif closed_at and abs(f_ts - closed_at) <= FILL_MATCH_WINDOW_SEC:
            exit_fills.append(f)
    total_fee = sum(_fill_fee(f) for f in entry_fills + exit_fills)
    return entry_fills, exit_fills, total_fee


def apply_fee_fixes(fixes: list[tuple[dict, float, float]]) -> int:
    """Patch trading_state.json in place with Phemex-truth fees.

    fixes = list of (trade_dict, local_fee, phemex_fee).
    Trades are matched back into state by (opened_at, symbol, closed_at).
    Uses atomic temp+rename. Aborts if the state file's closed_trades count
    shrinks between read and write (meaning the bot wrote concurrently and
    we'd lose data by overwriting).
    """
    if not fixes:
        return 0
    for attempt in range(5):
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception as e:
            print(f"[ERROR] cannot read state for apply: {e}")
            return -1
        closed = state.get("closed_trades") or []
        original_count = len(closed)
        by_key: dict[tuple, dict] = {}
        for t in closed:
            key = (t.get("opened_at"), t.get("symbol"), t.get("closed_at"))
            by_key[key] = t

        modified = 0
        for t, _lf, phemex_fee in fixes:
            key = (t.get("opened_at"), t.get("symbol"), t.get("closed_at"))
            live = by_key.get(key)
            if not live:
                continue
            old_fee = float(live.get("fees_usdt") or 0)
            if abs(old_fee - phemex_fee) <= FEE_TOLERANCE_USDT:
                continue
            gross = float(live.get("pnl_usdt") or 0)
            funding = float(live.get("funding_usdt") or 0)
            live["fees_usdt"] = round(phemex_fee, 6)
            live["net_pnl"] = round(gross - phemex_fee - funding, 6)
            live["fees_source"] = "phemex_reconcile"
            live["fees_reconciled_at"] = int(time.time())
            modified += 1

        if modified == 0:
            return 0

        tmp = STATE_FILE.with_suffix(".json.reconcile.tmp")
        tmp.write_text(json.dumps(state))

        # Sanity: re-read current state right before swap. If the bot has
        # closed a new trade in the meantime, retry rather than clobber it.
        try:
            current = json.loads(STATE_FILE.read_text())
        except Exception:
            current = {}
        if len(current.get("closed_trades") or []) != original_count:
            tmp.unlink(missing_ok=True)
            time.sleep(0.25)
            continue

        os.replace(tmp, STATE_FILE)
        return modified

    print("[WARN] apply aborted after 5 retries — bot writing concurrently")
    return -1


def main():
    apply_mode = "--apply" in sys.argv
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - LOOKBACK_DAYS * 86400 * 1000

    print(f"=== Phemex Reconciliation (last {LOOKBACK_DAYS}d){' [APPLY]' if apply_mode else ''} ===")
    print(f"Window: since={time.strftime('%Y-%m-%d %I:%M %p', time.localtime(since_ms/1000))}")

    local_trades = load_closed_trades(since_ms)
    print(f"Local closed_trades in window: {len(local_trades)}")
    if not local_trades:
        print("Nothing to reconcile.")
        return

    # Discover symbols
    symbols = sorted({t.get("symbol") for t in local_trades if t.get("symbol")})

    exchange = Exchange()
    fills_by_sym = fetch_phemex_fills(exchange, symbols, since_ms)

    # Reconcile trade-by-trade
    unmatched: list[dict] = []          # local trades with no Phemex fills nearby
    fee_drift: list[tuple[dict, float, float]] = []  # (trade, local_fee, phemex_fee)
    matched_count = 0

    for t in local_trades:
        sym = t.get("symbol") or "?"
        fills = fills_by_sym.get(sym, [])
        entry_fills, exit_fills, phemex_fee = match_trade_to_fills(t, fills)
        if not entry_fills and not exit_fills:
            unmatched.append(t)
            continue
        matched_count += 1
        local_fee = t.get("fees_usdt")
        if local_fee is None:
            # Any missing fee is itself a drift (pre-fix trades OR I7 silent zero)
            fee_drift.append((t, 0.0, phemex_fee))
        elif abs(float(local_fee) - phemex_fee) > FEE_TOLERANCE_USDT:
            fee_drift.append((t, float(local_fee), phemex_fee))

    # Per-symbol summary
    by_sym: dict[str, dict] = defaultdict(lambda: {"count": 0, "local_fee": 0.0, "phemex_fee": 0.0})
    for t in local_trades:
        sym = t.get("symbol") or "?"
        fills = fills_by_sym.get(sym, [])
        _, _, phemex_fee = match_trade_to_fills(t, fills)
        by_sym[sym]["count"] += 1
        by_sym[sym]["local_fee"] += float(t.get("fees_usdt") or 0)
        by_sym[sym]["phemex_fee"] += phemex_fee

    print()
    print(f"{'Symbol':<18}{'Trades':>8}{'LocalFee':>12}{'PhemexFee':>12}{'Δfee':>10}")
    print("-" * 60)
    sym_drift = 0
    for sym in sorted(by_sym.keys()):
        b = by_sym[sym]
        d = b["phemex_fee"] - b["local_fee"]
        flag = ""
        if abs(d) > FEE_TOLERANCE_USDT:
            flag = "  <-- DIFF"
            sym_drift += 1
        print(f"{sym:<18}{b['count']:>8}{b['local_fee']:>12.4f}{b['phemex_fee']:>12.4f}{d:>10.4f}{flag}")
    print("-" * 60)

    discrepancies = len(unmatched) + len(fee_drift)
    print()
    print(f"Matched: {matched_count}/{len(local_trades)}")
    print(f"Unmatched (no Phemex fill within {FILL_MATCH_WINDOW_SEC}s): {len(unmatched)}")
    print(f"Fee drift > ${FEE_TOLERANCE_USDT:.2f}: {len(fee_drift)}")
    print(f"Total discrepancies: {discrepancies}")

    if unmatched:
        print()
        print("UNMATCHED TRADES:")
        for t in unmatched[:10]:
            ts = time.strftime('%m-%d %I:%M %p', time.localtime((t.get('closed_at') or 0)))
            print(f"  {ts} {t.get('symbol'):<18} {t.get('side',''):<5} pnl={t.get('pnl_usdt',0):+.4f}")
        if len(unmatched) > 10:
            print(f"  ... and {len(unmatched)-10} more")

    if fee_drift:
        print()
        print("FEE DRIFT:")
        for t, lf, pf in fee_drift[:10]:
            ts = time.strftime('%m-%d %I:%M %p', time.localtime((t.get('closed_at') or 0)))
            print(f"  {ts} {t.get('symbol'):<18} local={lf:.4f} phemex={pf:.4f} Δ={pf-lf:+.4f}")
        if len(fee_drift) > 10:
            print(f"  ... and {len(fee_drift)-10} more")

    # Apply fixes to local state if requested
    applied = 0
    if apply_mode and fee_drift:
        applied = apply_fee_fixes(fee_drift)
        print()
        if applied > 0:
            print(f"[APPLY] Patched fees on {applied} trades in {STATE_FILE.name}")
        elif applied == 0:
            print("[APPLY] Nothing to patch (already within tolerance)")
        else:
            print("[APPLY] Patch aborted — concurrent bot write detected")

    # Telegram alert on drift
    if discrepancies > 0:
        try:
            from notifier import send  # type: ignore
            suffix = f" | applied={applied}" if apply_mode else ""
            msg = (
                f"⚠️ Phmex-S reconcile: {len(unmatched)} unmatched, "
                f"{len(fee_drift)} fee drift > ${FEE_TOLERANCE_USDT:.2f} "
                f"(last {LOOKBACK_DAYS}d){suffix}. Check logs."
            )
            send(msg)
        except Exception as e:
            print(f"[WARN] telegram alert failed: {e}")


if __name__ == "__main__":
    main()
