"""Experiment 7 - Mathematical results checked against the full simulation.

Result 3  onset of condensation of a dilute element (closed form vs simulation)
Result 4  relative volatility and Fenske minimum stages for key pairs
Result 6  minimum work of separation vs the vaporization energy
"""
import _common  # noqa: F401
import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim import theory
from paramanu_sim.energy import energy_curve
from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import RESULTS, record, save

feed = make_feed()

# ---- Result 3: onset temperature of elements condensing as pure metals ----
lad = run_ladder(feed, T_start=3200.0, dT=10.0)
gas_mol = lad.duties.set_index("T")["gas_mol"]
rows = []
for el in ("Fe", "Cu", "Ni", "Pb", "Zn"):
    n0 = feed.element_moles[el]
    st = lad.steps[lad.steps.element == el].sort_values("T", ascending=False)
    # simulated onset: first step with any condensation of the element as pure metal
    sp = lad.species[lad.species.species.str.match(rf"^{el}\(|^{el.upper()}\(")]
    if sp.empty:
        continue
    T_sim = float(sp["T"].max())
    y = n0 / float(gas_mol.loc[gas_mol.index >= T_sim - 1e-9].iloc[-1])
    T_exact = theory.condensation_onset(el, y)
    tb = theory.boiling_point(el)
    dh = theory.enthalpy_of_vaporization(el, tb)
    T_cf = theory.condensation_onset_closed_form(tb, dh, y)
    rows.append({"element": el, "gas_mole_fraction": y, "T_boil_K": tb, "dH_vap_kJ": dh / 1000,
                 "onset_closed_form_K": T_cf, "onset_exact_K": T_exact, "onset_simulated_K": T_sim})
onset = pd.DataFrame(rows)
onset.to_csv(RESULTS / "theory_condensation_onset.csv", index=False)
record("theory_onset_max_abs_diff_K", float((onset.onset_closed_form_K - onset.onset_simulated_K).abs().max()))

# ---- Result 4: relative volatility and minimum stages ----
pairs = [("Zn", "Fe", 1500), ("Mg", "Fe", 1600), ("Hg", "Zn", 700), ("Pb", "Cu", 1800), ("Ag", "Au", 2000),
         ("Cu", "Ni", 2200), ("Cd", "Zn", 900), ("Sn", "Cu", 2200), ("Au", "Fe", 2500), ("Co", "Ni", 2600),
         ("Pd", "Fe", 2600)]
vol = []
for a, b, T in pairs:
    al = theory.relative_volatility(a, b, T)
    lo, hi = (a, b) if al >= 1 else (b, a)
    al = max(al, 1 / al)
    vol.append({"light": lo, "heavy": hi, "T_K": T, "alpha": al,
                "N_min_99": theory.fenske_min_stages(al, 0.99, 0.99),
                "N_min_999": theory.fenske_min_stages(al, 0.999, 0.999),
                "single_stage_light_left_when_99pct_heavy_condensed":
                    1 - theory.rayleigh_single_stage(al, 0.99)})
vol = pd.DataFrame(vol)
vol.to_csv(RESULTS / "theory_relative_volatility.csv", index=False)
record("theory_volatility", vol.round(4).to_dict(orient="records"))

# ---- Result 6: minimum work of separation ----
atoms = dict(feed.element_moles)
atoms.update({e: g / theory.load_vapor_data()[e].molar_mass for e, g in feed.trace_grams.items()})
w_min = theory.min_separation_work(atoms)
e_gas = energy_curve(feed, [2890.0]).MWh.iloc[0] * 3.6e9
record("theory_min_separation_work_MWh", w_min / 3.6e9)
record("theory_min_work_share_of_vaporization", w_min / e_gas)

fig, ax = plt.subplots(figsize=(5.8, 3.0))
v = vol.sort_values("alpha", ascending=False)
ax.barh(range(len(v)), v.N_min_99.clip(upper=40), color=["#2E8B2E" if n <= 5 else "#E0A800" if n <= 10 else "#C2185B" for n in v.N_min_99])
ax.set_yticks(range(len(v)))
ax.set_yticklabels([f"{r.light} from {r.heavy}  (alpha = {r.alpha:.3g})" for r in v.itertuples()], fontsize=7.5)
ax.invert_yaxis()
for i, n in enumerate(v.N_min_99):
    ax.text(min(n, 40) + 0.5, i, f"{n:.1f}", va="center", fontsize=7)
ax.set_xlim(0, 46)
ax.set_xlabel("Minimum ideal stages for a 99%/99% split (Fenske)")
ax.set_title("Which pairs physics can separate, and at what cost", fontsize=9)
save(fig, "fig_fenske")
print(onset.round(1).to_string(index=False))
print(vol.round(3).to_string(index=False))
print(f"W_min = {w_min/3.6e9:.4f} MWh per wet tonne = {100*w_min/e_gas:.2f}% of the all-gas energy")
