#!/usr/bin/env python3
"""
Strategy Factory — Generate, test, validate, and deploy strategy candidates.

The pipeline:
  1. HYPOTHESIS  → Define what edge you're testing
  2. BACKTEST    → Run on historical data
  3. PAPER TRADE → Run in a slot with $0 real capital
  4. VALIDATE    → Positive Kelly after 50+ paper trades → promote
  5. DEPLOY      → Assign capital, set kill switch
  6. MONITOR     → Monthly recalibration catches decay

Usage:
    python strategy_factory.py list              # List all strategies and their status
    python strategy_factory.py test <name>       # Backtest a strategy
    python strategy_factory.py validate <name>   # Check if paper results pass promotion criteria
    python strategy_factory.py promote <name>    # Move from paper to live
    python strategy_factory.py kill <name>       # Disable a strategy
    python strategy_factory.py report            # Full pipeline status report
"""
import json
import os
import sys
import time
from datetime import datetime

FACTORY_FILE = os.path.join(os.path.dirname(__file__), "strategy_factory_state.json")

# Strategy lifecycle stages
STAGES = {
    "hypothesis": "Idea documented, not yet tested",
    "backtesting": "Running backtest on historical data",
    "paper": "Running in paper mode, collecting live signals",
    "validating": "Has 50+ paper trades, checking promotion criteria",
    "live": "Deployed with real capital",
    "killed": "Disabled — negative edge or decay detected",
    "retired": "Manually retired — replaced by better strategy",
}

# Promotion criteria
PROMOTION_CRITERIA = {
    "min_trades": 50,           # Minimum paper trades before promotion
    "min_wr": 40.0,             # Minimum win rate %
    "min_kelly": 0.0,           # Kelly must be positive (any value > 0)
    "max_dd_pct": 15.0,         # Max drawdown %
    "min_profit_factor": 1.1,   # Gross profit / gross loss > 1.1
}

# Kill criteria
KILL_CRITERIA = {
    "min_trades_for_kill": 50,  # Don't kill before 50 trades (noise)
    "negative_kelly_trades": 50, # Negative Kelly after 50 trades → kill
    "wr_floor": 30.0,           # WR below 30% after 25 trades → kill
    "consecutive_loss_months": 3, # 3 months declining → flag
}


def load_factory_state():
    if os.path.exists(FACTORY_FILE):
        with open(FACTORY_FILE) as f:
            return json.load(f)
    return {"strategies": {}, "pipeline_log": []}


def save_factory_state(state):
    with open(FACTORY_FILE, "w") as f:
        json.dump(state, f, indent=2)


def log_event(state, strategy_name, event):
    entry = {
        "time": datetime.now().isoformat(),
        "strategy": strategy_name,
        "event": event,
    }
    state["pipeline_log"].append(entry)
    # Keep last 100 events
    state["pipeline_log"] = state["pipeline_log"][-100:]


def register_strategy(state, name, hypothesis, timeframe="5m", stage="hypothesis"):
    """Register a new strategy candidate."""
    if name in state["strategies"]:
        print(f"Strategy '{name}' already exists. Use a different name.")
        return
    state["strategies"][name] = {
        "name": name,
        "hypothesis": hypothesis,
        "timeframe": timeframe,
        "stage": stage,
        "created": datetime.now().isoformat(),
        "promoted": None,
        "killed": None,
        "kill_reason": None,
        "backtest_results": None,
        "paper_results": None,
        "live_results": None,
    }
    log_event(state, name, f"Registered — stage: {stage}")
    save_factory_state(state)
    print(f"  Registered: {name} ({stage}) — {hypothesis}")


def list_strategies(state):
    """List all strategies by stage."""
    strats = state.get("strategies", {})
    if not strats:
        print("  No strategies registered. Use: python strategy_factory.py register <name> <hypothesis>")
        return

    by_stage = {}
    for name, s in strats.items():
        stage = s.get("stage", "unknown")
        by_stage.setdefault(stage, []).append(s)

    print(f"\n{'='*60}")
    print(f"  STRATEGY FACTORY — {len(strats)} strategies")
    print(f"{'='*60}")

    for stage in ["live", "paper", "validating", "backtesting", "hypothesis", "killed", "retired"]:
        if stage not in by_stage:
            continue
        color = {"live": "32", "paper": "33", "killed": "31", "retired": "90"}.get(stage, "36")
        print(f"\n  \033[{color}m{stage.upper()}\033[0m ({STAGES.get(stage, '')})")
        for s in by_stage[stage]:
            print(f"    {s['name']:25s} | {s['timeframe']} | {s['hypothesis'][:50]}")
            if s.get("backtest_results"):
                r = s["backtest_results"]
                print(f"      Backtest: {r.get('trades', 0)} trades, WR {r.get('wr', 0)}%, Kelly {r.get('kelly', 0):.3f}")


def test_strategy(state, name):
    """Run backtest for a strategy."""
    if name not in state["strategies"]:
        print(f"Strategy '{name}' not found.")
        return

    print(f"\n  Running backtest for '{name}'...")
    print(f"  Use: python backtester.py --strategy {name}")
    print(f"  Then update results: python strategy_factory.py update-backtest {name} <trades> <wr> <kelly> <pnl>")

    state["strategies"][name]["stage"] = "backtesting"
    log_event(state, name, "Moved to backtesting")
    save_factory_state(state)


def update_backtest(state, name, trades, wr, kelly, pnl):
    """Record backtest results."""
    if name not in state["strategies"]:
        print(f"Strategy '{name}' not found.")
        return

    state["strategies"][name]["backtest_results"] = {
        "trades": trades,
        "wr": wr,
        "kelly": kelly,
        "pnl": pnl,
        "date": datetime.now().isoformat(),
    }

    # Auto-advance if backtest looks good
    if kelly > 0 and wr >= PROMOTION_CRITERIA["min_wr"]:
        state["strategies"][name]["stage"] = "paper"
        log_event(state, name, f"Backtest passed (WR={wr}%, Kelly={kelly:.3f}) → moved to paper")
        print(f"  Backtest passed! Strategy moved to PAPER stage.")
    else:
        log_event(state, name, f"Backtest results: WR={wr}%, Kelly={kelly:.3f} — needs improvement")
        print(f"  Backtest didn't pass promotion criteria. Refine strategy.")

    save_factory_state(state)


def validate_strategy(state, name):
    """Check if a paper-mode strategy meets promotion criteria."""
    if name not in state["strategies"]:
        print(f"Strategy '{name}' not found.")
        return

    s = state["strategies"][name]
    print(f"\n  Validating '{name}' against promotion criteria:")
    print(f"  {'Criterion':25s} {'Required':>10s} {'Actual':>10s} {'Status':>8s}")
    print(f"  {'-'*55}")

    # Load paper results from state file
    state_file = f"trading_state_{name}.json"
    path = os.path.join(os.path.dirname(__file__), state_file)

    if not os.path.exists(path):
        print(f"  No state file found: {state_file}")
        print(f"  Strategy needs to run in paper mode first.")
        return

    with open(path) as f:
        data = json.load(f)
    trades = data.get("closed_trades", [])

    if not trades:
        print(f"  No trades yet. Keep running in paper mode.")
        return

    wins = [t for t in trades if t.get("pnl_usdt", 0) > 0]
    losses = [t for t in trades if t.get("pnl_usdt", 0) <= 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    pnl = sum(t.get("pnl_usdt", 0) for t in trades)

    avg_win = sum(t["pnl_usdt"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["pnl_usdt"] for t in losses) / len(losses)) if losses else 0
    kelly = (wr/100 * avg_win - (1-wr/100) * avg_loss) / avg_win if avg_win > 0 else 0

    gross_profit = sum(t["pnl_usdt"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl_usdt"] for t in losses)) if losses else 1
    pf = gross_profit / gross_loss if gross_loss > 0 else 0

    checks = [
        ("Min trades", f">={PROMOTION_CRITERIA['min_trades']}", str(len(trades)), len(trades) >= PROMOTION_CRITERIA["min_trades"]),
        ("Win rate", f">={PROMOTION_CRITERIA['min_wr']}%", f"{wr:.1f}%", wr >= PROMOTION_CRITERIA["min_wr"]),
        ("Kelly", f"> {PROMOTION_CRITERIA['min_kelly']}", f"{kelly:.3f}", kelly > PROMOTION_CRITERIA["min_kelly"]),
        ("Profit factor", f">= {PROMOTION_CRITERIA['min_profit_factor']}", f"{pf:.2f}", pf >= PROMOTION_CRITERIA["min_profit_factor"]),
    ]

    all_pass = True
    for label, required, actual, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  {label:25s} {required:>10s} {actual:>10s} {status:>8s}")
        if not passed:
            all_pass = False

    if all_pass:
        print(f"\n  ALL CRITERIA MET — ready for promotion!")
        print(f"  Run: python strategy_factory.py promote {name}")
        state["strategies"][name]["stage"] = "validating"
    else:
        print(f"\n  Not all criteria met yet. Continue paper trading.")

    save_factory_state(state)


def promote_strategy(state, name, capital_pct=0.2):
    """Promote a validated strategy to live."""
    if name not in state["strategies"]:
        print(f"Strategy '{name}' not found.")
        return

    state["strategies"][name]["stage"] = "live"
    state["strategies"][name]["promoted"] = datetime.now().isoformat()
    log_event(state, name, f"PROMOTED to live with {capital_pct*100:.0f}% capital")
    save_factory_state(state)

    print(f"\n  '{name}' PROMOTED to LIVE")
    print(f"  Action needed: Update bot.py slot config:")
    print(f"    - Set paper_mode=False")
    print(f"    - Set capital_pct={capital_pct}")
    print(f"    - Restart bot")


def kill_strategy(state, name, reason="Manual kill"):
    """Disable a strategy."""
    if name not in state["strategies"]:
        print(f"Strategy '{name}' not found.")
        return

    state["strategies"][name]["stage"] = "killed"
    state["strategies"][name]["killed"] = datetime.now().isoformat()
    state["strategies"][name]["kill_reason"] = reason
    log_event(state, name, f"KILLED — {reason}")
    save_factory_state(state)

    print(f"\n  '{name}' KILLED — {reason}")
    print(f"  Action needed: Set enabled=False in bot.py slot config and restart")


def pipeline_report(state):
    """Full pipeline status report."""
    strats = state.get("strategies", {})

    live = [s for s in strats.values() if s["stage"] == "live"]
    paper = [s for s in strats.values() if s["stage"] in ("paper", "validating")]
    killed = [s for s in strats.values() if s["stage"] == "killed"]
    ideas = [s for s in strats.values() if s["stage"] in ("hypothesis", "backtesting")]

    print(f"\n{'='*60}")
    print(f"  STRATEGY FACTORY PIPELINE REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"\n  Live:      {len(live)} strategies generating revenue")
    print(f"  Paper:     {len(paper)} strategies collecting data")
    print(f"  Pipeline:  {len(ideas)} ideas in development")
    print(f"  Killed:    {len(killed)} strategies retired")
    print(f"  Total:     {len(strats)} strategies in factory")

    # Health check
    print(f"\n  Health:")
    if len(live) < 2:
        print(f"  WARNING: Only {len(live)} live strategies — target is 3-5")
    if len(paper) < 1:
        print(f"  WARNING: No strategies in paper testing — pipeline is dry")
    if len(ideas) < 1:
        print(f"  WARNING: No new ideas in development — R&D needed")
    if len(live) >= 3 and len(paper) >= 1:
        print(f"  OK: Pipeline healthy — {len(live)} live, {len(paper)} testing, {len(ideas)} developing")

    # Recent events
    events = state.get("pipeline_log", [])[-10:]
    if events:
        print(f"\n  Recent Events:")
        for e in reversed(events):
            print(f"    {e['time'][:16]} | {e['strategy']:20s} | {e['event']}")


def main():
    state = load_factory_state()

    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    if cmd == "list":
        list_strategies(state)

    elif cmd == "register" and len(sys.argv) >= 4:
        name = sys.argv[2]
        tf = "5m"  # default
        args = sys.argv[3:]
        # Extract --tf flag before building hypothesis
        filtered = []
        skip_next = False
        for i, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if arg == "--tf" and i+1 < len(args):
                tf = args[i+1]
                skip_next = True
            else:
                filtered.append(arg)
        hypothesis = " ".join(filtered)
        register_strategy(state, name, hypothesis, tf)

    elif cmd == "test" and len(sys.argv) >= 3:
        test_strategy(state, sys.argv[2])

    elif cmd == "update-backtest" and len(sys.argv) >= 6:
        name = sys.argv[2]
        trades = int(sys.argv[3])
        wr = float(sys.argv[4])
        kelly = float(sys.argv[5])
        pnl = float(sys.argv[6]) if len(sys.argv) > 6 else 0
        update_backtest(state, name, trades, wr, kelly, pnl)

    elif cmd == "validate" and len(sys.argv) >= 3:
        validate_strategy(state, sys.argv[2])

    elif cmd == "promote" and len(sys.argv) >= 3:
        capital = float(sys.argv[3]) if len(sys.argv) > 3 else 0.2
        promote_strategy(state, sys.argv[2], capital)

    elif cmd == "kill" and len(sys.argv) >= 3:
        reason = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else "Manual kill"
        kill_strategy(state, sys.argv[2], reason)

    elif cmd == "report":
        pipeline_report(state)

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
