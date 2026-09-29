"""Experiment 18 - Independent verification: could the model itself be wrong?

(a) Independent solver. Every equilibrium state of the condensation ladder is
    recomputed with Cantera's multiphase equilibrium solver (the VCS algorithm
    of Smith & Missen, implemented independently of PARAMANU's gibbs.py) from
    the same element totals, and the phase assemblages and amounts compared.
(b) Independent data. The major-element ladder is recomputed with the full
    NASA CEA database (NASA-9 polynomials, thermo.inp, McBride, Zehe & Gordon
    2002 and later updates) in place of Cantera's NASA-7 subset, and the
    condensation temperatures compared.

    python 18_independent_verification.py [path/to/thermo.inp]
"""
import _common  # noqa: F401
import sys
from pathlib import Path

import cantera as ct
import numpy as np
import pandas as pd

from paramanu_sim.equilibrium import certify, equilibrate
from paramanu_sim.feed import make_feed
from paramanu_sim.plotting import RESULTS, record
from paramanu_sim.thermo import load

ct.suppress_thermo_warnings()
th = load()
feed = make_feed()
ATOM = {"Al": "AL", "Cl": "CL"}


def cantera_equilibrium(element_moles, T, P=ct.one_atm):
    """Equilibrium by Cantera's VCS multiphase solver: gas + pure condensed phases."""
    gas = ct.Solution(thermo="ideal-gas", species=th.gas.species())
    cond = [ct.Solution(thermo="fixed-stoichiometry", species=[ph.species(0)])
            for ph in th.condensed_at(T)
            if set(ph.species(0).composition) <= {e for e, n in element_moles.items() if n > 0}]
    X = {ATOM.get(e, e): n for e, n in element_moles.items() if n > 0}
    gas.TPX = T, P, X
    mix = ct.Mixture([(gas, sum(X.values()))] + [(c, 0.0) for c in cond])
    mix.T, mix.P = T, P
    used = None
    for solver in ("vcs", "gibbs"):
        try:
            mix.equilibrate("TP", solver=solver, max_steps=20000, **({"estimate_equil": -1} if solver == "vcs" else {}))
            used = solver
            break
        except ct.CanteraError:
            gas.TPX = T, P, X                      # restart from the atoms
            mix = ct.Mixture([(gas, sum(X.values()))] + [(c, 0.0) for c in cond])
            mix.T, mix.P = T, P
    if used is None:
        return None, None, None
    condensed = {cond[i - 1].species_names[0]: mix.phase_moles(i) for i in range(1, mix.n_phases)}
    return {k: v for k, v in condensed.items() if v > 0}, gas, used


def compare(element_moles, T):
    ours = equilibrate(element_moles, T, ct.one_atm, th, fallback=False)   # PARAMANU's own solver only
    final = equilibrate(element_moles, T, ct.one_atm, th)                   # as used: certified, with backups
    ours_ok, ours_cert = certify(ours, element_moles)
    cert = {"paramanu_certified": ours_ok, "paramanu_worst_violation": max(ours_cert.values()),
            "final_solver": final.solver, "final_certified": bool(final.certified)}
    theirs, gas, used = cantera_equilibrium(element_moles, T)
    if theirs is None:
        return {"T": T, "cantera_solver": "none converged", "same_phase_set": None, **cert}
    total = sum(element_moles.values())
    big = lambda d: {k: v for k, v in d.items() if v > 1e-9 * total}   # noqa: E731
    a, b = big(ours.condensed), big(theirs)
    same_phases = set(a) == set(b)
    rel = max([abs(a.get(k, 0) - b.get(k, 0)) / max(a.get(k, 0), b.get(k, 0)) for k in set(a) | set(b)] or [0.0])
    n_ours = sum(ours.gas.values())
    x_ours = {k: v / n_ours for k, v in ours.gas.items()}
    major = [k for k, v in x_ours.items() if v > 1e-6]
    x_theirs = dict(zip(gas.species_names, gas.X))
    gas_rel = max(abs(x_ours[k] - x_theirs.get(k, 0)) / x_ours[k] for k in major)
    return {"T": T, "cantera_solver": used, "paramanu_converged": bool(ours.converged),
            "same_phase_set": same_phases, "n_condensed": len(a),
            "max_rel_diff_condensed": rel, "max_rel_diff_gas_major": gas_rel,
            "only_ours": ",".join(sorted(set(a) - set(b))), "only_cantera": ",".join(sorted(set(b) - set(a))),
            **cert}


# (a1) the whole heap, closed, from the all-gas state to the cold end
rows = [dict(compare(feed.element_moles, T), case="whole heap")
        for T in np.arange(3000.0, 399.0, -100.0)]
# (a2) the real ladder states: the gas left at each step after removing condensate
from paramanu_sim.ladder import DILUTE_SHARE, run_ladder  # noqa: E402
lad = run_ladder(feed, dT=100.0, include_traces=False)
inv = dict(feed.element_moles)
removed = lad.steps.groupby(["T", "element"]).moles.sum()
for T in sorted(lad.steps["T"].unique(), reverse=True):
    # the elements the ladder gives to the global solver (DILUTE_SHARE and above;
    # rarer elements are placed by the dilute-limit solver, Section 5.12)
    rows.append(dict(compare({e: n for e, n in inv.items() if n >= DILUTE_SHARE * sum(inv.values())}, float(T)),
                     case="ladder step"))
    for el, n in removed.loc[T].items():
        inv[el] = max(inv.get(el, 0.0) - n, 0.0)
solver = pd.DataFrame(rows)
solver.to_csv(RESULTS / "verification_independent_solver.csv", index=False)
both = solver[solver.same_phase_set.notna()]
ok = both[both.paramanu_converged.astype(bool)]           # both solvers converged
record("verification_independent_solver", {
    "states": int(len(solver)), "cantera_converged": int(len(both)),
    "paramanu_not_converged": int((~both.paramanu_converged.astype(bool)).sum()),
    "both_converged": int(len(ok)),
    "same_phase_set": int(ok.same_phase_set.astype(bool).sum()),
    "max_rel_diff_condensed": float(ok.max_rel_diff_condensed.max()),
    "max_rel_diff_gas_major": float(ok.max_rel_diff_gas_major.max()),
    "paramanu_raw_certified": int(solver.paramanu_certified.astype(bool).sum()),
    "final_certified": int(solver.final_certified.astype(bool).sum()),
    "final_by_cantera": int((solver.final_solver == "cantera-vcs").sum())})
print(solver.to_string(index=False, float_format="%.2e"))


# (b) independent data: the full NASA CEA database (NASA-9) instead of Cantera's NASA-7 subset
from paramanu_sim.thermo import EQUILIBRIUM_ELEMENTS, ThermoSet  # noqa: E402
from paramanu_sim.trace_thermo import _float  # noqa: E402

# The full NASA CEA database ships with the code (data/nasa_cea_thermo.NOTICE.txt
# gives its source, license and SHA-256); another copy can be given on the command line.
CEA = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    Path(__file__).resolve().parents[1] / "paramanu_sim" / "data" / "nasa_cea_thermo.inp"
SYM = {e.upper(): e for e in EQUILIBRIUM_ELEMENTS}


SKIPPED: list[str] = []


def cea_species(path):
    L = path.read_text().splitlines()
    i = L.index("thermo") + 2
    gas, cond = [], []
    while i < len(L):
        line = L[i]
        if not line.strip() or line.startswith(("!", "END")):
            i += 1
            continue
        try:
            nint = int(L[i + 1][:2])
        except (ValueError, IndexError):
            i += 1
            continue
        r2 = L[i + 1]
        comp = {}
        for k in range(5):
            f = r2[10 + 8 * k:18 + 8 * k]
            if f[:2].strip() and float(f[2:]) != 0:
                comp[f[:2].strip().upper()] = float(f[2:])
        name = line[:24].split()[0]
        n = 3 if nint == 0 else 2 + 3 * nint
        if nint > 0 and comp and set(comp) <= set(SYM) and not name.endswith(("+", "-")):
            coeffs = [nint]
            for k in range(nint):
                t, c1, c2 = L[i + 2 + 3 * k], L[i + 3 + 3 * k], L[i + 4 + 3 * k]
                coeffs += [float(t[:11]), float(t[11:22])]
                coeffs += [_float(c1[16 * j:16 * j + 16]) for j in range(5)]
                coeffs += [_float(c2[16 * j:16 * j + 16]) for j in range(2)]
                coeffs += [_float(c2[48:64]), _float(c2[64:80])]
            sp = ct.Species(name, {SYM[e]: v for e, v in comp.items()})
            try:
                sp.thermo = ct.Nasa9PolyMultiTempRegion(coeffs[1], coeffs[11 * (nint - 1) + 2], ct.one_atm, coeffs)
                (cond if int(r2[50:52]) != 0 else gas).append(sp)
            except ct.CanteraError:
                SKIPPED.append(name)          # inconsistent temperature ranges in the record
        i += n
    return gas, cond


gas_sp, cond_sp = cea_species(CEA)
names = {s.name for s in gas_sp}
gas_sp = [s for s in gas_sp if s.name in names]
th_cea = ThermoSet(list(EQUILIBRIUM_ELEMENTS), ct.Solution(thermo="ideal-gas", species=gas_sp), [])
for sp in cond_sp:
    try:
        th_cea.condensed.append(ct.Solution(thermo="fixed-stoichiometry", species=[sp]))
    except ct.CanteraError:
        pass
print(f"CEA records skipped for inconsistent temperature ranges: {len(SKIPPED)} {SKIPPED[:8]}")
print(f"CEA database: {len(gas_sp)} gas and {len(th_cea.condensed)} condensed species "
      f"(Cantera subset: {th.gas.n_species} and {len(th.condensed)})")

lad_ref = run_ladder(feed, dT=25.0, include_traces=False)
lad_cea = run_ladder(feed, dT=25.0, include_traces=False, thermo=th_cea)
t_ref, t_cea = lad_ref.condensation_temperature(), lad_cea.condensation_temperature()
b_ref, b_cea = lad_ref.recovery_table(), lad_cea.recovery_table()
data_rows = []
# every element in both ladders, including those that never reach 50% condensed (T50 empty)
for el in sorted(set(b_ref.index) & set(b_cea.index)):
    t1, t2 = t_ref.get(el, np.nan), t_cea.get(el, np.nan)
    data_rows.append({"element": el, "T50_cantera_nasa7": t1, "T50_cea_nasa9": t2,
                      "diff_K": t2 - t1,
                      "main_band_nasa7": b_ref.loc[el].idxmax(), "main_band_nasa9": b_cea.loc[el].idxmax(),
                      "share_main_nasa7": b_ref.loc[el].max(), "share_same_band_nasa9": b_cea.loc[el, b_ref.loc[el].idxmax()]})
data = pd.DataFrame(data_rows)
data.to_csv(RESULTS / "verification_independent_data.csv", index=False)
record("verification_independent_data", {
    "elements": int(len(data)), "same_main_band": int((data.main_band_nasa7 == data.main_band_nasa9).sum()),
    "max_abs_T50_diff_K": float(data.diff_K.abs().max()),
    "median_abs_T50_diff_K": float(data.diff_K.abs().median())})
print(data.to_string(index=False, float_format="%.3f"))
