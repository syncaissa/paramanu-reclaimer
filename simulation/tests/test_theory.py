"""The closed-form results of the paper's design-principles section (Section 4)."""
import math

import pytest

from paramanu_sim import theory
from paramanu_sim.equilibrium import equilibrate
from paramanu_sim.feed import make_feed


def test_vapor_pressure_equals_one_atm_at_boiling_point():
    for el, tb in (("Zn", 1180.0), ("Pb", 2022.0), ("Cu", 2835.0)):
        assert abs(theory.vapor_pressure(el, theory.boiling_point(el)) / 101325.0 - 1.0) < 1e-6
        assert abs(theory.boiling_point(el) - tb) / tb < 0.01


def test_onset_closed_form_accuracy():
    """Within 2% for y >= 1e-4, within 3.5% at y = 1e-6, and never above the exact onset."""
    for el in ("Fe", "Cu", "Zn", "Pb"):
        tb = theory.boiling_point(el)
        dh = theory.enthalpy_of_vaporization(el, tb)
        for y, tol in ((1e-2, 0.02), (1e-4, 0.02), (1e-6, 0.035)):
            exact = theory.condensation_onset(el, y)
            cf = theory.condensation_onset_closed_form(tb, dh, y)
            assert abs(cf - exact) / exact < tol
            assert cf <= exact + 1e-6


def test_fenske_limits():
    assert theory.fenske_min_stages(1.0) == math.inf
    # alpha = 99^2 needs exactly one stage for a 99/99 split
    assert theory.fenske_min_stages(99.0 ** 2) == pytest.approx(1.0)


def test_min_work_is_small_fraction_of_vaporization():
    feed = make_feed()
    w = theory.min_separation_work(feed.element_moles)
    assert 0 < w < 0.1 * 2.9 * 3.6e9


@pytest.mark.parametrize("T", [2600.0, 2200.0, 1800.0])
def test_alloy_solution_conserves_elements(T):
    feed = make_feed()
    eq = equilibrate(feed.element_moles, T, metal_solution=True, min_moles=0.0)
    got = eq.element_moles()
    for el, n in feed.element_moles.items():
        if n > 1e-3:
            assert abs(got[el] - n) / n < 1e-6, el
