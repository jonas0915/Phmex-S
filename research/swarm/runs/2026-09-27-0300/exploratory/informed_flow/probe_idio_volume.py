"""EXPLORATORY ONLY (informed_flow lens, run 2026-09-27-0300) -- not the screen, numbers are not evidence.
long_1h train era only (load_data enforces). Question: do idiosyncratic (alt minus BTC) 24h moves
behave differently by relative volume (Llorente et al. informed-vs-uninformed; Bianchi et al. low-volume reversal)?
Forward return measured in the direction of the prior idio move (positive = continuation)."""
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld

syms = [s for s in ld.list_symbols("long_1h") if s not in ("BTC", "GIGGLE")]
btc = ld.load_ohlcv("BTC", "1h", era="train", dataset="long_1h")
print("BTC train range", btc.index.min(), btc.index.max())
rb = np.log(btc.close).diff(24)
rows = []
for s in syms:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    lc = np.log(df.close)
    r24 = lc.diff(24)
    idio = r24 - rb.reindex(df.index)
    v24 = df.volume.rolling(24).sum()
    rv = v24 / v24.rolling(24 * 30).mean()
    for h in (12, 24, 48):
        df[f"f{h}"] = lc.shift(-h) - lc  # forward (probe only, outcome not signal)
    d = pd.DataFrame({"idio": idio, "rv": rv, "f12": df.f12, "f24": df.f24, "f48": df.f48})
    d = d.iloc[::24].dropna()  # one obs per day-ish, non-overlapping entry grid
    d["sym"] = s
    rows.append(d)
D = pd.concat(rows)
print("n obs", len(D), "symbols", len(syms))
for thr in (0.03, 0.05, 0.08):
    big = D[D.idio.abs() > thr]
    for lab, m in (("rv<0.8", big.rv < 0.8), ("0.8-1.5", (big.rv >= 0.8) & (big.rv < 1.5)), ("rv>=1.5", big.rv >= 1.5)):
        x = big[m]
        if len(x) < 5:
            print(thr, lab, "n", len(x)); continue
        sgn = np.sign(x.idio)
        out = [f"{h}h cont_bps={1e4*(sgn*x[f'f{h}']).mean():.1f}" for h in (12, 24, 48)]
        print(f"|idio|>{thr} {lab:8s} n={len(x):4d}", " ".join(out))
