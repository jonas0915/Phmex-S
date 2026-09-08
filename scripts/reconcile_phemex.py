#!/usr/bin/env python3
"""Reconcile every real-money ledger's closed_trades vs Phemex fills + funding.

Ledgers covered (``ledger_files``):
  * ``trading_state.json``          (main book; rows with no ``mode`` key are
    historical real money, ``mode == "paper"`` rows are sims since 8/26)
  * ``trading_state_<slot>.json``   (slot ledgers; only ``mode == "live"`` rows
    ever touched Phemex — no-mode slot rows are paper era)
  Sidecars (``*_blocked``, ``*_mode``) and archives (``v8_245trades``,
  ``SR_BOUNCE_era1``) are skipped.

For each real closed_trade in the lookback window (``--lookback-days N``,
default 7):
  1. Match Phemex fills (``fetch_my_trades``) near opened_at (±60 s) and
     closed_at (−300 s … +60 s — sync-loop closes are stamped late). Funding
     settlement rows interleaved in the fill stream (``info.tradeType == "4"``
     / ``action == "13"``) are skipped. Matching is ONE global pass over every
     ledger's rows in closed_at order with a single claimed set, so a fill (or
     a funding settlement) can be absorbed by at most one row across all books.
     Fills are taken in time order and only until the row's matched quantity
     covers ``amount`` (0.1% lot-rounding slack), so a reversal (long exits
     with a sell, short enters with a sell seconds later) cannot leak the next
     entry into this exit.
  2. Sum the real fees (entry + exit) and compare to local ``fees_usdt``.
  3. Attribute Phemex funding payments (``fetch_funding_history``) to the row
     of the same symbol whose (opened_at, closed_at] contains the settlement.
     Sign convention (verified read-only 9/7 on the real account):
     ``amount`` positive = PAID (cost), negative = RECEIVED. That is exactly
     the writer's ``net_pnl = pnl_usdt - fees_usdt - funding_usdt``.
  4. Flag rows with no Phemex fills (UNMATCHED — reported, never patched),
     fee drift > ``FEE_TOLERANCE_USDT``, and any funding change.

By default this is a print-only desync detector.

Run with ``--apply`` to patch each ledger in place: writes ``fees_usdt`` /
``fees_source`` / ``fees_reconciled_at`` (and drops ``fees_pending``) when
fees drifted, ``funding_usdt`` / ``funding_source`` / ``funding_reconciled_at``
when funding changed or was never stamped, and recomputes ``net_pnl``. Each
file is written atomically (temp + ``os.replace``): the patch is applied to a
state re-read immediately before the dump, and the replace is skipped (retried)
if the file's mtime/size moved in that window — the bot's ``_save_state``
rewrites ``positions`` in place every cycle and must never be reverted.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402
from exchange import Exchange  # noqa: E402

LOOKBACK_DAYS = 7
FILL_MATCH_WINDOW_SEC = 60          # fills up to 60s AFTER opened_at / closed_at
ENTRY_MATCH_BEFORE_SEC = 300        # MR slot stamps opened_at 60-80s AFTER the maker fill
                                    # (9/7 dry run: ADA 8/9 63s, 1000SHIB 8/24 67s, BTC 8/30 79s)
EXIT_MATCH_BEFORE_SEC = 300         # exchange_close rows are stamped by the sync loop up to
                                    # a few minutes AFTER the real fill (cycle ≤ 180s watchdog)
QTY_COVERED_FRAC = 0.999            # a leg is covered (stops taking fills) once matched qty ≥ amount × this;
                                    # the 0.1% slack absorbs exchange lot rounding on the last fill
PRINT_CAP = 15                      # max lines per category per ledger in the report
FEE_TOLERANCE_USDT = 0.01           # patch fees when |local - phemex| > this
FUNDING_TOLERANCE_USDT = 1e-6       # funding is exact: patch on any change
MAIN_STATE_FILE = ROOT / "trading_state.json"
STATE_FILE = MAIN_STATE_FILE        # back-compat alias
ARCHIVE_MARKERS = ("_blocked", "_mode", "v8_245trades", "SR_BOUNCE_era1")


def trade_key(t: dict) -> tuple:
    return (t.get("opened_at"), t.get("symbol"), t.get("closed_at"))


def is_funding_row(fill: dict) -> bool:
    """Phemex fetch_my_trades interleaves 8h funding settlements with fills.
    Verified 9/7: settlement rows carry info.tradeType "4" / action "13"
    (real fills: tradeType "1", action "1"). Their fee.cost is the funding
    amount, so counting them as fees would corrupt the round-trip sum."""
    info = fill.get("info") or {}
    return str(info.get("tradeType")) == "4" or str(info.get("action")) == "13"


def fill_key(fill: dict) -> str:
    fid = fill.get("id")
    if fid:
        return str(fid)
    return f"{fill.get('timestamp')}:{fill.get('side')}:{fill.get('price')}:{fill.get('amount')}"


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


def _qty_cap(trade: dict) -> float | None:
    """Per-leg quantity at which the row counts as covered, or None when the
    row has no usable amount (None/0 → no cap, today's behavior)."""
    try:
        amount = float(trade.get("amount") or 0)
    except Exception:
        return None
    return amount * QTY_COVERED_FRAC if amount > 0 else None


def _fill_qty(fill: dict) -> float:
    try:
        return abs(float(fill.get("amount") or 0))
    except Exception:
        return 0.0


def _leg_sides(trade: dict) -> tuple[str | None, str | None]:
    """(entry_side, exit_side) in fill terms for this row; (None, None) = unknown."""
    side = str(trade.get("side") or "").lower()
    if side in ("long", "buy"):
        return "buy", "sell"
    if side in ("short", "sell"):
        return "sell", "buy"
    return None, None


def match_trade_to_fills(trade: dict, fills: list[dict], claimed: set | None = None) -> tuple[list[dict], list[dict], float]:
    """Return (entry_fills, exit_fills, total_fee) for this trade.

    Entry window: opened_at-300s .. opened_at+60s (the slot stamps opened_at a
    cycle after the maker fill). Exit window: closed_at-300s .. closed_at+60s
    (sync-loop closes are stamped late). Matching is side-aware: a long's entry
    is a buy and its exit a sell (the reverse for a short), so the next trade's
    same-symbol entry landing seconds after this exit (PUMP 8/10 8:51 PM) is
    never counted as part of this round trip. Funding settlement rows are
    skipped. `claimed` (fill ids already assigned to an earlier trade) prevents
    a crumb close and the real entry that followed it seconds later from
    sharing fills.

    Fills are visited in ascending timestamp and each leg stops accepting
    fills once its matched quantity covers ``amount`` (× QTY_COVERED_FRAC), so a
    same-side fill from the NEXT trade (a long's exit sell followed by a
    short's entry sell inside the exit window) is left for that trade. Rows
    without a usable ``amount`` (None/0) have no cap. Crumb rows carry the
    intended amount, larger than what filled, so the cap never binds there.
    """
    opened_at = trade.get("opened_at") or 0
    closed_at = trade.get("closed_at") or 0
    entry_side, exit_side = _leg_sides(trade)
    qty_cap = _qty_cap(trade)
    entry_fills: list[dict] = []
    exit_fills: list[dict] = []
    entry_qty = exit_qty = 0.0
    for f in sorted(fills, key=lambda x: x.get("timestamp") or 0):
        if is_funding_row(f):
            continue
        k = fill_key(f)
        if claimed is not None and k in claimed:
            continue
        f_ts = (f.get("timestamp") or 0) / 1000
        f_side = str(f.get("side") or "").lower()
        f_qty = _fill_qty(f)
        in_entry = bool(opened_at) and (opened_at - ENTRY_MATCH_BEFORE_SEC) <= f_ts <= (opened_at + FILL_MATCH_WINDOW_SEC)
        in_exit = bool(closed_at) and (closed_at - EXIT_MATCH_BEFORE_SEC) <= f_ts <= (closed_at + FILL_MATCH_WINDOW_SEC)
        if (in_entry and (entry_side is None or f_side == entry_side)
                and (qty_cap is None or entry_qty < qty_cap)):
            entry_fills.append(f)
            entry_qty += f_qty
        elif (in_exit and (exit_side is None or f_side == exit_side)
                and (qty_cap is None or exit_qty < qty_cap)):
            exit_fills.append(f)
            exit_qty += f_qty
        else:
            continue
        if claimed is not None:
            claimed.add(k)
    total_fee = sum(_fill_fee(f) for f in entry_fills + exit_fills)
    return entry_fills, exit_fills, total_fee


def attribute_funding(trades: list[dict], funding_rows: list[dict]) -> dict[tuple, float]:
    """Sum funding PAID (positive = paid, negative = received — Phemex
    convention verified 9/7) per trade. A payment belongs to the trade of the
    same symbol whose (opened_at, closed_at] contains it; when a partial_tp row
    and its runner both contain it, the earliest-closing row claims it, so each
    settlement is counted exactly once."""
    ordered = sorted(trades, key=lambda t: (t.get("closed_at") or 0))
    out: dict[tuple, float] = {trade_key(t): 0.0 for t in ordered}
    for row in sorted(funding_rows, key=lambda r: r.get("timestamp") or 0):
        ts = (row.get("timestamp") or 0) / 1000
        for t in ordered:
            if t.get("symbol") != row.get("symbol"):
                continue
            o, c = t.get("opened_at") or 0, t.get("closed_at") or 0
            if o < ts <= c:
                out[trade_key(t)] += float(row.get("paid") or 0)
                break
    return out


def ledger_files() -> list[tuple[Path, str]]:
    """Main book + every slot ledger; skips sidecars (_blocked/_mode) and archives."""
    out: list[tuple[Path, str]] = []
    if MAIN_STATE_FILE.exists():
        out.append((MAIN_STATE_FILE, "main"))
    for p in sorted(ROOT.glob("trading_state_*.json")):
        if any(m in p.name for m in ARCHIVE_MARKERS):
            continue
        out.append((p, "slot"))
    return out


def is_real_row(t: dict, kind: str) -> bool:
    """Main: historical rows have no mode = real; mode=="paper" = sim (8/26 demotion).
    Slot: only mode=="live" rows ever touched Phemex (no-mode slot rows are paper era)."""
    if kind == "main":
        return t.get("mode") != "paper"
    return t.get("mode") == "live"


def load_rows(path: Path, kind: str, since_ms: int) -> list[dict]:
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print(f"[ERROR] failed to read {path.name}: {e}")
        return []
    closed = data.get("closed_trades", []) or []
    return [t for t in closed
            if (t.get("closed_at") or 0) * 1000 >= since_ms and is_real_row(t, kind)]


def fetch_funding_rows(exchange: Exchange, symbol: str, since_ms: int) -> list[dict]:
    """Phemex funding payments for symbol since since_ms, as
    {"timestamp": ms, "symbol": unified, "paid": float}. Phemex ignores `since`
    and pages by offset (max 200/page), so page until a short page or 5 pages.
    Sign: positive = paid, negative = received (verified 9/7 on the real account)."""
    out: list[dict] = []
    for page in range(5):
        try:
            rows = exchange.client.fetch_funding_history(symbol, limit=200, params={"offset": page * 200}) or []
        except Exception as e:
            print(f"[WARN] fetch_funding_history({symbol}, offset={page*200}) failed: {e}")
            break
        for r in rows:
            ts = int(r.get("timestamp") or 0)
            if ts < since_ms:
                continue
            out.append({"timestamp": ts, "symbol": symbol, "paid": float(r.get("amount") or 0)})
        if len(rows) < 200:
            break
    return out


def build_patches(rows: list[dict], fills_by_sym: dict[str, list[dict]],
                  funding_by_key: dict[tuple, float]) -> tuple[list[dict], list[dict]]:
    """Decide per row what to write. Rows with no matching fills are reported as
    unmatched and never patched (they did not exist on Phemex).

    Fees are patched only from a complete round trip (entry AND exit legs
    matched). The one exception is a runner: a row sharing (opened_at, symbol)
    with an earlier-closing row (partial_tp) — its entry fee already lives in
    the sibling, so its exit leg alone is its complete fee. Any other one-leg
    match (entry older than Phemex's fill-history horizon, adopted position)
    is a `partial` patch: funding is stamped (the row is proven real) and the
    local fee is left alone."""
    patches: list[dict] = []
    unmatched: list[dict] = []
    claimed: set = set()
    seen_positions: set = set()
    for t in sorted(rows, key=lambda r: (r.get("closed_at") or 0)):
        sym = t.get("symbol") or "?"
        entry_fills, exit_fills, phemex_fee = match_trade_to_fills(t, fills_by_sym.get(sym, []), claimed)
        if not entry_fills and not exit_fills:
            unmatched.append(t)
            continue
        position = (t.get("opened_at"), sym)
        is_runner = position in seen_positions
        seen_positions.add(position)
        complete = bool(entry_fills and exit_fills) or (is_runner and bool(exit_fills))
        local_fee = t.get("fees_usdt")
        new_fee = None
        if complete and (local_fee is None or abs(float(local_fee) - phemex_fee) > FEE_TOLERANCE_USDT):
            new_fee = phemex_fee
        local_funding = float(t.get("funding_usdt") or 0)
        paid = float(funding_by_key.get(trade_key(t), 0.0))
        new_funding = None
        if abs(paid - local_funding) > FUNDING_TOLERANCE_USDT or not t.get("funding_source"):
            new_funding = paid
        if new_fee is None and new_funding is None:
            continue
        patches.append({"key": trade_key(t), "fees_usdt": new_fee, "funding_usdt": new_funding,
                        "local_fee": float(local_fee or 0), "local_funding": local_funding,
                        "partial": not complete, "phemex_fee": phemex_fee,
                        "legs": f"{len(entry_fills)}e/{len(exit_fills)}x", "row": t})
    return patches, unmatched


def reconcile_ledgers(ledgers: list[tuple[Path, str, list[dict]]], fills_by_sym: dict[str, list[dict]],
                      funding_rows: list[dict]) -> dict[Path, tuple[list[dict], list[dict]]]:
    """ONE matching pass across every ledger, then regroup per file.

    Claims are global: all rows from all ledgers are matched in closed_at
    order against a single claimed set, and funding is attributed over the
    union, so a main-book row and a slot row on the same symbol minutes apart
    can never both absorb the same fill or the same settlement — the
    earlier-closing row owns it and the other lands partial/unmatched.
    Returns {path: (patches, unmatched)} in ledger order."""
    owner: dict[int, Path] = {}
    all_rows: list[dict] = []
    for path, _kind, rows in ledgers:
        for t in rows:
            owner[id(t)] = path
            all_rows.append(t)
    funding_by_key = attribute_funding(all_rows, funding_rows)
    patches, unmatched = build_patches(all_rows, fills_by_sym, funding_by_key)
    out: dict[Path, tuple[list[dict], list[dict]]] = {path: ([], []) for path, _, _ in ledgers}
    for p in patches:
        out[owner[id(p["row"])]][0].append(p)
    for t in unmatched:
        out[owner[id(t)]][1].append(t)
    return out


def _patch_closed_rows(closed: list[dict], by_key: dict[tuple, dict], now: int) -> int:
    """Write the precomputed patch values onto matching rows in place; returns count."""
    modified = 0
    for t in closed:
        p = by_key.get(trade_key(t))
        if not p:
            continue
        gross = float(t.get("pnl_usdt") or 0)
        if p["fees_usdt"] is not None:
            t["fees_usdt"] = round(float(p["fees_usdt"]), 6)
            t["fees_source"] = "phemex_reconcile"
            t["fees_reconciled_at"] = now
            t.pop("fees_pending", None)
        if p["funding_usdt"] is not None:
            t["funding_usdt"] = round(float(p["funding_usdt"]), 8)
            t["funding_source"] = "phemex_reconcile"
            t["funding_reconciled_at"] = now
        fees = float(t.get("fees_usdt") or 0)
        funding = float(t.get("funding_usdt") or 0)
        t["net_pnl"] = round(gross - fees - funding, 6)
        modified += 1
    return modified


def _file_sig(path: Path) -> tuple | None:
    """(inode, mtime_ns, size) — moves on any write, including the bot's
    in-place ``_save_state`` (open("w")) that rewrites ``positions``."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def apply_patches(path: Path, patches: list[dict]) -> int:
    """Patch closed_trades rows in `path` with Phemex-truth fees/funding.

    The patch values are decided before this runs (``patches``); here the
    read→replace window is kept to a single fresh read, an in-memory row
    update and one JSON dump: the state re-read at the top of each attempt is
    exactly what gets written, so ``positions``/``peak_balance`` are whatever
    the bot last saved. Before ``os.replace`` the file's (inode, mtime_ns,
    size) must still equal what it was just before that read — a bot write
    landing in the window (positions rewrite or a closed_trades append) makes
    it move and the attempt is retried on a fresh read. Aborts (returns -1)
    if the bot keeps writing concurrently."""
    if not patches:
        return 0
    by_key = {p["key"]: p for p in patches}
    now = int(time.time())
    tmp = path.with_suffix(".json.reconcile.tmp")
    for attempt in range(5):
        sig_before = _file_sig(path)
        try:
            state = json.loads(path.read_text())
        except Exception as e:
            print(f"[ERROR] cannot read {path.name} for apply: {e}")
            return -1
        closed = state.get("closed_trades") or []
        modified = _patch_closed_rows(closed, by_key, now)
        if modified == 0:
            return 0
        tmp.write_text(json.dumps(state))
        if sig_before is None or _file_sig(path) != sig_before:
            tmp.unlink(missing_ok=True)
            time.sleep(0.25)
            continue
        os.replace(tmp, path)
        return modified
    print(f"[WARN] apply aborted for {path.name} after 5 retries — bot writing concurrently")
    return -1


def _fmt_ts(sec: float) -> str:
    return time.strftime('%m-%d %I:%M %p', time.localtime(sec or 0))


def main():
    apply_mode = "--apply" in sys.argv
    lookback = LOOKBACK_DAYS
    if "--lookback-days" in sys.argv:
        lookback = int(sys.argv[sys.argv.index("--lookback-days") + 1])
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - lookback * 86400 * 1000
    stamp = time.strftime('%Y-%m-%d %H:%M:%S')

    print(f"=== Phemex Reconciliation (last {lookback}d){' [APPLY]' if apply_mode else ''} ===")
    print(f"Window: since={time.strftime('%Y-%m-%d %I:%M %p', time.localtime(since_ms/1000))}")

    ledgers = [(p, k, load_rows(p, k, since_ms)) for p, k in ledger_files()]
    ledgers = [(p, k, rows) for p, k, rows in ledgers if rows]
    total_rows = sum(len(r) for _, _, r in ledgers)
    print(f"Real closed_trades in window: {total_rows} across {len(ledgers)} ledger(s)")
    if not ledgers:
        print(f"{stamp} Total discrepancies: 0")
        return

    if not Config.is_live():
        print("[WARN] Not in live mode — cannot reconcile against Phemex")
        return
    exchange = Exchange()
    symbols = sorted({t.get("symbol") for _, _, rows in ledgers for t in rows if t.get("symbol")})
    fills_by_sym = fetch_phemex_fills(exchange, symbols, since_ms)
    funding_rows = [r for sym in symbols for r in fetch_funding_rows(exchange, sym, since_ms)]

    results = reconcile_ledgers(ledgers, fills_by_sym, funding_rows)

    grand_unmatched = 0
    grand_patches = 0
    grand_applied = 0
    funding_applied = 0.0
    for path, kind, rows in ledgers:
        patches, unmatched = results[path]
        fee_patches = [p for p in patches if p["fees_usdt"] is not None]
        fund_patches = [p for p in patches if p["funding_usdt"] is not None]
        fund_changes = [p for p in fund_patches
                        if abs(p["funding_usdt"] - p["local_funding"]) > FUNDING_TOLERANCE_USDT]
        partials = [p for p in patches if p["partial"]]
        print()
        print(f"--- {path.name} ({kind}): {len(rows)} rows | unmatched {len(unmatched)} | partial {len(partials)} | "
              f"fee drift > ${FEE_TOLERANCE_USDT:.2f}: {len(fee_patches)} | "
              f"funding updates: {len(fund_patches)} ({len(fund_changes)} nonzero)")
        for t in unmatched[:PRINT_CAP]:
            print(f"  UNMATCHED {_fmt_ts(t.get('closed_at'))} {t.get('symbol'):<18} {t.get('side',''):<5} pnl={t.get('pnl_usdt',0):+.4f}")
        if len(unmatched) > PRINT_CAP:
            print(f"  ... and {len(unmatched) - PRINT_CAP} more unmatched")
        for p in partials[:PRINT_CAP]:
            print(f"  PARTIAL {p['key'][1]:<18} {_fmt_ts(p['key'][2])} legs={p['legs']} local={p['local_fee']:.4f} "
                  f"phemex_seen={p['phemex_fee']:.4f} (fee kept)")
        for p in fee_patches[:PRINT_CAP]:
            print(f"  FEE  {p['key'][1]:<18} {_fmt_ts(p['key'][2])} local={p['local_fee']:.4f} phemex={p['fees_usdt']:.4f} Δ={p['fees_usdt']-p['local_fee']:+.4f}")
        if len(fee_patches) > PRINT_CAP:
            print(f"  ... and {len(fee_patches) - PRINT_CAP} more fee drifts")
        for p in fund_changes[:PRINT_CAP]:
            print(f"  FUND {p['key'][1]:<18} {_fmt_ts(p['key'][2])} paid={p['funding_usdt']:+.6f} (was {p['local_funding']:+.6f})")
        if len(fund_changes) > PRINT_CAP:
            print(f"  ... and {len(fund_changes) - PRINT_CAP} more funding changes")
        grand_unmatched += len(unmatched)
        grand_patches += len(fee_patches)
        if apply_mode and patches:
            n = apply_patches(path, patches)
            if n > 0:
                grand_applied += n
                funding_applied += sum(p["funding_usdt"] - p["local_funding"] for p in fund_patches)
                print(f"  [APPLY] patched {n} rows in {path.name}")
            elif n < 0:
                print(f"  [APPLY] aborted for {path.name} — concurrent bot write")

    discrepancies = grand_unmatched + grand_patches
    print()
    print(f"{stamp} Total discrepancies: {discrepancies} (unmatched {grand_unmatched}, fee drift {grand_patches})")
    if apply_mode:
        print(f"{stamp} Applied: {grand_applied} rows, funding delta {funding_applied:+.4f} USDT")

    if discrepancies > 0:
        try:
            from notifier import send  # type: ignore
            suffix = f" | applied={grand_applied}, funding Δ{funding_applied:+.4f}" if apply_mode else ""
            send(f"⚠️ Phmex-S reconcile: {grand_unmatched} unmatched, {grand_patches} fee drift > "
                 f"${FEE_TOLERANCE_USDT:.2f} across {len(ledgers)} ledgers (last {lookback}d){suffix}.")
        except Exception as e:
            print(f"[WARN] telegram alert failed: {e}")


if __name__ == "__main__":
    main()
