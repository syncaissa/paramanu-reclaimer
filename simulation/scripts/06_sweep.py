"""Experiment 6 - Monte Carlo robustness sweep.

Do the conclusions survive realistic variation of the feed, pre-treatment,
pressure and trace-metal activity? Run small here, large on a cluster:

    python 06_sweep.py --samples 24                       # laptop / CI
    python 06_sweep.py --samples 5000 --backend ray       # GPU/CPU cluster

Finished samples are checkpointed to results/sweep_<N>.partial.jsonl as they
complete; rerunning the same command after a crash resumes from there. The
log gets STATUS lines (START / RESUMING / PROGRESS / COMPLETE / FAILED) with
timestamps, so a log that ends without COMPLETE or FAILED means the machine
or process died at about the last timestamp.
"""
import _common  # noqa: F401
import argparse
import sys
import time
import traceback
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np

from paramanu_sim.plotting import RESULTS, record, save
from paramanu_sim.sweep import SweepConfig, available_cpus, run

ap = argparse.ArgumentParser()
ap.add_argument("--samples", type=int, default=24)
ap.add_argument("--backend", choices=["process", "ray", "serial"], default="process")
ap.add_argument("--workers", type=int, default=None)
ap.add_argument("--dT", type=float, default=50.0)
args = ap.parse_args()



def status(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] STATUS {msg}", flush=True)


t0 = time.time()
last = {"t": 0.0}


def progress(done: int, total: int, resumed: int) -> None:
    now = time.time()
    if done != total and now - last["t"] < 60 and done % 25:
        return
    last["t"] = now
    rate = (done - resumed) / (now - t0)
    eta = (total - done) / rate if rate else float("nan")
    status(f"PROGRESS {done}/{total} ({100 * done / total:.1f}%) "
           f"{rate * 3600:.0f} samples/h, ETA {eta / 3600:.1f} h")


RESULTS.mkdir(exist_ok=True)
ckpt = RESULTS / f"sweep_{args.samples}.partial.jsonl"
if ckpt.exists():
    status(f"RESUMING from {ckpt.name} (previous run did not finish)")
status(f"START samples={args.samples} backend={args.backend} "
       f"workers={args.workers or available_cpus()} dT={args.dT}")
try:
    df = run(SweepConfig(samples=args.samples, dT=args.dT), backend=args.backend,
             workers=args.workers, checkpoint=ckpt, progress=progress)
except BaseException:
    status("FAILED")
    traceback.print_exc()
    sys.exit(1)
df.to_csv(RESULTS / f"sweep_{args.samples}.csv", index=False)
ckpt.unlink(missing_ok=True)
elapsed = time.time() - t0

summary = {}
for col in ("share_Au", "ppm_in_band_Au", "Hg_left_in_gas", "Zn_in_Au_band", "Cd_in_Au_band",
            "Pb_in_Au_band", "T50_Fe", "T50_Au", "T50_Zn"):
    if col in df:
        v = df[col].dropna()
        summary[col] = {"p05": float(v.quantile(0.05)), "median": float(v.median()),
                        "p95": float(v.quantile(0.95))}
summary["Au_band_mode"] = str(df["band_Au"].mode().iloc[0]) if "band_Au" in df else None
summary["samples"] = int(len(df))
summary["seconds"] = elapsed
record(f"sweep_summary_{args.samples}", summary)

fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.4))
axes[0].hist(df["share_Au"] * 100, bins=12, color="#C9A227")
axes[0].set_xlabel("Au in its main band (%)")
axes[1].hist(df[[c for c in ("Zn_in_Au_band", "Cd_in_Au_band", "Pb_in_Au_band") if c in df]].max(axis=1) * 100,
             bins=12, color="#C2185B")
axes[1].set_xlabel("Zn, Cd, Pb in Au band (max %)")
axes[2].hist(df["Hg_left_in_gas"] * 100, bins=12, color="#2E8B2E")
axes[2].set_xlabel("Hg still gaseous (%)")
for ax in axes:
    ax.set_ylabel("samples")
fig.suptitle(f"Monte Carlo sweep, {len(df)} feeds (pre-treatment 0-30%, 0.1-5 atm)", fontsize=8.5)
fig.tight_layout()
save(fig, "fig_sweep")
print(df.describe().T.round(3).to_string())
print(f"{len(df)} samples in {elapsed:.0f} s")
status(f"COMPLETE {len(df)} samples in {elapsed / 3600:.2f} h")
