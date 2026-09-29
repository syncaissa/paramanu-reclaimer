"""Experiment 21 - Which uncertain input actually drives each result? (Sobol indices)

First-order Sobol index of input X_i for output Y:
    S_i = Var( E[Y | X_i] ) / Var(Y),
the share of the output's variance that X_i explains alone (Sobol 1993,
Saltelli et al. 2008). It is estimated from the sweep's own 5,000 random feeds
by the given-data method (Plischke, Borgonovo & Smith 2013): sort the feeds by
X_i, cut them into 25 equal-count bins (or one bin per value for discrete
inputs), and take the variance of the bin means. The estimator's positive bias
is measured by repeating it on randomly permuted inputs and subtracted; an
index below the 95th percentile of that null is reported as indistinguishable
from zero. The inputs of every feed are regenerated from its seed
(sweep.draw), so no input needs to be stored.

    python 21_global_sensitivity.py --samples 5000
"""
import _common  # noqa: F401
import argparse

import numpy as np
import pandas as pd

from paramanu_sim.plotting import RESULTS, record
from paramanu_sim.sweep import SweepConfig, draw

ap = argparse.ArgumentParser()
ap.add_argument("--samples", type=int, default=5000)
ap.add_argument("--bins", type=int, default=25)
ap.add_argument("--csv", default=None, help="sweep table (default results/sweep_<samples>.csv)")
ap.add_argument("--no-record", action="store_true")
args = ap.parse_args()

out = pd.read_csv(args.csv or RESULTS / f"sweep_{args.samples}.csv").set_index("sample")
out = out[out.get("error", pd.Series(index=out.index, dtype=object)).isna()] if "error" in out else out
cfg = SweepConfig(samples=args.samples)
rows = []
for i in out.index:
    p = draw(cfg, int(i))
    r = {f"mass_{k}": np.log(v) for k, v in p["masses"].items()}
    r.update({f"trace_{k}": np.log(v) for k, v in p["traces"].items()})
    r.update({"hg_ppm": np.log(p["hg_ppm"]), "pretreat": p["pretreat"], "pressure": np.log10(p["P_atm"]),
              "chloride_data": p["trace_data"]})
    r.update({f"gamma_{k.replace('|', '_in_')}": np.log(v) for k, v in p["gamma_scale"].items()})
    rows.append(r)
X = pd.DataFrame(rows, index=out.index)

OUTPUTS = {"gold in Band B": "Au_in_B", "gold in Bands B+C": None, "gold half-condensation T": "T50_Au",
           "mercury left in gas": "Hg_left_in_gas", "cadmium in gold bands": "Cd_in_gold_bands"}
Y = pd.DataFrame(index=out.index)
for name, col in OUTPUTS.items():
    Y[name] = out["Au_in_B"] + out["Au_in_C"] if col is None else out[col]


def first_order(x: pd.Series, y: pd.Series, bins: int) -> float:
    if x.dtype == object or x.nunique() <= 5:
        g = x.astype(str)
    else:
        g = pd.qcut(x.rank(method="first"), bins, labels=False)
    means = y.groupby(g).mean()
    counts = y.groupby(g).size()
    return float(((means - y.mean()) ** 2 * counts).sum() / counts.sum() / y.var(ddof=0))


rng = np.random.default_rng(2026)
res = []
# All feeds, then only the feeds at 1 atm: pressure is an operating choice, so the
# second set shows which uncertain inputs matter once the plant's pressure is set.
for subset, keep in (("all", X.pressure.notna()), ("1 atm", X.pressure.abs() < 1e-9)):
    for name in Y:
        y = Y.loc[keep, name].astype(float)
        y = y[y.notna()]
        if len(y) < 200 or y.var() == 0:
            continue
        for inp in X:
            x = X.loc[y.index, inp]
            if x.nunique() <= 1:
                continue
            s = first_order(x, y, args.bins)
            null = [first_order(pd.Series(rng.permutation(x.values), index=x.index), y, args.bins) for _ in range(20)]
            res.append({"subset": subset, "output": name, "input": inp, "S1_raw": s, "null_mean": np.mean(null),
                        "S1": max(s - np.mean(null), 0.0), "significant": s > np.percentile(null, 95)})
S = pd.DataFrame(res)
if not args.no_record:
    S.to_csv(RESULTS / "global_sensitivity.csv", index=False)
top = {}
for (subset, name), g in S.groupby(["subset", "output"], sort=False):
    g = g.sort_values("S1", ascending=False)
    t = {r.input: round(r.S1, 3) for r in g.head(4).itertuples() if r.significant}
    t["sum_all_first_order"] = round(float(g.S1.sum()), 3)
    top[f"{subset}: {name}"] = t
if not args.no_record:
    record("global_sensitivity_top", top)
for name, t in top.items():
    print(f"{name}: {t}")
