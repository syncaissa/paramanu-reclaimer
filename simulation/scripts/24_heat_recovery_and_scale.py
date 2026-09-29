"""Experiment 24 - Practical answers to engineering objections (four quantified here; the fifth, slag, is in the paper).

(a) Heat recovery. The condenser stages release their heat at 400-2,600 K. No heat
    engine runs at 2,000 K, but none has to: the stages are built as the radiant
    water walls of a steam boiler, as the evaporative cooling systems and waste-heat
    boilers of electric-arc-furnace off-gas already do from about 1,700 C down to
    200 C (Gandt et al. 2016). The heat leaves as steam and drives a turbine.
    Assumptions: 60-70% of each stage's duty is captured as steam (EAF systems
    recover "up to 70%" of the off-gas energy), and a steam cycle converts it to
    electricity at 30-35%.
(b) Emissivity. The grey-gas estimate of Result 5 uses epsilon = 0.3; gas carrying
    condensing particles can approach 1. The hot-zone loss scales linearly with
    epsilon; the residence time that keeps it at 10% scales as epsilon^(-3/2).
    With boiler walls, the radiated heat is not lost but becomes steam.
(c) Scale-out. A 1,000 t/day plant can be built as N parallel modules. Smaller
    modules lose more to radiation (m_dot^(-1/3)), so each needs a shorter
    residence time for the same loss.
(d) Grinding. Only the mineral fraction must be fine; organics leave as gas in
    pre-heating. A cement vertical roller mill grinds raw meal for about 19.4 kWh/t
    (Japan Cement Association); Bond's law, W ~ 1/sqrt(P80), scales that from the
    usual raw-meal size (about 90 um) to 20 um by sqrt(90/20).
(e) Self-sufficiency with heat recovery, on the basis of script 23.

    python 24_heat_recovery_and_scale.py        (needs 08 and 23 to have run)
"""
import _common  # noqa: F401

import json
import math

import pandas as pd

from paramanu_sim import theory
from paramanu_sim.plotting import RESULTS, record

kn = json.loads((RESULTS / "key_numbers.json").read_text())
duty = kn["design_condenser_duty_MWh_per_t"]            # MWh per tonne excavated, by stage
basis = kn["design_hot_zone_basis"]
gross = float(kn["energy_MWh_all_gas_1atm"])
revenue = float(kn["self_sufficiency"]["revenue_per_t"])
T, e, nu = basis["T_K"], basis["e_MJ_per_excavated_kg"] * 1e6, basis["gas_mol_per_excavated_kg"]
P = 101325.0
MDOT = 1e6 / 86400.0                                    # kg/s for 1,000 t/day

# (a) heat recovery from the condenser stages as steam
stages = ["A", "B", "C", "D1", "D2", "E"]
stage_heat = sum(duty[s] for s in stages)
CAPTURE = (0.60, 0.70)
CYCLE = (0.30, 0.35)
steam_e = (stage_heat * CAPTURE[0] * CYCLE[0], stage_heat * CAPTURE[1] * CYCLE[1])   # MWh_e per tonne

# (b) emissivity: loss at 25 ms, residence time for 10% loss, wall flux
rows_eps = []
for eps in (0.3, 0.6, 1.0):
    loss25 = theory.flow_loss_fraction(MDOT, e, nu, T, P, 0.025, emissivity=eps)
    t10 = 0.025 * (0.10 / loss25) ** 1.5
    q = eps * theory.SIGMA * (T ** 4 - 600.0 ** 4) / 1e6
    rows_eps.append({"emissivity": eps, "loss_at_25ms": loss25, "residence_ms_for_10pct": t10 * 1e3,
                     "wall_flux_MW_m2": q})
eps_tab = pd.DataFrame(rows_eps)

# (c) scale-out into N modules
rows_mod = []
for n in (1, 2, 4, 10):
    m = MDOT / n
    for eps in (0.3, 1.0):
        loss25 = theory.flow_loss_fraction(m, e, nu, T, P, 0.025, emissivity=eps)
        t10 = 0.025 * (0.10 / loss25) ** 1.5
        rows_mod.append({"modules": n, "emissivity": eps, "t_per_day_each": 1000.0 / n,
                         "torch_MW_each_gross": basis["torch_MW_no_loss_1000tpd_excluding_drying"] / n,
                         "torch_MW_each_demonstrated": 2.3 * basis["torch_MW_no_loss_1000tpd_excluding_drying"] / n,
                         "residence_ms_for_10pct": t10 * 1e3})
mod_tab = pd.DataFrame(rows_mod)

# (d) grinding the dry residue (upper bound: all 711 kg per wet tonne)
DRY_KG = 711.0
VRM_KWH_T = 19.4
bond = math.sqrt(90.0 / 20.0)
grind_kwh = DRY_KG / 1000.0 * VRM_KWH_T * bond
grind_share = grind_kwh / 1000.0 / gross

# (e) self-sufficiency with heat recovery (fuel 0.13-0.6 MWh_e as in script 23; power at 5 c/kWh)
fuel_e = (0.126, 0.600)
rows_ss = []
for case, mult in (("gross enthalpy", 1.0), ("best demonstrated", 2.3)):
    need = gross * mult
    for label, own in (("low", fuel_e[0] + steam_e[0]), ("high", fuel_e[1] + steam_e[1])):
        buy = max(need - own, 0.0)
        rows_ss.append({"energy_case": case, "own_power": label, "MWh_needed": need, "MWh_own": own,
                        "MWh_to_buy": buy,
                        "coverage_at_0.05": min((own + revenue / 50.0) / need, 9.99),
                        "break_even_c_per_kWh": (revenue / (buy * 1000.0) * 100.0) if buy > 0 else float("inf")})
ss_tab = pd.DataFrame(rows_ss)

eps_tab.to_csv(RESULTS / "heat_recovery_emissivity.csv", index=False)
mod_tab.to_csv(RESULTS / "heat_recovery_modules.csv", index=False)
ss_tab.to_csv(RESULTS / "heat_recovery_self_sufficiency.csv", index=False)
record("heat_recovery", {
    "stage_heat_MWh_per_t": round(stage_heat, 3),
    "steam_electricity_MWh_per_t": [round(x, 3) for x in steam_e],
    "steam_share_of_gross": [round(x / gross, 3) for x in steam_e],
    "steam_MW_1000tpd": [round(x * 1000 / 24, 1) for x in steam_e],
    "emissivity": eps_tab.round(4).to_dict(orient="records"),
    "modules": mod_tab.round(3).to_dict(orient="records"),
    "grinding_kWh_per_t": round(grind_kwh, 1), "grinding_share_of_gross": round(grind_share, 4),
    "self_sufficiency": ss_tab.round(4).to_dict(orient="records"),
})
pd.set_option("display.width", 200)
print(f"condenser-stage heat A-E: {stage_heat:.3f} MWh/t; as electricity via steam: "
      f"{steam_e[0]:.2f}-{steam_e[1]:.2f} MWh/t ({steam_e[0]/gross:.0%}-{steam_e[1]/gross:.0%} of gross; "
      f"{steam_e[0]*1000/24:.0f}-{steam_e[1]*1000/24:.0f} MW at 1,000 t/day)")
print(eps_tab.round(3).to_string(index=False))
print(mod_tab.round(2).to_string(index=False))
print(f"grinding: {grind_kwh:.0f} kWh/t = {grind_share:.1%} of the gross enthalpy")
print(ss_tab.round(3).to_string(index=False))
