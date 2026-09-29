"""Validation against independent references.

1. Normal boiling points of pure elements predicted by the solver + NASA data,
   compared with the CRC Handbook of Chemistry and Physics.
2. Gas-phase equilibrium from our solver compared with Cantera's own
   element-potential solver for the same mixture.
"""
from __future__ import annotations

import cantera as ct
import numpy as np
import pandas as pd

from .equilibrium import equilibrate
from .thermo import load

# Normal boiling points, K (CRC Handbook, 95th ed.)
CRC_BOILING_K = {"Fe": 3134, "Cu": 2835, "Ni": 3186, "Cr": 2944, "Al": 2743, "Si": 3538,
                 "Ti": 3560, "Ca": 1757, "Mg": 1363, "Na": 1156, "K": 1032, "Li": 1615,
                 "Zn": 1180, "Pb": 2022, "Hg": 630}


def boiling_point(element: str, P: float = ct.one_atm, lo: float = 300.0, hi: float = 6000.0,
                  tol: float = 0.5) -> float:
    """Temperature at which 1 mol of the pure element is fully vaporized at P."""
    def has_condensed(T):
        eq = equilibrate({element: 1.0}, T, P)
        return sum(eq.condensed.values()) > 1e-9

    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if has_condensed(mid):
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def boiling_point_table() -> pd.DataFrame:
    rows = []
    for el, ref in CRC_BOILING_K.items():
        tb = boiling_point(el)
        rows.append({"element": el, "model_K": round(tb, 1), "CRC_K": ref,
                     "error_K": round(tb - ref, 1), "error_pct": round(100 * (tb - ref) / ref, 2)})
    return pd.DataFrame(rows)


def gas_crosscheck(element_moles: dict[str, float], T: float, P: float = ct.one_atm) -> pd.DataFrame:
    """Compare major gas mole fractions with Cantera's gas-phase equilibrium."""
    th = load()
    ours = equilibrate(element_moles, T, P, th, allow_condensed=False)
    tot = sum(ours.gas.values())
    gas = th.gas
    species = [s for s in gas.species() if set(s.composition) <= set(element_moles)]
    ref = ct.Solution(thermo="ideal-gas", species=species)
    x0 = {}
    for e, n in element_moles.items():
        name = "AL" if e == "Al" else "CL" if e == "Cl" else e
        x0[name] = n
    ref.TPX = T, P, x0
    ref.equilibrate("TP")
    rows = []
    for name, x in zip(ref.species_names, ref.X):
        if x > 1e-4:
            rows.append({"species": name, "cantera_X": x, "paramanu_X": ours.gas.get(name, 0.0) / tot})
    df = pd.DataFrame(rows)
    df["rel_diff"] = (df.paramanu_X - df.cantera_X) / df.cantera_X
    return df
