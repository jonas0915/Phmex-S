"""TEST 1 (funding-settlement microstructure) + TEST 4 (CME weekend-gap fill)."""
import json, os
import numpy as np
import pandas as pd
from stats_lib import block_bootstrap_ci, make_time_folds, benjamini_hochberg, fmt_pct

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FUND_DATA = os.path.join(HERE, "..", "funding-2026-06-13", "data")

FEE_TAKER_RT = 0.00132
FEE_MAKER_RT = 0.00024


def section(t):
    print("\n" + "=" * 86)
    print(t)
    print("=" * 86)


def load_binanceus():
    d = json.load(open(os.path.join(DATA, "ohlcv1h_binanceus.json")))
    out = {}
    for sym, rows in d.items():
        df = pd.DataFrame(rows, columns=["ts", "o", "h", "l", "c", "v"])
        df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.sort_values("ts").reset_index(drop=True)
        df["gap"] = (df["dt"] - df["dt"].shift(1)).dt.total_seconds() / 3600.0
        out[sym] = df
    return out


# ---------------------------------------------------------------------------
# TEST 1 — FUNDING-SETTLEMENT MICROSTRUCTURE
# ---------------------------------------------------------------------------
def test_funding_settlement(data):
    section("TEST 1 — FUNDING-SETTLEMENT MICROSTRUCTURE")
    print("Phemex funding settles every 8h at 00:00 / 08:00 / 16:00 UTC.")
    print("Hypothesis: longs pay when funding>0 -> sell PRE-stamp (dip), bounce POST-stamp.")
    print("We measure, conditioned on funding SIGN/magnitude at each stamp T:")
    print("  PRE  drift = close(T) / close(T-2h) - 1   (the 2h leading into the stamp)")
    print("  POST drift = close(T+2h) / close(T) - 1   (the 2h after the stamp)")
    print("Funding is paid AT T for the interval ending at T. Binanceus spot price used")
    print("(no funding on spot, so price is uncontaminated by the funding payment itself).\n")

    fund = json.load(open(os.path.join(FUND_DATA, "funding.json")))
    # fund: {symbol_key: [[ts, rate], ...]}  symbol keys like 'BTC/USDT:USDT'
    # map perp symbol -> binanceus spot symbol
    def spot_key(perp):
        base = perp.split("/")[0]
        return f"{base}/USDT"

    results = []
    pre_pool, post_pool, prepost_pool = [], [], []  # for pooled significance, pos-funding only

    print(f"{'sym':10s} {'nstamp':>6} | {'PREpos%':>8} {'POSTpos%':>8} {'P-Pspr%':>8} "
          f"| {'PREneg%':>8} {'POSTneg%':>8}")
    for perp, rows in fund.items():
        sk = spot_key(perp)
        if sk not in data:
            continue
        df = data[sk]
        # build a fast close lookup by timestamp (hourly grid)
        cmap = dict(zip(df["ts"].values, df["c"].values))
        H = 3600_000
        recs = []
        for ts, rate in rows:
            ts = int(ts)
            # align to hour
            if ts % H != 0:
                ts = (ts // H) * H
            c_T = cmap.get(ts)
            c_pre = cmap.get(ts - 2 * H)
            c_post = cmap.get(ts + 2 * H)
            if c_T is None or c_pre is None or c_post is None:
                continue
            pre = c_T / c_pre - 1
            post = c_post / c_T - 1
            recs.append((ts, rate, pre, post))
        if len(recs) < 50:
            continue
        rr = pd.DataFrame(recs, columns=["ts", "rate", "pre", "post"])
        pos = rr[rr["rate"] > 0]
        neg = rr[rr["rate"] < 0]
        results.append((sk, rr, pos, neg))
        # pooled pos-funding (most common case)
        pre_pool.extend(pos["pre"].values)
        post_pool.extend(pos["post"].values)
        prepost_pool.extend((pos["post"] - pos["pre"]).values)
        print(f"{sk:10s} {len(rr):6d} | "
              f"{fmt_pct(pos['pre'].mean()):>8} {fmt_pct(pos['post'].mean()):>8} "
              f"{fmt_pct(pos['post'].mean()-pos['pre'].mean()):>8} | "
              f"{fmt_pct(neg['pre'].mean()) if len(neg) else 'na':>8} "
              f"{fmt_pct(neg['post'].mean()) if len(neg) else 'na':>8}")

    # Pooled significance (positive-funding case: expect PRE<0, POST>0 if hypothesis true)
    print("\n--- POOLED (positive-funding stamps), block-bootstrap CI ---")
    for label, pool in [("PRE drift (expect<0)", pre_pool),
                        ("POST drift (expect>0)", post_pool),
                        ("POST-PRE spread (expect>0)", prepost_pool)]:
        m, lo, hi, p = block_bootstrap_ci(np.array(pool), n_boot=4000, block=3, seed=7)
        print(f"  {label:28s} n={len(pool):6d} mean%={fmt_pct(m):>9} "
              f"CI[{fmt_pct(lo)},{fmt_pct(hi)}] p={p:.4f}")

    # Strategy framing: the structural play is SHORT into stamp / LONG out of stamp when
    # funding very positive. Net round-trip needs to beat fees. Evaluate the POST-stamp
    # bounce as a long entered at T, exit T+2h, only on high-positive-funding stamps.
    print("\n--- TRADE TEST: LONG at stamp T, exit T+2h, gated on funding magnitude ---")
    print("    (the 'post-settlement bounce' play). Net of taker 0.132% / maker 0.024% RT.\n")
    big = []
    for sk, rr, pos, neg in results:
        big.append(rr.assign(sym=sk))
    allrr = pd.concat(big, ignore_index=True)
    print(f"{'gate (rate>=)':>14} {'n':>6} {'grossPost%':>10} {'netTaker%':>10} {'netMaker%':>10} {'WR%':>6}")
    for thr in [0.0, 0.0001, 0.0003, 0.0005, 0.001]:
        g = allrr[allrr["rate"] >= thr]
        if len(g) < 20:
            print(f"{thr:14.4%} {len(g):6d}  (too few)")
            continue
        gp = g["post"].mean()
        print(f"{thr:14.4%} {len(g):6d} {fmt_pct(gp):>10} "
              f"{fmt_pct(gp-FEE_TAKER_RT):>10} {fmt_pct(gp-FEE_MAKER_RT):>10} "
              f"{(g['post']>0).mean()*100:6.1f}")

    # Also test the SHORT-into-stamp play (enter T-2h, exit T) on high-positive funding
    print("\n--- TRADE TEST: SHORT at T-2h, cover at T, gated on funding magnitude ---")
    print(f"{'gate (rate>=)':>14} {'n':>6} {'grossShort%':>11} {'netTaker%':>10} {'netMaker%':>10} {'WR%':>6}")
    for thr in [0.0, 0.0001, 0.0003, 0.0005, 0.001]:
        g = allrr[allrr["rate"] >= thr]
        if len(g) < 20:
            continue
        gs = (-g["pre"]).mean()  # short profit = -pre drift
        print(f"{thr:14.4%} {len(g):6d} {fmt_pct(gs):>11} "
              f"{fmt_pct(gs-FEE_TAKER_RT):>10} {fmt_pct(gs-FEE_MAKER_RT):>10} "
              f"{((-g['pre'])>0).mean()*100:6.1f}")
    print("\nNote: Phemex funding history only spans ~195 days (Dec 2025 - Jun 2026),")
    print("so this test is regime-limited; treat marginal results with caution.")


# ---------------------------------------------------------------------------
# TEST 4 — CME WEEKEND-GAP FILL (BTC)
# ---------------------------------------------------------------------------
def test_cme_gap(data):
    section("TEST 4 — CME WEEKEND-GAP FILL (BTC)")
    print("CME BTC futures close Fri 22:00 UTC (5pm ET), reopen Sun 23:00 UTC (6pm ET).")
    print("Crypto trades 24/7, so a 'gap' forms = Sun-reopen price vs Fri-close price.")
    print("Hypothesis: spot price tends to REVERT to fill the gap (move back toward Fri close).")
    print("We proxy CME with binanceus spot at those stamps (standard proxy).\n")

    df = data["BTC/USDT"].copy()
    df = df.set_index("dt")
    c = df["c"]

    # Build weekly observations
    recs = []
    # iterate over Fridays
    fri_close_hour = 22  # UTC
    sun_open_hour = 23   # UTC
    # find all timestamps at Fri 22:00 and the following Sun 23:00
    s = c.copy()
    idx = s.index
    fri_mask = (idx.dayofweek == 4) & (idx.hour == fri_close_hour)
    for t_fri in idx[fri_mask]:
        t_sun = t_fri + pd.Timedelta(days=2, hours=1)  # Fri22:00 -> Sun23:00
        if t_sun not in s.index or t_fri not in s.index:
            continue
        p_fri = s.loc[t_fri]
        p_sun = s.loc[t_sun]
        gap = p_sun / p_fri - 1  # + = gap up over weekend
        # forward: does price move back toward p_fri after Sun open? measure return
        # over next 24h and whether it closes the gap.
        for hfwd in [6, 12, 24]:
            t_fwd = t_sun + pd.Timedelta(hours=hfwd)
            if t_fwd not in s.index:
                p_fwd = np.nan
            else:
                p_fwd = s.loc[t_fwd]
            recs.append((t_fri, gap, hfwd, p_sun, p_fwd))
    rr = pd.DataFrame(recs, columns=["t_fri", "gap", "hfwd", "p_sun", "p_fwd"])
    rr = rr.dropna()
    rr["fwd_ret"] = rr["p_fwd"] / rr["p_sun"] - 1
    # gap-fill signal: if gap up (>0), reversion means fwd_ret<0; trade = SHORT.
    # if gap down (<0), reversion means fwd_ret>0; trade = LONG.
    # "reversion return" = -sign(gap)*fwd_ret  (profit if price reverts)
    rr["rev_ret"] = -np.sign(rr["gap"]) * rr["fwd_ret"]

    print(f"Weeks analyzed: {rr['t_fri'].nunique()}  ({rr['t_fri'].min().date()} .. {rr['t_fri'].max().date()})")
    print(f"Gap up weeks: {(rr[rr.hfwd==24].gap>0).sum()}  gap down: {(rr[rr.hfwd==24].gap<0).sum()}")
    print(f"Mean |gap|: {fmt_pct(rr[rr.hfwd==24]['gap'].abs().mean())}%\n")

    print(f"{'horizon':>8} {'corr(gap,fwd)':>13} {'revRet%':>9} {'CI':>22} {'p':>7} {'WR%':>6}")
    for hfwd in [6, 12, 24]:
        g = rr[rr["hfwd"] == hfwd]
        corr = np.corrcoef(g["gap"], g["fwd_ret"])[0, 1]
        m, lo, hi, p = block_bootstrap_ci(g["rev_ret"].values, n_boot=4000, block=4, seed=hfwd)
        wr = (g["rev_ret"] > 0).mean() * 100
        print(f"{hfwd:6d}h  {corr:13.4f} {fmt_pct(m):>9} "
              f"[{fmt_pct(lo)},{fmt_pct(hi)}]   {p:7.4f} {wr:6.1f}")

    # Condition on gap SIZE — small gaps fill more reliably (documented)
    print("\n--- Conditioned on |gap| size (24h reversion) ---")
    g24 = rr[rr["hfwd"] == 24].copy()
    g24["absgap"] = g24["gap"].abs()
    qs = g24["absgap"].quantile([0.33, 0.66]).values
    def bucket(x):
        return "small" if x <= qs[0] else ("mid" if x <= qs[1] else "large")
    g24["bk"] = g24["absgap"].apply(bucket)
    for bk in ["small", "mid", "large"]:
        b = g24[g24["bk"] == bk]
        m, lo, hi, p = block_bootstrap_ci(b["rev_ret"].values, n_boot=3000, block=4, seed=1)
        print(f"  {bk:6s} n={len(b):4d} |gap|range gross-revRet%={fmt_pct(m):>9} "
              f"net-taker%={fmt_pct(m-FEE_TAKER_RT):>9} p={p:.4f} WR={(b['rev_ret']>0).mean()*100:5.1f}%")

    # Walk-forward + per-year on 24h all-gaps reversion
    print("\n--- Walk-forward (24h, all gaps) ---")
    g24 = g24.sort_values("t_fri").reset_index(drop=True)
    folds = make_time_folds(len(g24), 5)
    full = g24["rev_ret"].mean()
    fm = [g24["rev_ret"].values[idx].mean() for idx in folds]
    same = sum(1 for f in fm if np.sign(f) == np.sign(full))
    print(f"  full revRet% {fmt_pct(full)} | fold means% {[round(f*100,4) for f in fm]} | sign-match {same}/5")
    g24["year"] = g24["t_fri"].dt.year
    yr = g24.groupby("year")["rev_ret"].mean()
    print("  per-year revRet%:", {int(y): round(v*100, 4) for y, v in yr.items()})


if __name__ == "__main__":
    data = load_binanceus()
    test_funding_settlement(data)
    test_cme_gap(data)
