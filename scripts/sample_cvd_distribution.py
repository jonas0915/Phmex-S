"""
Sample cvd_slope and large_trade_bias distribution from live Phemex WS trades.

Run this for ~10 minutes against 5 symbols, then prints percentiles + how often
the ±0.3 gate would block. Standalone — does NOT touch the running bot.

Usage:
    python3 scripts/sample_cvd_distribution.py
"""
import asyncio
import collections
import time
import statistics
import ccxt.pro as ccxtpro

SYMBOLS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "LINK/USDT:USDT",
]
DURATION_S = 600        # 10 minutes
SAMPLE_EVERY_S = 5      # snapshot computed metric every 5s

# Per-symbol state mirroring ws_feed.py
candle_deltas: dict[str, collections.deque] = {s: collections.deque(maxlen=10) for s in SYMBOLS}
current_candle_start: dict[str, int] = {s: 0 for s in SYMBOLS}
current_delta: dict[str, float] = {s: 0.0 for s in SYMBOLS}
trade_count: dict[str, int] = {s: 0 for s in SYMBOLS}
recent_notionals: dict[str, collections.deque] = {s: collections.deque(maxlen=200) for s in SYMBOLS}
recent_large_sides: dict[str, collections.deque] = {s: collections.deque(maxlen=50) for s in SYMBOLS}

# Captured samples
cvd_slope_samples: list[float] = []
large_bias_samples: list[float] = []
large_count_samples: list[int] = []
trade_count_samples: list[int] = []


def compute_cvd_slope(sym: str) -> float:
    deltas = list(candle_deltas[sym])
    if len(deltas) < 2:
        return 0.0
    half = len(deltas) // 2
    diff = sum(deltas[half:]) - sum(deltas[:half])
    total_abs = sum(abs(d) for d in deltas)
    return diff / total_abs if total_abs > 0 else 0.0


def compute_large_bias(sym: str) -> tuple[float, int]:
    sides = list(recent_large_sides[sym])
    if len(sides) < 5:
        return 0.0, len(sides)
    buys = sum(1 for s in sides if s > 0)
    sells = sum(1 for s in sides if s < 0)
    denom = max(1, buys + sells)
    return (buys - sells) / denom, buys + sells


async def watch_symbol(exchange, sym: str):
    while True:
        try:
            trades = await exchange.watch_trades(sym)
            for t in trades:
                cost = t.get("cost") or (t.get("amount", 0) * t.get("price", 0))
                ts = t.get("timestamp", 0)
                cs = (ts // 300_000) * 300_000
                if current_candle_start[sym] and cs != current_candle_start[sym]:
                    candle_deltas[sym].append(current_delta[sym])
                    current_delta[sym] = 0.0
                current_candle_start[sym] = cs
                side = t.get("side")
                signed = cost if side == "buy" else -cost
                current_delta[sym] += signed
                trade_count[sym] += 1
                if cost and cost > 0:
                    n = recent_notionals[sym]
                    if len(n) >= 20:
                        sn = sorted(n)
                        median = sn[len(sn) // 2]
                        threshold = max(median * 5.0, 1.0)
                        if cost >= threshold:
                            recent_large_sides[sym].append(1 if side == "buy" else -1)
                    n.append(cost)
        except Exception as e:
            print(f"[{sym}] error: {e}")
            await asyncio.sleep(2)


async def sampler():
    end = time.time() + DURATION_S
    while time.time() < end:
        await asyncio.sleep(SAMPLE_EVERY_S)
        for s in SYMBOLS:
            cvd_s = compute_cvd_slope(s)
            lb, lc = compute_large_bias(s)
            if trade_count[s] > 20:
                cvd_slope_samples.append(cvd_s)
                large_bias_samples.append(lb)
                large_count_samples.append(lc)
                trade_count_samples.append(trade_count[s])


def pct(xs, p):
    if not xs:
        return float("nan")
    xs2 = sorted(xs)
    k = int(len(xs2) * p)
    return xs2[min(k, len(xs2) - 1)]


def report():
    print("\n========== CVD SLOPE / LARGE BIAS DISTRIBUTION ==========")
    print(f"Samples: {len(cvd_slope_samples)} (across {len(SYMBOLS)} symbols, {DURATION_S}s)")
    if not cvd_slope_samples:
        print("No samples (volume too low).")
        return

    cs = cvd_slope_samples
    print("\n-- cvd_slope (normalized [-1,1]) --")
    print(f"  min={min(cs):+.3f}  p10={pct(cs,.10):+.3f}  p25={pct(cs,.25):+.3f}  "
          f"median={pct(cs,.5):+.3f}  p75={pct(cs,.75):+.3f}  p90={pct(cs,.90):+.3f}  max={max(cs):+.3f}")
    print(f"  mean={statistics.mean(cs):+.3f}  stdev={statistics.pstdev(cs):.3f}")
    fired_long = sum(1 for v in cs if v < -0.3) / len(cs) * 100
    fired_short = sum(1 for v in cs if v > 0.3) / len(cs) * 100
    fired_long_05 = sum(1 for v in cs if v < -0.5) / len(cs) * 100
    fired_short_05 = sum(1 for v in cs if v > 0.5) / len(cs) * 100
    print(f"  Gate ±0.3 -> blocks LONG {fired_long:.1f}% of the time, SHORT {fired_short:.1f}%")
    print(f"  Gate ±0.5 -> blocks LONG {fired_long_05:.1f}% of the time, SHORT {fired_short_05:.1f}%")

    lb = large_bias_samples
    print("\n-- large_trade_bias [-1,1] --")
    print(f"  min={min(lb):+.3f}  p10={pct(lb,.10):+.3f}  median={pct(lb,.5):+.3f}  "
          f"p90={pct(lb,.90):+.3f}  max={max(lb):+.3f}")
    long_b = sum(1 for v in lb if v < -0.3) / len(lb) * 100
    short_b = sum(1 for v in lb if v > 0.3) / len(lb) * 100
    print(f"  Gate ±0.3 -> blocks LONG {long_b:.1f}%, SHORT {short_b:.1f}%")
    nz = sum(1 for v in lb if v != 0.0) / len(lb) * 100
    print(f"  Active (>=5 large trades): {nz:.1f}% of samples")

    lc = large_count_samples
    print(f"\n-- large_trade_count -- median={pct(lc,.5)}  max={max(lc)}")
    tc = trade_count_samples
    print(f"-- trade_count -- median={pct(tc,.5)}  max={max(tc)}")


async def main():
    ex = ccxtpro.phemex({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    try:
        tasks = [asyncio.create_task(watch_symbol(ex, s)) for s in SYMBOLS]
        tasks.append(asyncio.create_task(sampler()))
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=DURATION_S + 10)
    finally:
        report()
        try:
            await ex.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
