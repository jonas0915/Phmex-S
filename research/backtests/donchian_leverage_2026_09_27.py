"""Donchian ensemble at leverage — backtest (owner request 9/27/2026: "do 5x leverage, do a backtest").

Rule: the bot's own donchian_slot.run_history (frozen 9-lookback ensemble, 25% vol target, cap 2.0).
Leverage L = multiple of the rule's size: position notional = L x w x equity (compounding account).
  L=1 is the paper design; L=5 is the owner's ask (exposure up to 10x equity when w hits its 2.0 cap).
Prices: Coinbase spot daily (BTC-USD, ETH-USD) — long history incl. 2018 and 2022 bears.
Costs: 0.06% taker per side on every |change in notional| (conservative vs 0.01% maker entries);
  funding: Phemex USDT-perp settlements from 2022-11 (longs pay when positive), before that the
  Phemex-era mean per day (assumption, sensitivity reported).
Liquidation: cross-margin account per coin; if the day's LOW would take equity to the maintenance
  margin (0.5% of notional), the account is wiped (equity -> 0) and stays at 0.
Read-only research: no orders, no bot state touched. Data cached to research/backtests/data/.
"""
from __future__ import annotations
import json, math, os, sys, time
from datetime import datetime, timezone
import ccxt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import donchian_slot as ds  # noqa: E402

DATA = os.path.join(HERE, "data"); os.makedirs(DATA, exist_ok=True)
TAKER = 0.0006
MM = 0.005
LEVS = (1, 2, 3, 5)


def day(ms): return datetime.fromtimestamp(ms / 1e3, timezone.utc).strftime("%Y-%m-%d")


def fetch_ohlcv(ex_name, sym, since_iso, cache):
    p = os.path.join(DATA, cache)
    if os.path.exists(p):
        return json.load(open(p))
    ex = getattr(ccxt, ex_name)({"timeout": 20000, "enableRateLimit": True})
    since, out = ex.parse8601(since_iso), []
    while True:
        o = ex.fetch_ohlcv(sym, "1d", since=since, limit=300)
        if not o:
            if not out and since < ex.milliseconds():            # listing starts later: step forward
                since += 300 * 86400000
                continue
            break
        out += [r for r in o if not out or r[0] > out[-1][0]]
        if len(o) < 2 or o[-1][0] <= since:
            break
        since = o[-1][0] + 1
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = [r for r in out if day(r[0]) < today]            # complete UTC daily bars only
    json.dump(out, open(p, "w"))
    return out


def fetch_funding(sym, cache):
    p = os.path.join(DATA, cache)
    if os.path.exists(p):
        return json.load(open(p))
    ex = ccxt.phemex({"timeout": 20000, "enableRateLimit": True})
    since, out = ex.parse8601("2022-11-01T00:00:00Z"), []
    while True:
        f = ex.fetch_funding_rate_history(sym, since=since, limit=100)
        if not f:
            break
        out += [[x["timestamp"], x["fundingRate"]] for x in f if not out or x["timestamp"] > out[-1][0]]
        if f[-1]["timestamp"] <= since or len(f) < 2:
            break
        since = f[-1]["timestamp"] + 1
    json.dump(out, open(p, "w"))
    return out


def simulate(dates, o, h, l, c, w, fund_by_day, fund_default, L):
    """Day i: at close i hold notional L*w[i]*E (rebalanced at the close, taker fee on the change);
    during day i+1 the position earns c[i+1]/c[i]-1, pays funding for day i+1, and is checked against
    day i+1's low for liquidation."""
    E, N, eq, liq, fees, funding = 100.0, 0.0, [100.0], None, 0.0, 0.0
    for i in range(len(c) - 1):
        target = L * w[i] * E
        fee = abs(target - N) * TAKER
        E -= fee; fees += fee; N = target
        if N > 0:
            worst = E + N * (l[i + 1] / c[i] - 1)
            if worst <= MM * N * (l[i + 1] / c[i]):
                liq = dates[i + 1]; E = 0.0; eq.append(0.0)
                eq += [0.0] * (len(c) - 2 - i); break
            fr = fund_by_day.get(dates[i + 1], fund_default)
            E += N * (c[i + 1] / c[i] - 1) - N * fr
            funding += N * fr
            N *= c[i + 1] / c[i]                            # position value drifts with price
        eq.append(E)
    return eq, liq, fees, funding


def stats(dates, eq):
    yrs = (len(eq) - 1) / 365.0
    end = eq[-1]
    cagr = (end / eq[0]) ** (1 / yrs) - 1 if end > 0 and yrs > 0 else -1.0
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v); mdd = max(mdd, 1 - v / peak if peak > 0 else 0)
    rets = [eq[i + 1] / eq[i] - 1 for i in range(len(eq) - 1) if eq[i] > 0]
    mu = sum(rets) / len(rets) if rets else 0
    sd = (sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 if len(rets) > 1 else 0
    by_year = {}
    for i in range(1, len(eq)):
        y = dates[i][:4]
        by_year.setdefault(y, [eq[i - 1], eq[i]])[1] = eq[i]
    return {"end": end, "total_pct": (end / eq[0] - 1) * 100, "cagr_pct": cagr * 100, "max_dd_pct": mdd * 100,
            "sharpe": (mu / sd * math.sqrt(365)) if sd else 0.0,
            "by_year_pct": {y: ((b / a - 1) * 100 if a > 0 else None) for y, (a, b) in by_year.items()}}


def run(coin):
    cb = fetch_ohlcv("coinbase", f"{coin}/USD", "2015-01-01T00:00:00Z", f"coinbase_{coin}_1d.json")
    ph = fetch_ohlcv("phemex", f"{coin}/USDT:USDT", "2022-11-01T00:00:00Z", f"phemex_{coin}_perp_1d.json")
    fr = fetch_funding(f"{coin}/USDT:USDT", f"phemex_{coin}_funding.json")
    dates = [day(r[0]) for r in cb]; o = [r[1] for r in cb]; h = [r[2] for r in cb]
    l = [r[3] for r in cb]; c = [r[4] for r in cb]
    fund_by_day = {}
    for ts, rate in fr:
        if rate is not None:
            fund_by_day[day(ts)] = fund_by_day.get(day(ts), 0.0) + rate
    fund_mean = sum(fund_by_day.values()) / len(fund_by_day)
    _, _, _, infos = ds.run_history(c)
    w = [inf["w"] for inf in infos]
    start = ds.MIN_BARS                                      # fully warm ensemble
    D, O, H, Lo, C, W = (x[start:] for x in (dates, o, h, l, c, w))
    # sanity: perp vs spot closes on overlap, and our w vs the live signal file on the paper window
    ph_close = {day(r[0]): r[4] for r in ph}
    ov = [abs(ph_close[d] / C[i] - 1) for i, d in enumerate(D) if d in ph_close]
    sig = {d["date"]: d["w"] for d in json.load(open(ds.SIGNAL_FILES[f"{coin}/USDT:USDT"]))["days"]}
    wgap = [abs(sig[d] - W[i]) for i, d in enumerate(D) if d in sig]
    res = {"coin": coin, "window": [D[0], D[-1]], "days": len(D), "funding_days": len(fund_by_day),
           "funding_mean_per_day_pct": fund_mean * 100,
           "perp_vs_spot_close_gap_median_pct": sorted(ov)[len(ov) // 2] * 100 if ov else None,
           "w_vs_live_signal_max_gap": max(wgap) if wgap else None, "w_vs_live_signal_days": len(wgap),
           "avg_w": sum(W) / len(W), "hold": stats(D, [100 * x / C[0] for x in C]), "runs": {}}
    for L in LEVS:
        for label, fdef in (("base", fund_mean), ("no_pre2022_funding", 0.0), ("double_pre2022_funding", 2 * fund_mean)):
            if label != "base" and L != 5:
                continue
            eq, liq, fees, funding = simulate(D, O, H, Lo, C, W, fund_by_day, fdef, L)
            s = stats(D, eq); s.update({"liquidated_on": liq, "fees": fees, "funding": funding})
            res["runs"][f"{L}x" + ("" if label == "base" else f"_{label}")] = s
    # exposure actually taken at 5x
    res["max_exposure_at_5x"] = 5 * max(W)
    return res


if __name__ == "__main__":
    out = {c: run(c) for c in ("BTC", "ETH")}
    json.dump(out, open(os.path.join(HERE, "donchian_leverage_2026_09_27.json"), "w"), indent=1)
    for coin, r in out.items():
        print(f"\n== {coin} {r['window'][0]} -> {r['window'][1]} ({r['days']} days)  avg w {r['avg_w']:.3f}  "
              f"max exposure at 5x {r['max_exposure_at_5x']:.2f}x")
        print(f"   checks: perp-vs-spot median close gap {r['perp_vs_spot_close_gap_median_pct']:.3f}%  "
              f"w vs live signal max gap {r['w_vs_live_signal_max_gap']} over {r['w_vs_live_signal_days']} days  "
              f"funding days {r['funding_days']} mean {r['funding_mean_per_day_pct']:.4f}%/day")
        hs = r["hold"]
        print(f"   buy&hold 1x: total {hs['total_pct']:.0f}%  CAGR {hs['cagr_pct']:.1f}%  maxDD {hs['max_dd_pct']:.1f}%")
        for k, s in r["runs"].items():
            print(f"   {k:28s} total {s['total_pct']:9.1f}%  CAGR {s['cagr_pct']:6.1f}%  maxDD {s['max_dd_pct']:5.1f}%  "
                  f"Sharpe {s['sharpe']:.2f}  liquidated {s['liquidated_on']}  fees ${s['fees']:.2f} funding ${s['funding']:.2f}")
        print("   by year (1x | 5x | hold):", {y: (round(r['runs']['1x']['by_year_pct'][y] or -100, 1),
              round(r['runs']['5x']['by_year_pct'].get(y) or -100, 1), round(hs['by_year_pct'][y], 1))
              for y in hs['by_year_pct']})
