import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QPointF, QSettings, Qt  # noqa: E402

import gmode as gm  # noqa: E402
from gmode.gui.app import MainWindow  # noqa: E402
from gmode.gui.dialogs import LibraryDialog  # noqa: E402
from gmode.gui.document import ProjectDocument  # noqa: E402
from gmode.gui.inspector import FloatEditor, TupleEditor  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot, tmp_path):
    empty = gm.Project(materials={"SiO2": "SiO2"}, background="SiO2", domain=gm.Domain(size=(3.0, 2.0)),
                       mesh=gm.Mesh(dx=0.02, dy=0.02), solver=gm.SolverSettings(num_modes=2))
    w = MainWindow(ProjectDocument(empty), in_process_solver=True,
                   settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    w.show()  # not qtbot.addWidget: pytest-qt would close it before we mark it clean
    yield w
    w.doc.undo_stack.setClean()  # closing must not open a "save changes?" dialog
    w.close()
    w.deleteLater()


def type_into(qtbot, line_edit, text):
    line_edit.setFocus()
    line_edit.selectAll()
    qtbot.keyClicks(line_edit, text)
    qtbot.keyClick(line_edit, Qt.Key.Key_Return)


def test_build_and_solve_500x160_wire(window, qtbot):
    """M3 acceptance: draw the 500 x 160 nm Si wire, set symmetry, solve, read TE0."""
    w, doc = window, window.doc
    doc.add_material("Si", gm.material("Si"))
    w.canvas.getPlotItem().vb.setRange(xRange=(-1, 1), yRange=(-1, 1), padding=0)
    w.act_rect.trigger()
    assert doc.selection == ("structure", 0)
    s = doc.project.structures[0]
    assert s.material == "Si"

    size = w.inspector.form.editors["size"]
    center = w.inspector.form.editors["center"]
    assert isinstance(size, TupleEditor)
    type_into(qtbot, size.edits[0], "0.5")
    type_into(qtbot, size.edits[1], "0.16")
    type_into(qtbot, center.edits[0], "0")
    type_into(qtbot, center.edits[1], "0")
    assert doc.project.structures[0].size == (0.5, 0.16)
    assert doc.project.structures[0].center == (0.0, 0.0)

    doc.select(("boundaries",))
    form = w.inspector.form
    form.editors["x_symmetry"].combo.setCurrentText("pec")
    form.editors["y_symmetry"].combo.setCurrentText("pmc")
    doc.select(("mesh",))
    for name in ("dx", "dy"):
        type_into(qtbot, w.inspector.form.editors[name].edit, "0.01")
    assert doc.project.boundaries.x_symmetry == "pec" and doc.project.mesh.dx == 0.01

    w.act_solve.trigger()
    qtbot.waitUntil(lambda: doc.results is not None, timeout=60_000)
    te0 = doc.results[0]
    # MPB reference for this guide (n = 3.476 / 1.444): 2.16479
    assert te0.neff.real == pytest.approx(2.1648, abs=2e-3)
    assert te0.te_fraction > 0.95
    assert w.table.rowCount() == len(doc.results)
    assert w.showing_fields
    assert w.readout.neff.text() == f"{te0.neff.real:.6f}"
    assert w.modes_list.count() == len(doc.results)
    assert not doc.results_stale

    doc.select(("structure", 0))
    type_into(qtbot, w.inspector.form.editors["size"].edits[0], "0.45")
    assert doc.results_stale and "out of date" in w.stale_label.text()


def test_viewer_components(window, qtbot):
    window.doc.replace(gm.Project.model_validate({**window.doc.project.model_dump(),
                                                  "materials": {"SiO2": "SiO2", "Si": "Si"},
                                                  "structures": [gm.Rectangle(material="Si", size=(0.5, 0.22))]}))
    window.solve()
    qtbot.waitUntil(lambda: window.doc.results is not None, timeout=60_000)
    v = window.viewer
    for comp in ("|E|", "|H|", "Ex", "Ey", "Ez", "Hx", "Hy", "Hz", "Sz", "n"):
        v.component.setCurrentText(comp)
        assert v.image.image is not None and np.all(np.isfinite(v.image.image))
    v.component.setCurrentText("Ex")
    v.log.setChecked(True)
    assert v.image.image.max() == pytest.approx(0.0) and v.image.image.min() >= -50.0
    window.modes_list.setCurrentRow(1)
    assert v.index == 1
    assert window.mode_section.header.label.text() == "MODE 1"


def test_undo_redo_and_delete(window):
    doc = window.doc
    doc.add_structure(gm.Rectangle(material="SiO2", size=(0.2, 0.2)))
    doc.update_structure(0, {"center": (0.5, 0.0)})
    assert doc.project.structures[0].center == (0.5, 0.0)
    window.act_undo.trigger()
    assert doc.project.structures[0].center == (0.0, 0.0)
    window.act_redo.trigger()
    assert doc.project.structures[0].center == (0.5, 0.0)
    doc.select(("structure", 0))
    window.act_delete.trigger()
    assert doc.project.structures == [] and doc.selection is None
    window.act_undo.trigger()
    assert len(doc.project.structures) == 1


def test_invalid_edit_is_rejected(window, qtbot):
    doc = window.doc
    doc.select(("mesh",))
    before = doc.project.mesh.dx
    type_into(qtbot, window.inspector.form.editors["dx"].edit, "-1")
    assert doc.project.mesh.dx == before
    assert window.inspector.error.text()
    assert window.inspector.form.editors["dx"].edit.text() == f"{before:g}"


def test_canvas_drag_commits_snapped_geometry(window):
    doc, canvas = window.doc, window.canvas
    doc.add_structure(gm.Rectangle(material="SiO2", size=(0.4, 0.2)))
    canvas.rebuild()
    roi = canvas._rois[0]
    roi.setPos(QPointF(0.1234, -0.0571), finish=False)
    roi.sigRegionChangeFinished.emit(roi)
    s = doc.project.structures[0]
    assert s.center == pytest.approx((0.32, 0.04))  # lower-left snapped to 10 nm: (0.12, -0.06)
    assert s.size == pytest.approx((0.4, 0.2))


def test_polygon_and_circle_round_trip_through_canvas(window):
    doc, canvas = window.doc, window.canvas
    window.act_trap.trigger()
    window.act_circle.trigger()
    canvas.rebuild()
    ridge = doc.project.structures[0].vertices  # sloped walls: off the 10 nm grid
    assert any(abs(v[0] * 100 - round(v[0] * 100)) > 1e-6 for v in ridge)
    for i in (0, 1):
        before = doc.project.structures[i].model_dump()
        canvas._commit(i, canvas._rois[i])  # an unchanged shape commits exactly the same geometry
        assert doc.project.structures[i].model_dump() == before
    # a pure move snaps the offset and keeps the off-grid shape intact
    roi = canvas._rois[0]
    roi.setPos(roi.pos() + QPointF(0.1234, 0.0), finish=False)
    canvas._commit(0, roi)
    moved = doc.project.structures[0].vertices
    assert np.allclose(np.array(moved), np.array(ridge) + [0.12, 0.0])


def test_materials_rename_and_delete(window):
    doc = window.doc
    doc.add_material("Si", gm.material("Si"))
    doc.add_structure(gm.Rectangle(material="Si", size=(0.4, 0.2)))
    doc.rename_material("Si", "silicon")
    assert doc.project.structures[0].material == "silicon"
    with pytest.raises(ValueError, match="used by"):
        doc.remove_material("silicon")
    with pytest.raises(ValueError, match="used by"):
        doc.remove_material("SiO2")  # background


def test_library_dialog(qtbot):
    dlg = LibraryDialog(1.55)
    qtbot.addWidget(dlg)
    dlg.list.setCurrentRow(list(gm.material_library()).index("AlGaAs"))
    dlg.x.setValue(0.25)
    m = dlg.material()
    assert isinstance(m, gm.AlGaAsMaterial) and m.x == 0.25
    assert "AlGaAs" in dlg.info.text()


def test_save_and_open(window, tmp_path):
    doc = window.doc
    doc.add_structure(gm.Rectangle(material="SiO2", size=(0.3, 0.3)))
    assert doc.dirty and "*" in window.windowTitle()
    path = tmp_path / "proj.gmode"
    doc.save(path)
    assert not doc.dirty and "proj.gmode" in window.windowTitle()
    doc.replace(gm.Project(materials={"a": gm.ConstantMaterial(n=1)}, background="a"))
    window.open_project(str(path))
    assert len(doc.project.structures) == 1 and doc.path == path


def test_subprocess_solver_and_cancel(qtbot):
    """The real runner: solves in a worker process and can be cancelled mid-solve."""
    from gmode.gui.solver import SolveRunner

    r = SolveRunner()
    try:
        p = gm.Project(materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
                       structures=[gm.Rectangle(material="Si", size=(0.5, 0.22))],
                       domain=gm.Domain(size=(2.0, 1.5)), mesh=gm.Mesh(dx=0.04, dy=0.04),
                       solver=gm.SolverSettings(num_modes=1))
        with qtbot.waitSignal(r.finished, timeout=60_000) as sig:
            r.solve(p)
        modes, warnings = sig.args
        assert modes[0].neff.real == pytest.approx(2.4, abs=0.1) and warnings == []

        big = p.model_copy(update={"mesh": gm.Mesh(dx=0.004, dy=0.004)})
        with qtbot.waitSignal(r.cancelled, timeout=5_000):
            r.solve(big)
            qtbot.wait(300)
            r.cancel()
        assert not r.busy

        bad = p.model_copy(update={"wavelength": 0.5})  # outside Si's valid range: still solves, with a warning
        with qtbot.waitSignal(r.finished, timeout=60_000) as sig:
            r.solve(bad)
        assert any("only valid" in w for w in sig.args[1])
    finally:
        r.shutdown()


def test_destroying_document_with_unsaved_changes_is_quiet(qtbot):
    """Closing with unsaved changes destroys a dirty undo stack, which emits cleanChanged
    from its destructor; that must not reach the already-deleted document."""
    from shiboken6 import Shiboken

    doc = ProjectDocument()
    doc.add_structure(gm.Circle(material="Si", radius=0.1))
    assert doc.dirty
    with qtbot.captureExceptions() as exceptions:
        Shiboken.delete(doc)
    assert not exceptions, exceptions[0][1]


def test_sweep_view_runs_tracks_and_opens_points(window, qtbot):
    w, doc = window, window.doc
    doc.add_material("Si", gm.material("Si"))
    doc.add_structure(gm.Rectangle(name="core", material="Si", size=(0.5, 0.22)))
    from gmode.gui.sweep import sweep_parameters

    paths = dict(sweep_parameters(doc.project))
    assert paths["core width"] == "structures.core.size.0" and paths["wavelength"] == "wavelength"

    w.show_sweep()
    assert w.sweep_section.isVisible()
    setup = w.sweep_setup
    setup.param.setCurrentText("core width")
    setup._param_picked(setup.param.currentIndex())
    assert doc.project.sweep.parameter == "structures.core.size.0"
    assert (doc.project.sweep.start, doc.project.sweep.stop) == pytest.approx((0.4, 0.6))
    setup.steps.setValue(4)
    assert doc.project.sweep.steps == 4
    w.act_undo.trigger()
    assert doc.project.sweep.steps == 11  # sweep settings are undoable project edits
    w.act_redo.trigger()

    w.act_sweep.trigger()
    qtbot.waitUntil(lambda: w.sweep_result is not None, timeout=120_000)
    r = w.sweep_result
    assert r.neff.shape == (4, 2) and np.all(np.isfinite(r.neff))
    assert len(w.sweep_view._curves) == 2
    assert not w.sweep_view.quantity.buttons["D"].isEnabled()  # not a wavelength sweep
    for q in ("n_g", "loss", "TE", "A_eff", "n_eff"):
        w.sweep_view.quantity.setCurrentText(q)
        assert len(w.sweep_view._curves) == 2

    w._sweep_point(2, 1)
    assert w.showing_fields and doc.results is r.steps[2]
    assert w.viewer.index == r.assignments[2][1]
    assert "sweep step 2" in w.status.text()


def test_sweep_runner_pool_and_cancel(qtbot):
    """The real runner: steps on a pool of worker processes, tracked in order, cancellable."""
    from gmode.gui.sweep import SweepRunner

    p = gm.Project(materials={"Si": "Si", "SiO2": "SiO2"}, background="SiO2",
                   structures=[gm.Rectangle(name="core", material="Si", size=(0.5, 0.22))],
                   domain=gm.Domain(size=(2.0, 1.5)), mesh=gm.Mesh(dx=0.04, dy=0.04),
                   solver=gm.SolverSettings(num_modes=1),
                   sweep=gm.SweepSettings(parameter="wavelength", start=1.5, stop=1.6, steps=5))
    r = SweepRunner(workers=2)
    try:
        updates = []
        r.updated.connect(lambda res: updates.append(len(res.values)))
        with qtbot.waitSignal(r.finished, timeout=120_000) as sig:
            r.run(p)
        result, warnings = sig.args
        serial = gm.sweep(p, "wavelength", p.sweep.values, workers=1)
        assert result.neff == pytest.approx(serial.neff, abs=1e-10)
        assert updates == sorted(updates) and updates[-1] == 5
        assert result.dispersion().shape == (5, 1)

        big = p.model_copy(update={"mesh": gm.Mesh(dx=0.005, dy=0.005)})
        with qtbot.waitSignal(r.cancelled, timeout=10_000):
            r.run(big)
            qtbot.wait(300)
            r.cancel()
        assert not r.busy
    finally:
        r.shutdown()


def test_export_and_reopen_results(window, qtbot, tmp_path):
    w = window
    w.open_example("si_strip")
    w.solve()
    qtbot.waitUntil(lambda: w.doc.results is not None, timeout=60_000)
    csv_path = w.export("modes_csv", tmp_path / "m.csv")
    npz_path = w.export("modes_npz", tmp_path / "m.npz")
    assert csv_path.read_text().startswith("mode,wavelength_um,neff_real")
    for view in ("Geometry", "Fields"):
        w.view_seg.setCurrentText(view)
        png = w.export("image", str(tmp_path / f"{view}.png"))
        assert png.stat().st_size > 5000
    neff = w.doc.results[0].neff
    w.doc.set_results(None)
    w.open_results(str(npz_path))
    assert w.doc.results[0].neff == neff and w.modes_list.count() == len(w.doc.results)
    w._update_export_actions()
    assert w.act_export_csv.isEnabled() and not w.act_export_sweep_csv.isEnabled()
