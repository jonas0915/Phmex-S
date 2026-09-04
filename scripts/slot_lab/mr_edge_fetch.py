#!/usr/bin/env python3
"""
mr_edge_fetch.py — fixed-window OHLCV + funding refill for the MR edge search.

Fetches [--start, --end) UTC from Phemex with its OWN ccxt client (never imports
bot.py / exchange.py / config.py / risk_manager.py; never touches trading_state*.json
or .env). Paginates with limit=1000, >=0.6 s between calls, retry/backoff on
errors (pattern copied from backtest.fetch_ohlcv_full — re-implemented, NOT imported).

Output dir layout (matches the pickle convention of mean_revert_replay._cached:
a pandas DataFrame with a UTC `timestamp` index and open/high/low/close/volume
columns, duplicates dropped keep-last, sorted):
  {SYMKEY}_{tf}.pkl          SYMKEY = symbol with "/" and ":" -> "_"
  funding_{SYMKEY}.json      list of {"ts": ms, "rate": float}
  manifest.json              per-key checkpoint: rows, first/last ts, expected,
                             deficit, gaps>2 bars, June parity, complete flag

Run under `nice -n 19 python3 -u ...`. Resumable with --resume.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import time
from datetime import datetime, timezone

import pandas as pd

try:  # tests never hit the network but do use the exception classes
    import ccxt
except ImportError:  # pragma: no cover
    ccxt = None

_HERE = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.dirname(os.path.dirname(_HERE))
JUNE_DIR = os.path.join(BOT_DIR, "backtest_data_june")

TF_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}
FUNDING_MS = 8 * 3_600_000
FETCH_LIMIT = 1000
FUNDING_LIMIT = 100
SPACING_S = 0.6
CLOSE_TOL = 1e-9


class FetchFailed(RuntimeError):
    """Raised when a symbol/tf cannot be fetched after max_errors attempts."""


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}Z] {msg}", flush=True)


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------

def symkey(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


def parse_utc_date(s: str) -> int:
    """'YYYY-MM-DD' -> ms since epoch at 00:00 UTC."""
    dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def expected_bars(start_ms: int, until_ms: int, tf: str) -> int:
    return max(0, (until_ms - start_ms) // TF_MS[tf])


def expected_calls(n_bars: int, limit: int) -> int:
    return int(math.ceil(n_bars / limit)) if n_bars > 0 else 0


def rows_to_df(rows: list) -> pd.DataFrame:
    """[ts,o,h,l,c,v] rows -> DataFrame in the mean_revert_replay cache convention."""
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


def gap_stats(ts_list: list, tf: str) -> dict:
    """Largest gap (in bar-steps between consecutive rows), total missing bars,
    and every gap with >2 missing bars."""
    tf_ms = TF_MS[tf]
    out = {"largest_gap_bars": 0, "missing_bars": 0, "gaps_gt2": []}
    if len(ts_list) < 2:
        return out
    for a, b in zip(ts_list[:-1], ts_list[1:]):
        steps = (b - a) // tf_ms
        if steps > 1:
            missing = steps - 1
            out["missing_bars"] += missing
            if steps > out["largest_gap_bars"]:
                out["largest_gap_bars"] = steps
            if missing > 2:
                out["gaps_gt2"].append({"from_ts": int(a), "to_ts": int(b), "missing": int(missing)})
        elif steps == 1 and out["largest_gap_bars"] < 1:
            out["largest_gap_bars"] = 1
    return out


def should_skip(path: str, key: str, manifest: dict, resume: bool) -> bool:
    if not resume:
        return False
    if not os.path.exists(path):
        return False
    return bool(manifest.get(key, {}).get("complete"))


def load_manifest(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_manifest(path: str, manifest: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def june_parity(df5: pd.DataFrame, csv_path: str, tol: float = CLOSE_TOL) -> dict:
    """Bar-for-bar close comparison vs a backtest_data_june CSV on overlapping timestamps."""
    june = pd.read_csv(csv_path)
    june["timestamp"] = pd.to_datetime(june["timestamp"], utc=True, format="ISO8601")
    june = june.set_index("timestamp").sort_index()
    june = june[~june.index.duplicated(keep="last")]
    common = df5.index.intersection(june.index)
    n = int(len(common))
    if n == 0:
        return {"overlap_n": 0, "match_n": 0, "match_rate": None, "first_mismatch_ts": None}
    a = df5.loc[common, "close"].astype(float).values
    b = june.loc[common, "close"].astype(float).values
    ok = abs(a - b) <= tol
    match_n = int(ok.sum())
    first_bad = None
    if match_n < n:
        idx = int((~ok).argmax())
        first_bad = int(common[idx].value // 1_000_000)
    return {"overlap_n": n, "match_n": match_n, "match_rate": match_n / n,
            "first_mismatch_ts": first_bad}


def build_plan(symbols: list, timeframes: list, start_ms: int, until_ms: int,
               funding: bool) -> list:
    plan = []
    for sym in symbols:
        for tf in timeframes:
            n = expected_bars(start_ms, until_ms, tf)
            plan.append({"kind": "ohlcv", "symbol": sym, "tf": tf, "expected": n,
                         "calls": expected_calls(n, FETCH_LIMIT)})
        if funding:
            n = max(0, (until_ms - start_ms) // FUNDING_MS)
            plan.append({"kind": "funding", "symbol": sym, "tf": "8h", "expected": n,
                         "calls": expected_calls(n, FUNDING_LIMIT)})
    return plan


# ---------------------------------------------------------------------------
# paginators (retry pattern mirrors backtest.fetch_ohlcv_full)
# ---------------------------------------------------------------------------

def _retry_sleep(exc: Exception, attempt: int, sleep_fn) -> None:
    if ccxt is not None and isinstance(exc, ccxt.RateLimitExceeded):
        _log(f"    rate limit: {exc} — sleeping 10s")
        sleep_fn(10)
    elif ccxt is not None and isinstance(exc, ccxt.NetworkError):
        wait = min(60, 5 * (2 ** (attempt - 1)))
        _log(f"    network error: {exc} — retry in {wait}s")
        sleep_fn(wait)
    else:
        wait = min(60, 5 * (2 ** (attempt - 1)))
        _log(f"    error: {type(exc).__name__}: {exc} — retry in {wait}s")
        sleep_fn(wait)


def paginate_ohlcv(exchange, symbol: str, tf: str, since_ms: int, until_ms: int,
                   limit: int = FETCH_LIMIT, sleep_fn=time.sleep, spacing: float = SPACING_S,
                   max_errors: int = 8, stats: dict | None = None) -> list:
    """Fetch [since_ms, until_ms) for one symbol/tf. Returns deduped, sorted
    [ts,o,h,l,c,v] rows with ts < until_ms."""
    tf_ms = TF_MS[tf]
    by_ts: dict = {}
    cur = since_ms
    errors = 0
    calls = 0
    while cur < until_ms:
        try:
            batch = exchange.fetch_ohlcv(symbol, tf, since=cur, limit=limit)
            calls += 1
        except Exception as e:  # noqa: BLE001 — retry everything, bounded
            calls += 1
            errors += 1
            if errors >= max_errors:
                raise FetchFailed(f"{symbol} {tf}: {errors} consecutive errors, last={e!r}")
            _retry_sleep(e, errors, sleep_fn)
            continue
        errors = 0
        if not batch:
            break
        for r in batch:
            by_ts[int(r[0])] = [int(r[0])] + [float(x) for x in r[1:6]]
        last_ts = int(batch[-1][0])
        if len(batch) < limit or last_ts + tf_ms >= until_ms:
            break
        cur = last_ts + tf_ms
        sleep_fn(spacing)
    if stats is not None:
        stats["calls"] = calls
    return [by_ts[t] for t in sorted(by_ts) if t < until_ms]


def paginate_funding(exchange, symbol: str, since_ms: int, until_ms: int,
                     limit: int = FUNDING_LIMIT, sleep_fn=time.sleep,
                     spacing: float = SPACING_S, max_errors: int = 8,
                     stats: dict | None = None) -> list:
    """fetch_funding_rate_history over [since_ms, until_ms). Returns sorted
    [{"ts": ms, "rate": float}] deduped by ts."""
    by_ts: dict = {}
    cur = since_ms
    errors = 0
    calls = 0
    while cur < until_ms:
        try:
            batch = exchange.fetch_funding_rate_history(symbol, since=cur, limit=limit)
            calls += 1
        except Exception as e:  # noqa: BLE001
            calls += 1
            errors += 1
            if errors >= max_errors:
                raise FetchFailed(f"{symbol} funding: {errors} consecutive errors, last={e!r}")
            _retry_sleep(e, errors, sleep_fn)
            continue
        errors = 0
        if not batch:
            break
        for r in batch:
            ts = int(r["timestamp"])
            rate = r.get("fundingRate")
            by_ts[ts] = float(rate) if rate is not None else None
        last_ts = max(int(r["timestamp"]) for r in batch)
        if len(batch) < limit or last_ts >= until_ms:
            break
        cur = last_ts + 1
        sleep_fn(spacing)
    if stats is not None:
        stats["calls"] = calls
    return [{"ts": t, "rate": by_ts[t]} for t in sorted(by_ts) if t < until_ms]


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def _fmt_ts(ms) -> str:
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def fetch_one_ohlcv(ex, sym: str, tf: str, start_ms: int, until_ms: int, out_dir: str,
                    manifest: dict, manifest_path: str) -> dict:
    key = f"{symkey(sym)}_{tf}"
    path = os.path.join(out_dir, f"{key}.pkl")
    exp = expected_bars(start_ms, until_ms, tf)
    t0 = time.time()
    stats: dict = {}
    entry = {"symbol": sym, "tf": tf, "kind": "ohlcv", "expected": exp, "complete": False,
             "file": os.path.basename(path)}
    try:
        rows = paginate_ohlcv(ex, sym, tf, start_ms, until_ms, stats=stats)
    except FetchFailed as e:
        entry.update({"error": str(e), "calls": stats.get("calls"), "secs": round(time.time() - t0, 1)})
        manifest[key] = entry
        save_manifest(manifest_path, manifest)
        _log(f"  FAILED {key}: {e}")
        return entry
    df = rows_to_df(rows)
    with open(path, "wb") as f:
        pickle.dump(df, f)
    ts_list = [r[0] for r in rows]
    g = gap_stats(ts_list, tf)
    entry.update({
        "rows": len(rows),
        "first_ts": ts_list[0] if ts_list else None,
        "last_ts": ts_list[-1] if ts_list else None,
        "deficit": exp - len(rows),
        "largest_gap_bars": g["largest_gap_bars"],
        "missing_bars_internal": g["missing_bars"],
        "gaps_gt2": g["gaps_gt2"],
        "calls": stats.get("calls"),
        "secs": round(time.time() - t0, 1),
        "complete": True,
    })
    if tf == "5m":
        csv = os.path.join(JUNE_DIR, f"{symkey(sym)}_5m.csv")
        if os.path.exists(csv):
            entry["june_parity"] = june_parity(df, csv)
    manifest[key] = entry
    save_manifest(manifest_path, manifest)
    jp = entry.get("june_parity")
    jp_s = (f" june={jp['match_n']}/{jp['overlap_n']}"
            f"={(jp['match_rate'] or 0) * 100:.2f}%" if jp and jp["overlap_n"] else "")
    _log(f"  {key}: rows={len(rows)} exp={exp} deficit={entry['deficit']} "
         f"largest_gap={g['largest_gap_bars']} gaps>2={len(g['gaps_gt2'])} "
         f"first={_fmt_ts(entry['first_ts'])} last={_fmt_ts(entry['last_ts'])} "
         f"calls={stats.get('calls')} {entry['secs']}s{jp_s}")
    return entry


def fetch_one_funding(ex, sym: str, start_ms: int, until_ms: int, out_dir: str,
                      manifest: dict, manifest_path: str) -> dict:
    key = f"funding_{symkey(sym)}"
    path = os.path.join(out_dir, f"{key}.json")
    exp = max(0, (until_ms - start_ms) // FUNDING_MS)
    t0 = time.time()
    stats: dict = {}
    entry = {"symbol": sym, "tf": "8h", "kind": "funding", "expected": exp, "complete": False,
             "file": os.path.basename(path)}
    try:
        rates = paginate_funding(ex, sym, start_ms, until_ms, stats=stats)
    except FetchFailed as e:
        entry.update({"error": str(e), "calls": stats.get("calls"), "secs": round(time.time() - t0, 1)})
        manifest[key] = entry
        save_manifest(manifest_path, manifest)
        _log(f"  FAILED {key}: {e}")
        return entry
    with open(path, "w") as f:
        json.dump(rates, f)
    entry.update({
        "rows": len(rates),
        "first_ts": rates[0]["ts"] if rates else None,
        "last_ts": rates[-1]["ts"] if rates else None,
        "deficit": exp - len(rates),
        "calls": stats.get("calls"),
        "secs": round(time.time() - t0, 1),
        "complete": True,
    })
    manifest[key] = entry
    save_manifest(manifest_path, manifest)
    _log(f"  {key}: rows={len(rates)} exp={exp} deficit={entry['deficit']} "
         f"first={_fmt_ts(entry['first_ts'])} last={_fmt_ts(entry['last_ts'])} "
         f"calls={stats.get('calls')} {entry['secs']}s")
    return entry


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, help="UTC date YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", required=True, help="UTC date YYYY-MM-DD (exclusive)")
    ap.add_argument("--universe", required=True, help="JSON file: list of ccxt symbols")
    ap.add_argument("--timeframes", nargs="+", default=["5m", "1m", "1h"])
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--funding", action="store_true", help="also fetch funding-rate history")
    ap.add_argument("--resume", action="store_true", help="skip complete symbol/tf files")
    ap.add_argument("--dry-run", action="store_true", help="print the call plan only")
    args = ap.parse_args(argv)

    for tf in args.timeframes:
        if tf not in TF_MS:
            ap.error(f"unsupported timeframe {tf}")
    start_ms = parse_utc_date(args.start)
    until_ms = parse_utc_date(args.end)
    if until_ms <= start_ms:
        ap.error("--end must be after --start")
    with open(args.universe) as f:
        symbols = json.load(f)
    if isinstance(symbols, dict):
        symbols = symbols.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        ap.error("universe must be a non-empty JSON list (or a dict with a 'symbols' list)")
    symbols = list(dict.fromkeys(symbols))  # dedupe, keep order

    plan = build_plan(symbols, args.timeframes, start_ms, until_ms, args.funding)
    tot_calls = sum(p["calls"] for p in plan)
    tot_bars = sum(p["expected"] for p in plan if p["kind"] == "ohlcv")
    _log(f"window {args.start} -> {args.end} UTC ({(until_ms - start_ms) // 86_400_000} days), "
         f"{len(symbols)} symbols x {args.timeframes} funding={args.funding}")
    per_tf = {}
    for p in plan:
        d = per_tf.setdefault(p["tf"], {"n": 0, "bars": 0, "calls": 0})
        d["n"] += 1
        d["bars"] += p["expected"]
        d["calls"] += p["calls"]
    for tf, d in per_tf.items():
        _log(f"  {tf}: {d['n']} series, expected {d['bars']} rows, {d['calls']} calls")
    est_s = tot_calls * SPACING_S * 1.5  # spacing + latency
    _log(f"  TOTAL: {tot_calls} calls, {tot_bars} OHLCV bars, est ~{est_s / 60:.0f} min at {SPACING_S}s spacing")
    if args.dry_run:
        for p in plan:
            print(f"    {p['kind']:8s} {p['symbol']:22s} {p['tf']:3s} expected={p['expected']:7d} calls={p['calls']}")
        return 0

    if ccxt is None:
        _log("ccxt not installed")
        return 2
    os.makedirs(args.out, exist_ok=True)
    manifest_path = os.path.join(args.out, "manifest.json")
    manifest = load_manifest(manifest_path) if args.resume else {}
    manifest["_meta"] = {"start": args.start, "end": args.end, "start_ms": start_ms,
                         "until_ms": until_ms, "timeframes": args.timeframes,
                         "funding": args.funding, "universe": symbols,
                         "started_utc": datetime.now(timezone.utc).isoformat()}
    ex = ccxt.phemex({"enableRateLimit": True})
    ex.load_markets()
    missing = [s for s in symbols if s not in ex.markets]
    if missing:
        _log(f"WARNING: {len(missing)} symbols not in Phemex markets: {missing}")

    t0 = time.time()
    failed = []
    for i, sym in enumerate(symbols, 1):
        _log(f"[{i}/{len(symbols)}] {sym}")
        if sym in missing:
            for tf in args.timeframes:
                manifest[f"{symkey(sym)}_{tf}"] = {"symbol": sym, "tf": tf, "kind": "ohlcv",
                                                   "complete": False, "error": "not in markets"}
            failed.append(sym)
            save_manifest(manifest_path, manifest)
            continue
        for tf in args.timeframes:
            key = f"{symkey(sym)}_{tf}"
            path = os.path.join(args.out, f"{key}.pkl")
            if should_skip(path, key, manifest, args.resume):
                _log(f"  {key}: skip (resume, complete)")
                continue
            entry = fetch_one_ohlcv(ex, sym, tf, start_ms, until_ms, args.out, manifest, manifest_path)
            if not entry.get("complete"):
                failed.append(f"{sym} {tf}")
            time.sleep(SPACING_S)
        if args.funding:
            key = f"funding_{symkey(sym)}"
            path = os.path.join(args.out, f"{key}.json")
            if should_skip(path, key, manifest, args.resume):
                _log(f"  {key}: skip (resume, complete)")
            else:
                entry = fetch_one_funding(ex, sym, start_ms, until_ms, args.out, manifest, manifest_path)
                if not entry.get("complete"):
                    failed.append(f"{sym} funding")
                time.sleep(SPACING_S)

    manifest["_meta"]["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["_meta"]["runtime_secs"] = round(time.time() - t0, 1)
    manifest["_meta"]["failed"] = failed
    save_manifest(manifest_path, manifest)
    _log(f"DONE in {(time.time() - t0) / 60:.1f} min; failed={failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
