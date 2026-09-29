"""Experiment 3 - Does the heap carry its own reducing agent?

Runs the ladder with the organic fraction (plastics, paper) scaled by 0, 0.5,
1 and 2 and reports what share of each metal condenses as metal rather than as
oxide, carbide or salt.
"""
import _common  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim.equilibrium import composition
from paramanu_sim.feed import DEFAULT_MASSES, make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import RESULTS, record, save
from paramanu_sim.thermo import load

METALS = ["Fe", "Ni", "Cu", "Cr", "Si", "Zn", "Pb"]
th = load()
rows = []
for factor in (0.0, 0.5, 1.0, 2.0):
    masses = dict(DEFAULT_MASSES)
    masses["plastics"] *= factor
    masses["paper"] *= factor
    feed = make_feed(masses, pretreat_fraction=0.0)   # keep every metal in all variants
    res = run_ladder(feed, dT=50.0, include_traces=False)
    sp = res.species
    for el in METALS:
        metal = oxide = 0.0
        for _, r in sp.iterrows():
            comp = composition(th, r.species)
            if el not in comp:
                continue
            n = r.moles * comp[el]
            if len(comp) == 1:
                metal += n
            else:
                oxide += n
        total = metal + oxide
        rows.append({"organics_factor": factor, "element": el,
                     "metal_share": metal / total if total else np.nan})
    c_over_o = (feed.element_moles["C"] + feed.element_moles["H"] / 2) / feed.element_moles["O"]
    rows.append({"organics_factor": factor, "element": "(C+H/2)/O", "metal_share": c_over_o})

df = pd.DataFrame(rows).pivot(index="element", columns="organics_factor", values="metal_share")
df.to_csv(RESULTS / "reductant_metal_share.csv")
record("reductant_ratio_default", float(df.loc["(C+H/2)/O", 1.0]))
record("reductant_Fe_metal_share", {str(k): float(v) for k, v in df.loc["Fe"].items()})

fig, ax = plt.subplots(figsize=(5.8, 2.9))
sub = df.drop(index="(C+H/2)/O")
w = 0.2
for i, f in enumerate(sub.columns):
    ax.bar(np.arange(len(sub)) + (i - 1.5) * w, sub[f] * 100, w,
           color=["#B0B0B0", "#E0A800", "#2E8B2E", "#1F4E9E"][i],
           label=f"organics x{f:g}  (C+H/2)/O = {df.loc['(C+H/2)/O', f]:.2f}")
ax.set_xticks(range(len(sub)))
ax.set_xticklabels(sub.index)
ax.set_ylabel("% condensed as metal")
ax.set_title("The heap's own carbon and hydrogen reduce metals during condensation", fontsize=9)
ax.legend(fontsize=6.5, frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.12))
save(fig, "fig_reductant")
print(df.round(3).to_string())
