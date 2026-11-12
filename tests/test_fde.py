import numpy as np
import pytest
from scipy.optimize import brentq, newton

import gmode as gm

WL = 1.55
K0 = 2 * np.pi / WL


def mats(**indices):
    return {k: gm.ConstantMaterial(n=np.real(v), k=np.imag(v)) for k, v in indices.items()}


def slab_project(n_core, n_clad, t, dy=0.005, half_height=1.5, **kw):
    """Slab of thickness t (normal to y), infinite along x via a single periodic cell."""
    return gm.Project(
        wavelength=WL,
        materials=mats(core=n_core, clad=n_clad),
        background="clad",
        structures=[gm.Rectangle(material="core", size=(10, t))],
        domain=gm.Domain(size=(dy, 2 * half_height)),
        mesh=gm.Mesh(dx=dy, dy=dy),
        boundaries=gm.Boundaries(x_min="periodic", x_max="periodic", **kw),
        solver=gm.SolverSettings(num_modes=2),
    )


def analytic_slab(n1, n2, t, pol, k0=K0):
    """Fundamental mode of a symmetric slab; complex n1 allowed."""
    def f(n, n1=n1):
        r = 1 if pol == "te" else n1**2 / n2**2
        kappa = k0 * np.sqrt(n1**2 - n**2 + 0j)
        gamma = k0 * np.sqrt(n**2 - n2**2 + 0j)
        return kappa * np.tan(kappa * t / 2) - r * gamma

    # bracket the fundamental (kappa * t / 2 < pi / 2) of the lossless slab, then follow it into loss
    n1r = np.real(n1)
    lo = max(n2, np.sqrt(max(n1r**2 - (np.pi / (k0 * t)) ** 2, 0))) + 1e-9
    n0 = brentq(lambda n: f(n, n1r).real, lo, n1r - 1e-9)
    if np.imag(n1) == 0:
        return n0
    return newton(f, n0 + 0j, tol=1e-14, maxiter=200)


def te_mode(modeset):
    return max((m for m in modeset if m.te_fraction > 0.5), key=lambda m: m.neff.real)


def tm_mode(modeset):
    return max((m for m in modeset if m.te_fraction < 0.5), key=lambda m: m.neff.real)


def test_uniform_medium_periodic():
    p = gm.Project(
        materials=mats(m=1.5), background="m",
        domain=gm.Domain(size=(0.2, 0.2)), mesh=gm.Mesh(dx=0.05, dy=0.05),
        boundaries=gm.Boundaries(x_min="periodic", x_max="periodic", y_min="periodic", y_max="periodic"),
        solver=gm.SolverSettings(num_modes=2),
    )
    ms = p.solve()
    assert np.allclose(ms.neff, 1.5, atol=1e-10)
    assert np.isclose(ms[0].power, 1.0)


@pytest.mark.parametrize("n_core", [3.476, 3.476 + 0.01j])
@pytest.mark.parametrize("pol", ["te", "tm"])
def test_symmetric_slab_matches_analytic(n_core, pol):
    t = 0.22
    ms = slab_project(n_core, 1.444, t).solve()
    m = te_mode(ms) if pol == "te" else tm_mode(ms)
    expected = analytic_slab(n_core, 1.444, t, pol)
    assert abs(m.neff.real - np.real(expected)) < 1e-3
    if np.imag(n_core):
        assert m.neff.imag == pytest.approx(np.imag(expected), rel=0.02)
    else:
        assert abs(m.neff.imag) < 1e-10


def leaky_te_dispersion(n, n_top, layers, n_sub):
    """TE transverse resonance for top half-space / layers (top to bottom) / radiating substrate."""
    q = K0 * np.sqrt(n**2 - n_top**2)
    a, b = 1.0 + 0j, -q  # E and dE/dy just below the top half-space (decaying upward)
    for nl, t in layers:
        k = K0 * np.sqrt(nl**2 - n**2 + 0j)
        a, b = a * np.cos(k * t) - b * np.sin(k * t) / k, a * k * np.sin(k * t) + b * np.cos(k * t)
    ks = K0 * np.sqrt(n_sub**2 - n**2 + 0j)  # outgoing (downward) wave in the substrate
    return b + 1j * ks * a


def test_leaky_slab_on_substrate_with_pml():
    """SiN slab on a thin oxide buffer over silicon leaks into the substrate."""
    t_core, t_buf = 0.4, 0.6
    p = gm.Project(
        wavelength=WL,
        materials=mats(SiN=2.0, SiO2=1.444, Si=3.476),
        background="SiO2",
        structures=[
            gm.Rectangle(name="core", material="SiN", center=(0, t_core / 2), size=(10, t_core)),
            gm.Rectangle(name="substrate", material="Si", center=(0, -t_buf - 5), size=(10, 10)),
        ],
        domain=gm.Domain(center=(0, 0.2), size=(0.005, 3.0)),
        mesh=gm.Mesh(dx=0.005, dy=0.005),
        boundaries=gm.Boundaries(x_min="periodic", x_max="periodic", y_min="pml"),
        solver=gm.SolverSettings(num_modes=4, target_neff=1.9),
    )
    m = te_mode(p.solve())

    guided = analytic_slab(2.0, 1.444, t_core, "te")
    expected = newton(lambda n: leaky_te_dispersion(n, 1.444, [(2.0, t_core), (1.444, t_buf)], 3.476),
                      guided + 1e-4j, tol=1e-14, maxiter=200)
    assert expected.imag > 1e-5  # the reference really is leaky
    assert abs(m.neff.real - expected.real) < 1e-3
    assert m.neff.imag == pytest.approx(expected.imag, rel=0.05)


def si_wire(dx=0.02, **boundaries):
    return gm.Project(
        wavelength=WL,
        materials=mats(Si=3.476, SiO2=1.444),
        background="SiO2",
        structures=[gm.Rectangle(name="core", material="Si", size=(0.5, 0.16))],
        domain=gm.Domain(size=(3.0, 2.0)),
        mesh=gm.Mesh(dx=dx, dy=dx),
        boundaries=gm.Boundaries(**boundaries),
        solver=gm.SolverSettings(num_modes=2),
    )


@pytest.mark.parametrize("x_sym, y_sym, pick", [("pec", "pmc", te_mode), ("pmc", "pec", tm_mode)])
def test_symmetry_matches_full_domain(x_sym, y_sym, pick):
    full = pick(si_wire().solve())
    half = si_wire(x_symmetry=x_sym, y_symmetry=y_sym).solve()[0]
    assert half.neff == pytest.approx(full.neff, abs=1e-8)
    assert half.E.shape == full.E.shape
    assert np.allclose(np.abs(half.E), np.abs(full.E), atol=1e-6 * np.abs(full.E).max())


def test_si_wire_te0_matches_mpb_reference():
    # MPB, resolution 160 px/um, 3 x 2 um cell: neff = 2.16479, ng = 3.8982
    m = si_wire(dx=0.01, x_symmetry="pec", y_symmetry="pmc").solve()[0]
    assert m.neff.real == pytest.approx(2.16479, abs=1e-3)
    assert m.group_index == pytest.approx(3.8982, rel=3e-3)
    assert m.te_fraction > 0.95


@pytest.mark.parametrize("pol", ["te", "tm"])
def test_dispersive_slab_group_index_matches_analytic(pol):
    """Si slab in SiO2 with Sellmeier materials: n_g from one solve vs d(k0 neff)/d(k0) of the exact solution."""
    si, sio2, t = gm.material("Si"), gm.material("SiO2"), 0.22

    def exact(wl):
        return analytic_slab(si.index(wl).real, sio2.index(wl).real, t, pol, k0=2 * np.pi / wl)

    h = 1e-4
    ng_exact = exact(WL) - WL * (exact(WL + h) - exact(WL - h)) / (2 * h)
    p = slab_project(3.0, 1.4, t)
    p.materials = {"core": si, "clad": sio2}
    ms = p.solve()
    m = te_mode(ms) if pol == "te" else tm_mode(ms)
    assert m.neff.real == pytest.approx(exact(WL), abs=1e-3)
    assert m.group_index == pytest.approx(ng_exact, rel=2e-3)
    # material dispersion is a large part of n_g here
    assert ng_exact - m.neff.real > 0.5


@pytest.mark.parametrize("materials", [{"Si": "Si", "SiO2": "SiO2"}, mats(Si=3.476, SiO2=1.444)])
def test_group_index_equals_discrete_dispersion(materials):
    """The Yee-grid energy n_g is the exact derivative of the discrete neff, even on a coarse mesh."""
    def solve(wl):
        p = si_wire(dx=0.04, x_symmetry="pec", y_symmetry="pmc")
        p.wavelength, p.materials = wl, materials
        return p.solve()[0]

    h = 2e-3
    m = solve(WL)
    ng_fd = m.neff.real - WL * (solve(WL + h).neff.real - solve(WL - h).neff.real) / (2 * h)
    assert m.group_index == pytest.approx(ng_fd, rel=1e-5)


def test_pml_has_no_spurious_modes_above_cladding():
    """With PML on all sides, the modes found above the cladding index are exactly the guided ones.

    A purely imaginary stretch (pml_kappa=0) puts a band of PML modes with Re(neff) > n_clad
    around the target, which displaced the guided modes and slowed the eigensolver ~10x.
    """
    pml = dict(x_min="pml", x_max="pml", y_min="pml", y_max="pml")
    n_clad = 1.444
    box = si_wire(dx=0.04)
    box.solver.num_modes = 4
    guided = [m.neff.real for m in box.solve() if m.neff.real > n_clad + 0.01]
    assert len(guided) == 2  # TE0 and TM0

    p = si_wire(dx=0.04, **pml)
    p.solver.num_modes = 4
    above = [m for m in p.solve() if m.neff.real > n_clad + 0.01]
    assert len(above) == len(guided)
    assert all(abs(m.neff.imag) < 1e-6 for m in above)
    assert above[0].neff.real == pytest.approx(guided[0], abs=1e-5)  # TE0 is well confined
    # TM0 sits near cutoff and feels the PEC box walls, so only loose agreement is expected
    assert above[1].neff.real == pytest.approx(guided[1], abs=1e-2)

    # the property that rules them out: Re(s) >= Im(s) everywhere, so Re(1/s^2) >= 0
    from gmode.grid import build_axis
    for ax in "xy":
        a = build_axis(p, ax)
        for s in (a.s_nodes, a.s_half):
            assert np.all(s.real >= s.imag) and s.imag.max() > 1


def test_project_json_roundtrip(tmp_path):
    p = si_wire(x_symmetry="pec")
    p.structures.append(gm.Polygon.trapezoid("Si", (0, -0.5), 0.4, 0.2, 10))
    p.save(tmp_path / "p.json")
    assert gm.Project.load(tmp_path / "p.json") == p


def test_unknown_material_rejected():
    with pytest.raises(ValueError, match="unknown material"):
        gm.Project(materials=mats(a=1.0), background="a", structures=[gm.Rectangle(material="b", size=(1, 1))])
