# Running large sweeps on your servers

The Monte Carlo sweep (`scripts/06_sweep.py`) is embarrassingly parallel:
each sample is one independent condensation ladder with full trace chemistry
(about 3.5 core-seconds on a cloud server core at the default 50 K step). The
published 5,000-sample run took 4.9 core-hours: 22 minutes on 13 cores. Install
the pinned versions in `requirements.txt`; newer SciPy/pandas stalled some feeds. Set `OMP_NUM_THREADS=1` so each worker
uses one thread; `--workers` defaults to the CPUs the container may use.

## One server

```bash
python scripts/06_sweep.py --samples 5000 --workers 64
```

## Many servers (Ray)

```bash
pip install "ray[default]"
# on the head node
ray start --head --port=6379
# on every other node
ray start --address=<head-ip>:6379
# from any node
RAY_ADDRESS=auto python scripts/06_sweep.py --samples 20000 --backend ray
```

## Slurm

See `slurm_sweep.sh`. Each array task runs an independent slice with its
own seed range; merge the CSVs afterwards.

## GPUs

Equilibrium solves do not benefit from GPUs. GPUs are used by
`scripts/05_chamber.py --gpu` (CuPy) for dense Saha ionization grids, and
are the right hardware for the next steps listed in the paper's research
agenda: reacting-flow CFD of the chamber and machine-learned interatomic
potentials for species missing from the NASA database.
