"""GMode main window: project panel | stage | solve and properties."""
import sys
import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

import gmode as gm

from . import theme
from .canvas import GeometryCanvas
from .dialogs import ConstantDialog, LibraryDialog
from .document import ProjectDocument, default_project
from .fields import FieldViewer, ModeTable
from .inspector import InspectorPanel
from .solver import SolveRunner
from .sweep import SweepRunner, SweepSetup, SweepView
from .tree import ProjectTree
from .widgets import ModeList, ModeReadout, Section, Segmented, toggle

FILE_FILTER = "GMode project (*.gmode *.json);;All files (*)"
SNAP_STEPS = {"off": 0.0, "1": 0.001, "5": 0.005, "10": 0.01, "50": 0.05, "100": 0.1}
_MAX_RECENT = 8
HINT_GEOMETRY = ("<b>drag</b> move  ·  <b>handles</b> resize  ·  <b>R C T P</b> add shape  ·  "
                 "<b>F</b> fit  ·  <b>F5</b> solve")
HINT_FIELDS = "<b>click</b> a mode on the right  ·  <b>scroll</b> zoom  ·  <b>drag</b> pan  ·  <b>F5</b> solve"
HINT_SWEEP = ("<b>click</b> a point to view its modes  ·  <b>scroll</b> zoom  ·  <b>F6</b> run sweep  ·  "
              "<b>esc</b> stop")


def _hint(text):
    lab = QLabel(text.replace("<b>", f"<span style='color:{theme.DIM}'>").replace("</b>", "</span>"))
    lab.setObjectName("hint")
    return lab


class SolveButton(QPushButton):
    """The main action: big, filled, with its key on the right."""

    def __init__(self, text="SOLVE", key="F5"):
        self.text_idle, self.key_idle = text, key
        super().__init__()
        self.setObjectName("primary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(54)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        self.label = QLabel()
        f = theme.mono_font(14, QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        self.label.setFont(f)
        self.key = QLabel()
        self.key.setFont(theme.mono_font(10))
        for w in (self.label, self.key):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            w.setStyleSheet("color: inherit; background: transparent;")
        lay.addWidget(self.label)
        lay.addStretch()
        lay.addWidget(self.key)
        self.set_running(False)

    def set_running(self, running: bool):
        self.label.setText("CANCEL" if running else self.text_idle)
        self.key.setText("esc" if running else self.key_idle)
        color = theme.ACCENT_INK if running else theme.INK
        self.label.setStyleSheet(f"color: {color}; background: transparent;")
        self.key.setStyleSheet(f"color: {color}; background: transparent;")
        self.setProperty("running", running)
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self, doc: ProjectDocument | None = None, in_process_solver: bool = False,
                 settings: QSettings | None = None):
        super().__init__()
        self.doc = doc or ProjectDocument()
        self.settings = settings or QSettings("GMode", "GMode")
        self.runner = SolveRunner(self, in_process=in_process_solver)
        self.sweeper = SweepRunner(self, in_process=in_process_solver)
        self.sweep_result = None
        self.resize(1440, 880)

        self.canvas = GeometryCanvas(self.doc)
        self.viewer = FieldViewer()
        self.sweep_view = SweepView()
        self.sweep_setup = SweepSetup(self.doc)
        self.tree = ProjectTree(self.doc)
        self.inspector = InspectorPanel(self.doc)
        self.modes_list = ModeList()
        self.readout = ModeReadout()
        self.table = ModeTable()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._build_actions()
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._left_panel())
        split.addWidget(self._stage())
        split.addWidget(self._right_panel())
        split.setStretchFactor(1, 1)
        split.setSizes([250, 860, 330])
        split.setChildrenCollapsible(False)
        self.setCentralWidget(split)

        dock = QDockWidget("Mode table", self)
        dock.setObjectName("mode-table")
        dock.setWidget(self.table)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        dock.hide()
        self.table_dock = dock
        self.view_menu.addAction(dock.toggleViewAction())

        self._tick = QTimer(self, interval=200)
        self._tick.timeout.connect(lambda: self.status.setText(f"solving  ·  {self.runner.elapsed():.1f} s"))
        self._connect()
        self.restoreGeometry(self.settings.value("geometry", b""))
        self._update_title()
        self._refresh_results()

    # ---- layout ---------------------------------------------------------------------------
    def _left_panel(self):
        w = QWidget()
        w.setMinimumWidth(220)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 14, 14)
        lay.setSpacing(12)
        head = QVBoxLayout()
        head.setSpacing(2)
        title = QLabel("GMode")
        title.setObjectName("title")
        title.setFont(theme.serif_font(19))
        sub = QLabel("waveguide mode solver")
        sub.setObjectName("subtitle")
        self.file_label = QLabel()
        self.file_label.setObjectName("dim")
        head.addWidget(title)
        head.addWidget(sub)
        head.addSpacing(6)
        head.addWidget(self.file_label)
        lay.addLayout(head)

        proj = Section("Project")
        proj.add(self.tree)
        lay.addWidget(proj, 1)

        add = Section("Add")
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (text, act) in enumerate((("Rectangle", self.act_rect), ("Circle", self.act_circle),
                                         ("Ridge", self.act_trap), ("Polygon", self.act_poly))):
            b = QPushButton(text)
            b.setToolTip(act.statusTip() + f"  [{act.shortcut().toString()}]")
            b.clicked.connect(act.trigger)
            grid.addWidget(b, i // 2, i % 2)
        mat = QPushButton("Material…")
        mat.clicked.connect(self.act_mat_lib.trigger)
        grid.addWidget(mat, 2, 0, 1, 2)
        add.body.addLayout(grid)
        lay.addWidget(add)

        edit = Section("Edit")
        row = QGridLayout()
        row.setSpacing(6)
        self.undo_btn, self.redo_btn = QPushButton("Undo"), QPushButton("Redo")
        self.undo_btn.clicked.connect(self.doc.undo_stack.undo)
        self.redo_btn.clicked.connect(self.doc.undo_stack.redo)
        self.doc.undo_stack.canUndoChanged.connect(self.undo_btn.setEnabled)
        self.doc.undo_stack.canRedoChanged.connect(self.redo_btn.setEnabled)
        self.undo_btn.setEnabled(False)
        self.redo_btn.setEnabled(False)
        dup, dele = QPushButton("Copy"), QPushButton("Delete")
        dup.clicked.connect(self.act_duplicate.trigger)
        dele.clicked.connect(self.act_delete.trigger)
        for i, b in enumerate((self.undo_btn, self.redo_btn, dup, dele)):
            row.addWidget(b, i // 2, i % 2)
        edit.body.addLayout(row)
        lay.addWidget(edit)

        log = Section("Log")
        self.log.setFixedHeight(110)
        log.add(self.log)
        lay.addWidget(log)
        return w

    def _stage(self):
        w = QWidget()
        w.setObjectName("stage")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)
        bar = QWidget()
        bar.setObjectName("stagebar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        self.view_seg = Segmented(["Geometry", "Fields", "Sweep"])
        bl.addWidget(self.view_seg)
        bl.addStretch()

        geo = QWidget()
        gl = QHBoxLayout(geo)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(6)
        gl.addStretch()
        snap_label = QLabel("snap nm")
        snap_label.setObjectName("hint")
        self.snap_seg = Segmented(list(SNAP_STEPS), "10")
        self.snap_seg.currentTextChanged.connect(lambda t: self.canvas.set_snap(SNAP_STEPS[t]))
        self.index_toggle = toggle("index", True)
        self.index_toggle.toggled.connect(self.canvas.set_show_index)
        fit = QPushButton("fit")
        fit.clicked.connect(self.canvas.fit)
        for x in (snap_label, self.snap_seg, self.index_toggle, fit):
            x.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            gl.addWidget(x)
        self.bar_stack = QStackedWidget()
        self.bar_stack.addWidget(geo)
        self.bar_stack.addWidget(self.viewer.controls)
        self.bar_stack.addWidget(self.sweep_view.controls)
        self.bar_stack.setStyleSheet(f"background: {theme.BG};")
        bl.addWidget(self.bar_stack)
        lay.addWidget(bar)

        self.stage_stack = QStackedWidget()
        self.stage_stack.addWidget(self.canvas)
        self.stage_stack.addWidget(self.viewer)
        self.stage_stack.addWidget(self.sweep_view)
        lay.addWidget(self.stage_stack, 1)
        self.hint = _hint(HINT_GEOMETRY)
        lay.addWidget(self.hint)
        self.view_seg.currentTextChanged.connect(self._switch_view)
        return w

    def _right_panel(self):
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 14, 16, 18)
        lay.setSpacing(12)
        self.solve_btn = SolveButton()
        self.solve_btn.clicked.connect(lambda: self.runner.cancel() if self.runner.busy else self.solve())
        lay.addWidget(self.solve_btn)
        self.status = QLabel("not solved yet")
        self.status.setObjectName("status")
        self.stale_label = QLabel()
        self.stale_label.setObjectName("stale")
        self.stale_label.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addWidget(self.stale_label)

        self.sweep_section = Section("Sweep")
        self.sweep_section.add(self.sweep_setup)
        self.sweep_btn = SolveButton("SWEEP", "F6")
        self.sweep_btn.setMinimumHeight(44)
        self.sweep_btn.clicked.connect(lambda: self.sweeper.cancel() if self.sweeper.busy else self.run_sweep())
        self.sweep_section.add(self.sweep_btn)
        self.sweep_status = QLabel("")
        self.sweep_status.setObjectName("status")
        self.sweep_status.setWordWrap(True)
        self.sweep_section.add(self.sweep_status)
        self.sweep_section.hide()
        lay.addWidget(self.sweep_section)

        modes = Section("Modes")
        self.modes_hint = QLabel("press solve to find modes")
        self.modes_hint.setObjectName("hint")
        modes.add(self.modes_hint)
        modes.add(self.modes_list)
        lay.addWidget(modes)
        self.mode_section = Section("Mode")
        self.mode_section.add(self.readout)
        lay.addWidget(self.mode_section)
        props = Section("Properties")
        props.add(self.inspector)
        lay.addWidget(props)
        lay.addStretch()

        # follow the panel width instead of growing to the widest child (no sideways scrolling)
        inner.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(300)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        return scroll

    def _switch_view(self, name):
        i = ["Geometry", "Fields", "Sweep"].index(name)
        self.stage_stack.setCurrentIndex(i)
        self.bar_stack.setCurrentIndex(i)
        self.hint.setText(_hint((HINT_GEOMETRY, HINT_FIELDS, HINT_SWEEP)[i]).text())
        self.sweep_section.setVisible(name == "Sweep")

    def show_fields(self):
        self.view_seg.setCurrentText("Fields")

    def show_geometry(self):
        self.view_seg.setCurrentText("Geometry")

    def show_sweep(self):
        self.view_seg.setCurrentText("Sweep")

    @property
    def showing_fields(self) -> bool:
        return self.view_seg.currentText() == "Fields"

    # ---- actions --------------------------------------------------------------------------
    def _action(self, text, slot, shortcut=None, tip=None):
        a = QAction(text, self)
        a.triggered.connect(lambda checked=False: slot())
        if shortcut:
            a.setShortcut(shortcut)
        a.setStatusTip(tip or text)
        self.addAction(a)  # shortcuts work wherever focus is
        return a

    def _build_actions(self):
        S = QKeySequence.StandardKey
        self.act_new = self._action("New", self.new_project, S.New)
        self.act_open = self._action("Open...", self.open_project, S.Open)
        self.act_save = self._action("Save", self.save_project, S.Save)
        self.act_save_as = self._action("Save As...", self.save_project_as, S.SaveAs)
        self.act_quit = self._action("Quit", self.close, S.Quit)
        self.act_undo = self.doc.undo_stack.createUndoAction(self, "Undo")
        self.act_undo.setShortcut(S.Undo)
        self.act_redo = self.doc.undo_stack.createRedoAction(self, "Redo")
        self.act_redo.setShortcut(S.Redo)
        self.act_delete = self._action("Delete", self.delete_selected, S.Delete)
        self.act_duplicate = self._action("Duplicate", self.duplicate_selected, "Ctrl+D")
        self.act_rect = self._action("Rectangle", lambda: self.add_structure("rectangle"), "R", "Add a rectangle")
        self.act_circle = self._action("Circle", lambda: self.add_structure("circle"), "C", "Add a circle")
        self.act_trap = self._action("Ridge", lambda: self.add_structure("trapezoid"), "T",
                                     "Add an etched ridge with sloped sidewalls")
        self.act_poly = self._action("Polygon", lambda: self.add_structure("polygon"), "P",
                                     "Add a polygon; drag vertices, double-click an edge to add one")
        self.act_mat_lib = self._action("Material from library...", lambda: self.add_material("library"), "Ctrl+M")
        self.act_mat_const = self._action("Constant-index material...", lambda: self.add_material("constant"))
        self.act_mat_file = self._action("Import n,k file...", lambda: self.add_material("file"))
        self.act_solve = self._action("Solve", self.solve, "F5", "Find modes")
        self.act_sweep = self._action("Run sweep", self.run_sweep, "F6", "Solve at every sweep value and track modes")
        self.act_cancel = self._action("Cancel", self.cancel_running, "Esc")
        self.act_cancel.setEnabled(False)
        self.act_fit = self._action("Fit to domain", self.canvas.fit, "F")
        self.act_geometry = self._action("Geometry", self.show_geometry, "Ctrl+1")
        self.act_fields = self._action("Fields", self.show_fields, "Ctrl+2")
        self.act_sweep_view = self._action("Sweep", self.show_sweep, "Ctrl+3")

        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.act_new, self.act_open):
            m.addAction(a)
        self.recent_menu = m.addMenu("Open Recent")
        examples = m.addMenu("Open Example")
        from gmode.examples import catalog

        for name, title in catalog().items():
            examples.addAction(title, lambda n=name: self.open_example(n))
        m.addAction("Open Results (.npz)...", self.open_results)
        m.addSeparator()
        for a in (self.act_save, self.act_save_as):
            m.addAction(a)
        exp = m.addMenu("Export")
        self.act_export_csv = exp.addAction("Modes as CSV...", lambda: self.export("modes_csv"))
        self.act_export_npz = exp.addAction("Modes with fields (.npz)...", lambda: self.export("modes_npz"))
        exp.addSeparator()
        self.act_export_sweep_csv = exp.addAction("Sweep as CSV...", lambda: self.export("sweep_csv"))
        self.act_export_sweep_npz = exp.addAction("Sweep (.npz)...", lambda: self.export("sweep_npz"))
        exp.addSeparator()
        exp.addAction("Plot image (PNG)...", lambda: self.export("image"))
        exp.aboutToShow.connect(self._update_export_actions)
        m.addSeparator()
        m.addAction(self.act_quit)
        m = mb.addMenu("&Edit")
        for a in (self.act_undo, self.act_redo, None, self.act_duplicate, self.act_delete):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("&Add")
        for a in (self.act_rect, self.act_circle, self.act_trap, self.act_poly, None,
                  self.act_mat_lib, self.act_mat_const, self.act_mat_file):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("&Simulate")
        m.addAction(self.act_solve)
        m.addAction(self.act_sweep)
        m.addAction(self.act_cancel)
        self.view_menu = mb.addMenu("&View")
        for a in (self.act_geometry, self.act_fields, self.act_sweep_view, self.act_fit):
            self.view_menu.addAction(a)
        self.view_menu.addSeparator()
        self._rebuild_recent()

    def _connect(self):
        d = self.doc
        d.titleChanged.connect(self._update_title)
        d.changed.connect(self._update_stale)
        d.resultsChanged.connect(self._refresh_results)
        self.tree.addStructureRequested.connect(self.add_structure)
        self.tree.addMaterialRequested.connect(self.add_material)
        self.canvas.statusMessage.connect(lambda t: self.statusBar().showMessage(t, 4000))
        self.modes_list.modeSelected.connect(self._select_mode)
        self.table.modeSelected.connect(self._select_mode)
        r = self.runner
        r.started.connect(self._solve_started)
        r.finished.connect(self._solve_finished)
        r.failed.connect(self._solve_failed)
        r.cancelled.connect(self._solve_cancelled)
        sw = self.sweeper
        sw.progress.connect(self._sweep_progress)
        sw.updated.connect(self.sweep_view.set_result)
        sw.finished.connect(self._sweep_finished)
        sw.failed.connect(self._sweep_failed)
        sw.cancelled.connect(self._sweep_cancelled)
        self.sweep_view.pointClicked.connect(self._sweep_point)

    def _select_mode(self, i):
        res = self.doc.results
        if res is None or i >= len(res):
            return
        self.viewer.show_mode(i)
        self.readout.show_mode(res[i], res, i)
        self.mode_section.set_caption(f"Mode {i}")
        for widget in (self.modes_list, self.table):
            widget.blockSignals(True)
        self.modes_list.setCurrentRow(i)
        self.table.selectRow(i)
        for widget in (self.modes_list, self.table):
            widget.blockSignals(False)
        self.show_fields()

    # ---- files ----------------------------------------------------------------------------
    def _update_title(self):
        self.setWindowTitle(self.doc.title)
        name = self.doc.path.name if self.doc.path else "untitled"
        self.file_label.setText(name + ("  · edited" if self.doc.dirty else ""))

    def _confirm_discard(self) -> bool:
        if not self.doc.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to the current project?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save_project()
        return r == QMessageBox.StandardButton.Discard

    def new_project(self):
        if self._confirm_discard():
            self.doc.replace(default_project())
            self.canvas.fit()
            self.show_geometry()

    def _update_export_actions(self):
        has_modes = self.doc.results is not None and len(self.doc.results) > 0
        has_sweep = self.sweep_result is not None and len(self.sweep_result.values) > 0
        for a in (self.act_export_csv, self.act_export_npz):
            a.setEnabled(has_modes)
        for a in (self.act_export_sweep_csv, self.act_export_sweep_npz):
            a.setEnabled(has_sweep)

    def _current_plot(self):
        view = self.view_seg.currentText()
        return {"Geometry": self.canvas, "Fields": self.viewer.plot, "Sweep": self.sweep_view.plot}[view]

    def export(self, what: str, path: str | None = None):
        """Write results or the current plot. With `path`, no dialog is shown (scripts and tests)."""
        name = self.doc.project.name
        spec = {
            "modes_csv": (f"{name}_modes.csv", "CSV (*.csv)"),
            "modes_npz": (f"{name}_modes.npz", "NumPy archive (*.npz)"),
            "sweep_csv": (f"{name}_sweep.csv", "CSV (*.csv)"),
            "sweep_npz": (f"{name}_sweep.npz", "NumPy archive (*.npz)"),
            "image": (f"{name}_{self.view_seg.currentText().lower()}.png", "PNG image (*.png)"),
        }[what]
        interactive = path is None
        if interactive:
            path, _ = QFileDialog.getSaveFileName(self, "Export", str(Path(self._last_dir()) / spec[0]), spec[1])
            if not path:
                return None
        try:
            if what == "modes_csv":
                out = self.doc.results.to_csv(path)
            elif what == "modes_npz":
                out = self.doc.results.save(path)
            elif what == "sweep_csv":
                out = self.sweep_result.to_csv(path)
            elif what == "sweep_npz":
                out = self.sweep_result.save(path)
            else:
                import pyqtgraph.exporters as pex

                # pyqtgraph's SVG exporter fails on image items, so plots export as PNG only
                item = self._current_plot().getPlotItem()
                exporter = pex.ImageExporter(item)
                exporter.parameters()["width"] = 2 * int(item.width())  # 2x for crisp figures
                exporter.export(str(path))
                out = Path(path)
        except Exception as e:  # report I/O problems instead of crashing the window
            if not interactive:
                raise
            QMessageBox.critical(self, "Export failed", f"{path}\n\n{e}")
            return None
        self.log_message(f"exported {out}")
        self.statusBar().showMessage(f"Exported {out}", 4000)
        return out

    def open_results(self, path=None):
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Open results", self._last_dir(), "NumPy archive (*.npz)")
            if not path:
                return
        try:
            res = gm.ModeSet.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Could not open results", f"{path}\n\n{e}")
            return
        self.doc.set_results(res)
        self.status.setText(f"results from {Path(path).name}  ·  {len(res)} modes")
        self.log_message(f"opened results {path} (project {res.project.name!r})")

    def open_example(self, name: str):
        if not self._confirm_discard():
            return
        from gmode.examples import catalog, load

        self.doc.replace(load(name))
        self.canvas.fit()
        self.show_geometry()
        self.doc.select(("project",))
        self.log_message(f"opened example: {catalog()[name]}")

    def open_project(self, path=None):
        if not self._confirm_discard():
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Open project", self._last_dir(), FILE_FILTER)
            if not path:
                return
        try:
            project = gm.Project.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Could not open project", f"{path}\n\n{e}")
            return
        self.doc.replace(project, path)
        self.canvas.fit()
        self.show_geometry()
        self._add_recent(path)
        self.log_message(f"opened {path}")

    def save_project(self) -> bool:
        if self.doc.path is None:
            return self.save_project_as()
        self.doc.save()
        self._add_recent(self.doc.path)
        self.statusBar().showMessage(f"Saved {self.doc.path}", 3000)
        return True

    def save_project_as(self) -> bool:
        start = str(Path(self._last_dir()) / f"{self.doc.project.name}.gmode")
        path, _ = QFileDialog.getSaveFileName(self, "Save project", start, FILE_FILTER)
        if not path:
            return False
        self.doc.save(path)
        self._add_recent(path)
        return True

    def _last_dir(self) -> str:
        recent = self.settings.value("recent", []) or []
        return str(Path(recent[0]).parent) if recent else str(Path.home())

    def _add_recent(self, path):
        recent = [str(Path(path))] + [p for p in (self.settings.value("recent", []) or []) if p != str(Path(path))]
        self.settings.setValue("recent", recent[:_MAX_RECENT])
        self._rebuild_recent()

    def _rebuild_recent(self):
        self.recent_menu.clear()
        for p in self.settings.value("recent", []) or []:
            self.recent_menu.addAction(p, lambda p=p: self.open_project(p))
        self.recent_menu.setEnabled(not self.recent_menu.isEmpty())

    # ---- editing --------------------------------------------------------------------------
    def _default_material(self) -> str:
        p = self.doc.project
        others = [m for m in p.materials if m != p.background]
        sel = self.doc.selected_object()
        if isinstance(sel, (gm.Rectangle, gm.Circle, gm.Polygon)):
            return sel.material
        return others[0] if others else p.background

    def add_structure(self, kind: str):
        c = self.canvas.view_center()
        x, y = c.x(), c.y()
        mat = self._default_material()
        if kind == "rectangle":
            s = gm.Rectangle(name="rectangle", material=mat, center=(x, y), size=(0.4, 0.2))
        elif kind == "circle":
            s = gm.Circle(name="circle", material=mat, center=(x, y), radius=0.2)
        elif kind == "trapezoid":
            s = gm.Polygon.trapezoid(mat, (x, y), 0.4, 0.22, 10.0, name="ridge")
            s = s.model_copy(update={"vertices": [(round(a, 9), round(b, 9)) for a, b in s.vertices]})
        else:
            s = gm.Polygon(name="polygon", material=mat,
                           vertices=[(x - 0.2, y - 0.15), (x + 0.2, y - 0.15), (x, y + 0.2)])
        self.doc.add_structure(s)
        self.show_geometry()

    def add_material(self, how: str):
        if how == "library":
            dlg = LibraryDialog(self.doc.project.wavelength, self)
            if dlg.exec():
                self.doc.add_material(dlg.project_name(), dlg.material())
        elif how == "constant":
            dlg = ConstantDialog(self)
            if dlg.exec():
                self.doc.add_material(dlg.name.text().strip() or "material", dlg.material())
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Import n,k data", self._last_dir(),
                                                  "Data (*.csv *.txt *.dat);;All files (*)")
            if not path:
                return
            unit = "nm" if "nm" in Path(path).read_text()[:500].lower() else "um"
            try:
                m = gm.TabulatedMaterial.from_file(path, wavelength_unit=unit)
            except Exception as e:
                QMessageBox.critical(self, "Could not import", str(e))
                return
            name = self.doc.add_material(Path(path).stem, m)
            self.log_message(f"imported {name}: {len(m.wavelengths)} points, "
                             f"{m.wavelengths[0]:g} to {m.wavelengths[-1]:g} µm (wavelengths read as {unit})")

    def delete_selected(self):
        sel = self.doc.selection
        if not sel:
            return
        if sel[0] == "structure":
            self.doc.remove_structure(sel[1])
        elif sel[0] == "material":
            try:
                self.doc.remove_material(sel[1])
            except ValueError as e:
                QMessageBox.warning(self, "Cannot delete material", str(e))

    def duplicate_selected(self):
        sel = self.doc.selection
        if sel and sel[0] == "structure":
            self.doc.duplicate_structure(sel[1])

    # ---- solving --------------------------------------------------------------------------
    def solve(self):
        self.runner.solve(self.doc.project)

    def cancel_running(self):
        self.runner.cancel()
        self.sweeper.cancel()

    # ---- sweeps ---------------------------------------------------------------------------
    def run_sweep(self):
        if self.sweeper.busy or self.runner.busy:
            return
        self.show_sweep()
        try:
            self.sweeper.run(self.doc.project)
        except ValueError as e:  # e.g. a sweep value the project rejects, like a negative width
            QMessageBox.warning(self, "Cannot run sweep", str(e))

    def _sweep_progress(self, done, total):
        if done == 0:
            st = self.doc.project.sweep
            self.sweep_btn.set_running(True)
            self.act_solve.setEnabled(False)
            self.act_sweep.setEnabled(False)
            self.act_cancel.setEnabled(True)
            self.sweep_view.set_result(None)
            self.sweep_view.progress.setRange(0, total)
            self.sweep_view.progress.show()
            from gmode.sweep import parameter_label

            self.log_message(f"sweep: {parameter_label(st.parameter)} from {st.start:g} to {st.stop:g}, "
                             f"{total} steps")
        self.sweep_view.progress.setValue(done)
        self.sweep_status.setText(f"step {done} of {total}  ·  {self.sweeper.elapsed():.1f} s")

    def _sweep_done(self):
        self.sweep_btn.set_running(False)
        self.act_solve.setEnabled(True)
        self.act_sweep.setEnabled(True)
        self.act_cancel.setEnabled(False)
        self.sweep_view.progress.hide()

    def _sweep_finished(self, result, warnings):
        self._sweep_done()
        self.sweep_result = result
        self.sweep_view.set_result(result)
        for w in warnings:
            self.log_message(f"warning: {w}")
        t = self.sweeper.elapsed() or (time.perf_counter() - self.sweeper.t_start)
        kept = "  ·  click a point for its fields" if result.steps else ""
        self.sweep_status.setText(f"{len(result.values)} steps  ·  {t:.1f} s{kept}")
        self.log_message(f"sweep finished in {t:.1f} s\n{result.table()}")

    def _sweep_failed(self, message, tb):
        self._sweep_done()
        self.sweep_status.setText("sweep failed (see log)")
        self.log_message(f"sweep failed: {message}\n{tb}".rstrip())
        QMessageBox.warning(self, "Sweep failed", message)

    def _sweep_cancelled(self, partial):
        self._sweep_done()
        self.sweep_result = partial
        self.sweep_view.set_result(partial)
        self.sweep_status.setText(f"stopped after {len(partial.values)} steps")
        self.log_message("sweep stopped")

    def _sweep_point(self, step, track):
        r = self.sweep_result
        if r is None:
            return
        value = f"{r.label.rsplit(' (', 1)[0]} = {r.values[step]:g}"
        if not r.steps or r.steps[step] is None:
            self.sweep_status.setText(f"{value}  ·  fields were not kept for this sweep")
            return
        j = r.assignments[step][track]
        if j is None:
            return
        self.doc.set_results(r.steps[step])
        self._select_mode(j)
        self.status.setText(f"sweep step {step}  ·  {value}")

    def _solve_started(self):
        self.act_solve.setEnabled(False)
        self.act_cancel.setEnabled(True)
        self.solve_btn.set_running(True)
        self._tick.start()
        self.status.setText("solving")
        p = self.doc.project
        self.log_message(f"solving {p.solver.num_modes} modes at {p.wavelength:g} µm ({p.solver.backend})")

    def _solve_done(self):
        self._tick.stop()
        self.act_solve.setEnabled(True)
        self.act_cancel.setEnabled(False)
        self.solve_btn.set_running(False)

    def _solve_finished(self, modes, warnings):
        self._solve_done()
        for w in warnings:
            self.log_message(f"warning: {w}")
        meta = modes[0].meta if len(modes) else {}
        t, shape = meta.get("solve_time", 0.0), meta.get("grid_shape")
        grid = f"  ·  {shape[0]} × {shape[1]} grid" if shape else ""
        warn = f"  ·  {len(warnings)} warning{'s' if len(warnings) > 1 else ''}" if warnings else ""
        self.status.setText(f"{len(modes)} modes  ·  {t:.2f} s{grid}{warn}")
        self.log_message(f"found {len(modes)} modes in {t:.2f} s\n{modes.table()}")
        self.doc.set_results(modes)

    def _solve_failed(self, message, tb):
        self._solve_done()
        self.status.setText("solve failed (see log)")
        self.log_message(f"solve failed: {message}\n{tb}".rstrip())
        QMessageBox.warning(self, "Solve failed", message)

    def _solve_cancelled(self):
        self._solve_done()
        self.status.setText("cancelled")
        self.log_message("solve cancelled")

    def _refresh_results(self):
        res = self.doc.results
        self.modes_list.set_modes(res)
        self.modes_list.setVisible(bool(res))
        self.modes_hint.setVisible(not res)
        self.table.set_modes(res)
        self.viewer.set_modes(res)
        self.readout.show_mode(res[0] if res else None, res, 0)
        self.mode_section.set_caption("Mode 0" if res else "Mode")
        self.mode_section.setVisible(bool(res))
        self._update_stale()
        if res is not None and len(res):
            self.show_fields()

    def _update_stale(self):
        self.stale_label.setText("results are out of date  ·  F5 to re-solve" if self.doc.results_stale else "")
        self.stale_label.setVisible(self.doc.results_stale)

    def log_message(self, text):
        self.log.appendPlainText(text)

    def closeEvent(self, ev):
        if not self._confirm_discard():
            ev.ignore()
            return
        self.runner.shutdown()
        self.sweeper.shutdown()
        self.settings.setValue("geometry", self.saveGeometry())
        ev.accept()


def _self_test(app) -> int:
    """Open an example, solve it in a real worker process, check TE0, and quit (for built apps and CI)."""
    import tempfile

    settings = QSettings(str(Path(tempfile.mkdtemp()) / "self-test.ini"), QSettings.Format.IniFormat)
    win = MainWindow(settings=settings)
    outcome = {"code": 2}

    def finished(modes, _warnings):
        neff = modes[0].neff.real
        ok = abs(neff - 2.45004) < 2e-3
        print(f"self-test: TE0 neff {neff:.5f} ({'ok' if ok else 'unexpected'}), "
              f"solved in a worker process in {modes[0].meta.get('solve_time', 0):.2f} s", flush=True)
        outcome["code"] = 0 if ok else 1
        win.doc.undo_stack.setClean()
        app.quit()

    def failed(message, tb):
        print(f"self-test: solve failed: {message}\n{tb}", flush=True)
        outcome["code"] = 1
        app.quit()

    win.runner.finished.connect(finished)
    win.runner.failed.connect(failed)
    win.show()
    QTimer.singleShot(0, lambda: (win.open_example("si_strip"), win.solve()))
    QTimer.singleShot(180_000, app.quit)  # give up after 3 minutes
    app.exec()
    win.runner.shutdown()
    return outcome["code"]


def main(argv=None):
    import multiprocessing
    import os

    multiprocessing.freeze_support()  # frozen apps: solver workers must not start another window
    argv = list(sys.argv if argv is None else argv)
    self_test = "--self-test" in argv
    if self_test:
        argv.remove("--self-test")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("GMode")
    app.setOrganizationName("GMode")
    theme.apply(app)
    if self_test:
        return _self_test(app)
    win = MainWindow()
    if len(argv) > 1:
        win.open_project(argv[1])
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
