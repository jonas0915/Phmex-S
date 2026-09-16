import ccxt, json, time, datetime as dt
ex = ccxt.phemex({'options': {'defaultType': 'swap'}})
print('ccxt', ccxt.__version__)
print('has fetch_open_interest', ex.has.get('fetchOpenInterest'), 'history', ex.has.get('fetchOpenInterestHistory'), 'liquidations', ex.has.get('fetchLiquidations'), 'fundingHist', ex.has.get('fetchFundingRateHistory'))
m = ex.load_markets()
swaps = [x for x in m.values() if x.get('swap') and x.get('quote')=='USDT' and x.get('linear')]
inv = [x for x in m.values() if x.get('swap') and x.get('inverse')]
print('usdt linear swaps', len(swaps), 'inverse swaps', len(inv))
btc = m['BTC/USDT:USDT']
print('BTC info keys', sorted(btc['info'].keys()))
# listing times
lt = []
for x in swaps:
    info = x['info']
    for k in ('listTime','listingTime','launchTime','onboardTime'):
        if k in info:
            lt.append((x['symbol'], k, info[k]))
print('listing-time fields found', len(lt), lt[:5])
# sort by listTime if present
if lt:
    lt2 = sorted(lt, key=lambda t: int(t[2]))
    for s,k,v in lt2[-15:]:
        print('recent', s, dt.datetime.utcfromtimestamp(int(v)/1000 if int(v)>1e12 else int(v)).isoformat())
try:
    oi = ex.fetch_open_interest('BTC/USDT:USDT'); print('OI', {k: oi.get(k) for k in ('symbol','openInterestAmount','openInterestValue','timestamp')})
except Exception as e: print('OI err', type(e).__name__, str(e)[:200])
try:
    fr = ex.fetch_funding_rate('BTC/USDT:USDT'); print('funding', {k: fr.get(k) for k in ('fundingRate','fundingTimestamp','fundingDatetime','nextFundingTimestamp','predictedFundingRate','interval')})
except Exception as e: print('fr err', type(e).__name__, str(e)[:200])
try:
    h = ex.fetch_funding_rate_history('BTC/USDT:USDT', limit=5); print('fr hist n', len(h), [(dt.datetime.utcfromtimestamp(r['timestamp']/1000).isoformat(), r['fundingRate']) for r in h])
except Exception as e: print('frh err', type(e).__name__, str(e)[:200])
try:
    t = ex.fetch_ticker('BTC/USDT:USDT'); print('ticker info keys', sorted(t['info'].keys()))
except Exception as e: print('ticker err', e)
