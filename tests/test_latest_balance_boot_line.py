"""_latest_balance must also read the boot line (2026-07-16).

After every bot restart there is a <=10-cycle window with no `=== STATS ===`
line in the fresh log, during which the dashboard ticker showed BAL $0.00 /
DD 0.0%. The bot prints `Starting balance: X USDT` (bot.py:751) at every boot —
the parser must accept it as a balance source, with the most recent
balance-bearing line (boot or STATS) winning.
"""
import web_dashboard as wd

STATS = ("2026-07-16 21:13:00 [INFO] === STATS === Trades: 743 (L:400 S:343) | "
         "Win Rate: 48.0% | Total PnL: -74.92 USDT | Balance: 42.10 USDT | Drawdown: 9.2%")
BOOT = "2026-07-16 21:00:13 [INFO] Starting balance: 41.90 USDT"
NOISE = "2026-07-16 21:00:35 [INFO] [WS] Feed ready — streaming 12 pair(s) (5m)"


def test_boot_line_alone_yields_balance():
    assert wd._latest_balance([NOISE, BOOT, NOISE]) == 41.90


def test_latest_line_wins_stats_after_boot():
    assert wd._latest_balance([BOOT, NOISE, STATS]) == 42.10


def test_latest_line_wins_boot_after_stats():
    # Restart after a STATS line: boot balance is the current truth.
    assert wd._latest_balance([STATS, NOISE, BOOT]) == 41.90


def test_no_balance_lines_returns_zero():
    assert wd._latest_balance([NOISE]) == 0.0
