"""Experiment 11 - Removing the pure-phase assumption: liquid-metal alloying.

Repeats the ladder with one ideal liquid-metal solution (Fe, Ni, Cu, Cr, Si,
Al, Ti, Pb, Zn, Mg, Hg liquids mix ideally). Real alloys are not ideal, so
this brackets the truth together with the pure-phase model.
"""
import _common  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim.energy import all_gas_temperature
from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import CLASS, COLORS, RESULTS, record, save
from paramanu_sim.equilibrium import equilibrate

feed = make_feed()
res = {}
for label, ms in (("pure phases", False), ("ideal alloy", True)):
    res[label] = run_ladder(feed, T_start=3200.0, dT=25.0, metal_solution=ms)

t50 = pd.DataFrame({k: r.condensation_temperature() for k, r in res.items()})
t50.to_csv(RESULTS / "alloy_T50.csv")
rec = {k: r.recovery_table() for k, r in res.items()}
pd.concat(rec, axis=1).to_csv(RESULTS / "alloy_recovery.csv")

# where does gold go, and how rich is the metal it condenses with?
for label, r in res.items():
    grams = r.band_table()
    band = rec[label].loc["Au"].idxmax()
    sp = r.species.copy()
    sp["band"] = sp["T"].map(r.band_of)
    metal = sp[sp.species.str.contains(r"\(L\)|\(cr\)|\(a\)|\(c\)|\(d\)") &
               ~sp.species.str.contains("O|C\\(|CL|F|S\\(|N")]
    record(f"alloy[{label}]_Au_band", band)
    record(f"alloy[{label}]_Au_share", float(rec[label].loc["Au", band]))
    for el in ("Fe", "Ni", "Cu", "Au", "Pd", "Zn", "Pb", "Cd", "Hg"):
        if el in rec[label].index:
            record(f"alloy[{label}]_{el}_share_in_Au_band", float(rec[label].loc[el].get(band, 0.0)))

Tg_alloy = None
for T in np.arange(3400, 2500, -25.0):
    eq = equilibrate(feed.element_moles, float(T), metal_solution=True)
    if sum(eq.condensed.values()) > 1e-6 * sum(feed.element_moles.values()):
        Tg_alloy = float(T + 25.0)
        break
record("alloy_all_gas_T_1atm", Tg_alloy)

fig, ax = plt.subplots(figsize=(6.0, 3.6))
d = t50.dropna(how="all").sort_values("pure phases", ascending=False)
y = np.arange(len(d))
ax.scatter(d["pure phases"], y, s=16, color="#B0B0B0", label="pure phases", zorder=3)
ax.scatter(d["ideal alloy"], y, s=16, color="#1F4E9E", label="ideal liquid-metal alloy", zorder=3)
for i, (el, r) in enumerate(d.iterrows()):
    ax.plot([r["pure phases"], r["ideal alloy"]], [i, i], color=COLORS[CLASS.get(el, "other")], lw=1)
ax.set_yticks(y)
ax.set_yticklabels(d.index, fontsize=7)
ax.invert_yaxis()
ax.invert_xaxis()
ax.set_xlabel("Temperature at which 50% has condensed (K)")
ax.set_title("Effect of alloying on the condensation ladder", fontsize=9)
ax.legend(fontsize=7, frameon=False, loc="lower left")
save(fig, "fig_alloy")
print(t50.round(0).to_string())
for k in rec:
    b = rec[k].loc["Au"].idxmax()
    print(k, "Au band", b, (rec[k][b] * 100).round(1).loc[["Fe", "Ni", "Cu", "Au", "Pd", "Zn", "Pb", "Cd", "Hg"]].to_dict())
print("all-gas T with alloy:", Tg_alloy)
