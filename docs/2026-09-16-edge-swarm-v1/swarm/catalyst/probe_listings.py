import ccxt, datetime as dt, json
ex = ccxt.phemex({'options': {'defaultType': 'swap'}})
m = ex.load_markets()
swaps = [x for x in m.values() if x.get('swap') and x.get('quote')=='USDT' and x.get('linear')]
now = dt.datetime.now(dt.timezone.utc)
recent = [x for x in swaps if int(x['info'].get('listTime',0)) > (now - dt.timedelta(days=60)).timestamp()*1000]
print('listed in last 60d:', len(recent))
tk = ex.fetch_tickers([x['symbol'] for x in recent])
rows=[]
for x in recent:
    t = tk.get(x['symbol'],{}); info=t.get('info',{})
    rows.append((x['symbol'], dt.datetime.fromtimestamp(int(x['info']['listTime'])/1000, dt.timezone.utc).strftime('%Y-%m-%d %H:%M'), float(info.get('turnoverRv') or 0), float(info.get('fundingRateRr') or 0), float(info.get('openInterestRv') or 0), x['info'].get('status'), x['info'].get('perpProductSubType')))
rows.sort(key=lambda r: r[1])
for r in rows: print(f"{r[0]:<22} listed {r[1]}  24h turnover ${r[2]:>14,.0f}  funding8h {r[3]*100:>8.4f}%  OI {r[4]:>12,.1f}  {r[5]} {r[6]}")
# listings per week over last 365d
yr = [int(x['info']['listTime']) for x in swaps if int(x['info'].get('listTime',0)) > (now - dt.timedelta(days=365)).timestamp()*1000]
print('listings last 365d:', len(yr), '-> per week', round(len(yr)/52.14,2))
yr90 = [v for v in yr if v > (now - dt.timedelta(days=90)).timestamp()*1000]
print('listings last 90d:', len(yr90), '-> per week', round(len(yr90)/12.86,2))
hours = {}
for v in yr: h = dt.datetime.fromtimestamp(v/1000, dt.timezone.utc).hour; hours[h]=hours.get(h,0)+1
print('listing hour UTC histogram', hours)
# how many of the 365d listings still clear $3M turnover
tk_all = ex.fetch_tickers([x['symbol'] for x in swaps if int(x['info'].get('listTime',0)) > (now - dt.timedelta(days=365)).timestamp()*1000])
above = sum(1 for s,t in tk_all.items() if float(t.get('info',{}).get('turnoverRv') or 0) >= 3_000_000)
print('of', len(tk_all), '365d listings, >= $3M 24h turnover now:', above)
json.dump({'recent': rows}, open('listings_out.json','w'), indent=1, default=str)
