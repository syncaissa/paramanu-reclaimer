"""Multiphase chemical equilibrium of a sealed batch at fixed T and P.

Thermodynamic data come from the NASA polynomials shipped with Cantera
(thermo.py); the minimization itself is gibbs.py, an implementation of the
NASA CEA algorithm (Gordon & McBride, RP-1311). Phases: one ideal gas plus
pure stoichiometric condensed phases (no solid or liquid solutions; dilute
trace metals are handled separately in traces.py).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import cantera as ct
import numpy as np

from .gibbs import minimize, refine
from .thermo import ThermoSet, load


@dataclass
class EquilibriumResult:
    T: float
    P: float
    gas: dict[str, float]          # species -> mol
    condensed: dict[str, float]    # condensed species -> mol
    enthalpy: float                # J, total enthalpy of the equilibrium state
    converged: bool
    thermo: ThermoSet
    residual: float = 0.0          # relative element-balance error
    enthalpy_gas: float = 0.0      # J, enthalpy of the gas phase alone
    potentials: dict[str, float] | None = None  # element potentials / RT (Result 2)
    solver: str = "paramanu"                     # which solver produced the state
    certified: bool | None = None                # passed the Result 2 certificate
    certificate: dict | None = None              # largest violation of each condition

    def element_moles(self, phase: str = "all") -> dict[str, float]:
        """Moles of each element in 'gas', 'condensed' or 'all'."""
        out = {e: 0.0 for e in self.thermo.elements}
        sources = []
        if phase in ("gas", "all"):
            sources.append(self.gas)
        if phase in ("condensed", "all"):
            sources.append(self.condensed)
        for moles in sources:
            for name, n in moles.items():
                for e, k in composition(self.thermo, name).items():
                    if e in out:
                        out[e] += n * k
        return out


METALS = {"Fe", "Ni", "Cu", "Cr", "Co", "Pb", "Zn", "Al", "Mg", "Ti", "Si", "Hg"}

_COMP: dict[str, dict[str, float]] = {}
_GAS_MATRIX: dict[int, np.ndarray] = {}


def composition(th: ThermoSet, name: str) -> dict[str, float]:
    if name not in _COMP:
        if name in th.gas.species_names:
            _COMP[name] = dict(th.gas.species(name).composition)
        else:
            for ph in th.condensed:
                if ph.species_names[0] == name:
                    _COMP[name] = dict(ph.species(0).composition)
                    break
    return _COMP[name]


def _gas_matrix(th: ThermoSet) -> np.ndarray:
    key = id(th.gas)
    if key not in _GAS_MATRIX:
        names = th.elements
        _GAS_MATRIX[key] = np.array([[sp.composition.get(e, 0.0) for e in names]
                                     for sp in th.gas.species()])
    return _GAS_MATRIX[key]


_ATOM = {"Al": "AL", "Cl": "CL"}
_FB_GAS: dict = {}
FALLBACK_STATS: list = []          # (T, solver, outcome, seconds) for diagnostics
_FB_PHASE: dict = {}


def _cantera_fallback(element_moles, T, P, th, present, cond, min_moles):
    """Recompute a state that gibbs.minimize failed to converge with Cantera's
    independent multiphase solver (VCS), and recover
    the element potentials from its gas by least squares on
    ln x_k + g_k + ln(P/P0) = a_k . lambda (Result 2), adding a_c . lambda = g_c
    for each pure phase present. Returns None if Cantera fails too."""
    key = id(th)
    if key not in _FB_GAS:
        _FB_GAS[key] = ct.Solution(thermo="ideal-gas", species=th.gas.species())
    gas = _FB_GAS[key]
    phases = []
    for ph in cond:                      # building Cantera phases is slow: build each once
        name = ph.species_names[0]
        if (key, name) not in _FB_PHASE:
            _FB_PHASE[(key, name)] = ct.Solution(thermo="fixed-stoichiometry", species=[ph.species(0)])
        phases.append(_FB_PHASE[(key, name)])
    X = {_ATOM.get(e, e): element_moles[e] for e in present}
    # Cantera's "gibbs" solver was tried as a second fallback; it never rescued a
    # state that VCS could not solve and took ~60 s per call, so only VCS is used.
    for solver in ("vcs",):
        gas.TPX = T, P, X
        mix = ct.Mixture([(gas, sum(X.values()))] + [(c, 0.0) for c in phases])
        mix.T, mix.P = T, P
        t0 = time.perf_counter()
        try:
            mix.equilibrate("TP", solver=solver, max_steps=2000, estimate_equil=-1)
            FALLBACK_STATS.append((T, solver, "ok", time.perf_counter() - t0))
            break
        except ct.CanteraError:
            FALLBACK_STATS.append((T, solver, "failed", time.perf_counter() - t0))
            continue
    else:
        return None
    n_gas = mix.phase_moles(0)
    gas_moles = {k: float(x * n_gas) for k, x in zip(gas.species_names, gas.X) if x * n_gas > min_moles}
    condensed = {phases[i - 1].species_names[0]: float(mix.phase_moles(i))
                 for i in range(1, mix.n_phases) if mix.phase_moles(i) > min_moles}
    # element potentials
    th.gas.TP = T, ct.one_atm
    g0 = dict(zip(th.gas.species_names, th.gas.standard_gibbs_RT))
    rows, rhs = [], []
    for k, n in gas_moles.items():
        x = n / n_gas
        if x > 1e-14:
            comp = th.gas.species(k).composition
            rows.append([comp.get(e, 0.0) for e in present])
            rhs.append(math.log(x) + g0[k] + math.log(P / ct.one_atm))
    for ph in phases:
        name = ph.species_names[0]
        if name in condensed:
            ph.TP = T, ct.one_atm
            rows.append([ph.species(0).composition.get(e, 0.0) for e in present])
            rhs.append(float(ph.standard_gibbs_RT[0]))
    lam = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0]
    h_g = th.gas.standard_enthalpies_RT * ct.gas_constant / 1000.0 * T
    idx = {k: i for i, k in enumerate(th.gas.species_names)}
    H_gas = sum(n * h_g[idx[k]] for k, n in gas_moles.items())
    H = H_gas
    for ph in phases:
        name = ph.species_names[0]
        if name in condensed:
            ph.TP = T, ct.one_atm
            H += condensed[name] * ph.enthalpy_mole / 1000.0
    res = EquilibriumResult(T, P, gas_moles, condensed, H, True, th, 0.0, H_gas,
                            dict(zip(present, map(float, lam))))
    bal = res.element_moles("all")
    res.residual = max(abs(bal[e] - element_moles[e]) / element_moles[e] for e in present)
    res.solver = f"cantera-{solver}"
    return res


def certify(eq: "EquilibriumResult", element_moles: dict[str, float],
            tol: float = 1e-4, share_floor: float = 1e-9) -> tuple[bool, dict]:
    """Certificate of equilibrium from Result 2 (duality), independent of the
    solver that produced the state. One set of element potentials lambda must
    satisfy, within `tol`:
      gas species present:   ln x_k = a_k . lambda - g_k - ln(P/P0)
      gas species absent:    a_k . lambda - g_k - ln(P/P0) <= ln(x_min)
      condensed present:     a_c . lambda = g_c
      condensed absent:      a_c . lambda <= g_c   (nothing supersaturated)
    and the element balance must close for every element above share_floor of
    the batch. lambda is fitted to the state by least squares, so the test does
    not trust any solver's own potentials."""
    th, T, P = eq.thermo, eq.T, eq.P
    lnP = math.log(P / ct.one_atm)
    total = sum(element_moles.values())
    present = [e for e in th.elements if element_moles.get(e, 0.0) > 0]
    th.gas.TP = T, ct.one_atm
    g0 = th.gas.standard_gibbs_RT
    names = th.gas.species_names
    N = sum(eq.gas.values())
    rows, rhs = [], []
    for k, n in eq.gas.items():
        if N > 0 and n / N > 1e-12:
            rows.append([th.gas.species(k).composition.get(e, 0.0) for e in present])
            rhs.append(math.log(n / N) + g0[names.index(k)] + lnP)
    cond_all = [ph for ph in th.condensed_at(T) if set(ph.species(0).composition) <= set(present)]
    for ph in cond_all:
        if ph.species_names[0] in eq.condensed:
            ph.TP = T, ct.one_atm
            rows.append([ph.species(0).composition.get(e, 0.0) for e in present])
            rhs.append(float(ph.standard_gibbs_RT[0]))
    lam = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0]
    L = dict(zip(present, lam))
    v_gas = 0.0
    x_min = 1e-12
    preds = []
    for k, name in enumerate(names):
        comp = th.gas.species(k).composition
        if not set(comp) <= set(present):
            continue
        pred = sum(c * L[e] for e, c in comp.items()) - g0[k] - lnP
        preds.append(pred)
        if N <= 0:
            continue
        x = eq.gas.get(name, 0.0) / N
        if x > x_min:
            v_gas = max(v_gas, abs(math.log(x) - pred))
        else:
            v_gas = max(v_gas, pred - math.log(x_min))       # predicted far above what is there
    if N <= 0 and preds:
        # no gas: the gas phase must be unstable, sum of predicted mole fractions <= 1
        m = max(preds)
        v_gas = max(0.0, m + math.log(sum(math.exp(q - m) for q in preds)))
    v_cond_present, v_cond_absent = 0.0, 0.0
    for ph in cond_all:
        ph.TP = T, ct.one_atm
        a_lam = sum(c * L[e] for e, c in ph.species(0).composition.items())
        gap = a_lam - float(ph.standard_gibbs_RT[0])
        if ph.species_names[0] in eq.condensed:
            v_cond_present = max(v_cond_present, abs(gap))
        else:
            v_cond_absent = max(v_cond_absent, gap)           # > 0 means supersaturated
    bal = eq.element_moles("all")
    v_bal = max((abs(bal[e] - element_moles[e]) / element_moles[e] for e in present
                 if element_moles[e] > share_floor * total), default=0.0)
    report = {"gas": v_gas, "condensed_present": v_cond_present,
              "condensed_absent": v_cond_absent, "balance": v_bal}
    ok = v_gas <= tol and v_cond_present <= tol and v_cond_absent <= tol and v_bal <= tol
    return ok, report


def repair(eq: "EquilibriumResult", element_moles: dict[str, float]) -> "EquilibriumResult":
    """Recover phase amounts from a state whose element potentials are right but
    whose amounts are not (the dilute-element failure of gibbs.py).

    1. Every dilute element whose balance is off gets its own potential re-solved
       with the others fixed (a one-variable, monotone equation, as in the trace
       chemistry): gas moles of the element = its total minus what the present
       condensed phases hold.
    2. Gas total and condensed amounts are re-solved by non-negative least
       squares on the element balance, with weights floored at 1e-6 of the batch
       so that no trace element dominates.
    Returns a new EquilibriumResult (solver tag '+repair'); certify() decides."""
    from scipy.optimize import nnls
    th, T, P = eq.thermo, eq.T, eq.P
    lnP = math.log(P / ct.one_atm)
    present = [e for e in th.elements if element_moles.get(e, 0.0) > 0]
    total = sum(element_moles.values())
    lam = dict(eq.potentials)
    th.gas.TP = T, ct.one_atm
    g0 = th.gas.standard_gibbs_RT
    comps = [th.gas.species(k).composition for k in range(th.gas.n_species)]
    use = [k for k, c in enumerate(comps) if set(c) <= set(present)]
    A = np.array([[comps[k].get(e, 0.0) for e in present] for k in use])
    g = g0[use]
    cond_all = [ph for ph in th.condensed_at(T) if set(ph.species(0).composition) <= set(present)]
    cond = [ph for ph in cond_all if ph.species_names[0] in eq.condensed]
    Ac = np.array([[ph.species(0).composition.get(e, 0.0) for e in present] for ph in cond]).reshape(len(cond), len(present))

    def amounts(lam_vec):
        lx = A @ lam_vec - g - lnP
        x = np.exp(lx - np.max(lx))
        x = x / x.sum()
        w = 1.0 / np.maximum(np.array([element_moles[e] for e in present]), 1e-6 * total)
        cols = np.column_stack([A.T @ x] + [Ac[i] for i in range(len(cond))])
        amt, _ = nnls(cols * w[:, None], np.array([element_moles[e] for e in present]) * w, maxiter=5000)
        return x, amt

    lam_vec = np.array([lam[e] for e in present])
    x, amt = amounts(lam_vec)
    for _ in range(8):                       # re-solve dilute potentials, then amounts
        n_gas = amt[0]
        cond_el = Ac.T @ amt[1:] if len(cond) else np.zeros(len(present))
        for j, e in enumerate(present):
            target = element_moles[e] - cond_el[j]
            if element_moles[e] > 1e-6 * total or target <= 0 or not A[:, j].any():
                continue
            def f(u, j=j):
                lv = lam_vec.copy(); lv[j] = u
                lx = A @ lv - g - lnP
                return math.log(max(np.exp(lx) @ A[:, j], 1e-300)) + math.log(n_gas) - math.log(target)
            lo, hi = lam_vec[j] - 5.0, lam_vec[j] + 5.0
            for _k in range(60):
                if f(lo) <= 0: break
                lo -= 5.0
            for _k in range(60):
                if f(hi) >= 0: break
                hi += 5.0
            for _k in range(100):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
            lam_vec[j] = 0.5 * (lo + hi)
        # active set: a phase supersaturated at these potentials must be present
        added = False
        for ph in cond_all:
            if ph in cond:
                continue
            ph.TP = T, ct.one_atm
            a_c = np.array([ph.species(0).composition.get(e, 0.0) for e in present])
            if a_c @ lam_vec - float(ph.standard_gibbs_RT[0]) > 1e-6:
                cond.append(ph)
                added = True
        if added:
            Ac = np.array([[p_.species(0).composition.get(e, 0.0) for e in present] for p_ in cond])
        x, amt = amounts(lam_vec)
        # a condensed phase that received no material is dropped again
        keep = [i for i in range(len(cond)) if amt[1 + i] > 0]
        if len(keep) < len(cond):
            cond = [cond[i] for i in keep]
            Ac = np.array([[p_.species(0).composition.get(e, 0.0) for e in present] for p_ in cond]).reshape(len(cond), len(present))
            x, amt = amounts(lam_vec)
    names = th.gas.species_names
    gas = {names[k]: float(xi * amt[0]) for k, xi in zip(use, x) if xi * amt[0] > 1e-12}
    condensed = {ph.species_names[0]: float(a) for ph, a in zip(cond, amt[1:]) if a > 1e-12}
    h_g = th.gas.standard_enthalpies_RT * ct.gas_constant / 1000.0 * T
    H_gas = sum(n * h_g[names.index(k)] for k, n in gas.items())
    H = H_gas
    for ph in cond:
        if ph.species_names[0] in condensed:
            ph.TP = T, ct.one_atm
            H += condensed[ph.species_names[0]] * ph.enthalpy_mole / 1000.0
    out = EquilibriumResult(T, P, gas, condensed, H, True, th, 0.0, H_gas, dict(zip(present, map(float, lam_vec))))
    bal = out.element_moles("all")
    out.residual = max(abs(bal[e] - element_moles[e]) / element_moles[e] for e in present)
    out.solver = eq.solver + "+repair"
    return out


def equilibrate(element_moles: dict[str, float], T: float, P: float = ct.one_atm,
                thermo: ThermoSet | None = None, min_moles: float = 1e-12,
                allow_condensed: bool = True, metal_solution: bool = False,
                fallback: bool = True) -> EquilibriumResult:
    """Equilibrium state of a closed batch holding `element_moles` at (T, P).

    If PARAMANU's solver (gibbs.py) does not converge, the state is recomputed
    with Cantera's independent multiphase solver (fallback=True, pure phases
    only); result.solver records which solver produced it."""
    th = thermo or load()
    present = [e for e in th.elements if element_moles.get(e, 0.0) > 0]
    col = [th.elements.index(e) for e in present]
    A_all = _gas_matrix(th)
    other = [i for i in range(len(th.elements)) if i not in col]
    gas_idx = np.where(A_all[:, other].sum(axis=1) == 0)[0] if other else np.arange(A_all.shape[0])
    th.gas.TP = T, ct.one_atm
    g0_g = th.gas.standard_gibbs_RT[gas_idx]
    A_g = A_all[np.ix_(gas_idx, col)]

    cond = [ph for ph in th.condensed_at(T) if set(ph.species(0).composition) <= set(present)] \
        if allow_condensed else []
    solutions = None
    if metal_solution and allow_condensed:
        # one ideal liquid-metal solution: every liquid pure metal, extrapolated a
        # little below its melting point (alloys melt lower than pure metals)
        liq = [ph for ph in th.condensed
               if ph.species_names[0].endswith("(L)") and len(ph.species(0).composition) == 1
               and next(iter(ph.species(0).composition)) in METALS
               and set(ph.species(0).composition) <= set(present)
               and 0.6 * ph.species(0).thermo.min_temp <= T <= ph.species(0).thermo.max_temp]
        cond = [ph for ph in cond if ph not in liq] + liq
        solutions = [list(range(len(cond) - len(liq), len(cond)))] if liq else None
    for ph in cond:
        ph.TP = T, ct.one_atm
    A_c = np.array([[ph.species(0).composition.get(e, 0.0) for e in present] for ph in cond]).reshape(len(cond), len(present))
    g0_c = np.array([ph.standard_gibbs_RT[0] for ph in cond])
    b = np.array([element_moles[e] for e in present])

    res = minimize(A_g, g0_g, A_c, g0_c, b, P / ct.one_atm, solutions)
    if fallback and not solutions and allow_condensed:
        ours = _result(res, th, T, P, gas_idx, cond, present, min_moles)
        ok, rep = certify(ours, element_moles)
        ours.certified, ours.certificate = bool(ok), rep
        if ok:
            return ours
        candidates = [ours]
        ref = refine(A_g, g0_g, A_c, g0_c, b, P / ct.one_atm, res.n_gas, res.n_cond)
        if ref is not None:
            fixed = _result(ref, th, T, P, gas_idx, cond, present, min_moles)
            ok, rep = certify(fixed, element_moles)
            fixed.certified, fixed.certificate = bool(ok), rep
            fixed.solver = "paramanu+phase-set"
            if ok:
                return fixed
            candidates.append(fixed)
        fb = _cantera_fallback(element_moles, T, P, th, present, cond, min_moles)
        if fb is not None:
            ok, rep = certify(fb, element_moles)
            fb.certified, fb.certificate = bool(ok), rep
            if ok:
                return fb
            candidates.append(fb)
        fixed = repair(ours, element_moles)
        ok, rep = certify(fixed, element_moles)
        fixed.certified, fixed.certificate = bool(ok), rep
        if ok:
            return fixed
        candidates.append(fixed)
        # none certified: return the least-violating state, flagged
        return min(candidates, key=lambda r: max(r.certificate.values()))

    return _result(res, th, T, P, gas_idx, cond, present, min_moles)


def _result(res, th, T, P, gas_idx, cond, present, min_moles) -> EquilibriumResult:
    th.gas.TP = T, ct.one_atm
    names = th.gas.species_names
    h_g = th.gas.standard_enthalpies_RT[gas_idx] * ct.gas_constant / 1000.0 * T   # J/mol
    gas = {names[k]: float(n) for k, n in zip(gas_idx, res.n_gas) if n > min_moles}
    H = float(res.n_gas @ h_g)
    H_gas = H
    condensed = {}
    for c, n in res.n_cond.items():
        cond[c].TP = T, ct.one_atm
        if n > min_moles:
            condensed[cond[c].species_names[0]] = float(n)
        H += n * cond[c].enthalpy_mole / 1000.0
    return EquilibriumResult(T, P, gas, condensed, H, res.converged, th, res.residual, H_gas,
                             dict(zip(present, map(float, res.pi))))
