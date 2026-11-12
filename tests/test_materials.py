import warnings

import numpy as np
import pytest

import gmode as gm

LIBRARY = list(gm.material_library())


def numeric_deps(m, wl):
    h = 1e-5 * wl
    return (m.eps(wl + h) - m.eps(wl - h)) / (2 * h)


# Values at 1.55 um (1.31 um where noted) quoted for these fits in the literature and on refractiveindex.info
@pytest.mark.parametrize("name, wl, n_expected, tol", [
    ("Si", 1.55, 3.4764, 2e-4),
    ("Si", 1.31, 3.5005, 2e-4),
    ("SiO2", 1.55, 1.4440, 1e-4),
    ("SiO2", 0.6328, 1.4570, 1e-4),
    ("Si3N4", 1.55, 1.9963, 2e-4),
    ("LiNbO3_o", 1.55, 2.2111, 2e-4),
    ("LiNbO3_e", 1.55, 2.1376, 2e-4),
    ("GaAs", 1.55, 3.3702, 2e-4),
    ("InP", 1.55, 3.1649, 2e-4),
    ("AlAs", 1.55, 2.8924, 2e-4),
])
def test_reference_indices(name, wl, n_expected, tol):
    assert gm.material(name).index(wl).real == pytest.approx(n_expected, abs=tol)


def test_si_fits_agree():
    """Li's fit (built-in) against Salzberg & Villa's independent Sellmeier fit for silicon."""
    salzberg = gm.SellmeierMaterial(terms=[(10.6684293, 0.301516485**2), (0.0030434748, 1.13475115**2),
                                           (1.54133408, 1104.0**2)])
    wl = np.linspace(1.4, 5.0, 40)
    assert np.max(np.abs(gm.material("Si").index(wl) - salzberg.index(wl))) < 3e-3


@pytest.mark.parametrize("name", LIBRARY)
def test_analytic_derivative_matches_numeric(name):
    m = gm.material(name)
    lo, hi = m.valid_range() or (0.5, 5.0)
    for wl in np.linspace(lo * 1.05, min(hi, 5.0) * 0.95, 5):
        d = m.deps_dwavelength(wl)
        assert d == pytest.approx(numeric_deps(m, wl), rel=1e-5, abs=1e-9)


@pytest.mark.parametrize("name", LIBRARY)
def test_group_index_definition(name):
    m = gm.material(name)
    if np.imag(m.eps(1.55)):
        return  # bulk group index is not meaningful for metals
    h = 1e-4
    dn = (m.index(1.55 + h).real - m.index(1.55 - h).real) / (2 * h)
    assert m.group_index(1.55) == pytest.approx(m.index(1.55).real - 1.55 * dn, rel=1e-7)


@pytest.mark.parametrize("name", ["Au", "Ag", "Al"])
def test_metals_absorb(name):
    eps = gm.material(name).eps(np.array([0.8, 1.55, 3.0]))
    assert np.all(eps.real < 0) and np.all(eps.imag > 0)


def test_rakic_gold_against_published_drude_limit():
    """Far in the infrared the Rakic model is dominated by its Drude term."""
    au = gm.material("Au")
    w = gm.materials.EV_UM / 6.0
    drude = 1 - 0.760 * 9.03**2 / (w * (w + 0.053j))
    assert au.eps(6.0) == pytest.approx(drude, rel=0.05)


def test_algaas_endpoints_match_binary_fits():
    for x, ref in ((0.0, "GaAs"), (1.0, "AlAs")):
        a, b = gm.material("AlGaAs", x=x), gm.material(ref)
        for wl in (1.0, 1.31, 1.55, 2.0):
            assert a.index(wl).real == pytest.approx(b.index(wl).real, rel=3e-3)


def test_algaas_composition_and_gap():
    n = [gm.material("AlGaAs", x=x).index(1.55).real for x in (0.0, 0.2, 0.4, 0.6)]
    assert np.all(np.diff(n) < 0)  # more aluminium, lower index
    a = gm.material("AlGaAs", x=0.3)
    assert a.valid_range()[0] > a.gap_wavelength() == pytest.approx(gm.materials.EV_UM / (1.424 + 1.266 * 0.3 + 0.26 * 0.09), rel=1e-12)
    with pytest.raises(ValueError, match="band gap"):
        a.eps(0.65)
    with pytest.raises(ValueError):
        gm.AlGaAsMaterial(x=1.2)


def test_constant_material_is_non_dispersive():
    m = gm.ConstantMaterial(n=2.0, k=0.1)
    assert m.group_eps(1.3) == m.eps(1.3) == (2 + 0.1j) ** 2
    assert np.shape(m.eps(np.ones(3))) == (3,)


def test_lorentz_drude_conventions():
    m = gm.LorentzDrudeMaterial(eps_inf=2.0, poles=[gm.LorentzPole(strength=4.0, resonance=3.0, damping=0.1)])
    w = gm.materials.EV_UM / 1.0
    assert m.eps(1.0) == pytest.approx(2.0 + 4.0 / (9.0 - w**2 - 0.1j * w))
    assert m.eps(1.0).imag > 0  # exp(-i omega t): absorption has Im(eps) > 0


def test_tabulated_reproduces_smooth_model():
    ref = gm.material("SiO2")
    wl = np.arange(1.2, 1.9001, 0.01)
    tab = gm.TabulatedMaterial(wavelengths=wl[::-1].tolist(), n=ref.index(wl).real[::-1].tolist())
    assert tab.wavelengths[0] == pytest.approx(1.2)  # sorted on construction
    assert tab.wavelength_range == pytest.approx((1.2, 1.9))
    for x in (1.31, 1.55, 1.6789):
        assert tab.index(x).real == pytest.approx(ref.index(x).real, abs=1e-7)
        assert tab.group_index(x) == pytest.approx(ref.group_index(x), abs=2e-4)
    with pytest.raises(ValueError, match="outside the tabulated range"):
        tab.eps(2.0)


def test_tabulated_from_file(tmp_path):
    f = tmp_path / "gold.csv"
    f.write_text("# measured\nwl,n,k\n1500,0.50,10.0\n1550, 0.52, 10.5\n1600,0.55,11.0\n")
    m = gm.TabulatedMaterial.from_file(f, wavelength_unit="nm")
    assert m.wavelengths == pytest.approx([1.5, 1.55, 1.6])
    assert m.index(1.55) == pytest.approx(0.52 + 10.5j)
    assert m.description == "gold"
    with pytest.raises(ValueError, match="same length"):
        gm.TabulatedMaterial(wavelengths=[1, 2], n=[1.0])


def test_library_returns_fresh_copies():
    a = gm.material("Si")
    a.description = "changed"
    assert gm.material("Si").description != "changed"
    with pytest.raises(ValueError, match="no built-in material"):
        gm.material("Unobtainium")


def test_project_library_shorthand_and_json_roundtrip(tmp_path):
    p = gm.Project(
        materials={
            "core": "Si", "clad": "SiO2", "metal": "Au", "ox": "AlOx",
            "alloy": gm.material("AlGaAs", x=0.25),
            "meas": gm.TabulatedMaterial(wavelengths=[1.0, 2.0], n=[1.5, 1.4], k=[0.0, 0.01]),
        },
        background="clad",
        structures=[gm.Rectangle(material=m, size=(0.1, 0.1)) for m in ("core", "metal", "ox", "alloy", "meas")],
    )
    assert isinstance(p.materials["core"], gm.SellmeierMaterial)
    p.save(tmp_path / "p.json")
    q = gm.Project.load(tmp_path / "p.json")
    assert q == p
    assert q.eps_at(0.0, 0.0) == pytest.approx(p.eps_at(0.0, 0.0))
    assert q.materials["alloy"].x == 0.25


def tiny_uniform(material, wavelength):
    return gm.Project(
        wavelength=wavelength, materials={"m": material}, background="m",
        domain=gm.Domain(size=(0.2, 0.2)), mesh=gm.Mesh(dx=0.05, dy=0.05),
        boundaries=gm.Boundaries(x_min="periodic", x_max="periodic", y_min="periodic", y_max="periodic"),
        solver=gm.SolverSettings(num_modes=1),
    )


def test_out_of_range_warns():
    with pytest.warns(UserWarning, match="only valid for 1.2-14 um"):
        tiny_uniform("Si", 1.0).solve()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        tiny_uniform("Si", 1.55).solve()


def test_uniform_dispersive_medium_group_index():
    """A plane wave in a uniform dispersive medium travels at the bulk group velocity."""
    m = tiny_uniform("Si", 1.55).solve()[0]
    si = gm.material("Si")
    assert m.neff.real == pytest.approx(si.index(1.55).real, abs=1e-10)
    assert m.group_index == pytest.approx(si.group_index(1.55), rel=1e-6)
