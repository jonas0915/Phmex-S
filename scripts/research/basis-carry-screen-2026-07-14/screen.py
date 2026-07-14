"""
Feasibility SCREEN — market-neutral spot-perp basis/carry on Phemex.
Read-only. Uses ccxt phemex public endpoints (markets + funding). No orders.
Cites every number to its API call. Run:
  python3 scripts/research/basis-carry-screen-2026-07-14/screen.py
"""
import ccxt, time, statistics, json, sys

ex = ccxt.phemex({"enableRateLimit": True, "timeout": 20000,
                  "options": {"defaultType": "swap"}})

print("=" * 78)
print("Q1 — SPOT MARKET ACCESSIBILITY via ccxt phemex")
print("=" * 78)
mk = ex.load_markets()
types = {}
for m in mk.values():
    t = m.get("type") or ("spot" if m.get("spot") else "other")
    types[t] = types.get(t, 0) + 1
print("market-type counts:", types)
spot = [m for m in mk.values() if m.get("spot")]
swap = [m for m in mk.values() if m.get("swap")]
print(f"spot markets: {len(spot)}  |  swap markets: {len(swap)}")

# sample spot USDT markets + their fees
spot_usdt = [m for m in spot if m.get("quote") == "USDT" and m.get("active")]
print(f"active spot USDT markets: {len(spot_usdt)}")
print("sample spot USDT (symbol, maker, taker):")
for m in spot_usdt[:8]:
    print(f"  {m['symbol']:>14}  maker={m.get('maker')}  taker={m.get('taker')}")
# swap fees for reference
sample_swap = [m for m in swap if m.get("quote") == "USDT" and m.get("active")][:3]
print("sample swap USDT fees (symbol, maker, taker):")
for m in sample_swap:
    print(f"  {m['symbol']:>18}  maker={m.get('maker')}  taker={m.get('taker')}")

# Build list of top liquid USDT perps to query funding
WANT = ["BTC","ETH","SOL","BNB","XRP","DOGE","ADA","AVAX","LINK","LTC",
        "ARB","OP","SUI","APT","TIA","SEI","NEAR","INJ"]
def perp_symbol(base):
    # phemex unified swap symbol
    cands = [f"{base}/USDT:USDT", f"{base}USDT"]
    for c in cands:
        if c in mk and mk[c].get("swap"):
            return c
    for m in swap:
        if m.get("base") == base and m.get("quote") == "USDT":
            return m["symbol"]
    return None
perps = [(b, perp_symbol(b)) for b in WANT]
perps = [(b, s) for b, s in perps if s]
print(f"\nresolved {len(perps)} perp symbols for funding query")

print("\n" + "=" * 78)
print("Q2 — CURRENT funding rates (fetch_funding_rate per symbol)")
print("=" * 78)
print(f"{'sym':>7} {'fund%/8h':>10} {'bps/8h':>8} {'APR%':>8}  {'interval_h':>10}")
cur = []
for b, s in perps:
    try:
        fr = ex.fetch_funding_rate(s)
        r = fr.get("fundingRate")
        if r is None:
            print(f"{b:>7}  (no fundingRate)")
            continue
        # interval: phemex funding is 8h standard; check timestamps if present
        ih = 8.0
        info = fr.get("info", {})
        pct = r * 100.0
        bps = r * 1e4
        apr = r * (24/ih) * 365 * 100.0
        cur.append((b, r, ih))
        print(f"{b:>7} {pct:>10.4f} {bps:>8.2f} {apr:>8.2f}  {ih:>10.1f}")
        time.sleep(0.15)
    except Exception as e:
        print(f"{b:>7}  ERR {type(e).__name__}: {str(e)[:60]}")
pos = sum(1 for _,r,_ in cur if r > 0)
neg = sum(1 for _,r,_ in cur if r < 0)
zero = sum(1 for _,r,_ in cur if r == 0)
if cur:
    mags = [abs(r)*1e4 for _,r,_ in cur]
    print(f"\nCURRENT: n={len(cur)}  positive={pos}  negative={neg}  zero={zero}")
    print(f"  |funding| bps/8h: median={statistics.median(mags):.2f}  mean={statistics.mean(mags):.2f}  max={max(mags):.2f}")

print("\n" + "=" * 78)
print("Q3 — funding-rate HISTORY (fetch_funding_rate_history)")
print("=" * 78)
majors = ["BTC","ETH","SOL","XRP","DOGE","ARB","OP","SUI"]
print(f"{'sym':>7} {'n':>5} {'span_d':>7} {'mean_bps':>9} {'std_bps':>8} {'%pos':>6} {'medAPR%':>8}")
hist_summary = {}
for b in majors:
    s = perp_symbol(b)
    if not s:
        continue
    try:
        rows = ex.fetch_funding_rate_history(s, limit=1000)
        rates = [x["fundingRate"] for x in rows if x.get("fundingRate") is not None]
        ts = [x["timestamp"] for x in rows if x.get("timestamp")]
        if not rates:
            print(f"{b:>7}  (empty)")
            continue
        span_d = (max(ts) - min(ts)) / 86400000.0 if len(ts) > 1 else 0
        mean_bps = statistics.mean(rates) * 1e4
        std_bps = statistics.pstdev(rates) * 1e4 if len(rates) > 1 else 0
        pctpos = 100.0 * sum(1 for r in rates if r > 0) / len(rates)
        med = statistics.median(rates)
        med_apr = med * (24/8) * 365 * 100.0
        hist_summary[b] = dict(n=len(rates), span_d=span_d, mean_bps=mean_bps,
                               std_bps=std_bps, pctpos=pctpos, med_apr=med_apr,
                               median_rate=med)
        print(f"{b:>7} {len(rates):>5} {span_d:>7.1f} {mean_bps:>9.3f} {std_bps:>8.3f} {pctpos:>6.1f} {med_apr:>8.2f}")
        time.sleep(0.2)
    except Exception as e:
        print(f"{b:>7}  ERR {type(e).__name__}: {str(e)[:70]}")

# note the endpoint limit
print(f"\n(endpoint limit param used: limit=1000; actual rows returned above under n)")

print("\n" + "=" * 78)
print("Q4/Q5 — COST MODEL + SIZE REALITY")
print("=" * 78)
BAL = 46.36  # trading_state.json peak_balance
# per-leg notional if split: ~half spot, half perp notional
NOTIONAL = BAL / 2.0
# fee rates observed above (filled after run). Placeholders computed from market fees:
spot_taker = spot_usdt[0].get("taker") if spot_usdt else None
spot_maker = spot_usdt[0].get("maker") if spot_usdt else None
# ccxt does not populate phemex swap maker/taker in the market dict (returns None).
# Use bot's config-verified rates: TAKER_FEE_PERCENT=0.06 (.env), MAKER 0.01 (config.py:101)
perp_taker = sample_swap[0].get("taker") if (sample_swap and sample_swap[0].get("taker")) else 0.0006
perp_maker = sample_swap[0].get("maker") if (sample_swap and sample_swap[0].get("maker")) else 0.0001
print(f"per-leg notional at ${BAL} split 50/50: ${NOTIONAL:.2f}")
print(f"observed fees: spot maker={spot_maker} taker={spot_taker} | perp maker={perp_maker} taker={perp_taker}")

def cost_model(fund_rate_8h, spot_fee, perp_fee, label):
    # round trip = open+close both legs = 2*spot_fee + 2*perp_fee (as fraction of notional)
    rt_fee_frac = 2 * spot_fee + 2 * perp_fee
    # funding collected per 8h as fraction of notional (short perp collects when positive)
    if fund_rate_8h <= 0:
        print(f"  [{label}] funding<=0, skip")
        return
    breakeven_periods = rt_fee_frac / fund_rate_8h
    breakeven_days = breakeven_periods * 8 / 24.0
    # $/month optimistic: hold continuously, funding on notional, 3 periods/day * 30
    monthly_funding = fund_rate_8h * NOTIONAL * 3 * 30
    monthly_funding_net_one_rt = monthly_funding - rt_fee_frac * NOTIONAL
    print(f"  [{label}] fund={fund_rate_8h*1e4:.2f}bps/8h  RT_fee={rt_fee_frac*1e4:.1f}bps  "
          f"breakeven={breakeven_periods:.1f} periods ({breakeven_days:.1f} days)  "
          f"gross ${monthly_funding:.3f}/mo  net(1 RT) ${monthly_funding_net_one_rt:.3f}/mo")

if spot_maker is not None and hist_summary:
    # use ETH & a high-funding coin (OP/ARB) median
    for b in ["ETH","BTC","OP","ARB","SUI"]:
        if b in hist_summary:
            fr = hist_summary[b]["median_rate"]
            print(f"\n{b} median funding = {fr*1e4:.2f} bps/8h:")
            cost_model(fr, spot_maker, perp_maker, "all-maker")
            cost_model(fr, spot_taker, perp_taker, "all-taker")

# dump json for record
out = dict(types=types, n_spot=len(spot), n_swap=len(swap),
           n_spot_usdt=len(spot_usdt),
           spot_maker=spot_maker, spot_taker=spot_taker,
           perp_maker=perp_maker, perp_taker=perp_taker,
           current=[(b, r, ih) for b,r,ih in cur],
           current_pos=pos, current_neg=neg,
           hist=hist_summary, balance=BAL)
json.dump(out, open("scripts/research/basis-carry-screen-2026-07-14/out.json","w"),
          indent=2, default=str)
print("\nsaved out.json")
