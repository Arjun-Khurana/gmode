import csv

import numpy as np
import pytest

import gmode as gm


def test_modeset_npz_roundtrip(tmp_path):
    p = gm.examples.load("strip_bend")
    p.fiber.mfd = 3.0
    ms = p.solve()
    path = ms.save(tmp_path / "modes.npz")
    back = gm.ModeSet.load(path)
    assert back.project == ms.project and back.backend == "fde" and len(back) == len(ms)
    for a, b in zip(ms, back):
        assert b.neff == a.neff and b.ng == a.ng and b.meta["bend_radius"] == 1.5
        assert np.array_equal(a.E, b.E) and np.array_equal(a.H, b.H) and np.array_equal(a.eps_group, b.eps_group)
        assert b.group_index == a.group_index and b.bend_loss_db_per_90deg == a.bend_loss_db_per_90deg
    assert back.confinement(0, "core") == pytest.approx(ms.confinement(0, "core"))
    with np.load(path) as z:  # plain numpy archive, no pickles
        assert str(z["format"]) == "gmode-modes"


def test_modeset_csv(tmp_path):
    p = gm.examples.load("inverse_taper_tip")
    ms = p.solve()
    rows = list(csv.DictReader(open(ms.to_csv(tmp_path / "modes.csv"))))
    assert len(rows) == len(ms)
    r = rows[0]
    assert float(r["neff_real"]) == pytest.approx(ms[0].neff.real)
    assert float(r["group_index"]) == pytest.approx(ms[0].group_index)
    assert float(r["fiber_coupling_mfd_2.5um"]) == pytest.approx(gm.gaussian_coupling(ms[0], 1.25))


def test_sweep_csv_and_npz(tmp_path):
    p = gm.examples.load("strip_dispersion")
    p.mesh = gm.Mesh(dx=0.04, dy=0.04)
    r = gm.sweep(p, "wavelength", np.linspace(1.5, 1.6, 4), workers=1)
    rows = list(csv.DictReader(open(r.to_csv(tmp_path / "sweep.csv"))))
    assert len(rows) == 4 * r.n_tracks
    assert float(rows[1]["dispersion_ps_per_nm_km"]) == pytest.approx(r.dispersion()[1, 0])
    back = gm.SweepResult.load(r.save(tmp_path / "sweep.npz"))
    assert back.parameter == "wavelength" and back.assignments == r.assignments
    assert np.array_equal(back.neff, r.neff) and back.dispersion() == pytest.approx(r.dispersion())


def test_sweep_csv_leaves_lost_tracks_empty(tmp_path):
    p = gm.examples.load("si_strip")
    p.mesh = gm.Mesh(dx=0.04, dy=0.04)
    p.boundaries = gm.Boundaries(x_min="pml", x_max="pml", y_min="pml", y_max="pml")
    p.solver.num_modes = 3
    r = gm.sweep(p, "structures.core.size.0", [0.6, 0.5, 0.3], workers=1)
    rows = list(csv.DictReader(open(r.to_csv(tmp_path / "w.csv"))))
    lost = [row for row in rows if row["track"] == "2" and row["neff_real"] == ""]
    assert lost  # TE1 is cut off at 0.3 um


def test_wrong_file_type(tmp_path):
    np.savez(tmp_path / "other.npz", format=np.array("something"))
    with pytest.raises(ValueError, match="not a GMode"):
        gm.ModeSet.load(tmp_path / "other.npz")
