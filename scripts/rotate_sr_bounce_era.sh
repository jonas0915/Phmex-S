#!/bin/zsh
# SR_BOUNCE era rotation (2026-07-30, v2 fixed-geometry prereg).
# Run ONLY while the bot is STOPPED, immediately before the v2 restart:
#   1. archives the era-1 ledger (n=50 KILL final) to _era1.json
#   2. clears killed_at in the mode sidecar so the slot boots enabled
# Idempotent: refuses to re-archive if _era1.json already exists.
set -e
cd "$(dirname "$0")/.."

if pgrep -f "Python.*main\.py" > /dev/null; then
  echo "REFUSING: bot is running (edit≠live rule — stop it first)" >&2
  exit 1
fi

if [ -f trading_state_SR_BOUNCE_era1.json ]; then
  echo "REFUSING: trading_state_SR_BOUNCE_era1.json already exists" >&2
  exit 1
fi

n=$(python3 -c "import json;print(len(json.load(open('trading_state_SR_BOUNCE.json'))['closed_trades']))")
if [ "$n" -lt 50 ]; then
  echo "REFUSING: ledger has n=$n < 50 — this is not the decided era-1 file" >&2
  exit 1
fi

# Only a DECIDED ledger may be archived: the kill must actually be on record
# (review catch 7/30 — without this, misuse could archive a healthy ledger).
ka=$(python3 -c "import json;d=json.load(open('trading_state_SR_BOUNCE_mode.json'));print(d.get('killed_at') or '')")
if [ -z "$ka" ]; then
  echo "REFUSING: sidecar killed_at not set — ledger is not a decided kill" >&2
  exit 1
fi

mv trading_state_SR_BOUNCE.json trading_state_SR_BOUNCE_era1.json
python3 - << 'PY'
import json
p = "trading_state_SR_BOUNCE_mode.json"
d = json.load(open(p))
d["killed_at"] = None
json.dump(d, open(p, "w"))
print("sidecar killed_at cleared:", d)
PY
echo "era-1 ledger archived (n=$n) — fresh v2 ledger will be created on boot"
