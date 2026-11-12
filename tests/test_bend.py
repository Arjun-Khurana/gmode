"""Bend modes against the exact solution of a curved slab (complex-order Bessel functions)."""
import numpy as np
import pytest

import gmode as gm

mp = pytest.importorskip("mpmath")

WL = 1.55
K = 2 * np.pi / WL


def exact_curved_slab(n1, n2, t, R, pol, nu0):
    """Leaky mode of a curved slab with core R - t/2 < r < R + t/2, fields ~ Z(r) exp(i nu phi).

    pol "ey": E along the bend axis (E and dE/dr continuous);
    pol "hy": H along the bend axis (H and (1/n^2) dH/dr continuous).
    Outgoing Hankel field outside, regular Bessel field inside. Returns nu / (k R).
    """
    mp.mp.dps = 30
    R1, R2 = R - t / 2, R + t / 2
    w1, w2 = (1, 1) if pol == "ey" else (1 / n1**2, 1 / n2**2)

    def Z(f, nu, n, r):
        z = K * n * r
        return f(nu, z), K * n * (f(nu - 1, z) - f(nu + 1, z)) / 2

    def det(nu):
        J2a, dJ2a = Z(mp.besselj, nu, n2, R1)
        J1a, dJ1a = Z(mp.besselj, nu, n1, R1)
        Y1a, dY1a = Z(mp.bessely, nu, n1, R1)
        J1b, dJ1b = Z(mp.besselj, nu, n1, R2)
        Y1b, dY1b = Z(mp.bessely, nu, n1, R2)
        H2b, dH2b = Z(mp.hankel1, nu, n2, R2)
        return mp.det(mp.matrix([[J2a, -J1a, -Y1a, 0], [w2 * dJ2a, -w1 * dJ1a, -w1 * dY1a, 0],
                                 [0, J1b, Y1b, -H2b], [0, w1 * dJ1b, w1 * dY1b, -w2 * dH2b]]))

    nu = mp.findroot(det, mp.mpc(nu0, 1e-3), solver="muller", tol=1e-24, maxsteps=200)
    return complex(nu) / (K * R)


def curved_slab(n1, n2, t, R, inner=1.5, outer=5.0, dx=0.005, **solver):
    """Slab of width t at x = 0 bent with radius R measured there; extra room on the outside."""
    return gm.Project(
        wavelength=WL, materials={"core": gm.ConstantMaterial(n=n1), "clad": gm.ConstantMaterial(n=n2)},
        background="clad", structures=[gm.Rectangle(name="core", material="core", size=(t, 10))],
        domain=gm.Domain(center=((outer - inner) / 2, 0), size=(inner + outer, dx)), mesh=gm.Mesh(dx=dx, dy=dx),
        boundaries=gm.Boundaries(x_min="pml", x_max="pml", y_min="periodic", y_max="periodic", pml_layers=60),
        solver=gm.SolverSettings(num_modes=2, bend_radius=R, bend_location=0.0, target_neff=1.7, **solver),
    )


@pytest.mark.parametrize("R", [5.0, 8.0])
def test_curved_slab_matches_exact_solution(R):
    ms = curved_slab(2.0, 1.45, 0.4, R).solve()
    assert len(ms) == 2
    for m in ms:
        pol = "ey" if m.te_fraction < 0.5 else "hy"
        ex = exact_curved_slab(2.0, 1.45, 0.4, R, pol, m.neff.real * K * R)
        assert m.neff.real == pytest.approx(ex.real, abs=2e-4)
        assert m.neff.imag == pytest.approx(ex.imag, rel=0.03)
        assert m.bend_loss_db_per_90deg == pytest.approx(m.loss_db_per_cm * np.pi / 2 * R * 1e-4)


def test_large_radius_recovers_straight_guide_and_mode_shifts_outward():
    def wire(**solver):
        return gm.Project(materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
                          structures=[gm.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
                          domain=gm.Domain(size=(3.0, 2.0)), mesh=gm.Mesh(dx=0.02, dy=0.02),
                          solver=gm.SolverSettings(num_modes=1, **solver))

    straight = wire().solve()[0]
    gentle = wire(bend_radius=1e4).solve()[0]
    assert gentle.neff.real == pytest.approx(straight.neff.real, abs=1e-5)
    tight = wire(bend_radius=2.0).solve()[0]

    def centroid(m):
        I = np.sum(np.abs(m.E) ** 2, 0)
        return m.integrate(I * m.x[:, None]).real / m.integrate(I).real

    assert centroid(tight) > 0.01 > abs(centroid(straight))
    flipped = wire(bend_radius=-2.0).solve()[0]
    assert centroid(flipped) == pytest.approx(-centroid(tight), abs=1e-3)
    assert flipped.neff.real == pytest.approx(tight.neff.real, abs=1e-6)


def test_bend_group_index_matches_discrete_dispersion():
    """The Yee energy n_g includes the bend's mu, so it still equals d(k0 neff)/d(k0)."""
    def solve(wl):
        p = curved_slab(2.0, 1.45, 0.4, 8.0, outer=3.0, dx=0.01)
        p.wavelength = wl
        return [m for m in p.solve() if m.te_fraction < 0.5][0]

    h = 1e-3
    m = solve(WL)
    ng_fd = m.neff.real - WL * (solve(WL + h).neff.real - solve(WL - h).neff.real) / (2 * h)
    assert m.group_index == pytest.approx(ng_fd, rel=1e-4)


def test_bend_validation():
    p = curved_slab(2.0, 1.45, 0.4, 5.0)
    with pytest.raises(ValueError, match="too small"):
        p.model_copy(update={"solver": p.solver.model_copy(update={"bend_radius": 1.0})}).solve()
    with pytest.raises(ValueError, match="symmetry"):
        gm.Project.model_validate({**p.model_dump(), "boundaries": {**p.boundaries.model_dump(),
                                                                    "x_min": "pec", "x_symmetry": "pec"}})
    with pytest.raises(ValueError):
        gm.SolverSettings(bend_radius=0.0)
