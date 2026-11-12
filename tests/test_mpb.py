import numpy as np
import pytest

import gmode as gm

pytest.importorskip("meep")
pytestmark = pytest.mark.mpb


def si_wire(backend):
    periodic = dict(x_min="periodic", x_max="periodic", y_min="periodic", y_max="periodic")
    return gm.Project(
        materials={"Si": gm.ConstantMaterial(n=3.476), "SiO2": gm.ConstantMaterial(n=1.444)},
        background="SiO2",
        structures=[gm.Rectangle(name="core", material="Si", center=(0.3, -0.2), size=(0.5, 0.16))],
        domain=gm.Domain(center=(0.3, -0.2), size=(3.0, 2.0)),
        mesh=gm.Mesh(dx=0.01, dy=0.01),
        boundaries=gm.Boundaries(**periodic),
        solver=gm.SolverSettings(backend=backend, num_modes=2),
    )


def test_fde_and_mpb_agree():
    fde, mpb = si_wire("fde").solve(), si_wire("mpb").solve()
    assert len(mpb) == 2
    for a, b in zip(fde, mpb):
        assert a.neff.real == pytest.approx(b.neff.real, abs=2e-3)
        assert a.te_fraction == pytest.approx(b.te_fraction, abs=0.02)
        assert a.group_index == pytest.approx(b.group_index, rel=5e-3)
        assert b.power == pytest.approx(1.0)
        # the mode sits on the (off-origin) core in both backends' coordinates
        for m in (a, b):
            I = np.sum(np.abs(m.E) ** 2, 0)
            cx = m.integrate(I * m.x[:, None]).real / m.integrate(I).real
            cy = m.integrate(I * m.y[None, :]).real / m.integrate(I).real
            assert (cx, cy) == pytest.approx((0.3, -0.2), abs=0.02)


def test_mpb_rejects_lossy_materials():
    p = si_wire("mpb")
    p.materials["Si"] = gm.ConstantMaterial(n=3.476, k=0.01)
    with pytest.raises(ValueError, match="lossless"):
        p.solve()
