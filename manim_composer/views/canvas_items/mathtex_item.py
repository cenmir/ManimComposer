"""MathTex canvas item — renders LaTeX formulas on the QGraphicsScene."""

import os
import subprocess
import tempfile

from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsItem
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont, QFontMetrics
from PyQt6.QtCore import Qt

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _hex_to_dvipng_fg(color_hex: str) -> str:
    """Convert '#RRGGBB' to dvipng fg spec like 'rgb 1.000 1.000 1.000'."""
    c = QColor(color_hex)
    return f"rgb {c.redF():.3f} {c.greenF():.3f} {c.blueF():.3f}"


def render_latex(latex: str, color: str = "#FFFFFF", dpi: int = 300) -> QPixmap | None:
    """Render LaTeX to a transparent QPixmap via latex + dvipng.

    Returns None if the LaTeX toolchain is unavailable or compilation fails.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tex = os.path.join(tmp, "f.tex")
        dvi = os.path.join(tmp, "f.dvi")
        png = os.path.join(tmp, "f1.png")

        with open(tex, "w") as fh:
            fh.write(
                "\\documentclass[preview,border=2pt]{standalone}\n"
                "\\usepackage{amsmath,amssymb}\n"
                "\\begin{document}\n"
                f"\\fontsize{{28}}{{34}}\\selectfont ${latex}$\n"
                "\\end{document}\n"
            )

        try:
            subprocess.run(
                ["latex", "-interaction=nonstopmode",
                 f"-output-directory={tmp}", tex],
                capture_output=True, timeout=30,
                creationflags=_CREATE_NO_WINDOW,
            )
            if not os.path.isfile(dvi):
                return None

            subprocess.run(
                ["dvipng", "-D", str(dpi), "-T", "tight",
                 "-bg", "Transparent",
                 "-fg", _hex_to_dvipng_fg(color),
                 "-o", png, dvi],
                capture_output=True, timeout=15,
                creationflags=_CREATE_NO_WINDOW,
            )
            if os.path.isfile(png):
                return QPixmap(png)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
    return None


def render_fallback(latex: str, color: str = "#FFFFFF", size: int = 36) -> QPixmap:
    """Render LaTeX source as styled text (fallback when LaTeX is not installed)."""
    font = QFont("Cambria Math", size)
    font.setItalic(True)
    metrics = QFontMetrics(font)
    text = f" {latex} "
    rect = metrics.boundingRect(text)
    pad = 8
    pixmap = QPixmap(rect.width() + pad * 2, rect.height() + pad * 2)
    pixmap.fill(Qt.GlobalColor.transparent)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(pad - rect.x(), pad - rect.y(), text)
    p.end()
    return pixmap


class MathTexItem(QGraphicsPixmapItem):
    """Displays a rendered LaTeX formula on the canvas."""

    _latex_available = None  # None = untested, True/False after first attempt

    def __init__(self, latex: str = "F=ma", color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self.latex = latex
        self.color = color

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self._do_render()

    def set_latex(self, latex: str):
        self.latex = latex
        self._do_render()

    def set_color(self, color: str):
        self.color = color
        self._do_render()

    def _do_render(self):
        pm = None
        if MathTexItem._latex_available is not False:
            pm = render_latex(self.latex, self.color)
            MathTexItem._latex_available = pm is not None
        if pm is None:
            pm = render_fallback(self.latex, self.color)
        self.setPixmap(pm)
        self.setOffset(-pm.width() / 2, -pm.height() / 2)
