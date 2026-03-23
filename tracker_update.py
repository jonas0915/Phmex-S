#!/usr/bin/env python3
"""
CLI tool to update the project tracker state.

Usage:
    python tracker_update.py check p1t1          # Mark task as completed
    python tracker_update.py uncheck p1t3        # Mark task as not completed
    python tracker_update.py status              # Show all task statuses
    python tracker_update.py phase 1             # Show phase 1 status

Task IDs:
    Phase 1: p1t1-p1t6 (Fix Current Bot)
    Phase 2: p2t1-p2t4 (Strategy Slots + 1h Momentum)
    Phase 3: p3t1-p3t2 (Mean Reversion + Recalibration)
    Phase 4: p4t1-p4t2 (Liquidation + Funding Rate)
    Phase 5: p5t1-p5t2 (Strategy Factory)
"""
import json
import os
import sys

STATE_FILE = os.path.join(os.path.dirname(__file__), "tracker_state.json")

TASK_NAMES = {
    "p1t1": "Widen adverse exit -3% → -5% ROI",
    "p1t2": "Remove soft time exits (keep 4h hard only)",
    "p1t3": "Add tiered trailing stop",
    "p1t4": "Add weekend Kelly multiplier (1.3x Sat/Sun)",
    "p1t5": "Add candle-boundary entry bias",
    "p1t6": "Re-enable bb_mean_reversion with regime gate",
    "p2t1": "Refactor bot.py for strategy slots",
    "p2t2": "Build backtester + WFO framework",
    "p2t3": "Build 1h momentum strategy (Slot 2)",
    "p2t4": "Integrate proven edges into all slots",
    "p3t1": "bb_mean_reversion as Slot 3 (paper → live)",
    "p3t2": "Build recalibration.py",
    "p4t1": "Liquidation cascade strategy (Slot 4)",
    "p4t2": "Funding rate contrarian strategy (Slot 5)",
    "p5t1": "Strategy factory pipeline",
    "p5t2": "Continuous R&D process",
}

PHASES = {
    1: ["p1t1", "p1t2", "p1t3", "p1t4", "p1t5", "p1t6"],
    2: ["p2t1", "p2t2", "p2t3", "p2t4"],
    3: ["p3t1", "p3t2"],
    4: ["p4t1", "p4t2"],
    5: ["p5t1", "p5t2"],
}


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {k: False for k in TASK_NAMES}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def show_status(state):
    total_done = sum(1 for v in state.values() if v)
    total = len(state)
    print(f"\n{'=' * 60}")
    print(f"  PHMEX-S v10 PIPELINE — {total_done}/{total} tasks ({total_done/total*100:.0f}%)")
    print(f"{'=' * 60}\n")

    for phase_num, tasks in PHASES.items():
        done = sum(1 for t in tasks if state.get(t, False))
        pct = done / len(tasks) * 100
        status = "DONE" if pct == 100 else "IN PROGRESS" if done > 0 else "NOT STARTED"
        color = "\033[32m" if pct == 100 else "\033[33m" if done > 0 else "\033[90m"
        print(f"  {color}Phase {phase_num}: {status} ({done}/{len(tasks)})\033[0m")
        for t in tasks:
            check = "\033[32m✓\033[0m" if state.get(t, False) else "\033[90m○\033[0m"
            print(f"    {check} {t}: {TASK_NAMES[t]}")
        print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()
    state = load_state()

    if cmd == "status":
        show_status(state)

    elif cmd == "phase" and len(sys.argv) >= 3:
        phase_num = int(sys.argv[2])
        tasks = PHASES.get(phase_num, [])
        for t in tasks:
            check = "✓" if state.get(t, False) else "○"
            print(f"  {check} {t}: {TASK_NAMES[t]}")

    elif cmd in ("check", "done", "complete") and len(sys.argv) >= 3:
        task_id = sys.argv[2]
        if task_id not in TASK_NAMES:
            print(f"Unknown task: {task_id}. Valid: {', '.join(sorted(TASK_NAMES.keys()))}")
            return
        state[task_id] = True
        save_state(state)
        print(f"  ✓ {task_id}: {TASK_NAMES[task_id]} — COMPLETED")

    elif cmd in ("uncheck", "undo", "revert") and len(sys.argv) >= 3:
        task_id = sys.argv[2]
        if task_id not in TASK_NAMES:
            print(f"Unknown task: {task_id}. Valid: {', '.join(sorted(TASK_NAMES.keys()))}")
            return
        state[task_id] = False
        save_state(state)
        print(f"  ○ {task_id}: {TASK_NAMES[task_id]} — REVERTED")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
