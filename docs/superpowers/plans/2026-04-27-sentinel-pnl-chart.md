# Sentinel-Era Cumulative PnL Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Sentinel-era cumulative PnL chart with a vertical marker at the 2026-04-26 strategy cull, embedded in the existing Sentinel audit card on the dashboard.

**Architecture:** Single-file additive change to `web_dashboard.py`. Promote the existing `SENTINEL_DEPLOY_TS` constant from inside `render()` to module scope, add a `SENTINEL_CULL_TS` constant, add a chart-generator function `_make_cumulative_pnl_sentinel(trades)` that mirrors the existing `_make_cumulative_pnl()` style, register it in `refresh_charts()`, and embed an `<img>` tag inside the existing Sentinel audit card. The generic `/chart/<name>` route handler at `web_dashboard.py:2219` requires no change.

**Tech Stack:** Python 3.14, matplotlib (Agg backend, already imported), stdlib `datetime`, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-27-sentinel-pnl-chart-design.md`

---

### Task 1: Promote SENTINEL_DEPLOY_TS + add SENTINEL_CULL_TS + cull-index helper (TDD)

**Files:**
- Modify: `web_dashboard.py` (constants near top, around the chart-cache block at line 49-52; remove duplicate computation inside `render()` at line 1364-1366)
- Test: `tests/test_sentinel_chart.py` (create)

The cull-marker index lookup is the only piece of pure logic worth unit-testing. Chart bytes themselves are visual and tested manually per the spec. Following the project's existing pattern (`tests/test_postonly_param.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_sentinel_chart.py`:

```python
"""Tests for Sentinel-era cumulative PnL chart helpers in web_dashboard.py."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web_dashboard import (
    SENTINEL_DEPLOY_TS,
    SENTINEL_CULL_TS,
    _cull_marker_index,
)


def test_sentinel_deploy_ts_matches_2026_04_02_06_01_utc():
    """Sentinel deployed 2026-04-01 23:01 PT = 2026-04-02 06:01 UTC."""
    from datetime import datetime, timezone
    expected = datetime(2026, 4, 2, 6, 1, 0, tzinfo=timezone.utc).timestamp()
    assert SENTINEL_DEPLOY_TS == expected


def test_sentinel_cull_ts_matches_commit_479f879():
    """Strategy cull (Option A) commit 479f879 landed 2026-04-26 19:22:55 PT."""
    from datetime import datetime, timezone
    expected = datetime(2026, 4, 27, 2, 22, 55, tzinfo=timezone.utc).timestamp()
    assert SENTINEL_CULL_TS == expected


def test_cull_marker_index_returns_first_post_cull_index():
    """Index is 1-based, matching the chart's x-axis (trade #1, #2, ...)."""
    trades = [
        {"opened_at": SENTINEL_CULL_TS - 100},  # pre-cull
        {"opened_at": SENTINEL_CULL_TS - 50},   # pre-cull
        {"opened_at": SENTINEL_CULL_TS + 10},   # first post-cull
        {"opened_at": SENTINEL_CULL_TS + 20},   # post-cull
    ]
    assert _cull_marker_index(trades) == 3


def test_cull_marker_index_returns_none_when_no_post_cull_trades():
    trades = [
        {"opened_at": SENTINEL_CULL_TS - 100},
        {"opened_at": SENTINEL_CULL_TS - 50},
    ]
    assert _cull_marker_index(trades) is None


def test_cull_marker_index_returns_none_for_empty_list():
    assert _cull_marker_index([]) is None


def test_cull_marker_index_falls_back_to_closed_at_when_opened_at_missing():
    """Mirrors the existing render-path filter at web_dashboard.py:1369."""
    trades = [
        {"closed_at": SENTINEL_CULL_TS - 50},
        {"closed_at": SENTINEL_CULL_TS + 10},
    ]
    assert _cull_marker_index(trades) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_sentinel_chart.py -v`
Expected: FAIL with `ImportError: cannot import name 'SENTINEL_DEPLOY_TS' from 'web_dashboard'` (or similar — symbols not yet exported).

- [ ] **Step 3: Promote the constant + add new constant + helper**

In `web_dashboard.py`, just below the existing chart-cache block (around line 53, after `_chart_version = 0`), add:

```python
# ── Sentinel-era anchors ─────────────────────────────────────────────────
# Sentinel deployed 2026-04-01 23:01 PT (= 2026-04-02 06:01 UTC), trade #342+
SENTINEL_DEPLOY_TS = datetime(2026, 4, 2, 6, 1, 0, tzinfo=timezone.utc).timestamp()
# Strategy cull (Option A) commit 479f879 landed 2026-04-26 19:22:55 PT
SENTINEL_CULL_TS = datetime(2026, 4, 27, 2, 22, 55, tzinfo=timezone.utc).timestamp()


def _cull_marker_index(sentinel_trades: list[dict]) -> int | None:
    """Return 1-based index of the first post-cull trade, or None if none exist.

    Index is 1-based to match the chart's x-axis convention (trade #1, #2, ...).
    Falls back to ``closed_at`` if ``opened_at`` is missing — mirrors the
    existing filter logic in ``render()``.
    """
    for i, t in enumerate(sentinel_trades, start=1):
        ts = t.get("opened_at") or t.get("closed_at") or 0
        if ts >= SENTINEL_CULL_TS:
            return i
    return None
```

If `datetime` and `timezone` are not yet imported at module top (the existing code imports them locally inside `render()`), add at the top of the file alongside other stdlib imports:

```python
from datetime import datetime, timezone
```

Then remove the now-redundant local computation in `render()`. Locate this block (around line 1364-1366):

```python
    # Sentinel-era audit (deployed 2026-04-01 23:01 PT = 2026-04-02 06:01 UTC, trade #342+)
    from datetime import datetime as _dt, timezone as _tz
    SENTINEL_DEPLOY_TS = _dt(2026, 4, 2, 6, 1, 0, tzinfo=_tz.utc).timestamp()
```

Replace it with:

```python
    # Sentinel-era audit (deployed 2026-04-01 23:01 PT = 2026-04-02 06:01 UTC, trade #342+)
    # SENTINEL_DEPLOY_TS is module-level (see top of file)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/test_sentinel_chart.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add web_dashboard.py tests/test_sentinel_chart.py
git commit -m "$(cat <<'EOF'
refactor(dashboard): promote SENTINEL_DEPLOY_TS + add SENTINEL_CULL_TS

Hoists the Sentinel-deploy timestamp from a local computation inside
render() to a module-level constant, and adds SENTINEL_CULL_TS for the
2026-04-26 strategy cull (commit 479f879). Adds _cull_marker_index
helper for the upcoming Sentinel chart.

Tests: 6 unit tests covering both constants and the helper.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add the `_make_cumulative_pnl_sentinel` chart generator

**Files:**
- Modify: `web_dashboard.py` (add new function alongside `_make_cumulative_pnl` at ~line 1025)

No unit test — chart bytes are visual, verified manually per the spec.

- [ ] **Step 1: Add the chart-generator function**

In `web_dashboard.py`, immediately after `_make_cumulative_pnl()` (after line 1049, before the blank lines preceding `_make_pnl_by_reason`), insert:

```python
def _make_cumulative_pnl_sentinel(trades: list[dict]) -> bytes:
    """Cumulative net PnL chart, filtered to Sentinel-era trades only.

    Mirrors _make_cumulative_pnl style. Adds a vertical dashed marker at the
    2026-04-26 strategy cull commit (479f879). Returns b"" if no Sentinel
    trades exist, so render() can omit the cache key.
    """
    sentinel_trades = [
        t for t in trades
        if (t.get("opened_at") or t.get("closed_at") or 0) >= SENTINEL_DEPLOY_TS
    ]
    if not sentinel_trades:
        return b""

    pnls = [_net_pnl(t) for t in sentinel_trades]
    cum = []
    r = 0.0
    for p in pnls:
        r += p
        cum.append(r)
    x = list(range(1, len(cum) + 1))

    fig, ax = plt.subplots(figsize=(9, 4), facecolor="#1e1e2e")
    ax.set_facecolor("#1e1e2e")
    ax.plot(x, cum, color="#89b4fa", linewidth=2, marker="o", markersize=3)
    ax.fill_between(x, cum, 0, where=[c >= 0 for c in cum], color="#a6e3a1", alpha=0.15)
    ax.fill_between(x, cum, 0, where=[c < 0 for c in cum], color="#f38ba8", alpha=0.15)
    ax.axhline(y=0, color="#585b70", linestyle="--", alpha=0.5)

    cull_x = _cull_marker_index(sentinel_trades)
    if cull_x is not None:
        ax.axvline(x=cull_x, color="#f9e2af", linestyle="--", linewidth=1, alpha=0.6)
        # Place "cull" label near the top of the axes
        y_top = max(cum) if cum else 0
        ax.text(cull_x, y_top, " cull", color="#a6adc8", fontsize=8,
                va="top", ha="left")

    ax.set_xlabel("Trade # (Sentinel-era)", color="#cdd6f4")
    ax.set_ylabel("Cumulative PnL (USDT)", color="#cdd6f4")
    ax.set_title("Cumulative PnL — Sentinel Era", color="#cdd6f4", fontsize=13)
    ax.tick_params(colors="#a6adc8")
    ax.grid(True, alpha=0.15, color="#585b70")
    for spine in ax.spines.values():
        spine.set_color("#585b70")
    return _fig_to_png(fig)
```

- [ ] **Step 2: Smoke test the function in isolation**

Run:
```bash
cd ~/Desktop/Phmex-S && python3 -c "
from web_dashboard import _make_cumulative_pnl_sentinel, read_state
trades = read_state().get('closed_trades', [])
b = _make_cumulative_pnl_sentinel(trades)
print(f'PNG bytes: {len(b)}')
assert len(b) > 1000, 'expected non-trivial PNG output'
print('OK')
"
```
Expected: prints `PNG bytes: <number>` (some thousands) then `OK`.

- [ ] **Step 3: Run full test suite to verify no regression**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/ -v`
Expected: all existing tests still pass (12 pre-existing + 6 new from Task 1 = 18 total).

- [ ] **Step 4: Commit**

```bash
git add web_dashboard.py
git commit -m "$(cat <<'EOF'
feat(dashboard): add Sentinel-era cumulative PnL chart generator

Adds _make_cumulative_pnl_sentinel(): mirrors _make_cumulative_pnl style
filtered to trade #342+, with a yellow dashed marker at the 2026-04-26
strategy cull (commit 479f879). Not yet wired into refresh_charts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire chart into `refresh_charts()` and embed in the Sentinel audit card

**Files:**
- Modify: `web_dashboard.py:1088-1099` (`refresh_charts`)
- Modify: `web_dashboard.py:1500-1511` (Sentinel audit card render block inside `render()`)

- [ ] **Step 1: Register the chart in `refresh_charts()`**

Locate `refresh_charts()` at `web_dashboard.py:1088`. The current body is:

```python
def refresh_charts():
    """Regenerate all charts and cache as PNG bytes."""
    global _chart_version
    state = read_state()
    trades = state.get("closed_trades", [])
    charts = {}
    if trades:
        charts["cumulative_pnl"] = _make_cumulative_pnl(trades)
        charts["pnl_by_reason"] = _make_pnl_by_reason(trades)
    with _chart_lock:
        _chart_cache.update(charts)
        _chart_version += 1
```

Add the new chart conditionally — only set the cache key if the function returned non-empty bytes (otherwise the route handler 404s gracefully and the render path can detect absence):

```python
def refresh_charts():
    """Regenerate all charts and cache as PNG bytes."""
    global _chart_version
    state = read_state()
    trades = state.get("closed_trades", [])
    charts = {}
    if trades:
        charts["cumulative_pnl"] = _make_cumulative_pnl(trades)
        charts["pnl_by_reason"] = _make_pnl_by_reason(trades)
        sentinel_png = _make_cumulative_pnl_sentinel(trades)
        if sentinel_png:
            charts["cumulative_pnl_sentinel"] = sentinel_png
    with _chart_lock:
        _chart_cache.update(charts)
        _chart_version += 1
```

- [ ] **Step 2: Embed the `<img>` inside the Sentinel audit card**

Locate the Sentinel audit card block in `render()` at `web_dashboard.py:1500-1511`. Currently:

```python
        <div class="glass-card dash-item" data-id="audit-sentinel">
            <h2>Performance Audit <span style="color:var(--accent);font-size:0.65em;font-weight:500;letter-spacing:0.08em">SENTINEL</span></h2>
            <div style="font-size:0.65em;color:var(--text-dim);margin:-4px 0 8px;font-family:'JetBrains Mono',monospace">since 2026-04-01 11:01 PM PT &middot; {len(sentinel_trades)} trades</div>
            <div class="perf-summary">
                <div class="perf-summary-item"><span class="stat-label">Win Rate</span>...
                ...
            </div>
            {sentinel_audit_html}
        </div>
```

Just before the rendering of this card (anywhere after `_v = _chart_version` is assigned in the surrounding scope — that already happens at line 1399 inside the `if has_charts:` block; we need it accessible here regardless), build a `sentinel_chart_img` snippet. Add this just before the `<!-- 3-column grid -->` comment near line 1489, after the existing `chart_section` assignment:

```python
    # Sentinel-era chart fragment (None if cache key absent — chart returned empty bytes)
    with _chart_lock:
        has_sentinel_chart = "cumulative_pnl_sentinel" in _chart_cache
        _v_sentinel = _chart_version
    sentinel_chart_img = (
        f'<div class="chart-box" style="margin-bottom:12px"><img src="/chart/cumulative_pnl_sentinel?v={_v_sentinel}" alt="Cumulative PnL — Sentinel Era"></div>'
        if has_sentinel_chart else ""
    )
```

Then modify the Sentinel audit card block to inject the image directly above the `<div class="perf-summary">`:

```python
        <div class="glass-card dash-item" data-id="audit-sentinel">
            <h2>Performance Audit <span style="color:var(--accent);font-size:0.65em;font-weight:500;letter-spacing:0.08em">SENTINEL</span></h2>
            <div style="font-size:0.65em;color:var(--text-dim);margin:-4px 0 8px;font-family:'JetBrains Mono',monospace">since 2026-04-01 11:01 PM PT &middot; {len(sentinel_trades)} trades</div>
            {sentinel_chart_img}
            <div class="perf-summary">
                ...unchanged...
```

(Keep the rest of the card identical.)

- [ ] **Step 3: Restart dashboard and visually verify**

Find the running dashboard and restart so the new code is loaded:

```bash
ps aux | grep "python3.*web_dashboard" | grep -v grep
# kill if running, then:
cd ~/Desktop/Phmex-S && python3 web_dashboard.py >> logs/dashboard.log 2>&1 &
```

Wait ~30 seconds for `chart_thread_loop` to populate the cache, then open `http://localhost:8050` in a browser.

Verify:
- New chart appears inside the Sentinel audit card, directly above the Win Rate / Avg Win / Avg Loss / Best / Worst stats row.
- X-axis label reads `Trade # (Sentinel-era)`.
- Title reads `Cumulative PnL — Sentinel Era`.
- Yellow dashed vertical line with `cull` label is visible (assuming any post-cull trades exist; one synced ETH win exists per 2026-04-26 report).
- All-time `cumulative_pnl` and `pnl_by_reason` charts at the top of the center column are unchanged.
- No browser console errors. No 404 on `/chart/cumulative_pnl_sentinel`.

- [ ] **Step 4: Run full test suite again**

Run: `cd ~/Desktop/Phmex-S && python3 -m pytest tests/ -v`
Expected: 18 tests pass.

- [ ] **Step 5: Commit**

```bash
git add web_dashboard.py
git commit -m "$(cat <<'EOF'
feat(dashboard): wire Sentinel cumulative PnL chart into render path

Registers cumulative_pnl_sentinel in refresh_charts() and embeds the
<img> inside the existing Sentinel audit card, above the perf-summary
stats. Matches CLAUDE.md propagation rule scope: dashboard-only viz,
no metric/gate/exit-reason change → no Telegram/report propagation
required.

Spec: docs/superpowers/specs/2026-04-27-sentinel-pnl-chart-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Final verification

**Files:** None (verification only).

- [ ] **Step 1: Confirm dashboard process is running with new code**

```bash
ps aux | grep "python3.*web_dashboard" | grep -v grep
```
Expected: one process running, started after the Task 3 restart.

- [ ] **Step 2: Hit the chart endpoint directly**

```bash
curl -sI http://localhost:8050/chart/cumulative_pnl_sentinel | head -5
```
Expected: `HTTP/1.0 200 OK`, `Content-Type: image/png`, non-zero `Content-Length`.

- [ ] **Step 3: Confirm dashboard log shows no chart errors**

```bash
tail -50 ~/Desktop/Phmex-S/logs/dashboard.log | grep -i "chart\|error" || echo "no chart errors"
```
Expected: either no matches or only routine `[CHART]` info lines — no `Error refreshing charts` lines.

- [ ] **Step 4: Confirm bot is unaffected**

```bash
ps aux | grep "Python.*main\.py" | grep -v grep
tail -5 ~/Desktop/Phmex-S/logs/bot.log
```
Expected: bot still running (PID unchanged from session start), recent log lines normal.

The bot was never touched — this verification just confirms the dashboard restart didn't accidentally collide with anything.

- [ ] **Step 5: Visual check — push button summary**

Open `localhost:8050`, screenshot the Sentinel audit card if helpful. Confirm:
- Chart present, readable, marker positioned correctly.
- Card layout unbroken (perf-summary + audit table render below the chart).
- Page refresh shows chart updates if a new trade closes (verify `?v=` URL increments after `chart_thread_loop` cycle).

No commit needed for this task — verification only.
