import csv, math
from datetime import datetime

def load(path):
    rows=[]
    with open(path) as f:
        r=csv.DictReader(f)
        for row in r:
            rows.append({
                'ts': row['timestamp'],
                'o': float(row['open']), 'h': float(row['high']),
                'l': float(row['low']), 'c': float(row['close']),
            })
    return rows

def atr(rows, period=14):
    trs=[None]*len(rows)
    for i in range(1,len(rows)):
        h,l,pc = rows[i]['h'], rows[i]['l'], rows[i-1]['c']
        tr = max(h-l, abs(h-pc), abs(l-pc))
        trs[i]=tr
    atrs=[None]*len(rows)
    for i in range(period, len(rows)):
        window = trs[i-period+1:i+1]
        if any(x is None for x in window): continue
        atrs[i]=sum(window)/period
    return atrs

def sma(vals, period, idx):
    window = vals[idx-period+1:idx+1]
    if any(x is None for x in window): return None
    return sum(window)/period

def count_signals(path, sym):
    rows = load(path)
    atrs = atr(rows, 14)
    n=len(rows)
    sig_count=0
    long_count=0
    short_count=0
    for i in range(40, n):
        if atrs[i] is None: continue
        avg_atr20 = sma(atrs, 20, i-1)  # avg of prior 20 ATRs (not including current) to avoid lookahead-ish
        if avg_atr20 is None or avg_atr20==0: continue
        expansion = atrs[i] >= 1.3*avg_atr20
        if not expansion: continue
        window = rows[i-12:i]  # prior 12 bars (not including current)
        roll_hi = max(x['h'] for x in window)
        roll_lo = min(x['l'] for x in window)
        c = rows[i]['c']
        thresh = 0.3*atrs[i]
        if c >= roll_hi + thresh:
            sig_count+=1; long_count+=1
        elif c <= roll_lo - thresh:
            sig_count+=1; short_count+=1
    t0 = datetime.strptime(rows[0]['ts'], '%Y-%m-%d %H:%M:%S')
    t1 = datetime.strptime(rows[-1]['ts'], '%Y-%m-%d %H:%M:%S')
    days = (t1-t0).total_seconds()/86400
    weeks = days/7
    print(f"{sym}: rows={n} range={rows[0]['ts']}->{rows[-1]['ts']} days={days:.1f} weeks={weeks:.2f}")
    print(f"  signals={sig_count} (long={long_count}, short={short_count})  per_week={sig_count/weeks:.2f}")

count_signals('/Users/jonaspenaso/Desktop/Phmex-S/backtest_data/BTC_USDT_USDT_5m.csv', 'BTC')
count_signals('/Users/jonaspenaso/Desktop/Phmex-S/backtest_data/ETH_USDT_USDT_5m.csv', 'ETH')

def avg_atr_pct(path, sym):
    rows = load(path)
    atrs = atr(rows, 14)
    vals=[]
    for i,row in enumerate(rows):
        if atrs[i] is not None:
            vals.append(atrs[i]/row['c']*100)
    print(f"{sym}: mean ATR(14,5m) as %% of price = {sum(vals)/len(vals):.4f}%  median approx via sorted mid")
    sv = sorted(vals)
    print(f"  median = {sv[len(sv)//2]:.4f}%")

avg_atr_pct('/Users/jonaspenaso/Desktop/Phmex-S/backtest_data/BTC_USDT_USDT_5m.csv', 'BTC')
avg_atr_pct('/Users/jonaspenaso/Desktop/Phmex-S/backtest_data/ETH_USDT_USDT_5m.csv', 'ETH')
