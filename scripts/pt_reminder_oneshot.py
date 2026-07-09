"""One-shot reminder (fires Sat 2026-07-11 9:00 AM PT via launchd): revisit the
PT-token fee-discount purchase. Sends via st2_lab.notify (attempts=4 retry),
then removes its own plist, boots the job out, and deletes itself.

Launched as Python directly (NOT zsh) — launchd+zsh reading ~/Desktop scripts
hits TCC exit 127 (lessons.md); the Python framework binary has disk access
like every other Phmex-S launchd job (adjudicator, nightly-research)."""
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from st2_lab.notify import telegram_alert  # noqa: E402

PLIST = os.path.expanduser("~/Library/LaunchAgents/com.phmex.pt-reminder.plist")

ok = telegram_alert(
    "\U0001FA99 WEEKEND REMINDER — PT-token fee discount\n\n"
    "Revisit buying ~$25-30 of PT (Phemex token) for the 10% futures-fee discount:\n"
    "1. Buy PT (~$25-30 = ~3-month float at current volume)\n"
    "2. Transfer PT into the FUTURES account (not spot)\n"
    "3. Enable the fee-deduction toggle in Fee Level / Fee Discount settings\n\n"
    "Caveat: if PT runs out, trades silently pay full fee. "
    "Research: docs/overnight-2026-07-05/r2_fee_research.md. "
    "After enabling, ask Claude to add the fee-rate watchdog.",
    attempts=4)
print("pt-reminder telegram:", "sent" if ok else "FAILED")

# Self-cleanup only after a successful send — on failure the job stays loaded
# so a manual `launchctl kickstart gui/501/com.phmex.pt-reminder` can re-fire it.
if ok:
    try:
        os.remove(PLIST)
    except OSError:
        pass
    try:
        os.remove(os.path.abspath(__file__))
    except OSError:
        pass
    # bootout last — it kills this process
    subprocess.run(["/bin/launchctl", "bootout", "gui/501/com.phmex.pt-reminder"],
                   check=False)
