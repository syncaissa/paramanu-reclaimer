"""Trace-metal chemistry in the dilute limit (Henrian partitioning).

A trace element X at parts per million does not change the major-element
equilibrium, so the element potentials lambda_i of the majors (Result 2,
EquilibriumResult.potentials) are fixed. What remains is one equation in one
unknown, the element potential lambda_X of the trace, from the element balance
of X:

    n_X = sum_gas nu_k N_gas exp(a_k . lambda + nu_k lambda_X - g_k - ln P)
        + sum_hosts N_h exp(lambda_X - g_X(L) - ln gamma_X,h)
        + (pure phases of X, which exist only where a_c . lambda + nu_c lambda_X = g_c)

* Gas: every gas species of X (atoms, chlorides, oxides, ...) in the same ideal
  gas as the majors, x_k = exp(a_k . lambda - g_k - ln P).
* Dissolution: X dissolves in each metal host h condensing at this step
  (N_h moles), with the pure liquid as reference state and the Henrian
  activity coefficient gamma_X,h.
* Pure phases: a condensed phase containing X (Au(cr), AgCl(L), SnO2(cr), ...)
  is stable only where it caps lambda_X; it then holds whatever the gas and
  the hosts cannot.

The left side is a sum of exponentials in lambda_X with positive coefficients,
so it increases strictly and the root is unique (bisection is enough). This is
exact to first order in the trace concentration; tests/test_trace.py checks it
against the full multiphase solver for a trace that the full solver can handle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .trace_thermo import TraceSpecies, load_trace_thermo, trace_elements

# Metals that can host dissolved traces (single-element condensed phases).
HOST_METALS = {"Fe", "Ni", "Cu", "Co", "Cr", "Pb", "Zn", "Al", "Mg", "Ti", "Mn", "Sn"}


@dataclass
class TracePartition:
    element: str
    gas: float                                   # mol still gaseous
    dissolved: dict[str, float]                  # host element -> mol dissolved
    pure: dict[str, float]                       # pure phase -> mol of X in it
    gas_species: dict[str, float] = field(default_factory=dict)   # mol of X per species
    potential: float = 0.0                       # lambda_X

    @property
    def condensed(self) -> float:
        return sum(self.dissolved.values()) + sum(self.pure.values())


def _host_element(name: str, comp: dict[str, float]) -> str | None:
    if len(comp) == 1:
        el = next(iter(comp))
        if el in HOST_METALS and not name.startswith("C("):
            return el
    return None


class TraceChemistry:
    """Partition trace metals between gas, dissolved-in-metal and pure phases."""

    def __init__(self, data_set: str = "central", gamma=None):
        self.species = load_trace_thermo(data_set)
        self.traces = [t for t in trace_elements()
                       if any(t in s.composition for s in self.species)]
        self.gamma = gamma or (lambda solute, host, T: 1.0)
        self._by_trace: dict[str, list[TraceSpecies]] = {}
        for t in self.traces:
            self._by_trace[t] = [s for s in self.species if s.composition.get(t, 0) > 0
                                 and not (set(s.composition) - {t}) & set(self.traces)]

    def _liquid(self, X: str) -> TraceSpecies | None:
        liq = [s for s in self._by_trace[X] if s.phase == "cond" and s.composition == {X: 1.0}
               and "(L)" in s.name]
        return liq[0] if liq else None

    def partition(self, X: str, n_X: float, T: float, P_atm: float,
                  potentials: dict[str, float], n_gas: float,
                  hosts: dict[str, float]) -> TracePartition:
        """Equilibrium split of n_X moles of trace X at one ladder step.

        potentials: element potentials / RT of the majors present;
        n_gas: total moles of gas; hosts: host element -> moles condensing now.
        """
        terms, labels, nus = [], [], []
        for s in self._by_trace[X]:
            if s.phase != "gas" or not set(s.composition) - {X} <= set(potentials):
                continue
            nu = s.composition[X]
            base = sum(c * potentials[e] for e, c in s.composition.items() if e != X)
            terms.append(math.log(n_gas) + base - s.g_RT(T) - math.log(P_atm) + math.log(nu))
            labels.append(("gas", s.name)); nus.append(nu)
        liq = self._liquid(X)
        if liq is not None:
            gL = liq.g_RT(T)
            for h, N_h in hosts.items():
                if N_h > 0 and h != X:
                    terms.append(math.log(N_h) - gL - math.log(self.gamma(X, h, T)))
                    labels.append(("host", h)); nus.append(1.0)
        # pure phases containing X cap its potential
        cap, cap_phase = math.inf, None
        for s in self._by_trace[X]:
            if s.phase != "cond" or not s.valid(T) or not set(s.composition) - {X} <= set(potentials):
                continue
            nu = s.composition[X]
            base = sum(c * potentials[e] for e, c in s.composition.items() if e != X)
            u = (s.g_RT(T) - base) / nu
            if u < cap:
                cap, cap_phase = u, s
        terms, nus = np.array(terms), np.array(nus)

        def log_total(u):                      # ln(moles of X in gas + hosts), and its slope
            v = terms + nus * u
            m = v.max()
            w = np.exp(v - m)
            return m + math.log(w.sum()), float(w @ nus / w.sum())

        target = math.log(n_X)
        pure = {}
        if len(terms) == 0 or (math.isfinite(cap) and log_total(cap)[0] <= target):
            u = cap                             # pure phase takes the remainder
            rest = n_X - (math.exp(log_total(u)[0]) if len(terms) else 0.0)
            pure[cap_phase.name] = max(rest, 0.0)
        else:
            # log_total is convex and increasing in u (a log-sum-exp with positive
            # slopes nu): bracket the root, then Newton steps kept inside the bracket.
            lo, hi = min(cap, 0.0) - 1.0, min(cap, 0.0)
            for _ in range(200):
                if log_total(lo)[0] <= target:
                    break
                lo -= 2.0 * (hi - lo)
            for _ in range(200):
                if log_total(hi)[0] >= target:
                    break
                hi += 2.0 * (hi - lo)
            if not (log_total(lo)[0] <= target <= log_total(hi)[0]):
                raise RuntimeError(f"cannot bracket the potential of {X} at T = {T} K")
            u = 0.5 * (lo + hi)
            for _ in range(100):
                f, slope = log_total(u)
                f -= target
                if f < 0:
                    lo = u
                else:
                    hi = u
                step = u - f / slope
                u = step if lo < step < hi else 0.5 * (lo + hi)
                if abs(f) < 1e-13 or hi - lo < 1e-13:
                    break
        # Split what the pure phase does not hold among gas species and hosts by
        # their shares, computed in log space: at the cold end n_X can be ~1e-300
        # mol, where absolute amounts exp(terms + nu u) would underflow to zero.
        rest = n_X - sum(pure.values())
        gas_sp, dissolved = {}, {}
        if len(terms):
            v = terms + nus * u
            w = np.exp(v - v.max())
            for (kind, name), a in zip(labels, w / w.sum() * rest):
                (gas_sp if kind == "gas" else dissolved)[name] = float(a)
        return TracePartition(X, sum(gas_sp.values()), dissolved, pure, gas_sp, float(u))

    def hosts_from(self, eq) -> dict[str, float]:
        """Host metals condensing in an equilibrium result (element -> mol)."""
        out: dict[str, float] = {}
        for name, n in eq.condensed.items():
            from .equilibrium import composition
            el = _host_element(name, composition(eq.thermo, name))
            if el:
                out[el] = out.get(el, 0.0) + n
        return out


def henry_gamma(scale: dict[tuple[str, str], float] | None = None, factor: float = 1.0):
    """Activity coefficients from data/trace_gamma.json (ln gamma = A/T + B).

    scale: multiply chosen pairs, e.g. {("Au", "Fe"): 2.0} pushes gold's
    coefficient in iron to the top of its uncertainty band. factor multiplies
    every pair (a one-number sensitivity). Pairs without data are ideal
    (gamma = 1) before scaling.
    """
    import json
    from pathlib import Path
    table = {(p["solute"], p["host"]): p for p in
             json.loads((Path(__file__).parent / "data" / "trace_gamma.json").read_text())["pairs"]}
    scale = scale or {}

    def gamma(solute: str, host: str, T: float) -> float:
        p = table.get((solute, host))
        g = math.exp(p["A_K"] / T + p["B"]) if p else 1.0
        return g * scale.get((solute, host), 1.0) * factor

    gamma.table = table
    return gamma
