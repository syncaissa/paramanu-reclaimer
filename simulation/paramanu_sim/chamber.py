"""First-order engineering of the sealed plasma chamber.

  * Vessel volume needed to hold a vaporized batch at a design pressure.
  * Radiative heat loss from hot gas to cooled walls (grey-gas estimate).
  * Ionization fraction of the plasma heap from the Saha equation.

The Saha solver is vectorized over temperature/pressure grids and runs on a
GPU through CuPy when available (backend.py), otherwise on NumPy.
"""
from __future__ import annotations

import math

import numpy as np

from .backend import xp_for

R = 8.314462618
SIGMA = 5.670374419e-8          # Stefan-Boltzmann, W m^-2 K^-4
K_B = 1.380649e-23
H_PLANCK = 6.62607015e-34
M_E = 9.1093837015e-31
EV = 1.602176634e-19

# First ionization energies, eV (NIST Atomic Spectra Database).
IONIZATION_EV = {"H": 13.598, "C": 11.260, "N": 14.534, "O": 13.618, "F": 17.423,
                 "Na": 5.139, "Mg": 7.646, "Al": 5.986, "Si": 8.152, "P": 10.487,
                 "S": 10.360, "Cl": 12.968, "K": 4.341, "Ca": 6.113, "Ti": 6.828,
                 "Cr": 6.767, "Fe": 7.902, "Ni": 7.640, "Cu": 7.726, "Zn": 9.394,
                 "Pb": 7.417, "Hg": 10.438, "Li": 5.392, "Ar": 15.760}


def vessel_volume_m3(gas_mol: float, T: float, P_pa: float) -> float:
    """Ideal-gas volume of the vaporized batch."""
    return gas_mol * R * T / P_pa


def sphere_area_m2(volume_m3: float) -> float:
    r = (3.0 * volume_m3 / (4.0 * math.pi)) ** (1.0 / 3.0)
    return 4.0 * math.pi * r * r


def radiative_loss_w(T_gas: float, area_m2: float, emissivity: float = 0.3,
                     T_wall: float = 600.0) -> float:
    """Grey-gas radiation from the plasma heap to cooled walls."""
    return emissivity * SIGMA * area_m2 * (T_gas ** 4 - T_wall ** 4)


def saha_ionization(element_moles: dict[str, float], T, P_pa, use_gpu: bool = False,
                    iters: int = 80):
    """Ionization fraction (electrons per heavy particle) vs temperature/pressure.

    Assumes every element is present as atoms (upper bound on ionization at a
    given T), single ionization only, and partition-function ratio 2*g+/g0 = 1.
    T and P_pa may be arrays of the same shape. Solved by bisection on the
    electron fraction, fully vectorized.
    """
    xp = xp_for(use_gpu)
    T = xp.asarray(T, dtype=float)
    P = xp.asarray(P_pa, dtype=float) * xp.ones_like(T)
    names = [e for e, n in element_moles.items() if n > 0 and e in IONIZATION_EV]
    tot = sum(element_moles[e] for e in names)
    y = xp.asarray([element_moles[e] / tot for e in names]).reshape(-1, *([1] * T.ndim))
    chi = xp.asarray([IONIZATION_EV[e] * EV for e in names]).reshape(-1, *([1] * T.ndim))
    lam3 = (H_PLANCK ** 2 / (2.0 * math.pi * M_E * K_B * T)) ** 1.5
    n_tot = P / (K_B * T)                              # heavy particles + electrons
    # S_i = n_e n_i+ / n_i0 (Saha constant for each element)
    S = (1.0 / lam3) * xp.exp(-chi / (K_B * T))
    lo = xp.zeros_like(T)
    hi = xp.ones_like(T)
    for _ in range(iters):
        xe = 0.5 * (lo + hi)                           # electrons per heavy particle
        n_heavy = n_tot / (1.0 + xe)
        ne = xe * n_heavy
        frac = S / (S + ne)                            # ionized fraction of element i
        f = (y * frac).sum(axis=0) - xe
        hi = xp.where(f < 0, xe, hi)
        lo = xp.where(f >= 0, xe, lo)
    out = 0.5 * (lo + hi)
    return out.get() if hasattr(out, "get") else out
