"""Sweep panel: setup, a pool of solver processes, and the tracked-mode plot."""
import multiprocessing as mp
import time
from typing import Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QSpinBox, QVBoxLayout,
    QWidget,
)

from gmode.project import Project
from gmode.sweep import SweepCollector, SweepResult, default_workers, get_parameter, parameter_label, step_projects

from . import theme
from .inspector import _FloatEdit
from .solver_process import serve
from .widgets import Segmented

QUANTITIES = {"n_eff": "n_eff", "n_g": "group index", "loss": "loss (dB/cm)", "TE": "TE fraction",
              "A_eff": "A_eff (µm²)", "D": "D (ps/nm/km)"}
_FIELD_BUDGET = 2e9  # bytes of mode fields kept for clicking through a sweep


def sweep_parameters(project: Project) -> list[tuple[str, str]]:
    """(label, path) pairs the GUI offers for this project."""
    out = [("wavelength", "wavelength")]
    for s in project.structures:
        base = f"structures.{s.name}"
        if s.type == "rectangle":
            out += [(f"{s.name} width", f"{base}.size.0"), (f"{s.name} height", f"{base}.size.1"),
                    (f"{s.name} x", f"{base}.center.0"), (f"{s.name} y", f"{base}.center.1")]
        elif s.type == "circle":
            out += [(f"{s.name} radius", f"{base}.radius"), (f"{s.name} x", f"{base}.center.0"),
                    (f"{s.name} y", f"{base}.center.1")]
    for name, m in project.materials.items():
        if m.kind == "constant":
            out.append((f"{name} index n", f"materials.{name}.n"))
        elif m.kind == "algaas":
            out.append((f"{name} Al fraction x", f"materials.{name}.x"))
    out += [("mesh step", "mesh.step"), ("domain width", "domain.size.0"), ("domain height", "domain.size.1")]
    return out


def suggested_range(project: Project, path: str) -> tuple[float, float]:
    v = get_parameter(project, path)
    if path == "wavelength":
        return round(v - 0.05, 6), round(v + 0.05, 6)
    if path.endswith(".x") and path.startswith("materials"):
        return 0.0, min(1.0, max(0.4, 2 * v))
    if path.endswith("center.0") or path.endswith("center.1"):
        return round(v - 0.2, 6), round(v + 0.2, 6)
    return round(0.8 * v, 6), round(1.2 * v, 6)


class SweepRunner(QObject):
    """Runs sweep steps on a pool of persistent solver processes; tracks modes as steps arrive."""

    progress = Signal(int, int)  # finished steps, total
    updated = Signal(object)  # partial SweepResult (tracked steps so far)
    finished = Signal(object, list)  # SweepResult, warnings
    failed = Signal(str, str)
    cancelled = Signal(object)  # partial SweepResult

    def __init__(self, parent=None, in_process: bool = False, workers: Optional[int] = None):
        super().__init__(parent)
        self.in_process = in_process
        self.n_workers = workers
        self._workers: list[dict] = []
        self._busy = False
        self._timer = QTimer(self, interval=40)
        self._timer.timeout.connect(self._poll)
        self.t_start = 0.0

    @property
    def busy(self) -> bool:
        return self._busy

    def elapsed(self) -> float:
        return time.perf_counter() - self.t_start if self._busy else 0.0

    def run(self, project: Project):
        if self._busy:
            return
        st = project.sweep
        values = st.values
        self._projects = step_projects(project, st.parameter, values, st.extra_modes)
        self._col = SweepCollector(st.parameter, values, project.solver.num_modes, st.keep_fields)
        self._queue = list(range(len(values)))
        self._finished = 0
        self._warnings: list[str] = []
        self._busy = True
        self.t_start = time.perf_counter()
        self.progress.emit(0, len(values))
        if self.in_process:
            for k, p in enumerate(self._projects):
                self._accept(k, p.solve(), [])
            self._busy = False
            self.finished.emit(self._col.result(), self._warnings)
            return
        n = self.n_workers or default_workers(len(values))
        self._ensure_workers(n)
        for w in self._workers:
            self._dispatch(w)
        self._timer.start()

    def cancel(self):
        if not self._busy:
            return
        self._timer.stop()
        self._kill_workers()
        self._busy = False
        self.cancelled.emit(self._col.result())

    def shutdown(self):
        self._timer.stop()
        self._kill_workers()

    # ---- pool -----------------------------------------------------------------------------
    def _ensure_workers(self, n):
        self._workers = [w for w in self._workers if w["proc"].is_alive()]
        ctx = mp.get_context("spawn")
        while len(self._workers) < n:
            conn, child = ctx.Pipe()
            proc = ctx.Process(target=serve, args=(child,), daemon=True, name=f"gmode-sweep-{len(self._workers)}")
            proc.start()
            child.close()
            self._workers.append({"proc": proc, "conn": conn, "step": None})

    def _kill_workers(self):
        for w in self._workers:
            w["proc"].terminate()
        for w in self._workers:
            w["proc"].join(timeout=2)
            w["conn"].close()
        self._workers = []

    def _dispatch(self, w):
        if self._queue:
            k = self._queue.pop(0)
            w["step"] = k
            w["conn"].send(("solve", self._projects[k].model_dump_json()))
        else:
            w["step"] = None

    def _poll(self):
        for w in self._workers:
            if w["step"] is None:
                continue
            try:
                if not w["conn"].poll():
                    if not w["proc"].is_alive():
                        raise EOFError
                    continue
                msg = w["conn"].recv()
            except (EOFError, OSError):
                self._abort("A solver process stopped unexpectedly (out of memory?)", "")
                return
            k = w["step"]
            if msg[0] != "ok":
                value = self._col.values[k]
                self._abort(f"step {k + 1} ({parameter_label(self._col.parameter)} = {value:g}): {msg[1]}", msg[2])
                return
            self._accept(k, msg[1], msg[2])
            self._dispatch(w)
        if self._finished == len(self._projects):
            self._timer.stop()
            self._busy = False
            self.finished.emit(self._col.result(), self._warnings)

    def _accept(self, k, modes, warnings):
        for msg in warnings:
            if msg not in self._warnings:
                self._warnings.append(msg)
        if self._col.keep_fields and self._finished == 0:
            per_step = sum(m.E.nbytes + m.H.nbytes + m.eps.nbytes for m in modes)
            if per_step * len(self._projects) > _FIELD_BUDGET:
                self._col.keep_fields = False
                self._warnings.append(
                    f"fields not kept: about {per_step * len(self._projects) / 1e9:.1f} GB for this sweep "
                    "(scalar results are unaffected)")
        before = self._col.done
        self._col.add(k, modes)
        self._finished += 1
        self.progress.emit(self._finished, len(self._projects))
        if self._col.done > before:
            self.updated.emit(self._col.result())

    def _abort(self, message, tb):
        self._timer.stop()
        self._kill_workers()
        self._busy = False
        self.failed.emit(message, tb)


class SweepSetup(QWidget):
    """Parameter, range and steps, stored in project.sweep (undoable)."""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc = doc
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.param = QComboBox()
        self.start = _FloatEdit()
        self.stop = _FloatEdit()
        self.steps = QSpinBox()
        self.steps.setRange(2, 2001)
        self.steps.setKeyboardTracking(False)
        self.keep = QCheckBox("keep fields")
        self.keep.setToolTip("Keep every step's mode fields, so clicking a point shows them")
        rng = QHBoxLayout()
        rng.setSpacing(6)
        rng.addWidget(self.start)
        dash = QLabel("to")
        dash.setObjectName("dim")
        rng.addWidget(dash)
        rng.addWidget(self.stop)
        for label, w in (("Parameter", self.param), ("Range", rng), ("Steps", self.steps)):
            lab = QLabel(label)
            lab.setObjectName("dim")
            form.addRow(lab, w)
        form.addRow(self.keep)
        self.note = QLabel()
        self.note.setObjectName("info")
        self.note.setWordWrap(True)
        form.addRow(self.note)
        self.param.activated.connect(self._param_picked)
        self.start.committed.connect(lambda v: self._set(start=v))
        self.stop.committed.connect(lambda v: self._set(stop=v))
        self.steps.valueChanged.connect(lambda v: self._set(steps=v))
        self.keep.toggled.connect(lambda v: self._set(keep_fields=v))
        doc.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        p = self.doc.project
        st = p.sweep
        self._choices = sweep_parameters(p)
        self.param.blockSignals(True)
        self.param.clear()
        paths = [path for _, path in self._choices]
        for label, _ in self._choices:
            self.param.addItem(label)
        if st.parameter not in paths:
            self.param.addItem(st.parameter)
            paths.append(st.parameter)
        self.param.setCurrentIndex(paths.index(st.parameter))
        self.param.blockSignals(False)
        self.start.set_value(st.start)
        self.stop.set_value(st.stop)
        self.steps.blockSignals(True)
        self.steps.setValue(st.steps)
        self.steps.blockSignals(False)
        self.keep.blockSignals(True)
        self.keep.setChecked(st.keep_fields)
        self.keep.blockSignals(False)
        n = p.solver.num_modes
        self.note.setText(f"tracks the first {n} mode{'s' if n > 1 else ''} (set in Solver), solving "
                          f"{n + st.extra_modes} per step so crossings stay in view")

    def _set(self, **changes):
        d = self.doc.project.model_dump()
        d["sweep"].update(changes)
        try:
            self.doc.edit(d, "Edit sweep")
        except ValueError:
            self.refresh()

    def _param_picked(self, i):
        if i >= len(self._choices):
            return
        path = self._choices[i][1]
        lo, hi = suggested_range(self.doc.project, path)
        self._set(parameter=path, start=lo, stop=hi)


class SweepView(QWidget):
    """Tracked modes against the swept parameter. Emits pointClicked(step, track)."""

    pointClicked = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: Optional[SweepResult] = None
        self.quantity = Segmented(list(QUANTITIES))
        self.controls = QWidget()
        bar = QHBoxLayout(self.controls)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addStretch()
        self.quantity.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        bar.addWidget(self.quantity)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plot = pg.PlotWidget()
        theme.style_plot(self.plot)
        self.plot.showGrid(x=True, y=True, alpha=0.08)
        self.legend = self.plot.addLegend(offset=(-10, 10), labelTextColor=theme.DIM)
        self.legend.setBrush(pg.mkBrush(7, 9, 8, 200))
        self.marker = pg.ScatterPlotItem(size=14, pen=pg.mkPen(theme.INK, width=1.5), brush=pg.mkBrush(0, 0, 0, 0))
        self.plot.addItem(self.marker)
        lay.addWidget(self.plot)
        self.placeholder = QLabel("set up a sweep on the right, then run it (F6)")
        self.placeholder.setObjectName("hint")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.placeholder)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.setStyleSheet(f"QProgressBar {{ background: {theme.HAIR2}; border: 0; }}"
                                    f"QProgressBar::chunk {{ background: {theme.ACCENT_LINE}; }}")
        self.progress.hide()
        lay.addWidget(self.progress)
        self.quantity.currentTextChanged.connect(lambda _: self.redraw())
        self._curves = []
        self.set_result(None)

    def set_result(self, result: Optional[SweepResult]):
        self.result = result
        self.plot.setVisible(result is not None)
        self.placeholder.setVisible(result is None)
        self.quantity.buttons["D"].setEnabled(result is not None and result.parameter == "wavelength"
                                              and len(result.values) >= 3)
        if self.quantity.currentText() == "D" and not self.quantity.buttons["D"].isEnabled():
            self.quantity.setCurrentText("n_eff")
        self.redraw()

    def data(self, q: str) -> np.ndarray:
        r = self.result
        return {"n_eff": lambda: r.neff.real, "n_g": lambda: r.group_index, "loss": lambda: r.loss_db_per_cm,
                "TE": lambda: r.te_fraction, "A_eff": lambda: r.effective_area,
                "D": lambda: r.dispersion()}[q]()

    def redraw(self):
        for c in self._curves:
            self.plot.removeItem(c)
        self._curves = []
        self.legend.clear()
        self.marker.clear()
        r = self.result
        if r is None or not len(r.values):
            return
        q = self.quantity.currentText()
        try:
            y = self.data(q)
        except ValueError:
            return
        self.plot.setLabel("bottom", r.label)
        self.plot.setLabel("left", QUANTITIES[q])
        for t in range(r.n_tracks):
            color = theme.PALETTE[t % len(theme.PALETTE)]
            te = np.nanmean(r.te_fraction[:, t]) if np.any(np.isfinite(r.te_fraction[:, t])) else np.nan
            pol = "" if not np.isfinite(te) else (" · TE" if te >= 0.5 else " · TM")
            c = pg.PlotDataItem(r.values, y[:, t], pen=pg.mkPen(color, width=1.6), symbol="o", symbolSize=5,
                                symbolBrush=color, symbolPen=None, name=f"mode {t}{pol}", connect="finite")
            c.sigPointsClicked.connect(lambda item, pts, ev, t=t: self._clicked(t, pts))
            self.plot.addItem(c)
            self._curves.append(c)

    def _clicked(self, track, points):
        if not len(points):
            return
        x = points[0].pos().x()
        step = int(np.argmin(np.abs(self.result.values - x)))
        self.mark(step, track)
        self.pointClicked.emit(step, track)

    def mark(self, step, track):
        try:
            y = self.data(self.quantity.currentText())[step, track]
        except (ValueError, IndexError):
            return
        if np.isfinite(y):
            self.marker.setData([self.result.values[step]], [y])
