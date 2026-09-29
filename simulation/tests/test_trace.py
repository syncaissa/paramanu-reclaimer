"""Trace-metal chemistry: data sanity, statistical mechanics, and the dilute
limit checked against the full multiphase solver."""
import math
import re

import cantera as ct
import pytest

from paramanu_sim import trace_thermo as tt
from paramanu_sim.equilibrium import composition, equilibrate
from paramanu_sim.feed import make_feed
from paramanu_sim.thermo import load
from paramanu_sim.trace_chem import TraceChemistry
from paramanu_sim.trace_thermo import TraceSpecies


def _h298(s):
    """H(298.15) from G/RT by the Gibbs-Helmholtz relation, J/mol."""
    T, e = 298.15, 0.01
    return -tt.R * T * T * (s.g_RT(T + e) - s.g_RT(T - e)) / (2 * e)


def test_cea_records_reproduce_their_heats_of_formation():
    text = (tt.DATA / "trace_cea.inp").read_text().splitlines()
    stated = {}
    for i, line in enumerate(text[:-1]):
        if line[:1].isalpha() and not line.startswith(("END", "thermo")) and text[i + 1][:2].strip().isdigit():
            stated[line[:24].split()[0]] = float(text[i + 1][65:80])
    checked = 0
    for s in tt.read_cea():
        if s.name in stated and s.valid(298.15):
            assert abs(_h298(s) - stated[s.name]) < 50.0, s.name
            checked += 1
    assert checked >= 15


def test_burcat_records_reproduce_their_heats_of_formation():
    """Every kept Burcat record states HF298 in its comment; the polynomial must agree."""
    lines = (tt.DATA / "trace_burcat.thr").read_text().splitlines()
    primary = {}                  # header line -> first HF298 stated in its comment block
    for i, line in enumerate(lines):
        if len(line) >= 80 and line[79] == "1":
            j = i - 1
            while j >= 0 and not (len(lines[j]) >= 80 and lines[j][79] == "4"):
                j -= 1
            m = re.findall(r"HF298\s*=\s*(-?[\d.]+)(?:\s*\+/-\s*[\d.]+)?\s*(kcal|kJ)?", " ".join(lines[j + 1:i]))
            if m:
                value, unit = m[0]
                primary[line[:18].strip()] = float(value) * (4.184 if unit == "kcal" else 1.0)
    checked = 0
    for s in tt.read_burcat():
        key = s.source.split(": ")[-1]
        if s.phase == "gas" and key in primary:
            assert abs(_h298(s) / 1000 - primary[key]) < 1.0, s.name
            checked += 1
    assert checked >= 10


def test_statistical_mechanics_reproduces_tabulated_entropy():
    # AgCl(g): NBS tables S298 = 245.92 J/mol/K; HCl(g): NASA/JANAF 186.90
    H, S = tt.rrho_functions(298.15, 143.321, 1, True, [0.12298388], [(341.15, 1)], [(0.0, 1)])
    assert S == pytest.approx(245.92, abs=0.2)
    H, S = tt.rrho_functions(298.15, 36.461, 1, True, [10.59341], [(2885.31, 1)], [(0.0, 1)])
    assert S == pytest.approx(186.90, abs=0.3)


def test_vapor_pressures_hit_the_boiling_points():
    sp = {s.name: s for s in tt.load_trace_thermo("central")}
    for gas, liq, Tb in (("Au", "Au(L)", 3129.0), ("Ag", "Ag(L)", 2435.0), ("Pt", "Pt(L)", 4098.0)):
        p = math.exp(sp[liq].g_RT(Tb) - sp[gas].g_RT(Tb))
        assert 0.6 < p < 1.6, (gas, p)


def _cantera_trace(th, el):
    out = []
    for sp in th.gas.species():
        if el in sp.composition:
            k = th.gas.species_index(sp.name)

            def g(T, k=k):
                th.gas.TP = T, ct.one_atm
                return float(th.gas.standard_gibbs_RT[k])
            out.append(TraceSpecies(sp.name, dict(sp.composition), "gas", 200, 6000, g, "cantera", "tabulated"))
    for ph in th.condensed:
        sp = ph.species(0)
        if el in sp.composition:
            def g(T, ph=ph):
                ph.TP = T, ct.one_atm
                return float(ph.standard_gibbs_RT[0])
            out.append(TraceSpecies(sp.name, dict(sp.composition), "cond", sp.thermo.min_temp,
                                    sp.thermo.max_temp, g, "cantera", "tabulated"))
    chem = TraceChemistry.__new__(TraceChemistry)
    chem.species, chem.traces = tuple(out), [el]
    chem.gamma = lambda a, b, T: 1.0
    chem._by_trace = {el: out}
    return chem


@pytest.mark.parametrize("el,frac,T,alloy", [("Pb", 1e-5, 950.0, False), ("Ni", 1e-6, 2100.0, True)])
def test_dilute_limit_matches_full_solver(el, frac, T, alloy):
    """Put a trace through the full multiphase solver, then remove it, solve the
    majors alone and place the trace with the dilute-limit solver: same answer."""
    th = load()
    b = dict(make_feed().element_moles)
    b.pop(el)
    n = frac * sum(b.values())
    full = equilibrate({**b, el: n}, T, ct.one_atm, th, metal_solution=alloy)
    gas_full = sum(k * composition(th, s).get(el, 0) for s, k in full.gas.items()) / n
    maj = equilibrate(b, T, ct.one_atm, th, metal_solution=alloy)
    hosts = {s: k for s, k in maj.condensed.items()
             if alloy and s.endswith("(L)") and len(composition(th, s)) == 1}
    p = _cantera_trace(th, el).partition(el, n, T, 1.0, maj.potentials, sum(maj.gas.values()), hosts)
    assert 0.02 < gas_full < 0.98                       # a case where the split is non-trivial
    assert p.gas / n == pytest.approx(gas_full, rel=1e-3)
