"""Small styled widgets: segmented controls, sections, the mode list and readout."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QProgressBar, QPushButton, QVBoxLayout,
    QWidget,
)

from . import theme


class Segmented(QFrame):
    """Exclusive row of buttons. API mirrors QComboBox's text accessors."""

    currentTextChanged = Signal(str)

    def __init__(self, options, current=None, parent=None):
        super().__init__(parent)
        self.setObjectName("seg")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for i, opt in enumerate(options):
            b = QPushButton(opt)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == len(options) - 1:
                b.setProperty("last", True)
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[opt] = b
        self.setCurrentText(current or options[0])
        self.group.buttonToggled.connect(lambda b, on: on and self.currentTextChanged.emit(b.text()))

    def currentText(self) -> str:
        b = self.group.checkedButton()
        return b.text() if b else ""

    def setCurrentText(self, text: str):
        if text in self.buttons and not self.buttons[text].isChecked():
            self.buttons[text].setChecked(True)

    def setEnabled(self, on: bool):
        super().setEnabled(on)
        for b in self.buttons.values():
            b.setEnabled(on)


def toggle(text, checked=False) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("toggle")
    b.setCheckable(True)
    b.setChecked(checked)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def section_label(text: str, right: str = "") -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lab = QLabel(text.upper())
    lab.setObjectName("seclabel")
    f = theme.mono_font(8.5)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
    lab.setFont(f)
    lay.addWidget(lab)
    lay.addStretch()
    if right:
        r = QLabel(right)
        r.setObjectName("seclabel")
        lay.addWidget(r)
    w.label = lab
    return w


class Section(QFrame):
    """Hairline-topped block with an uppercase caption, like the panels of a lab notebook."""

    def __init__(self, caption: str, first: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("section")
        if first:
            self.setStyleSheet("QFrame#section { border-top: 0; }")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0 if first else 10, 0, 2)
        self.body.setSpacing(7)
        self.header = section_label(caption)
        self.body.addWidget(self.header)

    def set_caption(self, text: str):
        self.header.label.setText(text.upper())

    def add(self, w):
        self.body.addWidget(w)
        return w


class ModeList(QListWidget):
    """One row per mode: index, n_eff, polarization."""

    modeSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(theme.mono_font(11))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.currentRowChanged.connect(lambda i: i >= 0 and self.modeSelected.emit(i))

    def set_modes(self, modes):
        self.blockSignals(True)
        self.clear()
        for i, m in enumerate(modes or []):
            te = m.te_fraction
            pol = f"TE {te:4.0%}" if te >= 0.5 else f"TM {1 - te:4.0%}"
            loss = f"  {m.loss_db_per_cm:.3g} dB/cm" if m.loss_db_per_cm > 1e-6 else ""
            it = QListWidgetItem(f"{i:<3}{m.neff.real:.6f}   {pol}{loss}")
            self.addItem(it)
        self.setFixedHeight(max(1, self.count()) * 26 + 6)
        self.blockSignals(False)
        if self.count():
            self.setCurrentRow(0)


class Stat(QWidget):
    """label .......... value"""

    def __init__(self, label, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        name = QLabel(label)
        name.setObjectName("dim")
        self.value = QLabel("-")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(name)
        lay.addStretch()
        lay.addWidget(self.value)


class Bar(QWidget):
    """label [=====      ] value, for fractions."""

    def __init__(self, label, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        name = QLabel(label)
        name.setObjectName("dim")
        name.setFixedWidth(84)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {theme.HAIR2}; border: 0; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background: {theme.ACCENT_LINE}; border-radius: 2px; }}")
        self.value = QLabel("-")
        self.value.setFixedWidth(52)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(name)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.value)

    def set(self, frac: float):
        self.bar.setValue(int(round(1000 * max(0.0, min(1.0, frac)))))
        self.value.setText(f"{frac:.1%}")


class ModeReadout(QWidget):
    """Big n_eff, then the derived quantities for the selected mode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        row = QHBoxLayout()
        self.neff = QLabel("-")
        self.neff.setObjectName("bignum")
        self.neff.setFont(theme.mono_font(23, QFont.Weight.Medium))
        self.imag = QLabel("")
        self.imag.setObjectName("unit")
        row.addWidget(self.neff)
        row.addWidget(self.imag, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch()
        lay.addLayout(row)
        self.stats = {k: Stat(k) for k in ("group index", "loss", "effective area")}
        for s in self.stats.values():
            lay.addWidget(s)
        self.te = Bar("TE fraction")
        lay.addWidget(self.te)

    def show_mode(self, m):
        if m is None:
            self.neff.setText("-")
            self.imag.clear()
            for s in self.stats.values():
                s.value.setText("-")
            self.te.set(0)
            return
        self.neff.setText(f"{m.neff.real:.6f}")
        self.imag.setText(f"{m.neff.imag:+.2e}i" if abs(m.neff.imag) > 1e-12 else "n_eff")
        self.stats["group index"].value.setText(f"{m.group_index:.5f}")
        self.stats["loss"].value.setText(f"{m.loss_db_per_cm:.4g} dB/cm")
        self.stats["effective area"].value.setText(f"{m.effective_area:.4f} µm²")
        self.te.set(m.te_fraction)
