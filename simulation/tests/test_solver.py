"""Solver correctness: conservation, agreement with Cantera, known boiling points."""
import numpy as np
import pytest

from paramanu_sim.equilibrium import equilibrate
from paramanu_sim.feed import make_feed
from paramanu_sim.validation import CRC_BOILING_K, boiling_point, gas_crosscheck


@pytest.mark.parametrize("T", [6000.0, 2500.0, 1800.0, 1200.0, 700.0, 300.0])
def test_element_conservation_heap(T):
    feed = make_feed()
    eq = equilibrate(feed.element_moles, T, min_moles=0.0)
    got = eq.element_moles()
    for el, n in feed.element_moles.items():
        if n > 1e-3:
            assert abs(got[el] - n) / n < 1e-3, (el, got[el], n)


@pytest.mark.parametrize("T", [1500.0, 3000.0])
def test_gas_phase_matches_cantera(T):
    df = gas_crosscheck({"C": 1, "H": 4, "O": 1.5, "N": 2, "Si": 0.3, "Fe": 0.1, "Cl": 0.05}, T)
    assert df.rel_diff.abs().max() < 1e-6


@pytest.mark.parametrize("el", ["Fe", "Cu", "Zn", "Pb", "Hg", "Mg", "Na"])
def test_boiling_points_within_one_percent(el):
    tb = boiling_point(el, tol=1.0)
    assert abs(tb - CRC_BOILING_K[el]) / CRC_BOILING_K[el] < 0.01


def test_pure_element_below_boiling_is_condensed():
    eq = equilibrate({"Fe": 1.0}, 2000.0)
    assert sum(eq.condensed.values()) == pytest.approx(1.0, rel=1e-6)
