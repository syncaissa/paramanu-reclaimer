"""Experiment 23 - Can PARAMANU pay for its own energy?

The plant's energy can come from two of its own outputs:
  (1) fuel: the hydrogen, carbon monoxide and methane it draws off, burned in a
      fuel cell or turbine on site;
  (2) money: the recovered elements, sold in pure or usable compound form, whose
      revenue buys the rest of the electricity.
This script puts both on the same per-tonne basis and asks how much of the
electricity bill each covers, and at what electricity price the two together
cover all of it (break-even).

Inputs (all per tonne of excavated material, the paper's basis):
  - recovered amounts: results/landfill_inventory.csv (script 16: simulated band
    capture at 1 atm x refining yield);
  - energy demand: 2.9 MWh gross enthalpy of the all-gas state (key_numbers.json,
    energy_MWh_all_gas_1atm), and 2.3 times that at the best demonstrated
    vaporization efficiency (Sayce 1976, Section "Energy Needs");
  - prices: the editable assumptions of the Sort-First spreadsheet
    (model/build_balance.py, Elements sheet column F, $ per kg of the sold form,
    and its product/element mass ratio), so both plants are valued alike.
    Elements the spreadsheet does not price are counted at zero (conservative),
    except platinum (priced like palladium) and bulk mineral products (silica,
    alumina, lime, magnesia, salts), counted at the spreadsheet's aggregate/slag
    price of $5 per tonne;
  - fuel: at equilibrium about 19 kg/t of gas remains (script 02), of which about
    1.2 kg is nitrogen and the rest methane; if the gas is quenched quickly,
    hydrogen and carbon monoxide survive, up to the 1.2 MWh/t of chemical energy
    of the Sort-First baseline's syngas. Converted to electricity at 50%.

    python 23_self_sufficiency.py
"""
import _common  # noqa: F401

import json

import pandas as pd

from paramanu_sim.plotting import RESULTS, record

# $ per kg of sold product and kg of product per kg of element
# (model/build_balance.py, Elements sheet columns F and L).
PRICE = {
    "Fe": (0.30, 1.0), "Cu": (9.0, 1.0), "Zn": (2.7, 1.0), "Pb": (2.0, 1.0),
    "Ni": (16.0, 1.0), "Sn": (30.0, 1.0), "Sb": (40.0, 1.20), "Cr": (10.0, 1.46),
    "Co": (30.0, 1.0), "Li": (60.0, 5.32), "Nd": (50.0, 1.17), "Ag": (1200.0, 1.0),
    "Au": (110000.0, 1.0), "Pd": (35000.0, 1.0), "Pt": (35000.0, 1.0),   # Pt: priced like Pd
    "F": (0.5, 2.05),
}
# Bulk mineral products at the spreadsheet's aggregate/slag price ($5 per tonne).
BULK_PRICE = 0.005
BULK = {"Si": 60.08 / 28.09, "Al": 101.96 / 53.96, "Ca": 56.08 / 40.08,
        "Mg": 40.30 / 24.31, "Na": 58.44 / 22.99, "K": 74.55 / 39.10}
ELEC_PRICE = 0.10          # $/kWh, spreadsheet "Electricity purchase price"
ELEC_PRICE_LOW = 0.05      # $/kWh, a firm industrial contract (spreadsheet export price)
DEMONSTRATED = 2.3         # best demonstrated vaporization energy / gross enthalpy
FUEL_TO_POWER = 0.50       # fuel cell or combined cycle
CH4_LHV_MWH_PER_KG = 50.0 / 3600.0
GAS_LEFT_KG, N2_KG = 19.4, 1.2      # script 02 (band "gas"), inventory N
SYNGAS_MAX_MWH = 1.2                # Sort-First baseline syngas, chemical energy

inv = pd.read_csv(RESULTS / "landfill_inventory.csv").set_index("element")
kn = json.loads((RESULTS / "key_numbers.json").read_text())
gross = float(kn["energy_MWh_all_gas_1atm"])

rows = []
for el, r in inv.iterrows():
    kg = r.kg_per_t * r.captured * r.refining_yield
    if el in PRICE:
        price, ratio = PRICE[el]
    elif el in BULK:
        price, ratio = BULK_PRICE, BULK[el]
    else:
        continue
    rows.append({"element": el, "kg_recovered_per_t": kg, "product_kg": kg * ratio,
                 "price_per_kg_product": price, "revenue_per_t": kg * ratio * price})
rev = pd.DataFrame(rows).sort_values("revenue_per_t", ascending=False)
revenue = float(rev.revenue_per_t.sum())

fuel_chem = {"equilibrium": (GAS_LEFT_KG - N2_KG) * CH4_LHV_MWH_PER_KG, "quenched": SYNGAS_MAX_MWH}
out = []
for case, mult in (("gross enthalpy", 1.0), ("best demonstrated", DEMONSTRATED)):
    need = gross * mult
    for gas, chem in fuel_chem.items():
        own = chem * FUEL_TO_POWER
        net = need - own
        out.append({"energy_case": case, "fuel_case": gas, "MWh_needed": need,
                    "MWh_from_own_fuel": own, "fuel_share": own / need, "MWh_to_buy": net,
                    "cost_at_0.10": net * 1000 * ELEC_PRICE, "cost_at_0.05": net * 1000 * ELEC_PRICE_LOW,
                    "sales_share_at_0.10": revenue / (net * 1000 * ELEC_PRICE),
                    "sales_share_at_0.05": revenue / (net * 1000 * ELEC_PRICE_LOW),
                    "own_fuel_plus_sales_share_at_0.05":
                        (own + revenue / (1000 * ELEC_PRICE_LOW)) / need,
                    "break_even_price_per_kWh": revenue / (net * 1000)})
tab = pd.DataFrame(out)
rev.to_csv(RESULTS / "self_sufficiency_revenue.csv", index=False)
tab.to_csv(RESULTS / "self_sufficiency.csv", index=False)
top = rev.head(6)
record("self_sufficiency", {
    "revenue_per_t": round(revenue, 1),
    "top_revenue": {e: round(v, 1) for e, v in zip(top.element, top.revenue_per_t)},
    "gross_MWh": round(gross, 3),
    "cases": tab.round(4).to_dict(orient="records"),
})
pd.set_option("display.width", 200)
print(rev.round(3).to_string(index=False))
print(f"\nrevenue from recovered elements: ${revenue:.1f} per tonne")
print(tab.round(3).to_string(index=False))
