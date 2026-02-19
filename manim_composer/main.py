"""Manim Composer — Entry point."""

import sys
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QButtonGroup, QGraphicsScene,
    QAbstractItemView, QGraphicsView, QListView,
)
from PyQt6.QtGui import QBrush, QColor, QPainter
from PyQt6.QtCore import Qt, QEvent
from PyQt6 import uic

from manim_composer.views.canvas_items.mathtex_item import MathTexItem


class ManimComposerWindow(QMainWindow):
    """Main application window, loaded from the .ui file."""

    def __init__(self):
        super().__init__()

        # Load the .ui file
        ui_path = os.path.join(os.path.dirname(__file__), "main_window.ui")
        uic.loadUi(ui_path, self)

        self._fix_widget_enums()
        self._setup_toolbar_tabs()
        self._setup_center_tabs()
        self._setup_tool_button_group()
        self._setup_canvas()
        self._setup_default_proportions()

    def _fix_widget_enums(self):
        """Set widget properties that use scoped enums (avoids uic XML warnings)."""
        self.canvasView.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.canvasView.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.scenesList.setViewMode(QListView.ViewMode.ListMode)
        self.scenesList.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.animationsList.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def _setup_toolbar_tabs(self):
        """Wire the toolbar selector QTabBar to the toolbar QStackedWidget."""
        self.toolbarSelector.addTab("Design")
        self.toolbarSelector.addTab("Animation")
        self.toolbarSelector.currentChanged.connect(self.toolbarStack.setCurrentIndex)

    def _setup_center_tabs(self):
        """Wire the center tab bar to switch between Canvas and Code views."""
        self.centerTabBar.addTab("Canvas")
        self.centerTabBar.addTab("Code")
        self.centerTabBar.currentChanged.connect(self.centerStack.setCurrentIndex)

    def _setup_tool_button_group(self):
        """Make design tool buttons mutually exclusive."""
        self.toolGroup = QButtonGroup(self)
        self.toolGroup.setExclusive(True)
        for btn in (
            self.toolSelect,
            self.toolMathTex,
            self.toolText,
            self.toolCircle,
            self.toolRectangle,
            self.toolArrow,
            self.toolLine,
        ):
            self.toolGroup.addButton(btn)

    def _setup_default_proportions(self):
        """Set the default splitter sizes to match the intended layout."""
        self.leftPanelSplitter.setMaximumWidth(350)
        # ~10% left, ~80% center canvas, ~10% right properties
        self.mainSplitter.setSizes([190, 1660, 190])
        self.mainSplitter.setStretchFactor(0, 0)  # left: fixed
        self.mainSplitter.setStretchFactor(1, 1)  # center: stretches
        self.mainSplitter.setStretchFactor(2, 0)  # right: fixed

    def _setup_canvas(self):
        """Initialize the QGraphicsScene with black background and a default MathTex."""
        self.canvas_scene = QGraphicsScene(self)
        self.canvas_scene.setSceneRect(-700, -400, 1400, 800)
        self.canvas_scene.setBackgroundBrush(QBrush(QColor("#000000")))
        self.canvasView.setScene(self.canvas_scene)

        # Place default F=ma at the center
        self.statusBar.showMessage("Rendering LaTeX…")
        QApplication.processEvents()
        default_item = MathTexItem(latex="F=ma", color="#FFFFFF")
        self.canvas_scene.addItem(default_item)
        default_item.setPos(0, 0)

        if MathTexItem._latex_available:
            self.statusBar.showMessage("LaTeX rendered successfully", 3000)
        else:
            self.statusBar.showMessage(
                "LaTeX not found — using text fallback (install MiKTeX/TeX Live for full rendering)",
                5000,
            )

        # Listen for tool-click placement on the canvas
        self.canvasView.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        """Handle mouse clicks on the canvas for placing new objects."""
        if obj is self.canvasView.viewport():
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                active = self.toolGroup.checkedButton()
                if active is self.toolMathTex:
                    pos = self.canvasView.mapToScene(event.pos())
                    item = MathTexItem(latex="F=ma", color="#FFFFFF")
                    self.canvas_scene.addItem(item)
                    item.setPos(pos.x(), pos.y())
                    # Switch back to Select after placing
                    self.toolSelect.setChecked(True)
                    return True
        return super().eventFilter(obj, event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Manim Composer")

    window = ManimComposerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
