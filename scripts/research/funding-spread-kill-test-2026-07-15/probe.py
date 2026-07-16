"""
Probe 1 — can we get INVERSE perp funding history on Phemex at all?
Tries ccxt fetch_funding_rate_history with several param variants on
BTC/USD:BTC and ETH/USD:ETH, and prints the endpoint ccxt uses.
Read-only, public data.
"""
import ccxt, json, time, traceback

ex = ccxt.phemex({"enableRateLimit": True, "timeout": 20000,
                  "options": {"defaultType": "swap"}})
mk = ex.load_markets()

# Show which markets are inverse
inv = [m for m in mk.values() if m.get("swap") and m.get("inverse")]
print(f"inverse swaps listed: {len(inv)}")
for m in inv:
    print(f"  {m['symbol']:>16}  id={m['id']}  active={m.get('active')}  settle={m.get('settle')}")

# What endpoint does ccxt map fetch_funding_rate_history to?
print("\nccxt has['fetchFundingRateHistory'] =", ex.has.get("fetchFundingRateHistory"))
# find candidate api paths mentioning funding
paths = []
def walk(d, prefix=""):
    if isinstance(d, dict):
        for k, v in d.items():
            walk(v, prefix + "/" + str(k))
    elif isinstance(d, (int, float)):
        if "funding" in prefix.lower():
            paths.append(prefix)
walk(ex.api)
print("api paths containing 'funding':")
for p in paths:
    print(" ", p)

SYMS = ["BTC/USD:BTC", "ETH/USD:ETH", "BTC/USDT:USDT"]  # last = linear control
variants = [
    ("plain limit=5", dict(limit=5)),
    ("limit=100", dict(limit=100)),
    ("since 30d ago, limit=100", dict(since=ex.milliseconds() - 30*86400000, limit=100)),
    ("no args", dict()),
]

for s in SYMS:
    if s not in mk:
        print(f"\n{s}: NOT IN MARKETS")
        continue
    print(f"\n===== {s} (id={mk[s]['id']}, inverse={mk[s].get('inverse')}) =====")
    for label, kw in variants:
        try:
            rows = ex.fetch_funding_rate_history(s, **kw)
            if rows:
                t0 = rows[0]["timestamp"]; t1 = rows[-1]["timestamp"]
                print(f"  [{label}] OK n={len(rows)} first_ts={t0} last_ts={t1} "
                      f"first_rate={rows[0]['fundingRate']} last_rate={rows[-1]['fundingRate']}")
            else:
                print(f"  [{label}] OK but EMPTY")
        except Exception as e:
            print(f"  [{label}] {type(e).__name__}: {str(e)[:160]}")
        time.sleep(0.3)
