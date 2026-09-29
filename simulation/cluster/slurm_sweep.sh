#!/bin/bash
#SBATCH --job-name=paramanu-sweep
#SBATCH --array=0-49
#SBATCH --cpus-per-task=32
#SBATCH --time=02:00:00
# 50 tasks x 200 samples = 10,000 samples. Each task writes its own CSV.
set -euo pipefail
cd "$SLURM_SUBMIT_DIR/../scripts"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1   # one thread per worker
python - <<PY
import sys; sys.path.insert(0, "..")
from paramanu_sim.sweep import SweepConfig, run
cfg = SweepConfig(samples=200, seed=20260928 + ${SLURM_ARRAY_TASK_ID})
run(cfg, workers=${SLURM_CPUS_PER_TASK}).to_csv("../results/sweep_task_${SLURM_ARRAY_TASK_ID}.csv", index=False)
PY
