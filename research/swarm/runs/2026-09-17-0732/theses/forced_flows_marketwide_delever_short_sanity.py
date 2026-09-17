"""Sanity check for the thesis signal on long_1h TRAIN (18 symbols, GIGGLE excluded):
bar counts, value set, nonzero count per symbol, and screen.causality_check on every symbol."""
import importlib.util, json
from research.swarm.lib import load_data as ld, screen as sc
p = "research/swarm/runs/2026-09-17-0732/theses/forced_flows_marketwide_delever_short_signal.py"
spec = importlib.util.spec_from_file_location("sig", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
syms = [s for s in ld.list_symbols("long_1h") if s != "GIGGLE"]
out = {}
for s in syms:
    df = ld.load_ohlcv(s, "1h", era="train", dataset="long_1h")
    sig = m.signals(df)
    sc.causality_check(m.signals, df, symbol=s)
    out[s] = {"bars": int(len(df)), "span": [str(df.index.min()), str(df.index.max())], "values": sorted(int(v) for v in sig.unique()),
              "nonzero": int((sig != 0).sum()), "causality": "PASS"}
    print(s, json.dumps(out[s]))
json.dump(out, open("research/swarm/runs/2026-09-17-0732/theses/forced_flows_marketwide_delever_short.sanity_train.json", "w"), indent=2)
