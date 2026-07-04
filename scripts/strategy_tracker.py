#!/usr/bin/env python3
"""Phmex-S Strategy Improvement Tracker — generator.

Reads primary sources (trading_state*.json, logs/bot.log, .env, mode sidecars)
and writes strategy_tracker.html. Numbers are NEVER hardcoded — regenerate with:

    python3 scripts/strategy_tracker.py

Curated research verdicts (the CLOSED RESEARCH section) are editorial entries
maintained here, each carrying its date and source doc. Everything numeric is
computed at generation time.
"""
import json
import glob
import os
import re
import subprocess
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "strategy_tracker.html")


def read_states():
    rows = []
    total = 0.0
    for f in sorted(glob.glob(os.path.join(ROOT, "trading_state*.json"))):
        base = os.path.basename(f)
        if base.endswith("_mode.json"):
            continue
        try:
            d = json.load(open(f))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        trades = d.get("closed_trades") or []
        if not trades:
            continue
        net = sum(
            (t.get("net_pnl") if t.get("net_pnl") is not None else t.get("pnl_usdt", 0) or 0)
            for t in trades if isinstance(t, dict)
        )
        wins = sum(1 for t in trades if isinstance(t, dict)
                   and ((t.get("net_pnl") if t.get("net_pnl") is not None else t.get("pnl_usdt", 0)) or 0) > 0)
        rows.append({
            "file": base,
            "n": len(trades),
            "net": round(net, 2),
            "wr": round(100.0 * wins / len(trades), 1),
        })
        total += net
    return rows, round(total, 2)


def slot_mode(name):
    p = os.path.join(ROOT, f"trading_state_{name}_mode.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p))
    except Exception:
        return None


def latest_balance():
    try:
        out = subprocess.run(
            ["grep", "-oE", r"Balance: [0-9.]+", os.path.join(ROOT, "logs", "bot.log")],
            capture_output=True, text=True).stdout.strip().splitlines()
        return float(out[-1].split()[-1]) if out else None
    except Exception:
        return None


def bot_pid():
    try:
        out = subprocess.run(["pgrep", "-f", "MacOS/Python main.py"],
                             capture_output=True, text=True).stdout.strip().splitlines()
        return out[0] if out else None
    except Exception:
        return None


def requote_events():
    try:
        out = subprocess.run(["grep", "-ciE", "requote", os.path.join(ROOT, "logs", "bot.log")],
                             capture_output=True, text=True).stdout.strip()
        return int(out or 0)
    except Exception:
        return 0


def env_value(key):
    try:
        for line in open(os.path.join(ROOT, ".env")):
            if line.startswith(key + "="):
                return line.strip().split("=", 1)[1]
    except Exception:
        pass
    return None


# ── Editorial: curated research ledger (dates + source docs; no numbers invented)
CLOSED_RESEARCH = [
    ("2026-07-01", "L2X exit strategy", "HONEST NULL",
     "148 real htf_l2 fills: entry adverse selection confirmed (−4.5bps@1m), "
     "losers mildly continue, HOLD beats cut 9/9 cells. L2X not built. "
     "Tool: scripts/l2x_lab/postentry_drift.py"),
    ("2026-06-29", "New-strategy feasibility", "NULL — closed",
     "Funding, cross-sectional, OI all eliminated at this scale. ST2.0 signal "
     "likely wrong-signed. Lab exhausted 0/500. DO NOT re-mine."),
    ("2026-06-29", "ST2.0 book×tape absorption", "DEMOTED TO PAPER",
     "35 live trades −$4.14, 95% CI excl. 0. Root cause: execution adverse "
     "selection, not signal. Re-arm requires a promote path, not a flag delete."),
    ("2026-06-13", "Entry-gate quantification", "NULL",
     "No gate measurably blocks winners or losers; every 95% CI spans 0. "
     "Gate stack left alone. Don't re-run."),
    ("2026-06-13", "Edge-hunt (5 backtest edges)", "ALL DIED under verification",
     "Imbalance / reversion / vol-fade / funding / XS-momentum. Backtesting "
     "this data makes artifacts; forward-testing is the only adjudicator."),
]

WATCHING = [
    ("MR forward-test scoreboard", "Telegram 'Counters:' line (requote_fill / miss / aborts) "
     "judges the re-quote; RSI-floor verdict needs blocked-entry counterfactuals."),
    ("24h trading (since 6/30)", "Time-of-day block removed (TRADING_BLOCKED_HOURS_UTC empty). "
     "Reversible; gate-quantify found no time edge."),
    ("Scanner blacklist cleared (6/30)", "9 April-era cuts back in circulation; old list "
     "preserved in .env comment. BTC stays IN per Jonas 6/30."),
]


def status_of(base, modes):
    if base == "trading_state.json":
        return ("LIVE", "live"), "Main bot — htf_l2 signal (gross-positive, fee drag)"
    if "5m_mean_revert" in base:
        m = modes.get("5m_mean_revert") or {}
        return (("LIVE", "live") if not m.get("paper_mode", True) else ("PAPER", "paper")), \
            "MR slot — RSI floor + re-quote forward test (LIVE 7/2)"
    if "ST2.0" in base and "blocked" not in base:
        m = modes.get("ST2.0") or {}
        return (("PAPER", "paper") if m.get("paper_mode") else ("LIVE", "live")), \
            "Demoted 6/29 — paper sims for data only"
    if "narrow" in base or "liq_cascade" in base:
        return ("KILLED", "dead"), "Killed slot (historical)"
    if "v8" in base:
        return ("ARCHIVE", "dead"), "v8-era archive"
    return ("?", "dead"), ""


def fmt_usd(v, signed=True):
    if v is None:
        return "—"
    s = f"{v:+.2f}" if signed else f"{v:.2f}"
    return f"${s}" if not signed else (f"+${v:.2f}" if v >= 0 else f"−${abs(v):.2f}")


def main():
    rows, total = read_states()
    modes = {"5m_mean_revert": slot_mode("5m_mean_revert"), "ST2.0": slot_mode("ST2.0")}
    bal = latest_balance()
    pid = bot_pid()
    rq = requote_events()
    rsi_min = env_value("MEAN_REVERT_LONG_RSI_MIN")
    drift = env_value("SLOT_REQUOTE_MAX_DRIFT_PCT")
    now = datetime.datetime.now().strftime("%b %-d, %Y %-I:%M %p PT")

    mr = next((r for r in rows if "5m_mean_revert" in r["file"]), None)

    ledger_rows = ""
    for r in rows:
        (label, cls), desc = status_of(r["file"], modes)
        color = {"live": "#4ecb71", "paper": "#fbbf24", "dead": "#6b7280"}[cls]
        net_col = "#4ecb71" if r["net"] >= 0 else "#e05252"
        ledger_rows += f"""
        <tr>
          <td><span class="pill" style="border-color:{color};color:{color}">{label}</span></td>
          <td class="mono">{r['file']}</td>
          <td class="desc">{desc}</td>
          <td class="num">{r['n']}</td>
          <td class="num">{r['wr']}%</td>
          <td class="num" style="color:{net_col}">{fmt_usd(r['net'])}</td>
        </tr>"""

    research_rows = "".join(
        f"""<div class="research"><div class="rhead"><span class="rdate">{d}</span>
        <strong>{t}</strong> <span class="verdict">{v}</span></div>
        <div class="rbody">{b}</div></div>"""
        for d, t, v, b in CLOSED_RESEARCH)

    watching_rows = "".join(
        f"""<div class="watch"><strong>{t}</strong><div class="rbody">{b}</div></div>"""
        for t, b in WATCHING)

    live_exp = f"""
      <div class="research live-exp">
        <div class="rhead"><span class="rdate">2026-07-02</span>
          <strong>MR forward-test bundle</strong>
          <span class="pill" style="border-color:#4ecb71;color:#4ecb71">LIVE</span></div>
        <div class="rbody">
          RSI floor blocks longs when RSI &lt; <b>{rsi_min or '?'}</b> +
          bounded maker re-quote (1 retry at touch, drift cap <b>{drift or '?'}%</b>,
          zombie guard) attacking the ~15% fill rate.<br>
          Slot record so far: <b>{mr['n'] if mr else '?'} trades,
          {fmt_usd(mr['net']) if mr else '?'}</b> (only green book on the desk).
          Re-quote events in current bot.log: <b>{rq}</b>{' — none fired yet' if rq == 0 else ''}.
          Rollback: MEAN_REVERT_LONG_RSI_MIN=0 / remove requote_attempts=1 + restart.
        </div>
      </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phmex-S — Strategy Improvement Tracker</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0b0e13; color:#d7dce3; font:14px/1.5 "SF Mono", Menlo, monospace; padding:28px; }}
  h1 {{ color:#f0a500; font-size:19px; letter-spacing:1px; margin-bottom:2px; }}
  .sub {{ color:#8b93a1; font-size:12px; margin-bottom:22px; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; margin-bottom:26px; }}
  .tile {{ background:#12161f; border:1px solid #232a38; border-radius:6px; padding:12px 14px; }}
  .tile .k {{ color:#8b93a1; font-size:11px; text-transform:uppercase; letter-spacing:1px; }}
  .tile .v {{ font-size:22px; margin-top:4px; color:#e8ecf2; }}
  .tile .n {{ font-size:11px; color:#8b93a1; margin-top:2px; }}
  h2 {{ color:#f0a500; font-size:13px; letter-spacing:2px; text-transform:uppercase;
        border-bottom:1px solid #232a38; padding-bottom:6px; margin:26px 0 12px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; color:#8b93a1; font-size:11px; text-transform:uppercase; padding:6px 8px; }}
  td {{ padding:7px 8px; border-top:1px solid #1a2030; vertical-align:top; }}
  td.num {{ text-align:right; white-space:nowrap; }}
  th:nth-child(n+4) {{ text-align:right; }}
  .mono {{ color:#aeb6c2; font-size:12px; }}
  .desc {{ color:#8b93a1; font-size:12px; }}
  .pill {{ border:1px solid; border-radius:3px; font-size:10px; padding:1px 7px; letter-spacing:1px; }}
  .research, .watch {{ background:#12161f; border:1px solid #232a38; border-radius:6px;
        padding:11px 14px; margin-bottom:9px; }}
  .live-exp {{ border-color:#2c5a3c; }}
  .rhead {{ display:flex; gap:10px; align-items:baseline; flex-wrap:wrap; }}
  .rdate {{ color:#8b93a1; font-size:11px; }}
  .verdict {{ color:#fbbf24; font-size:11px; letter-spacing:1px; }}
  .rbody {{ color:#aeb6c2; font-size:12.5px; margin-top:5px; }}
  .foot {{ color:#5b6270; font-size:11px; margin-top:28px; border-top:1px solid #1a2030; padding-top:10px; }}
  b {{ color:#e8ecf2; }}
</style></head><body>
<h1>PHMEX-S — STRATEGY IMPROVEMENT TRACKER</h1>
<div class="sub">Generated {now} · regenerate: <b>python3 scripts/strategy_tracker.py</b> · all numbers computed from state files + logs at generation time</div>

<div class="tiles">
  <div class="tile"><div class="k">Balance</div><div class="v">${bal if bal is not None else '—'}</div><div class="n">latest bot.log line</div></div>
  <div class="tile"><div class="k">Lifetime net (all books)</div><div class="v" style="color:{'#4ecb71' if total>=0 else '#e05252'}">{fmt_usd(total)}</div><div class="n">sum of ALL trading_state*.json</div></div>
  <div class="tile"><div class="k">Live green book</div><div class="v" style="color:#4ecb71">{fmt_usd(mr['net']) if mr else '—'}</div><div class="n">5m_mean_revert · {mr['n'] if mr else 0} trades</div></div>
  <div class="tile"><div class="k">Bot</div><div class="v" style="color:{'#4ecb71' if pid else '#e05252'}">{'RUNNING' if pid else 'DOWN'}</div><div class="n">{'PID ' + pid if pid else 'no main.py process'}</div></div>
</div>

<h2>Live experiment</h2>
{live_exp}

<h2>Strategy ledger — every book, fee-inclusive</h2>
<table>
  <tr><th>Status</th><th>State file</th><th>What</th><th>Trades</th><th>WR</th><th>Net</th></tr>
  {ledger_rows}
</table>

<h2>Closed research — verdicts stand, do not re-mine</h2>
{research_rows}

<h2>Watching</h2>
{watching_rows}

<div class="foot">Sources: trading_state*.json (closed_trades, net_pnl→pnl_usdt fallback), logs/bot.log (balance, requote grep), .env (thresholds), *_mode.json sidecars (live/paper). Research verdicts curated in scripts/strategy_tracker.py with dates + source docs. Never edit numbers in this HTML — regenerate.</div>
</body></html>"""
    open(OUT, "w").write(html)
    print(f"wrote {OUT}  (balance={bal}, lifetime={total}, books={len(rows)}, pid={pid})")


if __name__ == "__main__":
    main()
