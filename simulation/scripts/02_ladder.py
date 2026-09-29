"""Experiment 2 - The condensation ladder of the default heap at 1 atm.

Tests the paper's central claims: (a) elements condense in separable bands,
(b) precious metals are concentrated into a small band, (c) toxic volatile
metals end up away from the precious metals.
"""
import _common  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import SIMULATED_BANDS as SIM_BANDS, run_ladder
from paramanu_sim.equilibrium import composition
from paramanu_sim.plotting import CLASS, COLORS, RESULTS, record, save
from paramanu_sim.thermo import ATOMIC_MASS, load


feed = make_feed()
res = run_ladder(feed, dT=25.0, bands=SIM_BANDS)
res.steps.to_csv(RESULTS / "ladder_steps.csv", index=False)
res.species.to_csv(RESULTS / "ladder_species.csv", index=False)
t10, t50, t90 = (res.condensation_temperature(s) for s in (0.1, 0.5, 0.9))
tt = pd.DataFrame({"T10": t10, "T50": t50, "T90": t90}).sort_values("T50", ascending=False)
tt.to_csv(RESULTS / "ladder_condensation_T.csv")
grams = res.band_table()
rec = res.recovery_table()
grams.to_csv(RESULTS / "ladder_band_grams.csv")
rec.to_csv(RESULTS / "ladder_band_recovery.csv")

# Headline numbers
au_band = rec.loc["Au"].idxmax()
feed_ppm = feed.trace_grams["Au"] / (feed.dry_kg * 1000.0) * 1e6
band_ppm = grams.loc["Au", au_band] / grams[au_band].sum() * 1e6
record("ladder_Au_band", au_band)
record("ladder_Au_share_in_band", float(rec.loc["Au", au_band]))
record("ladder_Au_feed_ppm", float(feed_ppm))
record("ladder_Au_band_ppm", float(band_ppm))
record("ladder_Au_enrichment", float(band_ppm / feed_ppm))
record("ladder_band_mass_kg", {b: float(grams[b].sum() / 1000) for b in grams.columns})

# A collector separates liquid metal from oxide/carbide slag by density, as in
# any smelter. Metal mass per band = condensed pure metallic elements.
th = load()
sp = res.species.copy()
sp["band"] = sp["T"].map(res.band_of)
def _metal_kg(row):
    comp = composition(th, row.species)
    if len(comp) == 1 and "C" not in comp and not {"O", "H", "N", "S", "F", "Cl", "P"} & set(comp):
        el = next(iter(comp))
        return row.moles * ATOMIC_MASS[el] / 1000.0
    return 0.0
sp["metal_kg"] = sp.apply(_metal_kg, axis=1)
metal_kg = sp.groupby("band")["metal_kg"].sum()
metal_kg.to_csv(RESULTS / "ladder_band_metal_kg.csv")
au_metal_ppm = grams.loc["Au", au_band] / (metal_kg[au_band] * 1000.0) * 1e6
record("ladder_band_metal_kg", {b: float(v) for b, v in metal_kg.items()})
record("ladder_Au_ppm_in_band_metal", float(au_metal_ppm))
record("ladder_Au_enrichment_in_metal", float(au_metal_ppm / feed_ppm))
for el in ("Hg", "Cd", "Zn", "Pb"):
    record(f"ladder_{el}_share_in_Au_band", float(rec.loc[el].get(au_band, 0.0)))
    record(f"ladder_{el}_left_in_gas", float(rec.loc[el].get("gas", 0.0)))
record("ladder_T50_K", {k: (None if np.isnan(v) else float(v)) for k, v in t50.items()})
record("ladder_first_condensation_K", float(res.species["T"].max()))

# Figure: condensation temperatures (10-50-90 %) by element
tt = tt.dropna(subset=["T50"])
fig, ax = plt.subplots(figsize=(6.3, 4.6))
y = np.arange(len(tt))
for i, (el, r) in enumerate(tt.iterrows()):
    c = COLORS[CLASS.get(el, "other")]
    ax.plot([r.T90 if not np.isnan(r.T90) else 300, r.T10], [i, i], color=c, lw=2.2, alpha=0.6)
    ax.plot(r.T50, i, "o", color=c, ms=4.5)
for name, lower in SIM_BANDS:
    ax.axvline(lower, color="0.75", lw=0.8, ls="--")
    ax.text(lower - 15, -0.9, f"band {name}", fontsize=7, color="0.4", ha="right")
ax.set_yticks(y)
ax.set_yticklabels(tt.index, fontsize=7.5)
ax.invert_yaxis()
ax.invert_xaxis()
ax.set_xlabel("Temperature (K) - the gas cools from left to right")
ax.set_title("Simulated condensation of the plasma heap (1 atm): 10-50-90% condensed", fontsize=9, pad=14)
handles = [plt.Line2D([], [], color=COLORS[k], marker="o", lw=2, label=k) for k in
           ("precious", "bulk", "refractory", "toxic", "light")]
ax.legend(handles=handles, fontsize=7, loc="lower left", frameon=False)
save(fig, "fig_ladder_simulated")

# Figure: where each element goes (share per band)
order = [e for e in tt.index if e in rec.index] + [e for e in rec.index if e not in tt.index]
fig, ax = plt.subplots(figsize=(6.3, 4.2))
im = ax.imshow(rec.loc[order].T.values * 100, aspect="auto", cmap="Blues", vmin=0, vmax=100)
ax.set_xticks(range(len(order)))
ax.set_xticklabels(order, fontsize=7, rotation=90)
ax.set_yticks(range(len(rec.columns)))
ax.set_yticklabels([f"Band {c}" if c != "gas" else "gas" for c in rec.columns], fontsize=8)
fig.colorbar(im, ax=ax, label="% of element collected", shrink=0.8)
ax.set_title("Where each element is collected (simulated bands)", fontsize=9)
save(fig, "fig_ladder_recovery")

print(tt.round(0).to_string())
print((rec * 100).round(1).to_string())
print("Au band", au_band, "feed ppm", round(feed_ppm, 3), "band ppm", round(band_ppm, 2))
print("band mass kg", (grams.sum() / 1000).round(2).to_dict())
print("band metal kg", metal_kg.round(2).to_dict(), "Au ppm in band metal", round(au_metal_ppm, 1))
