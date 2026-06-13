"""Funding-rate edge analysis for Phemex USDT perps.

Inputs (from fetch_funding.py):
  data/funding.json  -> {symbol: [[ts_ms, fundingRate], ...]}
  data/ohlcv1h.json  -> {symbol: [[ts,o,h,l,c,v], ...]}

Fee assumptions (from docs/2026-06-11-fee-ground-truth.md, exact observed):
  taker = 0.06% per side, maker = 0.01% per side.

Funding sign convention (ccxt/Phemex): positive fundingRate => LONGS PAY SHORTS.
So a SHORT position RECEIVES funding when rate>0; a LONG receives when rate<0.

All numbers computed from real fetched data. No fabrication.
"""
import json, os, math, statistics
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

TAKER = 0.0006   # 0.06% per side
MAKER = 0.0001   # 0.01% per side

def dt(ms):
    return datetime.fromtimestamp(ms/1000, tz=timezone.utc)

def load():
    funding = json.load(open(os.path.join(DATA, "funding.json")))
    ohlcv = json.load(open(os.path.join(DATA, "ohlcv1h.json")))
    return funding, ohlcv

def detect_interval_h(rows):
    """Median spacing between settlements, in hours."""
    if len(rows) < 3:
        return None
    diffs = [(rows[i+1][0]-rows[i][0])/3600000 for i in range(len(rows)-1)]
    diffs = [d for d in diffs if d > 0]
    return statistics.median(diffs) if diffs else None

def ohlcv_close_map(rows):
    """ts_ms -> close, plus sorted ts list for lookups."""
    return {r[0]: r[4] for r in rows}

def close_at_or_after(ts, closes_sorted, close_by_ts):
    """Return close of the 1h candle whose open == ts (funding ts aligns to hour)."""
    return close_by_ts.get(ts)

# ---------------------------------------------------------------------------
# TEST 1: Funding distribution / APR
# ---------------------------------------------------------------------------
def test1_distribution(funding):
    print("\n" + "="*78)
    print("TEST 1 — FUNDING DISTRIBUTION & ANNUALIZED APR (per symbol)")
    print("="*78)
    print(f"{'symbol':<14}{'n':>6}{'int_h':>6}{'mean%':>9}{'median%':>9}{'|mean|%':>9}"
          f"{'APR%':>9}{'absAPR%':>9}{'%pos':>7}{'max%':>8}{'min%':>8}")
    results = {}
    for sym, rows in funding.items():
        if len(rows) < 10:
            continue
        ih = detect_interval_h(rows)
        rates = [r[1] for r in rows]
        n = len(rates)
        mean = statistics.mean(rates)
        med = statistics.median(rates)
        absmean = statistics.mean(abs(r) for r in rates)
        per_year = (365*24)/ih  # settlements per year
        apr = mean * per_year          # signed APR (what a passive long pays)
        abs_apr = absmean * per_year   # harvestable magnitude APR
        pct_pos = 100*sum(1 for r in rates if r > 0)/n
        results[sym] = dict(n=n, ih=ih, mean=mean, apr=apr, abs_apr=abs_apr,
                            pct_pos=pct_pos, absmean=absmean)
        print(f"{sym.split('/')[0]:<14}{n:>6}{ih:>6.1f}{mean*100:>9.4f}{med*100:>9.4f}"
              f"{absmean*100:>9.4f}{apr*100:>9.2f}{abs_apr*100:>9.2f}{pct_pos:>7.1f}"
              f"{max(rates)*100:>8.3f}{min(rates)*100:>8.3f}")
    return results

# ---------------------------------------------------------------------------
# TEST 2: Funding harvest (directional, unhedged)
#   When rate>0 (longs pay) -> go SHORT to collect; hold N settlements.
#   PnL = funding_collected + price_pnl(short) - fees
#   Symmetric: when rate<0 -> go LONG.
#   "Collect funding only if |rate| above threshold."
# ---------------------------------------------------------------------------
def simulate_harvest(funding, ohlcv, hold_settlements, rate_thresh, fee_per_side):
    """Returns list of per-trade net returns (fraction of notional).
    Enters at the funding timestamp's hour-open price (use close of that hour candle
    as a proxy for executable price), receives funding at each settlement during hold,
    exits after hold_settlements later. Direction = collect-funding side.
    """
    trades = []
    for sym, rows in funding.items():
        if len(rows) < hold_settlements + 5:
            continue
        cb = ohlcv_close_map(ohlcv.get(sym, []))
        if not cb:
            continue
        for i in range(len(rows) - hold_settlements):
            ts0, r0 = rows[i]
            if abs(r0) < rate_thresh:
                continue
            entry_px = cb.get(ts0)
            exit_ts = rows[i + hold_settlements][0]
            exit_px = cb.get(exit_ts)
            if entry_px is None or exit_px is None or entry_px <= 0:
                continue
            # direction: short if r0>0 (collect), long if r0<0
            side = -1 if r0 > 0 else 1
            # funding collected over the hold: settlements at i+1 .. i+hold occur during hold
            # Convention: a position open at settlement time pays/receives that settlement.
            # We collect settlements from i (entry settlement) through i+hold_settlements-1.
            funding_cf = 0.0
            for j in range(i, i + hold_settlements):
                rj = rows[j][1]
                # short receives +rj when rj>0; long receives -rj when rj<0
                # generic: position_return_from_funding = -side_sign? Use: receive = -side*?
                # short (side=-1) receives rj when rj>0 -> cf = +rj * (1 if short else ...)
                # Cleaner: funding paid by LONG = rj. Short receives rj. Long pays rj (gets -rj).
                if side == -1:      # short
                    funding_cf += rj
                else:               # long
                    funding_cf += -rj
            price_ret = side * (exit_px - entry_px) / entry_px
            fees = 2 * fee_per_side  # entry + exit
            net = funding_cf + price_ret - fees
            trades.append((sym, ts0, side, funding_cf, price_ret, fees, net))
    return trades

def summarize_trades(trades, label):
    if not trades:
        print(f"  {label}: NO TRADES")
        return None
    nets = [t[6] for t in trades]
    fcf = [t[3] for t in trades]
    pr = [t[4] for t in trades]
    n = len(nets)
    mean_net = statistics.mean(nets)
    wr = 100*sum(1 for x in nets if x > 0)/n
    mean_f = statistics.mean(fcf)
    mean_p = statistics.mean(pr)
    tot = sum(nets)
    sd = statistics.pstdev(nets) if n > 1 else 0
    print(f"  {label}: n={n:>5} netμ={mean_net*100:>7.4f}% WR={wr:>5.1f}% "
          f"fundμ={mean_f*100:>7.4f}% priceμ={mean_p*100:>7.4f}% "
          f"Σnet={tot*100:>8.2f}% sd={sd*100:.3f}")
    return dict(n=n, mean_net=mean_net, wr=wr, mean_f=mean_f, mean_p=mean_p, tot=tot, sd=sd)

def test2_harvest(funding, ohlcv):
    print("\n" + "="*78)
    print("TEST 2 — FUNDING HARVEST (directional, UNHEDGED, single-exchange)")
    print("  Collect funding by taking the receiving side; net of price risk + fees.")
    print("="*78)
    for fee_label, fee in [("TAKER 0.06%/side", TAKER), ("MAKER 0.01%/side", MAKER), ("ZERO fees", 0.0)]:
        print(f"\n--- fees = {fee_label} ---")
        for hold in [1, 3, 9]:  # 1=8h(ish), 3=~24h, 9=~3d (in settlements)
            for thr in [0.0, 0.0001, 0.0003, 0.0005]:
                trades = simulate_harvest(funding, ohlcv, hold, thr, fee)
                summarize_trades(trades, f"hold={hold:>2}settle thr={thr*100:.2f}%")
            print()

def test2_per_symbol(funding, ohlcv):
    print("\n" + "="*78)
    print("TEST 2b — HARVEST PER SYMBOL (hold=3 settlements, thr=0.03%, TAKER fees)")
    print("="*78)
    print(f"{'symbol':<12}{'n':>6}{'netμ%':>9}{'WR%':>7}{'fundμ%':>9}{'priceμ%':>9}{'Σnet%':>9}")
    for sym in funding:
        trades = simulate_harvest({sym: funding[sym]}, {sym: ohlcv.get(sym, [])}, 3, 0.0003, TAKER)
        if not trades:
            continue
        nets = [t[6] for t in trades]
        n = len(nets)
        print(f"{sym.split('/')[0]:<12}{n:>6}{statistics.mean(nets)*100:>9.4f}"
              f"{100*sum(1 for x in nets if x>0)/n:>7.1f}"
              f"{statistics.mean(t[3] for t in trades)*100:>9.4f}"
              f"{statistics.mean(t[4] for t in trades)*100:>9.4f}{sum(nets)*100:>9.2f}")

# ---------------------------------------------------------------------------
# TEST 3: Funding as SIGNAL — does extreme funding predict forward price?
#   Hypothesis: very positive funding (crowded longs) -> price falls next period.
#   Measure forward return over next 1/3 settlements, bucketed by funding extremity.
# ---------------------------------------------------------------------------
def test3_signal(funding, ohlcv):
    print("\n" + "="*78)
    print("TEST 3 — FUNDING AS SIGNAL (does extreme funding predict forward price?)")
    print("  Forward PRICE return (not incl. funding) after each settlement, by funding bucket.")
    print("="*78)
    for fwd in [1, 3]:
        print(f"\n--- forward horizon = {fwd} settlement(s) ---")
        # collect (rate, fwd_price_ret) across all symbols
        pts = []
        for sym, rows in funding.items():
            cb = ohlcv_close_map(ohlcv.get(sym, []))
            if not cb:
                continue
            for i in range(len(rows) - fwd):
                ts0, r0 = rows[i]
                p0 = cb.get(ts0)
                p1 = cb.get(rows[i+fwd][0])
                if p0 and p1 and p0 > 0:
                    pts.append((r0, (p1-p0)/p0))
        if not pts:
            print("  no data")
            continue
        rates = sorted(r for r, _ in pts)
        n = len(rates)
        # quintiles by funding rate
        qs = [rates[int(n*q)] for q in [0.2, 0.4, 0.6, 0.8]]
        buckets = {0: [], 1: [], 2: [], 3: [], 4: []}
        for r, fr in pts:
            b = 0
            for k, qv in enumerate(qs):
                if r > qv:
                    b = k+1
            buckets[b].append(fr)
        print(f"  {'bucket':<22}{'n':>6}{'fwdRetμ%':>10}{'fwdRet_med%':>12}{'%up':>7}")
        labels = ["Q1 most-neg fund", "Q2", "Q3 mid", "Q4", "Q5 most-pos fund"]
        for b in range(5):
            v = buckets[b]
            if not v:
                continue
            mu = statistics.mean(v)*100
            md = statistics.median(v)*100
            up = 100*sum(1 for x in v if x > 0)/len(v)
            print(f"  {labels[b]:<22}{len(v):>6}{mu:>10.4f}{md:>12.4f}{up:>7.1f}")
        # correlation rate vs fwd ret
        rs = [p[0] for p in pts]; frs = [p[1] for p in pts]
        mr, mf = statistics.mean(rs), statistics.mean(frs)
        cov = sum((a-mr)*(b-mf) for a,b in pts)/len(pts)
        sr = statistics.pstdev(rs); sf = statistics.pstdev(frs)
        corr = cov/(sr*sf) if sr>0 and sf>0 else 0
        print(f"  corr(funding_rate, fwd_price_ret) = {corr:+.4f}  (n={len(pts)})")

# ---------------------------------------------------------------------------
# TEST 4: Funding momentum vs reversion (does funding predict its own next value?)
# ---------------------------------------------------------------------------
def test4_funding_autocorr(funding):
    print("\n" + "="*78)
    print("TEST 4 — FUNDING MOMENTUM vs REVERSION (autocorrelation of funding rate)")
    print("="*78)
    print(f"{'symbol':<12}{'n':>6}{'AC(1)':>8}{'AC(3)':>8}{'AC(9)':>8}")
    for sym, rows in funding.items():
        rates = [r[1] for r in rows]
        if len(rates) < 20:
            continue
        def ac(lag):
            x = rates
            m = statistics.mean(x)
            num = sum((x[i]-m)*(x[i+lag]-m) for i in range(len(x)-lag))
            den = sum((v-m)**2 for v in x)
            return num/den if den else 0
        print(f"{sym.split('/')[0]:<12}{len(rates):>6}{ac(1):>8.3f}{ac(3):>8.3f}{ac(9):>8.3f}")

# ---------------------------------------------------------------------------
def main():
    funding, ohlcv = load()
    span_days = None
    for sym, rows in funding.items():
        if rows:
            span_days = (rows[-1][0]-rows[0][0])/86400000
            break
    print(f"Loaded {len(funding)} symbols. History span ~{span_days:.0f} days "
          f"({dt(min(r[0][0] for r in funding.values() if r)).date()} .. "
          f"{dt(max(r[-1][0] for r in funding.values() if r)).date()})")
    r1 = test1_distribution(funding)
    test4_funding_autocorr(funding)
    test3_signal(funding, ohlcv)
    test2_harvest(funding, ohlcv)
    test2_per_symbol(funding, ohlcv)

if __name__ == "__main__":
    main()
