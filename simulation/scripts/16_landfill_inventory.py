"""Experiment 16 - What a whole city landfill holds, and what could be recovered.

For every element in the feed model (no radioactive elements are in it):
  theoretical = everything in the excavated material (no pre-treatment removed),
  practical   = the share the simulation collects in that element's recovery
                stream at 1 atm (its product band), times the recovery that
                established refining achieves for that stream (REFINING_YIELD,
                with sources), scaled to the reference landfill (LANDFILL_T).

Contents of Au, Pd and Pt are assumptions (no measurement in landfill fines
exists); every other metal content follows the feed model and its sources.

    python 16_landfill_inventory.py
"""
import _common  # noqa: F401

import pandas as pd

from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import run_ladder
from paramanu_sim.plotting import RESULTS, record
from paramanu_sim.thermo import ATOMIC_MASS

# Reference size: the median US municipal landfill, 2.33 million tonnes of waste in
# place (2,175 landfills; our calculation from the US EPA Landfill Methane Outreach
# Program database, September 2024; open sites 4.59 Mt, closed sites 1.00 Mt).
LANDFILL_T = 2_300_000
LB_PER_KG = 2.20462

# Product stream of each element: the band(s) whose material goes to recovery,
# and the form it is sold or stored in.
STREAM = {
    "Fe": ("B", "metal"), "Co": ("B", "metal"), "Pd": ("B", "metal"), "Pt": ("B", "metal"),
    "Au": ("BC", "metal"), "Cu": ("C", "metal"), "Ni": ("BC", "metal"), "Cr": ("C", "metal"),
    "Sn": ("BC", "metal"), "Sb": ("BC", "metal"), "Ga": ("BC", "metal"), "Ag": ("D", "metal"),
    "Bi": ("D", "metal"), "Pb": ("D", "metal"), "Zn": ("E", "metal"), "Cd": ("E", "CdS"),
    "In": ("DE", "metal"), "Mn": ("D", "oxide"), "W": ("A", "WC/oxide"), "Ti": ("A", "TiC/oxide"),
    "Nd": ("AB", "oxide"), "Al": ("B", "oxide"), "Ca": ("B", "oxide"), "Mg": ("C", "oxide"),
    "Si": ("ABC", "silica/glass"), "Na": ("D", "NaCl"), "K": ("D", "KCl"), "Cl": ("D", "salts"),
    "S": ("CD", "sulfate/sulfur"), "P": ("E", "phosphate"), "F": ("DE", "CaF2"), "Li": ("E", "Li2CO3"),
    "Hg": ("cold+gas", "HgS (trap)"), "H": ("cold+gas", "water, fuel gas"),
    "C": ("cold+gas+E", "fuel gas, carbon"), "N": ("gas", "N2"), "O": ("all", "in oxides, water"),
}
# Recovery of established refining for each stream (fraction). Filled from the
# literature cited in the paper; 1.0 where the product is the band itself.
PRECIOUS = 0.95   # gold "close to 100%" at an integrated smelter (Hagelueken & Corti,
                  # Gold Bull. 43 (2010) 209, p. 213); 95% taken as a conservative value
ASSUMED = 0.85    # metals without a published process yield (an assumption, stated in the paper)
REFINING_YIELD: dict[str, float] = {
    "Au": PRECIOUS, "Ag": PRECIOUS, "Pd": PRECIOUS, "Pt": PRECIOUS,
    "Zn": 0.92,   # plasma fuming of EAF dust, "about 92 %" (EU BREF Non-Ferrous Metals 2017, sec. 6.1.2.4.1)
    "Cu": 0.84,   # copper alloy scrap remelting, "70 % to 97 %" (same BREF, ch. 3): midpoint
    "Fe": 0.88,   # steel from scrap, 1,039-1,232 kg scrap per t steel (EU BREF Iron & Steel 2013, Table 8.1): midpoint
    **{m: ASSUMED for m in ("Ni", "Co", "Cr", "Sn", "Sb", "Pb", "Bi", "In", "Ga", "W", "Ti", "Mn", "Nd", "Cd")},
}

feed = make_feed(pretreat_fraction=0.0)
kg = {e: n * ATOMIC_MASS[e] / 1000.0 for e, n in feed.element_moles.items() if n > 0}
kg.update({e: g / 1000.0 for e, g in feed.trace_grams.items()})
water = feed.moisture_kg
kg["H"] += water * 2 * 1.008 / 18.015
kg["O"] += water * 15.999 / 18.015

lad = run_ladder(feed, dT=25.0)
rec = lad.recovery_table()

rows = []
for el, per_t in kg.items():
    bands, form = STREAM.get(el, ("", ""))
    if el in rec.index:
        cols = list(rec.columns) if bands == "all" else \
            [c for c in rec.columns if c in bands.split("+") or (len(c) == 1 and c in bands)
             or (c in ("D1", "D2") and "D" in bands)]      # "D" = both halves of Band D
        captured = float(rec.loc[el, cols].sum())
    else:
        captured = 1.0
    y = REFINING_YIELD.get(el, 1.0)
    rows.append({"element": el, "kg_per_t": per_t, "stream": bands, "form": form,
                 "captured": captured, "refining_yield": y,
                 "theoretical_lb": per_t * LANDFILL_T * LB_PER_KG,
                 "practical_lb": per_t * captured * y * LANDFILL_T * LB_PER_KG})
inv = pd.DataFrame(rows).sort_values("theoretical_lb", ascending=False)
inv.to_csv(RESULTS / "landfill_inventory.csv", index=False)
record("landfill_inventory", {"landfill_t": LANDFILL_T, "elements": inv.round(4).to_dict(orient="records")})
pd.set_option("display.width", 160)
print(inv.round(3).to_string(index=False))
