"""Mode table and field viewer."""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from gmode.geometry import Circle, Rectangle
from gmode.plot import field as field_component
from gmode.results import Mode, ModeSet

from . import theme
from .widgets import Segmented, toggle

COMPONENTS = ["|E|", "Ex", "Ey", "Ez", "|H|", "Hx", "Hy", "Hz", "Sz", "n"]
_DB_FLOOR = -50.0


def mode_image(mode: Mode, component: str, part: str = "auto", log: bool = False):
    """Return (data[x, y], signed, label) for display."""
    if component == "n":
        return np.sqrt(mode.eps).real, False, "n"
    if component == "Sz":
        E, H = mode.E, mode.H
        f = 0.5 * np.real(E[0] * np.conj(H[1]) - E[1] * np.conj(H[0]))
        signed, label = False, "Sz"
    elif component in ("|E|", "|H|"):
        f, _ = field_component(mode, component[1])
        signed, label = False, component
    else:
        f, part = field_component(mode, component, part)
        signed, label = part != "abs", f"{part}({component})"
    if log:
        a = np.abs(f)
        f = np.maximum(20 * np.log10(np.maximum(a, 1e-300) / a.max()), _DB_FLOOR) if a.max() > 0 else a
        signed, label = False, f"{label} (dB)"
    return f, signed, label


class ModeTable(QTableWidget):
    modeSelected = Signal(int)
    HEADERS = ["#", "n_eff", "Im(n_eff)", "loss (dB/cm)", "n_g", "TE fraction", "A_eff (µm²)"]

    def __init__(self, parent=None):
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.itemSelectionChanged.connect(self._selected)

    def set_modes(self, modes: ModeSet | None):
        self.blockSignals(True)
        self.setRowCount(0 if modes is None else len(modes))
        for i, m in enumerate(modes or []):
            vals = [str(i), f"{m.neff.real:.6f}", f"{m.neff.imag:.3e}", f"{m.loss_db_per_cm:.4g}",
                    f"{m.group_index:.5f}", f"{m.te_fraction:.3f}", f"{m.effective_area:.4f}"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(i, j, it)
        self.blockSignals(False)
        if modes:
            self.selectRow(0)
            self.modeSelected.emit(0)

    def _selected(self):
        rows = {i.row() for i in self.selectedItems()}
        if rows:
            self.modeSelected.emit(min(rows))


class FieldViewer(QWidget):
    """Mode field plot. Its controls live in `self.controls`, which the window puts in the stage bar."""

    PART_KEYS = {"auto": "auto", "Re": "real", "Im": "imag", "abs": "abs"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modes: ModeSet | None = None
        self.index = 0
        self.component = Segmented(COMPONENTS)
        self.part = Segmented(list(self.PART_KEYS))
        self.log = toggle("dB")
        self.outline = toggle("outline", True)
        self.controls = QWidget()
        bar = QHBoxLayout(self.controls)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        bar.addStretch()
        for w in (self.component, self.part, self.log, self.outline):
            w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            bar.addWidget(w)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plot = pg.PlotWidget()
        theme.style_plot(self.plot)
        self.plot.setAspectLocked(True)
        self.plot.setLabel("bottom", "x (µm)")
        self.plot.setLabel("left", "y (µm)")
        self.image = pg.ImageItem()
        self.plot.addItem(self.image)
        self.cbar = pg.ColorBarItem(values=(0, 1), colorMap=theme.magnitude_colormap(), width=10, interactive=False)
        self.cbar.setImageItem(self.image, insert_in=self.plot.getPlotItem())
        self.cbar.axis.setStyle(tickFont=theme.mono_font(9))
        self.cbar.axis.setTextPen(pg.mkPen(theme.FAINT))
        self.caption = pg.TextItem(color=theme.DIM, anchor=(0, 0))
        self.caption.setFont(theme.mono_font(10))
        self.caption.setParentItem(self.plot.getPlotItem().vb)
        self.caption.setPos(10, 6)
        self._outlines = []
        lay.addWidget(self.plot)
        self.placeholder = QLabel("solve (F5) to see mode fields")
        self.placeholder.setObjectName("hint")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.placeholder)
        for w in (self.component, self.part):
            w.currentTextChanged.connect(lambda _: self.redraw())
        for w in (self.log, self.outline):
            w.toggled.connect(lambda _: self.redraw())
        self.set_modes(None)

    def set_modes(self, modes: ModeSet | None):
        first = self.modes is None
        self.modes = modes
        self.index = 0
        self.plot.setVisible(bool(modes))
        self.placeholder.setVisible(not modes)
        self.controls.setEnabled(bool(modes))
        self.redraw()
        if modes and first:
            self.plot.autoRange()

    def show_mode(self, i: int):
        self.index = i
        self.redraw()

    def redraw(self):
        for it in self._outlines:
            self.plot.removeItem(it)
        self._outlines = []
        if not self.modes or self.index >= len(self.modes):
            self.caption.setText("")
            return
        m = self.modes[self.index]
        comp = self.component.currentText()
        self.part.setEnabled(comp in ("Ex", "Ey", "Ez", "Hx", "Hy", "Hz"))
        f, signed, label = mode_image(m, comp, self.PART_KEYS[self.part.currentText()], self.log.isChecked())
        dx, dy = m.x[1] - m.x[0], m.y[1] - m.y[0]
        self.image.setImage(f, autoLevels=False)
        self.image.setRect(QRectF(m.x[0] - dx / 2, m.y[0] - dy / 2, len(m.x) * dx, len(m.y) * dy))
        if signed:
            v = float(np.abs(f).max()) or 1.0
            self.cbar.setColorMap(theme.field_colormap())
            self.cbar.setLevels((-v, v))
        else:
            lo, hi = float(np.min(f)), float(np.max(f))
            self.cbar.setColorMap(theme.index_colormap() if comp == "n" else theme.magnitude_colormap())
            self.cbar.setLevels((lo, hi if hi > lo else lo + 1))
        imag = f" {m.neff.imag:+.2e}i" if abs(m.neff.imag) > 1e-12 else ""
        self.caption.setText(f"mode {self.index}  ·  {label}  ·  n_eff {m.neff.real:.6f}{imag}")
        if self.outline.isChecked() and comp != "n":
            self._draw_outlines()

    def _draw_outlines(self):
        pen = pg.mkPen((255, 255, 255, 190), width=1.2)
        for s in self.modes.project.structures:
            if isinstance(s, Rectangle):
                x0, y0, x1, y1 = s.bounds()
                xs, ys = [x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0]
            elif isinstance(s, Circle):
                t = np.linspace(0, 2 * np.pi, 120)
                xs, ys = s.center[0] + s.radius * np.cos(t), s.center[1] + s.radius * np.sin(t)
            else:
                v = np.asarray(s.vertices + s.vertices[:1])
                xs, ys = v[:, 0], v[:, 1]
            it = pg.PlotCurveItem(np.asarray(xs, float), np.asarray(ys, float), pen=pen)
            self.plot.addItem(it, ignoreBounds=True)  # substrates often extend far past the domain
            self._outlines.append(it)
