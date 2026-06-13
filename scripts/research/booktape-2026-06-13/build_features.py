#!/usr/bin/env python3
"""
Book+Tape interaction research — feature builder.
Read-only. Uses et (exchange time) as the common clock.

For each symbol, sample the book on a fixed et grid (SAMPLE_DT seconds).
At each sample compute:
  - book imbalance (top-1 and top-5)
  - mid price, spread
  - tape features over trailing TAPE_WIN seconds: signed vol, buy/sell vol,
    trade count, aggressor ratio, large-trade signed vol
  - OFI (order flow imbalance, Cont et al.) accumulated over trailing window
  - forward mid return at 30/60/300s (no look-ahead)

Writes a parquet/csv of the per-sample feature matrix per symbol.
"""
import json, sys, os
import numpy as np
import bisect

SYMBOLS = ["BTC", "ETH", "INJ", "ARB"]
DATADIR = "logs/l2_ticks"
OUTDIR = "scripts/research/booktape-2026-06-13/out"
DATE = "2026-06-13"

SAMPLE_DT = 5.0          # seconds between samples (et)
TAPE_WIN = 30.0          # trailing window for tape features (s)
FWD = [30.0, 60.0, 300.0]  # forward return horizons (s)

os.makedirs(OUTDIR, exist_ok=True)


def load_book(sym):
    """Return arrays: et(s), mid, bid_px, bid_sz(top5 sum & top1), ask..., imb1, imb5,
    plus raw top-1 bid/ask px & sz for OFI."""
    path = f"{DATADIR}/{sym}_USDT_USDT/{DATE}.jsonl"
    et = []; mid = []; spr = []
    b1p = []; b1s = []; a1p = []; a1s = []
    bs5 = []; as5 = []
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            b = r.get("b"); a = r.get("a")
            if not b or not a:
                continue
            bp = b[0][0]; bsz = b[0][1]
            ap = a[0][0]; asz = a[0][1]
            if bp <= 0 or ap <= 0 or ap <= bp:
                continue
            et.append(r["et"] / 1000.0)
            m = (bp + ap) / 2.0
            mid.append(m)
            spr.append((ap - bp) / m)
            b1p.append(bp); b1s.append(bsz); a1p.append(ap); a1s.append(asz)
            bs5.append(sum(x[1] for x in b[:5]))
            as5.append(sum(x[1] for x in a[:5]))
    return (np.array(et), np.array(mid), np.array(spr),
            np.array(b1p), np.array(b1s), np.array(a1p), np.array(a1s),
            np.array(bs5), np.array(as5))


def load_trades(sym):
    path = f"{DATADIR}/{sym}_USDT_USDT/trades-{DATE}.jsonl"
    et = []; px = []; sz = []; sgn = []
    with open(path) as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            s = 1.0 if r["side"] == "buy" else -1.0   # buy = aggressor lifts ask = +
            et.append(r["et"] / 1000.0)
            px.append(r["px"]); sz.append(r["sz"]); sgn.append(s)
    # sort by et (trades may be slightly out of order)
    et = np.array(et); px = np.array(px); sz = np.array(sz); sgn = np.array(sgn)
    order = np.argsort(et, kind="mergesort")
    return et[order], px[order], sz[order], sgn[order]


def compute_ofi(b1p, b1s, a1p, a1s):
    """Cont/Kukanov OFI per book update (event-level), then we'll accumulate over windows.
    e_n = I(Pb>=Pb_prev)*Qb - I(Pb<=Pb_prev)*Qb_prev
        - I(Pa<=Pa_prev)*Qa + I(Pa>=Pa_prev)*Qa_prev
    """
    n = len(b1p)
    ofi = np.zeros(n)
    for i in range(1, n):
        # bid side
        if b1p[i] > b1p[i-1]:
            db = b1s[i]
        elif b1p[i] < b1p[i-1]:
            db = -b1s[i-1]
        else:
            db = b1s[i] - b1s[i-1]
        # ask side
        if a1p[i] < a1p[i-1]:
            da = a1s[i]
        elif a1p[i] > a1p[i-1]:
            da = -a1s[i-1]
        else:
            da = a1s[i] - a1s[i-1]
        ofi[i] = db - da
    return ofi


def build(sym):
    (bet, mid, spr, b1p, b1s, a1p, a1s, bs5, as5) = load_book(sym)
    tet, tpx, tsz, tsgn = load_trades(sym)
    ofi_event = compute_ofi(b1p, b1s, a1p, a1s)
    # cumulative arrays for fast windowed sums on trades
    tsv = tsz * tsgn                       # signed volume per trade
    cum_sv = np.concatenate([[0], np.cumsum(tsv)])
    cum_vol = np.concatenate([[0], np.cumsum(tsz)])
    cum_buyvol = np.concatenate([[0], np.cumsum(np.where(tsgn > 0, tsz, 0.0))])
    cum_cnt = np.arange(len(tet) + 1, dtype=float)
    # large trade threshold = 90th pct of trade size for this symbol
    big_thr = np.quantile(tsz, 0.90)
    big_sv = np.where(tsz >= big_thr, tsv, 0.0)
    cum_bigsv = np.concatenate([[0], np.cumsum(big_sv)])
    # cumulative OFI over book events (indexed by book et)
    cum_ofi = np.concatenate([[0], np.cumsum(ofi_event)])

    # sample grid on et
    t0 = max(bet[0], tet[0]) + TAPE_WIN          # need trailing window available
    t1 = min(bet[-1], tet[-1]) - max(FWD)        # need forward window available
    if t1 <= t0:
        print(f"  {sym}: insufficient overlap"); return None
    grid = np.arange(t0, t1, SAMPLE_DT)

    rows = []
    for gt in grid:
        bi = bisect.bisect_right(bet, gt) - 1      # last book <= gt
        if bi < 0:
            continue
        m_now = mid[bi]
        # tape window [gt-TAPE_WIN, gt]
        lo = bisect.bisect_left(tet, gt - TAPE_WIN)
        hi = bisect.bisect_right(tet, gt)
        cnt = cum_cnt[hi] - cum_cnt[lo]
        sv = cum_sv[hi] - cum_sv[lo]
        vol = cum_vol[hi] - cum_vol[lo]
        buyvol = cum_buyvol[hi] - cum_buyvol[lo]
        bigsv = cum_bigsv[hi] - cum_bigsv[lo]
        aggr = (buyvol / vol) if vol > 0 else 0.5   # fraction buy-aggressor
        # OFI over trailing window (book events)
        blo = bisect.bisect_left(bet, gt - TAPE_WIN)
        ofi_w = cum_ofi[bi + 1] - cum_ofi[blo]
        # forward returns
        fr = {}
        ok = True
        for h in FWD:
            fi = bisect.bisect_right(bet, gt + h) - 1
            if fi < 0 or bet[fi] < gt + h - SAMPLE_DT * 3:  # ensure a book near horizon
                ok = False; break
            fr[h] = (mid[fi] - m_now) / m_now
        if not ok:
            continue
        rows.append((
            gt, m_now, spr[bi], bs5[bi], as5[bi],
            (b1s[bi] - a1s[bi]) / (b1s[bi] + a1s[bi]),          # imb1
            (bs5[bi] - as5[bi]) / (bs5[bi] + as5[bi]),          # imb5
            sv, vol, cnt, aggr, bigsv, ofi_w,
            fr[30.0], fr[60.0], fr[300.0]
        ))
    cols = ["et", "mid", "spread", "bidsz5", "asksz5", "imb1", "imb5",
            "tape_sv", "tape_vol", "tape_cnt", "tape_aggr", "tape_bigsv", "ofi_w",
            "fwd30", "fwd60", "fwd300"]
    import pandas as pd
    df = pd.DataFrame(rows, columns=cols)
    out = f"{OUTDIR}/{sym}_features.csv"
    df.to_csv(out, index=False)
    print(f"  {sym}: {len(df)} samples, big_thr={big_thr:.4f}, "
          f"imb1 mean={df.imb1.mean():.3f} std={df.imb1.std():.3f} "
          f"-> {out}")
    return df


if __name__ == "__main__":
    for s in SYMBOLS:
        print(f"Building {s} ...")
        build(s)
