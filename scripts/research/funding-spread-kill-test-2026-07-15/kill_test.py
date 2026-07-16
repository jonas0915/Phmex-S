"""
KILL TEST — realized linear-vs-inverse perp funding spread ON PHEMEX.
Adjudicates the same-venue delta-neutral carry (short linear + long inverse).

Root cause of the prior 10500 error (found 2026-07-15): ccxt routes inverse
contracts to the /v1/api-data/... path, which returns
{"msg":"please try again later! null","code":10500} for every request.
The SAME endpoint WITHOUT the /v1 prefix (v2) serves inverse funding
symbols fine. Also, ccxt builds '.ETHFR8H' for cETHUSD (baseId), but the
products spec says the real symbol is '.cETHFR8H'.

This script bypasses ccxt and hits the v2 endpoint directly:
  GET https://api.phemex.com/api-data/public/data/funding-rate-history
      ?symbol=<fundingRate8hSymbol>&limit=N&end=<ms>
paginating backwards until >= TARGET_DAYS of history or the series ends.

Read-only, public data only. Run:
  python3 scripts/research/funding-spread-kill-test-2026-07-15/kill_test.py
"""
import json, time, urllib.request, urllib.parse, statistics, sys

BASE = "https://api.phemex.com/api-data/public/data/funding-rate-history"
TARGET_DAYS = 400          # aim for >6 months; take what exists
PAGE_LIMIT = 100           # rows per request (probe max separately)
PERIODS_PER_DAY = 3        # 8h funding
OUTDIR = "scripts/research/funding-spread-kill-test-2026-07-15"

# fundingRate8hSymbol values verified from GET /public/products on 2026-07-15:
#   BTCUSD  (inverse, settle BTC): .BTCFR8H
#   cETHUSD (inverse, settle ETH): .cETHFR8H
#   linear USDT perps use .<id>FR8H per ccxt (works, verified in probe)
SERIES = {
    "BTC_linear":  ".BTCUSDTFR8H",
    "BTC_inverse": ".BTCFR8H",
    "ETH_linear":  ".ETHUSDTFR8H",
    "ETH_inverse": ".cETHFR8H",
}

def get(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "research/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def fetch_series(fsym):
    """Paginate backwards using end=<ms>. Returns {fundingTime_ms: rate_float}."""
    out = {}
    end = None
    for page in range(200):
        params = {"symbol": fsym, "limit": PAGE_LIMIT}
        if end is not None:
            params["end"] = end
        try:
            resp = get(params)
        except Exception as e:
            print(f"  {fsym} page {page}: HTTP ERR {type(e).__name__}: {e}", flush=True)
            time.sleep(2)
            resp = get(params)
        if resp.get("code") != 0:
            print(f"  {fsym} page {page}: API code={resp.get('code')} msg={resp.get('msg')}")
            break
        rows = (resp.get("data") or {}).get("rows") or []
        if not rows:
            break
        new = 0
        for r in rows:
            ts = int(r["fundingTime"])
            if ts not in out:
                out[ts] = float(r["fundingRate"])
                new += 1
        oldest = min(int(r["fundingTime"]) for r in rows)
        if new == 0:
            break
        end = oldest - 1
        span_d = (max(out) - min(out)) / 86400000.0
        if span_d >= TARGET_DAYS:
            break
        time.sleep(0.25)
    return out

print("=" * 78)
print("STEP 1 — fetch funding histories (v2 endpoint, backward pagination)")
print("=" * 78)
data = {}
for name, fsym in SERIES.items():
    s = fetch_series(fsym)
    data[name] = s
    if s:
        lo, hi = min(s), max(s)
        print(f"{name:>12} ({fsym:>14}): n={len(s)}  span={(hi-lo)/86400000.0:.1f}d  "
              f"first={time.strftime('%Y-%m-%d', time.gmtime(lo/1000))}  "
              f"last={time.strftime('%Y-%m-%d', time.gmtime(hi/1000))}")
    else:
        print(f"{name:>12} ({fsym:>14}): EMPTY / FAILED")

if any(not v for v in data.values()):
    print("\nAt least one series unobtainable — cannot compute spread. ABORT.")
    sys.exit(1)

json.dump({k: {str(t): r for t, r in sorted(v.items())} for k, v in data.items()},
          open(f"{OUTDIR}/raw_funding.json", "w"), indent=0)
print(f"\nraw series saved to {OUTDIR}/raw_funding.json")

print("\n" + "=" * 78)
print("STEP 2 — aligned spread analysis (spread = inverse - linear, per 8h)")
print("=" * 78)

def annualize(rate_8h):
    return rate_8h * PERIODS_PER_DAY * 365 * 100.0  # percent/yr

results = {}
for coin in ("BTC", "ETH"):
    lin, inv = data[f"{coin}_linear"], data[f"{coin}_inverse"]
    common = sorted(set(lin) & set(inv))
    spreads = [(t, inv[t] - lin[t]) for t in common]
    sp = [s for _, s in spreads]
    n = len(sp)
    span_d = (common[-1] - common[0]) / 86400000.0 if n > 1 else 0
    mean8h = statistics.mean(sp)
    med8h = statistics.median(sp)
    std8h = statistics.pstdev(sp)
    pct_neg = 100.0 * sum(1 for s in sp if s < 0) / n
    pct_pos = 100.0 * sum(1 for s in sp if s > 0) / n

    # rolling 90d windows (90d * 3 = 270 periods), stepped by 1 day (3 periods):
    win = 90 * PERIODS_PER_DAY
    step = PERIODS_PER_DAY
    means = []
    for i in range(0, n - win + 1, step):
        means.append(statistics.mean(sp[i:i + win]))
    one_signed_neg = sum(1 for m in means if m < 0)
    one_signed_pos = sum(1 for m in means if m > 0)

    results[coin] = dict(
        n=n, span_days=span_d,
        mean_spread_8h=mean8h, median_spread_8h=med8h, std_spread_8h=std8h,
        mean_spread_bps_8h=mean8h * 1e4, std_spread_bps_8h=std8h * 1e4,
        annualized_mean_pct=annualize(mean8h),
        annualized_median_pct=annualize(med8h),
        pct_periods_negative=pct_neg, pct_periods_positive=pct_pos,
        n_90d_windows=len(means),
        pct_90d_windows_negative=(100.0 * one_signed_neg / len(means)) if means else None,
        pct_90d_windows_positive=(100.0 * one_signed_pos / len(means)) if means else None,
        mean_linear_ann_pct=annualize(statistics.mean([lin[t] for t in common])),
        mean_inverse_ann_pct=annualize(statistics.mean([inv[t] for t in common])),
    )
    r = results[coin]
    print(f"\n{coin}: aligned n={n} periods, span {span_d:.1f} days")
    print(f"  mean linear funding  : {r['mean_linear_ann_pct']:+.3f}%/yr annualized")
    print(f"  mean inverse funding : {r['mean_inverse_ann_pct']:+.3f}%/yr annualized")
    print(f"  spread (inv-lin) per 8h: mean {r['mean_spread_bps_8h']:+.4f} bps, "
          f"median {med8h*1e4:+.4f} bps, std {r['std_spread_bps_8h']:.4f} bps")
    print(f"  spread ANNUALIZED: mean {r['annualized_mean_pct']:+.3f}%/yr, "
          f"median {r['annualized_median_pct']:+.3f}%/yr")
    print(f"  % periods spread<0 (favors short-lin/long-inv): {pct_neg:.1f}%   "
          f"spread>0: {pct_pos:.1f}%")
    if means:
        print(f"  rolling 90d windows (n={len(means)}): "
              f"{r['pct_90d_windows_negative']:.1f}% negative-mean, "
              f"{r['pct_90d_windows_positive']:.1f}% positive-mean")

print("\n" + "=" * 78)
print("STEP 3 — economics at measured spread (costs from 7/14 screen)")
print("=" * 78)
# All-in entry+exit cost, from basis-carry-screen-2026-07-14 receipts:
#   spot BTC collateral leg: 0.1% per side (buy BTC to margin the inverse leg,
#   sell it back at the end) = 0.2% RT on the collateral notional
#   4 perp maker legs (open+close x 2 contracts) at 0.01% = 0.04% RT
SPOT_RT = 0.001 * 2
PERP_MAKER_RT = 0.0001 * 4
ALLIN_RT = SPOT_RT + PERP_MAKER_RT
print(f"all-in RT cost = 2x spot 0.1% + 4x perp maker 0.01% = {ALLIN_RT*100:.2f}% of notional")

for coin in ("BTC", "ETH"):
    r = results[coin]
    edge_yr = abs(r["annualized_mean_pct"]) / 100.0     # fraction/yr, harvestable magnitude
    print(f"\n{coin}: |mean spread| = {abs(r['annualized_mean_pct']):.3f}%/yr")
    if edge_yr <= 0:
        print("  zero edge — never breaks even")
        continue
    be_months = ALLIN_RT / edge_yr * 12
    print(f"  break-even holding time vs {ALLIN_RT*100:.2f}% RT cost: {be_months:.1f} months")
    for cap in (250, 500, 2000):
        gross_mo = cap * edge_yr / 12
        print(f"  ${cap:>4} deployed: gross ${gross_mo:.2f}/mo  "
              f"(one-time RT cost ${cap*ALLIN_RT:.2f})")

json.dump(results, open(f"{OUTDIR}/results.json", "w"), indent=2)
print(f"\nresults saved to {OUTDIR}/results.json")
