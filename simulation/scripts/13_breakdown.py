"""Experiment 13 - How complex waste is broken down, and why its complexity does not matter.

Result 7 (paper): at fixed T and P the equilibrium depends on the feed only
through its element totals b, not on the molecules the atoms arrived in.

(a) Three very different starting mixtures with IDENTICAL element totals -
    bare atoms; "hard" molecules (aromatics, PFAS end-products, chlorinated
    solvents, phosgene); and monomer-like molecules - are equilibrated by
    Cantera's own solver (independent of ours) and by the PARAMANU solver.
    All four must give the same state.
(b) What is left of complex molecules at equilibrium in the real heap (the
    default feed, all phases allowed), from 1,000 K to the all-gas temperature.
(c) How long a silica grain takes to heat and vaporize in hot gas, against its
    diameter (paramanu_sim/particle.py): the time grows as the square of the size.

Run:  python 13_breakdown.py
"""
import _common  # noqa: F401

import cantera as ct
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import nnls

from paramanu_sim.equilibrium import equilibrate
from paramanu_sim.plotting import RESULTS, record, save
from paramanu_sim.thermo import load

ELEMENTS = ["C", "H", "O", "N", "Cl", "F", "Ar"]
ct.suppress_thermo_warnings()
species = [s for s in ct.Species.list_from_file("nasa_gas.yaml")
           if set(s.composition) <= set(ELEMENTS) and not s.name.endswith(("+", "-"))
           and "E" not in s.composition]
gas = ct.Solution(thermo="ideal-gas", species=species)

# "Hard" molecules standing in for plastics, pharmaceuticals, PFAS and medical waste (mol).
HARD = {"C10H8,naphthale": 1.0, "C12H10,bipheny": 1.0, "C6H5OH,phenol": 2.0, "CF4": 0.5,
        "C2F4": 0.5, "CH3CL": 1.0, "CCL4": 0.1, "COCL2": 0.1, "HCN": 0.5, "C2H5OH": 1.0,
        "NH3": 0.3, "H2O": 30.0, "AR": 5.0}
# A different molecular basis with the same atoms (solved to match the element totals).
MONOMER_BASIS = ["C2H4", "C3H6,propylene", "C2HCL", "CHF3", "C2N2", "CO2", "H2", "H2O", "HCL", "AR", "O2"]
HARD_NAMES = [k for k in HARD if k not in ("H2O", "AR", "NH3")]


def element_vector(mix):
    b = np.zeros(len(ELEMENTS))
    for name, n in mix.items():
        comp = gas.species(name).composition
        b += n * np.array([comp.get(e, 0.0) for e in ELEMENTS])
    return b


b = element_vector(HARD)
A = np.array([[gas.species(s).composition.get(e, 0.0) for s in MONOMER_BASIS] for e in ELEMENTS])
x, resid = nnls(A, b)
MONOMERS = {s: v for s, v in zip(MONOMER_BASIS, x) if v > 0}
ATOMS = {{"C": "C", "H": "H", "O": "O", "N": "N", "Cl": "CL", "F": "F", "Ar": "AR"}[e]: v
         for e, v in zip(ELEMENTS, b)}
starts = {"atoms": ATOMS, "hard molecules": HARD, "monomers": MONOMERS}
assert resid < 1e-9 and all(np.allclose(element_vector(m), b) for m in starts.values())

rows, compare = [], []
th = load(tuple(ELEMENTS))
for T in (1000.0, 1500.0, 2000.0, 2500.0, 2890.0):
    finals = {}
    for label, mix in starts.items():
        gas.TPX = T, ct.one_atm, {k: v for k, v in mix.items()}
        gas.equilibrate("TP")
        finals[label] = pd.Series(gas.X, index=gas.species_names)
    eq = equilibrate(dict(zip(ELEMENTS, b)), T, ct.one_atm, th, allow_condensed=False)
    ntot = sum(eq.gas.values())
    ours = pd.Series({k: v / ntot for k, v in eq.gas.items()}).reindex(gas.species_names).fillna(0.0)
    finals["PARAMANU solver"] = ours
    ref = finals["atoms"]
    major = ref > 1e-6
    for label, x_ in finals.items():
        compare.append({"T": T, "start": label,
                        "max_rel_diff_major": float((abs(x_[major] - ref[major]) / ref[major]).max())})

# (b) the real heap: default feed, full element set, condensed phases allowed
from paramanu_sim.feed import make_feed  # noqa: E402
feed = make_feed()
th_all = load()
for T in (1000.0, 1500.0, 2000.0, 2500.0, 2890.0):
    eq = equilibrate(feed.element_moles, T, ct.one_atm, th_all)
    # Exact mole fraction of EVERY gas species from the element potentials
    # (x_k = exp(a_k . lambda - g_k - ln P), Result 2); the solver itself floors
    # species below ~1e-14, which would overstate the rarest molecules.
    th_all.gas.TP = T, ct.one_atm
    g0 = th_all.gas.standard_gibbs_RT
    lam = eq.potentials
    xg = pd.Series({n: np.exp(sum(c * lam[e] for e, c in th_all.gas.species(n).composition.items())
                              - g0[k])
                    for k, n in enumerate(th_all.gas.species_names)
                    if set(th_all.gas.species(n).composition) <= set(lam)})
    for name in HARD_NAMES + ["CH4", "C6H6", "C2H2,acetylene"]:
        rows.append({"T": T, "species": name, "mole_fraction": float(xg.get(name, 0.0))})
    atoms = {n: sum(th_all.gas.species(n).composition.values()) for n in xg.index}
    big = xg[[n for n in xg.index if atoms[n] >= 6]]
    rows.append({"T": T, "species": "largest molecule with >= 6 atoms",
                 "mole_fraction": float(big.max()) if len(big) else 0.0,
                 "which": big.idxmax() if len(big) else ""})

cmp_df = pd.DataFrame(compare)
res = pd.DataFrame(rows)
cmp_df.to_csv(RESULTS / "breakdown_start_independence.csv", index=False)
res.to_csv(RESULTS / "breakdown_residual_molecules.csv", index=False)
record("breakdown_max_rel_diff_between_starts", float(cmp_df.max_rel_diff_major.max()))
hot = res[res["T"] == 2890.0].set_index("species")["mole_fraction"]
record("breakdown_largest_6atom_fraction_2890K", float(hot["largest molecule with >= 6 atoms"]))
record("breakdown_fraction_2890K", {k.split(",")[0]: float(hot[k]) for k in HARD_NAMES})

# (c) mineral grains: time to heat and vaporize silica vs grain size (particle.py)
from paramanu_sim import particle  # noqa: E402
d_um = np.array([2, 5, 10, 20, 50, 100, 200])
prow = []
for Tg in (3500.0, 5000.0, 8000.0):
    for d in d_um:
        prow.append({"T_gas": Tg, "d_um": d, "t_ms": particle.vaporization_time(d * 1e-6, Tg) * 1e3})
    record(f"particle_max_diameter_um_T{int(Tg)}", {"10ms": particle.max_diameter(0.010, Tg) * 1e6,
                                                    "25ms": particle.max_diameter(0.025, Tg) * 1e6})
pdf = pd.DataFrame(prow)
pdf.to_csv(RESULTS / "breakdown_particle_times.csv", index=False)
dh, L = particle.silica_enthalpies()
record("silica_heat_and_vaporize_MJ_per_kg", {"heat": dh / 1e6, "vaporize": L / 1e6})

fig, (ax, ax2) = plt.subplots(1, 2, figsize=(6.8, 2.9))
for name in ["C10H8,naphthale", "C12H10,bipheny", "C6H5OH,phenol", "CF4", "CCL4", "COCL2", "CH3CL", "C6H6"]:
    s = res[res.species == name]
    ax.semilogy(s["T"], s.mole_fraction.clip(lower=1e-40), marker="o", ms=3,
                label=name.split(",")[0].replace("CL", "Cl"))
ax.set_ylim(1e-40, 1)
ax.set_xlabel("Temperature (K)")
ax.set_ylabel("Equilibrium mole fraction")
ax.set_title("Complex molecules left at equilibrium", fontsize=8.5)
ax.legend(fontsize=6, frameon=False, ncol=2)
for Tg, g in pdf.groupby("T_gas"):
    ax2.loglog(g.d_um, g.t_ms, marker="o", ms=3, label=f"gas at {Tg:.0f} K (lower bound)")
ax2.axhspan(10, 25, color="0.85", label="hot-zone residence 10-25 ms")
ax2.set_xlabel("Silica grain diameter (um)")
ax2.set_ylabel("Time to vaporize (ms)")
ax2.set_title("Mineral grains: time grows as d^2", fontsize=8.5)
ax2.legend(fontsize=5.5, frameon=False)
fig.tight_layout()
save(fig, "fig_breakdown")

print("Same state from every start (max relative difference of species above 1 ppm):")
print(cmp_df.pivot(index="T", columns="start", values="max_rel_diff_major").to_string(float_format="%.1e"))
print("\nMole fractions of the starting 'hard' molecules at equilibrium:")
print(res.pivot(index="species", columns="T", values="mole_fraction").to_string(float_format="%.1e"))
