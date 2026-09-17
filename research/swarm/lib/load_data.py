"""Dataset loaders with a hard era split. Screens call era='train'. Holdout rows — for
every loader, OHLCV and funding alike — are refused without the committee token; the
token is not a secret, it is a deliberate, greppable act (spec §5 step 4)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.swarm.lib.fee_math import base_symbol

REPO_ROOT = Path(__file__).resolve().parents[3]
COMMITTEE_TOKEN = "COMMITTEE-HOLDOUT-READ"

DATASETS = {
    "mr_edge": {"dir": "reports/cache/mr_edge_20260601_20260903", "pattern": "{sym}_{tf}.pkl",
                "timeframes": ("1m", "5m", "1h"), "span": "2026-06-01 → 2026-09-02"},
    "long_1h": {"dir": "scripts/research/mr-universe-scan-2026-08-01/cache", "pattern": "{sym}_{tf}_400d.parquet",
                "timeframes": ("1h", "5m"), "span": "2025-06-27 → 2026-08-01 (1h)"},
}


class HoldoutError(PermissionError):
    pass


def _cache_name(symbol: str) -> str:
    return f"{base_symbol(symbol)}_USDT_USDT"


def holdout_start(t0: pd.Timestamp, t1: pd.Timestamp, frac: float = 0.25) -> pd.Timestamp:
    return t1 - (t1 - t0) * frac


def split_era(df: pd.DataFrame, era: str, token: str | None = None, frac: float = 0.25,
              bounds: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> pd.DataFrame:
    if era not in ("train", "holdout", "all"):
        raise ValueError(f"era must be train|holdout|all, got {era!r}")
    t0, t1 = bounds if bounds is not None else (df.index.min(), df.index.max())
    hs = holdout_start(t0, t1, frac)
    if era == "train":
        return df[df.index < hs]
    if token != COMMITTEE_TOKEN:
        raise HoldoutError(f"era={era!r} requires the committee token (spec §5 step 4)")
    return df if era == "all" else df[df.index >= hs]


def list_symbols(dataset: str = "mr_edge", root: Path = REPO_ROOT) -> list[str]:
    spec = DATASETS[dataset]
    d = root / spec["dir"]
    names = {p.name.split("_USDT_USDT")[0] for p in d.iterdir() if "_USDT_USDT" in p.name and not p.name.startswith("funding")}
    return sorted(names)


def load_ohlcv(symbol: str, timeframe: str, era: str = "train", dataset: str = "mr_edge",
               token: str | None = None, root: Path = REPO_ROOT) -> pd.DataFrame:
    spec = DATASETS[dataset]
    if timeframe not in spec["timeframes"]:
        raise ValueError(f"{dataset} has timeframes {spec['timeframes']}, not {timeframe!r}")
    path = root / spec["dir"] / spec["pattern"].format(sym=_cache_name(symbol), tf=timeframe)
    # .pkl files here are trusted local research cache we generated ourselves
    # (reports/cache/mr_edge_*), not untrusted/external input.
    df = pd.read_pickle(path) if path.suffix == ".pkl" else pd.read_parquet(path)
    df = df[["open", "high", "low", "close", "volume"]].copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    return split_era(df, era, token)


def _mr_edge_1h_bounds(symbol: str, root: Path = REPO_ROOT) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Index bounds of this symbol's mr_edge 1h OHLCV cache — a metadata read (min/max of
    the index only) used to anchor the funding holdout boundary to the SAME boundary as
    price data. Deliberately does not go through load_ohlcv/split_era, so this can never
    be used as a backdoor to read holdout price rows."""
    spec = DATASETS["mr_edge"]
    path = root / spec["dir"] / spec["pattern"].format(sym=_cache_name(symbol), tf="1h")
    # trusted local research cache (see load_ohlcv) — read only for its index bounds.
    idx = pd.read_pickle(path).index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return idx.min(), idx.max()


def load_funding(symbol: str, era: str = "train", token: str | None = None, root: Path = REPO_ROOT) -> pd.DataFrame:
    path = root / DATASETS["mr_edge"]["dir"] / f"funding_{_cache_name(symbol)}.json"
    rows = json.loads(path.read_text())
    f = pd.DataFrame(rows)
    f["ts"] = pd.to_datetime(f["ts"], unit="ms", utc=True)
    f = f[["ts", "rate"]].sort_values("ts").reset_index(drop=True).set_index("ts")
    bounds = _mr_edge_1h_bounds(symbol, root)
    return split_era(f, era, token, bounds=bounds).reset_index()


def fetch_ohlcv_ccxt(symbol: str, timeframe: str, since_ms: int, until_ms: int, exchange_id: str = "phemex") -> pd.DataFrame:
    """Public OHLCV for horizons the caches don't cover (e.g. daily bars back years). Network."""
    import ccxt  # local import: optional dependency path
    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    market = f"{_cache_name(symbol).split('_')[0]}/USDT:USDT"
    out, since = [], since_ms
    while since < until_ms:
        batch = ex.fetch_ohlcv(market, timeframe, since=since, limit=1000)
        if not batch:
            break
        out.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    df = pd.DataFrame(out, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("ts").loc[: pd.Timestamp(until_ms, unit="ms", tz="UTC")]
