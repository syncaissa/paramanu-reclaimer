"""Experiment 10 - One-at-a-time sensitivity (tornado) of the headline results."""
import _common  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim.energy import all_gas_temperature, energy_curve
from paramanu_sim.feed import DEFAULT_MASSES, DEFAULT_TRACES_PPM, make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import RESULTS, record, save


def outputs(masses=None, traces=None, P=101325.0, gamma=1.0):
    f = make_feed(masses or DEFAULT_MASSES, traces_ppm=traces or DEFAULT_TRACES_PPM)
    Tg = all_gas_temperature(f, P)
    e = energy_curve(f, [Tg], P).MWh.iloc[0]
    r = run_ladder(f, P=P, T_start=3100.0, dT=50.0, gamma=gamma)
    rec = r.recovery_table()
    return {"all_gas_T": Tg, "MWh_per_t": e, "Au_main_band_share": float(rec.loc["Au"].max()),
            "Hg_left_in_gas": float(rec.loc["Hg"].get("gas", 0.0))}


base = outputs()
cases = []
for comp in ("fines", "plastics", "paper", "glass"):
    for f in (0.8, 1.2):
        m = dict(DEFAULT_MASSES)
        m[comp] *= f
        cases.append((f"{comp} x{f}", outputs(masses=m)))
for f in (0.5, 2.0):
    cases.append((f"traces x{f}", outputs(traces={k: v * f for k, v in DEFAULT_TRACES_PPM.items()})))
for P in (0.5, 2.0):
    cases.append((f"pressure {P} atm", outputs(P=P * 101325.0)))
for g in (0.3, 3.0):
    cases.append((f"trace activity {g}", outputs(gamma=g)))
rows = [{"case": "base", **base}] + [{"case": c, **o} for c, o in cases]
df = pd.DataFrame(rows)
df.to_csv(RESULTS / "sensitivity.csv", index=False)
record("sensitivity_base", base)

fig, axes = plt.subplots(1, 3, figsize=(7.0, 3.2), sharey=True)
for ax, col, lab in zip(axes, ("MWh_per_t", "Au_main_band_share", "Hg_left_in_gas"),
                        ("Energy (MWh/t)", "Au in main band", "Hg left in gas")):
    d = df[df.case != "base"].copy()
    ax.barh(d.case, d[col] - base[col], color=np.where(d[col] >= base[col], "#1F4E9E", "#C2185B"))
    ax.axvline(0, color="0.3", lw=0.8)
    ax.set_title(f"{lab}\n(base {base[col]:.2f})", fontsize=8)
    ax.tick_params(labelsize=7)
fig.suptitle("Sensitivity: change from the base case", fontsize=9)
fig.tight_layout()
save(fig, "fig_sensitivity")
print(df.round(3).to_string(index=False))
