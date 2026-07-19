#!/usr/bin/env python3
"""Pre-registered analysis of entry-position features. ALL IN-SAMPLE.

Registered BEFORE looking at feature values:
- Books: FULL (all reconstructed) and RESIDUAL (excluding toxic cell
  trade_count<=20 & htf_adx>=35 — already blocked by the F5 gate).
- Per feature (8): W vs L mean/median, Cohen's d, 10k-bootstrap 95% CI on
  mean diff. Bootstrap: resample winners and losers INDEPENDENTLY each
  iteration, take the DIFF, percentile the diffs (house bug rule: never
  sort per-side first).
- Threshold sweep: deciles 10..90% x {block-above, block-below}
  -> 8 x 9 x 2 = 144 tests per book. Metric: $saved = -sum(net of blocked).
- Multiple testing: family-wise placebo = 1000 permutations of the net
  vector; per permutation, max $saved over ALL 144 tests -> the real best
  candidate must beat this max-distribution (rank reported). Per-candidate
  placebo rank also reported (same cell, permuted nets). Bonferroni
  reference alpha = .05/144 = 3.5e-4.
- Conjunctions: pairs among top-3 features (by placebo-ranked $saved),
  joint decile sweep in each feature's chosen block direction
  (9x9=81 tests/pair), own family-wise placebo over all pair-tests.
"""
import json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(20260718)

FEATS = ["rsi14_o", "rsi7_o", "d_ema21_o", "d_ema50_o", "d_vwap_o",
         "stretch_ema21_atr_o", "stretch_vwap_atr_o", "range_pos20_o"]

rows = json.load(open(os.path.join(HERE, "features.json")))


def analyze(book_rows, book_name, n_perm=1000, n_boot=10000):
    out = {"book": book_name, "n": len(book_rows)}
    net = np.array([r["net"] for r in book_rows])
    X = {f: np.array([r[f] for r in book_rows]) for f in FEATS}
    win = net > 0
    out["winners"] = int(win.sum()); out["losers"] = int((~win).sum())
    out["sum_net"] = round(float(net.sum()), 2)

    # ---- per-feature distributions ----
    feat_tbl = []
    for f in FEATS:
        x = X[f]; xw, xl = x[win], x[~win]
        diff = xw.mean() - xl.mean()
        sp = np.sqrt(((len(xw)-1)*xw.var(ddof=1) + (len(xl)-1)*xl.var(ddof=1)) / (len(xw)+len(xl)-2))
        d = diff / sp if sp > 0 else 0.0
        boots = np.empty(n_boot)
        for b in range(n_boot):
            boots[b] = rng.choice(xw, len(xw)).mean() - rng.choice(xl, len(xl)).mean()
        lo, hi = np.percentile(boots, [2.5, 97.5])
        feat_tbl.append({"feature": f,
                         "mean_W": round(float(xw.mean()), 3), "mean_L": round(float(xl.mean()), 3),
                         "med_W": round(float(np.median(xw)), 3), "med_L": round(float(np.median(xl)), 3),
                         "diff": round(float(diff), 3), "cohens_d": round(float(d), 3),
                         "ci95": [round(float(lo), 3), round(float(hi), 3)],
                         "ci_excl_0": bool(lo > 0 or hi < 0)})
    out["features"] = feat_tbl

    # ---- threshold sweep ----
    def sweep_saved(net_vec):
        """Return (all_results, max_saved) for the 144-test family on net_vec."""
        res, mx = [], -1e18
        for f in FEATS:
            x = X[f]
            for q in range(10, 100, 10):
                thr = np.percentile(x, q)
                for direction in ("above", "below"):
                    mask = x >= thr if direction == "above" else x <= thr
                    nb = int(mask.sum())
                    if nb == 0 or nb == len(net_vec):
                        continue
                    saved = -float(net_vec[mask].sum())
                    res.append((f, q, float(thr), direction, nb, saved, mask))
                    if saved > mx:
                        mx = saved
        return res, mx

    real_res, real_max = sweep_saved(net)

    # family-wise + per-candidate placebo
    perm_max = np.empty(n_perm)
    # store permuted saved for each cell to get per-candidate ranks
    cell_saved_perm = {("%s|%d|%s" % (f, q, dr)): np.empty(n_perm)
                       for (f, q, thr, dr, nb, sv, m) in real_res}
    masks = {("%s|%d|%s" % (f, q, dr)): m for (f, q, thr, dr, nb, sv, m) in real_res}
    for pi in range(n_perm):
        pnet = rng.permutation(net)
        mx = -1e18
        for key, m in masks.items():
            s = -float(pnet[m].sum())
            cell_saved_perm[key][pi] = s
            if s > mx:
                mx = s
        perm_max[pi] = mx
    out["placebo_familywise"] = {
        "n_tests": len(real_res), "n_perm": n_perm,
        "real_best_saved": round(real_max, 2),
        "perm_max_median": round(float(np.median(perm_max)), 2),
        "perm_max_p95": round(float(np.percentile(perm_max, 95)), 2),
        "familywise_p": round(float((perm_max >= real_max).mean()), 4),
    }

    # per-feature best split with per-candidate placebo rank
    best_by_feat = {}
    for (f, q, thr, dr, nb, sv, m) in real_res:
        if f not in best_by_feat or sv > best_by_feat[f]["saved"]:
            key = "%s|%d|%s" % (f, q, dr)
            best_by_feat[f] = {
                "feature": f, "pctile": q, "thr": round(thr, 4), "block": dr,
                "n_blocked": nb, "winners_lost": int(win[m].sum()),
                "losers_avoided": int((~win)[m].sum()),
                "saved": round(sv, 2),
                "placebo_p_cell": round(float((cell_saved_perm[key] >= sv).mean()), 4),
            }
    out["best_splits"] = sorted(best_by_feat.values(), key=lambda r: -r["saved"])

    # ---- conjunctions: pairs among top-3 by saved ----
    top3 = [b["feature"] for b in out["best_splits"][:3]]
    dirs = {b["feature"]: b["block"] for b in out["best_splits"]}
    pair_res = []
    pair_masks = {}
    for a in range(len(top3)):
        for b in range(a + 1, len(top3)):
            fa, fb = top3[a], top3[b]
            for qa in range(10, 100, 10):
                ta = np.percentile(X[fa], qa)
                ma = X[fa] >= ta if dirs[fa] == "above" else X[fa] <= ta
                for qb in range(10, 100, 10):
                    tb = np.percentile(X[fb], qb)
                    mb = X[fb] >= tb if dirs[fb] == "above" else X[fb] <= tb
                    m = ma & mb
                    nb_ = int(m.sum())
                    if nb_ < 5 or nb_ == len(net):
                        continue
                    sv = -float(net[m].sum())
                    key = f"{fa}|{qa}&{fb}|{qb}"
                    pair_res.append({"pair": f"{fa} {dirs[fa]} p{qa} AND {fb} {dirs[fb]} p{qb}",
                                     "thr_a": round(float(ta), 4), "thr_b": round(float(tb), 4),
                                     "n_blocked": nb_, "winners_lost": int(win[m].sum()),
                                     "losers_avoided": int((~win)[m].sum()), "saved": round(sv, 2),
                                     "key": key})
                    pair_masks[key] = m
    if pair_res:
        perm_max_pair = np.empty(n_perm)
        cell_pair = {r["key"]: np.empty(n_perm) for r in pair_res}
        for pi in range(n_perm):
            pnet = rng.permutation(net)
            mx = -1e18
            for key, m in pair_masks.items():
                s = -float(pnet[m].sum())
                cell_pair[key][pi] = s
                if s > mx:
                    mx = s
            perm_max_pair[pi] = mx
        pair_res.sort(key=lambda r: -r["saved"])
        best_pair = pair_res[0]
        out["conjunctions"] = {
            "n_tests": len(pair_res), "top5": pair_res[:5],
            "familywise_p_best": round(float((perm_max_pair >= best_pair["saved"]).mean()), 4),
            "perm_max_median": round(float(np.median(perm_max_pair)), 2),
            "perm_max_p95": round(float(np.percentile(perm_max_pair, 95)), 2),
            "placebo_p_cell_best": round(float((cell_pair[best_pair["key"]] >= best_pair["saved"]).mean()), 4),
        }
        for r in pair_res:
            r.pop("key", None)
    return out


results = {
    "FULL": analyze(rows, "FULL"),
    "RESIDUAL": analyze([r for r in rows if not r["toxic"]], "RESIDUAL (non-toxic)"),
}
json.dump(results, open(os.path.join(HERE, "stats_results.json"), "w"), indent=1, default=str)
print(json.dumps(results, indent=1, default=str))
