"""Experiment 4 - Energy envelope from thermodynamic data.

How hot must the sealed batch get before everything is gas, and how much
energy does that take, as a function of pressure and pre-treatment?
"""
import _common  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim.energy import J_PER_MWH, DRYING_J_PER_KG, all_gas_temperature, energy_curve
from paramanu_sim.equilibrium import equilibrate
from paramanu_sim.feed import make_feed
from paramanu_sim.plotting import RESULTS, record, save

rows = []
for pre in (0.0, 0.052, 0.15, 0.30):
    feed = make_feed(pretreat_fraction=pre)
    for P_atm in (0.1, 1.0, 10.0):
        P = P_atm * 101325.0
        Tg = all_gas_temperature(feed, P)
        eq = equilibrate(feed.element_moles, Tg, P)
        e = (eq.enthalpy - feed.formation_enthalpy_J + feed.moisture_kg * DRYING_J_PER_KG) / J_PER_MWH
        e5k = energy_curve(feed, [5000.0], P).MWh.iloc[0]
        rows.append({"pretreat": pre, "P_atm": P_atm, "dry_kg": feed.dry_kg, "all_gas_T": Tg,
                     "MWh_at_all_gas_T": e, "MWh_at_5000K": e5k, "gas_mol": sum(eq.gas.values())})
df = pd.DataFrame(rows)
df.to_csv(RESULTS / "energy_envelope.csv", index=False)
base = df[(df.pretreat == 0.052) & (df.P_atm == 1.0)].iloc[0]
record("energy_all_gas_T_1atm", float(base.all_gas_T))
record("energy_MWh_all_gas_1atm", float(base.MWh_at_all_gas_T))
record("energy_MWh_5000K_1atm", float(base.MWh_at_5000K))
record("energy_MW_per_1000tpd", float(base.MWh_at_all_gas_T * 1000 / 24))
record("energy_table", df.round(3).to_dict(orient="records"))

curve = energy_curve(make_feed(), np.arange(300, 6001, 100))
curve.to_csv(RESULTS / "energy_curve_1atm.csv", index=False)
fig, ax = plt.subplots(figsize=(5.6, 3.0))
ax.plot(curve["T"], curve["MWh"], color="#1F4E9E", lw=1.8, label="thermodynamic model (this work)")
ax.axhline(10.5, color="#C2185B", ls="--", lw=1, label="paper proxy estimate: full atomization, 5000 K")
ax.axvline(base.all_gas_T, color="0.6", ls=":", lw=1)
ax.text(base.all_gas_T + 40, 1.0, f"all gas at {base.all_gas_T:.0f} K", fontsize=7.5, color="0.35")
ax.set_xlabel("Batch temperature (K), 1 atm")
ax.set_ylabel("MWh per wet tonne (gross)")
ax.set_title("Energy to bring one wet tonne to equilibrium at temperature T", fontsize=9)
ax.legend(fontsize=7, frameon=False, loc="center right")
save(fig, "fig_energy_model")
print(df.round(2).to_string(index=False))
