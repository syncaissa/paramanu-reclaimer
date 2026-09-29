"""Experiment 19 - Do the sweep results reproduce on a different machine?

Picks feeds from the published sweep at random (fixed seed), recomputes each
one from its own seed on this machine, and compares the recorded metrics.
Every feed is defined only by (SweepConfig, sample index), so a match shows
the published numbers do not depend on the computer they were produced on.

    python 19_reproducibility.py --samples 5000 --check 20
"""
import _common  # noqa: F401
import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from paramanu_sim.plotting import RESULTS, record
from paramanu_sim.sweep import SweepConfig, draw, evaluate

ap = argparse.ArgumentParser()
ap.add_argument("--samples", type=int, default=5000)
ap.add_argument("--check", type=int, default=20)
args = ap.parse_args()

published = pd.read_csv(RESULTS / f"sweep_{args.samples}.csv").set_index("sample")
ids = sorted(np.random.default_rng(2026).choice(published.index, size=args.check, replace=False).tolist())
cfg = SweepConfig(samples=args.samples)
with ProcessPoolExecutor() as ex:
    rows = list(ex.map(evaluate, [draw(cfg, i) for i in ids]))
local = pd.DataFrame(rows).set_index("sample")

cols = [c for c in local.columns if c in published.columns
        and pd.api.types.is_numeric_dtype(local[c]) and pd.api.types.is_numeric_dtype(published[c])]
diff = (local[cols] - published.loc[ids, cols]).abs()
worst = diff.max().sort_values(ascending=False)
same_bands = all((local[f"band_{e}"] == published.loc[ids, f"band_{e}"]).all()
                 for e in ("Au", "Pd", "Pt", "Ag") if f"band_{e}" in local)
record("reproducibility", {"feeds_checked": len(ids), "metrics_compared": len(cols),
                           "max_abs_diff": float(worst.max()), "same_main_bands": bool(same_bands),
                           "worst_metric": worst.index[0]})
print(f"{len(ids)} feeds, {len(cols)} metrics: largest absolute difference {worst.max():.2e} "
      f"({worst.index[0]}); main bands identical: {same_bands}")
print(worst.head(10).to_string())
