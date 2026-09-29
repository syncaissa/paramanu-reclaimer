#!/usr/bin/env bash
# Run every PARAMANU experiment, write results/, then regenerate ../Results.txt.
# About 1.5 hours on 2 cores. SAMPLES=5000 reproduces the published sweep (use a
# many-core machine: about 3.5 core-seconds per feed); FALSIFY=1 adds the
# adversarial search (about 6,600 ladders).
set -euo pipefail
cd "$(dirname "$0")/scripts"
for s in 01_validate 02_ladder 03_reductant 04_energy 05_chamber 07_theory_checks 08_reactor_design 09_convergence 10_sensitivity 11_alloy_model 13_breakdown 14_benchmarks 15_gold_copper 16_landfill_inventory 17_catalysts 18_independent_verification; do
  echo "== $s"; python -W ignore "$s.py" > "../results/log_$s.txt"
done
python -W ignore 06_sweep.py --samples "${SAMPLES:-24}" > ../results/log_06_sweep.txt
python -W ignore 12_sweep_analysis.py --samples "${SAMPLES:-24}" > ../results/log_12_sweep_analysis.txt
python -W ignore 22_dilution_and_margin.py > ../results/log_22_dilution_and_margin.txt   # needs falsification.csv
python -W ignore 23_self_sufficiency.py > ../results/log_23_self_sufficiency.txt   # needs 16's landfill_inventory.csv
python -W ignore 24_heat_recovery_and_scale.py > ../results/log_24_heat_recovery_and_scale.txt   # needs 08 and 23
python -W ignore 21_global_sensitivity.py --samples "${SAMPLES:-24}" --bins 5 > ../results/log_21_global_sensitivity.txt
python -W ignore 19_reproducibility.py --samples "${SAMPLES:-24}" --check 4 > ../results/log_19_reproducibility.txt
# The falsification search needs about 6,600 ladders: a cloud server (cluster/runpod/run_job_on_runpod.sh)
[ "${FALSIFY:-0}" = 1 ] && python -W ignore 20_falsification.py --gens 25 --pop 1 > ../results/log_20_falsification.txt
python ../tools/write_results.py
echo "done: see results/ and ../Results.txt"
