"""Geometry editor: structures as draggable shapes over a refractive-index map."""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from gmode.geometry import Circle, Polygon, Rectangle

from . import theme
from .document import ProjectDocument

PALETTE = theme.PALETTE
_PREVIEW_MAX = 500  # samples per axis for the index map


def material_color(project, name) -> str:
    names = list(project.materials)
    return PALETTE[names.index(name) % len(PALETTE)] if name in names else "#ffffff"


def snap(v, step):
    return float(np.round(np.round(v / step) * step, 9)) if step > 0 else float(np.round(v, 9))


class GeometryCanvas(pg.PlotWidget):
    statusMessage = Signal(str)

    def __init__(self, doc: ProjectDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.snap_step = 0.01
        self.show_index = True
        theme.style_plot(self)
        self.setAspectLocked(True)
        self.showGrid(x=True, y=True, alpha=0.06)
        self.setLabel("bottom", "x (µm)")
        self.setLabel("left", "y (µm)")
        self.image = pg.ImageItem()
        self.image.setZValue(-10)
        self.addItem(self.image)
        self.cbar = pg.ColorBarItem(values=(1, 3.5), colorMap=theme.index_colormap(), label="n", width=10,
                                    interactive=False)
        self.cbar.setImageItem(self.image, insert_in=self.getPlotItem())
        self.cbar.axis.setStyle(tickFont=theme.mono_font(9))
        self.cbar.axis.setTextPen(pg.mkPen(theme.FAINT))
        self._items = []  # domain/PML/symmetry overlays
        self._rois = []
        self._first = True
        self._pending = QTimer(self, singleShot=True, interval=0)
        self._pending.timeout.connect(self.rebuild)
        doc.changed.connect(self._pending.start)  # deferred: never delete a shape inside its own drag signal
        doc.selectionChanged.connect(self._on_selection)
        self.scene().sigMouseMoved.connect(self._mouse_moved)
        self.rebuild()

    # ---- drawing ------------------------------------------------------------------------
    def rebuild(self):
        p = self.doc.project
        for it in self._items + self._rois:
            self.removeItem(it)
        self._items, self._rois = [], []
        self._draw_index_map()
        self._draw_domain()
        for i, s in enumerate(p.structures):
            roi = self._make_roi(i, s)
            self.addItem(roi)
            self._rois.append(roi)
        self._restyle()
        if self._first:
            self.fit()
            self._first = False

    def fit(self):
        (cx, cy), (w, h) = self.doc.project.domain.center, self.doc.project.domain.size
        self.setRange(QRectF(cx - w / 2, cy - h / 2, w, h), padding=0.08)

    def _extent(self):
        p = self.doc.project
        (cx, cy), (w, h) = p.domain.center, p.domain.size
        b, m = p.boundaries, p.mesh
        x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
        x0 -= b.pml_layers * m.dx if b.x_min == "pml" else 0
        x1 += b.pml_layers * m.dx if b.x_max == "pml" else 0
        y0 -= b.pml_layers * m.dy if b.y_min == "pml" else 0
        y1 += b.pml_layers * m.dy if b.y_max == "pml" else 0
        return x0, x1, y0, y1

    def _draw_index_map(self):
        if not self.show_index:
            self.image.clear()
            return
        p = self.doc.project
        x0, x1, y0, y1 = self._extent()
        nx = int(min(_PREVIEW_MAX, max(2, round((x1 - x0) / p.mesh.dx))))
        ny = int(min(_PREVIEW_MAX, max(2, round((y1 - y0) / p.mesh.dy))))
        x = x0 + (np.arange(nx) + 0.5) * (x1 - x0) / nx
        y = y0 + (np.arange(ny) + 0.5) * (y1 - y0) / ny
        try:
            n = np.sqrt(p.eps_at(x[:, None], y[None, :])).real
        except ValueError as e:  # e.g. a tabulated material outside its range
            self.statusMessage.emit(str(e))
            self.image.clear()
            return
        self.image.setImage(n, autoLevels=False)
        self.image.setRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        lo, hi = float(np.nanmin(n)), float(np.nanmax(n))
        self.cbar.setLevels((lo, hi if hi > lo else lo + 1))

    def _draw_domain(self):
        p = self.doc.project
        (cx, cy), (w, h) = p.domain.center, p.domain.size
        dom = QGraphicsRectItem(cx - w / 2, cy - h / 2, w, h)
        pen = QPen(QColor(theme.ACCENT_LINE), 0)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        dom.setPen(pen)
        self.addItem(dom)
        self._items.append(dom)
        x0, x1, y0, y1 = self._extent()
        b = p.boundaries
        notes = [f"domain {w:g} × {h:g} µm", f"mesh {p.mesh.dx * 1e3:g} × {p.mesh.dy * 1e3:g} nm"]
        if "pml" in (b.x_min, b.x_max, b.y_min, b.y_max):
            notes.append(f"PML {b.pml_layers} layers")
        sym = [f"{ax} {v}" for ax, v in (("x", b.x_symmetry), ("y", b.y_symmetry)) if v != "none"]
        if sym:
            notes.append("symmetry " + ", ".join(sym))
        label = pg.TextItem("  ·  ".join(notes), color=theme.ACCENT_INK, anchor=(0, 1))
        label.setFont(theme.mono_font(9.5))
        label.setOpacity(0.75)
        label.setPos(cx - w / 2, cy + h / 2)
        self.addItem(label, ignoreBounds=True)
        self._items.append(label)
        pml_brush = QBrush(QColor(230, 236, 232, 26), Qt.BrushStyle.BDiagPattern)
        bands = []
        if b.x_min == "pml":
            bands.append((x0, y0, cx - w / 2 - x0, y1 - y0))
        if b.x_max == "pml":
            bands.append((cx + w / 2, y0, x1 - cx - w / 2, y1 - y0))
        if b.y_min == "pml":
            bands.append((x0, y0, x1 - x0, cy - h / 2 - y0))
        if b.y_max == "pml":
            bands.append((x0, cy + h / 2, x1 - x0, y1 - cy - h / 2))
        for r in bands:
            it = QGraphicsRectItem(*r)
            it.setBrush(pml_brush)
            it.setPen(QPen(Qt.PenStyle.NoPen))
            self.addItem(it)
            self._items.append(it)
        sym_pen = pg.mkPen(theme.WARN, width=1.2, style=Qt.PenStyle.DashDotLine)
        if b.x_symmetry != "none":
            it = pg.PlotCurveItem([cx, cx], [y0, y1], pen=sym_pen)
            self.addItem(it)
            self._items.append(it)
        if b.y_symmetry != "none":
            it = pg.PlotCurveItem([x0, x1], [cy, cy], pen=sym_pen)
            self.addItem(it)
            self._items.append(it)

    def _make_roi(self, i, s):
        kw = dict(pen=pg.mkPen("w"), handlePen=pg.mkPen(theme.INK), handleHoverPen=pg.mkPen(theme.ACCENT_INK),
                  hoverPen=pg.mkPen(theme.ACCENT_INK, width=2), movable=True, rotatable=False, removable=False,
                  snapSize=self.snap_step or 1e-3, translateSnap=self.snap_step > 0, scaleSnap=self.snap_step > 0)
        if isinstance(s, Rectangle):
            (cx, cy), (w, h) = s.center, s.size
            roi = pg.ROI((cx - w / 2, cy - h / 2), (w, h), **kw)
            for h_pos, anchor in (((1, 1), (0, 0)), ((0, 0), (1, 1)), ((1, 0), (0, 1)), ((0, 1), (1, 0)),
                                  ((0.5, 1), (0.5, 0)), ((0.5, 0), (0.5, 1)), ((1, 0.5), (0, 0.5)), ((0, 0.5), (1, 0.5))):
                roi.addScaleHandle(h_pos, anchor)
        elif isinstance(s, Circle):
            (cx, cy), r = s.center, s.radius
            roi = pg.CircleROI((cx - r, cy - r), (2 * r, 2 * r), **kw)
        else:
            roi = pg.PolyLineROI(s.vertices, closed=True, **kw)
        roi.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        roi.sigClicked.connect(lambda *_: self.doc.select(("structure", i)))
        roi.sigRegionChangeStarted.connect(lambda *_: self.doc.select(("structure", i)))
        roi.sigRegionChangeFinished.connect(lambda r: self._commit(i, r))
        roi.setToolTip(f"{s.name} [{s.material}]")
        return roi

    def _on_selection(self, _sel):
        self._restyle()

    def _restyle(self):
        p, sel = self.doc.project, self.doc.selection
        for i, roi in enumerate(self._rois):
            if i >= len(p.structures):
                continue
            color = material_color(p, p.structures[i].material)
            selected = sel == ("structure", i)
            pen = pg.mkPen(color, width=2.4 if selected else 1.3)
            roi.setPen(pen)
            roi.currentPen = pen
            roi.setZValue(10 + i + (1000 if selected else 0))
            for h in roi.getHandles():
                h.setVisible(selected)

    # ---- editing ------------------------------------------------------------------------
    def _commit(self, i, roi):
        p = self.doc.project
        if i >= len(p.structures):
            return
        # Snap only what the user changed: a pure move snaps the offset (so off-grid shapes keep
        # their exact size and shape), a resize snaps the moved edges, a vertex drag that vertex.
        s, st = p.structures[i], self.snap_step
        same = lambda a, b: abs(a - b) < 1e-7  # noqa: E731
        if isinstance(s, Rectangle):
            pos, size = roi.pos(), roi.size()
            x0, x1 = sorted((pos.x(), pos.x() + size.x()))
            y0, y1 = sorted((pos.y(), pos.y() + size.y()))
            (cx, cy), (w, h) = s.center, s.size
            if same(x1 - x0, w) and same(y1 - y0, h):
                dx, dy = snap((x0 + x1) / 2 - cx, st), snap((y0 + y1) / 2 - cy, st)
                changes = dict(center=(round(cx + dx, 9), round(cy + dy, 9)))
            else:
                old = (cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2)
                x0, x1, y0, y1 = (o if same(v, o) else snap(v, st) for v, o in zip((x0, x1, y0, y1), old))
                if x1 - x0 <= 0 or y1 - y0 <= 0:
                    self._pending.start()
                    return
                changes = dict(center=(round((x0 + x1) / 2, 9), round((y0 + y1) / 2, 9)),
                               size=(round(x1 - x0, 9), round(y1 - y0, 9)))
        elif isinstance(s, Circle):
            pos, size = roi.pos(), roi.size()
            r = abs(size.x()) / 2
            (cx, cy) = s.center
            new_c = (pos.x() + size.x() / 2, pos.y() + size.y() / 2)
            if same(r, s.radius):
                changes = dict(center=(round(cx + snap(new_c[0] - cx, st), 9), round(cy + snap(new_c[1] - cy, st), 9)))
            else:
                changes = dict(center=(snap(new_c[0], st), snap(new_c[1], st)), radius=snap(r, st / 2 if st else 0))
        else:
            old = s.vertices
            pts = [roi.mapToParent(h.pos()) for h in roi.getHandles()]
            new = [(q.x(), q.y()) for q in pts]
            deltas = [(a[0] - b[0], a[1] - b[1]) for a, b in zip(new, old)] if len(new) == len(old) else None
            if deltas and all(same(d[0], deltas[0][0]) and same(d[1], deltas[0][1]) for d in deltas):
                dx, dy = snap(deltas[0][0], st), snap(deltas[0][1], st)
                verts = [(round(x + dx, 9), round(y + dy, 9)) for x, y in old]
            else:
                olds = {(round(x, 7), round(y, 7)) for x, y in old}
                verts = [(x, y) if (round(x, 7), round(y, 7)) in olds else (snap(x, st), snap(y, st))
                         for x, y in new]
            changes = dict(vertices=verts)
        try:
            self.doc.update_structure(i, changes, f"Edit {s.name}")
        except ValueError as e:
            self.statusMessage.emit(str(e))
        self._pending.start()  # re-sync the shape with the (snapped) model

    def _mouse_moved(self, pos):
        if self.sceneBoundingRect().contains(pos):
            q = self.getPlotItem().vb.mapSceneToView(pos)
            try:
                n = np.sqrt(self.doc.project.eps_at(q.x(), q.y()))
                self.statusMessage.emit(f"x = {q.x():.4f} µm, y = {q.y():.4f} µm, n = {complex(n).real:.4f}"
                                        + (f" + {complex(n).imag:.3g}i" if complex(n).imag else ""))
            except ValueError:
                pass

    def view_center(self) -> QPointF:
        (x0, x1), (y0, y1) = self.getPlotItem().vb.viewRange()
        c = QPointF((x0 + x1) / 2, (y0 + y1) / 2)
        return QPointF(snap(c.x(), self.snap_step), snap(c.y(), self.snap_step))

    def set_snap(self, step: float):
        self.snap_step = step
        self.rebuild()

    def set_show_index(self, on: bool):
        self.show_index = on
        self._draw_index_map()
        self.cbar.setVisible(on)
