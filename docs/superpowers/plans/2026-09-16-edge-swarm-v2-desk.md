# Edge Swarm v2 ("the desk") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable multi-agent research desk under `research/swarm/` that starts from mechanisms, screens every thesis on data with shared, tested statistics before anyone opines, hands artifacts (not prose) between phases, and leaves a versioned knowledge base richer after every run; then run it once.

**Architecture:** A small tested Python library (`research/swarm/lib/`) does all statistics, data loading (with holdout refusal), spec freezing and screening. A knowledge base (`research/swarm/kb/`) is mandatory reading embedded in every agent prompt. A Workflow script (`research/swarm/workflows/desk.js`) orchestrates brief → analysts → gatekeeper → registrar → screen → audit → committee → report/critic/reconciler, using `pipeline()` per thesis and barriers only where cross-thesis context is required. A second script (`build.js`) turns a committee pass into a paper slot and stops at the owner's `/pre-restart-audit` gate.

**Tech Stack:** Python 3.14.3, pandas 2.3.3, numpy 2.4.2, pytest (repo `tests/`, run `python3 -m pytest -q`), ccxt 4.4.100 (optional longer history), Claude Code Workflow tool (plain JS scripts), git (`origin git@github.com:jonas0915/Phmex-S.git`).

**Spec:** `docs/superpowers/specs/2026-09-16-edge-swarm-v2-design.md`

## Global Constraints

- Capital basis **$200**; round-trip cost `c = 11.5 bps` (7.0 fees + 4.5 adverse selection); `p* = (x+c)/(2x)`; table: 25→73.0%, 50→61.5%, 100→55.8%, 300→51.9%, 1000→50.6%.
- Lot minimums (USD notional per lot): BTC 77.74, ETH 24.9738, SOL 1.0143, XRP 1.0044, DOGE 1.0010; `minOrderValueRv` = 1 USDT.
- Screens run **closed-bar**, **train era only**; holdout = final 25% of a dataset's time range; holdout readable only via an explicit committee token.
- Datasets: `reports/cache/mr_edge_20260601_20260903/` (35 syms × 1m/5m/1h pkl, index UTC 2026-06-01 → 2026-09-02 23:55, cols open/high/low/close/volume; `funding_<SYM>.json` list of `{ts, rate}`), `scripts/research/mr-universe-scan-2026-08-01/cache/<SYM>_USDT_USDT_{1h,5m}_400d.parquet` (19 syms, 1h 2025-06-27 → 2026-08-01).
- Bootstrap diff-CI: resample A and B independently, difference draw-order means, sort only the diffs (never sort each side first).
- Never modify bot trading code in the research stage. Build stage stops before any restart; owner runs `/pre-restart-audit`.
- Run the desk workflow **alone** (never concurrent with another workflow). Caps: 7 analysts, ≤5 screens.
- Every number in a report must trace to a file in `research/swarm/runs/<run_id>/`.
- Commit after each task; push `research/swarm/kb/` and `runs/` after each run. Never commit `.env` or raw data copies.
- All commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

---

## File map

Create:
- `research/__init__.py`, `research/swarm/__init__.py`, `research/swarm/lib/__init__.py` — packages
- `research/swarm/lib/fee_math.py` — p*, net bps, time-to-verdict, lot check, sizing
- `research/swarm/lib/bootstrap_ci.py` — mean CI, independent-resample diff CI
- `research/swarm/lib/load_data.py` — dataset loaders, era split, holdout refusal, funding, ccxt fetch
- `research/swarm/lib/registrar.py` — freeze spec + signal code with sha256; CLI
- `research/swarm/lib/screen.py` — causality check + closed-bar trade sim + `out.json`; CLI
- `research/swarm/lib/kb_check.py` — knowledge-base integrity checker; CLI
- `research/swarm/kb/{CONSTRAINTS,STANDARDS,DATA,DEAD_LIST,LESSONS,SURVIVORS}.md`
- `research/swarm/workflows/desk.js`, `research/swarm/workflows/build.js`
- `research/swarm/README.md`
- `tests/test_swarm_fee_math.py`, `tests/test_swarm_bootstrap_ci.py`, `tests/test_swarm_load_data.py`, `tests/test_swarm_registrar.py`, `tests/test_swarm_screen.py`, `tests/test_swarm_kb.py`

Modify:
- `.gitignore` — ignore `research/swarm/runs/*/screens/*/data*` and `research/swarm/runs/*/**/*.pkl`
- `CLAUDE.md` (Phmex-S) — one line pointing at `research/swarm/README.md` and the pull-before-read rule

---

### Task 1: Package scaffold + `fee_math`

**Files:**
- Create: `research/__init__.py`, `research/swarm/__init__.py`, `research/swarm/lib/__init__.py` (all empty)
- Create: `research/swarm/lib/fee_math.py`
- Test: `tests/test_swarm_fee_math.py`

**Interfaces:**
- Produces: `C_BPS: float = 11.5`, `FEES_RT_BPS = 7.0`, `ADVERSE_BPS = 4.5`, `LOT_MIN_USD: dict[str, float]`,
  `p_star(target_bps: float, cost_bps: float = C_BPS) -> float`,
  `net_bps(gross_bps: float, cost_bps: float = C_BPS) -> float`,
  `time_to_verdict_weeks(trades_per_week: float, n_required: int = 50) -> float`,
  `position_notional(capital_usd: float = 200.0, risk_frac: float = 0.10, leverage: int = 10) -> float`,
  `lot_check(symbol: str, notional_usd: float) -> dict` with keys `ok: bool, lots: int, lot_usd: float | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_swarm_fee_math.py
"""fee_math: the desk's single source of break-even arithmetic (spec §3)."""
import math
import pytest

from research.swarm.lib import fee_math as fm


@pytest.mark.parametrize("x,expected", [(25, 0.730), (50, 0.615), (100, 0.558), (300, 0.519), (1000, 0.506)])
def test_p_star_matches_spec_table(x, expected):
    assert round(fm.p_star(x), 3) == expected


def test_p_star_rejects_nonpositive_target():
    with pytest.raises(ValueError):
        fm.p_star(0)


def test_net_bps_subtracts_full_round_trip_cost():
    assert fm.net_bps(20.0) == pytest.approx(8.5)
    assert fm.C_BPS == pytest.approx(fm.FEES_RT_BPS + fm.ADVERSE_BPS)


def test_time_to_verdict_weeks():
    assert fm.time_to_verdict_weeks(10.0) == pytest.approx(5.0)
    assert math.isinf(fm.time_to_verdict_weeks(0.0))


def test_position_notional_default_is_200_dollars():
    # $200 capital, 10% margin at risk per position, 10x → $200 notional
    assert fm.position_notional() == pytest.approx(200.0)


def test_lot_check_btc_one_lot_at_200_notional():
    r = fm.lot_check("BTC", 200.0)
    assert r == {"ok": True, "lots": 2, "lot_usd": 77.74}


def test_lot_check_btc_fails_below_one_lot():
    r = fm.lot_check("BTC", 50.0)
    assert r["ok"] is False and r["lots"] == 0


def test_lot_check_unknown_symbol_uses_min_order_value():
    r = fm.lot_check("ZZZ", 5.0)
    assert r["ok"] is True and r["lot_usd"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_swarm_fee_math.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'research'`

- [ ] **Step 3: Implement**

```bash
mkdir -p research/swarm/lib && touch research/__init__.py research/swarm/__init__.py research/swarm/lib/__init__.py
```

```python
# research/swarm/lib/fee_math.py
"""Break-even arithmetic for the desk (spec §3). Every WR / time-to-verdict number
an agent reports must come from here, not from hand arithmetic."""
from __future__ import annotations

import math

FEES_RT_BPS = 7.0        # maker 0.01% + taker 0.06% per side (bot's real mix)
ADVERSE_BPS = 4.5        # measured post-fill adverse selection
C_BPS = FEES_RT_BPS + ADVERSE_BPS

# USD notional of one lot (Phemex USDT perps, 03_exchange_economics.md:57-68)
LOT_MIN_USD = {"BTC": 77.74, "ETH": 24.9738, "SOL": 1.0143, "XRP": 1.0044, "DOGE": 1.0010}
MIN_ORDER_VALUE_USD = 1.0


def p_star(target_bps: float, cost_bps: float = C_BPS) -> float:
    """Required win rate for a symmetric TP/SL of `target_bps` after round-trip cost."""
    if target_bps <= 0:
        raise ValueError("target_bps must be > 0")
    return (target_bps + cost_bps) / (2.0 * target_bps)


def net_bps(gross_bps: float, cost_bps: float = C_BPS) -> float:
    return gross_bps - cost_bps


def time_to_verdict_weeks(trades_per_week: float, n_required: int = 50) -> float:
    if trades_per_week <= 0:
        return math.inf
    return n_required / trades_per_week


def position_notional(capital_usd: float = 200.0, risk_frac: float = 0.10, leverage: int = 10) -> float:
    return capital_usd * risk_frac * leverage


def lot_check(symbol: str, notional_usd: float) -> dict:
    base = symbol.split("_")[0].split("/")[0].upper()
    lot_usd = LOT_MIN_USD.get(base)
    if lot_usd is None:
        return {"ok": notional_usd >= MIN_ORDER_VALUE_USD, "lots": int(notional_usd // MIN_ORDER_VALUE_USD), "lot_usd": None}
    lots = int(notional_usd // lot_usd)
    return {"ok": lots >= 1, "lots": lots, "lot_usd": lot_usd}
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_swarm_fee_math.py -q`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add research/__init__.py research/swarm/__init__.py research/swarm/lib/__init__.py research/swarm/lib/fee_math.py tests/test_swarm_fee_math.py
git commit -m "feat(swarm): fee_math — p*, net bps, time-to-verdict, lot check (\$200 basis)

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `bootstrap_ci`

**Files:**
- Create: `research/swarm/lib/bootstrap_ci.py`
- Test: `tests/test_swarm_bootstrap_ci.py`

**Interfaces:**
- Produces: `mean_ci(x, n_boot=2000, alpha=0.05, seed=0) -> tuple[float, float]`,
  `diff_ci(a, b, n_boot=2000, alpha=0.05, seed=0) -> tuple[float, float]`,
  `_buggy_diff_ci_sort_first(a, b, n_boot, alpha, seed)` (kept only as the regression oracle; underscore-private).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_swarm_bootstrap_ci.py
"""bootstrap_ci: correct independent-resample diff CI (feedback_bootstrap_diff_ci)."""
import numpy as np
import pytest

from research.swarm.lib import bootstrap_ci as bc


def test_mean_ci_contains_true_mean_and_is_ordered():
    rng = np.random.default_rng(1)
    x = rng.normal(5.0, 1.0, size=400)
    lo, hi = bc.mean_ci(x, n_boot=1000, seed=1)
    assert lo < 5.0 < hi and lo < hi


def test_mean_ci_empty_input_raises():
    with pytest.raises(ValueError):
        bc.mean_ci(np.array([]))


def test_diff_ci_contains_true_shift():
    rng = np.random.default_rng(2)
    a = rng.normal(0.0, 1.0, size=300)
    b = rng.normal(0.5, 1.0, size=300)
    lo, hi = bc.diff_ci(b, a, n_boot=1000, seed=2)
    assert lo < 0.5 < hi


def test_diff_ci_excludes_zero_for_clear_effect():
    rng = np.random.default_rng(3)
    a = rng.normal(0.0, 1.0, size=500)
    b = rng.normal(1.0, 1.0, size=500)
    lo, hi = bc.diff_ci(b, a, n_boot=1000, seed=3)
    assert lo > 0.0


def test_sort_first_bug_is_narrower_than_correct_ci():
    """Regression anchor: sorting each side before differencing shrinks the CI ~2x.
    The correct CI must be materially wider than the buggy one."""
    rng = np.random.default_rng(4)
    a = rng.normal(0.0, 1.0, size=200)
    b = rng.normal(0.0, 1.0, size=200)
    lo_ok, hi_ok = bc.diff_ci(a, b, n_boot=2000, seed=4)
    lo_bad, hi_bad = bc._buggy_diff_ci_sort_first(a, b, n_boot=2000, alpha=0.05, seed=4)
    assert (hi_ok - lo_ok) > 1.5 * (hi_bad - lo_bad)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_swarm_bootstrap_ci.py -q`
Expected: FAIL with `cannot import name 'bootstrap_ci'` / ModuleNotFoundError

- [ ] **Step 3: Implement**

```python
# research/swarm/lib/bootstrap_ci.py
"""Percentile bootstrap CIs. diff_ci resamples A and B INDEPENDENTLY, differences the
draw-order means, and sorts only the diffs — the record's documented bug is sorting
each side first (2.4x too-narrow CI). Keep _buggy_* only as a regression oracle."""
from __future__ import annotations

import numpy as np


def _as_array(x) -> np.ndarray:
    arr = np.asarray(x, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError("empty sample")
    return arr


def mean_ci(x, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    arr = _as_array(x)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(n_boot, arr.size))
    means = arr[idx].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def diff_ci(a, b, n_boot: int = 2000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    """CI for mean(a) - mean(b)."""
    a_arr, b_arr = _as_array(a), _as_array(b)
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, a_arr.size, size=(n_boot, a_arr.size))
    ib = rng.integers(0, b_arr.size, size=(n_boot, b_arr.size))
    diffs = a_arr[ia].mean(axis=1) - b_arr[ib].mean(axis=1)   # draw-order pairing
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])   # sort ONLY the diffs
    return float(lo), float(hi)


def _buggy_diff_ci_sort_first(a, b, n_boot: int, alpha: float, seed: int) -> tuple[float, float]:
    """DO NOT USE. The historical bug: sort each side's bootstrap means, then difference."""
    a_arr, b_arr = _as_array(a), _as_array(b)
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, a_arr.size, size=(n_boot, a_arr.size))
    ib = rng.integers(0, b_arr.size, size=(n_boot, b_arr.size))
    diffs = np.sort(a_arr[ia].mean(axis=1)) - np.sort(b_arr[ib].mean(axis=1))
    lo, hi = np.quantile(diffs, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_swarm_bootstrap_ci.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add research/swarm/lib/bootstrap_ci.py tests/test_swarm_bootstrap_ci.py
git commit -m "feat(swarm): bootstrap_ci with sort-first regression oracle

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `load_data` with era split and holdout refusal

**Files:**
- Create: `research/swarm/lib/load_data.py`
- Test: `tests/test_swarm_load_data.py`

**Interfaces:**
- Produces: `REPO_ROOT: Path`, `DATASETS: dict[str, dict]` (`mr_edge`, `long_1h`), `COMMITTEE_TOKEN = "COMMITTEE-HOLDOUT-READ"`, `class HoldoutError(PermissionError)`,
  `holdout_start(t0, t1, frac=0.25) -> pd.Timestamp`,
  `split_era(df, era, token=None, frac=0.25) -> pd.DataFrame`,
  `list_symbols(dataset="mr_edge") -> list[str]`,
  `load_ohlcv(symbol, timeframe, era="train", dataset="mr_edge", token=None, root=REPO_ROOT) -> pd.DataFrame`,
  `load_funding(symbol, root=REPO_ROOT) -> pd.DataFrame` (cols `ts` UTC datetime, `rate`),
  `fetch_ohlcv_ccxt(symbol, timeframe, since_ms, until_ms, exchange_id="phemex") -> pd.DataFrame` (network; untested).
- Symbols are the bare base (`"ETH"`) or the cache name (`"ETH_USDT_USDT"`); both accepted.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_swarm_load_data.py
"""load_data: era split + holdout refusal. Real-cache tests skip when the cache is absent."""
import numpy as np
import pandas as pd
import pytest

from research.swarm.lib import load_data as ld


def _frame(n=100, start="2026-01-01", freq="1h"):
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    v = np.linspace(100, 110, n)
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1, "close": v, "volume": 1.0}, index=idx)


def test_holdout_start_is_last_quarter():
    t0, t1 = pd.Timestamp("2026-06-01", tz="UTC"), pd.Timestamp("2026-09-02 23:55", tz="UTC")
    hs = ld.holdout_start(t0, t1)
    assert pd.Timestamp("2026-08-10", tz="UTC") <= hs <= pd.Timestamp("2026-08-11", tz="UTC")


def test_split_era_train_excludes_holdout_rows():
    df = _frame(100)
    train = ld.split_era(df, "train")
    assert len(train) == 75 and train.index.max() < ld.holdout_start(df.index.min(), df.index.max())


def test_split_era_holdout_requires_token():
    df = _frame(100)
    with pytest.raises(ld.HoldoutError):
        ld.split_era(df, "holdout")
    with pytest.raises(ld.HoldoutError):
        ld.split_era(df, "all")
    hold = ld.split_era(df, "holdout", token=ld.COMMITTEE_TOKEN)
    assert len(hold) == 25 and len(ld.split_era(df, "all", token=ld.COMMITTEE_TOKEN)) == 100


def test_split_era_rejects_unknown_era():
    with pytest.raises(ValueError):
        ld.split_era(_frame(10), "test")


def test_symbol_normalisation():
    assert ld._cache_name("ETH") == "ETH_USDT_USDT"
    assert ld._cache_name("ETH_USDT_USDT") == "ETH_USDT_USDT"
    assert ld._cache_name("ETH/USDT:USDT") == "ETH_USDT_USDT"


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_real_mr_edge_train_never_reaches_september():
    df = ld.load_ohlcv("ETH", "5m", era="train")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.tz is not None and df.index.max() < pd.Timestamp("2026-08-11", tz="UTC")


@pytest.mark.skipif(not (ld.REPO_ROOT / ld.DATASETS["mr_edge"]["dir"]).exists(), reason="mr_edge cache absent")
def test_real_funding_schema():
    f = ld.load_funding("ETH")
    assert list(f.columns) == ["ts", "rate"] and f["ts"].dt.tz is not None and len(f) > 100
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_swarm_load_data.py -q`
Expected: FAIL with ModuleNotFoundError / cannot import `load_data`

- [ ] **Step 3: Implement**

```python
# research/swarm/lib/load_data.py
"""Dataset loaders with a hard era split. Screens call era='train'. Holdout rows are
refused without the committee token — the token is not a secret, it is a deliberate,
greppable act (spec §5 step 4)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

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
    base = symbol.replace("/", "_").replace(":", "_").split("_")[0].upper()
    return f"{base}_USDT_USDT"


def holdout_start(t0: pd.Timestamp, t1: pd.Timestamp, frac: float = 0.25) -> pd.Timestamp:
    return t1 - (t1 - t0) * frac


def split_era(df: pd.DataFrame, era: str, token: str | None = None, frac: float = 0.25) -> pd.DataFrame:
    if era not in ("train", "holdout", "all"):
        raise ValueError(f"era must be train|holdout|all, got {era!r}")
    hs = holdout_start(df.index.min(), df.index.max(), frac)
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
    df = pd.read_pickle(path) if path.suffix == ".pkl" else pd.read_parquet(path)
    df = df[["open", "high", "low", "close", "volume"]].copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.sort_index()
    return split_era(df, era, token)


def load_funding(symbol: str, root: Path = REPO_ROOT) -> pd.DataFrame:
    path = root / DATASETS["mr_edge"]["dir"] / f"funding_{_cache_name(symbol)}.json"
    rows = json.loads(path.read_text())
    f = pd.DataFrame(rows)
    f["ts"] = pd.to_datetime(f["ts"], unit="ms", utc=True)
    return f[["ts", "rate"]].sort_values("ts").reset_index(drop=True)


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
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_swarm_load_data.py -q`
Expected: 7 passed (the two real-cache tests run on this Mac because the cache exists)

- [ ] **Step 5: Commit**

```bash
git add research/swarm/lib/load_data.py tests/test_swarm_load_data.py
git commit -m "feat(swarm): load_data — era split, holdout refusal, funding, ccxt fetch

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `registrar` — freeze spec + signal code

**Files:**
- Create: `research/swarm/lib/registrar.py`
- Test: `tests/test_swarm_registrar.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `REQUIRED_SPEC_KEYS`, `SPEC_KEYS_INNER`,
  `validate(thesis: dict) -> list[str]` (empty list = valid),
  `freeze(thesis: dict, run_dir: Path, frozen_at: str) -> Path` — writes `run_dir/specs/<id>.frozen.json` and `run_dir/screens/<id>/signal.py`, returns frozen path,
  `verify(frozen_path: Path) -> bool`,
  CLI: `python3 -m research.swarm.lib.registrar <thesis.json> <run_dir> <frozen_at_iso>` prints the frozen path.
- Thesis JSON shape (analysts produce this; gatekeeper passes it through unchanged):

```json
{"id": "snake_case_id", "lens": "forced_flows", "mechanism": "...", "counterparty": "...",
 "prediction": "...", "nearest_dead_rows": [{"row": 25, "why_different": "..."}],
 "spec": {"dataset": "mr_edge", "universe": ["ETH", "SOL"], "timeframe": "1h",
          "tp_bps": 120, "sl_bps": 120, "max_hold_bars": 24,
          "expected_trades_per_week": 6, "doa_line": "train CI95 upper < 0 → dead"},
 "signal_py": "import pandas as pd\ndef signals(df):\n    ...return pd.Series(...)"}
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_swarm_registrar.py
import json
from pathlib import Path

import pytest

from research.swarm.lib import registrar as rg

GOOD = {
    "id": "demo_thesis", "lens": "literature", "mechanism": "m", "counterparty": "c", "prediction": "p",
    "nearest_dead_rows": [{"row": 1, "why_different": "x"}],
    "spec": {"dataset": "mr_edge", "universe": ["ETH"], "timeframe": "1h", "tp_bps": 100, "sl_bps": 100,
             "max_hold_bars": 24, "expected_trades_per_week": 5, "doa_line": "train CI95 upper < 0 → dead"},
    "signal_py": "import pandas as pd\ndef signals(df):\n    return pd.Series(0, index=df.index)\n",
}


def test_validate_good_thesis_has_no_errors():
    assert rg.validate(GOOD) == []


def test_validate_reports_missing_keys_and_bad_id():
    bad = {**GOOD, "id": "Bad Id!", "spec": {k: v for k, v in GOOD["spec"].items() if k != "doa_line"}}
    errs = rg.validate(bad)
    assert any("doa_line" in e for e in errs) and any("id" in e for e in errs)


def test_freeze_writes_spec_and_signal_and_verifies(tmp_path: Path):
    p = rg.freeze(GOOD, tmp_path, "2026-09-16T20:00:00Z")
    frozen = json.loads(p.read_text())
    assert frozen["sha256"] and frozen["frozen_at"] == "2026-09-16T20:00:00Z"
    assert (tmp_path / "screens" / "demo_thesis" / "signal.py").read_text() == GOOD["signal_py"]
    assert rg.verify(p) is True


def test_freeze_is_deterministic_and_tamper_evident(tmp_path: Path):
    p1 = rg.freeze(GOOD, tmp_path / "a", "t")
    p2 = rg.freeze(GOOD, tmp_path / "b", "t")
    assert json.loads(p1.read_text())["sha256"] == json.loads(p2.read_text())["sha256"]
    d = json.loads(p1.read_text()); d["thesis"]["spec"]["tp_bps"] = 999
    p1.write_text(json.dumps(d))
    assert rg.verify(p1) is False


def test_freeze_refuses_invalid_thesis(tmp_path: Path):
    with pytest.raises(ValueError):
        rg.freeze({**GOOD, "signal_py": ""}, tmp_path, "t")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_swarm_registrar.py -q`
Expected: FAIL, cannot import `registrar`

- [ ] **Step 3: Implement**

```python
# research/swarm/lib/registrar.py
"""Freeze a thesis (spec + signal code) with a sha256 BEFORE any data is read (spec §5 step 4).
Deterministic: canonical JSON, sorted keys. Tamper-evident: verify() recomputes the hash."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED_SPEC_KEYS = ("id", "lens", "mechanism", "counterparty", "prediction", "nearest_dead_rows", "spec", "signal_py")
SPEC_KEYS_INNER = ("dataset", "universe", "timeframe", "tp_bps", "sl_bps", "max_hold_bars", "expected_trades_per_week", "doa_line")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


def validate(thesis: dict) -> list[str]:
    errs = [f"missing key {k!r}" for k in REQUIRED_SPEC_KEYS if k not in thesis]
    if "id" in thesis and not _ID_RE.match(str(thesis["id"])):
        errs.append("id must be snake_case [a-z0-9_], 3-41 chars")
    spec = thesis.get("spec") or {}
    errs += [f"spec missing {k!r}" for k in SPEC_KEYS_INNER if k not in spec]
    if not str(thesis.get("signal_py", "")).strip() or "def signals(" not in str(thesis.get("signal_py", "")):
        errs.append("signal_py must define signals(df)")
    if isinstance(spec.get("universe"), list) and not spec["universe"]:
        errs.append("spec.universe is empty")
    return errs


def _canonical(thesis: dict) -> str:
    return json.dumps(thesis, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def freeze(thesis: dict, run_dir: Path, frozen_at: str) -> Path:
    errs = validate(thesis)
    if errs:
        raise ValueError("; ".join(errs))
    run_dir = Path(run_dir)
    sha = hashlib.sha256(_canonical(thesis).encode()).hexdigest()
    specs, screen = run_dir / "specs", run_dir / "screens" / thesis["id"]
    specs.mkdir(parents=True, exist_ok=True); screen.mkdir(parents=True, exist_ok=True)
    (screen / "signal.py").write_text(thesis["signal_py"])
    out = specs / f"{thesis['id']}.frozen.json"
    out.write_text(json.dumps({"thesis": thesis, "sha256": sha, "frozen_at": frozen_at}, indent=2, sort_keys=True))
    return out


def verify(frozen_path: Path) -> bool:
    d = json.loads(Path(frozen_path).read_text())
    return hashlib.sha256(_canonical(d["thesis"]).encode()).hexdigest() == d.get("sha256")


if __name__ == "__main__":
    thesis_path, run_dir, frozen_at = sys.argv[1], sys.argv[2], sys.argv[3]
    print(freeze(json.loads(Path(thesis_path).read_text()), Path(run_dir), frozen_at))
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_swarm_registrar.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add research/swarm/lib/registrar.py tests/test_swarm_registrar.py
git commit -m "feat(swarm): registrar — freeze thesis spec + signal with sha256

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `screen` — causality check, closed-bar simulator, `out.json`

**Files:**
- Create: `research/swarm/lib/screen.py`
- Test: `tests/test_swarm_screen.py`

**Interfaces:**
- Consumes: `load_data.load_ohlcv`, `load_data.split_era`, `bootstrap_ci.mean_ci`, `fee_math.{p_star, C_BPS, time_to_verdict_weeks, lot_check, position_notional}`, `registrar.verify`.
- Produces: `class LookaheadError(Exception)`,
  `load_signal_fn(signal_path: Path)` → callable `signals(df) -> pd.Series` in {-1,0,1},
  `causality_check(signals_fn, df, n_points=12, seed=0) -> None` (raises `LookaheadError`),
  `simulate(df, sig, tp_bps, sl_bps, max_hold_bars, cost_bps=C_BPS) -> pd.DataFrame` (one row per trade: `entry_ts, exit_ts, side, entry, exit, gross_bps, net_bps, exit_reason`),
  `run_screen(frozen_path: Path, run_dir: Path, era="train", token=None) -> dict` — writes `run_dir/screens/<id>/out.json` and `trades.csv`, returns the dict,
  CLI: `python3 -m research.swarm.lib.screen <frozen.json> <run_dir> [--era train]`.
- `out.json` keys: `id, spec_sha256, era, n, net_bps_mean, ci95, wr, p_star, trades_per_week, time_to_verdict_weeks, lot_check, per_symbol {sym: n}, train_span [start,end], causality: "PASS", signal_sha256`.
- Simulation rules (frozen): signal on closed bar `i` → enter at `open[i+1]`; per later bar check SL then TP on `low/high` (SL wins ties, conservative); `max_hold_bars` → exit at that bar's close; one position per symbol at a time; `gross_bps = side*(exit/entry-1)*1e4`; `net_bps = gross_bps - cost_bps`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_swarm_screen.py
"""screen: catches lookahead, simulates closed-bar trades, finds a planted edge, writes out.json."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.swarm.lib import registrar as rg
from research.swarm.lib import screen as sc


def _frame(n=600, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    o = np.r_[close[0], close[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, close) * 1.001, "low": np.minimum(o, close) * 0.999,
                         "close": close, "volume": 1.0}, index=idx)


CAUSAL = "import pandas as pd\ndef signals(df):\n    return ((df.close > df.close.shift(1)).astype(int)).where(df.index.hour == 0, 0)\n"
LOOKAHEAD = "import pandas as pd\ndef signals(df):\n    return (df.close.shift(-1) > df.close).astype(int)\n"


def _thesis(sig, tp=100, sl=100, hold=6, uni=("ETH",)):
    return {"id": "t_demo", "lens": "x", "mechanism": "m", "counterparty": "c", "prediction": "p",
            "nearest_dead_rows": [], "signal_py": sig,
            "spec": {"dataset": "mr_edge", "universe": list(uni), "timeframe": "1h", "tp_bps": tp, "sl_bps": sl,
                     "max_hold_bars": hold, "expected_trades_per_week": 3, "doa_line": "train CI95 upper < 0 → dead"}}


def test_causality_check_passes_causal_and_fails_lookahead(tmp_path: Path):
    df = _frame()
    ok = sc.load_signal_fn(_write(tmp_path, "ok.py", CAUSAL))
    sc.causality_check(ok, df)
    bad = sc.load_signal_fn(_write(tmp_path, "bad.py", LOOKAHEAD))
    with pytest.raises(sc.LookaheadError):
        sc.causality_check(bad, df)


def _write(d: Path, name: str, code: str) -> Path:
    p = d / name; p.write_text(code); return p


def test_simulate_enters_next_open_and_sl_wins_ties():
    idx = pd.date_range("2026-01-01", periods=5, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": [100, 100, 100, 100, 100], "high": [100, 100, 103, 100, 100],
                       "low": [100, 100, 97, 100, 100], "close": [100, 100, 100, 100, 100], "volume": 1}, index=idx)
    sig = pd.Series([0, 1, 0, 0, 0], index=idx)
    trades = sc.simulate(df, sig, tp_bps=200, sl_bps=200, max_hold_bars=3, cost_bps=11.5)
    assert len(trades) == 1
    t = trades.iloc[0]
    assert t.entry_ts == idx[2] and t.entry == 100 and t.exit_reason == "SL" and t.gross_bps == pytest.approx(-200)
    assert t.net_bps == pytest.approx(-211.5)


def test_simulate_max_hold_exits_at_close_and_one_position_per_symbol():
    idx = pd.date_range("2026-01-01", periods=6, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": [100] * 6, "high": [100.5] * 6, "low": [99.5] * 6, "close": [100, 100, 100, 101, 100, 100], "volume": 1}, index=idx)
    sig = pd.Series([1, 1, 1, 0, 0, 0], index=idx)
    trades = sc.simulate(df, sig, tp_bps=500, sl_bps=500, max_hold_bars=2, cost_bps=0)
    assert len(trades) == 1 and trades.iloc[0].exit_reason == "TIME" and trades.iloc[0].gross_bps == pytest.approx(100)


def test_run_screen_finds_planted_edge_and_writes_out_json(tmp_path: Path, monkeypatch):
    # plant: after a down bar at hour 0, price rises 0.5% over the next 3 bars
    df = _frame(800, seed=5)
    mask = (df.index.hour == 0) & (df.close < df.close.shift(1))
    bump = pd.Series(0.0, index=df.index)
    for ts in df.index[mask]:
        loc = df.index.get_loc(ts)
        bump.iloc[loc + 1: loc + 4] += 0.0017
    factor = np.exp(bump.cumsum())
    for c in ("open", "high", "low", "close"):
        df[c] = df[c] * factor
    sig_code = "import pandas as pd\ndef signals(df):\n    return ((df.close < df.close.shift(1)) & (df.index.hour == 0)).astype(int)\n"
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda symbol, timeframe, era="train", dataset="mr_edge", token=None, root=None: sc.ld.split_era(df, era, token))
    frozen = rg.freeze(_thesis(sig_code, tp=60, sl=60, hold=3), tmp_path, "t")
    out = sc.run_screen(frozen, tmp_path)
    assert out["causality"] == "PASS" and out["n"] > 15 and out["net_bps_mean"] > 0
    saved = json.loads((tmp_path / "screens" / "t_demo" / "out.json").read_text())
    assert saved["ci95"][0] < saved["net_bps_mean"] < saved["ci95"][1] and saved["p_star"] == pytest.approx((60 + 11.5) / 120)
    assert (tmp_path / "screens" / "t_demo" / "trades.csv").exists()


def test_run_screen_refuses_lookahead_signal(tmp_path: Path, monkeypatch):
    df = _frame(300, seed=6)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(LOOKAHEAD), tmp_path, "t")
    with pytest.raises(sc.LookaheadError):
        sc.run_screen(frozen, tmp_path)


def test_run_screen_refuses_holdout_without_token(tmp_path: Path, monkeypatch):
    df = _frame(300, seed=7)
    monkeypatch.setattr(sc.ld, "load_ohlcv", lambda *a, **k: sc.ld.split_era(df, k.get("era", "train"), k.get("token")))
    frozen = rg.freeze(_thesis(CAUSAL), tmp_path, "t")
    with pytest.raises(sc.ld.HoldoutError):
        sc.run_screen(frozen, tmp_path, era="holdout")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_swarm_screen.py -q`
Expected: FAIL, cannot import `screen`

- [ ] **Step 3: Implement**

```python
# research/swarm/lib/screen.py
"""Pre-registered screen runner (spec §5 step 5). Reads a FROZEN spec, refuses tampering,
refuses lookahead (causality check), simulates closed-bar trades with the desk's cost model,
and writes out.json — the only artifact downstream phases are allowed to cite."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import bootstrap_ci as bc
from . import fee_math as fm
from . import load_data as ld
from . import registrar as rg


class LookaheadError(Exception):
    pass


def load_signal_fn(signal_path: Path):
    spec = importlib.util.spec_from_file_location(f"sig_{signal_path.stem}_{abs(hash(str(signal_path)))}", signal_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.signals


def causality_check(signals_fn, df: pd.DataFrame, n_points: int = 12, seed: int = 0) -> None:
    """signals(df)[i] must equal signals(df[:i+1])[i] — a signal may not depend on later bars."""
    full = signals_fn(df).fillna(0).astype(int)
    rng = np.random.default_rng(seed)
    pts = rng.integers(max(50, len(df) // 10), len(df) - 1, size=n_points)
    for i in pts:
        trunc = signals_fn(df.iloc[: i + 1]).fillna(0).astype(int)
        if int(trunc.iloc[-1]) != int(full.iloc[i]):
            raise LookaheadError(f"signal at {df.index[i]} changes when future bars are removed")


def simulate(df: pd.DataFrame, sig: pd.Series, tp_bps: float, sl_bps: float, max_hold_bars: int,
             cost_bps: float = fm.C_BPS) -> pd.DataFrame:
    o, h, l, c = df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    s = sig.reindex(df.index).fillna(0).astype(int).to_numpy()
    rows, i, n = [], 0, len(df)
    while i < n - 1:
        side = int(s[i])
        if side == 0:
            i += 1; continue
        entry_i, entry = i + 1, o[i + 1]
        tp = entry * (1 + side * tp_bps / 1e4)
        sl = entry * (1 - side * sl_bps / 1e4)
        exit_i, exit_px, reason = None, None, None
        last = min(entry_i + max_hold_bars, n - 1)
        for j in range(entry_i, last + 1):
            hit_sl = l[j] <= sl if side == 1 else h[j] >= sl
            hit_tp = h[j] >= tp if side == 1 else l[j] <= tp
            if hit_sl:                       # SL first on ties — conservative
                exit_i, exit_px, reason = j, sl, "SL"; break
            if hit_tp:
                exit_i, exit_px, reason = j, tp, "TP"; break
            if j == last:
                exit_i, exit_px, reason = j, c[j], "TIME"
        if exit_i is None:
            break
        gross = side * (exit_px / entry - 1) * 1e4
        rows.append({"entry_ts": df.index[entry_i], "exit_ts": df.index[exit_i], "side": side, "entry": float(entry),
                     "exit": float(exit_px), "gross_bps": float(gross), "net_bps": float(gross - cost_bps), "exit_reason": reason})
        i = exit_i + 1                        # one position per symbol at a time
    return pd.DataFrame(rows, columns=["entry_ts", "exit_ts", "side", "entry", "exit", "gross_bps", "net_bps", "exit_reason"])


def run_screen(frozen_path: Path, run_dir: Path, era: str = "train", token: str | None = None) -> dict:
    frozen_path, run_dir = Path(frozen_path), Path(run_dir)
    if not rg.verify(frozen_path):
        raise ValueError(f"frozen spec failed sha verification: {frozen_path}")
    frozen = json.loads(frozen_path.read_text())
    th, spec = frozen["thesis"], frozen["thesis"]["spec"]
    sdir = run_dir / "screens" / th["id"]
    signal_path = sdir / "signal.py"
    if signal_path.read_text() != th["signal_py"]:
        raise ValueError("signal.py differs from frozen signal_py")
    signals_fn = load_signal_fn(signal_path)

    frames, all_trades, per_symbol = {}, [], {}
    for sym in spec["universe"]:
        df = ld.load_ohlcv(sym, spec["timeframe"], era=era, dataset=spec["dataset"], token=token)
        frames[sym] = df
    first_sym = spec["universe"][0]
    causality_check(signals_fn, frames[first_sym])
    for sym, df in frames.items():
        sig = signals_fn(df).fillna(0).astype(int)
        tr = simulate(df, sig, spec["tp_bps"], spec["sl_bps"], spec["max_hold_bars"])
        tr.insert(0, "symbol", sym)
        per_symbol[sym] = int(len(tr))
        all_trades.append(tr)
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    n = int(len(trades))
    span_start = min(df.index.min() for df in frames.values()); span_end = max(df.index.max() for df in frames.values())
    weeks = max((span_end - span_start).total_seconds() / (7 * 86400), 1e-9)
    notional = fm.position_notional()
    out = {
        "id": th["id"], "spec_sha256": frozen["sha256"], "era": era, "n": n,
        "net_bps_mean": float(trades["net_bps"].mean()) if n else None,
        "ci95": list(bc.mean_ci(trades["net_bps"].to_numpy())) if n >= 2 else None,
        "wr": float((trades["net_bps"] > 0).mean()) if n else None,
        "p_star": fm.p_star(spec["tp_bps"]),
        "trades_per_week": n / weeks,
        "time_to_verdict_weeks": fm.time_to_verdict_weeks(n / weeks),
        "lot_check": {sym: fm.lot_check(sym, notional) for sym in spec["universe"]},
        "per_symbol": per_symbol,
        "train_span": [str(span_start), str(span_end)],
        "causality": "PASS",
        "signal_sha256": hashlib.sha256(th["signal_py"].encode()).hexdigest(),
    }
    sdir.mkdir(parents=True, exist_ok=True)
    trades.to_csv(sdir / "trades.csv", index=False)
    (sdir / "out.json").write_text(json.dumps(out, indent=2, default=str))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("frozen"); ap.add_argument("run_dir"); ap.add_argument("--era", default="train"); ap.add_argument("--token", default=None)
    a = ap.parse_args()
    print(json.dumps(run_screen(Path(a.frozen), Path(a.run_dir), a.era, a.token), indent=2, default=str))
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_swarm_screen.py -q`
Expected: 6 passed. If `test_run_screen_finds_planted_edge_and_writes_out_json` is flaky on `n > 15`, lower to `n > 10` — the planted bump is deterministic (seed 5), so a failure means a simulator bug, not noise.

- [ ] **Step 5: Run the whole swarm suite + the repo suite for regressions**

Run: `python3 -m pytest tests/test_swarm_*.py -q && python3 -m pytest -q 2>&1 | tail -3`
Expected: all swarm tests pass; repo suite unchanged from baseline (1005 pass / 1 known ordering-only fail).

- [ ] **Step 6: Commit**

```bash
git add research/swarm/lib/screen.py tests/test_swarm_screen.py
git commit -m "feat(swarm): screen — causality check, closed-bar sim, out.json artifact

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Knowledge base + `kb_check`

**Files:**
- Create: `research/swarm/kb/CONSTRAINTS.md`, `STANDARDS.md`, `DATA.md`, `DEAD_LIST.md`, `LESSONS.md`, `SURVIVORS.md`
- Create: `research/swarm/lib/kb_check.py`
- Test: `tests/test_swarm_kb.py`

**Interfaces:**
- Produces: `kb_check.check(kb_dir: Path, root: Path) -> list[str]` (problems; empty = OK); CLI `python3 -m research.swarm.lib.kb_check`.
- `DEAD_LIST.md` row format (one per line, machine-checkable): `| <int row> | <family> | <one-line why dead> | <source file or memory ref> | <date YYYY-MM-DD> |`. Row numbers unique and ascending.
- `DATA.md` must mention every path in `load_data.DATASETS` and each must exist.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_swarm_kb.py
from pathlib import Path

from research.swarm.lib import kb_check, load_data as ld

KB = ld.REPO_ROOT / "research" / "swarm" / "kb"


def test_kb_files_exist_and_pass_integrity():
    problems = kb_check.check(KB, ld.REPO_ROOT)
    assert problems == [], "\n".join(problems)


def test_dead_list_has_at_least_the_v1_rows_and_memory_kills():
    rows = kb_check.dead_rows(KB / "DEAD_LIST.md")
    assert len(rows) >= 90                      # 76 v1 rows + ≥14 memory-reference kills
    assert len({r[0] for r in rows}) == len(rows)


def test_constraints_carry_the_p_star_table_and_capital():
    txt = (KB / "CONSTRAINTS.md").read_text()
    for needle in ("$200", "11.5", "73.0%", "61.5%", "55.8%", "51.9%", "50.6%", "77.74", "5-min"):
        assert needle in txt, needle
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_swarm_kb.py -q`
Expected: FAIL (module/files missing)

- [ ] **Step 3: Implement `kb_check.py`**

```python
# research/swarm/lib/kb_check.py
"""Knowledge-base integrity: files present, DEAD_LIST rows well-formed and unique,
DATA.md names every dataset path and each path exists. Run before every desk run."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from . import load_data as ld

REQUIRED = ("CONSTRAINTS.md", "STANDARDS.md", "DATA.md", "DEAD_LIST.md", "LESSONS.md", "SURVIVORS.md")
_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*$")


def dead_rows(path: Path) -> list[tuple[int, str, str, str, str]]:
    rows = []
    for line in path.read_text().splitlines():
        m = _ROW.match(line)
        if m:
            rows.append((int(m.group(1)), m.group(2), m.group(3), m.group(4), m.group(5)))
    return rows


def check(kb_dir: Path, root: Path) -> list[str]:
    problems = [f"missing {f}" for f in REQUIRED if not (kb_dir / f).exists()]
    if problems:
        return problems
    rows = dead_rows(kb_dir / "DEAD_LIST.md")
    nums = [r[0] for r in rows]
    if len(set(nums)) != len(nums):
        problems.append("DEAD_LIST.md has duplicate row numbers")
    if nums != sorted(nums):
        problems.append("DEAD_LIST.md rows not ascending")
    data_txt = (kb_dir / "DATA.md").read_text()
    for name, spec in ld.DATASETS.items():
        if spec["dir"] not in data_txt:
            problems.append(f"DATA.md does not mention {spec['dir']} ({name})")
        if not (root / spec["dir"]).exists():
            problems.append(f"dataset path missing on disk: {spec['dir']}")
    return problems


if __name__ == "__main__":
    kb = ld.REPO_ROOT / "research" / "swarm" / "kb"
    probs = check(kb, ld.REPO_ROOT)
    print("\n".join(probs) if probs else "KB OK")
    sys.exit(1 if probs else 0)
```

- [ ] **Step 4: Write `CONSTRAINTS.md`** (content is mandatory reading; embed verbatim in agent prompts)

```markdown
# CONSTRAINTS — read before anything else

## Capital and sizing
- Design basis **$200**. Position sizing for screens: `fee_math.position_notional()` = $200 notional (10% margin at 10x). Two paper slots max at this size; no cross-sectional baskets.
- Lot minimums (USD notional per lot): BTC **77.74**, ETH 24.97, SOL 1.01, XRP 1.00, DOGE 1.00. `minOrderValueRv` 1 USDT. Check with `fee_math.lot_check`.

## Costs (never re-derive by hand — use `fee_math`)
- Fees VIP-0: maker 0.01%, taker 0.06%. Bot's real mix = maker entry / taker exit = **7.0 bps** round trip.
- Measured adverse selection after fill: **4.5 bps**. Total `c = 11.5 bps`.
- Required win rate for symmetric TP/SL `x`: `p* = (x + c) / 2x` → 25 bps **73.0%**, 50 **61.5%**, 100 **55.8%**, 300 **51.9%**, 1000 **50.6%**. Scalping is fee-trapped: sub-0.1% moves cannot pay.
- Funding every 8h; BTC ≈ +0.01%/8h; meme perps often negative. Any hold > 8h must account for it.

## Execution reality of the Phmex-S bot
- **5-min poller** — no sub-minute reaction. Entries are maker limit orders (real maker fill ≈ 27%, and misses are adversely selected); exits taker.
- Order book snapshots every 60s, depth 5, BTC/ETH/INJ/ARB only. No streaming book.
- The Mac may sleep; slow horizons (hours–days) tolerate that, 5-min horizons do not.
- Paper slots run on the live feed with a `.paper` sentinel; graded daily 6 AM PT by `scripts/lab_adjudicator/adjudicate.py`; kill via `touch .kill_<slot>`.

## What "viable" means for this desk
1. Train-era screen: n ≥ 30 and bootstrap CI95 of net bps excludes 0 (after `c`).
2. Observed WR ≥ p* for the spec's TP.
3. Time-to-verdict (n=50) ≤ 26 weeks at expected frequency.
4. Every symbol in the universe passes `lot_check` at $200 notional.
5. Signal is computable on closed bars from data the bot actually has.
```

- [ ] **Step 5: Write `STANDARDS.md`**

```markdown
# STANDARDS — how research is done here (violations = the thesis dies)

1. **Mechanism first.** A thesis names the counterparty and why they are forced to pay. "Indicator X crosses Y" is not a thesis.
2. **Pre-register, then read.** Spec + signal code are frozen (`registrar.freeze`) with a sha before any data is read. A frozen spec is never edited; a new idea is a new thesis.
3. **Closed bars only.** `screen.causality_check` fails any signal that changes when future bars are removed. Live slots that read the forming bar reproduce only ~40% of closed-bar replays — do not build on forming-bar signals.
4. **Train / holdout.** Holdout = final 25% of the dataset's range. `load_data` refuses it without the committee token. It is read once, by the build stage, and recorded in the pre-reg doc.
5. **Statistics come from `lib/`.** `bootstrap_ci.mean_ci` / `diff_ci` (independent resampling, sort only the diffs), `fee_math.p_star`. Hand arithmetic in prose is a defect.
6. **Multiplicity.** The audit applies Benjamini–Hochberg across all screens in the run. One registered robustness read (±1 parameter step), never a grid.
7. **Fill realism.** Simulated fills are screening-grade upper bounds. Real maker fill ≈ 27%; adverse selection is in `c`. Forward test is the only adjudicator.
8. **Artifacts, not prose.** A candidate without `out.json` does not exist. Every number in a report links to a file. Orphaned artifacts are a critic finding.
9. **Never fabricate.** Run → read the tool output → write, with the path. "Not run" is a valid answer.
10. **Cite the dead list by row.** Every thesis lists its nearest dead rows and why the mechanism differs. The gatekeeper rejects relabels row-cited.
11. **Owner directives.** Never re-propose demoted books (main live, ST2.0, 5m_MR live, Donchian live), the BTC blacklist, gate loosening, universe swaps without a new mechanism, or the funding/XS/OI hunt. Plain English, verdict first.
12. **Reconcile.** Every screened thesis — pass or fail — becomes a row in DEAD_LIST.md or SURVIVORS.md; every process failure a dated line in LESSONS.md.
```

- [ ] **Step 6: Write `DATA.md`** (paths must match `load_data.DATASETS`)

```markdown
# DATA — what exists, where, how to load it

Use `research.swarm.lib.load_data`; never read caches by hand in a screen.

| dataset key | path | coverage | timeframes | notes |
|---|---|---|---|---|
| `mr_edge` | `reports/cache/mr_edge_20260601_20260903/` | 35 symbols, 2026-06-01 → 2026-09-02 23:55 UTC | 1m, 5m, 1h | pkl DataFrames, cols open/high/low/close/volume, UTC index. Funding: `funding_<SYM>_USDT_USDT.json` list of `{ts ms, rate}` (`load_funding`). Train ends ≈ 2026-08-10; holdout after. |
| `long_1h` | `scripts/research/mr-universe-scan-2026-08-01/cache/` | 19 symbols (1000PEPE 1000SHIB AAVE ADA BNB BTC DOGE ETH GIGGLE LINK LTC NEAR ONDO SOL SUI TAO UNI XLM XRP), 1h 2025-06-27 → 2026-08-01 | 1h (5m partial) | parquet. **Use this for multi-day / event-driven theses.** Train ends ≈ 2026-04-24. |

Longer daily history: `load_data.fetch_ohlcv_ccxt("BTC", "1d", since_ms, until_ms)` (Phemex public, network). Save fetched frames under the run dir `screens/<id>/data_*.pkl` (gitignored).

Other bot-collected data (not loadable via `load_data`; exploratory only):
- `logs/l2_ticks/<SYM>/<date>.jsonl.gz` — depth-5 book + tape, BTC/ETH/INJ/ARB, 2026-07-13 → 09-10 (1.9 GB).
- `logs/flow_capture.jsonl` — OB + flow snapshots 2026-05-11 → 09-09 (301 MB, 918k rows).
- `logs/entry_snapshots.jsonl` — 1,374 live entry contexts 2026-04-07 → 09-14.
- Archive tarball: `~/Desktop/Phmex-S-archive/phmex-s-market-data-2026-09-09.tar.gz` (1.97 GB) — same content.

Engines (reference; the desk uses `lib/screen.py`): `backtest.py`, `backtester.py`, `scripts/slot_lab/mr_edge_screen.py` (holdout guard pattern), `scripts/slot_lab/mr_edge_signal_table.py` (forming-bar regen).
```

- [ ] **Step 7: Write `DEAD_LIST.md`** — dispatch one agent (this is a consolidation task, not creative work):

Prompt for the agent: "Create `research/swarm/kb/DEAD_LIST.md`. Header lines explaining the row format, then ONE table with rows `| n | family | why dead (one line) | source | date |`. Rows 1–76: transcribe every numbered row from `docs/2026-09-16-edge-swarm-v1/01_dead_list.md` (A1 34 families + A2 42 levers), keeping their order, with the source `01_dead_list.md:<line>`. Rows 77+: one row per killed approach in these memory files that is NOT already covered: `~/.claude/projects/-Users-jonaspenaso-Desktop/memory/reference_*.md` (edge_hunt_exhaustion, new_strategy_feasibility, basis_carry_screen, btc_tsm_kill_test, nobarriers_search, scale_research, vwap_sma_cross, htf_l2_vwap_sma_filter, smallcap_viability, sr_bounce_scan, sr_bounce_lever_lab, mr_edge_search_2026-09-04, mr_overnight_program, mr_universe_scan, mr_ledger_trio, sl_loss_levers, overnight_sweep, gate_quantify, htf_l2_signal_rnd, htf_l2_entry_features, funding_spread_phemex). Then the 8 v1 swarm candidates (5 from `docs/2026-09-16-edge-swarm-v1/swarm/REPORT.md`, 3 from `sweep/REPORT.md`) as rows with source `swarm/REPORT.md` or `sweep/REPORT.md`. Finish with a short section 'Explicitly UNTESTED mechanisms' copied from 01_dead_list.md lines 189-204. Do not invent rows. Dates: use the date in the source; if none, 2026-09-16."

Verify: `python3 -c "from research.swarm.lib import kb_check, load_data as ld; print(len(kb_check.dead_rows(ld.REPO_ROOT/'research/swarm/kb/DEAD_LIST.md')))"` → ≥ 90.

- [ ] **Step 8: Write `LESSONS.md` seed and `SURVIVORS.md`**

```markdown
# LESSONS — the desk's own process failures (append-only, dated)

- 2026-09-16 — v1 discarded its own screens because phases handed off prose summaries. Rule: artifacts (`out.json`) are the only handoff.
- 2026-09-16 — v1 asserted "needs 56.5% WR" for two unrelated ideas with no derivation. Rule: all WR/time numbers come from `fee_math`.
- 2026-09-16 — v1 ideation was indicator-named; 8/8 were relabels. Rule: thesis schema requires counterparty + nearest dead rows.
- 2026-09-16 — v1 ran two workflows concurrently and died 4× on a shared rate ceiling. Rule: one workflow at a time.
- 2026-09-16 — v1 never explored multi-day / event-driven horizons though in scope. Rule: the desk brief must allocate at least two analyst lenses to horizons > 8h.
```

```markdown
# SURVIVORS — theses that passed the risk committee (append-only)

| run | id | train n | net bps | CI95 | WR | p* | prereg doc | status |
|---|---|---|---|---|---|---|---|---|
```

- [ ] **Step 9: Run tests**

Run: `python3 -m pytest tests/test_swarm_kb.py -q && python3 -m research.swarm.lib.kb_check`
Expected: 3 passed; `KB OK`

- [ ] **Step 10: Commit**

```bash
git add research/swarm/kb research/swarm/lib/kb_check.py tests/test_swarm_kb.py
git commit -m "feat(swarm): knowledge base (constraints, standards, data, dead list, lessons) + kb_check

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `desk.js` — the research workflow

**Files:**
- Create: `research/swarm/workflows/desk.js`
- Create: `research/swarm/README.md`
- Modify: `.gitignore` (append), `CLAUDE.md` (one line)

**Interfaces:**
- Consumes: CLIs from Tasks 4–6 (`registrar`, `screen`, `kb_check`), kb file contents.
- Produces: `research/swarm/runs/<run_id>/{mandate.md, theses/*.json, gate_rejections.json, specs/*.frozen.json, screens/<id>/{signal.py,out.json,trades.csv,audit.json}, committee/<id>.json, REPORT.md, CRITIC.md}`.
- Invocation: `Workflow({ scriptPath: "research/swarm/workflows/desk.js", args: { run_id: "2026-09-16-1400", now: "2026-09-16T21:00:00Z", max_analysts: 7, max_screens: 5, dry_run: false } })` — the script has no clock, so `now` and `run_id` come from args.
- The registrar is a *deterministic script* in the spec; the Workflow sandbox has no filesystem, so a low-effort agent runs the CLI and returns its stdout. That agent is forbidden from editing the thesis.

- [ ] **Step 1: Write `desk.js`**

```javascript
export const meta = {
  name: 'edge-desk-v2',
  description: 'Mechanism-first edge research desk: brief → analysts → gatekeeper → registrar → screen → audit → committee → report',
  phases: [
    { title: 'Brief', detail: 'read kb, write mandate' },
    { title: 'Analysts', detail: 'one market-participant lens each, ≤2 theses' },
    { title: 'Gate', detail: 'dedup + relabel check, row-cited' },
    { title: 'Register', detail: 'freeze spec+signal sha before data' },
    { title: 'Screen', detail: 'pre-registered train-era screen → out.json' },
    { title: 'Audit', detail: 're-run, lookahead/fee/era checks, BH' },
    { title: 'Committee', detail: 'economics + statistics, both must pass' },
    { title: 'Close', detail: 'report, critic, reconcile kb' },
  ],
}

const RUN_ID = args.run_id
const NOW = args.now
const MAX_ANALYSTS = args.max_analysts ?? 7
const MAX_SCREENS = args.max_screens ?? 5
const DRY = !!args.dry_run
const RUN_DIR = `research/swarm/runs/${RUN_ID}`
const KB = 'research/swarm/kb'
const REPO = '/Users/jonaspenaso/Desktop/Phmex-S'

const RULES = `You are one seat on a quant research desk for the Phmex-S bot (repo ${REPO}). Work from the repo root.
MANDATORY before anything: read ${KB}/CONSTRAINTS.md, ${KB}/STANDARDS.md, ${KB}/DATA.md and ${RUN_DIR}/mandate.md in full; grep ${KB}/DEAD_LIST.md for anything you touch.
Run dir for all outputs: ${RUN_DIR}. Never modify bot trading code. Never read holdout data. Never hand-compute win rates — use research.swarm.lib.fee_math. Cite files by path for every number. "Not run" is a valid answer; a made-up number is not.`

const THESIS_SCHEMA = {
  type: 'object',
  properties: {
    theses: { type: 'array', maxItems: 2, items: {
      type: 'object',
      properties: {
        id: { type: 'string' }, lens: { type: 'string' }, mechanism: { type: 'string' }, counterparty: { type: 'string' },
        prediction: { type: 'string' },
        nearest_dead_rows: { type: 'array', items: { type: 'object', properties: { row: { type: 'integer' }, why_different: { type: 'string' } }, required: ['row', 'why_different'] } },
        spec: { type: 'object', properties: {
          dataset: { type: 'string', enum: ['mr_edge', 'long_1h'] }, universe: { type: 'array', items: { type: 'string' }, minItems: 1 },
          timeframe: { type: 'string', enum: ['5m', '1h'] }, tp_bps: { type: 'number' }, sl_bps: { type: 'number' },
          max_hold_bars: { type: 'integer' }, expected_trades_per_week: { type: 'number' }, doa_line: { type: 'string' } },
          required: ['dataset', 'universe', 'timeframe', 'tp_bps', 'sl_bps', 'max_hold_bars', 'expected_trades_per_week', 'doa_line'] },
        signal_py: { type: 'string' }, thesis_path: { type: 'string' },
      },
      required: ['id', 'lens', 'mechanism', 'counterparty', 'prediction', 'nearest_dead_rows', 'spec', 'signal_py', 'thesis_path'],
    } },
    exploratory_notes: { type: 'string' },
  },
  required: ['theses'],
}

const GATE_SCHEMA = { type: 'object', properties: {
  kept: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, thesis_path: { type: 'string' }, reason: { type: 'string' } }, required: ['id', 'thesis_path', 'reason'] } },
  rejected: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, dead_row: { type: 'integer' }, reason: { type: 'string' } }, required: ['id', 'reason'] } },
  rejections_path: { type: 'string' } }, required: ['kept', 'rejected', 'rejections_path'] }

const REGISTER_SCHEMA = { type: 'object', properties: { frozen_path: { type: 'string' }, sha256: { type: 'string' }, ok: { type: 'boolean' }, error: { type: 'string' } }, required: ['ok'] }
const SCREEN_SCHEMA = { type: 'object', properties: { ok: { type: 'boolean' }, out_path: { type: 'string' }, n: { type: 'integer' }, net_bps_mean: { type: 'number' }, ci95: { type: 'array', items: { type: 'number' } }, wr: { type: 'number' }, p_star: { type: 'number' }, error: { type: 'string' } }, required: ['ok'] }
const AUDIT_SCHEMA = { type: 'object', properties: { verdict: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'RERUN_MISMATCH'] }, audit_path: { type: 'string' }, ci_excludes_zero: { type: 'boolean' }, bh_significant: { type: 'boolean' }, findings: { type: 'array', items: { type: 'string' } } }, required: ['verdict', 'audit_path', 'ci_excludes_zero'] }
const COMMITTEE_SCHEMA = { type: 'object', properties: { votes: { type: 'array', items: { type: 'object', properties: { id: { type: 'string' }, pass: { type: 'boolean' }, reasons: { type: 'array', items: { type: 'string' } } }, required: ['id', 'pass', 'reasons'] } }, path: { type: 'string' } }, required: ['votes', 'path'] }

const LENSES = [
  ['forced_flows', 'Forced flows: liquidations, funding settlement at 00/08/16 UTC, listings/delistings, index or perp-basis rebalances. Who is FORCED to trade and when?'],
  ['informed_flow', 'Informed vs uninformed flow: cross-venue lead-lag (Binance/Bybit/Coinbase → Phemex), spot→perp, large-cap→alt propagation at hourly+ horizons. Who knows first, and how long until Phemex prices it?'],
  ['dealer_inventory', 'Dealer / market-maker inventory: end-of-session unwind, weekend inventory, post-spike mean of the *basis* not price. Who must flatten, and when?'],
  ['session_calendar', 'Session and calendar structure at ≥ 8h horizons: Asia/EU/US opens, weekend→Monday, monthly/quarterly expiries, US macro release days. Multi-day holds only — intraday calendar effects are dead rows.'],
  ['vol_structure', 'Volatility structure: realized-vol regime shifts, vol-of-vol, compression→expansion at DAILY horizon, post-shock drift. Who is short gamma / forced to re-hedge?'],
  ['cross_asset', 'Cross-asset spillover: equities (SPX/NDX futures), DXY, rates moves → BTC/ETH at 1h–1d lags; ETH/BTC ratio regimes → alt beta. Who reprices late?'],
  ['literature', `Literature: open and disposition these already-fetched papers in docs/2026-09-16-edge-swarm-v1/sweep/: academic/*.txt, emoji_paper.txt, garcia_schweitzer.txt, hansen_periodicity.txt, petukhina_hft.txt, leadlag/guo.txt, onchain/*.txt, event/kse.txt. Run docs/2026-09-16-edge-swarm-v1/sweep/leadlag/local_check.py (fix paths if needed) and record its output under ${RUN_DIR}/exploratory/. Only a mechanism with a stated counterparty becomes a thesis.`],
].slice(0, MAX_ANALYSTS)

// ---------- Phase 1: Brief ----------
phase('Brief')
const mandate = await agent(`${RULES}
Write ${RUN_DIR}/mandate.md (create the dir). Contents: capital $200 and sizing; minimum net edge in bps after c=11.5 (justify from CONSTRAINTS.md); horizons in scope — intraday through multi-day, event-driven explicitly IN scope, and at least two analyst lenses must target holds > 8h; the bot's execution reality; datasets and their train/holdout boundaries (from DATA.md); the 15 DEAD_LIST rows most likely to be relabeled this run, by number. Also run: python3 -m research.swarm.lib.kb_check and include its output. Return the mandate text.`,
  { label: 'desk-brief', phase: 'Brief', effort: 'medium' })
log('mandate written')

// ---------- Phase 2: Analysts (barrier is correct: gatekeeper needs ALL theses to dedup) ----------
phase('Analysts')
const analystOut = await parallel(LENSES.map(([lens, brief], i) => () => agent(`${RULES}
You are analyst #${i + 1}, lens = ${lens}. ${brief}
Produce at most 2 theses. Each MUST: name the counterparty and why they are forced to pay; state a falsifiable prediction; list the nearest DEAD_LIST.md rows by number and say precisely why the MECHANISM differs (not the parameters); give a full spec (dataset mr_edge or long_1h, universe of symbols present in that dataset per DATA.md, timeframe 5m or 1h, tp_bps, sl_bps, max_hold_bars, expected_trades_per_week, doa_line); and supply signal_py — Python defining signals(df) -> pd.Series in {-1,0,1} on CLOSED bars only (no .shift(-k), no iloc[-1] tricks; the screen runs a causality check and kills lookahead). df has columns open/high/low/close/volume with a UTC index. Funding is available via research.swarm.lib.load_data.load_funding(symbol) if the signal needs it (merge_asof on ts, use only rates settled BEFORE the bar).
You MAY run exploratory probes on TRAIN data (era='train') to shape the thesis; save them under ${RUN_DIR}/exploratory/${lens}/ and label them exploratory — they are NOT the screen. Do not touch holdout.
Write each thesis as JSON to ${RUN_DIR}/theses/<id>.json and return them in the schema with thesis_path set. If your lens yields no thesis with a genuine counterparty, return an empty list and say why in exploratory_notes.`,
  { label: `analyst:${lens}`, phase: 'Analysts', schema: THESIS_SCHEMA, effort: 'medium' })))
const theses = analystOut.filter(Boolean).flatMap(r => r.theses)
log(`${theses.length} theses from ${analystOut.filter(Boolean).length}/${LENSES.length} analysts`)
if (!theses.length) return { run_id: RUN_ID, result: 'NO_THESES', mandate }

// ---------- Phase 3: Gatekeeper ----------
phase('Gate')
const gate = await agent(`${RULES}
You are the gatekeeper. Theses (JSON files): ${theses.map(t => t.thesis_path).join(', ')}.
For each: (1) dedup against the others (same mechanism = keep the better-specified one); (2) relabel check against ${KB}/DEAD_LIST.md — if the MECHANISM matches a dead row (ignore renamed indicators, changed parameters, changed universe), reject and cite the row; (3) sanity: universe symbols exist in the named dataset (DATA.md), tp/sl/hold are consistent with the horizon, signal_py defines signals(df). Keep at most ${MAX_SCREENS}, ranked by novelty of mechanism then specificity. Write ${RUN_DIR}/gate_rejections.json with every rejection {id, dead_row, reason}. Return kept (with thesis_path) and rejected.`,
  { label: 'gatekeeper', phase: 'Gate', schema: GATE_SCHEMA, effort: 'high' })
const kept = (gate?.kept ?? []).slice(0, MAX_SCREENS)
log(`gate kept ${kept.length}, rejected ${(gate?.rejected ?? []).length}`)
if (!kept.length) { phase('Close'); await closeOut([], [], gate); return { run_id: RUN_ID, result: 'ALL_REJECTED_AT_GATE', gate } }

// ---------- Phases 4–6: per-thesis pipeline (register → screen → audit), no barrier ----------
const chains = await pipeline(kept,
  k => agent(`${RULES}
Registrar (mechanical). Run exactly: python3 -m research.swarm.lib.registrar ${k.thesis_path} ${RUN_DIR} ${NOW}
Do NOT edit the thesis. If validation fails, return ok=false with the error verbatim. Otherwise return ok=true, frozen_path (stdout), and the sha256 from that file.`,
    { label: `register:${k.id}`, phase: 'Register', schema: REGISTER_SCHEMA, effort: 'low' }),
  (reg, k) => reg?.ok ? agent(`${RULES}
Screener for thesis ${k.id}. Frozen spec: ${reg.frozen_path} (sha ${reg.sha256}). Run exactly:
python3 -m research.swarm.lib.screen ${reg.frozen_path} ${RUN_DIR} --era train
You may NOT edit the frozen spec or signal.py. If the signal errors (ImportError, KeyError, causality failure), return ok=false with the traceback tail; do not "fix" it. On success return ok=true, out_path=${RUN_DIR}/screens/${k.id}/out.json and the n, net_bps_mean, ci95, wr, p_star values read from that file.`,
    { label: `screen:${k.id}`, phase: 'Screen', schema: SCREEN_SCHEMA, effort: 'high' }) : { ok: false, error: reg?.error ?? 'registrar failed' },
  (scr, k) => scr?.ok ? agent(`${RULES}
Auditor for thesis ${k.id}. Inputs: ${RUN_DIR}/specs/${k.id}.frozen.json, ${RUN_DIR}/screens/${k.id}/{signal.py,out.json,trades.csv}.
1. Verify the frozen sha (python3 -c "from research.swarm.lib import registrar as r; print(r.verify('${RUN_DIR}/specs/${k.id}.frozen.json'))").
2. Re-run the screen into a temp run dir (python3 -m research.swarm.lib.screen <frozen> /tmp/audit_${RUN_ID}_${k.id} --era train) and diff n / net_bps_mean / ci95 against out.json — any difference = RERUN_MISMATCH.
3. Read signal.py: any .shift(-k), future index use, or iloc[-1]-style forming-bar logic = REFUTED (lookahead).
4. Check trades.csv: entries strictly after signal bar; no trade exits after the train span end in out.json; cost applied (net = gross − 11.5).
5. Recompute p_star and time_to_verdict with research.swarm.lib.fee_math and compare to out.json.
6. Record ci_excludes_zero from out.json (both CI bounds same sign and > 0 for the mean). BH across this run: there will be ≤ ${MAX_SCREENS} screens; compute the per-screen bootstrap p-value approximation (share of bootstrap means ≤ 0 using bootstrap_ci with the trades' net_bps) and mark bh_significant at q=0.10 assuming ${MAX_SCREENS} tests.
Write ${RUN_DIR}/screens/${k.id}/audit.json {verdict, ci_excludes_zero, bh_significant, findings[], numbers{}} and return it.`,
    { label: `audit:${k.id}`, phase: 'Audit', schema: AUDIT_SCHEMA, effort: 'high' }) : { verdict: 'REFUTED', audit_path: '', ci_excludes_zero: false, findings: [scr?.error ?? 'screen failed'] },
)
const results = kept.map((k, i) => ({ id: k.id, audit: chains[i] }))
const eligible = results.filter(r => r.audit?.verdict === 'CONFIRMED' && r.audit.ci_excludes_zero)
log(`audits: ${results.map(r => `${r.id}=${r.audit?.verdict ?? 'null'}`).join(', ')}; committee-eligible: ${eligible.length}`)

// ---------- Phase 7: Committee (barrier correct: needs BH context across all screens) ----------
phase('Committee')
let committee = []
if (eligible.length) {
  const ids = eligible.map(e => e.id)
  const files = ids.map(id => `${RUN_DIR}/screens/${id}/{out.json,audit.json}`).join(' ')
  committee = await parallel([
    () => agent(`${RULES}
Risk committee — ECONOMICS seat. Candidates: ${ids.join(', ')}. Files: ${files}. Judge ONLY from those files plus fee_math. For each: observed wr vs p_star; lot_check all ok at $200 notional; feasibility on a 5-min poller (signal timeframe ≥ 5m, no sub-bar timing); funding exposure at max_hold; time_to_verdict_weeks ≤ 26. Pass only if all hold. Write ${RUN_DIR}/committee/economics.json and return votes.`,
      { label: 'committee:economics', phase: 'Committee', schema: COMMITTEE_SCHEMA, effort: 'high' }),
    () => agent(`${RULES}
Risk committee — STATISTICS seat. Candidates: ${ids.join(', ')}. Files: ${files}. Judge ONLY from those files plus research.swarm.lib. For each: n ≥ 30; CI95 excludes 0; bh_significant true; trades spread across the train span (no single month > 50% of trades — check trades.csv); per_symbol not dominated by one symbol > 60% unless universe size is 1; one robustness read: re-run the screen with tp_bps and sl_bps each ±20% into /tmp/robust_${RUN_ID}_<id>_<variant> (4 variants; you MAY do this because it is the registered robustness read, and you must record all 4 results) — pass only if ≥ 3 of 4 keep net_bps_mean > 0. Write ${RUN_DIR}/committee/statistics.json and return votes.`,
      { label: 'committee:statistics', phase: 'Committee', schema: COMMITTEE_SCHEMA, effort: 'high' }),
  ])
}
const votes = committee.filter(Boolean)
const passed = eligible.filter(e => votes.length === 2 && votes.every(v => v.votes.find(x => x.id === e.id)?.pass)).map(e => e.id)
log(`committee passed: ${passed.length ? passed.join(', ') : 'none'}`)

// ---------- Phase 8: Close ----------
phase('Close')
const closing = await closeOut(results, passed, gate)
return { run_id: RUN_ID, result: passed.length ? 'SURVIVORS' : 'NO_SURVIVORS', passed, results, gate_rejected: gate?.rejected ?? [], closing }

async function closeOut(results, passed, gate) {
  const report = await agent(`${RULES}
Write ${RUN_DIR}/REPORT.md. Verdict first (one sentence: how many theses, how many screened, how many passed committee). Then one paragraph per thesis in this run — gate-rejected ones (from ${RUN_DIR}/gate_rejections.json) in one line each with the dead row; screened ones with n, net bps, CI95, WR vs p*, audit verdict, committee votes — every number followed by the file path it came from. Then 'What was not done' (any analyst that returned no thesis, any screen that errored, with the error). Then 'Next run should' (3 bullets, process not strategy). Plain English, no tables wider than 6 columns. Return the report text.`,
    { label: 'report', phase: 'Close', effort: 'high' })
  const critic = await agent(`${RULES}
Completeness critic. Read ${RUN_DIR}/REPORT.md and list the run dir recursively. Find: (a) any screens/<id>/ or exploratory/ artifact not cited in the report; (b) any number in the report without a file path; (c) contradictions between gate_rejections.json, out.json, audit.json, committee/*.json and the report; (d) any thesis whose nearest_dead_rows is empty or whose why_different is generic; (e) holdout access (grep the run dir for COMMITTEE-HOLDOUT-READ or era=holdout). Write ${RUN_DIR}/CRITIC.md and return it.`,
    { label: 'critic', phase: 'Close', effort: 'high' })
  const reconcile = await agent(`${RULES}
Reconciler. For EVERY thesis in ${RUN_DIR}/theses/: if it was gate-rejected or its screen/audit/committee failed, append ONE row to ${KB}/DEAD_LIST.md in the existing row format with the next row number, the decisive reason (cite out.json numbers when they exist, else the dead row it relabeled), source ${RUN_DIR}/REPORT.md, date ${NOW.slice(0, 10)}. If it passed committee (${passed.join(', ') || 'none'}), append a row to ${KB}/SURVIVORS.md instead. Then append dated lines to ${KB}/LESSONS.md for every process failure the critic found in ${RUN_DIR}/CRITIC.md (not strategy lessons — process). Run python3 -m research.swarm.lib.kb_check and return its output plus the rows you added.`,
    { label: 'reconcile', phase: 'Close', effort: 'high' })
  return { report, critic, reconcile }
}
```

- [ ] **Step 2: Write `research/swarm/README.md`**

```markdown
# Edge Swarm v2 — the desk

Spec: `docs/superpowers/specs/2026-09-16-edge-swarm-v2-design.md`. Plan: `docs/superpowers/plans/2026-09-16-edge-swarm-v2-desk.md`.

**Before any work on the bot's research:** `git pull` this repo, then read `kb/CONSTRAINTS.md`, `kb/STANDARDS.md`, `kb/DEAD_LIST.md`, `kb/LESSONS.md`. The knowledge base is the swarm's memory and lives in git, not on one laptop.

Run (alone — never concurrently with another workflow), from a Claude Code session in this repo:
```
Workflow({ scriptPath: "research/swarm/workflows/desk.js",
           args: { run_id: "<YYYY-MM-DD-HHMM PT>", now: "<ISO UTC>", max_analysts: 7, max_screens: 5 } })
```
Dry run of the plumbing: `args: { run_id: "dryrun-<date>", now: "...", max_analysts: 1, max_screens: 1, dry_run: true }`.

After a run: `python3 -m research.swarm.lib.kb_check && git add research/swarm && git commit && git push`.

Library tests: `python3 -m pytest tests/test_swarm_*.py -q`.
Build stage (`workflows/build.js`) runs only on a committee pass AND the owner's "go"; it stops before any bot restart (`/pre-restart-audit`).
```

- [ ] **Step 3: Append to `.gitignore` and add a line to `CLAUDE.md`**

```bash
cat >> .gitignore <<'EOF'
# swarm v2: raw data copies inside run dirs never go to git
research/swarm/runs/*/screens/*/data*
research/swarm/runs/**/*.pkl
research/swarm/runs/**/*.parquet
EOF
```

Add to `CLAUDE.md` (Phmex-S), in the section that lists key files, one line:
`- research/swarm/ — edge-research desk (v2). Pull first, read kb/ before proposing any strategy work. See research/swarm/README.md.`

- [ ] **Step 4: Dry-run the plumbing on a deliberately dead thesis**

Invoke (Workflow tool, alone):
`Workflow({ scriptPath: "research/swarm/workflows/desk.js", args: { run_id: "dryrun-2026-09-16", now: "<ISO UTC now>", max_analysts: 1, max_screens: 1, dry_run: true } })`

With `max_analysts: 1` only the `forced_flows` lens runs. Expected shape: brief writes `mandate.md`; analyst returns ≤2 theses; gatekeeper either rejects row-cited (→ `ALL_REJECTED_AT_GATE`, reconciler appends DEAD_LIST rows and a LESSONS line, `kb_check` prints `KB OK`) or keeps 1 (→ registrar frozen file exists with sha, `out.json` exists, `audit.json` exists, committee ran only if CI excludes 0). Verify with:

```bash
find research/swarm/runs/dryrun-2026-09-16 -type f | sort
python3 -m research.swarm.lib.kb_check
git diff --stat research/swarm/kb
```

If any phase returned `null` or an agent "fixed" a frozen spec, edit the prompt and resume with `resumeFromRunId`.

- [ ] **Step 5: Commit**

```bash
git add research/swarm/workflows/desk.js research/swarm/README.md research/swarm/runs/dryrun-2026-09-16 research/swarm/kb .gitignore CLAUDE.md
git commit -m "feat(swarm): desk.js research workflow + README + dry run

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: `build.js` — build stage (written now, run only on a committee pass + owner go)

**Files:**
- Create: `research/swarm/workflows/build.js`

**Interfaces:**
- Consumes: `research/swarm/runs/<run_id>/{specs/<id>.frozen.json, screens/<id>/out.json, committee/*.json}`; framework recipe `docs/2026-09-16-edge-swarm-v1/02_framework_audit.md` §165-213; pattern files `donchian_slot.py`, `tests/test_donchian_slot.py`, `scripts/lab_adjudicator/adjudicate.py` (`EXPERIMENTS`, `grade_<name>`), `bot.py` `_evaluate_all_slots`.
- Produces: `docs/superpowers/specs/<date>-<id>-prereg.md` (with the ONE holdout read recorded), `<id>_slot.py`, `tests/test_<id>_slot.py`, adjudicator entry, dashboard/report propagation, `.kill_<id>` documented; a branch `swarm/<id>-slot`; **no restart**.
- Invocation: `Workflow({ scriptPath: "research/swarm/workflows/build.js", args: { run_id, thesis_id, now } })`.

- [ ] **Step 1: Write `build.js`**

```javascript
export const meta = {
  name: 'edge-desk-v2-build',
  description: 'Turn a committee-passed thesis into a pre-registered paper slot (TDD), stopping before any restart',
  phases: [
    { title: 'Prereg', detail: 'holdout read once, frozen verdict line' },
    { title: 'Implement', detail: 'slot + tests, mirrors donchian_slot' },
    { title: 'Review', detail: 'independent reviewer, full test suite' },
  ],
}
const { run_id, thesis_id, now } = args
const RUN_DIR = `research/swarm/runs/${run_id}`
const REPO = '/Users/jonaspenaso/Desktop/Phmex-S'
const RULES = `Quant desk build stage for Phmex-S (${REPO}). Read research/swarm/kb/CONSTRAINTS.md and STANDARDS.md first. Thesis: ${RUN_DIR}/specs/${thesis_id}.frozen.json, screen ${RUN_DIR}/screens/${thesis_id}/out.json, committee ${RUN_DIR}/committee/. Work on git branch swarm/${thesis_id}-slot (create from main if absent). NEVER start, restart, or signal the bot. NEVER touch .env.`

phase('Prereg')
const prereg = await agent(`${RULES}
Write docs/superpowers/specs/${now.slice(0, 10)}-${thesis_id}-prereg.md in the house format (see docs/superpowers/specs/2026-09-03-mr-edge-search-prereg.md for tone): Registered (${now}), Thesis (mechanism + counterparty verbatim from the frozen spec), Frozen data, Economics ($200 basis; sizing from fee_math.position_notional), Verdict line — verdict_n = 50; at n ≥ 50 net ≤ 0 → KILL; loss cap −$10 any n → KILL; anti-fishing clause (no parameter changes during the paper era), Prior (train out.json numbers with paths).
THEN perform the single registered HOLDOUT read: python3 -m research.swarm.lib.screen ${RUN_DIR}/specs/${thesis_id}.frozen.json ${RUN_DIR} --era holdout --token COMMITTEE-HOLDOUT-READ  (this writes screens/${thesis_id}/out.json — first copy the train out.json to out.train.json). Record holdout n, net bps, CI95 in the prereg doc under 'Holdout (read once, ${now})' with the path. If holdout CI95 upper < 0, write STATUS: DEAD-AT-HOLDOUT at the top and stop. Return the doc text.`,
  { label: 'prereg', phase: 'Prereg', effort: 'high' })
if (/STATUS: DEAD-AT-HOLDOUT/.test(prereg ?? '')) return { thesis_id, result: 'DEAD_AT_HOLDOUT', prereg }

phase('Implement')
const impl = await agent(`${RULES}
Implement the paper slot with TDD, mirroring donchian_slot.py and tests/test_donchian_slot.py exactly in structure:
1. tests/test_${thesis_id}_slot.py first — golden micro-cases for signal → entry/exit, sidecar state roundtrip, and orchestration on a bare bot with a fake exchange (pattern in test_donchian_slot.py). Run; confirm they fail.
2. ${thesis_id}_slot.py — pure module; signal logic transcribed from ${RUN_DIR}/screens/${thesis_id}/signal.py on CLOSED bars (must not read the forming bar); TP/SL/max_hold from the frozen spec; sizing fee_math.position_notional().
3. bot.py — _evaluate_${thesis_id} called from _evaluate_all_slots, paper-only (.paper sentinel semantics identical to donchian), rails opt-out loss_cap_usdt=-999.0, kelly_min_trades=10**9 as the recipe specifies, kill file .kill_${thesis_id}.
4. scripts/lab_adjudicator/adjudicate.py — EXPERIMENTS entry with verdict_n=50, grade_${thesis_id} implementing the prereg verdict line.
5. Dashboard / daily report propagation per CLAUDE.md rule for new slots.
Run python3 -m pytest -q; the suite must be at baseline (1005 pass, 1 known ordering-only fail) plus your new tests passing. Commit on the branch with a message ending 'Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>'. Return the list of files changed and the pytest tail.`,
  { label: 'implement', phase: 'Implement', effort: 'high' })

phase('Review')
const review = await agent(`${RULES}
Independent reviewer. git diff main...swarm/${thesis_id}-slot. Check: forming-bar reads (df.iloc[-1] on an unclosed bar) → BLOCK; any path that can place a LIVE order without the .paper sentinel → BLOCK; kill file honoured every cycle; adjudicator verdict line matches the prereg doc numerically; tests actually exercise the signal (not just construction); no .env or data files in the diff. Run python3 -m pytest -q and report the tail. Return APPROVE or BLOCK with reasons.`,
  { label: 'review', phase: 'Review', effort: 'high', agentType: 'feature-dev:code-reviewer' })
return { thesis_id, result: 'BUILT_AWAITING_OWNER_GO', branch: `swarm/${thesis_id}-slot`, prereg_doc: `docs/superpowers/specs/${now.slice(0, 10)}-${thesis_id}-prereg.md`, impl, review,
         next: 'Owner: review branch, run /pre-restart-audit, say go. Nothing has been restarted.' }
```

- [ ] **Step 2: Syntax-check the script without running it**

Run: `node --check research/swarm/workflows/build.js 2>&1 || echo "node absent — check with: python3 - <<'EOF'\nimport re,sys;src=open('research/swarm/workflows/build.js').read();assert src.count('{')==src.count('}') and src.count('(')==src.count(')');print('brace/paren balance OK')\nEOF"`
Expected: no syntax error (or balance OK if node is unavailable). `export const meta` will fail `node --check` as a script but pass as a module: use `node --input-type=module --check < file` if needed.

- [ ] **Step 3: Commit**

```bash
git add research/swarm/workflows/build.js
git commit -m "feat(swarm): build.js — committee pass → pre-registered paper slot, stops before restart

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Run 1, publish the knowledge base, record memory

**Files:**
- Produces: `research/swarm/runs/<run_id>/...`, updated `kb/`, pushed to `origin/main`; memory file `~/.claude/projects/-Users-jonaspenaso-Desktop/memory/project_edge_swarm_v2_2026-09-16.md` + MEMORY.md line.

- [ ] **Step 1: Preconditions**

```bash
cd ~/Desktop/Phmex-S && git status --short | grep -v '^ M scripts/research/funding-spread' ; python3 -m pytest tests/test_swarm_*.py -q && python3 -m research.swarm.lib.kb_check
ps aux | grep -c "[w]orkflow" ; date -u +%Y-%m-%dT%H:%M:%SZ ; TZ=America/Los_Angeles date +%Y-%m-%d-%H%M
```
Expected: clean tree (except the two pre-existing modified JSONs), all swarm tests pass, `KB OK`, no other workflow running. Also confirm usage headroom (v1 died on limits): if a session-limit warning is visible, wait for the reset.

- [ ] **Step 2: Launch run 1 (alone)**

`Workflow({ scriptPath: "research/swarm/workflows/desk.js", args: { run_id: "<PT stamp from step 1>", now: "<UTC stamp from step 1>", max_analysts: 7, max_screens: 5, dry_run: false } })`

Watch `/workflows`. If it dies on a limit, resume with `resumeFromRunId` after the reset — cached phases replay free.

- [ ] **Step 3: Read the result honestly**

Read `research/swarm/runs/<run_id>/REPORT.md` and `CRITIC.md`. Cross-check two numbers from the report against their `out.json` by hand. Run `python3 -m research.swarm.lib.kb_check`. Do NOT summarize to the owner until this is done.

- [ ] **Step 4: Publish**

```bash
git add research/swarm && git commit -m "swarm run <run_id>: <N> theses, <M> screened, <K> passed committee

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>" && git push origin main
```

- [ ] **Step 5: Memory**

Write `project_edge_swarm_v2_2026-09-16.md` (type: project) with: what was built, run 1 verdict with file paths, the "run alone / pull kb first" rules, and whether `build.js` is pending an owner go. Add one line to MEMORY.md; mark the v1 entry superseded.

- [ ] **Step 6: Report to owner** — verdict first, plain English: theses count, screened count, committee passes, the one or two decisive numbers with paths, what was not done, and (only if there is a survivor) that `build.js` is ready and waits for "go".

---

## Self-review

**Spec coverage.** §3 capital → Task 1 + CONSTRAINTS.md. §4 layout → Tasks 1–8 create every listed file; `runs/` created by the workflow. §5 phases 1–8 → `desk.js` Brief/Analysts/Gate/Register/Screen/Audit/Committee/Close; pipelining and barriers as specified; caps and "run alone" in README + Task 9. §6 build stage → Task 8, stops before restart. §7 paper/live → build.js prereg verdict line + adjudicator entry; live remains manual (stated in build.js return). §8 git records → README pull-first rule, CLAUDE.md line, Task 9 push, `.gitignore`. §9 testing → Tasks 1–6 tests incl. sort-first regression, holdout refusal, sha stability, planted edge + planted lookahead; dry run in Task 7. §10 out of scope untouched.

**Placeholders.** None: every code step is complete. The DEAD_LIST consolidation is an agent task by design (transcription of ~90 rows) with a machine check (`dead_rows ≥ 90`, unique ascending).

**Type consistency.** `registrar.freeze(thesis, run_dir, frozen_at) -> Path` used by `screen.run_screen(frozen_path, run_dir, era, token)` and by `desk.js` CLI; `load_data.split_era(df, era, token)` signature matches the `monkeypatch` lambdas in Task 5 tests (`era`, `token` kwargs); `fee_math.p_star(tp_bps)` used in `screen` matches Task 1; `kb_check.dead_rows(path)` used by Task 6 tests and reconciler row format `| n | family | why | source | date |` matches `_ROW`.
