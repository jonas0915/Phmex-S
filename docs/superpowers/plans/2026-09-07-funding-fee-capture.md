# Funding + Fee Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every real-money trade row carry exchange-exact fees and the funding actually paid/received, and make those values survive the bot's own state saves.

**Architecture:** The bot's close path stays cheap (no new API calls on the 60 s loop, with one bounded exception: a crumb close now reads its own order's fee, which may fall back to one fetch_order call on the rare min_margin_skip path); it only stops under-reporting fees on exchange-side closes and crumb closes. The existing 15-minute reconciler (`scripts/reconcile_phemex.py`, launchd `com.phmex.reconcile --apply`) becomes ledger-aware (main book + live slot files) and funding-aware (Phemex `fetch_funding_history`). `RiskManager._save_state` merges reconciler-written fields back into memory before it overwrites the file, so patches persist instead of being clobbered by the next close.

**Tech Stack:** Python 3.14, ccxt phemex (`fetchMyTrades`, `fetchFundingHistory`), pytest (`python3 -m pytest tests/ -q`), launchd.

**Spec:** Backlog item 1+2 in `~/.claude/projects/-Users-jonaspenaso-Desktop/memory/project_bot_backlog_2026-09-07.md`; diagnosis receipts in this session (9/7 8:15–8:40 PM PT):
- `funding_usdt` is 0.0 on all 51 keyed rows of `trading_state_5m_mean_revert.json`; 12 live rows straddled an 8 h settlement. Main book last had nonzero funding 4/7 (one-shot CSV backfill, `scripts/backfill_fees.py`).
- Phemex sign convention, verified read-only on the real account: `fetch_funding_history[].amount` is **positive = paid, negative = received** (ETH short 9/4 5:00 PM PT, rate +0.0000119, amount −0.00175251). This matches the writer's `net_pnl = gross − fees − funding` with `funding_usdt` = amount paid.
- `fetch_my_trades` interleaves funding settlements with fills: funding rows have `info.tradeType == "4"`, `info.action == "13"`, `type None`, negative-or-positive `fee.cost`; real fills have `tradeType == "1"`. Fill `id` is the Phemex `execId`; `order` is always `None`.
- Real round trip for the 9/4 ETH row: entry maker 0.01470822 + exit taker 0.08828856 = 0.10299678; the ledger holds 0.097074 (an estimate). Low-tier rows (8 `exchange_close` rows at 0.0004–0.01 % of notional) are the "last fill only" bug at `bot.py:4147-4174`.
- `_save_state` (`risk_manager.py:366`) dumps the in-memory list wholesale, so reconciler patches are reverted on the next close and only re-applied inside the 7-day lookback.
- Reconciler is main-book only (`STATE_FILE` hardcoded, `reconcile_phemex.py:36`).

## Global Constraints

- Edits do NOT reach the running bot (PID 78531) until an audited restart. `/pre-restart-audit` is mandatory and the owner must say "go" (CLAUDE.md).
- `scripts/reconcile_phemex.py` IS live the moment it is saved (launchd runs it every 15 min with `--apply`). Never leave it in a broken intermediate state; tests must pass before each save of that file.
- No shadow logging / paper-confirm validation. Ship live, small, reversible (`feedback_no_shadow_live_deploy.md`).
- Never run pytest without `PHMEX_LOG_FILE` routed away from `logs/bot.log` (conftest handles it; do not override).
- Fee constants: `Config.MAKER_FEE_PERCENT` 0.01, `Config.TAKER_FEE_PERCENT` 0.06, `SLIPPAGE_PERCENT` 0.05 (`.env` pins taker + slippage). Never re-estimate a number the exchange reports.
- Historical main-book rows with no `mode` key are real money; slot-file rows are real only when `mode == "live"`.
- Every bot-side change propagates to Telegram (`notifier.py`/`scripts/daily_report.py`) and dashboard (`web_dashboard.py`) per CLAUDE.md.
- Times in owner-facing output: 12-hour PT.
- Research/probe scripts run with `nice -n 19` and their own ccxt client; read-only.

---

### Task 0: Snapshot the ledgers before anything touches them

**Files:**
- Create: `reports/backup/2026-09-07-prefund/` (copies of every `trading_state*.json`)

- [ ] **Step 1: Copy every state file**

```bash
cd ~/Desktop/Phmex-S && mkdir -p reports/backup/2026-09-07-prefund && cp trading_state*.json reports/backup/2026-09-07-prefund/ && ls reports/backup/2026-09-07-prefund | wc -l
```
Expected: 26 files.

- [ ] **Step 2: Record the baseline git commit for the pre-restart audit**

```bash
git -C ~/Desktop/Phmex-S log -1 --format="%h %ad" --date=format:"%m/%d %I:%M %p"
```
Note the hash in TASKS.md (the hourly auto-backup commits the tree, so the diff for the audit is against the last commit before PID 78531 started on 9/3 9:31 PM PT, i.e. `git log --before="2026-09-03 21:31" -1`).

---

### Task 1: Reconciler — pure matching helpers (funding-row filter, claim-once fill matching, funding attribution)

**Files:**
- Modify: `scripts/reconcile_phemex.py` (top-level helpers; keep `main()` working)
- Test: `tests/test_reconcile_phemex.py` (new)

**Interfaces:**
- Produces:
  - `is_funding_row(fill: dict) -> bool`
  - `fill_key(fill: dict) -> str`
  - `match_trade_to_fills(trade, fills, claimed: set | None = None) -> tuple[list, list, float]` (existing name, new semantics: skips funding rows, exit window `closed_at−300 s … closed_at+60 s`, each fill claimed once)
  - `attribute_funding(trades: list[dict], funding_rows: list[dict]) -> dict[tuple, float]` keyed by `trade_key(t)`; funding rows are `{"timestamp": ms, "symbol": str, "paid": float}`
  - `trade_key(t) -> tuple = (t.get("opened_at"), t.get("symbol"), t.get("closed_at"))`
  - Constants: `FEE_TOLERANCE_USDT = 0.01`, `FUNDING_TOLERANCE_USDT = 1e-6`, `EXIT_MATCH_BEFORE_SEC = 300`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reconcile_phemex.py
"""Reconciler matching + funding attribution (2026-09-07 funding/fee capture).

Phemex facts these tests pin (verified read-only 9/7):
  * fetch_my_trades interleaves 8h funding settlements with fills; funding rows
    carry info.tradeType == "4" / info.action == "13"; real fills tradeType == "1".
  * fetch_funding_history[].amount is positive = PAID, negative = RECEIVED, which
    matches risk_manager's net_pnl = gross - fees - funding with funding = paid.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import reconcile_phemex as rp  # noqa: E402

SYM = "ETH/USDT:USDT"


def _fill(ts_s, side, price, amount, fee, trade_type="1", fid=None):
    return {
        "id": fid or f"{ts_s}:{side}",
        "timestamp": int(ts_s * 1000),
        "side": side,
        "price": price,
        "amount": amount,
        "fee": {"currency": "USDT", "cost": fee, "rate": 0.0006},
        "fees": [{"currency": "USDT", "cost": fee, "rate": 0.0006}],
        "info": {"tradeType": trade_type, "action": "13" if trade_type == "4" else "1"},
    }


def _trade(opened, closed, symbol=SYM, **kw):
    t = {"symbol": symbol, "opened_at": opened, "closed_at": closed, "side": "short",
         "pnl_usdt": 1.0, "fees_usdt": 0.05, "funding_usdt": 0.0, "net_pnl": 0.95}
    t.update(kw)
    return t


def test_is_funding_row_by_trade_type_or_action():
    assert rp.is_funding_row({"info": {"tradeType": "4"}})
    assert rp.is_funding_row({"info": {"action": "13"}})
    assert not rp.is_funding_row({"info": {"tradeType": "1", "action": "1"}})
    assert not rp.is_funding_row({})


def test_match_skips_funding_rows_and_sums_entry_plus_exit():
    t = _trade(1000.0, 5000.0)
    fills = [
        _fill(1001, "sell", 2451.0, 0.06, 0.0147),                 # entry
        _fill(3600, "sell", 2454.0, 0.06, -0.0017, trade_type="4"),  # funding settlement
        _fill(4990, "buy", 2452.0, 0.06, 0.0883),                  # exit fill
    ]
    entry, exit_, fee = rp.match_trade_to_fills(t, fills)
    assert [f["id"] for f in entry] == ["1001:sell"]
    assert [f["id"] for f in exit_] == ["4990:buy"]
    assert fee == pytest.approx(0.0147 + 0.0883)


def test_exit_window_reaches_300s_before_closed_at():
    # exchange_close rows are recorded by the sync loop up to a few minutes
    # AFTER the real fill (cycle can stretch to the 180s watchdog).
    t = _trade(1000.0, 5000.0)
    fills = [_fill(1001, "sell", 1.0, 1, 0.01), _fill(4750, "buy", 1.0, 1, 0.09)]
    entry, exit_, fee = rp.match_trade_to_fills(t, fills)
    assert len(exit_) == 1 and fee == pytest.approx(0.10)
    # ...but not 301s+ before
    fills2 = [_fill(1001, "sell", 1.0, 1, 0.01), _fill(4699, "buy", 1.0, 1, 0.09)]
    _, exit2, _ = rp.match_trade_to_fills(t, fills2)
    assert exit2 == []


def test_fills_claimed_once_across_consecutive_trades():
    # crumb closed at 10:03:41 then a real entry at 10:06 on the same symbol
    crumb = _trade(1000.0, 1000.5, exit_reason="min_margin_skip")
    real = _trade(1140.0, 5000.0)
    fills = [
        _fill(1000.2, "sell", 1.0, 1, 0.001, fid="crumb-entry"),
        _fill(1000.4, "buy", 1.0, 1, 0.006, fid="crumb-exit"),
        _fill(1140.1, "sell", 1.0, 1, 0.015, fid="real-entry"),
        _fill(4999.0, "buy", 1.0, 1, 0.088, fid="real-exit"),
    ]
    claimed = set()
    e1, x1, f1 = rp.match_trade_to_fills(crumb, fills, claimed)
    e2, x2, f2 = rp.match_trade_to_fills(real, fills, claimed)
    assert {f["id"] for f in e1 + x1} == {"crumb-entry", "crumb-exit"}
    assert {f["id"] for f in e2 + x2} == {"real-entry", "real-exit"}
    assert f1 == pytest.approx(0.007) and f2 == pytest.approx(0.103)


def test_attribute_funding_assigns_each_payment_once_and_signs_as_paid():
    partial = _trade(1000.0, 3000.0, exit_reason="partial_tp")
    runner = _trade(1000.0, 9000.0, exit_reason="take_profit")
    other_sym = _trade(1000.0, 9000.0, symbol="SOL/USDT:USDT")
    funding = [
        {"timestamp": 2000 * 1000, "symbol": SYM, "paid": -0.0017},   # received while full size
        {"timestamp": 8000 * 1000, "symbol": SYM, "paid": 0.0024},    # paid on the runner
        {"timestamp": 500 * 1000, "symbol": SYM, "paid": 9.9},        # before open: ignored
        {"timestamp": 9000 * 1000, "symbol": SYM, "paid": 0.001},     # exactly at close: included
        {"timestamp": 2000 * 1000, "symbol": "SOL/USDT:USDT", "paid": 0.5},
    ]
    out = rp.attribute_funding([runner, partial, other_sym], funding)
    assert out[rp.trade_key(partial)] == pytest.approx(-0.0017)
    assert out[rp.trade_key(runner)] == pytest.approx(0.0024 + 0.001)
    assert out[rp.trade_key(other_sym)] == pytest.approx(0.5)


def test_constants():
    assert rp.FEE_TOLERANCE_USDT == 0.01
    assert rp.FUNDING_TOLERANCE_USDT == 1e-6
    assert rp.EXIT_MATCH_BEFORE_SEC == 300
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_reconcile_phemex.py -q`
Expected: FAIL (`AttributeError: module has no attribute is_funding_row`, etc.).

- [ ] **Step 3: Implement the helpers in `scripts/reconcile_phemex.py`**

Replace the constants block and `match_trade_to_fills` with:

```python
LOOKBACK_DAYS = 7
FILL_MATCH_WINDOW_SEC = 60          # entry fills within ±60s of opened_at
EXIT_MATCH_BEFORE_SEC = 300         # exchange_close rows are stamped by the sync loop up to
                                    # a few minutes AFTER the real fill (cycle ≤ 180s watchdog)
FEE_TOLERANCE_USDT = 0.01           # patch fees when |local - phemex| > this
FUNDING_TOLERANCE_USDT = 1e-6       # funding is exact: patch on any change
MAIN_STATE_FILE = ROOT / "trading_state.json"
STATE_FILE = MAIN_STATE_FILE        # back-compat alias (daily_report imports nothing, but keep)
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


def match_trade_to_fills(trade: dict, fills: list[dict], claimed: set | None = None) -> tuple[list[dict], list[dict], float]:
    """Return (entry_fills, exit_fills, total_fee) for this trade.

    Entry window: |ts - opened_at| <= 60s. Exit window: closed_at-300s .. closed_at+60s
    (sync-loop closes are stamped late). Funding settlement rows are skipped.
    `claimed` (fill ids already assigned to an earlier trade) prevents a crumb
    close and the real entry that followed it seconds later from sharing fills.
    """
    opened_at = trade.get("opened_at") or 0
    closed_at = trade.get("closed_at") or 0
    entry_fills: list[dict] = []
    exit_fills: list[dict] = []
    for f in fills:
        if is_funding_row(f):
            continue
        k = fill_key(f)
        if claimed is not None and k in claimed:
            continue
        f_ts = (f.get("timestamp") or 0) / 1000
        if opened_at and abs(f_ts - opened_at) <= FILL_MATCH_WINDOW_SEC:
            entry_fills.append(f)
        elif closed_at and (closed_at - EXIT_MATCH_BEFORE_SEC) <= f_ts <= (closed_at + FILL_MATCH_WINDOW_SEC):
            exit_fills.append(f)
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
```

Keep `_fill_fee` as is (it takes `abs`, which is correct for fill fees; funding rows never reach it).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_reconcile_phemex.py -q`
Expected: 6 passed. Also `python3 -m py_compile scripts/reconcile_phemex.py` exits 0 (this file is live under launchd).

- [ ] **Step 5: Commit**

```bash
git add scripts/reconcile_phemex.py tests/test_reconcile_phemex.py
git commit -m "reconcile: funding-row filter, claim-once fill matching, funding attribution"
```

---

### Task 2: Reconciler — ledger discovery, funding fetch, per-file apply

**Files:**
- Modify: `scripts/reconcile_phemex.py` (`load_closed_trades` → `ledger_files` + `load_rows`; `apply_fee_fixes` → `apply_patches`; new `fetch_funding_rows`; rewrite `main()`)
- Test: `tests/test_reconcile_phemex.py` (extend)

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces:
  - `ledger_files() -> list[tuple[Path, str]]` — `[(main, "main"), (slot files..., "slot")]`, excluding `ARCHIVE_MARKERS`.
  - `is_real_row(t: dict, kind: str) -> bool` — main: `mode != "paper"`; slot: `mode == "live"`.
  - `load_rows(path, kind, since_ms) -> list[dict]`
  - `fetch_funding_rows(exchange, symbol, since_ms) -> list[dict]` → `[{"timestamp", "symbol", "paid"}]`, pages `offset` by 200 up to 5 pages.
  - `build_patches(rows, fills_by_sym, funding_by_key) -> tuple[list[dict], list[dict]]` → `(patches, unmatched)`; a patch is `{"key", "fees_usdt" | None, "funding_usdt" | None, "local_fee", "local_funding"}`.
  - `apply_patches(path: Path, patches: list[dict]) -> int` (−1 on abort).
  - CLI: `--apply`, `--lookback-days N` (default 7).
  - Written fields: `fees_usdt`, `fees_source="phemex_reconcile"`, `fees_reconciled_at`, `funding_usdt` (paid, positive = cost), `funding_source="phemex_reconcile"`, `funding_reconciled_at`, `net_pnl` recomputed; `fees_pending` removed when fees are patched.

- [ ] **Step 1: Write the failing tests (append to `tests/test_reconcile_phemex.py`)**

```python
import json


def test_ledger_files_excludes_sidecars_and_archives(monkeypatch, tmp_path):
    for name in ["trading_state.json", "trading_state_5m_mean_revert.json",
                 "trading_state_5m_mean_revert_mode.json", "trading_state_5m_narrow_blocked.json",
                 "trading_state_v8_245trades.json", "trading_state_SR_BOUNCE_era1.json"]:
        (tmp_path / name).write_text("{}")
    monkeypatch.setattr(rp, "ROOT", tmp_path)
    monkeypatch.setattr(rp, "MAIN_STATE_FILE", tmp_path / "trading_state.json")
    files = rp.ledger_files()
    names = [(p.name, k) for p, k in files]
    assert names == [("trading_state.json", "main"), ("trading_state_5m_mean_revert.json", "slot")]


def test_is_real_row_main_vs_slot():
    assert rp.is_real_row({}, "main")                       # historical main = real
    assert not rp.is_real_row({"mode": "paper"}, "main")
    assert rp.is_real_row({"mode": "live"}, "slot")
    assert not rp.is_real_row({}, "slot")                   # slot rows w/o mode = paper era
    assert not rp.is_real_row({"mode": "paper"}, "slot")


def test_build_patches_fees_funding_and_unmatched():
    t_ok = _trade(1000.0, 5000.0, fees_usdt=0.0059, funding_usdt=0.0, pnl_usdt=1.0, net_pnl=0.9941)
    t_same = _trade(6000.0, 7000.0, fees_usdt=0.103, funding_usdt=0.0, funding_source="phemex_reconcile")
    t_none = _trade(8000.0, 9000.0)
    fills = {SYM: [
        _fill(1001, "sell", 1.0, 1, 0.0147), _fill(4990, "buy", 1.0, 1, 0.0883),
        _fill(6001, "sell", 1.0, 1, 0.015), _fill(6999, "buy", 1.0, 1, 0.088),
    ]}
    funding = {rp.trade_key(t_ok): -0.0017, rp.trade_key(t_same): 0.0, rp.trade_key(t_none): 0.0}
    patches, unmatched = rp.build_patches([t_ok, t_same, t_none], fills, funding)
    assert unmatched == [t_none]
    by_key = {p["key"]: p for p in patches}
    p = by_key[rp.trade_key(t_ok)]
    assert p["fees_usdt"] == pytest.approx(0.103)          # 0.0059 → 0.103, drift > 0.01
    assert p["funding_usdt"] == pytest.approx(-0.0017)      # received
    # t_same: fees within tolerance, funding unchanged and already stamped → no patch
    assert rp.trade_key(t_same) not in by_key
    # unmatched rows never get funding stamped
    assert rp.trade_key(t_none) not in by_key


def test_build_patches_stamps_funding_zero_once():
    t = _trade(1000.0, 5000.0, fees_usdt=0.103, funding_usdt=0.0)   # no funding_source yet
    fills = {SYM: [_fill(1001, "sell", 1.0, 1, 0.015), _fill(4990, "buy", 1.0, 1, 0.088)]}
    patches, _ = rp.build_patches([t], fills, {rp.trade_key(t): 0.0})
    assert len(patches) == 1
    assert patches[0]["fees_usdt"] is None and patches[0]["funding_usdt"] == 0.0


def test_apply_patches_writes_fields_recomputes_net_and_clears_pending(tmp_path):
    path = tmp_path / "trading_state_5m_mean_revert.json"
    row = _trade(1000.0, 5000.0, mode="live", fees_usdt=0.105, fees_pending=True,
                 pnl_usdt=2.0, funding_usdt=0.0, net_pnl=1.895)
    path.write_text(json.dumps({"peak_balance": 1.0, "closed_trades": [row],
                                "trade_results": [], "positions": {"X": {"keep": 1}}}))
    n = rp.apply_patches(path, [{"key": rp.trade_key(row), "fees_usdt": 0.021,
                                 "funding_usdt": 0.0031, "local_fee": 0.105, "local_funding": 0.0}])
    assert n == 1
    got = json.loads(path.read_text())
    t = got["closed_trades"][0]
    assert t["fees_usdt"] == pytest.approx(0.021)
    assert t["funding_usdt"] == pytest.approx(0.0031)
    assert t["net_pnl"] == pytest.approx(2.0 - 0.021 - 0.0031)
    assert t["fees_source"] == "phemex_reconcile" and t["funding_source"] == "phemex_reconcile"
    assert "fees_pending" not in t
    assert got["positions"] == {"X": {"keep": 1}}           # untouched


def test_apply_patches_funding_only_keeps_fees(tmp_path):
    path = tmp_path / "trading_state.json"
    row = _trade(1000.0, 5000.0, fees_usdt=0.05, pnl_usdt=1.0, net_pnl=0.95)
    path.write_text(json.dumps({"closed_trades": [row]}))
    rp.apply_patches(path, [{"key": rp.trade_key(row), "fees_usdt": None,
                             "funding_usdt": 0.002, "local_fee": 0.05, "local_funding": 0.0}])
    t = json.loads(path.read_text())["closed_trades"][0]
    assert t["fees_usdt"] == 0.05 and "fees_source" not in t
    assert t["funding_usdt"] == pytest.approx(0.002) and t["net_pnl"] == pytest.approx(0.948)


class _FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def fetch_funding_history(self, symbol, since=None, limit=None, params=None):
        self.calls.append((symbol, limit, dict(params or {})))
        off = int((params or {}).get("offset", 0))
        return self.pages.get(off, [])


class _FakeExchange:
    def __init__(self, pages):
        self.client = _FakeClient(pages)


def test_fetch_funding_rows_pages_by_offset_and_filters_since():
    page0 = [{"timestamp": 9_000_000, "amount": -0.5, "symbol": "ETHUSDT"} for _ in range(200)]
    page1 = [{"timestamp": 5_000_000, "amount": 0.25, "symbol": "ETHUSDT"},
             {"timestamp": 1_000, "amount": 9.0, "symbol": "ETHUSDT"}]   # too old
    ex = _FakeExchange({0: page0, 200: page1})
    rows = rp.fetch_funding_rows(ex, SYM, since_ms=2_000_000)
    assert len(rows) == 201
    assert rows[-1] == {"timestamp": 5_000_000, "symbol": SYM, "paid": 0.25}
    assert ex.client.calls[0][1] == 200 and ex.client.calls[1][2] == {"offset": 200}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_reconcile_phemex.py -q`
Expected: new tests FAIL with AttributeError.

- [ ] **Step 3: Implement**

Replace `load_closed_trades`, `apply_fee_fixes`, and `main()` in `scripts/reconcile_phemex.py` with:

```python
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
    unmatched and never patched (they did not exist on Phemex)."""
    patches: list[dict] = []
    unmatched: list[dict] = []
    claimed: set = set()
    for t in sorted(rows, key=lambda r: (r.get("closed_at") or 0)):
        sym = t.get("symbol") or "?"
        entry_fills, exit_fills, phemex_fee = match_trade_to_fills(t, fills_by_sym.get(sym, []), claimed)
        if not entry_fills and not exit_fills:
            unmatched.append(t)
            continue
        local_fee = t.get("fees_usdt")
        new_fee = None
        if local_fee is None or abs(float(local_fee) - phemex_fee) > FEE_TOLERANCE_USDT:
            new_fee = phemex_fee
        local_funding = float(t.get("funding_usdt") or 0)
        paid = float(funding_by_key.get(trade_key(t), 0.0))
        new_funding = None
        if abs(paid - local_funding) > FUNDING_TOLERANCE_USDT or not t.get("funding_source"):
            new_funding = paid
        if new_fee is None and new_funding is None:
            continue
        patches.append({"key": trade_key(t), "fees_usdt": new_fee, "funding_usdt": new_funding,
                        "local_fee": float(local_fee or 0), "local_funding": local_funding})
    return patches, unmatched


def apply_patches(path: Path, patches: list[dict]) -> int:
    """Patch closed_trades rows in `path` with Phemex-truth fees/funding.
    Atomic temp+rename; only closed_trades rows are edited, everything else in
    the file (positions, peak) is whatever was on disk at the final re-read.
    Aborts (returns -1) if the bot keeps writing concurrently."""
    if not patches:
        return 0
    by_key = {p["key"]: p for p in patches}
    for attempt in range(5):
        try:
            state = json.loads(path.read_text())
        except Exception as e:
            print(f"[ERROR] cannot read {path.name} for apply: {e}")
            return -1
        closed = state.get("closed_trades") or []
        original_count = len(closed)
        modified = 0
        now = int(time.time())
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
        if modified == 0:
            return 0
        tmp = path.with_suffix(".json.reconcile.tmp")
        tmp.write_text(json.dumps(state))
        try:
            current = json.loads(path.read_text())
        except Exception:
            current = {}
        if len(current.get("closed_trades") or []) != original_count:
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

    grand_unmatched = 0
    grand_patches = 0
    grand_applied = 0
    funding_applied = 0.0
    for path, kind, rows in ledgers:
        funding_by_key = attribute_funding(rows, funding_rows)
        patches, unmatched = build_patches(rows, fills_by_sym, funding_by_key)
        fee_patches = [p for p in patches if p["fees_usdt"] is not None]
        fund_patches = [p for p in patches if p["funding_usdt"] is not None]
        print()
        print(f"--- {path.name} ({kind}): {len(rows)} rows | unmatched {len(unmatched)} | "
              f"fee drift > ${FEE_TOLERANCE_USDT:.2f}: {len(fee_patches)} | funding updates: {len(fund_patches)}")
        for t in unmatched[:10]:
            print(f"  UNMATCHED {_fmt_ts(t.get('closed_at'))} {t.get('symbol'):<18} {t.get('side',''):<5} pnl={t.get('pnl_usdt',0):+.4f}")
        for p in fee_patches[:10]:
            print(f"  FEE  {p['key'][1]:<18} {_fmt_ts(p['key'][2])} local={p['local_fee']:.4f} phemex={p['fees_usdt']:.4f} Δ={p['fees_usdt']-p['local_fee']:+.4f}")
        for p in fund_patches[:10]:
            if abs(p['funding_usdt'] - p['local_funding']) > FUNDING_TOLERANCE_USDT:
                print(f"  FUND {p['key'][1]:<18} {_fmt_ts(p['key'][2])} paid={p['funding_usdt']:+.6f} (was {p['local_funding']:+.6f})")
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
```

Delete the now-unused `load_closed_trades`, `apply_fee_fixes`, and the old per-symbol summary table. Keep `fetch_phemex_fills` and `_fill_fee`. Update the module docstring: ledgers covered, funding sign convention, `--lookback-days`.

Note on the dashboard: `web_dashboard._reconcile_status` looks for lines containing "Total discrepancies" that START with `YYYY-MM-DD HH:MM:SS` — the `stamp` prefix above makes the reconcile panel work; the old script never printed a timestamp on that line.

- [ ] **Step 4: Run tests + compile**

Run: `python3 -m pytest tests/test_reconcile_phemex.py -q && python3 -m py_compile scripts/reconcile_phemex.py`
Expected: 13 passed.

- [ ] **Step 5: Dry-run against the real account (read-only, default mode)**

```bash
cd ~/Desktop/Phmex-S && nice -n 19 python3 scripts/reconcile_phemex.py | tee /tmp/claude-501/reconcile_dry_7d.txt
nice -n 19 python3 scripts/reconcile_phemex.py --lookback-days 100 | tee reports/reconcile_backfill_dryrun_2026-09-07.txt
```
Expected: the 7-day pass lists the 9/4 ETH row (fee 0.097074 → 0.10299678, funding −0.00175251) and the 9/7 ETH row (fee 0.098588 → 0.10444692, funding 0). The 100-day pass should list the 8 low-tier `exchange_close` rows and the 3 `min_margin_skip` rows under FEE, and the 12 live straddler rows under FUND. Any UNMATCHED live row is a finding to report, not to patch.

- [ ] **Step 6: Commit**

```bash
git add scripts/reconcile_phemex.py tests/test_reconcile_phemex.py reports/reconcile_backfill_dryrun_2026-09-07.txt
git commit -m "reconcile: cover slot ledgers, capture funding, patch atomically per file"
```

(The launchd job now runs this version every 15 min with `--apply` on the 7-day window. The 100-day `--apply` waits for Task 7 — see the clobber note there.)

---

### Task 3: RiskManager — merge reconciler-written fields on save

**Files:**
- Modify: `risk_manager.py` (`__init__` ~line 310, `_save_state` line 366, `close_position` TODO at 769-778)
- Test: `tests/test_state_merge_reconciled.py` (new)

**Interfaces:**
- Produces: `RiskManager.RECONCILED_FIELDS` (tuple), `RiskManager._merge_reconciled() -> int`, `RiskManager._last_saved_mtime: float | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_state_merge_reconciled.py
"""_save_state must adopt reconciler-written ledger fields from the state FILE
before overwriting it (2026-09-07). Before this, every reconcile patch was
reverted by the next close and only re-applied inside the 7-day lookback."""
import json
import os
import time

from risk_manager import RiskManager

SYM = "ETH/USDT:USDT"


def _rm(tmp_path):
    rm = RiskManager(state_file=str(tmp_path / "trading_state_5m_mean_revert.json"))
    rm.is_paper = False
    rm._log_prefix = ""
    return rm


def _close_one(rm, exit_px=2450.0):
    rm.open_position(SYM, entry_price=2451.37, margin=15.0, side="short")
    rm.close_position(SYM, exit_price=exit_px, reason="hard_time_exit", fees_usdt=0.097074, mode="live")
    return rm.closed_trades[-1]


def _external_patch(path, **fields):
    state = json.loads(open(path).read())
    state["closed_trades"][0].update(fields)
    time.sleep(0.02)
    with open(path, "w") as f:
        json.dump(state, f)
    os.utime(path, None)


def test_save_merges_reconciled_fields_and_clears_pending(tmp_path):
    rm = _rm(tmp_path)
    row = _close_one(rm)
    row["fees_pending"] = True
    rm._save_state()
    _external_patch(rm.state_file, fees_usdt=0.10299678, fees_source="phemex_reconcile",
                    fees_reconciled_at=1, funding_usdt=-0.00175251,
                    funding_source="phemex_reconcile", funding_reconciled_at=1, net_pnl=0.123)
    rm.open_position("SOL/USDT:USDT", entry_price=100.0, margin=15.0, side="long")  # triggers a save
    merged = rm.closed_trades[0]
    assert merged["fees_usdt"] == 0.10299678
    assert merged["funding_usdt"] == -0.00175251
    assert merged["net_pnl"] == 0.123
    assert merged["fees_source"] == "phemex_reconcile"
    assert "fees_pending" not in merged
    on_disk = json.loads(open(rm.state_file).read())["closed_trades"][0]
    assert on_disk["fees_usdt"] == 0.10299678 and on_disk["funding_usdt"] == -0.00175251


def test_save_skips_merge_when_file_unchanged(tmp_path, monkeypatch):
    rm = _rm(tmp_path)
    _close_one(rm)
    calls = []
    real_open = open

    def spy_open(path, *a, **kw):
        if str(path) == rm.state_file and (not a or a[0] == "r"):
            calls.append(path)
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", spy_open)
    rm._save_state()      # mtime matches what we last wrote → no read
    assert calls == []


def test_merge_does_not_touch_rows_without_source_fields(tmp_path):
    rm = _rm(tmp_path)
    _close_one(rm)
    _external_patch(rm.state_file, fees_usdt=9.99)   # no *_source → not a reconciler write
    rm._save_state()
    assert rm.closed_trades[0]["fees_usdt"] == 0.097074


def test_merge_survives_unreadable_file(tmp_path):
    rm = _rm(tmp_path)
    _close_one(rm)
    time.sleep(0.02)
    with open(rm.state_file, "w") as f:
        f.write("{not json")
    rm._save_state()   # must not raise; rewrites a valid file
    assert json.loads(open(rm.state_file).read())["closed_trades"][0]["fees_usdt"] == 0.097074
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_state_merge_reconciled.py -q`
Expected: first test FAILS (fees_usdt still 0.097074 after save); the spy test may pass by accident — fine.

- [ ] **Step 3: Implement in `risk_manager.py`**

In `RiskManager.__init__`, after `self._log_prefix = ...`:

```python
        # 2026-09-07: mtime of the state file as of OUR last write. If the file
        # changed since, another writer (scripts/reconcile_phemex.py) patched
        # ledger rows and _save_state must merge them before overwriting.
        self._last_saved_mtime: float | None = None
```

Add as a class attribute right under `class RiskManager:`:

```python
    # Ledger fields only the reconciler writes (Phemex-exact fees + funding).
    # _save_state copies these from disk into memory before every write so a
    # close can never revert them (pre-9/7 every patch was clobbered on the
    # next close and re-applied only inside the reconciler's 7-day window).
    RECONCILED_FIELDS = ("fees_usdt", "net_pnl", "fees_source", "fees_reconciled_at",
                         "funding_usdt", "funding_source", "funding_reconciled_at")
```

Add the method before `_save_state`:

```python
    def _merge_reconciled(self) -> int:
        """Adopt reconciler-written fields from the on-disk ledger into memory.
        Cheap: an os.stat per save; the file is only re-read when its mtime
        differs from our last write. Returns rows merged."""
        try:
            mtime = os.path.getmtime(self.state_file)
        except OSError:
            return 0
        if self._last_saved_mtime is not None and mtime == self._last_saved_mtime:
            return 0
        try:
            with open(self.state_file) as f:
                on_disk = json.load(f).get("closed_trades") or []
        except Exception as e:
            logger.warning(f"[STATE] merge skipped — could not read {os.path.basename(self.state_file)}: {e}")
            return 0
        patched = {}
        for t in on_disk:
            if t.get("fees_source") or t.get("funding_source"):
                patched[(t.get("opened_at"), t.get("symbol"), t.get("closed_at"))] = t
        if not patched:
            return 0
        merged = 0
        for t in self.closed_trades:
            src = patched.get((t.get("opened_at"), t.get("symbol"), t.get("closed_at")))
            if src is None:
                continue
            for k in self.RECONCILED_FIELDS:
                if k in src:
                    t[k] = src[k]
            if src.get("fees_source"):
                t.pop("fees_pending", None)
            merged += 1
        if merged:
            logger.debug(f"[STATE] merged {merged} reconciled row(s) from disk")
        return merged
```

In `_save_state`, first line inside the `try:` → `self._merge_reconciled()`; after the `json.dump(...)` line add:

```python
            try:
                self._last_saved_mtime = os.path.getmtime(self.state_file)
            except OSError:
                self._last_saved_mtime = None
```

Replace the `# TODO(U5c spec, 2026-07-23 ...)` comment block above `funding_usdt = 0.0` in `close_position` with:

```python
        # Funding is captured by scripts/reconcile_phemex.py (launchd, every 15 min)
        # from Phemex fetch_funding_history and merged back into this list by
        # _save_state → _merge_reconciled (2026-09-07). Convention: funding_usdt =
        # amount PAID (positive = cost, negative = received), so net = gross - fees - funding.
        # The close path stays API-free; net_pnl is funding-blind for ≤15 min.
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_state_merge_reconciled.py tests/test_paper_fee_model.py tests/test_kill_switches.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add risk_manager.py tests/test_state_merge_reconciled.py
git commit -m "risk_manager: merge reconciler-written fees/funding on save"
```

---

### Task 4: bot.py — exchange-close fee summation + crumb-close real fee

**Files:**
- Modify: `bot.py` (`_sync_exchange_closes` lines 4132-4174; `min_margin_skip` sites at 2633-2640 and 3592-3596)
- Test: `tests/test_sync_close_fills.py` (new)

**Interfaces:**
- Produces: module-level `_close_fills_summary(recent: list, pos) -> tuple[float | None, float]` in `bot.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sync_close_fills.py
"""exchange_close fee capture (2026-09-07): sum ALL reduce-side post-entry fills,
skip Phemex funding-settlement rows, VWAP the exit price; return fee 0.0 when
nothing matched so close_position's estimator floor + fees_pending applies."""
from types import SimpleNamespace

import pytest

from bot import _close_fills_summary


def _tr(ts_s, side, price, amount, fee_cost, trade_type="1"):
    return {"timestamp": int(ts_s * 1000), "side": side, "price": price, "amount": amount,
            "fee": {"cost": fee_cost}, "fees": [{"cost": fee_cost}],
            "info": {"tradeType": trade_type, "action": "13" if trade_type == "4" else "1"}}


def _pos(side="short", opened_at=1000.0):
    return SimpleNamespace(side=side, opened_at=opened_at)


def test_sums_all_reduce_fills_and_vwaps_price():
    recent = [
        _tr(999, "sell", 100.0, 1.0, 0.01),       # entry (before opened_at) — ignored
        _tr(2000, "buy", 101.0, 0.6, 0.036),      # partial close
        _tr(2001, "buy", 103.0, 0.4, 0.025),      # rest of close
    ]
    px, fee = _close_fills_summary(recent, _pos())
    assert fee == pytest.approx(0.061)
    assert px == pytest.approx((101.0 * 0.6 + 103.0 * 0.4) / 1.0)


def test_skips_funding_rows_and_same_side_reentry():
    recent = [
        _tr(1500, "sell", 100.0, 1.0, -0.0017, trade_type="4"),  # funding settlement
        _tr(1600, "sell", 100.0, 1.0, 0.015),                    # a NEW short entry (same side) — not a close
        _tr(2000, "buy", 102.0, 1.0, 0.06),
    ]
    px, fee = _close_fills_summary(recent, _pos())
    assert fee == pytest.approx(0.06) and px == 102.0


def test_no_close_fill_returns_none_and_zero_fee():
    recent = [_tr(999, "sell", 100.0, 1.0, 0.01)]
    assert _close_fills_summary(recent, _pos()) == (None, 0.0)
    assert _close_fills_summary([], _pos()) == (None, 0.0)


def test_fee_cost_none_falls_back_to_fees_list_and_zero():
    recent = [{"timestamp": 2_000_000, "side": "buy", "price": 5.0, "amount": 2.0,
               "fee": {"cost": None}, "fees": [{"cost": 0.004}], "info": {"tradeType": "1"}}]
    assert _close_fills_summary(recent, _pos()) == (5.0, pytest.approx(0.004))
    recent[0]["fees"] = []
    assert _close_fills_summary(recent, _pos()) == (5.0, 0.0)   # → estimator floor downstream
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_sync_close_fills.py -q`
Expected: ImportError on `_close_fills_summary`.

- [ ] **Step 3: Implement**

Add to `bot.py` directly above `def _build_position_owners(main_risk, slots):` (line 455):

```python
def _close_fills_summary(recent: list, pos) -> tuple:
    """(exit_price, fee_total) for a position the exchange closed on its own.

    Uses EVERY post-entry fill on the REDUCE side of pos (short → 'buy', long →
    'sell'), skipping Phemex 8h funding-settlement rows that fetch_my_trades
    interleaves with fills (info.tradeType "4" / action "13"). exit_price is the
    size-weighted average. Returns (None, 0.0) when no close fill is visible yet;
    a 0.0 fee makes close_position substitute _estimate_live_fees + fees_pending
    (never $0), and the reconciler writes the exact number within 15 min.
    Pre-9/7 this summed only the LAST fill (ADA 7/22: $0.015 recorded vs ~$0.10).
    """
    entry_ts_ms = int(getattr(pos, "opened_at", 0) * 1000)
    reduce_side = "buy" if getattr(pos, "side", "") == "short" else "sell"
    fills = []
    for tr in recent or []:
        info = tr.get("info") or {}
        if str(info.get("tradeType")) == "4" or str(info.get("action")) == "13":
            continue
        if (tr.get("timestamp") or 0) <= entry_ts_ms:
            continue
        if tr.get("side") and tr.get("side") != reduce_side:
            continue
        fills.append(tr)
    if not fills:
        return None, 0.0
    fee_total = 0.0
    notional = 0.0
    qty = 0.0
    last_px = 0.0
    for tr in sorted(fills, key=lambda t: t.get("timestamp") or 0):
        fee = tr.get("fee") or {}
        if fee.get("cost") is not None:
            fee_total += abs(float(fee.get("cost") or 0))
        else:
            for f in tr.get("fees") or []:
                if f.get("cost") is not None:
                    fee_total += abs(float(f.get("cost") or 0))
        px = float(tr.get("price") or 0)
        amt = float(tr.get("amount") or 0)
        if px > 0:
            last_px = px
            if amt > 0:
                notional += px * amt
                qty += amt
    exit_px = (notional / qty) if qty > 0 else (last_px if last_px > 0 else None)
    return exit_px, fee_total
```

In `_sync_exchange_closes`, replace everything from the `# TODO(U5c spec, 2026-07-23 — NOT shipped ...` comment through the matching `except Exception:\n                        pass` (lines 4132-4174) with:

```python
                    # Fee/price from ALL reduce-side post-entry fills (funding rows
                    # skipped, same-side re-entries excluded); 0.0 → estimator floor.
                    sync_fee = 0.0
                    try:
                        recent = self.exchange.client.fetch_my_trades(symbol, limit=10)
                        fill_px, sync_fee = _close_fills_summary(recent, pos)
                        if fill_px:
                            exit_price = fill_px
                            logger.info(f"[SYNC] {symbol} real exit fill: {exit_price} (fee {sync_fee:.5f})")
                        else:
                            logger.debug(f"[SYNC] {symbol} no post-entry close fill found yet — using mark price")
                    except Exception:
                        pass
```

Main-bot crumb close (line ~2633): change

```python
                        close_ok = (
                            self.exchange.close_long(symbol, fill_amount)
                            if direction == "long"
                            else self.exchange.close_short(symbol, fill_amount)
                        )
                        if close_ok:
                            self.risk.close_position(symbol, fill_price, "min_margin_skip")
```
to
```python
                        close_order = (
                            self.exchange.close_long(symbol, fill_amount)
                            if direction == "long"
                            else self.exchange.close_short(symbol, fill_amount)
                        )
                        if close_order:
                            # Real exit-leg fee (crumb = one immediate reduce-only market
                            # order); 0.0 → estimator floor; reconciler adds the entry leg.
                            self.risk.close_position(symbol, fill_price, "min_margin_skip",
                                                     fees_usdt=self.exchange.extract_order_fee(close_order, symbol))
```

Slot crumb close (line ~3592): change

```python
                                closed = (self.exchange.close_long(symbol, fill_amount) if direction == "long"
                                          else self.exchange.close_short(symbol, fill_amount))
                                if closed:
                                    slot.risk.close_position(symbol, fill_price, "min_margin_skip", mode="live")
```
to
```python
                                closed = (self.exchange.close_long(symbol, fill_amount) if direction == "long"
                                          else self.exchange.close_short(symbol, fill_amount))
                                if closed:
                                    slot.risk.close_position(symbol, fill_price, "min_margin_skip", mode="live",
                                                             fees_usdt=self.exchange.extract_order_fee(closed, symbol))
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_sync_close_fills.py tests/test_live_slot.py tests/test_kill_switches.py -q`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add bot.py tests/test_sync_close_fills.py
git commit -m "bot: sum all exchange-close fills for fees, real fee on crumb closes"
```

---

### Task 5: Propagation — daily report shows funding

**Files:**
- Modify: `scripts/daily_report.py` (lines 51-55 helper, 184, 227, 384)

- [ ] **Step 1: Add helper under `_fee`**

```python
def _funding(t):
    """Funding PAID on the trade (positive = cost, negative = received); 0 if unset."""
    f = t.get("funding_usdt")
    return f if f is not None else 0
```

- [ ] **Step 2: Compute and print**

After `today_fees = sum(_fee(t) for t in today_trades)` add `today_funding = sum(_funding(t) for t in today_trades)`.
In the markdown block, after `- Fees: ${today_fees:.2f}` add `- Funding: ${today_funding:+.4f}`.
In the Telegram block, change `f"Fees: ${sum(_fee(t) for t in today_trades):.2f}\n"` to `f"Fees: ${sum(_fee(t) for t in today_trades):.2f} | Funding: ${sum(_funding(t) for t in today_trades):+.4f}\n"`.

- [ ] **Step 3: Verify**

Run: `python3 -m py_compile scripts/daily_report.py && python3 -m pytest tests/ -q -k "daily_report or report" `
Expected: compiles; any existing report tests pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/daily_report.py
git commit -m "daily_report: show funding next to fees"
```

Dashboard: `web_dashboard.py:1555` already renders `funding_usdt` per blotter row and `_net_pnl` reads `net_pnl`, so funding flows into every card once the ledger carries it. No change.

---

### Task 6: Full suite, audit, pre-restart gate

- [ ] **Step 1: Full suite**

Run: `cd ~/Desktop/Phmex-S && nice -n 19 python3 -m pytest tests/ -q`
Expected: baseline count + 19 new, 0 failed.

- [ ] **Step 2: Audit agents (parallel)** — one reviewer per changed file (`risk_manager.py`, `bot.py`, `scripts/reconcile_phemex.py`), each given the diff and the spec bullets above; a fourth agent re-derives the dry-run numbers from `trading_state_5m_mean_revert.json` + the probe output independently.

- [ ] **Step 3: `/pre-restart-audit`** then STOP and present the checklist. The bot restart needs the owner's "go".

---

### Task 7: After the restart — one-time 100-day backfill

Why after: with PID 78531 still running the old `_save_state`, a 100-day `--apply` would be reverted on the next close for rows older than 7 days and never re-applied.

- [ ] **Step 1: Confirm new PID loaded merge code**

```bash
pgrep -fil "Python main.py"; grep -c "_merge_reconciled" ~/Desktop/Phmex-S/risk_manager.py
```

- [ ] **Step 2: Apply**

```bash
cd ~/Desktop/Phmex-S && nice -n 19 python3 scripts/reconcile_phemex.py --lookback-days 100 --apply | tee reports/reconcile_backfill_apply_2026-09-07.txt
```

- [ ] **Step 3: Verify the MR ledger**

```bash
python3 - <<'EOF'
import json
rows = json.load(open("trading_state_5m_mean_revert.json"))["closed_trades"]
live = [t for t in rows if t.get("mode") == "live"]
print("live rows", len(live), "| funding stamped", sum(1 for t in live if t.get("funding_source")),
      "| fees exact", sum(1 for t in live if t.get("fees_source")), "| pending", sum(1 for t in live if t.get("fees_pending")))
print("sum fees", round(sum(t["fees_usdt"] for t in live), 4), "sum funding", round(sum(t["funding_usdt"] for t in live), 6),
      "sum net", round(sum(t["net_pnl"] for t in live), 4))
EOF
```
Expected: the 12 straddler rows carry nonzero funding; `fees_pending` count 0; the three crumb rows' fees drop from 0.105/0.21/0.105 to their real exit-leg + entry-leg fills. Report before/after sums to the owner (before: fees 2.7804, funding 0, net 1.1507 on 34 live rows).

- [ ] **Step 4: Memory + TASKS.md review section; update `project_bot_backlog_2026-09-07.md` (items 1+2 closed, sign convention, merge-on-save).**
