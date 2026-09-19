import json, sys
frozen, out_dir = sys.argv[1], sys.argv[2]
t = json.load(open(frozen))["thesis"]
base = t["spec"]["tp_bps"]
for name, mult in (("plus", 1.2), ("minus", 0.8)):
    v = json.loads(json.dumps(t)); v["spec"]["tp_bps"] = round(base * mult, 6)
    with open(f"{out_dir}/thesis_{name}.json", "w") as fh: json.dump(v, fh)
