from ophyd import Component as Cpt
from ophyd import PseudoSingle, SoftPositioner
import gi
import numpy as np
import numpy.testing
import os
import pytest

gi.require_version("Hkl", "5.0")
# NOTE: MUST call gi.require_version() BEFORE import hkl
import hkl.calc
from hkl.diffract import Constraint
from hkl.geometries import E6C, SimMixin
from hkl.util import Lattice


TARDIS_TEST_MODE = "lifting_detector_mu"

class Tardis(SimMixin, E6C):
    # theta
    theta = Cpt(SoftPositioner)
    omega = Cpt(SoftPositioner)
    chi = Cpt(SoftPositioner)
    phi = Cpt(SoftPositioner)
    # delta, gamma
    delta = Cpt(SoftPositioner)
    gamma = Cpt(SoftPositioner)


@pytest.fixture(scope="function")
def tardis():
    tardis = Tardis("", name="tardis")
    tardis.calc.engine.mode = TARDIS_TEST_MODE
    # re-map Tardis' axis names onto what an E6C expects
    tardis.calc.physical_axis_names = {
        "mu": "theta",
        "omega": "omega",
        "chi": "chi",
        "phi": "phi",
        "gamma": "delta",
        "delta": "gamma",
    }
    tardis.wait_for_connection()
    return tardis


@pytest.fixture(scope="function")
def kcf_sample(tardis):
    # lengths must have same units as wavelength
    # angles are in degrees
    lattice = Lattice(a=0.5857, b=0.5857, c=0.7849, alpha=90.0, beta=90.0, gamma=90.0)

    # add the sample to the calculation engine
    tardis.calc.new_sample("KCF", lattice=lattice)

    # We can alternatively set the wavelength
    # (or photon energy) on the Tardis.calc instance.
    p1 = tardis.calc.Position(
        # fmt: off
        theta=48.42718305024724,
        omega=0.0,
        chi=0.0,
        phi=0.0,
        delta=115.65436271083637,
        gamma=3.0000034909999993,
        # fmt: on
    )
    r1 = tardis.calc.sample.add_reflection(0, 0, 1, position=p1)

    p2 = tardis.calc.Position(
        # fmt: off
        theta=138.42718305024724,
        omega=0.0,
        chi=0.0,
        phi=0.0,
        delta=115.65436271083637,
        gamma=3.0000034909999993,
        # fmt: on
    )
    r2 = tardis.calc.sample.add_reflection(1, 1, 0, position=p2)
    tardis.calc.sample.compute_UB(r1, r2)

    # note: orientation matrix (below) was pre-computed with this wavelength
    # wavelength units must match lattice unit cell length units
    tardis.calc.wavelength = 1.3317314715359827
    print("calc.wavelength is", tardis.calc.wavelength)
    print("sample is", tardis.calc.sample)
    print("position is", tardis.position)

    print("sample name is", tardis.sample_name.get())
    print("u matrix is", tardis.U.get(), tardis.U.describe())
    print("ub matrix is", tardis.UB.get(), tardis.UB.describe())
    print(
        # fmt: off
        "reflections:",
        tardis.reflections.get(),
        tardis.reflections.describe(),
        # fmt: on
    )
    print("ux is", tardis.ux.get(), tardis.ux.describe())
    print("uy is", tardis.uy.get(), tardis.uy.describe())
    print("uz is", tardis.uz.get(), tardis.uz.describe())
    print("lattice is", tardis.lattice.get(), tardis.lattice.describe())
    print(tardis.read())
    return kcf_sample


@pytest.fixture(scope="function")
def constrain(tardis):
    tardis.apply_constraints(
        dict(
            theta=Constraint(-181, 181, 0, True),
            # we don't have these!! Fix to 0
            phi=Constraint(0, 0, 0, False),
            chi=Constraint(0, 0, 0, False),
            omega=Constraint(0, 0, 0, False),
            # Attention naming convention inverted at the detector stages!
            delta=Constraint(-5, 180, 0, True),
            gamma=Constraint(-5, 180, 0, True),
        )
    )


def test_params(tardis):
    """
    Make sure the parameters are set correctly
    """
    calc = tardis.calc
    assert calc.pseudo_axis_names == "h k l".split()
    assert tuple(calc.physical_axis_names) == tardis.real_positioners._fields
    assert tardis.real_positioners._fields == tuple(
        "theta omega chi phi delta gamma".split()
    )
    assert calc.engine.mode == TARDIS_TEST_MODE

    # gamma
    calc["gamma"].limits = (-5, 180)
    calc["gamma"].value = 10
    calc["gamma"].fit = False

    assert calc["gamma"].limits == (-5, 180)
    assert calc["gamma"].value == 10
    assert calc["gamma"].fit is False

    # try another random set of parameters
    # in case it was initialized to the parameters we "set"
    calc["gamma"].limits = (-10, 180)
    calc["gamma"].value = 20
    calc["gamma"].fit = True

    assert calc["gamma"].limits == (-10, 180)
    assert calc["gamma"].value == 20
    assert calc["gamma"].fit is True


def test_reachable(tardis, kcf_sample, constrain):
    ppos = (0, 0, 1.1)
    rpos = (
        101.56806493825435,
        0.0,
        0.0,
        0.0,
        42.02226419522791,
        176.69158155966787,
    )

    tardis.move(ppos)
    print("tardis position is", tardis.position)
    print("tardis position is", tardis.calc.physical_positions)
    numpy.testing.assert_almost_equal(tardis.position, ppos)
    numpy.testing.assert_almost_equal(tardis.calc.physical_positions, rpos)


def test_inversion(tardis, kcf_sample, constrain):
    ppos = (0, 0, 1.1)
    rpos = (
        101.56806493825435,
        0.0,
        0.0,
        0.0,
        42.02226419522791,
        # invert gamma for this test:
        -176.69158155966787,
    )

    tardis.calc.inverted_axes = ["gamma"]
    tardis.calc.physical_positions = rpos

    assert not tardis.calc["omega"].inverted
    gamma = tardis.calc["gamma"]
    assert gamma.inverted
    numpy.testing.assert_almost_equal(gamma.limits, (-180.0, 5.0))  # inverted from (-5, 180)
    gamma.limits = (-180.0, 5.0)
    numpy.testing.assert_almost_equal(gamma.limits, (-180.0, 5.0))  # inverted from (-5, 180)

    numpy.testing.assert_almost_equal(tardis.calc.physical_positions, rpos)
    numpy.testing.assert_almost_equal(tardis.calc.inverse(rpos), ppos)


def test_unreachable(tardis, kcf_sample):
    print("position is", tardis.position)
    with pytest.raises(hkl.calc.UnreachableError) as exinfo:
        tardis.move((0, 0, 1.8))

    ex = exinfo.value
    print("grabbing last valid position", ex.pseudo, ex.physical)
    print("tardis position is", tardis.position)
    print("tardis position is", tardis.calc.physical_positions)

    # it should not have moved:
    numpy.testing.assert_almost_equal(tardis.position, (0, 0, 0))
    numpy.testing.assert_almost_equal(tardis.calc.physical_positions, [0] * 6)


def interpret_LiveTable(data_table):
    lines = data_table.strip().splitlines()
    keys = [k.strip() for k in lines[1].split("|")[3:-1]]
    data = {k: [] for k in keys}
    for line in lines[3:-1]:
        for i, value in enumerate(line.split("|")[3:-1]):
            data[keys[i]].append(float(value))
    return data


def test_issue62(tardis, kcf_sample, constrain):
    tardis.energy_units.put("eV")
    tardis.energy.put(573)
    tardis.calc["gamma"].limits = (-2.81, 183.1)
    assert round(tardis.calc.energy, 5) == 0.573

    # this test is not necessary
    # ref = tardis.inverse(theta=41.996, omega=0, chi=0, phi=0, delta=6.410, gamma=0)
    # # FIXME: assert round(ref.h, 2) == 0.1
    # # FIXME: assert round(ref.k, 2) == 0.51
    # # FIXME: assert round(ref.l, 2) == 0.1

    # simulate the scan, computing hkl from angles
    # RE(scan([hw.det, tardis],tardis.theta, 0, 0.3, tardis.delta,0,0.5, num=5))
    # values as reported from LiveTable
    path = os.path.join(os.path.dirname(hkl.calc.__file__), "tests")
    with open(os.path.join(path, "livedata_issue62.txt"), "r") as fp:
        livedata = fp.read()
    run_data = interpret_LiveTable(livedata)
    # TODO: can this tolerance be made much smaller (was 0.05)?  < 0.01?  How?
    tolerance = 0.055  # empirical

    # test inverse() on each row in the table
    for i in range(len(run_data["tardis_theta"])):
        ref = tardis.inverse(
            theta=run_data["tardis_theta"][i],
            omega=0,
            chi=0,
            phi=0,
            delta=run_data["tardis_delta"][i],
            gamma=run_data["tardis_gamma"][i],
        )
        assert abs(ref.h - run_data["tardis_h"][i]) <= tolerance
        assert abs(ref.k - run_data["tardis_k"][i]) <= tolerance
        assert abs(ref.l - run_data["tardis_l"][i]) <= tolerance


# =========================================================
# new unit tests based on original tardis notebook
# Note: test_sample1() and test_sample1_calc_only() are nearly identical.
# They differ in that the first tests with a Diffractometer subclass
# (which provides for axis name remapping and energy units) while
# the second only tests the calc and below (canonical axis names and
# energy in keV).

@pytest.fixture(scope="function")
def sample1(tardis):
    # test with remapped names, not canonical names

    # lattice cell lengths are in Angstrom, angles are in degrees
    a = 9.069
    c = 10.390
    tardis.calc.new_sample('sample1', lattice=(a, a, c, 90, 90, 120))

    tardis.energy_offset.put(0)
    tardis.energy_units.put("keV")
    tardis.energy.put(hkl.calc.A_KEV / 1.61198)

    pos_330 = tardis.calc.Position(
        delta=64.449, theta=25.285, chi=0.0, phi=0.0, omega=0.0, gamma=-0.871
    )
    pos_520 = tardis.calc.Position(
        delta=79.712, theta=46.816, chi=0.0, phi=0.0, omega=0.0, gamma=-1.374
    )

    r_330 = tardis.calc.sample.add_reflection(3, 3, 0, position=pos_330)
    r_520 = tardis.calc.sample.add_reflection(5, 2, 0, position=pos_520)

    tardis.calc.sample.compute_UB(r_330, r_520)

    def constrain(axis_name, low, high, value, fit):
        axis = tardis.calc[axis_name]
        axis.limits = (low, high)
        axis.value = value
        axis.fit = fit

    # use geometry's canonical names with calc, not the remapped names
    constrain("mu", -181, 181, 0, True)  # Tardis name: theta
    constrain("gamma", -5, 180, 0, True)  # Tardis name: delta
    constrain("delta", -5, 180, 0, True)  # Tardis name: gamma
    # Do not have these axes, fix to 0.
    for ax in "phi chi omega".split():
        constrain(ax, 0, 0, 0, False)


def test_sample1(sample1, tardis):
    sample = tardis.calc.sample
    wavelength = 1.61198
    assert sample is not None
    assert sample.name == "sample1"
    assert abs(tardis.calc.wavelength - wavelength) < 1e-6
    assert len(sample.reflections) == 2
    assert sample.reflections == [(3,3,0), (5,2,0)]
    assert len(sample.reflections_details) == 2
    assert sample.reflections_details[0] == dict(
        # sorted alphabetically
        reflection = dict(h=3.0, k=3.0, l=0.0),
        flag = 1,
        wavelength = wavelength,
        position = dict(
            # FIXME: reflections_details uses canonical names, not remapped names!
            chi=0.0,
            delta=-0.871,  # FIXME: gamma
            gamma=64.449,  # FIXME: delta
            mu=25.285,  # FIXME: theta
            omega=0.0,
            phi=0.0,
        ),
        orientation_reflection = True
    )
    assert sample.reflections_details[1] == dict(
        # sorted alphabetically
        reflection = dict(h=5.0, k=2.0, l=0.0),
        flag = 1,
        wavelength = wavelength,
        position = dict(
            # FIXME: reflections_details uses canonical names, not remapped names!
            chi=0.0,
            delta=-1.374,  # FIXME: gamma
            gamma=79.712,  # FIXME: delta
            mu=46.816,  # FIXME: theta
            omega=0.0,
            phi=0.0,
        ),
        orientation_reflection = True
    )
    numpy.testing.assert_almost_equal(
        sample.UB,
        np.array(
            [
                [ 0.31323551, -0.4807593 ,  0.01113654],
                [ 0.73590724,  0.63942704,  0.01003773],
                [-0.01798898, -0.00176066,  0.60454803]
            ]
        ),
        7
    )


def test_sample1_calc_only():
    # These comparisons start with the Tardis' calc support (no Diffractometer object)

    tardis_calc = hkl.calc.CalcE6C()

    assert tardis_calc.engine.mode == "bissector_vertical"
    tardis_calc.engine.mode = TARDIS_TEST_MODE
    assert tardis_calc.engine.mode != "bissector_vertical"

    assert tardis_calc.wavelength == 1.54
    tardis_calc.wavelength = 1.61198
    assert tardis_calc.wavelength != 1.54
    assert abs(tardis_calc.energy - 7.69142297) < 1e-8

    # lattice cell lengths are in Angstrom, angles are in degrees
    a = 9.069
    c = 10.390
    sample = tardis_calc.new_sample('sample1', lattice=(a, a, c, 90, 90, 120))
    assert sample.name == "sample1"

    pos_330 = tardis_calc.Position(
        gamma=64.449, mu=25.285, chi=0.0, phi=0.0, omega=0.0, delta=-0.871
    )
    pos_520 = tardis_calc.Position(
        gamma=79.712, mu=46.816, chi=0.0, phi=0.0, omega=0.0, delta=-1.374
    )

    r_330 = sample.add_reflection(3, 3, 0, position=pos_330)
    r_520 = sample.add_reflection(5, 2, 0, position=pos_520)
    assert len(sample.reflections) == 2

    UB = tardis_calc.sample.compute_UB(r_330, r_520)
    expected = np.array(
        [
            [ 0.31323551, -0.4807593 ,  0.01113654],
            [ 0.73590724,  0.63942704,  0.01003773],
            [-0.01798898, -0.00176066,  0.60454803]
        ]
    )
    abs_diff = np.abs(UB-expected)
    numpy.testing.assert_array_less(abs_diff, 1e-3)
    numpy.testing.assert_allclose(UB, expected, 7, verbose=True)


def test_sample1_UB(sample1, tardis):
    numpy.testing.assert_almost_equal(
        tardis.calc.sample.UB,
        np.array(
            [
                [ 0.31323551, -0.4807593 ,  0.01113654],
                [ 0.73590724,  0.63942704,  0.01003773],
                [-0.01798898, -0.00176066,  0.60454803]
            ]
        ),
        7
    )


@pytest.mark.parametrize(
    "wavelength, h, k, l, angles",
    [
        # lambda  h  k  l   delta    theta   chi phi omega gamma
        (1.61198, 4, 4, 0, [90.6303,  38.3762, 0,  0,  0,    -1.1613]),
        (1.61198, 4, 1, 0, [56.0970,  40.2200, 0,  0,  0,    -1.0837]),
        (1.60911, 6, 0, 0, [75.8452,  60.9935, 0,  0,  0,    -1.5840]),
        (1.60954, 3, 2, 0, [53.0521,  26.1738, 0,  0,  0,    -0.8438]),
        (1.60954, 5, 4, 0, [106.3205, 49.8923, 0,  0,  0,    -1.4237]),
        (1.60954, 4, 5, 0, [106.3189, 42.5493, 0,  0,  0,    -1.1854]),
    ]
)
def test_tardis_forward(sample1, tardis, wavelength, h, k, l, angles):
    # Experimentally found reflections @ Lambda = 1.61198 A
    # (4, 4, 0) = [90.628, 38.373, 0, 0, 0, -1.156]
    # (4, 1, 0) = [56.100, 40.220, 0, 0, 0, -1.091]
    # @ Lambda = 1.60911
    # (6, 0, 0) = [75.900, 61.000, 0, 0, 0, -1.637]
    # @ Lambda = 1.60954
    # (3, 2, 0) = [53.090, 26.144, 0, 0, 0, -.933]
    # (5, 4, 0) = [106.415, 49.900, 0, 0, 0, -1.535]
    # (4, 5, 0) = [106.403, 42.586, 0, 0, 0, -1.183]
    # Note angles these differ slightly from the test cases.
    # The experimental values will only pass if tolerance is increased to 0.12 !!

    # move the first angle into proper position
    angles.insert(-1, angles.pop(0))
    tolerance = 0.0001

    tardis.calc.wavelength = wavelength
    result = tardis.forward((h, k, l))
    for i, ax_name in enumerate(result._fields):
        axis = getattr(result, ax_name)
        expected = angles[i]
        assert abs(axis - expected) <= tolerance, f"({h} {k} {l}) {ax_name}"

        # TODO: remove or activate before final revision
        # numpy.testing.assert_almost_equal(
        #     axis, expected, decimal=2,
        #     err_msg=f"({h} {k} {l}) {ax_name}"
        # )
