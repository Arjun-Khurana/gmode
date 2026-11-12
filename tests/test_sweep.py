import numpy as np
import pytest

import gmode as gm


def wire(num_modes=3, dx=0.02, **boundaries):
    return gm.Project(
        materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
        structures=[gm.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
        domain=gm.Domain(size=(3.0, 2.0)), mesh=gm.Mesh(dx=dx, dy=dx),
        boundaries=gm.Boundaries(**boundaries), solver=gm.SolverSettings(num_modes=num_modes),
    )


def test_parameter_paths():
    p = wire()
    assert gm.set_parameter(p, "structures.core.size.0", 0.7).structures[0].size == (0.7, 0.22)
    assert gm.set_parameter(p, "structures.0.center.1", 0.1).structures[0].center == (0.0, 0.1)
    assert gm.set_parameter(p, "wavelength", 1.31).wavelength == 1.31
    assert gm.set_parameter(p, "mesh.step", 0.01).mesh.dy == 0.01
    assert gm.set_parameter(p, "boundaries.pml_layers", 12.0).boundaries.pml_layers == 12
    assert gm.get_parameter(p, "structures.core.size.1") == 0.22
    q = p.model_copy(update={"materials": {**p.materials, "Si": gm.ConstantMaterial(n=3.5)}})
    assert gm.set_parameter(q, "materials.Si.n", 3.4).materials["Si"].n == 3.4
    assert p.structures[0].size == (0.5, 0.22)  # the original is untouched
    for bad in ("structures.nope.size.0", "structures.core.material", "nothing", "structures.core.size.5"):
        with pytest.raises(ValueError):
            gm.set_parameter(p, bad, 1.0)
    with pytest.raises(ValueError):
        gm.set_parameter(p, "mesh.dx", -1.0)  # validated like any edit


def test_overlap_identifies_modes():
    ms = wire(num_modes=3).solve()
    O = np.array([[a.overlap(b) for b in ms] for a in ms])
    assert np.allclose(np.diag(O), 1.0)
    assert np.all(O[~np.eye(3, dtype=bool)] < 0.05)
    # invariant to phase and scale
    m = ms[0]
    scaled = gm.Mode(**{**m.__dict__, "E": -2j * m.E, "H": -2j * m.H})
    assert m.overlap(scaled) == pytest.approx(1.0)


def test_width_sweep_tracks_modes_through_crossing():
    """TE1 overtakes TM0 near w = 0.66 um; tracks keep their polarization while n_eff order swaps."""
    widths = np.linspace(0.45, 0.95, 11)
    r = gm.sweep(wire(num_modes=3), "structures.core.size.0", widths, workers=1)
    assert r.neff.shape == (11, 3) and np.all(np.isfinite(r.neff))
    te0, tm0, te1 = 0, 1, 2
    assert np.all(r.te_fraction[:, te0] > 0.9)
    assert np.all(r.te_fraction[:, tm0] < 0.1)
    assert np.all(r.te_fraction[:, te1] > 0.5)
    # the crossing really happens inside the sweep...
    assert r.neff[0, te1].real < r.neff[0, tm0].real and r.neff[-1, te1].real > r.neff[-1, tm0].real
    # ...and every track's n_eff stays smooth (no jumps from swapping)
    assert np.all(np.diff(r.neff.real, axis=0) > 0)
    assert np.nanmin(r.overlap) > 0.9
    assert r.label == "core width (µm)"


def test_wavelength_sweep_group_index_and_dispersion():
    wl = np.linspace(1.50, 1.60, 7)
    r = gm.sweep(wire(num_modes=1, x_symmetry="pec", y_symmetry="pmc"), "wavelength", wl, workers=1)
    n = r.neff[:, 0].real
    ng_fd = n - wl * np.gradient(n, wl, edge_order=2)
    assert r.group_index[1:-1, 0] == pytest.approx(ng_fd[1:-1], rel=2e-5)
    D = r.dispersion()[:, 0]
    lam = wl * 1e-6
    d2n = np.gradient(np.gradient(n, lam, edge_order=2), lam, edge_order=2)
    D_from_neff = -lam / 299792458.0 * d2n * 1e6
    assert D[2:-2] == pytest.approx(D_from_neff[2:-2], rel=0.02)
    assert 300 < D[3] < 900  # anomalous, a few hundred ps/(nm km) for this strip at 1550 nm
    assert r.wavelengths == pytest.approx(wl)
    with pytest.raises(ValueError, match="wavelength"):
        gm.sweep(wire(num_modes=1), "structures.core.size.0", [0.5, 0.6, 0.7], workers=1).dispersion()


def test_parallel_matches_serial_and_keeps_fields():
    p = wire(num_modes=2, dx=0.04)
    values = np.linspace(0.45, 0.6, 4)
    serial = gm.sweep(p, "structures.core.size.0", values, workers=1)
    parallel = gm.sweep(p, "structures.core.size.0", values, workers=2, keep_fields=True)
    assert parallel.neff == pytest.approx(serial.neff, abs=1e-10)
    m = parallel.mode(2, 1)
    assert m.neff == pytest.approx(parallel.neff[2, 1])
    assert m.E.shape[0] == 3
    with pytest.raises(ValueError, match="keep_fields"):
        serial.mode(0, 0)


def test_cutoff_leaves_track_empty_and_custom_setter():
    """Shrinking the core cuts TE1 off; its track goes empty instead of grabbing a wrong mode."""
    def width(project, w):
        return gm.set_parameter(project, "structures.core.size.0", w)

    p = wire(num_modes=3, dx=0.04, x_min="pml", x_max="pml", y_min="pml", y_max="pml")
    r = gm.sweep(p, width, [0.6, 0.5, 0.4, 0.3], workers=1)
    assert r.parameter == "width"
    assert np.isfinite(r.neff[0, 2]) and r.te_fraction[0, 2] > 0.5
    lost = ~np.isfinite(r.neff[:, 2])
    assert list(lost) == [False, False, True, True]  # guided at 0.6 and 0.5 um, cut off below
    assert np.all(np.isfinite(r.neff[:, :2]))


def test_ordering_cache_reused():
    from gmode.solvers import fde

    if fde.pymetis is None:
        pytest.skip("pymetis not installed (the fallback ordering is not cached)")
    fde._ORDERINGS.clear()
    p = wire(num_modes=1, dx=0.04)
    p.solve()
    gm.set_parameter(p, "structures.core.size.0", 0.6).solve()
    gm.set_parameter(p, "wavelength", 1.31).solve()
    assert len(fde._ORDERINGS) == 1  # one grid, one ordering
    gm.set_parameter(p, "mesh.step", 0.05).solve()
    assert len(fde._ORDERINGS) == 2


def test_operator_pattern_is_wavelength_independent(monkeypatch):
    """Cancellation residue used to make the sparsity pattern depend on wavelength, which blew up
    the fill of a reused ordering five-fold. After pruning, the pattern is the same at every wavelength."""
    from gmode.solvers import fde

    patterns = []
    orig = fde._shift_invert

    def capture(A, sigma, key=None):
        patterns.append((A.nnz, hash(A.indices.tobytes())))
        return orig(A, sigma) if key is None else orig(A, sigma, key)

    monkeypatch.setattr(fde, "_shift_invert", capture)
    p = wire(num_modes=1, dx=0.04, x_min="pml", x_max="pml", y_min="pml", y_max="pml")
    for wl in (1.5, 1.533, 1.6):
        gm.set_parameter(p, "wavelength", wl).solve()
    assert len(set(patterns)) == 1
