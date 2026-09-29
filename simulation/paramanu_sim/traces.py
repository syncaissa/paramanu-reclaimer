"""Trace metals that are not in the NASA database (Au, Ag, Pd, Sn, ...).

Model (Tier 2, approximate): each trace metal i is either in the gas or
dissolved in the condensate being collected at that step. Raoult/Henry
partitioning with activity coefficient gamma gives, for one cooling step,

    n_cond / n_gas = (N_cond / N_gas) * P / (gamma * p_sat_i(T))

where N_cond, N_gas are the moles of condensate formed and of gas remaining.
p_sat comes from the Clausius-Clapeyron equation anchored at the normal
boiling point. If no host condenses, the metal condenses on its own once its
partial pressure exceeds p_sat. gamma = 1 (ideal dilute solution) by default;
real alloys differ, so gamma is a sweep parameter.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

R = 8.314462618
ATM = 101325.0
DATA = Path(__file__).parent / "data" / "trace_vapor.csv"


@dataclass(frozen=True)
class VaporData:
    element: str
    molar_mass: float   # g/mol
    t_boil: float       # K, normal boiling point
    dh_vap: float       # J/mol at the boiling point

    def p_sat(self, T: float) -> float:
        """Saturation pressure (Pa) from Clausius-Clapeyron."""
        return ATM * math.exp(-self.dh_vap / R * (1.0 / T - 1.0 / self.t_boil))


def load_vapor_data(path: Path = DATA) -> dict[str, VaporData]:
    out = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(r for r in fh if not r.startswith("#")):
            out[row["element"]] = VaporData(row["element"], float(row["molar_mass"]),
                                            float(row["t_boil_K"]), float(row["dh_vap_kJ"]) * 1000.0)
    return out


def partition_step(gas_moles: dict[str, float], T: float, P: float, n_gas: float,
                   n_host: float, vapor: dict[str, VaporData], gamma: float = 1.0) -> dict[str, float]:
    """Moles of each trace metal that condense during one cooling step."""
    condensed = {}
    for el, n in gas_moles.items():
        if n <= 0:
            continue
        psat = vapor[el].p_sat(T)
        if n_host > 0 and n_gas > 0:
            k = (n_host / n_gas) * P / (gamma * psat)
            frac = k / (1.0 + k)
        else:
            frac = 0.0
        # self-condensation if still supersaturated
        remaining = n * (1.0 - frac)
        y = remaining / max(n_gas, 1e-300)
        if y * P > psat and n_gas > 0:
            remaining = psat / P * n_gas
        condensed[el] = n - max(remaining, 0.0)
    return condensed
