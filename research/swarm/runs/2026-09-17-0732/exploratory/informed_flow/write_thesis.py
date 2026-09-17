"""Writes theses/informed_flow_eth_rally_alt_nonfollow_short.json and runs the sanity/causality
check of the exact signal_py text on era=train (output saved next to the thesis, per LESSONS)."""
import json, sys, importlib.util, tempfile
from pathlib import Path
import numpy as np, pandas as pd
from research.swarm.lib import load_data as ld, registrar as rg, screen as sc, fee_math as fm

RUN = Path("research/swarm/runs/2026-09-17-0732")
ID = "informed_flow_eth_rally_alt_nonfollow_short"

SIGNAL_PY = '''"""informed_flow_eth_rally_alt_nonfollow_short — closed-bar signal.
Short an alt at the next open when ETH's 4-closed-bar (1h) log return is >= +2 sigma
(sigma = 14-day rolling 1h std * sqrt(4)) AND the alt's own 4-bar log return is < 0.5x ETH's.
Leader frame: df.attrs["ETH"] if the runner attached one (build-stage holdout hook), else the
train-era ETH 1h frame of the same dataset via load_data (analysts never hold the committee
token, so the train screen always takes the fallback). Every leader value used at bar t is
computed from ETH bars with timestamp <= t (backward rolling + reindex on df.index)."""
import numpy as np
import pandas as pd
from research.swarm.lib import load_data as ld

K = 4          # closed 1h bars of ETH move
THR = 2.0      # sigma threshold on ETH K-bar return
CAP = 0.5      # alt captured less than this fraction of ETH's move
VOL_WIN = 24 * 14


def _leader(df):
    lead = df.attrs.get("ETH") if hasattr(df, "attrs") else None
    if lead is None:
        lead = ld.load_ohlcv("ETH", "1h", era="train", dataset="mr_edge")
    return lead


def signals(df):
    lead = _leader(df)
    L = np.log(lead["close"].astype(float))
    lk = L.diff(K)
    vol = L.diff().rolling(VOL_WIN).std() * np.sqrt(K)
    z = (lk / vol).reindex(df.index)
    lkr = lk.reindex(df.index)
    a = np.log(df["close"].astype(float)).diff(K)
    cond = (z >= THR) & (a < CAP * lkr)
    sig = pd.Series(0, index=df.index, dtype=int)
    sig[cond.fillna(False).to_numpy()] = -1
    return sig
'''

UNIVERSE = ["1000PEPE", "1000SHIB", "AAVE", "ADA", "ARB", "AVAX", "BCH", "BNB", "DOGE", "ENA", "HYPE", "LINK",
            "LIT", "LTC", "ONDO", "PUMP", "RENDER", "SOL", "SUI", "TAO", "UNI", "XLM", "XRP", "ZEC"]

thesis = {
 "id": ID,
 "lens": "informed_flow",
 "thesis_path": str(RUN / "theses" / f"{ID}.json"),
 "mechanism": (
  "Who knows first: ETH-specific flow (2026's ETH-treasury / spot-ETF bid) is priced on Binance and mirrored on Phemex within "
  "seconds; Kurihara & Matsumoto (Asia-Pacific Financial Markets 2026, 1-min Binance data) find BTC->alt transmission is unidirectional "
  "(Granger null rejected at 5% for every pair) and that large/medium caps show 'extremely high correlation coefficients at lag0, with no "
  "significant reactions observed in subsequent or previous periods' - i.e. liquid alts absorb a leader's move within the same minute. "
  "So when ETH has rallied >= 2 sigma over 4 closed 1h bars and a liquid alt has captured less than half of it, the shortfall is NOT a "
  "pending lag to be closed (that would take a minute, not hours); it is information that the marginal bid is ETH-only and that flow is "
  "rotating out of the alt. Guo, Sang, Tu & Wang (JEDC 2024) attribute cross-coin predictability to 'common shocks ... coupled with the "
  "limited attention of investors' - here the inattentive party is the alt-perp long who reads the ETH rally as a delayed alt rally. "
  "The alt continues to underperform over the next 8h as that positioning unwinds. This is the SHORT side only: the mirror (ETH dump, "
  "alt holds up, go long) was probed and is net-negative out-of-period (exploratory/informed_flow/probe2_out.json, long_1h side1 "
  "-51 bps), so it is not registered."),
 "counterparty": (
  "Levered alt-perp longs on Phemex/Binance who buy the alt into an ETH-led rally expecting beta catch-up (the 'altseason rotation' "
  "trade). Because transmission to liquid alts is complete within a minute (Kurihara & Matsumoto 2026), the catch-up they are positioned "
  "for is not coming; with 10-50x leverage and an alt that keeps lagging, their stop-outs and liquidations over the next hours are taker "
  "sells into a market whose bid is ETH-only. They are forced to pay by leverage, not by choice; the resting maker short is on the other "
  "side of those forced sells."),
 "prediction": (
  "On the mr_edge 1h train era, shorting an alt at the next open when ETH's 4-bar log return is >= +2 sigma (14-day 1h std * sqrt(4)) "
  "and the alt's 4-bar log return is < 0.5x ETH's, with TP 150 / SL 150 bps and max hold 8 bars, yields n >= 30, net_bps_mean > 0 with "
  "bootstrap CI95 excluding 0, and WR >= fee_math.p_star(150). Falsified if CI95 includes 0, WR < p*, or if TIME exits carry positive "
  "gross for the alt (which would mean the laggard catches up rather than continues down). Pre-registered robustness read: sign of "
  "net_bps_mean must hold at tp_bps 120 and 180 (+/-20%)."),
 "nearest_dead_rows": [
  {"row": 2, "why_different": "Row 2 bet CONVERGENCE (buy the alt that lagged ETH, expecting reversion to the leader). This thesis takes the opposite sign: the non-following alt keeps underperforming because, per the 2026 transmission evidence, a multi-hour shortfall in a liquid alt is rotation, not delay."},
  {"row": 3, "why_different": "Row 3 faded the ALT's own 1h volatility expansion. Here the alt has NOT moved (captured < half of ETH's move); the trigger is the leader's move and the alt's absence of one, so nothing about the alt's own vol is being faded."},
  {"row": 5, "why_different": "Row 5 was a market-neutral cross-sectional momentum basket needing ~100+ names and a long leg. This is a single-name conditional short with no ranking, no long leg, no basket, sized for two paper slots."},
  {"row": 6, "why_different": "Row 6 bought the reversal of a high-volume cascade bar in the same instrument. This trade fires precisely when the alt did NOT have a large move, and bets continuation of relative weakness, not reversal of an absolute move."},
  {"row": 8, "why_different": "Row 8 was pairs/cointegration (long one, short the other, spread reverts). There is no ETH leg and no spread-reversion premise; ETH is only the conditioning event and the alt is traded outright."},
  {"row": 13, "why_different": "Row 13 was BTC time-series momentum on BTC over 28 days. This never trades the leader; it trades the alt that failed to follow the leader, at a 4h/8h horizon."},
  {"row": 82, "why_different": "Row 82 keyed on the funding-settlement clock (a time-of-day gate, killed as calendar noise). This trigger is a cross-asset flow state with no time-of-day or funding component."}
 ],
 "source_urls": [
  "https://link.springer.com/article/10.1007/s10690-026-09589-z",
  "https://ideas.repec.org/a/eee/dyncon/v163y2024ics0165188924000551.html",
  "https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full"
 ],
 "evidence": (
  "Opened: Kurihara & Matsumoto, 'Price Transmission from Bitcoin to Altcoins: High-Frequency Evidence and Implications for Trading "
  "Strategy', Asia-Pacific Financial Markets 2026, https://link.springer.com/article/10.1007/s10690-026-09589-z - 'We used the Binance "
  "cryptocurrency exchange API to obtain 1-min closing prices and trade count data'; four regimes (Bull Feb 25-Mar 25 2024, Bear Jun 22-Jul 19 "
  "2024, Sideways Aug 24-Sep 24 2024, Crash Jan 30-Mar 1 2025); the Granger null 'using BTC returns from one minute prior does not improve "
  "the prediction accuracy of ALT returns' was 'rejected at the 5% significance level for all pairs'; large/medium caps (ETH, LTC) show "
  "'extremely high correlation coefficients at lag0, with no significant reactions observed in subsequent or previous periods'; only small "
  "caps QKC/BIFI/CITY show 'slightly higher correlation coefficients at lag-1 than at lag0'; fee assumed 0.02%. "
  "Opened: Guo, Sang, Tu & Wang, 'Cross-cryptocurrency return predictability', JEDC 163 (2024) abstract at "
  "https://ideas.repec.org/a/eee/dyncon/v163y2024ics0165188924000551.html - lagged returns of other coins predict focal coins on Binance; "
  "mechanism 'common shocks among cryptocurrencies coupled with the limited attention of investors lead to slow information diffusion "
  "across coins'; a long-short portfolio is 'sizable ... out-of-sample after accounting for transaction costs' (no number on the opened page; "
  "no number is claimed). Opened as negative evidence on minute-scale flow: Frontiers in Blockchain 2026 'Microstructure alpha', "
  "https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full - Binance spot+perp, 6 coins, Aug 2025-Feb 2026, "
  "minute bars: 'All net Sharpe ratios are deeply negative: -31.29 to -52.05 on spot, -10.68 to -18.42 on futures' at 124-204x daily "
  "turnover - which is why this thesis is an hourly-horizon, event-conditioned trade and not a minute-scale one. "
  "Exploratory only (NOT evidence, see research/swarm/runs/2026-09-17-0732/exploratory/informed_flow/probe3_out.json): the draft rule "
  "on mr_edge train gives cond_n 180, cond_net_mean 36.36, cond_ci95 [18.74, 54.44], cond_wr 0.683 vs p_star 0.538, cond_tpw 17.9, "
  "cond_ttv_weeks 2.80, all three months positive; unconditional-short baseline base_net_mean -9.25 [-11.98, -6.57] (n 10771), "
  "diff_ci95_cond_minus_base [27.13, 63.50]; on the disjoint long_1h train period (2025-06-27 -> 2026-04-23, same rule) cond_n 371, "
  "cond_net_mean 16.57 [2.83, 30.48], cond_wr 0.571, diff vs baseline [11.88, 39.54]. The mirror long side is -51 [-67, -35] on long_1h "
  "(probe2_out.json) and is deliberately not registered."),
 "spec": {
  "dataset": "mr_edge",
  "universe": UNIVERSE,
  "timeframe": "1h",
  "tp_bps": 150,
  "sl_bps": 150,
  "max_hold_bars": 8,
  "expected_trades_per_week": 18,
  "doa_line": "DEAD if the train-era screen out.json shows ci95 including 0, or wr < p_star, or n < 30, or net_bps_mean changes sign at tp_bps 120 or 180; in paper, DEAD when the first 50 fills have net mean bps <= 0 or the running CI95 upper bound < 0."
 },
 "signal_py": SIGNAL_PY,
}

errs = rg.validate(thesis)
print("registrar.validate errors:", errs)
assert not errs
(RUN / "theses").mkdir(parents=True, exist_ok=True)
(RUN / "theses" / f"{ID}.json").write_text(json.dumps(thesis, indent=1, ensure_ascii=False))

# --- sanity check of the EXACT signal_py text on era=train (saved per LESSONS) ---
tmp = Path(tempfile.mkdtemp()) / "signal.py"; tmp.write_text(SIGNAL_PY)
fn = sc.load_signal_fn(tmp)
lines = [f"sanity check of signal_py for {ID} on era=train dataset=mr_edge tf=1h (analyst seat, {pd.Timestamp.utcnow()})"]
notional = fm.position_notional()
for s in UNIVERSE:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="mr_edge")
    sig = fn(df).reindex(df.index).fillna(0).astype(int)
    vals = sorted(set(sig.unique().tolist()))
    sc.causality_check(fn, df, symbol=s)
    lines.append(f"{s}: bars={len(df)} span={df.index.min()}..{df.index.max()} values={vals} nonzero={int((sig != 0).sum())} causality=PASS lot_check={fm.lot_check(s, notional)}")
txt = "\n".join(lines); print(txt)
(RUN / "theses" / f"{ID}.sanity_train.txt").write_text(txt + "\n")
