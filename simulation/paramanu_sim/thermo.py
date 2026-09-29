"""Thermodynamic data: NASA gas and condensed species shipped with Cantera.

The NASA polynomial database (McBride, Zehe & Gordon, NASA/TP-2002-211556) is
the standard source used by NASA CEA. Cantera ships it as nasa_gas.yaml and
nasa_condensed.yaml. Each condensed species is only valid inside its own
temperature window (e.g. Fe(L) above 1809 K), so condensed phases are
selected per temperature.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import cantera as ct

ct.suppress_thermo_warnings()

# Elements modelled with full multiphase equilibrium (present in the NASA data).
EQUILIBRIUM_ELEMENTS = [
    "H", "C", "N", "O", "F", "Na", "Mg", "Al", "Si", "P", "S", "Cl", "K", "Ca",
    "Ti", "Cr", "Fe", "Ni", "Cu", "Zn", "Pb", "Hg", "Li", "Ar",
]

# Name of the monatomic gas species for each element in the NASA files.
ATOM_SPECIES = {e: e for e in EQUILIBRIUM_ELEMENTS}
ATOM_SPECIES.update({"Al": "AL", "Cl": "CL"})

ATOMIC_MASS = {  # g/mol, IUPAC standard atomic weights (abridged)
    "H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Na": 22.990,
    "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45,
    "K": 39.098, "Ca": 40.078, "Ti": 47.867, "Cr": 51.996, "Fe": 55.845, "Ni": 58.693,
    "Cu": 63.546, "Zn": 65.38, "Pb": 207.2, "Hg": 200.59, "Li": 6.94, "Ar": 39.948,
}


@dataclass
class ThermoSet:
    """Gas phase plus a library of pure condensed phases for a set of elements."""

    elements: list[str]
    gas: ct.Solution
    condensed: list[ct.Solution] = field(default_factory=list)

    def condensed_at(self, T: float) -> list[ct.Solution]:
        """Condensed phases whose NASA fit is valid at temperature T."""
        out = []
        for ph in self.condensed:
            sp = ph.species(0)
            if sp.thermo.min_temp - 1e-6 <= T <= sp.thermo.max_temp + 1e-6:
                out.append(ph)
        return out


@lru_cache(maxsize=4)
def load(elements: tuple[str, ...] = tuple(EQUILIBRIUM_ELEMENTS), ions: bool = False) -> ThermoSet:
    """Build the gas phase and condensed-phase library restricted to `elements`."""
    allowed = set(elements)
    gas_species = []
    for sp in ct.Species.list_from_file("nasa_gas.yaml"):
        comp = set(sp.composition)
        if not ions and ("E" in comp or sp.name.endswith(("+", "-"))):
            continue
        if comp - {"E"} <= allowed:
            gas_species.append(sp)
    gas = ct.Solution(thermo="ideal-gas", species=gas_species)

    condensed = []
    for sp in ct.Species.list_from_file("nasa_condensed.yaml"):
        if set(sp.composition) <= allowed:
            try:
                condensed.append(ct.Solution(thermo="fixed-stoichiometry", species=[sp]))
            except ct.CanteraError:
                pass  # species without the data a pure phase needs
    return ThermoSet(list(elements), gas, condensed)
