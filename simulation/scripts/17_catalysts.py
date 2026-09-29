"""Experiment 17 - What a catalyst could and could not do in the PARAMANU process.

(a) Survival: how long a catalyst particle lasts in the hot zone. A metal
    surface evaporates at the Hertz-Knudsen rate
        J = alpha p_sat(T) sqrt(M / (2 pi R T))        [kg m^-2 s^-1]
    so a sphere of radius r and density rho disappears in t = rho r / J
    (alpha = 1, the usual value for clean metals). p_sat comes from the same
    NASA / Burcat data as the rest of the model.
(b) Need: the Damkohler number Da = residence time / reaction time of the
    slowest molecule (CF4, Section 7). A catalyst only shortens the reaction
    time; when Da >> 1 the reaction already completes, and the outcome (the
    equilibrium, fixed by Result 2 and unchanged by any catalyst) is the same.
(c) The same check at the cold end, where catalysts do matter.

    python 17_catalysts.py
"""
import _common  # noqa: F401
import math

import cantera as ct
import pandas as pd

from paramanu_sim.plotting import RESULTS, record
from paramanu_sim.thermo import load
from paramanu_sim import trace_thermo as tt

R = 8.314462618
T_HOT = 2890.0
th = load()
trace = {s.name: s for s in tt.load_trace_thermo("central")}


def psat_major(el: str, liquid: str, T: float) -> float:
    th.gas.TP = T, ct.one_atm
    g_gas = th.gas.standard_gibbs_RT[th.gas.species_index(el)]
    ph = next(p for p in th.condensed if p.species_names[0] == liquid)
    ph.TP = T, ct.one_atm
    return math.exp(ph.standard_gibbs_RT[0] - g_gas) * 101325.0


def psat_trace(el: str, T: float) -> float:
    return math.exp(trace[f"{el}(L)"].g_RT(T) - trace[el].g_RT(T)) * 101325.0


CATALYSTS = {   # element: (molar mass kg/mol, liquid density kg/m3, p_sat function)
    "Ni": (0.058693, 7810.0, lambda T: psat_major("Ni", "Ni(L)", T)),
    "Fe": (0.055845, 6980.0, lambda T: psat_major("Fe", "Fe(L)", T)),
    "Pt": (0.195080, 19770.0, lambda T: psat_trace("Pt", T)),
    "Pd": (0.106420, 10380.0, lambda T: psat_trace("Pd", T)),
}
rows = []
for el, (M, rho, ps) in CATALYSTS.items():
    p = ps(T_HOT)
    J = p * math.sqrt(M / (2 * math.pi * R * T_HOT))
    for r, label in ((5e-9, "5 nm particle"), (1e-3, "1 mm pellet")):
        rows.append({"catalyst": el, "size": label, "p_sat_Pa": p, "flux_kg_m2_s": J,
                     "lifetime_s": rho * r / J})
surv = pd.DataFrame(rows)
surv.to_csv(RESULTS / "catalyst_survival.csv", index=False)
record("catalyst_lifetime_s_2890K", {f"{r.catalyst} {r.size}": r.lifetime_s for r in surv.itertuples()})

# (b) Damkohler numbers in the hot zone: CF4 from Modica & Sillers (1968)
kB = 1.380649e-23


def k_cf4(T):
    M = 101325.0 / (kB * T) * 1e-6
    return 0.339 * (T / 298) ** -4.64 * math.exp(-512200 / (R * T)) * M


hot = pd.DataFrame([{"T_K": T, "tau_CF4_s": 1 / k_cf4(T), "Da_25ms": 0.025 * k_cf4(T)}
                    for T in (2890.0, 2600.0, 2400.0, 2200.0)])
hot.to_csv(RESULTS / "catalyst_damkohler_hot.csv", index=False)
record("catalyst_damkohler_CF4", hot.set_index("T_K").Da_25ms.to_dict())

# (d) A reagent, not a catalyst: carbon lowers the temperature at which silica vaporizes.
#     SiO2(l) = SiO + 1/2 O2 (closed: p_O2 = p_SiO / 2)  ->  K1 = p_SiO^1.5 / sqrt(2)
#     SiO2(l) + C(gr) = SiO + CO (p_CO = p_SiO)          ->  K2 = p_SiO^2
gas = ct.Solution(thermo="ideal-gas", species=[s for s in ct.Species.list_from_file("nasa_gas.yaml")
                                               if s.name in ("SiO", "O2", "CO")])
cond = {s.name: s for s in ct.Species.list_from_file("nasa_condensed.yaml") if s.name in ("SiO2(L)", "C(gr)")}


def g(name, T):
    if name in cond:
        ph = ct.Solution(thermo="fixed-stoichiometry", species=[cond[name]])
        ph.TP = T, ct.one_atm
        return float(ph.standard_gibbs_RT[0])
    gas.TP = T, ct.one_atm
    return float(gas.standard_gibbs_RT[gas.species_index(name)])


def p_sio(T, carbon):
    if carbon:
        lnK = g("SiO2(L)", T) + g("C(gr)", T) - g("SiO", T) - g("CO", T)
        return math.exp(lnK / 2.0)
    lnK = g("SiO2(L)", T) - g("SiO", T) - 0.5 * g("O2", T)
    return (math.sqrt(2.0) * math.exp(lnK)) ** (2.0 / 3.0)


def t_for(p_atm, carbon):
    lo, hi = 1200.0, 4000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if p_sio(mid, carbon) < p_atm else (lo, mid)
    return 0.5 * (lo + hi)


sio = pd.DataFrame([{"p_SiO_atm": p, "T_with_carbon_K": t_for(p, True), "T_silica_alone_K": t_for(p, False)}
                    for p in (1e-3, 0.1, 0.5)])
sio.to_csv(RESULTS / "catalyst_carbothermic_sio.csv", index=False)
record("carbothermic_sio_T_K", sio.round({"T_with_carbon_K": 0, "T_silica_alone_K": 0}).to_dict(orient="records"))

print(surv.to_string(index=False, float_format="%.3g"))
print(sio.round(0).to_string(index=False))
print(hot.to_string(index=False, float_format="%.3g"))
