"""Energy envelope from thermodynamic data (replaces the proxy estimate).

Energy to take the feed from 298 K to the equilibrium state at (T, P):

    E(T) = H_equilibrium(T, P) - H_feed(298 K) + E_drying

H_feed is the sum of standard enthalpies of formation of the feed compounds
(feed.py); H_equilibrium comes from the NASA data for whatever species exist
at T. Drying evaporates the moisture from 25 C.
"""
from __future__ import annotations

import cantera as ct
import numpy as np
import pandas as pd

from .equilibrium import equilibrate
from .feed import Feed

DRYING_J_PER_KG = 2.26e6 + 4186.0 * 75.0   # latent heat + heating water 25 -> 100 C
J_PER_MWH = 3.6e9


def all_gas_temperature(feed: Feed, P: float = ct.one_atm, T_lo: float = 1500.0,
                        T_hi: float = 6000.0, tol: float = 5.0) -> float:
    """Lowest temperature at which no condensed phase remains (bisection)."""
    def vapor(T):
        eq = equilibrate(feed.element_moles, T, P)
        return sum(eq.condensed.values()) < 1e-6 * sum(feed.element_moles.values())

    if not vapor(T_hi):
        return np.nan
    lo, hi = T_lo, T_hi
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if vapor(mid):
            hi = mid
        else:
            lo = mid
    return hi


def energy_curve(feed: Feed, temperatures, P: float = ct.one_atm) -> pd.DataFrame:
    """Gross energy (MWh per batch) to reach equilibrium at each temperature."""
    rows = []
    e_dry = feed.moisture_kg * DRYING_J_PER_KG
    for T in temperatures:
        eq = equilibrate(feed.element_moles, float(T), P)
        e = eq.enthalpy - feed.formation_enthalpy_J + e_dry
        rows.append({"T": float(T), "MWh": e / J_PER_MWH, "gas_mol": sum(eq.gas.values()),
                     "condensed_mol": sum(eq.condensed.values())})
    return pd.DataFrame(rows)
