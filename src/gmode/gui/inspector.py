"""Property inspector: an editor form generated from a pydantic model's fields."""
import types
import typing
from typing import Literal, Union, get_args, get_origin

import numpy as np
import pyqtgraph as pg
from pydantic import BaseModel

from . import theme
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

LABELS = {
    "name": "Name", "wavelength": "Wavelength (µm)", "background": "Background material",
    "center": "Center (µm)", "size": "Size (µm)", "radius": "Radius (µm)", "material": "Material",
    "vertices": "Vertices (µm)", "dx": "dx (µm)", "dy": "dy (µm)", "subpixel": "Subpixel samples",
    "x_min": "x min", "x_max": "x max", "y_min": "y min", "y_max": "y max",
    "x_symmetry": "Symmetry at x = center", "y_symmetry": "Symmetry at y = center",
    "pml_layers": "PML layers", "pml_order": "PML grading order",
    "pml_sigma": "PML σ (empty = auto)", "pml_kappa": "PML κ (empty = σ)",
    "backend": "Backend", "num_modes": "Number of modes", "target_neff": "Target n_eff (empty = auto)",
    "bend_radius": "Bend radius (µm, empty = straight)", "bend_radial_axis": "Bend radial axis",
    "bend_location": "Radius measured at (µm, empty = center)",
    "mfd": "Mode field diameter (µm, empty = off)",
    "description": "Description", "reference": "Reference", "wavelength_range": "Valid range (µm)",
    "n": "n", "k": "k", "a": "a", "terms": "Terms (B, C in µm²)", "power_terms": "Power terms (D, p)",
    "eps_inf": "ε∞", "poles": "Poles (eV)", "x": "Al fraction x", "wavelengths": "Wavelengths",
}
META_LAST = {"description", "reference", "wavelength_range"}
HIDDEN = {"kind", "type", "schema_version", "materials", "structures", "domain", "mesh", "boundaries", "solver",
          "sweep", "fiber"}


def _fmt(v) -> str:
    return "" if v is None else f"{v:.10g}"


def _unwrap_optional(tp):
    if get_origin(tp) in (Union, types.UnionType):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1 and len(get_args(tp)) == 2:
            return args[0], True
    return tp, False


class _FloatEdit(QLineEdit):
    """Line edit for a float; empty means None when optional. Emits committed(value) on change."""

    committed = Signal(object)

    def __init__(self, optional=False, placeholder=""):
        super().__init__()
        self.optional = optional
        self._value = None
        self.setPlaceholderText(placeholder or ("auto" if optional else ""))
        self.editingFinished.connect(self._finish)

    def set_value(self, v):
        self._value = v
        self.setText(_fmt(v))

    def _finish(self):
        t = self.text().strip()
        if not t and self.optional:
            v = None
        else:
            try:
                v = float(t)
            except ValueError:
                self.set_value(self._value)
                return
        if v != self._value:
            self._value = v
            self.committed.emit(v)


class _Editor(QWidget):
    """One field editor. Subclasses set .committed callbacks via self.emit(value)."""

    def __init__(self, on_commit):
        super().__init__()
        self._on_commit = on_commit
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lay = lay

    def emit(self, v):
        self._on_commit(v)


class FloatEditor(_Editor):
    def __init__(self, on_commit, optional=False):
        super().__init__(on_commit)
        self.edit = _FloatEdit(optional)
        self.edit.committed.connect(self.emit)
        self.lay.addWidget(self.edit)

    def set_value(self, v):
        self.edit.set_value(v)


class IntEditor(_Editor):
    def __init__(self, on_commit):
        super().__init__(on_commit)
        self.spin = QSpinBox()
        self.spin.setRange(-10**6, 10**6)
        self.spin.setKeyboardTracking(False)
        self.spin.valueChanged.connect(self.emit)
        self.lay.addWidget(self.spin)

    def set_value(self, v):
        self.spin.blockSignals(True)
        self.spin.setValue(int(v))
        self.spin.blockSignals(False)


class TextEditor(_Editor):
    def __init__(self, on_commit):
        super().__init__(on_commit)
        self.edit = QLineEdit()
        self.edit.editingFinished.connect(lambda: self.edit.text() != self._v and self.emit(self.edit.text()))
        self.lay.addWidget(self.edit)
        self._v = ""

    def set_value(self, v):
        self._v = v or ""
        self.edit.setText(self._v)
        self.edit.setCursorPosition(0)


class BoolEditor(_Editor):
    def __init__(self, on_commit):
        super().__init__(on_commit)
        self.box = QCheckBox()
        self.box.toggled.connect(self.emit)
        self.lay.addWidget(self.box)

    def set_value(self, v):
        self.box.blockSignals(True)
        self.box.setChecked(bool(v))
        self.box.blockSignals(False)


class ChoiceEditor(_Editor):
    def __init__(self, on_commit, choices):
        super().__init__(on_commit)
        self.combo = QComboBox()
        self.combo.addItems([str(c) for c in choices])
        self.combo.currentTextChanged.connect(self.emit)
        self.lay.addWidget(self.combo)

    def set_choices(self, choices):
        cur = self.combo.currentText()
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems([str(c) for c in choices])
        self.combo.setCurrentText(cur)
        self.combo.blockSignals(False)

    def set_value(self, v):
        self.combo.blockSignals(True)
        if self.combo.findText(str(v)) < 0:
            self.combo.addItem(str(v))
        self.combo.setCurrentText(str(v))
        self.combo.blockSignals(False)


class TupleEditor(_Editor):
    """Fixed-length tuple of floats, optionally None as a whole (all fields empty)."""

    def __init__(self, on_commit, n=2, optional=False):
        super().__init__(on_commit)
        self.optional = optional
        self.edits = [_FloatEdit(optional) for _ in range(n)]
        for e in self.edits:
            e.committed.connect(self._changed)
            self.lay.addWidget(e)

    def set_value(self, v):
        for i, e in enumerate(self.edits):
            e.set_value(None if v is None else v[i])

    def _changed(self, _):
        vals = [e._value for e in self.edits]
        if all(v is None for v in vals) and self.optional:
            self.emit(None)
        elif all(v is not None for v in vals):
            self.emit(tuple(vals))


class TableEditor(_Editor):
    """List of rows: tuples of floats, or small models (e.g. Lorentz poles)."""

    def __init__(self, on_commit, columns, row_model=None):
        super().__init__(on_commit)
        self.columns, self.row_model = columns, row_model
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.cellChanged.connect(self._changed)
        buttons = QHBoxLayout()
        add, rem = QPushButton("Add row"), QPushButton("Remove row")
        add.clicked.connect(self._add)
        rem.clicked.connect(self._remove)
        buttons.addWidget(add)
        buttons.addWidget(rem)
        buttons.addStretch()
        box.addWidget(self.table)
        box.addLayout(buttons)
        self.lay.addLayout(box)
        self._rows = []

    def set_value(self, rows):
        self._rows = [self._as_list(r) for r in rows]
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            for j, v in enumerate(r):
                self.table.setItem(i, j, QTableWidgetItem(_fmt(v)))
        self.table.blockSignals(False)
        header = self.table.horizontalHeader().height() or 24
        self.table.setFixedHeight(header + 22 * min(max(len(self._rows), 1), 8) + 4)

    def _as_list(self, r):
        if isinstance(r, BaseModel):
            return [getattr(r, c) for c in self.columns]
        if isinstance(r, dict):
            return [r[c] for c in self.columns]
        return list(r)

    def _commit(self, rows):
        if self.row_model is not None:
            self.emit([dict(zip(self.columns, r)) for r in rows])
        else:
            self.emit([tuple(r) for r in rows])

    def _changed(self, i, j):
        try:
            v = float(self.table.item(i, j).text())
        except (ValueError, AttributeError):
            self.set_value(self._rows)
            return
        rows = [list(r) for r in self._rows]
        rows[i][j] = v
        self._commit(rows)

    def _add(self):
        rows = [list(r) for r in self._rows]
        rows.append(list(rows[-1]) if rows else [0.0] * len(self.columns))
        self._commit(rows)

    def _remove(self):
        i = self.table.currentRow()
        rows = [list(r) for r in self._rows]
        if rows:
            rows.pop(i if 0 <= i < len(rows) else -1)
            self._commit(rows)


class SummaryEditor(_Editor):
    def __init__(self, on_commit):
        super().__init__(on_commit)
        self.label = QLabel()
        self.lay.addWidget(self.label)

    def set_value(self, v):
        if v is None:
            self.label.setText("none")
        else:
            a = np.asarray(v, float)
            self.label.setText(f"{len(a)} values, {a.min():.4g} to {a.max():.4g}")


def _editor_for(name, annotation, on_commit, choices):
    if name in choices:
        return ChoiceEditor(on_commit, choices[name])
    tp, optional = _unwrap_optional(annotation)
    if get_origin(tp) is typing.Annotated:
        tp = get_args(tp)[0]
    origin, args = get_origin(tp), get_args(tp)
    if origin is Literal:
        return ChoiceEditor(on_commit, args)
    if tp is bool:
        return BoolEditor(on_commit)
    if tp is int:
        return IntEditor(on_commit)
    if tp is float:
        return FloatEditor(on_commit, optional)
    if tp is str:
        return TextEditor(on_commit)
    if origin is tuple and all(a is float for a in args):
        return TupleEditor(on_commit, len(args), optional)
    if origin is list:
        (item,) = args
        if get_origin(item) is tuple:
            cols = {"vertices": ["x", "y"], "terms": ["B", "C"], "power_terms": ["D", "p"]}.get(
                name, [f"c{i}" for i in range(len(get_args(item)))])
            return TableEditor(on_commit, cols)
        if isinstance(item, type) and issubclass(item, BaseModel):
            return TableEditor(on_commit, list(item.model_fields), row_model=item)
        return SummaryEditor(on_commit)
    return SummaryEditor(on_commit)


class ModelForm(QWidget):
    """Editors for every visible field of a pydantic model. Emits edited({field: value})."""

    edited = Signal(dict)

    def __init__(self, model: BaseModel, choices: dict | None = None, parent=None, hidden=()):
        super().__init__(parent)
        self.model_type = type(model)
        self.choices = choices or {}
        self.editors: dict[str, _Editor] = {}
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        fields = list(self.model_type.model_fields.items())
        fields.sort(key=lambda kv: kv[0] in META_LAST)  # stable: model fields first, provenance last
        for name, info in fields:
            if name in HIDDEN or name in hidden:
                continue
            ed = _editor_for(name, info.annotation, lambda v, n=name: self.edited.emit({n: v}), self.choices)
            self.editors[name] = ed
            label = QLabel(LABELS.get(name, name))
            label.setObjectName("dim")
            if isinstance(ed, TableEditor):
                label.setAlignment(Qt.AlignmentFlag.AlignTop)
            form.addRow(label, ed)
        self.set_model(model)

    def set_model(self, model: BaseModel, choices: dict | None = None):
        if choices:
            self.choices = choices
            for n, c in choices.items():
                if isinstance(self.editors.get(n), ChoiceEditor):
                    self.editors[n].set_choices(c)
        for name, ed in self.editors.items():
            ed.set_value(getattr(model, name))


class DispersionPlot(pg.PlotWidget):
    """n and k against wavelength for one material, with the project wavelength marked."""

    def __init__(self, parent=None):
        super().__init__(parent)
        theme.style_plot(self)
        self.setMinimumHeight(170)
        self.setLabel("bottom", "wavelength (µm)")
        legend = self.addLegend(offset=(5, 5), labelTextColor=theme.DIM)
        legend.setBrush(pg.mkBrush(0, 0, 0, 0))
        self.showGrid(x=True, y=True, alpha=0.08)

    def show_material(self, material, wavelength):
        self.clear()
        r = material.valid_range() or (0.4, 2.0)
        lo, hi = r[0], min(r[1], max(4 * r[0], 2.5 * wavelength, r[0] * 1.5))
        wl = np.linspace(lo, hi, 300)
        try:
            n = np.asarray(material.index(wl))
        except ValueError:
            return
        self.plot(wl, n.real, pen=pg.mkPen(theme.ACCENT_INK, width=1.6), name="n")
        if np.any(n.imag):
            self.plot(wl, n.imag, pen=pg.mkPen(theme.WARN, width=1.6), name="k")
        self.addItem(pg.InfiniteLine(wavelength, pen=pg.mkPen(theme.FAINT, style=Qt.PenStyle.DashLine)))


class InspectorPanel(QWidget):
    """Shows the selected object's form; edits go to the document as undoable steps."""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.form = None
        self._key = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel()
        self.title.setObjectName("objtitle")
        self.title.setFont(theme.serif_font(15))
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setObjectName("info")
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName("error")
        self.body = QVBoxLayout()
        self.plot = DispersionPlot()
        self.rename = QLineEdit()
        self.rename.setPlaceholderText("material name")
        self.rename.editingFinished.connect(self._rename)
        lay.addWidget(self.title)
        lay.addWidget(self.rename)
        lay.addWidget(self.info)
        lay.addLayout(self.body)
        lay.addWidget(self.error)
        lay.addWidget(self.plot)
        lay.addStretch()
        doc.selectionChanged.connect(self._on_selection)
        doc.changed.connect(self.refresh)
        self.refresh(rebuild=True)

    def _on_selection(self, _sel):
        self.refresh(rebuild=True)

    def _choices(self):
        names = list(self.doc.project.materials)
        return {"material": names, "background": names}

    def refresh(self, rebuild=False):
        obj = self.doc.selected_object()
        sel = self.doc.selection
        self.error.clear()
        key = (sel, type(obj))
        if obj is None:
            self._clear()
            self.title.setText("Nothing selected")
            self.info.setText("Select an item in the project tree or a shape in the geometry view.")
            return
        if rebuild or key != self._key or self.form is None:
            self._clear()
            # the project description is shown as wrapped text above the form instead
            self.form = ModelForm(obj, self._choices(), hidden=("description",) if sel[0] == "project" else ())
            self.form.edited.connect(self._apply)
            self.body.addWidget(self.form)
            self._key = key
        else:
            self.form.set_model(obj, self._choices())
        is_mat = sel[0] == "material"
        kind = {"rectangle": "Rectangle", "circle": "Circle", "polygon": "Polygon"}
        self.title.setText({"project": "Simulation", "domain": "Domain", "mesh": "Mesh", "boundaries": "Boundaries",
                            "solver": "Solver", "fiber": "Fiber coupling"}.get(sel[0]) or
                           (sel[1] if sel[0] == "material" else f"{obj.name} · {kind.get(obj.type, '')}"))
        self.rename.setVisible(is_mat)
        if is_mat:
            self.rename.setText(sel[1])
            text = obj.description + (f"\n{obj.reference}" if obj.reference else "")
            self.info.setText(text)
            self.plot.setVisible(True)
            self.plot.show_material(obj, self.doc.project.wavelength)
        else:
            self.info.setText(self.doc.project.description if sel[0] == "project" else {
                "boundaries": "PML layers are added outside the domain. Symmetry planes pass through the "
                              "domain center; pec/pmc there selects the mode parity.",
                "mesh": "Subpixel samples average the permittivity at material interfaces.",
                "solver": "Modes are found nearest the target index (default: the largest index present; for "
                          "bends, the straight guide's n_eff).",
                "fiber": "Reports each mode's coupling to a Gaussian fiber beam at the facet (mode-mismatch "
                         "overlap; no Fresnel reflection). SMF-28: 10.4 µm, lensed fibers: 2 to 3 µm.",
            }.get(sel[0], ""))
            self.plot.setVisible(False)

    def _clear(self):
        if self.form is not None:
            self.form.setParent(None)
            self.form.deleteLater()
            self.form = None
        self._key = None
        self.rename.setVisible(False)
        self.plot.setVisible(False)

    def _apply(self, changes: dict):
        try:
            self.doc.update_selected(changes)
        except ValueError as e:
            self.refresh()
            self.error.setText(_short_error(e))

    def _rename(self):
        sel = self.doc.selection
        if sel and sel[0] == "material":
            try:
                self.doc.rename_material(sel[1], self.rename.text())
            except ValueError as e:
                self.rename.setText(sel[1])
                self.error.setText(_short_error(e))


def _short_error(e: Exception) -> str:
    errs = getattr(e, "errors", None)
    if callable(errs):
        try:
            return "; ".join(f"{'.'.join(str(p) for p in d['loc'])}: {d['msg']}" if d.get("loc") else d["msg"]
                             for d in e.errors())
        except Exception:
            pass
    return str(e)
