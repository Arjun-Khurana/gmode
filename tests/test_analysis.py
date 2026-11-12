import numpy as np
import pytest
from scipy.optimize import brentq

import gmode as gm

WL = 1.55
K0 = 2 * np.pi / WL


def grid(half=12.0, n=401):
    return np.linspace(-half, half, n), np.linspace(-half, half, n)


@pytest.mark.parametrize("w1, w2, d, expected", [
    (2.0, 3.0, 0.0, (2 * 2 * 3 / (4 + 9)) ** 2),  # waist mismatch
    (2.0, 2.0, 1.0, np.exp(-1.0 / 4.0)),  # lateral offset
    (2.0, 2.0, 0.0, 1.0),
])
def test_gaussian_overlap_matches_analytic(w1, w2, d, expected):
    x, y = grid()
    a = gm.gaussian_beam(x, y, w1, WL)
    b = gm.gaussian_beam(x, y, w2, WL, center=(d, 0.0))
    assert gm.overlap(a, b) == pytest.approx(expected, rel=1e-6)
    assert gm.field_overlap(a, b) == pytest.approx(expected, rel=1e-6)  # same medium: both measures agree
    assert a.power == pytest.approx(1.0)
    cross = gm.gaussian_beam(x, y, w2, WL, polarization="y")
    assert gm.overlap(a, cross) < 1e-12  # orthogonal polarizations


def te_slab(t=0.22, n1=3.476, n2=1.444, dy=0.004):
    return gm.Project(
        wavelength=WL, materials={"core": gm.ConstantMaterial(n=n1), "clad": gm.ConstantMaterial(n=n2)},
        background="clad", structures=[gm.Rectangle(name="film", material="core", size=(10, t))],
        domain=gm.Domain(size=(dy, 3.0)), mesh=gm.Mesh(dx=dy, dy=dy),
        boundaries=gm.Boundaries(x_min="periodic", x_max="periodic"), solver=gm.SolverSettings(num_modes=2),
    )


def test_slab_power_fraction_and_confinement_match_analytic():
    t, n1, n2 = 0.22, 3.476, 1.444
    ms = te_slab(t, n1, n2).solve()
    i = max(range(len(ms)), key=lambda j: (ms[j].te_fraction > 0.5, ms[j].neff.real))
    neff = brentq(lambda n: np.sqrt(n1**2 - n**2) * np.tan(K0 * np.sqrt(n1**2 - n**2) * t / 2)
                  - np.sqrt(n**2 - n2**2), n2 + 1e-9, n1 - 1e-9)  # single-mode slab: one root in (n2, n1)
    kappa, gamma = K0 * np.sqrt(n1**2 - neff**2), K0 * np.sqrt(neff**2 - n2**2)
    core = t / 2 + np.sin(kappa * t) / (2 * kappa)
    clad = np.cos(kappa * t / 2) ** 2 / gamma
    frac = core / (core + clad)
    assert ms.power_fraction(i, "film") == pytest.approx(frac, abs=5e-3)
    # for a TE slab Re(E x H*) = neff |E|^2, so Gamma = (n_core / neff) * power fraction
    assert ms.confinement(i, "film") == pytest.approx(n1 / neff * frac, rel=1e-2)
    assert ms.confinement(i, "film") > ms.power_fraction(i, "film")
    # regions partition the cross-section
    total = ms.power_fraction(i, "core") + ms.power_fraction(i, "clad")
    assert total == pytest.approx(1.0)


def test_region_masks_follow_drawing_order():
    p = gm.Project(materials={"a": gm.ConstantMaterial(n=2), "b": gm.ConstantMaterial(n=3),
                              "bg": gm.ConstantMaterial(n=1)}, background="bg",
                   structures=[gm.Rectangle(name="big", material="a", size=(2, 2)),
                               gm.Rectangle(name="small", material="b", size=(1, 1))])
    x = np.array([0.0, 0.75, 1.5])
    y = np.zeros(3)
    assert list(p.owner_at(x, y)) == [1, 0, -1]
    assert list(p.region_mask("big", x, y)) == [False, True, False]  # covered where "small" is on top
    assert list(p.region_mask("b", x, y)) == [True, False, False]
    assert list(p.region_mask("bg", x, y)) == [False, False, True]
    with pytest.raises(ValueError, match="no structure or material"):
        p.region_mask("nothing", x, y)


def coupler(gap, **boundaries):
    w = 0.5
    return gm.Project(
        materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
        structures=[gm.Rectangle(name="left", material="Si", center=(-(gap + w) / 2, 0), size=(w, 0.22)),
                    gm.Rectangle(name="right", material="Si", center=((gap + w) / 2, 0), size=(w, 0.22))],
        domain=gm.Domain(size=(3.5, 2.0)), mesh=gm.Mesh(dx=0.02, dy=0.02),
        boundaries=gm.Boundaries(**boundaries), solver=gm.SolverSettings(num_modes=1),
    )


def test_directional_coupler_supermodes():
    # TE supermodes: even (Ex symmetric) with a pec plane, odd with pmc; TE needs y_symmetry pmc
    even = coupler(0.2, x_symmetry="pec", y_symmetry="pmc").solve()[0]
    odd = coupler(0.2, x_symmetry="pmc", y_symmetry="pmc").solve()[0]
    assert even.neff.real > odd.neff.real
    Lc = gm.coupling_length(even, odd)
    assert 5 < Lc < 50  # tens of microns for a 200 nm gap SOI coupler
    assert gm.beat_length(even, odd) == pytest.approx(2 * Lc)
    # each supermode splits its power evenly between the two guides
    ms = coupler(0.2, x_symmetry="pec", y_symmetry="pmc").solve()
    assert ms.power_fraction(0, "left") == pytest.approx(ms.power_fraction(0, "right"), abs=1e-6)
    # weaker coupling at a wider gap
    even4 = coupler(0.4, x_symmetry="pec", y_symmetry="pmc").solve()[0]
    odd4 = coupler(0.4, x_symmetry="pmc", y_symmetry="pmc").solve()[0]
    assert gm.coupling_length(even4, odd4) > 2 * Lc


def test_fiber_coupling_prefers_matched_waist():
    p = gm.Project(materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
                   structures=[gm.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
                   domain=gm.Domain(size=(3.0, 3.0)), mesh=gm.Mesh(dx=0.02, dy=0.02),
                   boundaries=gm.Boundaries(x_symmetry="pec", y_symmetry="pmc"), solver=gm.SolverSettings(num_modes=1))
    m = p.solve()[0]
    waists = np.array([0.15, 0.25, 0.35, 0.5, 0.8, 1.2])
    etas = np.array([gm.gaussian_coupling(m, w) for w in waists])
    assert np.all((etas > 0) & (etas < 1))
    best = int(np.argmax(etas))
    assert 0 < best < len(waists) - 1  # a matched waist exists, comparable to the mode size
    assert 0.6 < etas[best] < 0.99
    assert gm.gaussian_coupling(m, waists[best], polarization="y") < 0.05
    assert gm.gaussian_coupling(m, waists[best], center=(0.5, 0.0)) < etas[best]
    # a standard single-mode fiber (MFD 10.4 um) butt-coupled to a strip: about -20 dB
    assert 10 * np.log10(gm.gaussian_coupling(m, 5.2)) == pytest.approx(-20, abs=2)


def test_examples_load_save_and_solve(tmp_path):
    names = list(gm.examples.catalog())
    assert {"si_strip", "inverse_taper_tip", "curved_slab", "width_sweep_crossing"} <= set(names)
    paths = gm.examples.write_all(tmp_path)
    assert len(paths) == len(names)
    for name, path in zip(names, paths):
        p = gm.examples.load(name)
        assert p.description and gm.Project.load(path) == p
    # spot-check the validation examples against their stated references
    ms = gm.examples.load("si_slab").solve()
    assert ms[0].neff.real == pytest.approx(2.84778, abs=5e-4) and ms[1].neff.real == pytest.approx(2.05332, abs=1e-3)
    tip = gm.examples.load("inverse_taper_tip")
    m = tip.solve()[0]
    assert 10 * np.log10(gm.gaussian_coupling(m, tip.fiber.mfd / 2)) == pytest.approx(-0.46, abs=0.15)
    bend = gm.examples.load("strip_bend").solve()
    te = min(bend, key=lambda m: m.loss_db_per_cm)
    assert te.te_fraction > 0.9 and 2.3 < te.neff.real < 2.6 and te.bend_loss_db_per_90deg < 0.1
    with pytest.raises(ValueError, match="no example"):
        gm.examples.load("nope")
