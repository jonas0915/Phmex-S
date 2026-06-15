"""ST2.0 Recursive Improvement Lab.

A standalone, ISOLATED loop that autonomously evolves the ST2.0 strategy
(book x tape absorption short) by replaying recorded market data through
candidate configs, ranking them relatively, and carrying the winner forward.

Hard invariant: this package NEVER imports bot.py, mutates live state, or
restarts the bot. It reads recorded data read-only. Anything that would put
generated code or a config into the LIVE trading process is gated by a human
(see docs/superpowers/specs/2026-06-15-st2-recursive-improvement-lab-design.md).
"""
