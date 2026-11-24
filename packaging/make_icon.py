"""Draw the app icon (src/gmode/gui/icon.png, 1024 px) in the GUI's colours: a guided mode's intensity
glowing around a waveguide core, on the dark stage.

    uv run --extra gui python packaging/make_icon.py

PyInstaller turns the PNG into .icns / .ico at build time (it needs Pillow for that).
"""
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QPainter, QPen, QRadialGradient, QTransform

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gmode.gui import theme  # noqa: E402

S = 1024


def draw() -> QImage:
    img = QImage(S, S, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # tile: the macOS grid leaves a margin around an 824 px rounded square
    m, r = 100, 185
    tile = QRectF(m, m, S - 2 * m, S - 2 * m)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.BG2))
    p.drawRoundedRect(tile, r, r)

    # mode intensity: an elliptical glow, wider than tall like a strip guide's TE0
    c = QPointF(S / 2, S / 2 + 20)
    g = QRadialGradient(QPointF(0, 0), 1.0)
    for t, col, a in ((0.0, "#e8fff6", 255), (0.18, "#9fe6cf", 240), (0.42, "#3fae94", 200),
                      (0.72, "#0f4a46", 120), (1.0, theme.BG2, 0)):
        q = QColor(col)
        q.setAlpha(a)
        g.setColorAt(t, q)
    p.save()
    p.setTransform(QTransform().translate(c.x(), c.y()).scale(330, 205))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(0, 0), 1.0, 1.0)
    p.restore()

    # the core, a hairline rectangle, and the substrate surface under it
    pen = QPen(QColor(theme.INK))
    pen.setWidthF(10)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    w, h = 300, 130
    p.drawRect(QRectF(c.x() - w / 2, c.y() - h / 2, w, h))
    sub = QPen(QColor(theme.ACCENT_INK))
    sub.setWidthF(6)
    sub.setStyle(Qt.PenStyle.DashLine)
    p.setPen(sub)
    p.drawLine(QPointF(m + 70, c.y() + h / 2 + 150), QPointF(S - m - 70, c.y() + h / 2 + 150))
    p.end()
    return img


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    out = Path(__file__).resolve().parents[1] / "src" / "gmode" / "gui" / "icon.png"
    draw().save(str(out))
    print("wrote", out)
