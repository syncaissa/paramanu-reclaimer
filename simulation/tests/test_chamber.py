import numpy as np

from paramanu_sim.chamber import saha_ionization, vessel_volume_m3


def test_saha_bounded_and_increasing():
    T = np.linspace(3000, 12000, 50)
    x = saha_ionization({"H": 1.0, "Na": 0.01, "Fe": 0.01}, T, 101325.0)
    assert np.all((x >= 0) & (x <= 1))
    assert np.all(np.diff(x) >= -1e-12)


def test_vessel_volume_ideal_gas():
    assert abs(vessel_volume_m3(1.0, 273.15, 101325.0) - 0.022414) < 1e-4
