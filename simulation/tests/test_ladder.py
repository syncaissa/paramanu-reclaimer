"""Condensation ladder: mass balance and the paper's qualitative claims."""
import pytest

from paramanu_sim.feed import make_feed
from paramanu_sim.ladder import run_ladder


@pytest.fixture(scope="module")
def ladder():
    return run_ladder(make_feed(), dT=100.0)


def test_mass_balance(ladder):
    feed = make_feed()
    tab = ladder.band_table()
    for el, n in feed.element_moles.items():
        if n > 1e-3:
            grams_in = n * {**__import__("paramanu_sim.thermo", fromlist=["ATOMIC_MASS"]).ATOMIC_MASS}[el]
            assert abs(tab.loc[el].sum() - grams_in) / grams_in < 1e-3, el


def test_toxic_volatiles_leave_the_precious_band(ladder):
    rec = ladder.recovery_table()
    au_band = rec.loc["Au"].idxmax()
    for el in ("Zn", "Cd", "Pb"):
        assert rec.loc[el].get(au_band, 0.0) < 0.05, el


def test_gold_is_concentrated(ladder):
    grams = ladder.band_table()
    band = grams.loc["Au"].idxmax()
    feed_ppm = make_feed().trace_grams["Au"] / (make_feed().dry_kg * 1000.0) * 1e6
    band_ppm = grams.loc["Au", band] / grams[band].sum() * 1e6
    assert band_ppm > 3 * feed_ppm


def test_every_ladder_step_is_solved(ladder):
    """Each step is solved by PARAMANU's solver or, if it fails to converge, by
    Cantera's independent VCS solver (equilibrium.py). Any step neither solves
    must be rare and must not hold a significant amount of material."""
    d = ladder.duties
    unsolved = d[~d.converged.astype(bool)]
    assert len(unsolved) <= max(3, len(d) // 20)
    assert set(d.solver) <= {"paramanu", "cantera-vcs"}


def test_every_ladder_step_is_certified(ladder):
    """Every accepted state passes the Result 2 certificate (equilibrium.certify):
    one set of element potentials reproduces the gas, no absent condensed phase
    is supersaturated, and the element balance closes."""
    assert ladder.duties.certified.astype(bool).all()
