"""Experiment 5 - Sizing the sealed plasma chamber.

Vessel volume for a vaporized batch, radiative wall losses, heating time and
the ionization fraction of the plasma heap (Saha; GPU-accelerated grid when
CuPy and a GPU are available).
"""
import _common  # noqa: F401
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim.backend import gpu_available
from paramanu_sim.chamber import radiative_loss_w, saha_ionization, sphere_area_m2, vessel_volume_m3
from paramanu_sim.energy import all_gas_temperature, energy_curve
from paramanu_sim.equilibrium import equilibrate
from paramanu_sim.feed import make_feed
from paramanu_sim.plotting import RESULTS, record, save

ap = argparse.ArgumentParser()
ap.add_argument("--gpu", action="store_true", help="run the Saha grid on a GPU via CuPy")
ap.add_argument("--grid", type=int, default=400, help="Saha grid points per axis")
args = ap.parse_args()

feed = make_feed()
tonne_dry = feed.dry_kg
rows = []
for P_atm in (1.0, 10.0):
    P = P_atm * 101325.0
    Tg = all_gas_temperature(feed, P)
    eq = equilibrate(feed.element_moles, Tg, P)
    mol_per_kg = sum(eq.gas.values()) / tonne_dry
    mwh_per_kg = energy_curve(feed, [Tg], P).MWh.iloc[0] / tonne_dry
    for batch_kg in (10.0, 100.0, 1000.0):
        V = vessel_volume_m3(mol_per_kg * batch_kg, Tg, P)
        A = sphere_area_m2(V)
        for eps in (0.1, 0.3):
            q = radiative_loss_w(Tg, A, eps)
            e_batch = mwh_per_kg * batch_kg * 3.6e9
            rows.append({"P_atm": P_atm, "T_K": Tg, "batch_kg": batch_kg, "volume_m3": V,
                         "diameter_m": 2 * (3 * V / (4 * np.pi)) ** (1 / 3), "area_m2": A,
                         "emissivity": eps, "radiation_MW": q / 1e6,
                         "batch_energy_MWh": e_batch / 3.6e9,
                         "radiation_MWh_per_10min": q * 600 / 3.6e9})
df = pd.DataFrame(rows)
df.to_csv(RESULTS / "chamber_sizing.csv", index=False)
one = df[(df.P_atm == 1.0) & (df.batch_kg == 1000.0) & (df.emissivity == 0.3)].iloc[0]
ten = df[(df.P_atm == 10.0) & (df.batch_kg == 100.0) & (df.emissivity == 0.3)].iloc[0]
record("chamber_1t_1atm_volume_m3", float(one.volume_m3))
record("chamber_1t_1atm_radiation_MW", float(one.radiation_MW))
record("chamber_100kg_10atm_volume_m3", float(ten.volume_m3))
record("chamber_100kg_10atm_radiation_MW", float(ten.radiation_MW))

# Saha ionization grid
T = np.linspace(3000, 15000, args.grid)
Pg = np.logspace(-2, 1, args.grid) * 101325.0
TT, PP = np.meshgrid(T, Pg)
use_gpu = args.gpu and gpu_available()
xe = saha_ionization(feed.element_moles, TT, PP, use_gpu=use_gpu)
record("saha_backend", "cupy-gpu" if use_gpu else "numpy-cpu")
i1 = np.argmin(np.abs(Pg - 101325.0))
for Tq in (3000, 5000, 8000, 10000):
    record(f"saha_ionization_{Tq}K_1atm", float(np.interp(Tq, T, xe[i1])))
fig, ax = plt.subplots(figsize=(4.8, 3.2))
cs = ax.contourf(TT, PP / 101325.0, np.log10(np.maximum(xe, 1e-12)), levels=np.arange(-8, 0.5, 0.5), cmap="viridis")
ax.set_yscale("log")
ax.set_xlabel("Temperature (K)")
ax.set_ylabel("Pressure (atm)")
fig.colorbar(cs, ax=ax, label="log10 ionization fraction")
ax.set_title("Ionization of the plasma heap (Saha, upper bound)", fontsize=9)
save(fig, "fig_saha")
print(df.round(3).to_string(index=False))
print("backend:", "GPU" if use_gpu else "CPU", " x_e(1 atm):", {t: float(np.interp(t, T, xe[i1])) for t in (3000, 5000, 8000, 10000)})
