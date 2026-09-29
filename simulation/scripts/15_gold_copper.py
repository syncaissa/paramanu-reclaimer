"""Experiment 15 - Does gold stay with iron, or follow copper?

Measured equilibria (Yamaguchi et al., Mater. Trans. 47 (2006) 1864) show gold
strongly prefers liquid copper to liquid iron. In the condensation ladder the
question is one of timing: iron condenses first (2,000-2,600 K) and copper later
(1,600-2,000 K), and gold's dislike of iron weakens as temperature rises.

(a) Benchmark: the activity coefficients used here (data/trace_gamma.json)
    against the measured Fe/Cu distribution ratios at 1,373 K.
(b) The ladder at 1 atm with full trace chemistry and four sets of
    coefficients: ideal (gamma = 1), measured, measured pushed against iron
    (gamma_Au,Fe x2, gamma_Au,Cu /2) and pushed toward iron (/2, x2).
(c) The measured set at 0.1 and 5 atm.
"""
import _common  # noqa: F401
from concurrent.futures import ProcessPoolExecutor

import cantera as ct
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import RESULTS, record, save
from paramanu_sim.trace_chem import henry_gamma

# ---------------------------------------------------------------- (a)
g = henry_gamma()
T = 1373.0
M_FE, M_CU = 55.845, 63.546
measured = {"Au": (0.013, 0.0071), "Ag": (0.0027, 0.0027)}   # Table 3: Fe-Cu-P, Fe-Cu-P-C
rows = []
for el, (m_p, m_pc) in measured.items():
    pred = g(el, "Cu", T) / g(el, "Fe", T) * (M_CU / M_FE)   # mass-% ratio, dilute limit
    rows.append({"element": el, "gamma_in_Fe": g(el, "Fe", T), "gamma_in_Cu": g(el, "Cu", T),
                 "L_FeCu_predicted": pred, "L_FeCu_measured_FeCuP": m_p, "L_FeCu_measured_FeCuPC": m_pc,
                 "predicted_over_measured": [pred / m_p, pred / m_pc]})
bench = pd.DataFrame(rows)
bench.to_csv(RESULTS / "gold_copper_benchmark.csv", index=False)
record("gold_copper_benchmark", bench.to_dict(orient="records"))

# ---------------------------------------------------------------- (b), (c)
SCEN = {
    "ideal (gamma = 1)": (None, 1.0),
    "measured": ({}, 1.0),
    "measured, against iron": ({("Au", "Fe"): 2.0, ("Au", "Cu"): 0.5}, 1.0),
    "measured, toward iron": ({("Au", "Fe"): 0.5, ("Au", "Cu"): 2.0}, 1.0),
    "measured, 0.1 atm": ({}, 0.1),
    "measured, 5 atm": ({}, 5.0),
}


def run(item):
    name, (scale, P_atm) = item
    gamma = (lambda a, b, T: 1.0) if scale is None else henry_gamma(scale)
    lad = run_ladder(make_feed(), P=P_atm * ct.one_atm, dT=25.0, trace_model="chemistry",
                     trace_gamma=gamma)
    rec = lad.recovery_table()
    d = lad.trace_detail
    hosts = {}
    for el in ("Au", "Pd", "Ag"):
        sub = d[d.element == el]
        cols = [c for c in sub.columns if c.startswith("in_")]
        tot = sub[cols].sum()
        hosts[el] = (tot / tot.sum()).round(3).to_dict() if tot.sum() > 0 else {}
    T50 = lad.condensation_temperature()
    return name, rec.loc[["Au", "Pd", "Pt", "Ag", "Fe", "Cu"]], hosts, \
        {e: float(T50.get(e, np.nan)) for e in ("Fe", "Cu", "Ni", "Au", "Pd", "Ag")}


with ProcessPoolExecutor() as ex:
    results = list(ex.map(run, SCEN.items()))

out = []
for name, rec, hosts, T50 in results:
    for el in ("Au", "Pd", "Pt", "Ag"):
        r = rec.loc[el]
        out.append({"scenario": name, "element": el, **{f"band_{b}": float(r.get(b, 0.0)) for b in rec.columns},
                    "main_band": r.idxmax(), "hosts": hosts.get(el, {}), "T50": T50.get(el),
                    "T50_Fe": T50["Fe"], "T50_Cu": T50["Cu"]})
res = pd.DataFrame(out)
res.to_csv(RESULTS / "gold_copper_ladder.csv", index=False)
record("gold_copper_ladder", res[res.element == "Au"][["scenario", "main_band", "band_A", "band_B", "band_C"]]
       .round(3).to_dict(orient="records"))

fig, ax = plt.subplots(figsize=(6.2, 2.8))
au = res[res.element == "Au"].set_index("scenario")
bands = [b for b in ("A", "B", "C", "D1", "D2", "E") if f"band_{b}" in au]
left = np.zeros(len(au))
colors = {"A": "#F8D7DA", "B": "#FBC78D", "C": "#FDE5C8", "D1": "#D4F7D4", "D2": "#B8E6B8", "E": "#DCE8F7"}
for b in bands:
    v = au[f"band_{b}"].values * 100
    ax.barh(au.index, v, left=left, color=colors[b], edgecolor="0.4", label=f"Band {b}")
    left += v
ax.set_xlabel("Share of gold collected (%)")
ax.invert_yaxis()
ax.legend(fontsize=6.5, frameon=False, ncol=5, loc="lower center", bbox_to_anchor=(0.5, 1.0))
fig.tight_layout()
save(fig, "fig_gold_copper")

pd.set_option("display.width", 200)
print(bench.round(4).to_string(index=False))
print(res.drop(columns=["hosts"]).round(3).to_string(index=False))
for name, rec, hosts, T50 in results:
    print(f"{name}: gold condensed into {hosts['Au']}")
