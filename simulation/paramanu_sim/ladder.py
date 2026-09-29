"""The time-domain condensation ladder: fractional condensation of a sealed batch.

The batch starts fully vaporized. It is cooled in small steps; at each step the
remaining gas is brought to equilibrium, whatever condenses is removed to the
collector that is active in that temperature interval (its band), and only the
gas carries on to the next step. This is the Rayleigh / fractional-condensation
limit of the PARAMANU batch cycle (Algorithm 1 in the paper).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cantera as ct
import numpy as np
import pandas as pd

from .equilibrium import equilibrate
from .feed import Feed
from .thermo import ATOMIC_MASS, load
from .traces import load_vapor_data, partition_step

# Bands proposed in the paper (lower bound of each temperature interval, K).
PAPER_BANDS = [("I", 3500.0), ("II", 2800.0), ("III", 2000.0), ("IV", 1000.0), ("V", 300.0)]
# Bands derived from the simulated condensation temperatures (scripts/02_ladder.py).
# Band D is split at 1,300 K: the adversarial search (20_falsification.py) found
# feeds rich in organics where dilution carries 10-40% of the gold below 1,600 K;
# that gold condenses at 1,300-1,600 K (D1) and lead only below 1,300 K (D2).
SIMULATED_BANDS = [("A", 2600.0), ("B", 2000.0), ("C", 1600.0), ("D1", 1300.0), ("D2", 1000.0), ("E", 400.0)]
SCAVENGE_REL = 1e-9
# Elements below this share of the gas are placed by the dilute-limit solver
# (the method of trace_chem.py, validated against the full solver in
# tests/test_trace.py) at the certified element potentials of the others:
# solving parts-per-billion remnants together with major elements is what made
# the global solver fail (Independent Verification section of the paper).
DILUTE_SHARE = 1e-6


class _DiluteElements:
    """Dilute-limit placement of NASA-set elements present below DILUTE_SHARE."""

    def __init__(self, th):
        self.th, self.cache = th, {}

    def chem(self, el):
        if el not in self.cache:
            from .trace_chem import TraceChemistry
            from .trace_thermo import TraceSpecies
            th, out = self.th, []
            for k, sp in enumerate(th.gas.species()):
                if el in sp.composition and not sp.name.endswith(("+", "-")):
                    def g(T, k=k):
                        th.gas.TP = T, ct.one_atm
                        return float(th.gas.standard_gibbs_RT[k])
                    out.append(TraceSpecies(sp.name, dict(sp.composition), "gas", 200.0, 20000.0, g,
                                            "NASA (Cantera)", "tabulated"))
            for ph in th.condensed:
                sp = ph.species(0)
                if el in sp.composition:
                    def g(T, ph=ph):
                        ph.TP = T, ct.one_atm
                        return float(ph.standard_gibbs_RT[0])
                    out.append(TraceSpecies(sp.name, dict(sp.composition), "cond", sp.thermo.min_temp,
                                            sp.thermo.max_temp, g, "NASA (Cantera)", "tabulated"))
            c = TraceChemistry.__new__(TraceChemistry)
            c.species, c.traces, c._by_trace = tuple(out), [el], {el: out}
            c.gamma = lambda a, b, T: 1.0
            self.cache[el] = c
        return self.cache[el]


@dataclass
class LadderResult:
    steps: pd.DataFrame                # one row per (T, element) condensed
    species: pd.DataFrame              # one row per (T, condensed species)
    gas_left: dict[str, float]         # element moles still gaseous at the end
    bands: list[tuple[str, float]]
    feed_moles: dict[str, float] = field(default_factory=dict)
    duties: pd.DataFrame = field(default_factory=pd.DataFrame)   # heat removed per step (J)
    trace_detail: pd.DataFrame = field(default_factory=pd.DataFrame)  # trace chemistry per step

    def band_duty_J(self) -> pd.Series:
        """Heat each band's condenser must remove (J per batch)."""
        d = self.duties.copy()
        d["band"] = d["T"].map(self.band_of)
        return d.groupby("band")["duty_J"].sum()

    def band_of(self, T: float) -> str:
        for name, lower in self.bands:
            if T >= lower:
                return name
        return "cold"          # collected below the last band (cold trap)

    def band_table(self) -> pd.DataFrame:
        """Grams of each element collected in each band (plus final gas)."""
        df = self.steps.copy()
        df["band"] = df["T"].map(self.band_of)
        tab = df.pivot_table(index="element", columns="band", values="grams", aggfunc="sum", fill_value=0.0)
        gas = pd.Series({e: n * _mass(e) for e, n in self.gas_left.items()}, name="gas")
        tab = tab.join(gas, how="outer").fillna(0.0)
        cols = [b for b, _ in self.bands if b in tab.columns] + \
            [c for c in ("cold", "gas") if c in tab.columns]
        return tab[cols]

    def recovery_table(self) -> pd.DataFrame:
        """Share of each element's input that ends up in each band."""
        tab = self.band_table()
        return tab.div(tab.sum(axis=1), axis=0)

    def condensation_temperature(self, share: float = 0.5) -> pd.Series:
        """Temperature by which `share` of each element has condensed."""
        out = {}
        total = self.steps.groupby("element")["moles"].sum().add(pd.Series(self.gas_left, dtype=float), fill_value=0.0)
        for el, grp in self.steps.sort_values("T", ascending=False).groupby("element"):
            cum = grp["moles"].cumsum() / total[el]
            hit = grp.loc[cum >= share, "T"]
            out[el] = float(hit.iloc[0]) if len(hit) else np.nan
        return pd.Series(out).sort_values(ascending=False)


def _mass(el: str) -> float:
    if el in ATOMIC_MASS:
        return ATOMIC_MASS[el]
    return load_vapor_data()[el].molar_mass


def _is_metal_host(name: str, th) -> bool:
    for ph in th.condensed:
        if ph.species_names[0] == name:
            return len(ph.species(0).composition) == 1 and name[:2] not in ("C(",)
    return False


def run_ladder(feed: Feed, P: float = ct.one_atm, T_start: float = 6000.0, T_end: float = 300.0,
               dT: float = 25.0, bands=SIMULATED_BANDS, gamma: float = 1.0,
               include_traces: bool = True, metal_solution: bool = False,
               trace_model: str = "chemistry", trace_data: str = "central",
               trace_gamma=None, thermo=None) -> LadderResult:
    """Cool the heap step by step, removing whatever condenses at each step.

    trace_model: "chemistry" (default: full dilute-limit chemistry with chlorides,
    oxides and host-specific measured activity coefficients, trace_chem.py;
    `trace_data` picks the data set, `trace_gamma(solute, host, T)` overrides
    the coefficients and `gamma` multiplies them all) or "vapor" (the earlier
    model: vapor pressure plus one activity coefficient `gamma`, traces.py).
    """
    th = thermo or load()
    vapor = load_vapor_data()
    chem = None
    if trace_model == "chemistry":
        from .trace_chem import TraceChemistry, henry_gamma
        chem = TraceChemistry(trace_data, trace_gamma or henry_gamma(factor=gamma))
    elif trace_model != "vapor":
        raise ValueError(trace_model)
    detail_rows = []
    dilute_chem = _DiluteElements(th)
    inventory = {e: n for e, n in feed.element_moles.items() if n > 0}
    traces_gas = {e: g / vapor[e].molar_mass for e, g in feed.trace_grams.items()} if include_traces else {}
    rows, sp_rows, duty_rows = [], [], []
    h_gas_prev = None
    for T in np.arange(T_start, T_end - 1e-9, -dT):
        # Elements left at < 1e-9 of the gas are scavenged by this step's
        # collector: negligible mass, and they destabilize the VCS solver.
        total = sum(inventory.values())
        for el in [e for e, n in inventory.items() if n < SCAVENGE_REL * total]:
            n = inventory.pop(el)
            rows.append({"T": float(T), "element": el, "moles": n, "grams": n * ATOMIC_MASS[el]})
        total = sum(inventory.values())
        if metal_solution:
            major, dilute = dict(inventory), {}
        else:
            major = {e: n for e, n in inventory.items() if n >= DILUTE_SHARE * total}
            dilute = {e: n for e, n in inventory.items() if e not in major}
        eq = equilibrate(major, float(T), P, th, metal_solution=metal_solution)
        if h_gas_prev is not None:
            # heat removed: previous gas (at T_prev) -> gas + condensate at T
            duty_rows.append({"T": float(T), "duty_J": h_gas_prev - eq.enthalpy,
                              "gas_mol": sum(eq.gas.values()), "solver": eq.solver,
                              "converged": eq.converged, "residual": eq.residual,
                              "certified": eq.certified, "n_dilute": len(dilute)})
        h_gas_prev = eq.enthalpy_gas
        cond_el = eq.element_moles("condensed")
        if dilute:
            n_gas_eq = sum(eq.gas.values())
            for el, n in dilute.items():
                p = dilute_chem.chem(el).partition(el, n, float(T), P / ct.one_atm, eq.potentials, n_gas_eq, {})
                cond_el[el] = cond_el.get(el, 0.0) + p.condensed
        n_host = sum(n for name, n in eq.condensed.items() if _is_metal_host(name, th))
        if n_host == 0:
            n_host = sum(eq.condensed.values())
        n_gas = sum(eq.gas.values())
        for name, n in eq.condensed.items():
            sp_rows.append({"T": float(T), "species": name, "moles": n})
        for el, n in cond_el.items():
            if n > 1e-12:
                rows.append({"T": float(T), "element": el, "moles": n, "grams": n * ATOMIC_MASS[el]})
        if traces_gas and chem is not None:
            hosts = chem.hosts_from(eq)
            for el in [e for e in traces_gas if e in chem.traces and traces_gas[e] > 0]:
                p = chem.partition(el, traces_gas[el], float(T), P / ct.one_atm, eq.potentials, n_gas, hosts)
                if p.condensed > 0:
                    rows.append({"T": float(T), "element": el, "moles": p.condensed,
                                 "grams": p.condensed * vapor[el].molar_mass})
                detail_rows.append({"T": float(T), "element": el, "gas": p.gas,
                                    **{f"in_{h}": v for h, v in p.dissolved.items()},
                                    **{f"pure_{k}": v for k, v in p.pure.items()},
                                    **{f"gas_{k}": v for k, v in p.gas_species.items()}})
                traces_gas[el] = p.gas
        rest = {e: n for e, n in traces_gas.items() if chem is None or e not in chem.traces}
        if rest:
            got = partition_step(rest, float(T), P, n_gas, n_host, vapor, gamma)
            for el, n in got.items():
                if n > 0:
                    rows.append({"T": float(T), "element": el, "moles": n, "grams": n * vapor[el].molar_mass})
                    traces_gas[el] -= n
        # Exact bookkeeping: whatever condensed leaves; the rest stays gaseous.
        inventory = {e: max(n - cond_el.get(e, 0.0), 0.0) for e, n in inventory.items()}
        inventory = {e: n for e, n in inventory.items() if n > 0.0}
    gas_left = dict(inventory)
    gas_left.update({e: n for e, n in traces_gas.items() if n > 0})
    return LadderResult(pd.DataFrame(rows), pd.DataFrame(sp_rows), gas_left, list(bands),
                        dict(feed.element_moles), pd.DataFrame(duty_rows),
                        pd.DataFrame(detail_rows).fillna(0.0))
