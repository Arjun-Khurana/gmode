"""Material dialogs."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QSplitter, QVBoxLayout, QWidget,
)

import gmode as gm

from .inspector import DispersionPlot


class LibraryDialog(QDialog):
    """Pick a built-in material; shows its source, valid range and dispersion."""

    def __init__(self, wavelength: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add material from library")
        self.resize(720, 420)
        self.wavelength = wavelength
        self.materials = gm.material_library()
        lay = QVBoxLayout(self)
        split = QSplitter()
        self.list = QListWidget()
        for name, m in self.materials.items():
            it = QListWidgetItem(name)
            it.setToolTip(m.description)
            self.list.addItem(it)
        right = QWidget()
        rl = QVBoxLayout(right)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form = QFormLayout()
        self.form = form
        self.name = QLineEdit()
        self.x = QDoubleSpinBox()
        self.x.setRange(0, 1)
        self.x.setSingleStep(0.05)
        self.x.setDecimals(3)
        self.x.setValue(0.3)
        self.x.valueChanged.connect(self._update)
        form.addRow("Name in project", self.name)
        form.addRow("Al fraction x", self.x)
        self.plot = DispersionPlot()
        rl.addWidget(self.info)
        rl.addLayout(form)
        rl.addWidget(self.plot)
        split.addWidget(self.list)
        split.addWidget(right)
        split.setSizes([180, 540])
        lay.addWidget(split)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.list.currentTextChanged.connect(self._picked)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.list.setCurrentRow(1)

    def _picked(self, name):
        self.name.setText(name)
        self._update()

    def _update(self):
        name = self.list.currentItem().text() if self.list.currentItem() else None
        if not name:
            return
        is_alloy = name == "AlGaAs"
        self.form.setRowVisible(self.x, is_alloy)
        m = self.material()
        r = m.valid_range()
        rng = f"{r[0]:.3g} to {r[1]:.3g} µm" if r else "any wavelength"
        n = complex(m.index(self.wavelength)) if m.in_range(self.wavelength) else None
        n_txt = f"n = {n.real:.4f}" + (f" + {n.imag:.3g}i" if n and n.imag else "") if n else "outside valid range"
        self.info.setText(f"<b>{name}</b>: {m.description}<br>{m.reference or ''}<br>"
                          f"Valid: {rng}. At {self.wavelength:g} µm: {n_txt}")
        self.plot.show_material(m, self.wavelength)

    def material(self):
        name = self.list.currentItem().text()
        return gm.material(name, x=self.x.value()) if name == "AlGaAs" else self.materials[name]

    def project_name(self) -> str:
        return self.name.text().strip() or self.list.currentItem().text()


class ConstantDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add constant-index material")
        form = QFormLayout(self)
        self.name = QLineEdit("material")
        self.n = QDoubleSpinBox()
        self.n.setRange(-100, 100)
        self.n.setDecimals(5)
        self.n.setValue(1.5)
        self.k = QDoubleSpinBox()
        self.k.setRange(0, 100)
        self.k.setDecimals(6)
        form.addRow("Name", self.name)
        form.addRow("n", self.n)
        form.addRow("k", self.k)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def material(self):
        return gm.ConstantMaterial(n=self.n.value(), k=self.k.value())
