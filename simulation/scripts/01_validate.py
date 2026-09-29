"""Experiment 1 - Validation: does the solver reproduce known physics?"""
import _common  # noqa: F401
import matplotlib.pyplot as plt
import pandas as pd

from paramanu_sim.plotting import RESULTS, save, record
from paramanu_sim.validation import boiling_point_table, gas_crosscheck

bp = boiling_point_table()
bp.to_csv(RESULTS / "validation_boiling_points.csv", index=False)
cross = pd.concat([gas_crosscheck({"C": 1, "H": 4, "O": 1.5, "N": 2, "Si": 0.3, "Fe": 0.1, "Cl": 0.05}, T)
                   .assign(T=T) for T in (1500.0, 2000.0, 3000.0, 4000.0)])
cross.to_csv(RESULTS / "validation_gas_crosscheck.csv", index=False)

record("validation_bp_max_abs_error_pct", float(bp.error_pct.abs().max()))
record("validation_bp_median_abs_error_pct", float(bp.error_pct.abs().median()))
record("validation_gas_max_rel_diff", float(cross.rel_diff.abs().max()))

fig, ax = plt.subplots(figsize=(3.4, 3.2))
ax.plot([500, 3800], [500, 3800], color="0.7", lw=1)
ax.scatter(bp.CRC_K, bp.model_K, s=18, color="#1F4E9E", zorder=3)
for _, r in bp.iterrows():
    ax.annotate(r.element, (r.CRC_K, r.model_K), fontsize=7, xytext=(3, -8), textcoords="offset points")
ax.set_xlabel("CRC Handbook boiling point (K)")
ax.set_ylabel("PARAMANU solver (K)")
ax.set_title("Pure-element boiling points at 1 atm", fontsize=9)
save(fig, "fig_validation")
print(bp.to_string(index=False))
print("gas cross-check max |rel diff|:", cross.rel_diff.abs().max())
