#!/bin/bash
set -e
cd /Users/jonaspenaso/Desktop/Phmex-S/scripts/research/sr-bounce-scan

# Phase A (baseline) is already running in the background (PID from earlier
# launch). Wait for it to finish before starting L1/L4/analyze.
until grep -q "TOTAL" lever_lab_cache/phaseA_baseline.log 2>/dev/null; do
  sleep 30
done
echo "BASELINE_DONE $(date)"

python3 lever_lab.py L1 > lever_lab_cache/phaseB_L1.log 2>&1
echo "L1_DONE $(date)"

python3 lever_lab.py L4 > lever_lab_cache/phaseC_L4.log 2>&1
echo "L4_DONE $(date)"

python3 lever_lab.py analyze > lever_lab_cache/phaseD_analyze.log 2>&1
echo "ANALYZE_DONE $(date)"

echo "PIPELINE_COMPLETE"
