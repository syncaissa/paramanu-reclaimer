"""Experiment 20 - Falsification: an optimizer that tries to break the claims.

The Monte Carlo sweep (06_sweep.py) asks how the claims fare on typical
feeds. This script asks the harder question: is there ANY feed and data set,
within wide but plausible bounds, for which they fail? For each claim an
optimizer (differential evolution, Storn & Price 1997) searches every input of
the sweep at once and is rewarded for pushing a toxic volatile metal into a
band that collects gold:

  zinc     : never in a band holding >= 10% of the gold      (0.1-5 atm)
  mercury  : never in a band holding >= 10% of the gold      (0.1-5 atm)
  cadmium  : at most traces in the gold bands                (0.1-5 atm)
  lead     : never in a gold band at the operating point     (1-5 atm, pre-treatment <= 15%)

Search space (56 inputs, wider than the sweep): each component mass and each
trace concentration x/3 to x3 (mass) or x/6 to x6 (traces and mercury), i.e.
3 standard deviations of the sweep's distributions; pre-treatment 0-30%;
pressure continuous (log-uniform); every activity coefficient across its
stated uncertainty; any of the three chloride data sets.

Objective: the share of the metal in the gold bands. Where that share is
exactly zero the landscape is flat, so the optimizer is also rewarded for
closing the gap between gold's and the metal's half-condensation temperatures,
a continuous distance to failure. A claim is falsified if any evaluated input
puts more than 1% of zinc, mercury or lead (0.1% of cadmium) in the gold bands.

    python 20_falsification.py [--gens 20] [--pop 1]
"""
import _common  # noqa: F401
import argparse
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from paramanu_sim.feed import DEFAULT_MASSES, DEFAULT_TRACES_PPM
from paramanu_sim.plotting import RESULTS, record
from paramanu_sim.sweep import SweepConfig, _draw_chemistry, _safe_evaluate, available_cpus

ap = argparse.ArgumentParser()
ap.add_argument("--gens", type=int, default=20)
ap.add_argument("--pop", type=int, default=1, help="population = pop x number of inputs")
ap.add_argument("--seed", type=int, default=2026)
ap.add_argument("--smoke", action="store_true", help="evaluate two random inputs per claim and stop")
args = ap.parse_args()

CFG = SweepConfig()
GAMMA = _draw_chemistry(CFG, np.random.default_rng(0))["gamma_scale"]      # keys only
from paramanu_sim.trace_chem import henry_gamma  # noqa: E402
FACTOR = {f"{a}|{b}": p["factor"] for (a, b), p in henry_gamma().table.items()}
FACTOR.update({f"{a}|{b}": CFG.unknown_factor for a, b in CFG.unknown_pairs})
MASS, TRACE, PAIRS = sorted(DEFAULT_MASSES), sorted(DEFAULT_TRACES_PPM), sorted(GAMMA)
DATA = list(CFG.trace_data_sets)

CLAIMS = {   # name: (metal, pressure range atm, max pre-treatment, falsified above)
    "zinc": ("Zn", (0.1, 5.0), 0.30, 0.01),
    "mercury": ("Hg", (0.1, 5.0), 0.30, 0.01),
    "cadmium": ("Cd", (0.1, 5.0), 0.30, 0.001),
    "lead": ("Pb", (1.0, 5.0), 0.15, 0.01),
}


def bounds(claim):
    _, (p0, p1), pre, _ = CLAIMS[claim]
    b = [(-math.log(3), math.log(3))] * len(MASS) + [(-math.log(6), math.log(6))] * (len(TRACE) + 1)
    b += [(0.0, pre), (math.log(p0), math.log(p1))]
    b += [(-math.log(FACTOR[k]), math.log(FACTOR[k])) for k in PAIRS]
    b += [(0.0, len(DATA) - 1e-9)]
    return b


def params(x, tag=-1):
    i = 0
    masses = {k: DEFAULT_MASSES[k] * math.exp(x[i + j]) for j, k in enumerate(MASS)}
    i += len(MASS)
    traces = {k: DEFAULT_TRACES_PPM[k] * math.exp(x[i + j]) for j, k in enumerate(TRACE)}
    i += len(TRACE)
    hg, pre, P = 2.0 * math.exp(x[i]), float(x[i + 1]), math.exp(x[i + 2])
    i += 3
    scale = {k: math.exp(x[i + j]) for j, k in enumerate(PAIRS)}
    return {"sample": tag, "masses": masses, "traces": traces, "hg_ppm": hg, "pretreat": pre,
            "P_atm": P, "gamma": 1.0, "dT": CFG.dT, "timeout_s": CFG.timeout_s, "gamma_scale": scale,
            "trace_data": DATA[int(x[-1])], "trace_model": "chemistry"}


def score(row, metal):
    """Lower is closer to falsification (the optimizer minimizes)."""
    if "error" in row:
        return 0.0, float("nan")
    share = row.get(f"{metal}_in_gold_bands", 0.0) or 0.0
    gap = row.get("T50_Au", np.nan) - row.get(f"T50_{metal}", np.nan)
    if not np.isfinite(gap):     # the metal never half-condenses: it stays in the gas, far from gold
        gap = row.get("T50_Au", 2000.0) - 300.0
    return -(math.log10(share + 1e-12) - max(gap, 0.0) / 1000.0), share


LOG = []


def run_claim(claim, ex):
    metal = CLAIMS[claim][0]

    def batch(xs):
        xs = np.atleast_2d(xs)
        rows = list(ex.map(_safe_evaluate, [params(x) for x in xs]))
        out = []
        for x, r in zip(xs, rows):
            f, share = score(r, metal)
            LOG.append({"claim": claim, "eval": len(LOG), "objective": f, "share_in_gold_bands": share,
                        "gap_K": r.get("T50_Au", np.nan) - r.get(f"T50_{metal}", np.nan),
                        "error": r.get("error", ""), "P_atm": r.get("P_atm"),
                        "gold_bands": r.get("gold_bands", ""), "x": json.dumps([round(float(v), 5) for v in x])})
            out.append(f)
        print(f"STATUS {time.strftime('%H:%M:%S')} {claim}: {len(LOG)} evaluations, "
              f"worst share so far {max(l['share_in_gold_bands'] for l in LOG if l['claim'] == claim and l['share_in_gold_bands'] == l['share_in_gold_bands']):.3g}",
              flush=True)
        return out

    # scipy calls the vectorized objective with shape (n_inputs, pop); transpose back
    res = differential_evolution(lambda X: batch(np.asarray(X).T), bounds(claim), vectorized=True,
                                 updating="deferred", popsize=args.pop, maxiter=args.gens, tol=0,
                                 polish=False, seed=args.seed, init="sobol")
    return res


if args.smoke:
    rng = np.random.default_rng(1)
    with ProcessPoolExecutor(max_workers=2) as ex:
        for claim in CLAIMS:
            xs = [[rng.uniform(lo, hi) for lo, hi in bounds(claim)] for _ in range(2)]
            for x, r in zip(xs, ex.map(_safe_evaluate, [params(x) for x in xs])):
                print(claim, r.get("error", ""), r.get("P_atm"), r.get("gold_bands"), score(r, CLAIMS[claim][0]))
    raise SystemExit

t0 = time.time()
summary = {}
with ProcessPoolExecutor(max_workers=available_cpus()) as ex:
    for claim in CLAIMS:
        res = run_claim(claim, ex)
        log = pd.DataFrame([l for l in LOG if l["claim"] == claim])
        worst = log.loc[log.share_in_gold_bands.fillna(-1).idxmax()]
        closest = log.loc[log.gap_K.idxmin()]
        limit = CLAIMS[claim][3]
        summary[claim] = {"evaluations": int(len(log)), "failed_evaluations": int((log.error != "").sum()),
                          "worst_share_in_gold_bands": float(worst.share_in_gold_bands),
                          "falsified": bool(worst.share_in_gold_bands > limit), "threshold": limit,
                          "smallest_T50_gap_K": float(closest.gap_K), "pressure_at_worst_atm": float(worst.P_atm)}
        print(claim, summary[claim], flush=True)
pd.DataFrame(LOG).to_csv(RESULTS / "falsification.csv", index=False)
summary["wall_s"] = time.time() - t0
record("falsification", summary)
print("STATUS done", json.dumps(summary))
