"""Experiment 8 - Hot-zone design: why the heap must be hot only briefly.

(a) Batch: radiation time constant tau = E/Q vs batch mass, pressure, wall T
    (Result 5: tau ~ m^(1/3) P^(2/3)).
(b) Continuous flow: radiation loss / torch power vs hot-zone residence time.
(c) Condenser heat duty per band, starting just above the all-gas temperature.
"""
import _common  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim import theory
from paramanu_sim.energy import DRYING_J_PER_KG, all_gas_temperature
from paramanu_sim.equilibrium import equilibrate
from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import RESULTS, record, save

feed = make_feed()
# Basis: one tonne of EXCAVATED material (the feed model's unit, before its 5.2%
# pre-treatment), the same basis as the energy, the bands and the plant throughput
# (1,000 t/day of excavated material) everywhere else in the paper.
EXCAVATED_KG = 1000.0
state = {}
for P_atm in (1.0, 10.0):
    P = P_atm * 101325.0
    Tg = all_gas_temperature(feed, P)
    eq = equilibrate(feed.element_moles, Tg, P)
    e_hot = eq.enthalpy - feed.formation_enthalpy_J          # J per wet tonne, excluding drying
    state[P_atm] = {"T": Tg, "e_per_kg": e_hot / EXCAVATED_KG, "mol_per_kg": sum(eq.gas.values()) / EXCAVATED_KG}

s1 = state[1.0]
record("design_hot_zone_basis", {"T_K": float(s1["T"]), "e_MJ_per_excavated_kg": s1["e_per_kg"] / 1e6,
                                 "gas_mol_per_excavated_kg": s1["mol_per_kg"],
                                 "gas_m3_per_s_1000tpd": 1e6 / 86400 * s1["mol_per_kg"] * 8.314462618 * s1["T"] / 101325.0,
                                 "torch_MW_no_loss_1000tpd_excluding_drying": 1e6 / 86400 * s1["e_per_kg"] / 1e6})
# (a) batch time constant
rows = []
for P_atm, s in state.items():
    for Tw in (600.0, 2000.0):
        for m in np.logspace(0, 4, 17):                           # 1 kg to 10 t of excavated material
            tau = theory.radiation_time_constant(s["e_per_kg"] * m, s["mol_per_kg"] * m, s["T"],
                                                 P_atm * 101325.0, 0.3, Tw)
            rows.append({"P_atm": P_atm, "T_wall": Tw, "batch_kg": m, "tau_s": tau})
batch = pd.DataFrame(rows)
batch.to_csv(RESULTS / "design_batch_time_constant.csv", index=False)
b1 = batch[(batch.P_atm == 1) & (batch.T_wall == 600)]
slope = np.polyfit(np.log(b1.batch_kg), np.log(b1.tau_s), 1)[0]
record("design_batch_tau_1t_1atm_s", float(np.interp(1000, b1.batch_kg, b1.tau_s)))
record("design_batch_tau_scaling_exponent", float(slope))

# (b) continuous hot zone
rows = []
for tpd in (10.0, 100.0, 1000.0):
    mdot = tpd * 1000.0 / 86400.0
    for P_atm, s in state.items():
        for tr in np.logspace(-3, 1, 41):
            f = theory.flow_loss_fraction(mdot, s["e_per_kg"], s["mol_per_kg"], s["T"], P_atm * 101325.0, tr)
            rows.append({"t_per_day": tpd, "P_atm": P_atm, "residence_s": tr, "loss_fraction": f,
                         "torch_MW": mdot * s["e_per_kg"] / 1e6})
flow = pd.DataFrame(rows)
flow.to_csv(RESULTS / "design_flow_loss.csv", index=False)
for tpd in (10.0, 100.0, 1000.0):
    sub = flow[(flow.t_per_day == tpd) & (flow.P_atm == 1.0)]
    for lim in (0.05, 0.10):
        ok = sub[sub.loss_fraction <= lim]
        record(f"design_flow_max_residence_s_{int(tpd)}tpd_loss{int(lim*100)}pct",
               float(ok.residence_s.max()) if len(ok) else 0.0)

# (c) condenser duties from just above the all-gas temperature
T0 = np.ceil(state[1.0]["T"] / 25.0) * 25.0 + 25.0
lad = run_ladder(feed, T_start=T0, dT=25.0)
duty = lad.band_duty_J() / 3.6e9                                  # MWh per wet tonne
duty_mw = duty * 1000 / 24                                         # MW at 1,000 t/day
duty_tab = pd.DataFrame({"MWh_per_t": duty, "MW_at_1000tpd": duty_mw})
duty_tab.to_csv(RESULTS / "design_condenser_duty.csv")
record("design_condenser_duty_MWh_per_t", {k: float(v) for k, v in duty.items()})
record("design_heat_above_2000K_share", float(duty[[b for b in ("A", "B") if b in duty]].sum() / duty.sum()))

fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.8))
ax = axes[0]
for (P_atm, Tw), g in batch.groupby(["P_atm", "T_wall"]):
    ax.loglog(g.batch_kg, g.tau_s, label=f"{P_atm:g} atm, walls {Tw:.0f} K")
ax.set_xlabel("Batch (kg of feed)")
ax.set_ylabel("tau = E / Q  (s)")
ax.set_title("Batch: time before walls radiate\nthe whole batch energy", fontsize=8.5)
ax.legend(fontsize=6.5, frameon=False)
ax = axes[1]
for tpd, g in flow[flow.P_atm == 1.0].groupby("t_per_day"):
    ax.loglog(g.residence_s, g.loss_fraction * 100, label=f"{tpd:g} t/day")
ax.axhline(10, color="0.6", ls="--", lw=0.8)
ax.set_xlabel("Hot-zone residence time (s)")
ax.set_ylabel("Radiation loss / torch power (%)")
ax.set_title("Continuous hot zone (1 atm)", fontsize=8.5)
ax.legend(fontsize=6.5, frameon=False)
fig.tight_layout()
save(fig, "fig_reactor_design")
print(pd.DataFrame(state).T)
print("tau scaling exponent", round(slope, 3))
print(duty_tab.round(3))
