"""Thermodynamic data for the trace metals that Cantera's NASA subset lacks.

Three tiers, each species carrying its source:

1. ``tabulated``: NASA-9 records from the NASA CEA database (trace_cea.inp) and
   NASA-7 records from Burcat & Ruscic (trace_burcat.thr), evaluated with the
   standard polynomial formulas (McBride, Zehe & Gordon 2002, eqs. 1-3).
2. ``statmech``: gas species with measured molecular constants but no
   published table (AgCl, AuCl, CdCl2). Their functions are computed by
   rigid-rotor / harmonic-oscillator statistical mechanics, exactly as
   NIST-JANAF builds its tables, and anchored at a measured enthalpy of
   formation (trace_statmech.json).
3. ``bracket``: species known only from a measured reaction Gibbs energy over
   a limited range (Au2Cl2, Au2Cl6, PtCl2; trace_bracket.json). They are used
   only in the "most volatile" data set, to bound the effect of chlorine.

All Gibbs energies follow the NASA convention (elements in their reference
state have H = 0 at 298.15 K) and use the same standard-pressure label as
Cantera's copy of the NASA data, so they combine directly with the element
potentials of the major-element equilibrium.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

DATA = Path(__file__).parent / "data"
R = 8.314462618            # J/mol/K
H_PLANCK = 6.62607015e-34
K_B = 1.380649e-23
C_CM = 2.99792458e10       # speed of light, cm/s
AMU = 1.66053906660e-27
P_STD = 1.0e5              # Pa, standard pressure of the NASA/JANAF functions
HC_K = H_PLANCK * C_CM / K_B   # K per cm^-1 (1.4388)

ATOMIC_MASS = {  # g/mol (IUPAC); majors plus the trace metals
    "H": 1.008, "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Na": 22.990,
    "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45,
    "K": 39.098, "Ca": 40.078, "Ti": 47.867, "Cr": 51.996, "Fe": 55.845, "Ni": 58.693,
    "Cu": 63.546, "Zn": 65.38, "Pb": 207.2, "Hg": 200.59, "Li": 6.94, "Ar": 39.948,
    "Au": 196.967, "Ag": 107.868, "Pd": 106.42, "Pt": 195.08, "Sn": 118.71,
    "Sb": 121.76, "Cd": 112.41, "Co": 58.933, "Mn": 54.938, "Bi": 208.98,
    "In": 114.82, "Ga": 69.723, "W": 183.84,
}


def _symbol(s: str) -> str:
    """'CL' -> 'Cl', 'AG' -> 'Ag' (the source files write symbols in capitals)."""
    return s[0].upper() + s[1:].lower()


@dataclass
class TraceSpecies:
    name: str
    composition: dict[str, float]
    phase: str                      # "gas" or "cond"
    tmin: float
    tmax: float
    g_RT: Callable[[float], float]  # standard Gibbs energy / RT
    source: str
    tier: str                       # tabulated | statmech | bracket
    note: str = ""

    def valid(self, T: float) -> bool:
        return self.tmin - 1e-6 <= T <= self.tmax + 1e-6


# ---------------------------------------------------------------- polynomials
def nasa9_g_RT(T: float, a: list[float], b: list[float]) -> float:
    """G/RT from one NASA-9 interval: a1..a7, b1, b2 (NASA/TP-2002-211556)."""
    lnT = math.log(T)
    h = (-a[0] / T**2 + a[1] * lnT / T + a[2] + a[3] * T / 2 + a[4] * T**2 / 3
         + a[5] * T**3 / 4 + a[6] * T**4 / 5 + b[0] / T)
    s = (-a[0] / (2 * T**2) - a[1] / T + a[2] * lnT + a[3] * T + a[4] * T**2 / 2
         + a[5] * T**3 / 3 + a[6] * T**4 / 4 + b[1])
    return h - s


def nasa7_g_RT(T: float, a: list[float]) -> float:
    """G/RT from one NASA-7 range: a1..a7."""
    h = a[0] + a[1] * T / 2 + a[2] * T**2 / 3 + a[3] * T**3 / 4 + a[4] * T**4 / 5 + a[5] / T
    s = a[0] * math.log(T) + a[1] * T + a[2] * T**2 / 2 + a[3] * T**3 / 3 + a[4] * T**4 / 4 + a[6]
    return h - s


def _piecewise(intervals):
    """Evaluate the interval containing T; extrapolate the nearest one outside."""
    def g(T: float) -> float:
        for lo, hi, fn in intervals:
            if lo - 1e-6 <= T <= hi + 1e-6:
                return fn(T)
        lo, hi, fn = intervals[0] if T < intervals[0][0] else intervals[-1]
        return fn(T)
    return g


def _float(s: str) -> float:
    return float(s.replace("D", "E").replace("d", "e"))


def read_cea(path: Path = DATA / "trace_cea.inp") -> list[TraceSpecies]:
    L = path.read_text().splitlines()
    i = L.index("thermo") + 2
    out = []
    while i < len(L):
        line = L[i]
        if not line.strip() or line.startswith(("!", "END")):
            i += 1
            continue
        name = line[:24].split()[0]
        ref = line[18:].strip()
        r2 = L[i + 1]
        nint = int(r2[:2])
        comp = {}
        for k in range(5):
            s = r2[10 + 8 * k:18 + 8 * k]
            if s[:2].strip() and float(s[2:]) != 0:
                comp[_symbol(s[:2].strip())] = float(s[2:])
        cond = int(r2[50:52]) != 0
        if nint == 0:                                   # single-temperature record
            i += 3
            continue
        intervals = []
        for k in range(nint):
            t, c1, c2 = L[i + 2 + 3 * k], L[i + 3 + 3 * k], L[i + 4 + 3 * k]
            lo, hi = float(t[:11]), float(t[11:22])
            a = [_float(c1[16 * j:16 * j + 16]) for j in range(5)]
            a += [_float(c2[16 * j:16 * j + 16]) for j in range(2)]
            b = [_float(c2[48:64]), _float(c2[64:80])]
            intervals.append((lo, hi, (lambda T, a=a, b=b: nasa9_g_RT(T, a, b))))
        out.append(TraceSpecies(name, comp, "cond" if cond else "gas", intervals[0][0],
                                intervals[-1][1], _piecewise(intervals),
                                f"NASA CEA thermo.inp ({ref})", "tabulated"))
        i += 2 + 3 * nint
    return out


def read_burcat(path: Path = DATA / "trace_burcat.thr") -> list[TraceSpecies]:
    L = path.read_text().splitlines()
    out, seen = [], {}
    for i, line in enumerate(L[:-3]):
        if not (len(line) >= 80 and line[79] == "1" and L[i + 3][79:80] == "4"):
            continue
        comp = {}
        for k in range(4):
            s = line[24 + 5 * k:29 + 5 * k]
            if s[:2].strip() and s[2:].strip() and float(s[2:]) != 0:
                comp[_symbol(s[:2].strip())] = float(s[2:])
        phase = line[44]
        lo, hi = float(line[45:55]), float(line[55:65])
        c = []
        for j in (1, 2, 3):
            c += [L[i + j][15 * k:15 * k + 15] for k in range(5)]
        c = [_float(x) for x in c[:14]]          # the 15th field (H298/R) is unused
        high, low = c[:7], c[7:14]
        if not any(high):
            high = low
        if not any(low):
            low = high
        fn = (lambda T, hi7=high, lo7=low: nasa7_g_RT(T, hi7 if T > 1000.0 else lo7))
        formula = "".join(f"{e}{'' if n == 1 else int(n)}" for e, n in comp.items())
        tag = {"G": "", "S": "(cr)", "L": "(L)"}.get(phase, f"({phase})")
        name = formula + tag
        if phase != "G":
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                name += f"#{seen[name]}"
        out.append(TraceSpecies(name, comp, "gas" if phase == "G" else "cond", lo, hi, fn,
                                f"Burcat & Ruscic ({line[18:24].strip()}): {line[:18].strip()}",
                                "tabulated"))
    return out


# -------------------------------------------------------- statistical mechanics
def rrho_functions(T: float, mass_amu: float, sigma: int, linear: bool,
                   rot_cm1: list[float], vib_cm1: list[tuple[float, int]],
                   levels: list[tuple[float, int]]) -> tuple[float, float]:
    """Ideal-gas H(T)-H(0) (J/mol) and S(T) (J/mol/K) at P_STD.

    Translation: Sackur-Tetrode. Rotation: classical rigid rotor (linear:
    one constant B; nonlinear: A, B, C). Vibration: harmonic oscillators.
    Electronic: explicit sum over levels (energy cm^-1, degeneracy).
    """
    m = mass_amu * AMU
    q_tr = (2 * math.pi * m * K_B * T / H_PLANCK**2) ** 1.5 * K_B * T / P_STD
    S = R * (math.log(q_tr) + 2.5)
    H = 2.5 * R * T
    if linear:
        S += R * (math.log(T / (HC_K * rot_cm1[0] * sigma)) + 1.0)
        H += R * T
    else:
        A, B, C = rot_cm1
        q_rot = math.sqrt(math.pi) / sigma * (T / HC_K) ** 1.5 / math.sqrt(A * B * C)
        S += R * (math.log(q_rot) + 1.5)
        H += 1.5 * R * T
    for nu, g in vib_cm1:
        x = HC_K * nu / T
        S += g * R * (x / math.expm1(x) - math.log(-math.expm1(-x)))
        H += g * R * T * x / math.expm1(x)
    q_el = sum(g * math.exp(-HC_K * e / T) for e, g in levels)
    u_el = sum(g * HC_K * e * math.exp(-HC_K * e / T) for e, g in levels) / q_el
    S += R * (math.log(q_el) + u_el / T)
    H += R * u_el
    return H, S


def _statmech_species(d: dict, dfH298_kJ: float, tag: str) -> TraceSpecies:
    comp = d["composition"]
    mass = sum(ATOMIC_MASS[e] * n for e, n in comp.items())
    args = (mass, d["symmetry_number"], d["linear"], d["rotational_cm1"],
            [tuple(v) for v in d["vibrations_cm1"]], [tuple(v) for v in d["electronic_levels"]])
    H298, _ = rrho_functions(298.15, *args)

    def g_RT(T: float) -> float:
        H, S = rrho_functions(T, *args)
        return (dfH298_kJ * 1000.0 + H - H298) / (R * T) - S / R

    return TraceSpecies(d["name"] + tag, comp, "gas", 298.15, 6000.0, g_RT,
                        d["source"], "statmech", d.get("note", ""))


# ------------------------------------------------------------------ data sets
@lru_cache(maxsize=4)
def load_trace_thermo(data_set: str = "central") -> tuple[TraceSpecies, ...]:
    """All trace species for one data set.

    central:        tabulated + statmech species at their recommended enthalpies.
    least_volatile: statmech chlorides at the least stable end of their range.
    most_volatile:  statmech chlorides at the most stable end, plus the
                    bracket species (Au2Cl2, Au2Cl6, PtCl2).
    """
    if data_set not in ("central", "least_volatile", "most_volatile"):
        raise ValueError(data_set)
    species = read_cea() + read_burcat()
    sm = json.loads((DATA / "trace_statmech.json").read_text())
    key = {"central": "dfH298_kJ", "least_volatile": "dfH298_kJ_max",
           "most_volatile": "dfH298_kJ_min"}[data_set]
    for d in sm["species"]:
        species.append(_statmech_species(d, d[key], ""))
    if data_set == "most_volatile":
        species += bracket_species(species)
    return tuple(species)


def bracket_species(base: list[TraceSpecies]) -> list[TraceSpecies]:
    """Species defined by a measured reaction Gibbs energy dG = A + B T (J/mol),
    extrapolated with constant dH and dS (second-law) beyond the measured range."""
    import cantera as ct
    cl2 = next(s for s in ct.Species.list_from_file("nasa_gas.yaml") if s.name == "CL2")
    gas = ct.Solution(thermo="ideal-gas", species=[cl2])

    def g_cl2(T):
        gas.TP = T, ct.one_atm
        return float(gas.standard_gibbs_RT[0])

    def g_metal(el, T):
        cands = [s for s in base if s.phase == "cond" and s.composition == {el: 1.0}
                 and "(L)" not in s.name] if T < 1000 else []
        cands = cands or [s for s in base if s.phase == "cond" and s.composition == {el: 1.0}]
        valid = [s for s in cands if s.valid(T)] or cands
        return min(s.g_RT(T) for s in valid)          # stable condensed form

    out = []
    for d in json.loads((DATA / "trace_bracket.json").read_text())["species"]:
        el, nm, ncl2 = d["metal"], d["n_metal"], d["n_cl2"]

        def g_RT(T, d=d, el=el, nm=nm, ncl2=ncl2):
            return (d["A_J"] + d["B_J_per_K"] * T) / (R * T) + nm * g_metal(el, T) + ncl2 * g_cl2(T)

        out.append(TraceSpecies(d["name"], d["composition"], "gas", 298.15, 6000.0, g_RT,
                                d["source"], "bracket", d.get("note", "")))
    return out


def trace_elements() -> list[str]:
    return ["Au", "Ag", "Pd", "Pt", "Sn", "Sb", "Cd", "Co", "Mn", "Bi", "In", "Ga", "W"]
