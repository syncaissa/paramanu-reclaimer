"""How long a solid grain takes to heat, melt and vaporize in hot gas.

Heat reaches a small sphere by conduction (Nusselt number 2). With the gas
conductivity k(T) varying strongly, the exact flux is written with the heat
conduction potential S(T) = integral of k dT (Chen, Pure Appl. Chem. 60 (1988)
651, p. 652):

    q = (S(T_gas) - S(T_surface)) / r

A grain of diameter d0 and density rho that must absorb dH_heat per kg at
constant size and then L per kg while it shrinks (d^2 law) therefore needs

    t = rho d0^2 (dH_heat / 12 + L / 8) / (S(T_gas) - S(T_surface))

The time grows as d0^2. This is a lower bound: it neglects vapor shielding,
radiation losses and the cooling of the gas by a dense load of particles.

Gas conductivity: air at 1 atm from the curve fits of Gupta, Lee, Thompson &
Yos, NASA RP-1260 (1991), Eq. 30 and Table V (includes dissociation). A
hydrogen-rich gas conducts better, so air is the conservative choice here.
"""
from __future__ import annotations

import math

import cantera as ct
import numpy as np

_GUPTA_AIR = [  # T_lo, T_hi, A, B, C, D, E: ln k = A X^4 + B X^3 + C X^2 + D X + E, X = ln(T/10000)
    (500, 2250, 0.334316, 3.28202, 11.9939, 20.0944, 4.62882),
    (2250, 4250, 10.9992, 38.7106, 38.7282, 5.48304, -12.0106),
    (4250, 7750, 12.4072, -14.7438, -53.0293, -29.9886, -9.61485),
    (7750, 10750, -189.644, -82.8711, 9.98789, 2.27739, -5.81069),
]
CAL_CM = 418.4   # cal/(cm s K) -> W/(m K)


def k_air(T: float) -> float:
    """Thermal conductivity of equilibrium air at 1 atm, W/(m K), 500-10,750 K."""
    X = math.log(T / 1e4)
    for lo, hi, a, b, c, d, e in _GUPTA_AIR:
        if lo <= T <= hi:
            return math.exp(a * X**4 + b * X**3 + c * X**2 + d * X + e) * CAL_CM
    raise ValueError(f"T = {T} K outside the fitted range")


def conduction_potential_difference(T_gas: float, T_surface: float, k=k_air, n: int = 4000) -> float:
    """S(T_gas) - S(T_surface) = integral of k dT, W/m."""
    T = np.linspace(T_surface, T_gas, n)
    kv = np.array([k(t) for t in T])
    return float(np.sum(0.5 * (kv[1:] + kv[:-1]) * np.diff(T)))


def silica_enthalpies(T_surface: float = 2900.0) -> tuple[float, float]:
    """(heat to liquid at T_surface, then decompose to SiO(g) + 1/2 O2(g)), J/kg,
    from the NASA data used everywhere else in this package."""
    gas = ct.Solution(thermo="ideal-gas", species=[s for s in ct.Species.list_from_file("nasa_gas.yaml")
                                                   if s.name in ("SiO", "O2")])
    cond = {s.name: s for s in ct.Species.list_from_file("nasa_condensed.yaml") if s.name.startswith("SiO2")}

    def h_cond(T):
        for s in cond.values():
            if s.thermo.min_temp <= T <= s.thermo.max_temp:
                ph = ct.Solution(thermo="fixed-stoichiometry", species=[s])
                ph.TP = T, ct.one_atm
                return ph.enthalpy_mole / 1000.0          # J/mol
        raise ValueError(T)

    M = 60.084e-3
    h0, hs = h_cond(298.15), h_cond(T_surface)
    gas.TPX = T_surface, ct.one_atm, "SiO:1"
    h_sio = gas.enthalpy_mole / 1000.0
    gas.TPX = T_surface, ct.one_atm, "O2:1"
    h_o2 = gas.enthalpy_mole / 1000.0
    return (hs - h0) / M, (h_sio + 0.5 * h_o2 - hs) / M


def vaporization_time(d0: float, T_gas: float, T_surface: float = 2900.0, rho: float = 2200.0) -> float:
    """Seconds to heat and fully vaporize a silica grain of diameter d0 (m)."""
    dh, L = silica_enthalpies(T_surface)
    return rho * d0**2 * (dh / 12.0 + L / 8.0) / conduction_potential_difference(T_gas, T_surface)


def max_diameter(t: float, T_gas: float, T_surface: float = 2900.0, rho: float = 2200.0) -> float:
    """Largest silica grain (m) that vaporizes completely within t seconds."""
    return math.sqrt(t / vaporization_time(1.0, T_gas, T_surface, rho))
