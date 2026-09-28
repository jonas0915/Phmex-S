"""Donchian ensemble at leverage — CORRECTED backtest (v2), after the 9/27 six-agent audit.

Fixes vs v1 (donchian_leverage_2026_09_27.py, kept for the record):
  1. Funding = real history, not an assumed mean: Phemex USDT perp (2022-11 ->), Deribit perp
     (2019-04-30 ->), BitMEX XBTUSD (BTC, 2016-05 ->). ETH before 2019-04-30 uses BTC's BitMEX rate as
     a stand-in (BitMEX ETHUSD is a quanto contract with distorted funding) — stated assumption.
  2. Sizing like the spec/bot: rebalance to L x w x equity only when the rule's weight w changes;
     otherwise the position drifts with price (v1 re-levered to equity every day).
  3. Bad prints cleaned: a daily low below 50% of min(open, close) is replaced by min(open, close)
     (Coinbase BTC 2017-04-15 low $0.06, ETH 2017-06-21 low $0.10) — listed in the output.
  4. Max drawdown reported on closes AND on intraday lows.
Costs 0.06% taker per side; liquidation when the day's low takes equity to 0.5% maintenance margin.
Read-only research: no orders, no bot state. Data cache in research/backtests/data/ (gitignored).
"""
from __future__ import annotations
import json, math, os, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
import donchian_slot as ds                                       # noqa: E402
from donchian_leverage_2026_09_27 import day, fetch_ohlcv, fetch_funding   # noqa: E402

DATA = os.path.join(HERE, "data")
TAKER, MM = 0.0006, 0.005
WINDOWS = {"full": None, "phemex_era_2022-11-04": "2022-11-04", "post_publication_2025-04-01": "2025-04-01",
           "bear_2025-08-01_to_2026-07-15": ("2025-08-01", "2026-07-15"), "last_12m": "2025-09-27"}


def funding_by_day(coin):
    by, src = {}, {}
    bm = json.load(open(os.path.join(DATA, "bitmex_XBTUSD.json")))                 # [iso, rate] per 8h
    for iso, r in bm:
        if r is not None:
            d = iso[:10]; by[d] = by.get(d, 0.0) + r; src[d] = "bitmex_XBTUSD"
    der = json.load(open(os.path.join(DATA, f"deribit_{coin}-PERPETUAL.json")))    # {day: daily sum}
    for d, r in der.items():
        by[d] = r; src[d] = "deribit"
    ph = {}
    for ts, r in fetch_funding(f"{coin}/USDT:USDT", f"phemex_{coin}_funding.json"):
        if r is not None:
            ph[day(ts)] = ph.get(day(ts), 0.0) + r
    for d, r in ph.items():
        by[d] = r; src[d] = "phemex"
    return by, src


def clean_lows(dates, o, l, c):
    fixed = []
    for i in range(len(l)):
        floor = min(o[i], c[i])
        if l[i] < 0.5 * floor:
            fixed.append((dates[i], l[i], floor)); l[i] = floor
    return fixed


def simulate(c, l, w, fund, L, rebalance="on_change"):
    """Returns (equity at closes, equity at intraday lows, liquidation index, fees, funding, turnover)."""
    E, N, eq, eq_low, fees, paid, turn = 100.0, 0.0, [100.0], [100.0], 0.0, 0.0, 0.0
    for i in range(len(c) - 1):
        target = L * w[i] * E
        drifted = target > 0 and abs(N / target - 1) > 0.20
        if rebalance == "daily" or i == 0 or w[i] != w[i - 1] or (rebalance == "drift20" and drifted):
            fee = abs(target - N) * TAKER
            turn += abs(target - N) / E if E > 0 else 0.0     # turnover in multiples of equity
            E -= fee; fees += fee; N = target
        low_move = l[i + 1] / c[i] - 1
        if N > 0 and E + N * low_move <= MM * N * (1 + low_move):
            return eq + [0.0] * (len(c) - 1 - i), eq_low + [0.0] * (len(c) - 1 - i), i + 1, fees, paid, turn
        eq_low.append(E + N * low_move)
        fr = fund[i + 1]
        E += N * (c[i + 1] / c[i] - 1) - N * fr
        paid += N * fr
        N *= c[i + 1] / c[i]
        eq.append(E)
    return eq, eq_low, None, fees, paid, turn


def stats(eq, eq_low, i0=0, i1=None):
    e = eq[i0:(i1 or len(eq) - 1) + 1]; el = eq_low[i0:(i1 or len(eq) - 1) + 1]
    yrs = (len(e) - 1) / 365.0
    end = e[-1] / e[0] if e[0] > 0 else 0.0
    peak, dd, dd_low = e[0], 0.0, 0.0
    for v, vl in zip(e, el):
        dd_low = max(dd_low, 1 - vl / peak if peak > 0 else 0)
        peak = max(peak, v); dd = max(dd, 1 - v / peak if peak > 0 else 0)
    r = [e[k + 1] / e[k] - 1 for k in range(len(e) - 1) if e[k] > 0]
    mu = sum(r) / len(r) if r else 0.0
    sd = (sum((x - mu) ** 2 for x in r) / (len(r) - 1)) ** 0.5 if len(r) > 1 else 0.0
    return {"total_pct": (end - 1) * 100, "cagr_pct": ((end ** (1 / yrs) - 1) * 100 if end > 0 and yrs > 0 else -100.0),
            "max_dd_pct": dd * 100, "max_dd_at_lows_pct": dd_low * 100,
            "sharpe": mu / sd * math.sqrt(365) if sd else 0.0, "years": yrs}


def run(coin):
    cb = fetch_ohlcv("coinbase", f"{coin}/USD", "2015-01-01T00:00:00Z", f"coinbase_{coin}_1d.json")
    dates = [day(r[0]) for r in cb]; o = [r[1] for r in cb]; l = [r[3] for r in cb]; c = [r[4] for r in cb]
    bad = clean_lows(dates, o, l, c)
    by, src = funding_by_day(coin)
    btc_by = funding_by_day("BTC")[0] if coin != "BTC" else by
    w_all = [inf["w"] for inf in ds.run_history(c)[3]]
    s = ds.MIN_BARS
    D, C, Lo, W = dates[s:], c[s:], l[s:], w_all[s:]
    fund, fsrc = [], {}
    for d in D:
        if d in by:
            fund.append(by[d]); k = src[d]
        elif d in btc_by:
            fund.append(btc_by[d]); k = "bitmex_XBTUSD (BTC stand-in)"
        else:
            fund.append(0.0); k = "none (0)"
        fsrc[k] = fsrc.get(k, 0) + 1
    out = {"coin": coin, "window": [D[0], D[-1]], "bad_lows_cleaned": bad, "funding_sources_days": fsrc,
           "avg_w": sum(W) / len(W), "max_w": max(W), "runs": {}}
    idx = {d: i for i, d in enumerate(D)}

    def wins(eq, eql):
        res = {}
        for name, spec in WINDOWS.items():
            if spec is None:
                res[name] = stats(eq, eql)
            elif isinstance(spec, tuple):
                res[name] = stats(eq, eql, idx[spec[0]], idx[spec[1]])
            else:
                res[name] = stats(eq, eql, idx[spec])
        return res
    hold = [100 * x / C[0] for x in C]
    hold_low = [100.0] + [100 * Lo[i] / C[0] for i in range(1, len(C))]
    out["buy_hold_1x"] = wins(hold, hold_low)
    for L in (1, 2, 3, 5, 6, 7, 8):
        eq, eql, liq, fees, paid, turn = simulate(C, Lo, W, fund, L)
        out["runs"][f"{L}x"] = {"liquidated_on": D[liq] if liq else None, "fees": fees, "funding": paid,
                                "turnover_x_per_year": turn / ((len(C) - 1) / 365), "windows": wins(eq, eql),
                                "calendar_years_pct": {y: v for y, v in _years(D, eq).items()}}
    # exposure-matched constant hold at 5x (same average exposure, same costs, rebalanced when drifted >20%)
    avg = 5 * sum(W) / len(W)
    eq, eql, liq, fees, paid, _ = simulate(C, Lo, [avg / 5] * len(W), fund, 5, rebalance="drift20")
    out["matched_hold_5x"] = {"exposure": avg, "liquidated_on": D[liq] if liq else None, "windows": wins(eq, eql)}
    # sensitivity: v1-style daily re-levering, and 2x funding
    eq, eql, liq, *_ = simulate(C, Lo, W, fund, 5, rebalance="daily")
    out["sens_5x_daily_relever"] = {"liquidated_on": D[liq] if liq else None, "full": stats(eq, eql)}
    eq, eql, liq, *_ = simulate(C, Lo, W, [2 * f for f in fund], 5)
    out["sens_5x_double_funding"] = {"liquidated_on": D[liq] if liq else None, "full": stats(eq, eql),
                                     "phemex_era": stats(eq, eql, idx["2022-11-04"])}
    return out


def _years(D, eq):
    ys = {}
    for i in range(1, len(eq)):
        y = D[i][:4]
        ys.setdefault(y, [eq[i - 1], eq[i]])[1] = eq[i]
    return {y: ((b / a - 1) * 100 if a > 0 else None) for y, (a, b) in ys.items()}


if __name__ == "__main__":
    res = {c: run(c) for c in ("BTC", "ETH")}
    json.dump(res, open(os.path.join(HERE, "donchian_leverage_v2_2026_09_27.json"), "w"), indent=1)
    for coin, r in res.items():
        print(f"\n== {coin} {r['window'][0]} -> {r['window'][1]}  avg w {r['avg_w']:.3f} max w {r['max_w']:.3f}")
        print("   bad lows cleaned:", r["bad_lows_cleaned"], " funding days by source:", r["funding_sources_days"])
        for L, x in r["runs"].items():
            f = x["windows"]["full"]
            print(f"   {L:3s} full CAGR {f['cagr_pct']:7.1f}%  DD {f['max_dd_pct']:5.1f}% (at lows {f['max_dd_at_lows_pct']:5.1f}%)  "
                  f"Sharpe {f['sharpe']:.2f}  liq {x['liquidated_on']}  turnover {x['turnover_x_per_year']:.1f}x/yr")
        for name in WINDOWS:
            b = r["buy_hold_1x"][name]; x1 = r["runs"]["1x"]["windows"][name]; x5 = r["runs"]["5x"]["windows"][name]
            m = r["matched_hold_5x"]["windows"][name]
            print(f"   [{name}] total%  hold {b['total_pct']:8.1f} | 1x {x1['total_pct']:7.1f} | 5x {x5['total_pct']:9.1f} "
                  f"(DD {x5['max_dd_pct']:.1f}) | matched-hold@5x-exposure {m['total_pct']:8.1f} (DD {m['max_dd_pct']:.1f})")
        print("   5x by year:", {y: round(v, 1) if v is not None else None for y, v in r["runs"]["5x"]["calendar_years_pct"].items()})
        print("   sens 5x daily re-lever:", {k: round(v, 1) for k, v in r["sens_5x_daily_relever"]["full"].items() if k != 'years'},
              " | 5x double funding full CAGR", round(r["sens_5x_double_funding"]["full"]["cagr_pct"], 1),
              "phemex-era CAGR", round(r["sens_5x_double_funding"]["phemex_era"]["cagr_pct"], 1))
