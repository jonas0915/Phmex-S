# L2 Signal Dashboard Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live dashboard panel showing per-symbol L2/tape signal readings, plus a bot-side writer that produces the snapshot file the dashboard reads.

**Architecture:** Two-component feature. (1) `bot.py` accumulates ob+flow per symbol in each cycle and writes atomic `l2_snapshot.json`. (2) `web_dashboard.py` adds `_build_l2_monitor_panel()` rendering the snapshot as a styled HTML table inserted in the right column after Watchlist.

**Tech Stack:** Python 3.14 stdlib (`json`, `os`, `time`), existing dashboard HTML string concatenation

**Spec:** `docs/superpowers/specs/2026-04-17-l2-signal-dashboard-design.md`

---

### Task 1: Bot writes `l2_snapshot.json` each cycle

**Files:**
- Modify: `bot.py` — add snapshot dict accumulation in the main symbol loop + write at end of cycle
- Modify: `.gitignore` — add `l2_snapshot.json`

- [ ] **Step 1: Add `l2_snapshot.json` to .gitignore**

Check if `.gitignore` exists and what's in it:
```bash
cat /Users/jonaspenaso/Desktop/Phmex-S/.gitignore 2>/dev/null | head -20
```

Append one line:
```bash
echo "l2_snapshot.json" >> /Users/jonaspenaso/Desktop/Phmex-S/.gitignore
```

- [ ] **Step 2: Locate the main symbol loop in bot.py**

```bash
grep -n "for symbol in self.active_pairs\|for symbol in active_pairs" /Users/jonaspenaso/Desktop/Phmex-S/bot.py | head -5
```
Note the line number of the main symbol iteration loop (the one containing the strategy call, around line 880-1000).

- [ ] **Step 3: Initialize snapshot dict at start of cycle**

Near the top of `_run_cycle()` (search `def _run_cycle` to find), before the main `for symbol in self.active_pairs:` loop, add:

```python
        # Accumulate L2/tape signals for dashboard snapshot (written at end of cycle)
        _l2_snapshot_accum: dict[str, dict] = {}
```

Place this right before the `for symbol in self.active_pairs:` loop starts.

- [ ] **Step 4: Capture snapshot entry per symbol**

Inside the main symbol loop, right after `flow = self._ws_feed.get_order_flow(symbol) if self._ws_feed else None` (which was moved earlier in the L2 anticipation task), add:

```python
            # Record L2 snapshot for dashboard (overwritten each cycle)
            _price = float(df.iloc[-1]["close"]) if len(df) > 0 else 0.0
            _l2_snapshot_accum[symbol] = {
                "buy_ratio":         (flow or {}).get("buy_ratio"),
                "cvd_slope":         (flow or {}).get("cvd_slope"),
                "bid_depth_usdt":    (ob or {}).get("bid_depth_usdt"),
                "ask_depth_usdt":    (ob or {}).get("ask_depth_usdt"),
                "large_trade_bias":  (flow or {}).get("large_trade_bias"),
                "trade_count":       (flow or {}).get("trade_count", 0),
                "last_price":        _price,
                "updated_at":        time.time(),
            }
```

Locate the insertion point by searching for:
```bash
grep -n "flow = self._ws_feed.get_order_flow" /Users/jonaspenaso/Desktop/Phmex-S/bot.py
```

Insert the snapshot capture on the lines immediately following that `flow = ...` assignment (within the same `for symbol` loop).

- [ ] **Step 5: Write snapshot at end of cycle**

At the END of the `for symbol in self.active_pairs:` loop (but still inside `_run_cycle`), add the atomic write. The right location is immediately after the loop closes. Find the loop's end — it's typically followed by some other top-level logic in `_run_cycle`.

Use a helper function. Add this helper at module level (near the top of bot.py, after imports):

```python
def _write_l2_snapshot(snapshot_dict: dict, path: str = "l2_snapshot.json") -> None:
    """Atomic write of L2 snapshot for dashboard. Silent on failure."""
    try:
        import json as _json
        import os as _os
        payload = {
            "updated_at": time.time(),
            "symbols": snapshot_dict,
        }
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            _json.dump(payload, f, separators=(",", ":"))
        _os.replace(tmp, path)
    except Exception as e:
        logger.debug(f"[L2_SNAPSHOT] write failed: {e}")
```

Then call it at the END of the symbol loop in `_run_cycle`:
```python
        # Write L2 snapshot for dashboard (silent on failure)
        _write_l2_snapshot(_l2_snapshot_accum)
```

This should go right after the `for symbol` loop closes but before any cycle-level cleanup/reporting.

- [ ] **Step 6: Syntax check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile bot.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 7: Test the snapshot writer standalone**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -c "
from bot import _write_l2_snapshot
test_dict = {
    'BTC/USDT:USDT': {
        'buy_ratio': 0.58,
        'cvd_slope': 0.31,
        'bid_depth_usdt': 1200000,
        'ask_depth_usdt': 800000,
        'large_trade_bias': 0.12,
        'trade_count': 45,
        'last_price': 66800.5,
        'updated_at': 1713398400,
    }
}
_write_l2_snapshot(test_dict, 'l2_snapshot_test.json')
import json
with open('l2_snapshot_test.json') as f:
    data = json.load(f)
print('OK' if data['symbols']['BTC/USDT:USDT']['buy_ratio'] == 0.58 else 'FAIL')
import os
os.remove('l2_snapshot_test.json')
"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add bot.py .gitignore && git commit -m "feat: bot writes l2_snapshot.json each cycle for dashboard"
```

---

### Task 2: Dashboard reads snapshot and renders L2 monitor panel

**Files:**
- Modify: `web_dashboard.py` — add `_build_l2_monitor_panel()` + insert call in right column

- [ ] **Step 1: Add the panel builder function**

Find a good insertion point in `web_dashboard.py`. Right after `_build_watchlist_html()` (line 1024) is a natural spot since the new panel is related.

Locate:
```bash
grep -n "^def _build_watchlist_html\|^def build_content" /Users/jonaspenaso/Desktop/Phmex-S/web_dashboard.py
```

Insert this function between `_build_watchlist_html` (ends around line 1082) and `build_content` (line 1084):

```python
def _build_l2_monitor_panel() -> str:
    """Render the L2 Anticipation Signal Monitor panel from l2_snapshot.json."""
    import html as _html
    try:
        with open("l2_snapshot.json") as f:
            data = json.load(f)
    except FileNotFoundError:
        return (
            '<div class="glass-card dash-item" data-id="l2monitor">'
            '<h2>&#128225; L2 Anticipation Monitor</h2>'
            '<div class="muted">No L2 snapshot yet &mdash; bot is starting up.</div>'
            '</div>'
        )
    except Exception as e:
        return (
            '<div class="glass-card dash-item" data-id="l2monitor">'
            '<h2>&#128225; L2 Anticipation Monitor</h2>'
            f'<div class="muted">Snapshot unreadable &mdash; {_html.escape(str(e))}</div>'
            '</div>'
        )

    updated_at = data.get("updated_at", 0)
    age_sec = max(0, int(time.time() - updated_at))
    stale = age_sec > 120
    symbols = data.get("symbols", {})

    if not symbols:
        return (
            '<div class="glass-card dash-item" data-id="l2monitor">'
            '<h2>&#128225; L2 Anticipation Monitor</h2>'
            '<div class="muted">No symbols in snapshot.</div>'
            '</div>'
        )

    # Build table rows
    rows = []
    for sym in sorted(symbols.keys()):
        s = symbols[sym]
        tc = s.get("trade_count", 0) or 0
        short_sym = sym.split("/")[0]

        if tc < 5:
            rows.append(
                f'<tr><td>{_html.escape(short_sym)}</td>'
                f'<td class="l2-cell muted">&#9679;</td>'
                f'<td class="l2-cell muted">&#9679;</td>'
                f'<td class="l2-cell muted">&#9679;</td>'
                f'<td class="l2-cell muted">&#9679;</td>'
                f'<td class="l2-cell muted">no feed</td></tr>'
            )
            continue

        br = s.get("buy_ratio")
        cvd = s.get("cvd_slope")
        bd = s.get("bid_depth_usdt") or 0
        ad = s.get("ask_depth_usdt") or 0
        lt = s.get("large_trade_bias", 0) or 0

        # buy_ratio: 🟢 if < 0.45 or > 0.55, 🔴 if in 0.45-0.55
        if br is None:
            br_cell, br_pass = '<span class="muted">&mdash;</span>', False
        elif br > 0.55 or br < 0.45:
            br_cell = f'<span class="l2-ok">{br:.2f}</span>'
            br_pass = True
        else:
            br_cell = f'<span class="l2-fail">{br:.2f}</span>'
            br_pass = False

        # cvd_slope: 🟢 if |value| > 0.1 (meaningful direction), 🔴 otherwise
        if cvd is None:
            cvd_cell, cvd_pass = '<span class="muted">&mdash;</span>', False
        elif abs(cvd) > 0.1:
            cvd_cell = f'<span class="l2-ok">{cvd:+.2f}</span>'
            cvd_pass = True
        else:
            cvd_cell = f'<span class="l2-fail">{cvd:+.2f}</span>'
            cvd_pass = False

        # depth ratio: bid/ask
        if bd > 0 and ad > 0:
            ratio = bd / ad
            if abs(ratio - 1.0) > 0.2:
                depth_cell = f'<span class="l2-ok">{ratio:.2f}&times;</span>'
                depth_pass = True
            else:
                depth_cell = f'<span class="l2-fail">{ratio:.2f}&times;</span>'
                depth_pass = False
        else:
            depth_cell, depth_pass = '<span class="muted">&mdash;</span>', False

        # whale bias booster
        whale = '&#128011;' if abs(lt) > 0.2 else '&nbsp;'
        whale_cell = f'<span class="l2-whale">{whale} {lt:+.2f}</span>' if lt else f'<span>{whale}</span>'

        # READY count
        passing = sum([br_pass, cvd_pass, depth_pass])
        if passing == 3:
            ready_cell = '<span class="l2-ready">&#9989; 3/3</span>'
        elif passing >= 1:
            ready_cell = f'<span class="l2-partial">&#128992; {passing}/3</span>'
        else:
            ready_cell = '<span class="l2-fail">&#128308; 0/3</span>'

        rows.append(
            f'<tr><td>{_html.escape(short_sym)}</td>'
            f'<td class="l2-cell">{br_cell}</td>'
            f'<td class="l2-cell">{cvd_cell}</td>'
            f'<td class="l2-cell">{depth_cell}</td>'
            f'<td class="l2-cell">{whale_cell}</td>'
            f'<td class="l2-cell">{ready_cell}</td></tr>'
        )

    stale_banner = ''
    if stale:
        stale_banner = (
            f'<div class="l2-stale">Snapshot stale &mdash; last update {age_sec}s ago</div>'
        )

    table_html = (
        '<table class="l2-table">'
        '<thead><tr>'
        '<th>Symbol</th>'
        '<th>buy_ratio</th>'
        '<th>cvd_slope</th>'
        '<th>depth b/a</th>'
        '<th>whale</th>'
        '<th>READY</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
    )

    return (
        '<div class="glass-card dash-item" data-id="l2monitor">'
        '<h2>&#128225; L2 Anticipation Monitor</h2>'
        f'<div class="muted">Live snapshot &mdash; updated {age_sec}s ago</div>'
        f'{stale_banner}'
        f'{table_html}'
        '</div>'
    )
```

Also confirm `json` and `time` are already imported at the top of `web_dashboard.py`. If not:
```bash
head -40 /Users/jonaspenaso/Desktop/Phmex-S/web_dashboard.py | grep "^import\|^from"
```

Both should be present (the dashboard already reads `trading_state.json` and uses time elsewhere).

- [ ] **Step 2: Insert panel call in the right column**

Find the right column block:
```bash
grep -n "{_build_reconcile_card\|Right column" /Users/jonaspenaso/Desktop/Phmex-S/web_dashboard.py | head -5
```

Around line 1277, you'll see:
```python
        {_build_reconcile_card()}
        {_build_observability_panel()}
        {paper_html}
    </div>
```

Insert the L2 monitor call right BEFORE the reconcile card, so it appears right after the Watchlist:

```python
        {_build_l2_monitor_panel()}
        {_build_reconcile_card()}
        {_build_observability_panel()}
        {paper_html}
    </div>
```

- [ ] **Step 3: Add CSS styles for the panel**

Find the CSS section:
```bash
grep -n "/\* ── Watchlist\|<style>" /Users/jonaspenaso/Desktop/Phmex-S/web_dashboard.py | head -5
```

Find a suitable spot in the CSS block (after the Watchlist section around line 1569). Add:

```css
/* ── L2 Anticipation Monitor ── */
.l2-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; margin-top: 0.4rem; }
.l2-table th { text-align: left; padding: 0.3rem 0.4rem; font-weight: 600; color: var(--muted); border-bottom: 1px solid rgba(255,255,255,0.1); }
.l2-table td { padding: 0.3rem 0.4rem; border-bottom: 1px solid rgba(255,255,255,0.05); }
.l2-cell { text-align: center; font-variant-numeric: tabular-nums; }
.l2-ok { color: var(--positive); font-weight: 600; }
.l2-fail { color: var(--negative); font-weight: 600; }
.l2-ready { color: var(--positive); font-weight: 700; }
.l2-partial { color: var(--warning); font-weight: 600; }
.l2-whale { color: var(--accent); }
.l2-stale { background: rgba(251,146,60,0.15); color: var(--warning); padding: 0.3rem 0.6rem; border-radius: 4px; margin: 0.4rem 0; font-size: 0.8rem; }
```

Insert this CSS block right before the `/* ── Watchlist ── */` section (or right after it, either works).

- [ ] **Step 4: Syntax check**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -m py_compile web_dashboard.py && echo "OK"
```
Expected: `OK`

- [ ] **Step 5: Verify the panel builder works standalone**

Create a test snapshot file and render it:

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && /Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python -c "
import json
import time

# Write a test snapshot
snapshot = {
    'updated_at': time.time(),
    'symbols': {
        'BTC/USDT:USDT': {'buy_ratio': 0.58, 'cvd_slope': 0.31, 'bid_depth_usdt': 1400000, 'ask_depth_usdt': 1000000, 'large_trade_bias': 0.12, 'trade_count': 45, 'last_price': 66800, 'updated_at': time.time()},
        'ETH/USDT:USDT': {'buy_ratio': 0.49, 'cvd_slope': 0.05, 'bid_depth_usdt': 800000, 'ask_depth_usdt': 1000000, 'large_trade_bias': 0.0, 'trade_count': 30, 'last_price': 3400, 'updated_at': time.time()},
        'TAO/USDT:USDT': {'buy_ratio': None, 'cvd_slope': None, 'bid_depth_usdt': 0, 'ask_depth_usdt': 0, 'large_trade_bias': 0, 'trade_count': 2, 'last_price': 500, 'updated_at': time.time()},
    },
}
with open('l2_snapshot.json', 'w') as f:
    json.dump(snapshot, f)

from web_dashboard import _build_l2_monitor_panel
html = _build_l2_monitor_panel()
assert 'L2 Anticipation Monitor' in html, 'Header missing'
assert 'BTC' in html, 'BTC row missing'
assert 'ETH' in html, 'ETH row missing'
assert 'no feed' in html, 'TAO should show no feed (trade_count < 5)'
print('Panel render OK (' + str(len(html)) + ' chars)')
import os
os.remove('l2_snapshot.json')
"
```
Expected: `Panel render OK (NNNN chars)` — no assertion errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && git add web_dashboard.py && git commit -m "feat: add L2 Anticipation Signal Monitor dashboard panel"
```

---

### Task 3: Pre-Restart Audit + Restart + Verify Panel

- [ ] **Step 1: Run `/pre-restart-audit` skill**

Invoke the `pre-restart-audit` skill. Do not proceed until audit passes.

- [ ] **Step 2: Restart bot**

```bash
cd /Users/jonaspenaso/Desktop/Phmex-S
kill $(ps aux | grep "Python.*main" | grep -v grep | awk '{print $2}') 2>/dev/null
sleep 2
rm -rf __pycache__
/Library/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python main.py >> logs/bot.log 2>&1 &
sleep 10
cat .bot.pid
```
Expected: new PID printed.

- [ ] **Step 3: Verify snapshot file is written**

```bash
sleep 60
ls -la /Users/jonaspenaso/Desktop/Phmex-S/l2_snapshot.json
cat /Users/jonaspenaso/Desktop/Phmex-S/l2_snapshot.json | python3 -m json.tool | head -30
```
Expected: file exists (few hundred bytes to ~10 KB), contains `symbols` key with entries for each active pair.

- [ ] **Step 4: Check dashboard renders panel (if dashboard is running)**

```bash
ps aux | grep "web_dashboard\|python.*dashboard" | grep -v grep
```

If the dashboard is running, request `/api/content` and check for panel:
```bash
curl -s http://127.0.0.1:8050/api/content | grep -c "L2 Anticipation Monitor"
```
Expected: `1` — panel rendered once.

If dashboard isn't running, start it:
```bash
cd /Users/jonaspenaso/Desktop/Phmex-S && python3 web_dashboard.py &
```

- [ ] **Step 5: Verify no errors in bot log after restart**

```bash
grep -i "error\|traceback\|L2_SNAPSHOT" /Users/jonaspenaso/Desktop/Phmex-S/logs/bot.log | tail -10
```
Expected: no new errors. `[L2_SNAPSHOT]` messages (if any) should only appear on write failures — in normal operation the snapshot write is silent.
