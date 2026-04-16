#!/usr/bin/env python3
"""
Auto-Lifecycle Scanner — kill, promote, decay, rollback.
Runs every 4 hours via launchd.

Reads: trading_state_*.json, strategy_factory_state.json, parameter_changelog.json
Writes: sentinel files (.kill_, .pause_, .promote_, .demote_, .restart_bot)
"""
import json
import os
import sys
import time
import glob
import logging
from datetime import datetime

BOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BOT_DIR)
os.chdir(BOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BOT_DIR, ".env"))

from recalibration import compute_metrics, kill_switch_check, edge_decay_check

logging.basicConfig(
    filename=os.path.join(BOT_DIR, "logs", "auto_lifecycle.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Telegram notification (reuse pattern from monitor_daemon)
import requests
TG_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

FACTORY_FILE = os.path.join(BOT_DIR, "strategy_factory_state.json")
CHANGELOG_FILE = os.path.join(BOT_DIR, "parameter_changelog.json")
MAX_LIVE_SLOTS = 2


def tg_send(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def load_factory_state():
    if os.path.exists(FACTORY_FILE):
        with open(FACTORY_FILE) as f:
            return json.load(f)
    return {"strategies": {}}


def save_factory_state(state):
    with open(FACTORY_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_slot_trades(slot_id):
    """Load closed trades for a slot from its trading_state file."""
    path = os.path.join(BOT_DIR, f"trading_state_{slot_id}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        state = json.load(f)
    return state.get("closed_trades", [])


def get_live_slot_count(factory_state):
    """Count how many slots are currently in 'live' stage."""
    return sum(1 for s in factory_state.get("strategies", {}).values() if s.get("stage") == "live")


def scan_kills(factory_state):
    """Kill scan: negative Kelly after 50+ trades, or WR < 30% after 25+ trades."""
    actions = []
    for name, info in factory_state.get("strategies", {}).items():
        if info.get("stage") in ("killed", "retired"):
            continue
        slot_id = info.get("slot_id", name)
        trades = load_slot_trades(slot_id)
        if not trades:
            continue
        metrics = compute_metrics(trades)
        issues = kill_switch_check(metrics)
        if issues:
            sentinel_path = os.path.join(BOT_DIR, f".kill_{slot_id}")
            with open(sentinel_path, "w") as f:
                json.dump({"reason": issues[0], "ts": int(time.time())}, f)
            info["stage"] = "killed"
            info["killed_at"] = int(time.time())
            msg = f"🔪 <b>AUTO-KILL</b>: {slot_id} — {issues[0]}"
            tg_send(msg)
            logger.warning(msg)
            actions.append(f"KILL: {slot_id}")
    return actions


def scan_edge_decay(factory_state):
    """Edge decay scan: 7d WR vs historical, >30% drop → pause 24 hrs."""
    actions = []
    for name, info in factory_state.get("strategies", {}).items():
        if info.get("stage") in ("killed", "retired"):
            continue
        slot_id = info.get("slot_id", name)
        trades = load_slot_trades(slot_id)
        if not trades:
            continue
        alerts = edge_decay_check(trades)
        if alerts:
            sentinel_path = os.path.join(BOT_DIR, f".pause_{slot_id}")
            if not os.path.exists(sentinel_path):  # Don't overwrite existing pause
                with open(sentinel_path, "w") as f:
                    json.dump({"reason": alerts[0], "ts": int(time.time())}, f)
                msg = f"📉 <b>EDGE DECAY</b>: {slot_id} — {alerts[0]}. Paused 24 hrs."
                tg_send(msg)
                logger.warning(msg)
                actions.append(f"DECAY PAUSE: {slot_id}")
    return actions


def scan_promotions(factory_state):
    """Promote scan: paper slots meeting all criteria → promote to live."""
    actions = []
    for name, info in factory_state.get("strategies", {}).items():
        if info.get("stage") != "paper":
            continue
        slot_id = info.get("slot_id", name)
        trades = load_slot_trades(slot_id)
        if not trades:
            continue
        metrics = compute_metrics(trades)

        # Check all promotion criteria
        if metrics["trades"] < 50:
            continue
        if metrics["wr"] < 40.0:
            continue
        if metrics["kelly"] <= 0:
            continue
        if metrics["profit_factor"] < 1.1:
            continue
        # max_dd from compute_metrics is absolute dollars — convert to percentage
        total_pnl = metrics["pnl"]
        peak_pnl = total_pnl + metrics["max_dd"]  # peak = current + drawdown from peak
        max_dd_pct = (metrics["max_dd"] / peak_pnl * 100) if peak_pnl > 0 else 0
        if max_dd_pct > 15.0:
            continue

        live_count = get_live_slot_count(factory_state)
        if live_count >= MAX_LIVE_SLOTS:
            # Compare against weakest live slot
            weakest_id, weakest_kelly = None, float("inf")
            for sname, sinfo in factory_state.get("strategies", {}).items():
                if sinfo.get("stage") != "live":
                    continue
                s_slot_id = sinfo.get("slot_id", sname)
                s_trades = load_slot_trades(s_slot_id)
                if s_trades:
                    s_metrics = compute_metrics(s_trades)
                    if s_metrics["kelly"] < weakest_kelly:
                        weakest_kelly = s_metrics["kelly"]
                        weakest_id = s_slot_id
            if weakest_id and metrics["kelly"] > weakest_kelly:
                # Demote weakest
                demote_path = os.path.join(BOT_DIR, f".demote_{weakest_id}")
                with open(demote_path, "w") as f:
                    json.dump({"reason": "replaced by stronger candidate", "ts": int(time.time())}, f)
                for sname, sinfo in factory_state.get("strategies", {}).items():
                    if sinfo.get("slot_id", sname) == weakest_id:
                        sinfo["stage"] = "paper"
                        break
                msg = f"⬇️ <b>AUTO-DEMOTE</b>: {weakest_id} (Kelly {weakest_kelly:.3f}) — replaced by {slot_id}"
                tg_send(msg)
                logger.info(msg)
                actions.append(f"DEMOTE: {weakest_id}")
            else:
                continue  # Can't promote — at cap and candidate isn't better

        # Promote
        promote_path = os.path.join(BOT_DIR, f".promote_{slot_id}")
        with open(promote_path, "w") as f:
            json.dump({"capital_pct": 0.10, "ts": int(time.time())}, f)
        info["stage"] = "live"
        info["promoted_at"] = int(time.time())
        msg = (
            f"🚀 <b>AUTO-PROMOTE</b>: {slot_id} to live at 10%\n"
            f"{metrics['trades']} trades | {metrics['wr']}% WR | "
            f"Kelly {metrics['kelly']:.3f} | PF {metrics['profit_factor']:.2f}"
        )
        tg_send(msg)
        logger.info(msg)
        actions.append(f"PROMOTE: {slot_id}")
        break  # Only promote one slot per scan to avoid exceeding MAX_LIVE_SLOTS

    return actions


def scan_ramps(factory_state):
    """Ramp scan: increase capital for proven live slots."""
    actions = []
    for name, info in factory_state.get("strategies", {}).items():
        if info.get("stage") != "live":
            continue
        slot_id = info.get("slot_id", name)
        promoted_at = info.get("promoted_at", 0)
        current_pct = info.get("capital_pct", 0.10)

        # Count trades since promotion
        trades = load_slot_trades(slot_id)
        live_trades = [t for t in trades if t.get("closed_at", 0) >= promoted_at]
        profitable = [t for t in live_trades if t.get("pnl_usdt", 0) > 0]

        # Auto-demote FIRST if Kelly turns negative after 25 live trades
        if len(live_trades) >= 25:
            live_metrics = compute_metrics(live_trades)
            if live_metrics["kelly"] < 0:
                demote_path = os.path.join(BOT_DIR, f".demote_{slot_id}")
                with open(demote_path, "w") as f:
                    json.dump({"reason": f"negative Kelly ({live_metrics['kelly']:.3f}) after {len(live_trades)} live trades", "ts": int(time.time())}, f)
                info["stage"] = "paper"
                msg = f"⬇️ <b>AUTO-DEMOTE</b>: {slot_id} — negative Kelly ({live_metrics['kelly']:.3f}) after {len(live_trades)} live trades"
                tg_send(msg)
                actions.append(f"DEMOTE: {slot_id}")
                continue  # Skip ramp — slot is being demoted

        # Ramp up if still healthy
        if len(profitable) >= 50 and current_pct < 0.30:
            info["capital_pct"] = 0.30
            promote_path = os.path.join(BOT_DIR, f".promote_{slot_id}")
            with open(promote_path, "w") as f:
                json.dump({"capital_pct": 0.30, "ts": int(time.time())}, f)
            msg = f"📈 <b>RAMP</b>: {slot_id} → 30% capital ({len(profitable)} profitable trades)"
            tg_send(msg)
            actions.append(f"RAMP 30%: {slot_id}")
        elif len(profitable) >= 25 and current_pct < 0.20:
            info["capital_pct"] = 0.20
            promote_path = os.path.join(BOT_DIR, f".promote_{slot_id}")
            with open(promote_path, "w") as f:
                json.dump({"capital_pct": 0.20, "ts": int(time.time())}, f)
            msg = f"📈 <b>RAMP</b>: {slot_id} → 20% capital ({len(profitable)} profitable trades)"
            tg_send(msg)
            actions.append(f"RAMP 20%: {slot_id}")

    return actions


def scan_rollbacks():
    """Rollback scan: revert parameter changes that caused WR drop."""
    if not os.path.exists(CHANGELOG_FILE):
        return []

    actions = []
    with open(CHANGELOG_FILE) as f:
        changelog = json.load(f)

    now = time.time()
    for entry in changelog:
        changed_at = entry.get("changed_at", 0)
        if now - changed_at > 48 * 3600:
            continue  # Only check changes in last 48 hrs

        pre = entry.get("pre_change_metrics", {})
        param = entry.get("param", "unknown")
        param_source = entry.get("param_source")

        if not param_source:
            msg = f"⚠️ <b>ROLLBACK SKIPPED</b>: {param} — missing param_source"
            tg_send(msg)
            logger.warning(msg)
            continue

        # Load current metrics (last 20 trades from main state)
        trades = []
        try:
            with open(os.path.join(BOT_DIR, "trading_state.json")) as f:
                state = json.load(f)
            trades = state.get("closed_trades", [])[-20:]
        except Exception:
            continue

        if len(trades) < 10:
            continue

        post_metrics = compute_metrics(trades)
        pre_wr = pre.get("wr", 0)

        if pre_wr > 0 and post_metrics["wr"] < pre_wr * 0.85:
            # 15%+ WR drop — rollback
            old_value = entry.get("old_value")
            new_value = entry.get("new_value")
            source_key = entry.get("param_source_key", param)

            if param_source == "env":
                if not _rollback_env(source_key, old_value):
                    tg_send(f"⚠️ <b>ROLLBACK FAILED</b>: {param} — key {source_key} not found in .env")
                    continue
            elif param_source in ("bot_py", "strategies_py"):
                msg = f"⚠️ <b>ROLLBACK NEEDED</b>: {param} {new_value}→{old_value} in {param_source} — manual intervention required"
                tg_send(msg)
                logger.warning(msg)
                actions.append(f"ROLLBACK FLAGGED: {param}")
                continue

            # Write restart sentinel
            restart_path = os.path.join(BOT_DIR, ".restart_bot")
            with open(restart_path, "w") as f:
                json.dump({"reason": f"rollback {param}", "ts": int(time.time())}, f)

            msg = (
                f"🔙 <b>AUTO-ROLLBACK</b>: {param} {new_value}→{old_value}\n"
                f"WR dropped {pre_wr:.0f}% → {post_metrics['wr']:.0f}% in {(now - changed_at)/3600:.0f} hrs"
            )
            tg_send(msg)
            logger.warning(msg)
            actions.append(f"ROLLBACK: {param}")

    return actions


def _rollback_env(key, value):
    """Update a value in the .env file."""
    env_path = os.path.join(BOT_DIR, ".env")
    if not os.path.exists(env_path):
        return False
    lines = open(env_path).readlines()
    found = False
    with open(env_path + ".tmp", "w") as f:
        for line in lines:
            if line.startswith(f"{key}="):
                f.write(f"{key}={value}\n")
                found = True
            else:
                f.write(line)
    if found:
        os.replace(env_path + ".tmp", env_path)
        logger.info(f"Rolled back {key} to {value} in .env")
    else:
        os.remove(env_path + ".tmp")
        logger.warning(f"Rollback failed: {key} not found in .env")
    return found


def main():
    logger.info("=== Auto-Lifecycle scan started ===")
    factory_state = load_factory_state()

    all_actions = []
    all_actions.extend(scan_kills(factory_state))
    all_actions.extend(scan_edge_decay(factory_state))
    all_actions.extend(scan_promotions(factory_state))
    all_actions.extend(scan_ramps(factory_state))
    all_actions.extend(scan_rollbacks())

    if all_actions:
        save_factory_state(factory_state)
        logger.info(f"Actions taken: {', '.join(all_actions)}")
    else:
        logger.info("No actions needed")

    print(f"[{datetime.now().strftime('%H:%M')}] Lifecycle scan complete. {len(all_actions)} actions.")


if __name__ == "__main__":
    main()
