"""Visual theme: a dark lab look with hairline panels, one green accent,
STIX Two Text for titles and Spline Sans Mono for everything else.
"""
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

BG = "#070908"  # stage and plots
BG2 = "#0b0f0d"  # panels
BG3 = "#121a16"  # raised: selected rows, active segments, buttons
INK = "#e6ece8"
DIM = "#97a8a0"
FAINT = "#5a6a63"
HAIR = "rgba(230, 236, 232, 0.12)"
HAIR2 = "rgba(230, 236, 232, 0.06)"
ACCENT = "#00643c"  # filled: primary button, active toggles
ACCENT_INK = "#7fd1b0"  # accent text and lines on dark
ACCENT_LINE = "#2f8f6e"
WARN = "#ffb36b"
BAD = "#ff6b6b"
GOOD = "#7ee0a0"

MONO = "Spline Sans Mono"
SERIF = "STIX Two Text"
_MONO_FALLBACK = ["SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "monospace"]
_SERIF_FALLBACK = ["Times New Roman", "Georgia", "serif"]

# shape outline colours, readable on the dark stage
PALETTE = ["#7fd1b0", "#ffb36b", "#8fd8ff", "#ff8a73", "#c3a6ff", "#f2c84b", "#6fb2ff", "#e88fc4", "#c6cfdb"]


def hair_qcolor(alpha=0.12) -> QColor:
    c = QColor(INK)
    c.setAlphaF(alpha)
    return c


def field_colormap() -> pg.ColorMap:
    """Signed fields: light blue, through near-black, to warm orange."""
    return pg.ColorMap([0.0, 0.22, 0.5, 0.78, 1.0],
                       ["#d8eaff", "#3f7fd6", BG, "#d9714a", "#ffe2cc"])


def magnitude_colormap() -> pg.ColorMap:
    """Magnitudes: near-black through teal to pale mint."""
    return pg.ColorMap([0.0, 0.35, 0.7, 1.0], ["#070908", "#0f4a46", "#3fae94", "#e8fff6"])


def index_colormap() -> pg.ColorMap:
    """Refractive index on the geometry stage: low index stays just above the stage colour."""
    return pg.ColorMap([0.0, 1.0], ["#121a17", "#9fb3aa"])


def _load_fonts():
    folder = Path(__file__).parent / "fonts"
    families = set()
    for f in folder.glob("*.ttf"):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            families.update(QFontDatabase.applicationFontFamilies(fid))
    return families


def mono_font(size: float = 11.5, weight=QFont.Weight.Normal) -> QFont:
    f = QFont(MONO)
    f.setFamilies([MONO, *_MONO_FALLBACK])
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def serif_font(size: float = 17, weight=QFont.Weight.Medium) -> QFont:
    f = QFont(SERIF)
    f.setFamilies([SERIF, *_SERIF_FALLBACK])
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


STYLESHEET = f"""
* {{ outline: 0; }}
QWidget {{ background: {BG2}; color: {INK}; font-family: "{MONO}"; font-size: 11.5px; }}
QMainWindow, QSplitter {{ background: {BG2}; }}
QSplitter::handle {{ background: {HAIR}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QWidget#stage, QWidget#stage QWidget#stagebar {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-family: "{SERIF}"; font-size: 22px; font-weight: 500; color: {INK}; }}
QLabel#subtitle, QLabel#hint, QLabel#status {{ color: {FAINT}; font-size: 10.5px; }}
QLabel#seclabel {{ color: {FAINT}; font-size: 9.5px; }}
QLabel#objtitle {{ font-family: "{SERIF}"; font-size: 17px; font-weight: 500; }}
QLabel#bignum {{ font-size: 30px; font-weight: 500; }}
QLabel#unit, QLabel#dim {{ color: {DIM}; }}
QLabel#error {{ color: {BAD}; font-size: 10.5px; }}
QLabel#stale {{ color: {WARN}; font-size: 10.5px; }}
QLabel#info {{ color: {FAINT}; font-size: 10.5px; }}
QFrame#section {{ border: 0; border-top: 1px solid {HAIR}; background: transparent; }}
QFrame#section QWidget {{ background: transparent; }}

QPushButton {{ background: {BG3}; border: 1px solid {HAIR}; border-radius: 6px; padding: 5px 10px; color: {INK}; }}
QPushButton:hover {{ border-color: rgba(230, 236, 232, 0.3); }}
QPushButton:pressed {{ background: {HAIR2}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {HAIR2}; }}
QPushButton#primary {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: {INK}; font-size: 15px;
    font-weight: 600; padding: 14px 14px; text-align: left; }}
QPushButton#primary:hover {{ background: #00764a; }}
QPushButton#primary[running="true"] {{ background: {BG3}; color: {ACCENT_INK}; border-color: {ACCENT_LINE}; }}
QFrame#seg {{ border: 1px solid {HAIR}; border-radius: 6px; background: transparent; }}
QFrame#seg QPushButton {{ background: transparent; border: 0; border-radius: 0; border-right: 1px solid {HAIR};
    padding: 5px 9px; color: {DIM}; }}
QFrame#seg QPushButton[last="true"] {{ border-right: 0; }}
QFrame#seg QPushButton:hover {{ color: {INK}; background: {HAIR2}; }}
QFrame#seg QPushButton:checked {{ color: {ACCENT_INK}; background: {BG3}; border-bottom: 2px solid {ACCENT_LINE}; }}
QPushButton#toggle:checked {{ color: {ACCENT_INK}; border-color: {ACCENT_LINE}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {BG}; border: 1px solid {HAIR}; border-radius: 4px;
    padding: 3px 6px; selection-background-color: {ACCENT}; min-height: 18px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {ACCENT_LINE}; }}
QComboBox::drop-down {{ border: 0; width: 16px; }}
QComboBox QAbstractItemView {{ background: {BG3}; border: 1px solid {HAIR}; selection-background-color: {ACCENT}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: 0; }}
QCheckBox {{ background: transparent; color: {DIM}; }}

QTreeWidget, QListWidget, QTableWidget, QPlainTextEdit {{ background: transparent; border: 0; }}
QTreeWidget::item, QListWidget::item {{ padding: 3px 4px; border: 1px solid transparent; border-radius: 5px; color: {DIM}; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {HAIR2}; color: {INK}; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {BG3}; border-color: {HAIR}; color: {INK}; }}
QTreeWidget {{ show-decoration-selected: 0; }}
QTreeWidget::branch, QTreeWidget::branch:selected, QTreeWidget::branch:hover {{ background: transparent; }}
QTableWidget {{ gridline-color: {HAIR2}; }}
QTableWidget::item:selected {{ background: {BG3}; color: {INK}; }}
QHeaderView::section {{ background: {BG2}; color: {FAINT}; border: 0; border-bottom: 1px solid {HAIR}; padding: 4px; font-size: 10px; }}
QPlainTextEdit {{ color: {DIM}; font-size: 10.5px; }}

QScrollArea {{ border: 0; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {HAIR}; border-radius: 3px; min-height: 24px; }}
QScrollBar:horizontal {{ background: transparent; height: 6px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {HAIR}; border-radius: 3px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; width: 0; height: 0; }}

QMenuBar {{ background: {BG2}; border-bottom: 1px solid {HAIR}; }}
QMenuBar::item:selected {{ background: {BG3}; }}
QMenu {{ background: {BG3}; border: 1px solid {HAIR}; padding: 4px; }}
QMenu::item {{ padding: 4px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QMenu::separator {{ height: 1px; background: {HAIR}; margin: 4px 6px; }}
QToolTip {{ background: {BG3}; color: {INK}; border: 1px solid {HAIR}; padding: 4px 6px; }}
QDialog {{ background: {BG2}; }}
QStatusBar {{ background: {BG2}; color: {FAINT}; border-top: 1px solid {HAIR}; }}
QDockWidget {{ color: {DIM}; }}
QDockWidget::title {{ background: {BG2}; padding: 4px 8px; border-bottom: 1px solid {HAIR}; }}
QMessageBox {{ background: {BG2}; }}
"""


def style_plot(widget: pg.PlotWidget):
    """Plot chrome to match: stage background, faint axes, mono tick labels."""
    widget.setBackground(BG)
    item = widget.getPlotItem()
    font = mono_font(9)
    for name in ("left", "bottom"):
        ax = item.getAxis(name)
        ax.setPen(pg.mkPen(hair_qcolor(0.18)))
        ax.setTextPen(pg.mkPen(FAINT))
        ax.setStyle(tickFont=font, tickLength=-4)
        ax.label.setFont(font)
    for name in ("top", "right"):
        item.showAxis(name, False)


def apply(app: QApplication):
    """Install fonts, palette, stylesheet and pyqtgraph defaults on the application."""
    _load_fonts()
    app.setStyle("Fusion")
    app.setFont(mono_font())
    pal = QPalette()
    for role, color in ((QPalette.ColorRole.Window, BG2), (QPalette.ColorRole.Base, BG),
                        (QPalette.ColorRole.AlternateBase, BG3), (QPalette.ColorRole.Text, INK),
                        (QPalette.ColorRole.WindowText, INK), (QPalette.ColorRole.Button, BG3),
                        (QPalette.ColorRole.ButtonText, INK), (QPalette.ColorRole.Highlight, ACCENT),
                        (QPalette.ColorRole.HighlightedText, INK), (QPalette.ColorRole.ToolTipBase, BG3),
                        (QPalette.ColorRole.ToolTipText, INK), (QPalette.ColorRole.PlaceholderText, FAINT)):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
    pg.setConfigOptions(antialias=True, background=BG, foreground=DIM)
