#!/bin/zsh
# exploratory driver
cd /Users/jonaspenaso/Desktop/Phmex-S/research/swarm/runs/2026-09-17-0732/exploratory/vol_structure
for a in "1.0 2.0 200 48" "1.0 1.75 200 48" "0.9 1.75 150 48"; do
  parts=(${=a})
  f="01_out_c${parts[1]}_s${parts[2]}_tp${parts[3]}_h${parts[4]}.json"
  PYTHONPATH=/Users/jonaspenaso/Desktop/Phmex-S python3 01_probe_shock_continuation.py ${parts[1]} ${parts[2]} ${parts[3]} ${parts[4]} 2>/dev/null > "$f"
  python3 -c "
import json; d=json.load(open('$f')); print(d['params'],'n',d['n'],'net',round(d['net_bps_mean'],1),'ci',[round(x,1) for x in d['ci95']],'wr',round(d['wr'],3),'side',d['by_side'],d['exit_reason'])"
done
