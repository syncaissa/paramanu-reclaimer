"""Experiment 12 - Test each claim of the paper against a finished Monte Carlo sweep.

Reads results/sweep_<N>.csv from 06_sweep.py and writes the numbers quoted in
the paper's Robustness section: claim-by-claim outcomes, the rule-of-three
bound when a failure is never observed, and the breakdown by pressure.

    python 12_sweep_analysis.py --samples 5000
"""
import _common  # noqa: F401
import argparse

import numpy as np
import pandas as pd

from paramanu_sim.ladder import SIMULATED_BANDS
from paramanu_sim.plotting import RESULTS, record

ap = argparse.ArgumentParser()
ap.add_argument("--samples", type=int, default=5000)
ap.add_argument("--tag", default="", help='e.g. "_vapor_model" for the earlier trace model')
args = ap.parse_args()
name = f"sweep_{args.samples}{args.tag}"

df = pd.read_csv(RESULTS / f"{name}.csv")
failed = df[df["error"].notna()] if "error" in df else df.iloc[0:0]
if len(failed):
    print(f"{len(failed)} feeds failed and are excluded:")
    print(failed[["sample", "P_atm", "error"]].to_string(index=False))
    failed[["sample", "P_atm", "error"]].to_csv(RESULTS / f"{name}_failed.csv", index=False)
df = df[df["error"].isna()] if "error" in df else df
n = len(df)
chemistry = "scale_Au_in_Fe" in df


def band(T: float) -> str:
    for name, lower in SIMULATED_BANDS:
        if T >= lower:
            return name
    return "cold"


def rule_of_three(failures: int, trials: int) -> float | None:
    """95% upper bound on the failure rate when none is observed in `trials`."""
    return 3.0 / trials if failures == 0 and trials > 0 else None


out = {"samples": n, "failed": int(len(failed))}
for el in ("Zn", "Pb", "Cd", "Hg"):
    # only feeds that contain the element can test the claim (high pre-treatment
    # can remove every piece that carries it)
    col = df[f"{el}_in_Au_band"].dropna()
    fails = int((col > 0).sum())
    out[f"{el}_in_Au_band"] = {"feeds_containing": int(len(col)), "feeds_with_any": fails,
                               "max": float(col.max()), "median": float(col.median()),
                               "p95": float(col.quantile(0.95)),
                               "rate_bound_95": rule_of_three(fails, len(col))}
dT = df["T50_Au"] - df["T50_Fe"]
out["Au_minus_Fe_T50_K"] = {"median": float(dT.median()), "p05": float(dT.quantile(0.05)),
                            "p95": float(dT.quantile(0.95)),
                            "within_250K": float((dT.abs() <= 250).mean()),
                            "within_400K": float((dT.abs() <= 400).mean())}
out["share_Au"] = {"median": float(df.share_Au.median()), "p05": float(df.share_Au.quantile(0.05)),
                   "p95": float(df.share_Au.quantile(0.95))}
if chemistry:
    # gold between the iron band (B) and the copper band (C)
    for b_ in ("A", "B", "C", "D1", "D2"):
        col = f"Au_in_{b_}"
        if col in df:
            out[f"Au_share_in_{b_}"] = {"median": float(df[col].median()), "p05": float(df[col].quantile(0.05)),
                                       "p95": float(df[col].quantile(0.95))}
    ratio = np.log(df.scale_Au_in_Fe / df.scale_Au_in_Cu)
    out["Au_B_vs_gamma_ratio_corr"] = float(np.corrcoef(ratio, df.Au_in_B)[0, 1])
    for el in ("Pd", "Pt", "Ag"):
        out[f"{el}_band_counts"] = df[f"band_{el}"].value_counts().to_dict()
    out["Au_in_B_by_trace_data"] = df.groupby("trace_data").Au_in_B.median().to_dict()
    for el in ("Zn", "Pb", "Cd", "Hg"):
        col = df[f"{el}_in_gold_bands"].dropna()
        fails = int((col > 0).sum())
        out[f"{el}_in_gold_bands"] = {"feeds_containing": int(len(col)), "feeds_with_any": fails,
                                      "max": float(col.max()), "median": float(col.median()),
                                      "rate_bound_95": rule_of_three(fails, len(col))}
else:
    out["share_Au_by_gamma"] = {"gamma_below_0.6": float(df.share_Au[df.gamma < 0.6].median()),
                                "gamma_above_1.5": float(df.share_Au[df.gamma > 1.5].median()),
                                "corr_log_gamma": float(np.corrcoef(np.log(df.gamma), df.share_Au)[0, 1])}
out["Au_band_counts"] = df.band_Au.value_counts().to_dict()

rows = []
for P, g in df.groupby("P_atm"):
    rows.append({"P_atm": P, "feeds": len(g),
                 "Au_band_B": (g.band_Au == "B").mean(), "Au_band_A": (g.band_Au == "A").mean(),
                 "Au_band_C": (g.band_Au == "C").mean(), "Au_band_D1": (g.band_Au == "D1").mean(), "Au_band_D2": (g.band_Au == "D2").mean(),
                 **({"Au_in_B_median": g.Au_in_B.median(), "Au_in_C_median": g.Au_in_C.median(),
                     "Au_in_BC_median": (g.Au_in_B + g.Au_in_C).median(),
                     "Au_in_BC_p05": (g.Au_in_B + g.Au_in_C).quantile(0.05)} if chemistry else {}),
                 "T50_Fe_median": g.T50_Fe.median(), "T50_Au_median": g.T50_Au.median(),
                 "Au_same_band_as_Fe": (g.T50_Au.map(band) == g.T50_Fe.map(band)).mean(),
                 "share_Au_median": g.share_Au.median(),
                 "Cd_in_Au_band_max": g.Cd_in_Au_band.max(),
                 "Hg_gas_median": g.Hg_left_in_gas.median(),
                 "Hg_gas_p05": g.Hg_left_in_gas.quantile(0.05),
                 "Hg_gas_p95": g.Hg_left_in_gas.quantile(0.95)})
by_p = pd.DataFrame(rows)
by_p.to_csv(RESULTS / f"{name}_by_pressure.csv", index=False)
out["by_pressure"] = by_p.to_dict(orient="records")
record(f"{name}_claims", out)

pd.set_option("display.width", 160)
print(by_p.round(4).to_string(index=False))
for k, v in out.items():
    if k != "by_pressure":
        print(k, v)
