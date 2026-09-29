"""Closed-form results used as design equations (design principles, paper Section 4).

Every function here is the formula of a numbered result in the paper; the
experiment scripts check each one against the full simulation.

  vapor_pressure        pure-element saturation pressure from NASA data
  condensation_onset    Result 3: onset temperature of a dilute element
  relative_volatility   Result 4: alpha_ij = p_i / p_j
  fenske_min_stages     Result 4: minimum ideal stages for a binary split
  min_separation_work   Result 6: thermodynamic floor on the work of unmixing
  radiation_time_constant, flow_loss_fraction   Result 5: hot-zone design
"""
from __future__ import annotations

import math

import cantera as ct
import numpy as np

from .thermo import ATOM_SPECIES, load
from .traces import load_vapor_data

R = 8.314462618
SIGMA = 5.670374419e-8
P0 = ct.one_atm


# --------------------------------------------------------------------------
# Vapor pressure of a pure element
# --------------------------------------------------------------------------
def _pure_condensed(el: str, T: float):
    """Most stable pure condensed phase of element `el` valid at T (NASA data)."""
    th = load()
    best, g_best = None, np.inf
    for ph in th.condensed_at(T):
        comp = ph.species(0).composition
        if set(comp) == {el}:
            ph.TP = T, P0
            g = ph.standard_gibbs_RT[0] / comp[el]
            if g < g_best:
                best, g_best = ph, g
    return best, g_best


def vapor_pressure(el: str, T: float) -> float:
    """Saturation pressure (Pa) of element `el` over its pure condensed phase.

    NASA elements: p/P0 = exp(-(g_gas - g_cond)/RT) for the monatomic gas.
    Trace metals without NASA data: Clausius-Clapeyron from CRC data.
    """
    th = load()
    if el in th.elements:
        _, g_c = _pure_condensed(el, T)
        if not np.isfinite(g_c):
            return np.inf                       # no condensed phase valid: above critical range
        th.gas.TP = T, P0
        g_g = th.gas.standard_gibbs_RT[th.gas.species_index(ATOM_SPECIES[el])]
        return P0 * math.exp(-(g_g - g_c))
    return load_vapor_data()[el].p_sat(T)


def enthalpy_of_vaporization(el: str, T: float) -> float:
    """dH_vap (J/mol) at T from the slope of ln p: dH = R T^2 d(ln p)/dT."""
    h = 1.0
    return R * T * T * (math.log(vapor_pressure(el, T + h)) - math.log(vapor_pressure(el, T - h))) / (2 * h)


def boiling_point(el: str, P: float = P0) -> float:
    lo, hi = 300.0, 6000.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if vapor_pressure(el, mid) < P:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------
# Result 3: onset of condensation of a dilute element
# --------------------------------------------------------------------------
def condensation_onset(el: str, y: float, P: float = P0) -> float:
    """Temperature at which an element at gas mole fraction y starts to condense
    as its pure phase: solves y * P = p_sat(T) (exact, by bisection)."""
    target = y * P
    lo, hi = 200.0, 6000.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if vapor_pressure(el, mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def condensation_onset_closed_form(t_boil: float, dh_vap: float, y: float, P: float = P0) -> float:
    """Clausius-Clapeyron closed form: 1/T_c = 1/T_b - (R/dH) ln(y P / P0)."""
    return 1.0 / (1.0 / t_boil - (R / dh_vap) * math.log(y * P / P0))


# --------------------------------------------------------------------------
# Result 4: relative volatility and minimum stages (Fenske)
# --------------------------------------------------------------------------
def relative_volatility(el_i: str, el_j: str, T: float, gamma_i: float = 1.0, gamma_j: float = 1.0) -> float:
    return (gamma_i * vapor_pressure(el_i, T)) / (gamma_j * vapor_pressure(el_j, T))


def fenske_min_stages(alpha: float, purity_top: float = 0.99, purity_bottom: float = 0.99) -> float:
    """Minimum ideal equilibrium stages (total reflux) to split a binary with
    constant relative volatility alpha (> 1) into two products of the given purity."""
    if alpha <= 1.0:
        return math.inf
    xd, xb = purity_top, 1.0 - purity_bottom
    return math.log((xd / (1 - xd)) * ((1 - xb) / xb)) / math.log(alpha)


def rayleigh_single_stage(alpha: float, recovered_fraction_heavy: float) -> float:
    """Single-stage (Rayleigh) fractional condensation of a binary: fraction of the
    light (more volatile) component that has condensed when a fraction f of the
    heavy one has condensed: 1 - (1 - f)^(1/alpha)."""
    return 1.0 - (1.0 - recovered_fraction_heavy) ** (1.0 / alpha)


# --------------------------------------------------------------------------
# Result 5: hot-zone design (batch or flow)
# --------------------------------------------------------------------------
def sphere_area(volume: float) -> float:
    return (36.0 * math.pi) ** (1.0 / 3.0) * volume ** (2.0 / 3.0)


def radiation_time_constant(energy_J: float, gas_mol: float, T: float, P: float,
                            emissivity: float = 0.3, T_wall: float = 600.0) -> float:
    """tau = E / Q: time for wall radiation to equal the batch energy (s)."""
    V = gas_mol * R * T / P
    Q = emissivity * SIGMA * sphere_area(V) * (T ** 4 - T_wall ** 4)
    return energy_J / Q


def flow_loss_fraction(mass_flow_kg_s: float, e_J_per_kg: float, gas_mol_per_kg: float, T: float,
                       P: float, residence_s: float, emissivity: float = 0.3,
                       T_wall: float = 600.0) -> float:
    """Q/P for a continuous hot zone: radiation loss over torch power."""
    V = mass_flow_kg_s * gas_mol_per_kg * R * T / P * residence_s
    Q = emissivity * SIGMA * sphere_area(V) * (T ** 4 - T_wall ** 4)
    return Q / (mass_flow_kg_s * e_J_per_kg)


# --------------------------------------------------------------------------
# Result 6: minimum work of separation
# --------------------------------------------------------------------------
def min_separation_work(atom_moles: dict[str, float], T0: float = 298.15) -> float:
    """Work (J) to unmix an ideal mixture of the given atom amounts into pure
    elements at T0: W = -R T0 sum n_i ln x_i. A floor on the separation step
    alone (it excludes the energy to break chemical bonds)."""
    n = np.array([v for v in atom_moles.values() if v > 0])
    x = n / n.sum()
    return float(-R * T0 * np.sum(n * np.log(x)))
