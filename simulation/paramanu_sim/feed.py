"""Feed model: a tonne of excavated landfill material as elements.

Each component of the heap is represented by a proxy composition (mass
fractions of simple compounds). All numbers are illustrative defaults to be
replaced with site sampling data; every one is a parameter.

Sources for proxies
  * Soil / fines oxides: upper continental crust, Rudnick & Gao (2003).
  * Heavy metals in the fines: measured pseudo-total contents of landfill
    fines <4.5 mm, Mont-Saint-Guibert landfill, Vollprecht, Hernandez Parrodi,
    Lucas & Pomberger, Detritus 10 (2020) 26-43, doi:10.31025/2611-4135/2020.13940,
    Table 2 (unweighted mean of the four size classes). Metal is dispersed as
    grains of a few micrometres in fine soil, which magnets and eddy currents
    cannot remove, so pre-treatment leaves it in the feed.
  * Soda-lime glass: typical container-glass composition.
  * Plastics: polyolefin-dominated municipal plastic mix with PVC and PET.
  * Paper, wood, textiles: cellulose.
  * Component masses: the PARAMANU Sort-First baseline spreadsheet.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .thermo import ATOMIC_MASS, EQUILIBRIUM_ELEMENTS

# ---------------------------------------------------------------------------
# Compounds: element formula and standard enthalpy of formation (kJ/mol, 298 K)
# Oxide values: NASA/JANAF (as used by Cantera). Polymer values are
# approximate literature values per repeat unit; they shift the energy
# envelope by well under 1% and are exposed for sensitivity runs.
# ---------------------------------------------------------------------------
COMPOUNDS: dict[str, tuple[dict[str, float], float]] = {
    "SiO2": ({"Si": 1, "O": 2}, -910.7),
    "Al2O3": ({"Al": 2, "O": 3}, -1675.7),
    "FeO": ({"Fe": 1, "O": 1}, -272.0),
    "MgO": ({"Mg": 1, "O": 1}, -601.6),
    "CaO": ({"Ca": 1, "O": 1}, -634.9),
    "Na2O": ({"Na": 2, "O": 1}, -414.2),
    "K2O": ({"K": 2, "O": 1}, -361.5),
    "TiO2": ({"Ti": 1, "O": 2}, -944.0),
    "P2O5": ({"P": 2, "O": 5}, -1492.0),  # half of P4O10 (-2984 kJ/mol)
    "NaCl": ({"Na": 1, "Cl": 1}, -411.2),
    "CaSO4": ({"Ca": 1, "S": 1, "O": 4}, -1434.5),
    "CaF2": ({"Ca": 1, "F": 2}, -1228.0),
    "PE": ({"C": 2, "H": 4}, -56.0),          # polyethylene/polypropylene unit
    "PVC": ({"C": 2, "H": 3, "Cl": 1}, -95.0),
    "PET": ({"C": 10, "H": 8, "O": 4}, -476.0),
    "PS": ({"C": 8, "H": 8}, 50.0),
    "cellulose": ({"C": 6, "H": 10, "O": 5}, -963.0),
    "protein_N": ({"C": 2, "H": 5, "N": 1, "O": 2}, -528.0),  # glycine-like
    "graphite": ({"C": 1}, 0.0),
    # heavy-metal oxides in the fines (NIST-JANAF; their effect on the energy is < 0.1%)
    "CuO": ({"Cu": 1, "O": 1}, -156.1),
    "ZnO": ({"Zn": 1, "O": 1}, -350.5),
    "PbO": ({"Pb": 1, "O": 1}, -219.0),
    "Cr2O3": ({"Cr": 2, "O": 3}, -1134.7),
    "NiO": ({"Ni": 1, "O": 1}, -239.7),
}
for _el in EQUILIBRIUM_ELEMENTS:          # pure elements, standard state
    COMPOUNDS.setdefault(_el, ({_el: 1}, 0.0))

# Upper continental crust major oxides, wt% (Rudnick & Gao 2003), renormalized.
CRUST = {"SiO2": 66.62, "TiO2": 0.64, "Al2O3": 15.40, "FeO": 5.04, "MgO": 2.48,
         "CaO": 3.59, "Na2O": 3.27, "K2O": 2.80, "P2O5": 0.15}

# Heavy metals in landfill fines, mg per kg dry matter (Vollprecht et al. 2020,
# Table 2: mean of the 4.5-1.6, 1.6-0.5, 0.5-0.18 and <0.18 mm fractions).
FINES_METALS_MG_KG = {"Cu": (770 + 430 + 133 + 197) / 4, "Zn": (1203 + 1260 + 567 + 953) / 4,
                      "Pb": (670 + 1010 + 460 + 777) / 4, "Cr": (96 + 107 + 45 + 76) / 4,
                      "Ni": (74 + 95 + 41 + 69) / 4}
_OXIDE = {"Cu": ("CuO", 79.545 / 63.546), "Zn": ("ZnO", 81.38 / 65.38), "Pb": ("PbO", 223.2 / 207.2),
          "Cr": ("Cr2O3", 151.99 / (2 * 51.996)), "Ni": ("NiO", 74.69 / 58.693)}
_FINES_OXIDES = {_OXIDE[m][0]: mg * 1e-6 * _OXIDE[m][1] for m, mg in FINES_METALS_MG_KG.items()}

COMPONENTS: dict[str, dict[str, float]] = {   # mass fractions of compounds
    "fines": {**{k: (0.88 - sum(_FINES_OXIDES.values())) * v / sum(CRUST.values()) for k, v in CRUST.items()},
              **_FINES_OXIDES, "cellulose": 0.10, "protein_N": 0.01, "CaSO4": 0.01},
    "glass": {"SiO2": 0.72, "Na2O": 0.14, "CaO": 0.09, "MgO": 0.04, "Al2O3": 0.01},
    "plastics": {"PE": 0.75, "PVC": 0.10, "PET": 0.10, "PS": 0.05},
    "paper": {"cellulose": 0.97, "protein_N": 0.03},
    "ferrous": {"Fe": 0.97, "Cr": 0.02, "Ni": 0.01},
    "nonferrous": {"Al": 0.60, "Cu": 0.25, "Zn": 0.10, "Pb": 0.05},
    "ewaste": {"Cu": 0.20, "Fe": 0.08, "Al": 0.05, "Ni": 0.02, "Zn": 0.01, "Pb": 0.015,
               "PE": 0.425, "SiO2": 0.20},
    "batteries": {"Li": 0.02, "Ni": 0.05, "Al": 0.10, "Cu": 0.10, "Fe": 0.20,
                  "graphite": 0.20, "FeO": 0.20, "CaF2": 0.02, "PE": 0.11},
    "other": {**{k: 0.50 * v / sum(CRUST.values()) for k, v in CRUST.items()},
              "cellulose": 0.30, "Fe": 0.10, "NaCl": 0.05, "CaSO4": 0.05},
}

# kg per wet tonne (Sort-First baseline spreadsheet, dry basis x 0.75)
DEFAULT_MASSES = {"fines": 375.0, "plastics": 135.0, "paper": 90.0, "glass": 90.0,
                  "ferrous": 30.0, "nonferrous": 9.0, "ewaste": 2.25,
                  "batteries": 0.375, "other": 18.375}
DEFAULT_MOISTURE_KG = 250.0

# Trace elements outside the NASA equilibrium set, ppm of dry feed.
# Handled by traces.py (vapor pressure + dilute solution in the host condensate).
DEFAULT_TRACES_PPM = {"Au": 0.5, "Ag": 10, "Pd": 0.2, "Pt": 0.05, "Sn": 200, "Sb": 30,
                      "Cd": 5, "Co": 15, "Mn": 700, "Bi": 5, "In": 1, "Ga": 15,
                      "Nd": 20, "W": 2}
DEFAULT_HG_PPM = 2.0  # mercury is in the equilibrium set

# Order in which the implementer's pre-treatment removes mass (easiest first).
PRETREAT_ORDER = ["ferrous", "nonferrous", "batteries", "ewaste", "glass", "fines"]


@dataclass
class Feed:
    masses_kg: dict[str, float]
    moisture_kg: float
    element_moles: dict[str, float]
    trace_grams: dict[str, float]
    formation_enthalpy_J: float
    removed_kg: dict[str, float] = field(default_factory=dict)

    @property
    def dry_kg(self) -> float:
        return sum(self.masses_kg.values())


def make_feed(masses_kg: dict[str, float] | None = None, pretreat_fraction: float = 0.052,
              moisture_kg: float = DEFAULT_MOISTURE_KG,
              traces_ppm: dict[str, float] | None = None, hg_ppm: float = DEFAULT_HG_PPM,
              argon_mol: float = 0.0) -> Feed:
    """Build the batch that enters the sealed reactor.

    pretreat_fraction: share of the dry mass removed by the implementer's
    physical/magnetic pre-treatment (0 to ~0.3), taken in PRETREAT_ORDER.
    The default (~5%) removes the ferrous and non-ferrous metal pieces.
    """
    masses = dict(masses_kg or DEFAULT_MASSES)
    total = sum(masses.values())
    to_remove = pretreat_fraction * total
    removed = {}
    for comp in PRETREAT_ORDER:
        if to_remove <= 0:
            break
        take = min(masses.get(comp, 0.0), to_remove)
        if take > 0:
            masses[comp] -= take
            removed[comp] = take
            to_remove -= take

    moles = {e: 0.0 for e in EQUILIBRIUM_ELEMENTS}
    h_f = 0.0
    for comp, kg in masses.items():
        for cmpd, frac in COMPONENTS[comp].items():
            formula, dhf = COMPOUNDS[cmpd]
            molar_mass = sum(ATOMIC_MASS[e] * k for e, k in formula.items())
            n = kg * 1000.0 * frac / molar_mass
            h_f += n * dhf * 1000.0
            for e, k in formula.items():
                moles[e] += n * k
    dry = sum(masses.values())
    moles["Hg"] += hg_ppm * 1e-6 * dry * 1000.0 / ATOMIC_MASS["Hg"]
    moles["Ar"] += argon_mol
    traces = {e: ppm * 1e-6 * dry * 1000.0 for e, ppm in (traces_ppm or DEFAULT_TRACES_PPM).items()}
    return Feed(masses, moisture_kg, moles, traces, h_f, removed)
