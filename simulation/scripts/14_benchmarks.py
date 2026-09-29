"""Experiment 14 - The code against published measurements it was not tuned on.

Each case sets up the PARAMANU solver with the inputs documented in the paper
and compares the prediction with what was measured. The fairness of each
comparison (how close the experiment is to equilibrium) is stated with it.

A. Vapor pressures of Pb and Sn, 800-1300 C, against the values used by the
   vacuum-refining literature: Jia, Yang & Liu, Trans. Nonferrous Met. Soc.
   China 23 (2013) 1822, Table 4. A data-consistency check, not a blind test.
B. Carbothermic reduction of electric-arc-furnace dust with coke: Chang et al.,
   Materials 15 (2022) 2639, doi:10.3390/ma15072639 (CC-BY). Dust composition
   (their Table 3), coke analysis (their Tables 1-2), C/O = 0.16, 0.5, 0.8
   (fixed carbon over all oxygen of the dust), 1300 C, N2 at 3 L/min for 60 min.
   Measured with coke (sample ED-C): Zn removal 98.8% (C/O 0.8), 88.5% (0.5),
   about 50% (0.16); Fe metallization over 90% (0.8) falling to about 10% or
   less (0.16). Tests the waste-carries-its-own-reductant claim and zinc fuming.
C. Gold, silver, palladium and platinum between liquid iron and liquid copper
   (Yamaguchi et al., Mater. Trans. 47 (2006) 1864, Table 3): run by
   15_gold_copper.py once measured activity coefficients are in.
"""
import _common  # noqa: F401

import cantera as ct
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim.equilibrium import composition, equilibrate
from paramanu_sim.plotting import RESULTS, record, save
from paramanu_sim.thermo import load
from paramanu_sim import trace_thermo as tt

MW = {"ZnO": 81.38, "Fe3O4": 231.53, "CaO": 56.077, "MgO": 40.304, "SiO2": 60.084,
      "Al2O3": 101.961, "K2O": 94.196, "Cr2O3": 151.99, "PbO": 223.2, "S": 32.06,
      "P": 30.974, "Cl": 35.45, "Na2O": 61.979, "P2O5": 141.94, "Fe2O3": 159.69}
ATOMS = {"ZnO": {"Zn": 1, "O": 1}, "Fe3O4": {"Fe": 3, "O": 4}, "CaO": {"Ca": 1, "O": 1},
         "MgO": {"Mg": 1, "O": 1}, "SiO2": {"Si": 1, "O": 2}, "Al2O3": {"Al": 2, "O": 3},
         "K2O": {"K": 2, "O": 1}, "Cr2O3": {"Cr": 2, "O": 3}, "PbO": {"Pb": 1, "O": 1},
         "S": {"S": 1}, "P": {"P": 1}, "Cl": {"Cl": 1}, "Na2O": {"Na": 2, "O": 1},
         "P2O5": {"P": 2, "O": 5}, "Fe2O3": {"Fe": 2, "O": 3}}


def moles(grams: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    for comp, g in grams.items():
        for el, k in ATOMS[comp].items():
            out[el] = out.get(el, 0.0) + g / MW[comp] * k
    return out


# ------------------------------------------------------------------ case A
jia = pd.DataFrame({"T_C": [800, 900, 1000, 1100, 1200, 1300],
                    "Pb_Pa": [7.2, 42.3, 186.2, 656.8, 1942.5, 4983.47],
                    "Sn_Pa": [8.11e-5, 1.38e-3, 1.51e-2, 0.12, 0.68, 3.172]})
th = load()
sp = {s.name: s for s in tt.load_trace_thermo("central")}


def psat_pb(T):
    th.gas.TP = T, ct.one_atm
    g_gas = th.gas.standard_gibbs_RT[th.gas.species_index("Pb")]
    liq = next(ph for ph in th.condensed if ph.species_names[0] == "Pb(L)")
    liq.TP = T, ct.one_atm
    return np.exp(liq.standard_gibbs_RT[0] - g_gas) * 101325.0


def psat_sn(T):
    return np.exp(sp["Sn(L)"].g_RT(T) - sp["Sn"].g_RT(T)) * 101325.0


jia["Pb_model_Pa"] = [psat_pb(t + 273.15) for t in jia.T_C]
jia["Sn_model_Pa"] = [psat_sn(t + 273.15) for t in jia.T_C]
jia["Pb_ratio"] = jia.Pb_model_Pa / jia.Pb_Pa
jia["Sn_ratio"] = jia.Sn_model_Pa / jia.Sn_Pa
jia.to_csv(RESULTS / "benchmark_vapor_pressure.csv", index=False)
record("benchmark_vapor_pressure_ratio_range",
       {"Pb": [float(jia.Pb_ratio.min()), float(jia.Pb_ratio.max())],
        "Sn": [float(jia.Sn_ratio.min()), float(jia.Sn_ratio.max())]})

# ------------------------------------------------------------------ case B
DUST = {"ZnO": 32.5, "Fe3O4": 29.1, "CaO": 13.5, "MgO": 5.1, "SiO2": 4.3, "Al2O3": 0.5,
        "K2O": 2.5, "Cr2O3": 0.3, "PbO": 0.3, "S": 1.5, "P": 0.6, "Cl": 5.6}
# MnO2 (4.1%) is left out: Mn is not in the major-element set. Reducing it to MnO
# would consume 0.047 mol C per 100 g of dust, 4-19% of the carbon supplied.
COKE_ASH = {"CaO": 8.2, "MgO": 0.6, "Al2O3": 25.2, "SiO2": 56.3, "K2O": 0.7, "Na2O": 0.2,
            "P2O5": 0.6, "Fe2O3": 7.9}                      # % of the ash; MnO 0.3% left out
FIXED_C, ASH = 0.869, 0.141
N2_SWEEP = 3.0 * 60 / 24.465                                 # mol N2 through the furnace
PELLET_DUST_G = {0.16: 5.8 * 0.976, 0.5: 5.7 * 0.930, 0.8: 5.6 * 0.892}   # their Table 4
MEASURED = {0.8: (98.8, ">90"), 0.5: (88.5, None), 0.16: (50.0, "<=10")}

dust = moles(DUST)
O_dust = moles({k: v for k, v in DUST.items()})["O"]
rows = []
for co, (zn_meas, fe_meas) in MEASURED.items():
    nC = co * O_dust
    coke_g = nC * 12.011 / FIXED_C
    ash = moles({k: v / 100 * coke_g * ASH for k, v in COKE_ASH.items()})
    for label, n2 in (("sweep-equivalent N2", N2_SWEEP * 100 / PELLET_DUST_G[co]), ("closed, little N2", 1.0)):
        b = dict(dust)
        for el, v in ash.items():
            b[el] = b.get(el, 0.0) + v
        b["C"] = nC
        b["N"] = 2 * n2
        for T_C in (900, 1000, 1100, 1200, 1300):
            eq = equilibrate(b, T_C + 273.15, ct.one_atm, th)
            zn_gas = sum(n * composition(th, s).get("Zn", 0) for s, n in eq.gas.items())
            fe_met = sum(n for s, n in eq.condensed.items() if composition(th, s) == {"Fe": 1.0})
            rows.append({"C/O": co, "gas": label, "T_C": T_C,
                         "Zn_removal_pct": 100 * zn_gas / b["Zn"],
                         "Fe_metallization_pct": 100 * fe_met / b["Fe"],
                         "measured_Zn_removal_pct_1300C": zn_meas,
                         "measured_Fe_metallization_1300C": fe_meas})
eaf = pd.DataFrame(rows)
eaf.to_csv(RESULTS / "benchmark_eaf_dust.csv", index=False)
at1300 = eaf[eaf.T_C == 1300]
record("benchmark_eaf_dust_1300C", at1300[["C/O", "gas", "Zn_removal_pct", "Fe_metallization_pct"]]
       .round(1).to_dict(orient="records"))

fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.7))
ax = axes[0]
ax.semilogy(jia.T_C, jia.Pb_Pa, "o", color="k", label="Pb, Jia et al.")
ax.semilogy(jia.T_C, jia.Pb_model_Pa, "-", color="k", label="Pb, this model")
ax.semilogy(jia.T_C, jia.Sn_Pa, "s", color="#1F4E9E", label="Sn, Jia et al.")
ax.semilogy(jia.T_C, jia.Sn_model_Pa, "-", color="#1F4E9E", label="Sn, this model")
ax.set_xlabel("Temperature (C)")
ax.set_ylabel("Vapor pressure (Pa)")
ax.legend(fontsize=6, frameon=False)
ax = axes[1]
x = np.arange(3)
cos = [0.16, 0.5, 0.8]
sub = at1300[at1300.gas == "sweep-equivalent N2"].set_index("C/O")
sub2 = at1300[at1300.gas == "closed, little N2"].set_index("C/O")
ax.bar(x - 0.25, [MEASURED[c][0] for c in cos], 0.25, color="0.6", label="Zn removal, measured")
ax.bar(x, [sub.loc[c, "Zn_removal_pct"] for c in cos], 0.25, color="#C2185B", label="Zn removal, model (sweep)")
ax.bar(x + 0.25, [sub.loc[c, "Fe_metallization_pct"] for c in cos], 0.25, color="#2E8B2E",
       label="Fe metallized, model (sweep)")
ax.plot(x, [sub2.loc[c, "Zn_removal_pct"] for c in cos], "k_", ms=14, label="Zn removal, model (closed)")
ax.set_xticks(x, [f"C/O {c}" for c in cos])
ax.set_ylabel("% at 1300 C")
ax.set_ylim(0, 150)
ax.legend(fontsize=5.5, frameon=False, loc="upper left", ncol=2)
fig.tight_layout()
save(fig, "fig_benchmarks")

print(jia.round(4).to_string(index=False))
print(eaf.round(1).to_string(index=False))
