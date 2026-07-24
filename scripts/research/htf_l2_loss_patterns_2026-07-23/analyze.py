#!/usr/bin/env python3
"""htf_l2 live-era loss-pattern analysis (2026-07-23). READ-ONLY on bot state.
Sources: trading_state_HTF_L2.json (slot, mode=live), trading_state.json (main,
htf_l2 since 7/21 9:25 PM PT un-halt), embedded entry_snapshots (F7 fields)."""
import json, datetime, collections
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
ROOT = "/Users/jonaspenaso/Desktop/Phmex-S"

def pt(ts):
    return datetime.datetime.fromtimestamp(ts, PT)

def pts(ts):
    return pt(ts).strftime("%m/%d %I:%M %p")

# ---- slot live trades ----
slot = json.load(open(f"{ROOT}/trading_state_HTF_L2.json"))["closed_trades"]
slot_live = [t for t in slot if t.get("mode") == "live"]

# ---- main htf_l2 since un-halt, merge partial legs by opened_at ----
cut = datetime.datetime(2026, 7, 21, 21, 25, tzinfo=PT).timestamp()
main = [t for t in json.load(open(f"{ROOT}/trading_state.json"))["closed_trades"]
        if t.get("closed_at", 0) >= cut and "htf_l2" in str(t.get("strategy", ""))]
merged = {}
for t in main:
    k = (t["symbol"], round(t["opened_at"]))
    m = merged.setdefault(k, {**t, "net_pnl": 0.0, "legs": []})
    m["net_pnl"] += t["net_pnl"]
    m["legs"].append((t["exit_reason"], t["exit_price"], t["net_pnl"], t["closed_at"]))
    m["closed_at"] = max(m["closed_at"], t["closed_at"])
main_entries = sorted(merged.values(), key=lambda x: x["opened_at"])

entries = [dict(t, book="slot") for t in slot_live] + [dict(t, book="main") for t in main_entries]
entries.sort(key=lambda x: x["opened_at"])

print("=== ALL LIVE htf_l2 ENTRIES since 7/20 8 PM PT (slot live era + main since un-halt) ===")
for t in entries:
    s = t.get("entry_snapshot") or {}
    r = s.get("regime") or {}
    f = s.get("flow") or {}
    atr = r.get("atr_pct")
    vw = s.get("vwap_dist_pct")
    d = 1 if t["side"] == "long" else -1
    stretch = (d * vw / (atr * 100)) if (vw is not None and atr) else None
    t["_stretch"] = stretch
    t["_adx"] = r.get("adx"); t["_htf_adx"] = s.get("htf_adx")
    t["_tc"] = f.get("trade_count"); t["_br"] = f.get("buy_ratio")
    t["_conf"] = s.get("confidence"); t["_rsi"] = s.get("rsi")
    print(f"{t['book']:4s} {t['symbol'].split('/')[0]:9s} {t['side']:5s} "
          f"open={pts(t['opened_at'])} close={pts(t['closed_at'])} net={t['net_pnl']:+.4f} "
          f"reason={t.get('exit_reason','multi' if t.get('legs') else '?')} "
          f"conf={t['_conf']} adx5m={t['_adx']} htf_adx={t['_htf_adx']} tc={t['_tc']} "
          f"br={t['_br']} rsi={t['_rsi']} vwap%={vw} atr%={atr} "
          f"stretchATR={stretch if stretch is None else round(stretch,2)} "
          f"tags={t.get('gate_tags')} peak={t.get('peak_price')}")

losers = [t for t in entries if t["net_pnl"] < 0]
winners = [t for t in entries if t["net_pnl"] >= 0]
print(f"\nentries={len(entries)} (slot {len(slot_live)}, main {len(main_entries)}); "
      f"losers={len(losers)} sum={sum(t['net_pnl'] for t in losers):+.2f}; "
      f"winners={len(winners)} sum={sum(t['net_pnl'] for t in winners):+.2f}")
print(f"slot live net: {sum(t['net_pnl'] for t in slot_live):+.4f}; "
      f"main net: {sum(t['net_pnl'] for t in main_entries):+.4f}")

# ---- Q1 patterns ----
print("\n=== Q1 PATTERNS ===")
for grp, name in ((losers, "LOSERS"), (winners, "WINNERS")):
    dirs = collections.Counter(t["side"] for t in grp)
    syms = collections.Counter(t["symbol"].split("/")[0] for t in grp)
    hrs = collections.Counter(pt(t["opened_at"]).strftime("%I %p") for t in grp)
    print(f"{name} n={len(grp)}: dirs={dict(dirs)} syms={dict(syms)} entry_hours={dict(hrs)}")
    for k in ("_adx", "_htf_adx", "_tc", "_br", "_conf", "_rsi", "_stretch"):
        vals = [t[k] for t in grp if t[k] is not None]
        if vals:
            print(f"  {k}: {[round(v,2) for v in vals]} median={sorted(vals)[len(vals)//2]:.2f}")

# cells (thin=tc<=20, adx_hi=htf_adx>=35)
print("\ncells (thin_tape = tc<=20, adx_hi = htf_adx>=35):")
for t in entries:
    thin = t["_tc"] is not None and t["_tc"] <= 20
    hi = t["_htf_adx"] is not None and t["_htf_adx"] >= 35
    cell = ("thin&adx_hi" if thin and hi else "thin_only" if thin
            else "adx_hi_only" if hi else "neither")
    print(f"  {t['book']:4s} {t['symbol'].split('/')[0]:9s} net={t['net_pnl']:+.2f} cell={cell} tags={t.get('gate_tags')}")

# re-entry chains: same symbol entered <30 min after a loss close (either book)
print("\nre-entry <30min after a loss (same symbol, any book):")
found = False
for t in entries:
    for u in entries:
        if (u is not t and u["symbol"] == t["symbol"] and u["net_pnl"] < 0
                and 0 <= t["opened_at"] - u["closed_at"] <= 1800):
            print(f"  {t['symbol']} {t['book']} re-entry {pts(t['opened_at'])} "
                  f"= {round((t['opened_at']-u['closed_at'])/60,1)} min after {u['book']} loss "
                  f"({u['net_pnl']:+.2f} closed {pts(u['closed_at'])}); re-entry net={t['net_pnl']:+.2f}")
            found = True
if not found:
    print("  none")

# ---- Q2 VWAP-stretch >4 ATR tally ----
print("\n=== Q2 VWAP-STRETCH (side-oriented, ATR units) running tally ===")
above = [t for t in entries if t["_stretch"] is not None and t["_stretch"] > 4]
below = [t for t in entries if t["_stretch"] is not None and t["_stretch"] <= 4]
miss = [t for t in entries if t["_stretch"] is None]
for grp, name in ((above, ">4 ATR"), (below, "<=4 ATR")):
    w = sum(1 for t in grp if t["net_pnl"] >= 0)
    print(f"{name}: n={len(grp)} W={w} L={len(grp)-w} net={sum(t['net_pnl'] for t in grp):+.2f} "
          f"stretches={[round(t['_stretch'],2) for t in grp]}")
print(f"missing stretch: {len(miss)}")

# ---- Q5 hourly PnL (PT, entry hour) ----
print("\n=== Q5 HOURLY PnL (PT, by ENTRY hour; net incl fees) ===")
hourly = collections.defaultdict(lambda: [0, 0.0])
for t in entries:
    h = pt(t["opened_at"]).hour
    hourly[h][0] += 1
    hourly[h][1] += t["net_pnl"]
for h in sorted(hourly):
    lbl = datetime.time(h).strftime("%I %p")
    n, s = hourly[h]
    print(f"  {lbl}: n={n} net={s:+.2f}")

# ---- Q4 old-geometry levels + MFE/MAE table for slot losers ----
print("\n=== Q4 slot live losers: old geometry levels (SL 1.2% / TP 1.6% price) ===")
for t in [x for x in slot_live if x["net_pnl"] < 0]:
    e = t["entry_price"]; d = 1 if t["side"] == "long" else -1
    old_sl = e * (1 - 0.012 * d); old_tp = e * (1 + 0.016 * d)
    exit_move = (t["exit_price"] - e) / e * 100 * d
    peak = t.get("peak_price")
    mfe = (peak - e) / e * 100 * d if peak else None
    print(f"  {t['symbol'].split('/')[0]:9s} {t['side']:5s} entry={e} exit={t['exit_price']} "
          f"({exit_move:+.2f}% oriented) reason={t['exit_reason']} "
          f"old_SL={old_sl:.6g} old_TP={old_tp:.6g} peak={peak} MFE={mfe if mfe is None else round(mfe,2)}%")
