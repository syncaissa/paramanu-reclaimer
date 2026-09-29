"""Gibbs-energy minimization for an ideal gas plus pure condensed phases.

Two complementary methods, both standard:

1. Gas-phase Newton iteration of Gordon & McBride (NASA RP-1311, the CEA
   algorithm) - fast and robust while no condensed phase is present.

2. The dual (element-potential) problem, used once condensed phases appear.
   With lambda the element potentials / RT, x_k the gas mole fractions and
   g the standard Gibbs energies / RT at (T, 1 atm):

       maximize    b . lambda
       subject to  sum_k exp(a_k . lambda - g_k - ln P) <= 1   (gas phase)
                   a_c . lambda <= g_c   for every condensed species c

   This is a convex program in ~20 variables. Its constraints are exactly the
   equilibrium conditions: condensed species are stable only where their
   constraint is active. Phase amounts then follow from the element balance
   by non-negative least squares over the gas and the active condensed set.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize as sp_minimize, nnls
from scipy.special import logsumexp

LOG_TRACE = -32.0


@dataclass
class GibbsResult:
    n_gas: np.ndarray          # mol of each gas species
    n_cond: dict[int, float]   # condensed index -> mol
    pi: np.ndarray             # element potentials / RT
    iterations: int
    converged: bool
    residual: float            # relative element-balance error


def _gas_newton(A_g, g0_g, b, lnP, max_newton=500):
    """CEA iteration for a gas-only system (b normalized to O(1))."""
    ng, ne = A_g.shape
    ln_n = np.full(ng, np.log(0.1 / ng))
    N = 0.1
    pi = np.zeros(ne)
    for it in range(max_newton):
        n = np.exp(ln_n)
        mu = g0_g + ln_n - np.log(N) + lnP
        An = A_g * n[:, None]
        M = np.zeros((ne + 1, ne + 1))
        r = np.zeros(ne + 1)
        M[:ne, :ne] = A_g.T @ An
        M[:ne, -1] = An.sum(axis=0)
        r[:ne] = b - An.sum(axis=0) + An.T @ mu
        M[-1, :ne] = An.sum(axis=0)
        M[-1, -1] = n.sum() - N
        r[-1] = N - n.sum() + n @ mu
        sol = np.linalg.lstsq(M, r, rcond=None)[0]
        pi, dlnN = sol[:ne], sol[-1]
        dln = -mu + A_g @ pi + dlnN
        major = ln_n - np.log(N) > -18.42
        big = max(5.0 * abs(dlnN), np.max(np.abs(dln[major]), initial=0.0))
        lam = min(1.0, 2.0 / big) if big > 0 else 1.0
        minor = ~major & (dln > 0)
        if np.any(minor):
            cap = np.abs((-(ln_n[minor] - np.log(N)) - 9.2103) / (dln[minor] - dlnN + 1e-300))
            lam = min(lam, cap.min())
        lam = max(lam, 1e-3)
        ln_n = ln_n + lam * dln
        N = float(np.clip(N * np.exp(lam * dlnN), 1e-14, 10.0))
        ln_n = np.clip(ln_n, np.log(N) + LOG_TRACE, np.log(10.0))
        if np.max(np.abs(lam * dln[major]), initial=0.0) < 1e-7 and abs(lam * dlnN) < 1e-7:
            return np.exp(ln_n), pi, it + 1, True
    return np.exp(ln_n), pi, max_newton, False


def _amounts(lam, A_g, g0_g, A_c, g0_c, b, lnP, slack_tol):
    """Gas mole fractions from lambda, then amounts by NNLS on the element balance."""
    lx = A_g @ lam - g0_g - lnP
    lse = logsumexp(lx)
    x = np.exp(lx - lse)
    gas_present = lse > -slack_tol * 10     # gas exists only if sum_k x_k reaches 1
    slack = g0_c - A_c @ lam if len(g0_c) else np.zeros(0)
    active = [int(c) for c in np.where(slack < slack_tol)[0]]
    cols = ([A_g.T @ x] if gas_present else [np.zeros_like(b)]) + [A_c[c] for c in active]
    cols = np.column_stack(cols)
    w = 1.0 / b                                   # relative balance: traces count too
    amounts, _ = nnls(cols * w[:, None], b * w, maxiter=5000)
    resid = np.max(np.abs(cols @ amounts - b) / b)
    return x, active, amounts, resid


def _polish(A_g, g0_g, A_c, g0_c, b, lnP, n_g, n_c, max_newton=200):
    """CEA Newton iteration with the condensed set fixed (RP-1311 eqs 2.24-2.26)."""
    ng, ne = A_g.shape
    nc = len(n_c)
    N = n_g.sum()
    ln_n = np.log(np.maximum(n_g, N * np.exp(LOG_TRACE)))
    n_c = n_c.copy()
    for _ in range(max_newton):
        n = np.exp(ln_n)
        mu = g0_g + ln_n - np.log(N) + lnP
        An = A_g * n[:, None]
        size = ne + nc + 1
        M = np.zeros((size, size))
        r = np.zeros(size)
        M[:ne, :ne] = A_g.T @ An
        M[:ne, ne:ne + nc] = A_c.T
        M[:ne, -1] = An.sum(axis=0)
        r[:ne] = b - An.sum(axis=0) - A_c.T @ n_c + An.T @ mu
        M[ne:ne + nc, :ne] = A_c
        r[ne:ne + nc] = g0_c
        M[-1, :ne] = An.sum(axis=0)
        M[-1, -1] = n.sum() - N
        r[-1] = N - n.sum() + n @ mu
        sol = np.linalg.lstsq(M, r, rcond=None)[0]
        pi, dnc, dlnN = sol[:ne], sol[ne:ne + nc], sol[-1]
        dln = -mu + A_g @ pi + dlnN
        if not (np.all(np.isfinite(sol))):
            return None
        major = ln_n - np.log(N) > -18.42
        big = max(5.0 * abs(dlnN), np.max(np.abs(dln[major]), initial=0.0))
        lam = min(1.0, 2.0 / big) if big > 0 else 1.0
        # keep condensed amounts non-negative
        neg = dnc < 0
        if np.any(neg):
            lam = min(lam, np.min(0.9 * n_c[neg] / -dnc[neg]))
        lam = max(lam, 1e-4)
        ln_n = np.clip(ln_n + lam * dln, np.log(N) + LOG_TRACE, np.log(10.0))
        N = float(np.clip(N * np.exp(lam * dlnN), 1e-14, 10.0))
        n_c = n_c + lam * dnc
        if np.max(np.abs(lam * dln[major]), initial=0.0) < 1e-8 and abs(lam * dlnN) < 1e-8 \
                and (nc == 0 or np.max(np.abs(lam * dnc)) < 1e-10):
            return np.exp(ln_n), n_c, pi
    return np.exp(ln_n), n_c, pi


def _kkt_polish(lam, kinds, amt, A_g, g0_g, A_c, g0_c, b, lnP, solutions):
    """Solve the equilibrium conditions exactly for a fixed set of phases.

    Unknowns: element potentials pi, log amounts of the gas and of each solution,
    amounts of pure phases. Equations: element balances, sum x = 1 in the gas and
    in each solution, and a_c . pi = g_c for each pure phase.
    """
    from scipy.optimize import root

    keep = [(k, d, a) for (k, d), a in zip(kinds, amt) if a > 0]
    if not keep:
        return None
    ne = len(b)

    def unpack(z):
        return z[:ne], z[ne:]

    def fun(z):
        pi, rest = unpack(z)
        bal = np.zeros(ne)
        eqs = []
        for (kind, data, _), v in zip(keep, rest):
            if kind == "gas":
                lx = A_g @ pi - g0_g - lnP
                x = np.exp(lx)
                bal += np.exp(v) * (A_g.T @ x)
                eqs.append(np.log(x.sum()))
            elif kind == "pure":
                bal += v * A_c[data]
                eqs.append(A_c[data] @ pi - g0_c[data])
            else:
                s = solutions[data[0]]
                ls = A_c[s] @ pi - g0_c[s]
                x = np.exp(ls)
                bal += np.exp(v) * (A_c[s].T @ x)
                eqs.append(np.log(x.sum()))
        return np.concatenate([(bal - b) / b, eqs])

    z0 = [lam]
    for kind, data, a in keep:
        z0.append([np.log(a)] if kind in ("gas", "sol") else [a])
    z0 = np.concatenate(z0)
    try:
        sol = root(fun, z0, method="hybr", options={"xtol": 1e-13, "maxfev": 20000})
    except Exception:
        return None
    if not sol.success:
        return None
    pi, rest = unpack(sol.x)
    new_kinds, new_amt = [], []
    for (kind, data, _), v in zip(keep, rest):
        if kind == "gas":
            new_kinds.append(("gas", None)); new_amt.append(np.exp(v))
        elif kind == "pure":
            if v < 0:
                return None
            new_kinds.append(("pure", data)); new_amt.append(v)
        else:
            k = data[0]
            ls = A_c[solutions[k]] @ pi - g0_c[solutions[k]]
            new_kinds.append(("sol", (k, np.exp(ls - logsumexp(ls))))); new_amt.append(np.exp(v))
    # gas composition must be recomputed from the new potentials
    if new_kinds and new_kinds[0][0] == "gas":
        pass
    resid = float(np.max(np.abs(fun(sol.x)[:ne])))
    return pi, new_kinds, np.array(new_amt), resid


def _with_solutions(lam, A_g, g0_g, A_c, g0_c, b, lnP, pure, solutions, scale, its):
    """Phase amounts when ideal solutions are present (NNLS on the element balance)."""
    lx = A_g @ lam - g0_g - lnP
    x_g = np.exp(lx - logsumexp(lx))
    best = None
    for tol in (1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4):
        cols, kinds = [], []
        if logsumexp(lx) > -10 * tol:
            cols.append(A_g.T @ x_g); kinds.append(("gas", None))
        for c in pure:
            if g0_c[c] - A_c[c] @ lam < tol:
                cols.append(A_c[c]); kinds.append(("pure", int(c)))
        for k, s in enumerate(solutions):
            ls = A_c[s] @ lam - g0_c[s]
            if logsumexp(ls) > -10 * tol:
                x_s = np.exp(ls - logsumexp(ls))
                cols.append(A_c[s].T @ x_s); kinds.append(("sol", (k, x_s)))
        if not cols:
            continue
        M = np.column_stack(cols)
        w = 1.0 / b
        amt, _ = nnls(M * w[:, None], b * w, maxiter=5000)
        resid = float(np.max(np.abs(M @ amt - b) / b))
        if best is None or resid < best[-1]:
            best = (kinds, amt, resid)
        if resid < 1e-9:
            break
    kinds, amt, resid = best
    pol = _kkt_polish(lam, kinds, amt, A_g, g0_g, A_c, g0_c, b, lnP, solutions)
    if pol is not None and pol[-1] < resid:
        lam, kinds, amt, resid = pol
    lx = A_g @ lam - g0_g - lnP
    x_g = np.exp(lx - logsumexp(lx))
    n_gas = np.zeros(len(g0_g))
    n_cond: dict[int, float] = {}
    for (kind, data), a in zip(kinds, amt):
        if a <= 0:
            continue
        if kind == "gas":
            n_gas = x_g * a * scale
        elif kind == "pure":
            n_cond[data] = n_cond.get(data, 0.0) + a * scale
        else:
            k, x_s = data
            for idx, xs in zip(solutions[k], x_s):
                n_cond[idx] = n_cond.get(idx, 0.0) + a * xs * scale
    return GibbsResult(n_gas, n_cond, lam, its, bool(resid < 1e-3), resid)


def minimize(A_g: np.ndarray, g0_g: np.ndarray, A_c: np.ndarray, g0_c: np.ndarray,
             b: np.ndarray, P_atm: float, solutions: list[list[int]] | None = None) -> GibbsResult:
    """Equilibrium composition at fixed T and P (b: moles of each element, all > 0).

    solutions: groups of condensed-species indices that form ideal solutions
    (e.g. one liquid-metal alloy). Each group adds the convex constraint
    sum_s exp(a_s . lambda - g_s) <= 1, exactly like the gas phase at P = 1.
    """
    solutions = [list(s) for s in (solutions or []) if s]
    in_sol = {i for s in solutions for i in s}
    pure = np.array([i for i in range(len(g0_c)) if i not in in_sol], dtype=int)
    scale = b.sum()
    bn = b / scale
    lnP = np.log(P_atm)
    n_g, pi, its, ok = _gas_newton(A_g, g0_g, bn, lnP)

    # Is any condensed species supersaturated in the gas-only state?
    if len(g0_c) == 0 or np.min(g0_c - A_c @ pi) > -1e-9:
        res = np.max(np.abs(A_g.T @ n_g - bn)) / bn.max()
        return GibbsResult(n_g * scale, {}, pi, its, ok, float(res))

    def gas_con(lam):
        return -logsumexp(A_g @ lam - g0_g - lnP)

    def gas_jac(lam):
        lx = A_g @ lam - g0_g - lnP
        return -(A_g.T @ np.exp(lx - logsumexp(lx)))

    cons = [{"type": "ineq", "fun": gas_con, "jac": gas_jac}]
    if len(pure):
        Ap, gp = A_c[pure], g0_c[pure]
        cons.append({"type": "ineq", "fun": lambda lam: gp - Ap @ lam, "jac": lambda lam: -Ap})
    for s in solutions:
        As, gs = A_c[s], g0_c[s]
        cons.append({"type": "ineq",
                     "fun": lambda lam, As=As, gs=gs: -logsumexp(As @ lam - gs),
                     "jac": lambda lam, As=As, gs=gs: -(As.T @ np.exp((As @ lam - gs) - logsumexp(As @ lam - gs)))})
    opt = sp_minimize(lambda lam: -bn @ lam, pi, jac=lambda lam: -bn, constraints=cons,
                      method="SLSQP", options={"maxiter": 3000, "ftol": 1e-15})
    lam = opt.x

    if solutions:
        return _with_solutions(lam, A_g, g0_g, A_c, g0_c, bn, lnP, pure, solutions, scale, its + opt.nit)

    best = None
    for slack_tol in (1e-9, 1e-8, 1e-7, 1e-6, 1e-5, 1e-4):
        cand = _amounts(lam, A_g, g0_g, A_c, g0_c, bn, lnP, slack_tol)
        if best is None or cand[-1] < best[-1]:
            best = cand
        if cand[-1] < 1e-9:
            break
    x, active, amounts, resid = best
    keep = [i for i, c in enumerate(active) if amounts[i + 1] > 0]
    active = [active[i] for i in keep]
    n_g = x * amounts[0]
    n_c = np.array([amounts[i + 1] for i in keep])
    Ac_act = A_c[active] if active else np.zeros((0, A_g.shape[1]))
    pol = _polish(A_g, g0_g, Ac_act, g0_c[active], bn, lnP, n_g, n_c) if n_g.sum() > 1e-12 else None
    if pol is not None:
        pg, pc, ppi = pol
        bal = A_g.T @ pg + Ac_act.T @ pc
        pres = np.max(np.abs(bal - bn) / np.maximum(bn, 1e-300))
        if np.all(pc >= 0) and pres < resid:
            n_g, n_c, lam, resid = pg, pc, ppi, float(pres)
    n_cond = {c: n_c[i] * scale for i, c in enumerate(active) if n_c[i] > 0}
    return GibbsResult(n_g * scale, n_cond, lam, its + opt.nit, bool(resid < 1e-4), float(resid))


def refine(A_g: np.ndarray, g0_g: np.ndarray, A_c: np.ndarray, g0_c: np.ndarray, b: np.ndarray,
           P_atm: float, n_gas: np.ndarray, n_cond: dict[int, float], max_iter: int = 30) -> GibbsResult | None:
    """Phase-set iteration of NASA CEA (Gordon & McBride 1994, RP-1311 sec. 3.5),
    started from a previous state: Newton with the condensed set fixed, then add
    the most supersaturated absent phase (a . lambda > g) or drop a phase whose
    amount reaches zero, until no absent phase is supersaturated. Used when the
    certificate (equilibrium.certify) finds a phase the dual solve left out."""
    scale = b.sum()
    bn = b / scale
    lnP = np.log(P_atm)
    active = sorted(int(c) for c, n in n_cond.items() if n > 0)
    n_c = np.array([n_cond[c] / scale for c in active])
    n_g = np.maximum(np.asarray(n_gas, float) / scale, 1e-300)
    pi = None
    for it in range(max_iter):
        Ac = A_c[active] if active else np.zeros((0, A_g.shape[1]))
        pol = _polish(A_g, g0_g, Ac, g0_c[active], bn, lnP, n_g, n_c)
        if pol is None:
            return None
        n_g, n_c, pi = pol
        gone = [i for i, n in enumerate(n_c) if n <= 1e-14]
        if gone:
            active = [c for i, c in enumerate(active) if i not in gone]
            n_c = np.array([n for i, n in enumerate(n_c) if i not in gone])
            continue
        slack = g0_c - A_c @ pi if len(g0_c) else np.zeros(0)
        slack[active] = np.inf
        if len(slack) == 0 or slack.min() > -1e-7:
            break
        j = int(np.argmin(slack))
        els = np.where(A_c[j] > 0)[0]
        active.append(j)
        n_c = np.append(n_c, 1e-3 * min(bn[e] / A_c[j, e] for e in els))
    else:
        return None
    Ac = A_c[active] if active else np.zeros((0, A_g.shape[1]))
    bal = A_g.T @ n_g + Ac.T @ n_c
    resid = float(np.max(np.abs(bal - bn) / bn))
    return GibbsResult(n_g * scale, {c: n_c[i] * scale for i, c in enumerate(active)}, pi, it,
                       bool(resid < 1e-4), resid)
