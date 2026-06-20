# ST2.0 Lab Phase 2 — Self-Closing Confirm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/st2_lab/confirm.py` — an offline, self-closing adjudicator that registers Step-1 gate survivors (+ a permanent `LIVE` entry) and each daily run advances a SCREEN (forward-OOS replay) and an authoritative TRUTH (real live-fill subset) verdict, auto-emitting CONFIRM/REJECT without ever touching live.

**Architecture:** One new pure-stdlib module wired into `loop.run_iteration`. It reuses the shipped lab primitives (`walkforward`, `evaluator._replay_adverse` via `evaluate_with_trades`, `stats`, `safe_exec`, `real_trades`, `proposer.config_hash`, `champion` store). State lives in `champion.json` (`confirm_registry`, `live_config`). Verdicts flow to champion lineage + a `docs/fix-proposals/` doc. Never imports `bot.py`; CONFIRM is a human-gated recommendation, never an auto-deploy.

**Tech Stack:** Python 3.14, stdlib only, pytest (bare `assert` + `test_*` functions, no unittest/pytest imports unless needed for `tmp_path`/`monkeypatch` fixtures which are built-in).

## Global Constraints

- **Isolation invariant:** `confirm.py` must NOT import `bot.py`, `main.py`, or `loop.py` (avoid the circular import — `loop.py` imports `confirm`). It imports only `config`, `walkforward`, `evaluator`, `stats`, `safe_exec`, `real_trades`, `features`, `proposer`, `champion`.
- **No live touch:** no order placement, no `.env` / live-state writes, no network. Generated filter code runs ONLY through `safe_exec.compile_filter` (AST interpreter).
- **Determinism:** every function is deterministic; `bootstrap_diff_ci` is always called with `seed=0`. No `Date.now`/`random` outside seeded stats.
- **Economics/gate keys come from config:** reuse `champ["loop"]` keys `wf_windows`, `wf_embargo_secs`, `wf_min_trades`, `dsr_min`, `confirm_sample`; new keys added in Task 1.
- **Test logging:** run pytest with `PHMEX_LOG_FILE=logs/test_run.log` (per `tests/conftest.py`) so no test writes into the live `bot.log`.
- **Defensive defaults:** existing `champion.json` predates the new keys — every accessor uses `champ.setdefault(...)`; never assume a key exists.
- **Branch first:** before Task 1, create a feature branch: `git checkout -b phase2-self-closing-confirm`.

---

### Task 1: Registry + data model + kind classification + live-config eligibility

**Files:**
- Modify: `scripts/st2_lab/config.py` (add `DEFAULT_CHAMPION` keys + `DEFAULTS["confirm"]` block)
- Create: `scripts/st2_lab/confirm.py`
- Test: `tests/test_st2_lab_confirm.py`

**Interfaces:**
- Consumes: `proposer.config_hash(cfg) -> str`; `features.feature_names() -> tuple`.
- Produces:
  - `confirm.classify_kind(cfg: dict, live_config: dict | None) -> str` ("filter" | "base")
  - `confirm.truth_eligible(cfg: dict, live_config: dict | None) -> bool`
  - `confirm.ensure_live_entry(champ: dict, registered_ts: int) -> None`
  - `confirm.register_if_survivor(champ: dict, cfg: dict, registered_ts: int, run_count: int) -> bool`
  - Registry hypothesis shape (dict): keys `id, config, kind, registered_ts, registered_run, screen, truth, verdict`.

- [ ] **Step 1: Add config keys.** In `scripts/st2_lab/config.py`, inside `DEFAULT_CHAMPION` (after the `"loop"` line) add two keys, and inside `DEFAULTS` add a `confirm` block:

```python
# in DEFAULT_CHAMPION dict:
    "live_config": None,        # the live ST2.0 config (params+filters+exits); human-set at deploy
    "confirm_registry": [],     # Phase 2: hypotheses under forward adjudication
```

```python
# in DEFAULTS dict (after "dsr_min": 0.90,):
    # Phase 2 self-closing confirm
    "screen_min_trades": 40,    # forward-OOS replay trades before SCREEN self-closes
    "registry_cap": 50,         # max non-LIVE hypotheses retained in confirm_registry
```

- [ ] **Step 2: Write the failing test** for `truth_eligible` + `classify_kind` + registry. Create `tests/test_st2_lab_confirm.py`:

```python
"""TDD for scripts/st2_lab/confirm.py — self-closing forward adjudication."""
import os
import sys

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BOT_DIR, "scripts"))

from st2_lab import confirm as CF      # noqa: E402

LIVE = {"params": {"imb_min": 0.30, "br_min": 0.60, "min_trades": 15,
                   "hold_secs": 900, "sl_pct": 1.2, "tp_pct": 1.6}, "filters": []}


def _cfg(imb=0.30, br=0.60, mt=15, sl=1.2, tp=1.6, hold=900, filters=None):
    return {"params": {"imb_min": imb, "br_min": br, "min_trades": mt,
                       "hold_secs": hold, "sl_pct": sl, "tp_pct": tp},
            "filters": filters or [], "symbols": None}


def test_truth_eligible_stricter_entry_same_exits_rawfilter():
    cfg = _cfg(imb=0.35, filters=[{"code": "cvd_slope <= -0.3"}])  # stricter + raw filter
    assert CF.truth_eligible(cfg, LIVE) is True
    assert CF.classify_kind(cfg, LIVE) == "filter"


def test_truth_ineligible_when_entry_looser():
    cfg = _cfg(imb=0.25)               # looser than live 0.30 -> admits setups not in real data
    assert CF.truth_eligible(cfg, LIVE) is False
    assert CF.classify_kind(cfg, LIVE) == "base"


def test_truth_ineligible_when_exits_differ():
    cfg = _cfg(tp=2.0)                 # different exit -> realized net can't be reused
    assert CF.truth_eligible(cfg, LIVE) is False


def test_truth_ineligible_engineered_feature_filter():
    cfg = _cfg(filters=[{"code": "imb_mean >= 0.4"}])  # engineered feature absent on real recs
    assert CF.truth_eligible(cfg, LIVE) is False


def test_truth_ineligible_without_live_config():
    cfg = _cfg(imb=0.35)
    assert CF.truth_eligible(cfg, None) is False
    assert CF.classify_kind(cfg, None) == "base"


def test_register_if_survivor_adds_and_dedups():
    champ = {"live_config": LIVE}
    cfg = _cfg(imb=0.35)
    assert CF.register_if_survivor(champ, cfg, registered_ts=1000, run_count=3) is True
    assert CF.register_if_survivor(champ, cfg, registered_ts=2000, run_count=4) is False  # dup hash
    reg = champ["confirm_registry"]
    assert len(reg) == 1
    h = reg[0]
    assert h["kind"] == "filter"
    assert h["registered_ts"] == 1000 and h["registered_run"] == 3
    assert h["verdict"] == "accruing"
    assert h["screen"]["status"] == "accruing" and h["truth"]["status"] == "accruing"


def test_ensure_live_entry_idempotent():
    champ = {"live_config": LIVE}
    CF.ensure_live_entry(champ, registered_ts=500)
    CF.ensure_live_entry(champ, registered_ts=999)
    live = [h for h in champ["confirm_registry"] if h["id"] == "LIVE"]
    assert len(live) == 1
    assert live[0]["truth"]["applicable"] is True   # LIVE is always TRUTH-applicable
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/test_st2_lab_confirm.py -q`
Expected: FAIL — `ImportError: cannot import name 'confirm'`.

- [ ] **Step 4: Write minimal implementation.** Create `scripts/st2_lab/confirm.py`:

```python
"""Self-closing forward adjudication for ST2.0 lab hypotheses (Phase 2).

Registers Step-1 gate survivors (+ a permanent LIVE entry) and, each daily run,
advances a SCREEN (forward-OOS replay, "screening NOT truth") and an authoritative
TRUTH (real live-fill subset) verdict, auto-closing accruing -> confirm/reject.

ISOLATION: pure stdlib; never imports bot.py / main.py / loop.py. A CONFIRM is a
human-gated recommendation — this module never deploys anything.
"""
from __future__ import annotations

from . import config as C
from . import features as feat
from . import proposer

_EXIT_KEYS = ("sl_pct", "tp_pct", "hold_secs")
_ENTRY_KEYS = ("imb_min", "br_min", "min_trades")


def _raw_field_filters_only(cfg: dict) -> bool:
    """True if no filter code references an engineered features.py key (those are
    undefined on the single-snapshot real-trade records, so TRUTH can't judge them)."""
    eng = feat.feature_names()
    for f in cfg.get("filters", []) or []:
        code = f.get("code") if isinstance(f, dict) else f
        if any(name in (code or "") for name in eng):
            return False
    return True


def truth_eligible(cfg: dict, live_config: dict | None) -> bool:
    """TRUTH-judgeable on existing real trades iff: live baseline known, exits equal
    live, entry stricter-or-equal live, and filters use raw fields only."""
    if not live_config:
        return False
    lp, cp = live_config.get("params", {}), cfg.get("params", {})
    if any(cp.get(k) != lp.get(k) for k in _EXIT_KEYS):
        return False
    if any((cp.get(k, 0) or 0) < (lp.get(k, 0) or 0) for k in _ENTRY_KEYS):
        return False
    return _raw_field_filters_only(cfg)


def classify_kind(cfg: dict, live_config: dict | None) -> str:
    return "filter" if truth_eligible(cfg, live_config) else "base"


def _new_hypothesis(hid: str, cfg: dict, kind: str, registered_ts: int,
                    run_count: int, truth_applicable: bool) -> dict:
    return {
        "id": hid,
        "config": {"params": dict(cfg.get("params", {})),
                   "filters": list(cfg.get("filters", []) or []),
                   "symbols": cfg.get("symbols")},
        "kind": kind,
        "registered_ts": int(registered_ts),
        "registered_run": int(run_count),
        "screen": {"trades": 0, "expectancy": 0.0, "deflated_sharpe": 0.0,
                   "status": "accruing", "updated_ts": 0},
        "truth": {"applicable": bool(truth_applicable), "considered": 0, "kept": 0,
                  "dropped": 0, "expectancy": 0.0, "ci": [0.0, 0.0],
                  "status": "accruing", "updated_ts": 0},
        "verdict": "accruing",
    }


def ensure_live_entry(champ: dict, registered_ts: int) -> None:
    """Guarantee a permanent id=='LIVE' registry entry (TRUTH = all real trades)."""
    reg = champ.setdefault("confirm_registry", [])
    if any(h["id"] == "LIVE" for h in reg):
        return
    live_cfg = champ.get("live_config") or {"params": {}, "filters": [], "symbols": None}
    reg.append(_new_hypothesis("LIVE", live_cfg, "live", registered_ts,
                               champ.get("run_count", 0), truth_applicable=True))


def register_if_survivor(champ: dict, cfg: dict, registered_ts: int, run_count: int) -> bool:
    """Add cfg to confirm_registry (deduped by config_hash). Returns True if new."""
    reg = champ.setdefault("confirm_registry", [])
    hid = proposer.config_hash(cfg)
    if any(h["id"] == hid for h in reg):
        return False
    live_config = champ.get("live_config")
    kind = classify_kind(cfg, live_config)
    reg.append(_new_hypothesis(hid, cfg, kind, registered_ts, run_count,
                               truth_applicable=truth_eligible(cfg, live_config)))
    # bound non-LIVE entries (keep newest by registered_run)
    cap = champ.get("loop", {}).get("registry_cap", C.DEFAULTS["registry_cap"])
    non_live = [h for h in reg if h["id"] != "LIVE"]
    if len(non_live) > cap:
        non_live.sort(key=lambda h: h["registered_run"])
        drop = {id(h) for h in non_live[:len(non_live) - cap]}
        champ["confirm_registry"] = [h for h in reg if id(h) not in drop]
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/test_st2_lab_confirm.py -q`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/st2_lab/config.py scripts/st2_lab/confirm.py tests/test_st2_lab_confirm.py
git commit -m "feat(st2-lab): Phase 2 Task 1 — confirm registry + eligibility"
```

---

### Task 2: SCREEN verdict — forward-OOS replay

**Files:**
- Modify: `scripts/st2_lab/confirm.py`
- Test: `tests/test_st2_lab_confirm.py`

**Interfaces:**
- Consumes: `walkforward.walk_forward_splits(by_symbol, n_windows, embargo_secs)`; `evaluator.evaluate_with_trades(cfg, by_symbol, loop_cfg, adverse) -> (Metrics, trades)`; `stats.deflated_sharpe_ratio(...)`; `config.ADVERSE_FILL`.
- Produces: `confirm.screen_verdict(hyp: dict, by_symbol: dict, loop_cfg: dict) -> dict` (mutates and returns `hyp["screen"]`). Uses only snapshots with `ts > hyp["registered_ts"]`.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_st2_lab_confirm.py`:

```python
def _stream(symbol, n, start_ts, price0=100.0, drift=0.0, imb=0.4, br=0.7, tc=20):
    return {symbol: [{"ts": start_ts + i * 75, "symbol": symbol,
                      "price": price0 + drift * i, "imbalance": imb, "spread_pct": 0.05,
                      "buy_ratio": br, "trade_count": tc, "cvd_slope": -0.5,
                      "large_trade_bias": 0.0, "divergence_bullish": False,
                      "divergence_bearish": False, "hour": 12} for i in range(n)]


def _loop_cfg(**kw):
    base = {"wf_windows": 3, "wf_embargo_secs": 0, "wf_min_trades": 1,
            "dsr_min": 0.0, "screen_min_trades": 3, "confirm_sample": 5}
    base.update(kw); return base


def test_screen_uses_only_forward_rows():
    # registered_ts at 5000: rows before are search data and must be ignored
    by = _stream("ETH/USDT:USDT", 200, start_ts=0)
    hyp = CF._new_hypothesis("h1", {"params": {"imb_min": 0.30, "br_min": 0.60,
        "min_trades": 15, "hold_secs": 900, "sl_pct": 1.2, "tp_pct": 1.6},
        "filters": [], "symbols": None}, "filter", registered_ts=5000, run_count=1,
        truth_applicable=True)
    s = CF.screen_verdict(hyp, by, _loop_cfg())
    # every trade the screen scored must come from ts > 5000 (no leakage from search window)
    assert s["status"] in ("accruing", "pass", "fail")
    assert s["updated_ts"] >= 5000


def test_screen_accruing_below_threshold():
    by = _stream("ETH/USDT:USDT", 6, start_ts=0)   # too few forward trades
    hyp = CF._new_hypothesis("h2", {"params": {"imb_min": 0.30, "br_min": 0.60,
        "min_trades": 15, "hold_secs": 900, "sl_pct": 1.2, "tp_pct": 1.6},
        "filters": [], "symbols": None}, "filter", registered_ts=0, run_count=1,
        truth_applicable=True)
    s = CF.screen_verdict(hyp, by, _loop_cfg(screen_min_trades=999))
    assert s["status"] == "accruing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/test_st2_lab_confirm.py -q -k screen`
Expected: FAIL — `AttributeError: module 'st2_lab.confirm' has no attribute 'screen_verdict'`.

- [ ] **Step 3: Write minimal implementation.** Add to `scripts/st2_lab/confirm.py` (imports at top + function):

```python
# add to the import block:
from . import walkforward as wf
from . import stats
from .evaluator import evaluate_with_trades

_ADVERSE = dict(C.ADVERSE_FILL, enabled=True)


def _forward(by_symbol: dict, after_ts: int) -> dict:
    out = {}
    for sym, recs in by_symbol.items():
        kept = [r for r in recs if r.get("ts", 0) > after_ts]
        if kept:
            out[sym] = kept
    return out


def screen_verdict(hyp: dict, by_symbol: dict, loop_cfg: dict) -> dict:
    """Forward-OOS replay on snapshots with ts > registered_ts. Self-closes to
    'pass' (walk-forward majority-positive AND deflated-Sharpe >= dsr_min) or 'fail'
    once >= screen_min_trades forward trades exist; else 'accruing'. SCREEN is
    'screening, NOT truth' (modeled adverse fills)."""
    s = hyp["screen"]
    fwd = _forward(by_symbol, hyp["registered_ts"])
    cfg = hyp["config"]
    n_windows = loop_cfg.get("wf_windows", C.DEFAULTS["wf_windows"])
    embargo = loop_cfg.get("wf_embargo_secs", C.DEFAULTS["wf_embargo_secs"])
    min_tr = loop_cfg.get("wf_min_trades", C.DEFAULTS["wf_min_trades"])
    dsr_min = loop_cfg.get("dsr_min", C.DEFAULTS["dsr_min"])
    need = loop_cfg.get("screen_min_trades", C.DEFAULTS["screen_min_trades"])

    win_exps, total_trades, sharpes = [], 0, []
    try:
        splits = wf.walk_forward_splits(fwd, n_windows, embargo) if fwd else []
    except ValueError:
        splits = []
    for sp in splits:
        m, trades = evaluate_with_trades(cfg, sp["test"], loop_cfg, adverse=_ADVERSE)
        if m.trades >= min_tr:
            win_exps.append(m.expectancy)
            total_trades += m.trades
            nets = [t["net"] for t in trades]
            mean = sum(nets) / len(nets)
            sd = (sum((x - mean) ** 2 for x in nets) / len(nets)) ** 0.5
            sharpes.append(mean / sd if sd > 0 else 0.0)

    s["trades"] = total_trades
    s["expectancy"] = round(sum(win_exps) / len(win_exps), 6) if win_exps else 0.0
    s["updated_ts"] = max([hyp["registered_ts"]] +
                          [r["ts"] for recs in fwd.values() for r in recs[-1:]])
    if total_trades < need or not win_exps:
        s["status"] = "accruing"
        return s
    majority_pos = sum(1 for e in win_exps if e > 0) > len(win_exps) / 2
    agg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0
    var_sh = (sum((x - agg_sharpe) ** 2 for x in sharpes) / len(sharpes)) if len(sharpes) > 1 else 1.0
    dsr = stats.deflated_sharpe_ratio(agg_sharpe, max(total_trades, 2),
                                      max(len(sharpes), 1), var_sh or 1.0)
    s["deflated_sharpe"] = round(dsr, 6)
    s["status"] = "pass" if (majority_pos and dsr >= dsr_min) else "fail"
    return s
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/test_st2_lab_confirm.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/st2_lab/confirm.py tests/test_st2_lab_confirm.py
git commit -m "feat(st2-lab): Phase 2 Task 2 — SCREEN forward-OOS verdict"
```

---

### Task 3: TRUTH verdict — real-fill subset

**Files:**
- Modify: `scripts/st2_lab/confirm.py`
- Test: `tests/test_st2_lab_confirm.py`

**Interfaces:**
- Consumes: `safe_exec.compile_filter(code) -> callable(ctx)->bool` (raises `safe_exec.Rejection`); `stats.bootstrap_diff_ci(a, b, seed=0) -> (lo, hi)`.
- Produces: `confirm.truth_verdict(hyp: dict, real_records: list[dict], live_config: dict | None, loop_cfg: dict) -> dict` (mutates and returns `hyp["truth"]`). `hyp["id"]=="LIVE"` → all real records; filter-kind → the kept subset; else `applicable=False`.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_st2_lab_confirm.py`:

```python
def _real(imb, br, net, tc=20, cvd=-0.5):
    return {"imbalance": imb, "spread_pct": 0.05, "buy_ratio": br, "trade_count": tc,
            "cvd_slope": cvd, "large_trade_bias": 0.0, "divergence_bullish": False,
            "divergence_bearish": False, "hour": 12, "net": net}


def test_truth_live_uses_all_real_trades():
    champ = {"live_config": LIVE}
    CF.ensure_live_entry(champ, registered_ts=0)
    hyp = champ["confirm_registry"][0]
    reals = [_real(0.4, 0.7, +1.0), _real(0.4, 0.7, -0.5), _real(0.4, 0.7, +2.0)]
    t = CF.truth_verdict(hyp, reals, LIVE, _loop_cfg(confirm_sample=2))
    assert t["applicable"] is True
    assert t["kept"] == 3 and t["dropped"] == 0
    assert abs(t["expectancy"] - (1.0 - 0.5 + 2.0) / 3) < 1e-9


def test_truth_filter_judges_kept_subset_only():
    # candidate adds a raw filter cvd_slope <= -0.4; only trades passing it are kept
    cfg = _cfg(imb=0.35, filters=[{"code": "cvd_slope <= -0.4"}])
    hyp = CF._new_hypothesis(CF.proposer.config_hash(cfg), cfg, "filter",
                             registered_ts=0, run_count=1, truth_applicable=True)
    reals = [_real(0.4, 0.7, +3.0, cvd=-0.5),   # kept (cvd -0.5 <= -0.4)
             _real(0.4, 0.7, -9.0, cvd=-0.1),   # dropped (cvd -0.1 > -0.4)
             _real(0.4, 0.7, +1.0, cvd=-0.6)]   # kept
    t = CF.truth_verdict(hyp, reals, LIVE, _loop_cfg(confirm_sample=2))
    assert t["kept"] == 2 and t["dropped"] == 1
    assert abs(t["expectancy"] - (3.0 + 1.0) / 2) < 1e-9   # the -9.0 loser is excluded


def test_truth_accruing_below_confirm_sample():
    champ = {"live_config": LIVE}; CF.ensure_live_entry(champ, 0)
    hyp = champ["confirm_registry"][0]
    t = CF.truth_verdict(hyp, [_real(0.4, 0.7, +1.0)], LIVE, _loop_cfg(confirm_sample=5))
    assert t["status"] == "accruing"


def test_truth_confirm_when_ci_above_zero():
    champ = {"live_config": LIVE}; CF.ensure_live_entry(champ, 0)
    hyp = champ["confirm_registry"][0]
    reals = [_real(0.4, 0.7, +1.0) for _ in range(40)]   # all winners -> CI lower bound > 0
    t = CF.truth_verdict(hyp, reals, LIVE, _loop_cfg(confirm_sample=10))
    assert t["status"] == "confirm"
    assert t["ci"][0] > 0


def test_truth_reject_when_ci_below_zero():
    champ = {"live_config": LIVE}; CF.ensure_live_entry(champ, 0)
    hyp = champ["confirm_registry"][0]
    reals = [_real(0.4, 0.7, -1.0) for _ in range(40)]   # all losers -> CI upper bound < 0
    t = CF.truth_verdict(hyp, reals, LIVE, _loop_cfg(confirm_sample=10))
    assert t["status"] == "reject"
    assert t["ci"][1] < 0


def test_truth_inapplicable_for_base_candidate():
    cfg = _cfg(imb=0.25)   # looser -> base -> not TRUTH-judgeable
    hyp = CF._new_hypothesis("b1", cfg, "base", registered_ts=0, run_count=1,
                             truth_applicable=False)
    t = CF.truth_verdict(hyp, [_real(0.4, 0.7, +1.0) for _ in range(40)], LIVE, _loop_cfg())
    assert t["applicable"] is False
    assert t["status"] == "accruing"   # never closes on real fills
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/test_st2_lab_confirm.py -q -k truth`
Expected: FAIL — `AttributeError: ... has no attribute 'truth_verdict'`.

- [ ] **Step 3: Write minimal implementation.** Add to `scripts/st2_lab/confirm.py`:

```python
# add to the import block:
from . import safe_exec

_ENTRY = ("imb_min", "br_min", "min_trades")


def _entry_ok(rec: dict, p: dict) -> bool:
    return (rec.get("imbalance", 0.0) >= p.get("imb_min", 0.0)
            and rec.get("buy_ratio", 0.0) >= p.get("br_min", 0.0)
            and rec.get("trade_count", 0) >= p.get("min_trades", 0))


def _passes_candidate(rec: dict, cfg: dict, filter_fns) -> bool:
    if not _entry_ok(rec, cfg.get("params", {})):
        return False
    for fn in filter_fns:
        if not fn(rec):
            return False
    return True


def truth_verdict(hyp: dict, real_records: list, live_config: dict | None,
                  loop_cfg: dict) -> dict:
    """Real-fill verdict. LIVE -> all real trades. Filter-kind -> the kept subset
    (entry + raw filters applied to each real trade's recorded conditions). Base /
    ineligible -> applicable False, stays accruing. Self-closes at >= confirm_sample
    kept: confirm (CI lower > 0) / reject (CI upper < 0) / else accruing."""
    t = hyp["truth"]
    need = loop_cfg.get("confirm_sample", C.DEFAULTS["confirm_sample"])
    t["considered"] = len(real_records)

    if hyp["id"] == "LIVE":
        kept = list(real_records)
    elif hyp.get("truth", {}).get("applicable") and truth_eligible(hyp["config"], live_config):
        try:
            fns = [safe_exec.compile_filter(f.get("code") if isinstance(f, dict) else f)
                   for f in hyp["config"].get("filters", []) or []]
        except safe_exec.Rejection:
            t["applicable"] = False
            t["status"] = "accruing"
            return t
        kept = [r for r in real_records if _passes_candidate(r, hyp["config"], fns)]
    else:
        t["applicable"] = False
        t["status"] = "accruing"
        return t

    t["applicable"] = True
    t["kept"] = len(kept)
    t["dropped"] = len(real_records) - len(kept)
    nets = [float(r.get("net", 0.0)) for r in kept]
    t["expectancy"] = round(sum(nets) / len(nets), 6) if nets else 0.0
    if len(kept) < need or not nets:
        t["status"] = "accruing"
        t["ci"] = [0.0, 0.0]
        return t
    lo, hi = stats.bootstrap_diff_ci(nets, [0.0], seed=0)
    t["ci"] = [round(lo, 6), round(hi, 6)]
    t["status"] = "confirm" if lo > 0 else ("reject" if hi < 0 else "accruing")
    return t
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/test_st2_lab_confirm.py -q`
Expected: PASS (15 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/st2_lab/confirm.py tests/test_st2_lab_confirm.py
git commit -m "feat(st2-lab): Phase 2 Task 3 — TRUTH real-fill subset verdict"
```

---

### Task 4: tick() orchestration + outputs + loop.py wiring

**Files:**
- Modify: `scripts/st2_lab/confirm.py`
- Modify: `scripts/st2_lab/loop.py` (wire registration + tick into `run_iteration`)
- Test: `tests/test_st2_lab_confirm.py`

**Interfaces:**
- Consumes: `champion.append_lineage(champ, change, metrics, iteration)`; the `passed` survivor list + `run_count` + `cur_epoch` in `loop.run_iteration` (loop.py:263–308).
- Produces: `confirm.tick(champ: dict, by_symbol: dict, real_records: list) -> list[dict]` — advances SCREEN+TRUTH for every registered hypothesis, sets `verdict`, returns the list of NEW verdict transitions `[{"id", "from", "to", "kind", "alert": bool, "msg": str}]` (deduped: only when `verdict` changes). Mutates `champ` in place.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_st2_lab_confirm.py`:

```python
def test_tick_sets_verdict_and_returns_transition_once():
    champ = {"live_config": LIVE, "run_count": 1, "loop": _loop_cfg(confirm_sample=10)}
    CF.ensure_live_entry(champ, registered_ts=0)
    reals = [_real(0.4, 0.7, -1.0) for _ in range(40)]   # LIVE failing real confirmation
    by = {}                                              # no forward snapshots this fixture
    trans = CF.tick(champ, by, reals)
    live = [h for h in champ["confirm_registry"] if h["id"] == "LIVE"][0]
    assert live["verdict"] == "truth_reject"
    assert len(trans) == 1 and trans[0]["id"] == "LIVE" and trans[0]["alert"] is True
    # second identical tick emits NO new transition (dedup on unchanged verdict)
    assert CF.tick(champ, by, reals) == []


def test_tick_truth_authoritative_over_screen():
    champ = {"live_config": LIVE, "run_count": 1, "loop": _loop_cfg(confirm_sample=10)}
    CF.ensure_live_entry(champ, 0)
    reals = [_real(0.4, 0.7, +1.0) for _ in range(40)]
    CF.tick(champ, {}, reals)
    live = [h for h in champ["confirm_registry"] if h["id"] == "LIVE"][0]
    assert live["verdict"] == "truth_confirm"   # real-fill verdict wins
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/test_st2_lab_confirm.py -q -k tick`
Expected: FAIL — `AttributeError: ... has no attribute 'tick'`.

- [ ] **Step 3: Write minimal implementation.** Add to `scripts/st2_lab/confirm.py`:

```python
def _verdict_for(hyp: dict) -> str:
    t, s = hyp["truth"], hyp["screen"]
    if t.get("applicable") and t["status"] in ("confirm", "reject"):
        return "truth_" + t["status"]
    if s["status"] in ("pass", "fail"):
        return "screen_" + s["status"]
    return "accruing"


def tick(champ: dict, by_symbol: dict, real_records: list) -> list:
    """Advance SCREEN + TRUTH for every registered hypothesis; set verdict; return
    NEW verdict transitions (deduped on change). TRUTH is authoritative over SCREEN."""
    loop_cfg = champ.get("loop", dict(C.DEFAULTS))
    live_config = champ.get("live_config")
    transitions = []
    for hyp in champ.setdefault("confirm_registry", []):
        screen_verdict(hyp, by_symbol, loop_cfg)
        truth_verdict(hyp, real_records, live_config, loop_cfg)
        new_v = _verdict_for(hyp)
        old_v = hyp.get("verdict", "accruing")
        hyp["verdict"] = new_v
        if new_v != old_v and new_v != "accruing":
            is_live_reject = (hyp["id"] == "LIVE" and new_v == "truth_reject")
            transitions.append({
                "id": hyp["id"], "from": old_v, "to": new_v, "kind": hyp["kind"],
                "alert": is_live_reject,
                "msg": (f"ST2.0 confirm: {hyp['id']} {old_v} -> {new_v} "
                        f"(truth kept={hyp['truth']['kept']} exp={hyp['truth']['expectancy']:+.4f} "
                        f"ci={hyp['truth']['ci']}; screen={hyp['screen']['status']})"),
            })
    return transitions
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/test_st2_lab_confirm.py -q`
Expected: PASS (17 tests).

- [ ] **Step 5: Wire into `loop.run_iteration`.** In `scripts/st2_lab/loop.py`, add `from . import confirm` to the import block (near line 20). Then, immediately BEFORE the `if not dry_run:` / `champ_store.save(new_champ)` block (loop.py:307), insert:

```python
    # Phase 2 — self-closing confirm: register Step-1 survivors + LIVE, advance verdicts.
    try:
        confirm.ensure_live_entry(new_champ, cur_epoch)
        for c, _tr, _te in passed:
            confirm.register_if_survivor(new_champ, c, cur_epoch, run_count)
        from . import real_trades
        transitions = confirm.tick(new_champ, by_symbol, real_trades.load_real_trades())
        for tr in transitions:
            (logger.warning if tr["alert"] else logger.info)("[CONFIRM] %s", tr["msg"])
            champ_store.append_lineage(new_champ, f"confirm:{tr['id']}:{tr['to']}",
                                       {"verdict": tr["to"]}, run_count)
        result["confirm_transitions"] = [t["msg"] for t in transitions]
    except Exception as e:                       # confirm must never break the search loop
        logger.error("[CONFIRM] tick failed (non-fatal): %s", e, exc_info=True)
```

Note: `passed` (list of `(cfg, tr, te)`) and `cur_epoch` and `run_count` are already in scope at this point in `run_iteration`. `new_champ` is the post-accept champion. After the accept branch pops `_change` from `best_cfg`, the survivor cfgs in `passed` no longer carry `_change`; registration uses `config_hash` which ignores it.

- [ ] **Step 6: Run the FULL suite (regression — confirms the wiring didn't break the loop)**

Run: `PHMEX_LOG_FILE=logs/test_run.log python3 -m pytest tests/ -q`
Expected: PASS, 0 failed (existing st2_lab loop tests + the 17 new confirm tests all green).

- [ ] **Step 7: Real-data smoke (honest end-to-end check, not a test).**

Run:
```bash
cd ~/Desktop/Phmex-S && PHMEX_LOG_FILE=logs/test_run.log python3 -c "
import sys; sys.path.insert(0,'scripts')
from st2_lab import loop, champion, confirm, real_trades, dataset
champ = champion.load()
champ.setdefault('live_config', {'params': {'imb_min':0.30,'br_min':0.60,'min_trades':15,'hold_secs':900,'sl_pct':1.2,'tp_pct':1.6}, 'filters': [], 'symbols': None})
by = dataset.load_dataset(limit=40000)
confirm.ensure_live_entry(champ, champ.get('data_epoch',0))
trans = confirm.tick(champ, by, real_trades.load_real_trades())
live = [h for h in champ['confirm_registry'] if h['id']=='LIVE'][0]
print('LIVE verdict:', live['verdict'], '| truth:', live['truth']['status'],
      'kept', live['truth']['kept'], 'exp', live['truth']['expectancy'],
      '| screen:', live['screen']['status'], 'trades', live['screen']['trades'])
print('transitions:', [t['msg'] for t in trans])
print('OK — confirm runs end-to-end on real data (no champion.json written)')
"
```
Expected: prints a LIVE verdict (likely `accruing` — only 29 real trades, honest); no exception. Does NOT write `champion.json` (the script never calls `champion.save`).

- [ ] **Step 8: Commit**

```bash
git add scripts/st2_lab/confirm.py scripts/st2_lab/loop.py tests/test_st2_lab_confirm.py
git commit -m "feat(st2-lab): Phase 2 Task 4 — confirm.tick orchestration + loop wiring"
```

---

## Post-implementation

- Update `memory/project_st2_honest_lab.md` and the handoff (`.remember/remember.md`) with Phase 2 status.
- The `st2-watch` Telegram digest line + Lab Dashboard for confirm verdicts are explicit spec non-goals (separate units) — a follow-up plan.
- No bot restart / `/pre-restart-audit` needed: `confirm.py` and the `loop.py` change are offline lab code, never imported by the live `main.py` process; the daily 4:30 AM `com.phmex.st2-lab` launchd job auto-picks up the new behavior.

## Self-Review

**Spec coverage:** Registry+gating → Task 1. Live-config provenance/eligibility → Task 1 (`truth_eligible`, `classify_kind`). SCREEN forward-OOS → Task 2. TRUTH filter-subset + LIVE + eligibility + self-close → Task 3. tick orchestration + TRUTH-authoritative + dedup + LIVE-reject alert + lineage output → Task 4. Isolation/determinism → Global Constraints + tests. Dashboard/st2-watch line → explicitly deferred (spec non-goals). No gaps.

**Placeholder scan:** none — every step has real code/commands.

**Type consistency:** `config_hash(cfg)->str`, `register_if_survivor(champ,cfg,registered_ts,run_count)->bool`, `screen_verdict(hyp,by_symbol,loop_cfg)->dict`, `truth_verdict(hyp,real_records,live_config,loop_cfg)->dict`, `tick(champ,by_symbol,real_records)->list` are used identically across tasks and the loop wiring. `bootstrap_diff_ci(a,b,seed=0)->(lo,hi)` and `evaluate_with_trades(cfg,by,loop_cfg,adverse)->(Metrics,trades)` match the shipped signatures verified in the source.
