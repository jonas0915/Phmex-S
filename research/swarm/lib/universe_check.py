"""Universe tradeability gate (2026-09-21). A research cache does not know when the exchange
delists a market: GIGGLE/USDT:USDT was delisted on Phemex (last 1h bar 2026-08-07 10:00 UTC)
while the long_1h cache ends 2026-08-01, so a screen, a prereg and a paper slot all carried a
symbol the bot could never trade. `fee_math.lot_check` checks lot size only.

`check()` is PURE — it reads a ccxt markets dict and never touches the network. The one
network function is `fetch_markets()`; the desk's register seat and the build's prereg
precondition call the CLI, which uses it unless `--markets-json` supplies a saved dict.

A market is tradeable iff it is present in the dict and `active` is truthy (ccxt derives
`active` from Phemex `info.status == 'Listed'`)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from research.swarm.lib.fee_math import base_symbol

REPO_ROOT = Path(__file__).resolve().parents[3]
QUOTE = "USDT"
NOT_FOUND = "NOT_FOUND"


def to_exchange_symbol(symbol: str) -> str:
    """'GIGGLE', 'giggle', 'GIGGLE_USDT_USDT', 'GIGGLE/USDT:USDT' -> 'GIGGLE/USDT:USDT'."""
    return f"{base_symbol(symbol)}/{QUOTE}:{QUOTE}"


def check(symbols: list[str], markets: dict) -> dict:
    """Pure. {"symbols": [{input, symbol, found, active, status}], "tradeable": [inputs],
    "untradeable": [exchange symbols], "all_tradeable": bool}. Input order is kept."""
    recs = []
    for s in symbols:
        ex = to_exchange_symbol(s)
        m = markets.get(ex)
        found = m is not None
        info = (m or {}).get("info") or {}
        recs.append({
            "input": s,
            "symbol": ex,
            "found": found,
            "active": bool((m or {}).get("active")) if found else False,
            "status": info.get("status") if found else None,
        })
    result = {"symbols": recs}
    result["tradeable"] = [r["input"] for r in recs if _tradeable(r)]
    result["untradeable"] = untradeable(result)
    result["all_tradeable"] = all_tradeable(result)
    return result


def _tradeable(rec: dict) -> bool:
    return bool(rec["found"] and rec["active"])


def all_tradeable(result: dict) -> bool:
    """True iff every symbol is found and active. An empty universe is NOT tradeable."""
    recs = result["symbols"]
    return bool(recs) and all(_tradeable(r) for r in recs)


def untradeable(result: dict) -> list[str]:
    """Exchange-form symbols that are missing or not active, in input order."""
    return [r["symbol"] for r in result["symbols"] if not _tradeable(r)]


def _drop_status(rec: dict) -> str:
    return (rec["status"] or "INACTIVE") if rec["found"] else NOT_FOUND


def dropped_symbols(result: dict) -> list[dict]:
    """[{symbol, status}] for every untradeable symbol — the register seat's record."""
    return [{"symbol": r["symbol"], "status": _drop_status(r)} for r in result["symbols"] if not _tradeable(r)]


def prune_universe(thesis: dict, result: dict) -> tuple[dict, list[dict]]:
    """Copy of `thesis` with untradeable symbols removed from spec.universe (input form kept),
    plus the dropped list. The input dict is not mutated."""
    pruned = json.loads(json.dumps(thesis))
    keep = set(result["tradeable"])
    pruned["spec"]["universe"] = [s for s in thesis["spec"]["universe"] if s in keep]
    return pruned, dropped_symbols(result)


def fetch_markets(timeout_ms: int = 10000) -> dict:
    """The ONLY network call in this module. Never called by check()."""
    import ccxt  # local import: tests and check() never need it

    return ccxt.phemex({"timeout": timeout_ms, "options": {"defaultType": "swap"}}).load_markets()


def _universe_from_file(path: Path) -> list[str]:
    d = json.loads(Path(path).read_text())
    thesis = d["thesis"] if "thesis" in d else d          # frozen spec or bare thesis
    return list(thesis["spec"]["universe"])


def _line(rec: dict) -> str:
    state = "active" if _tradeable(rec) else ("DELISTED" if rec["found"] else NOT_FOUND)
    return f"{rec['symbol']} {state} status={rec['status']}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m research.swarm.lib.universe_check",
                                 description="Is every universe symbol a live Phemex USDT-perp market?")
    ap.add_argument("symbols", nargs="*", help="base or exchange-form symbols (GIGGLE, BTC/USDT:USDT)")
    ap.add_argument("--frozen", help="read spec.universe from a *.frozen.json (build prereg)")
    ap.add_argument("--thesis", help="read spec.universe from a thesis JSON (desk register seat)")
    ap.add_argument("--prune-to", help="with --thesis: write a copy with untradeable symbols removed from spec.universe (not written when nothing tradeable remains)")
    ap.add_argument("--markets-json", help="use a saved ccxt markets dict instead of the network")
    ap.add_argument("--save-markets", help="write the markets dict used to this path (reproducibility)")
    ap.add_argument("--json", action="store_true", help="print the check() dict as JSON")
    ap.add_argument("--timeout-ms", type=int, default=10000)
    a = ap.parse_args(argv)

    symbols = list(a.symbols)
    thesis = None
    if a.frozen:
        symbols += _universe_from_file(Path(a.frozen))
    if a.thesis:
        thesis = json.loads(Path(a.thesis).read_text())
        symbols += list(thesis["spec"]["universe"])
    if not symbols:
        ap.error("no symbols: pass SYM... or --frozen/--thesis")
    if a.prune_to and thesis is None:
        ap.error("--prune-to requires --thesis")

    markets = json.loads(Path(a.markets_json).read_text()) if a.markets_json else fetch_markets(a.timeout_ms)
    if a.save_markets:
        Path(a.save_markets).write_text(json.dumps(markets, sort_keys=True))

    result = check(symbols, markets)
    result["dropped_symbols"] = dropped_symbols(result)
    result["pruned_path"] = None
    if a.prune_to and result["tradeable"]:
        pruned, _ = prune_universe(thesis, result)
        Path(a.prune_to).parent.mkdir(parents=True, exist_ok=True)
        Path(a.prune_to).write_text(json.dumps(pruned, indent=2, ensure_ascii=False))
        result["pruned_path"] = a.prune_to

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        for rec in result["symbols"]:
            print(_line(rec))
        print("UNIVERSE OK" if result["all_tradeable"] else f"UNIVERSE UNTRADEABLE: {', '.join(result['untradeable'])}")
    return 0 if result["all_tradeable"] else 1


if __name__ == "__main__":
    sys.exit(main())
