"""Properties panel controller — wires right-panel widgets to SceneState."""

from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QColorDialog, QMainWindow
from PyQt6.QtGui import QColor
from PyQt6.QtCore import QObject, QTimer

if TYPE_CHECKING:
    from manim_composer.models.scene_state import SceneState


class PropertiesController(QObject):
    """Wires the Properties panel widgets to the SceneState."""

    def __init__(self, window: QMainWindow, scene_state: SceneState):
        super().__init__(window)
        self.w = window
        self.state = scene_state
        self._current_name: str | None = None
        self._updating = False

        self._latex_timer = QTimer(self)
        self._latex_timer.setSingleShot(True)
        self._latex_timer.timeout.connect(self._apply_latex_change)

        self._connect_signals()

    def _connect_signals(self):
        self.w.canvas_scene.selectionChanged.connect(self._on_selection_changed)
        self.w.canvas_scene.changed.connect(self._on_scene_changed)

        self.w.editObjName.editingFinished.connect(self._on_name_edited)
        self.w.editLatexCode.textChanged.connect(self._on_latex_edited)
        self.w.btnTextColor.clicked.connect(self._on_color_btn_clicked)
        self.w.spinPosX.valueChanged.connect(self._on_position_changed)
        self.w.spinPosY.valueChanged.connect(self._on_position_changed)

    # --- Selection ---

    def _on_selection_changed(self):
        try:
            selected = self.w.canvas_scene.selectedItems()
        except RuntimeError:
            return  # scene already deleted during shutdown
        if len(selected) == 1:
            name = self.state.find_name_for_item(selected[0])
            if name:
                self._show_properties(name)
                return
        self._current_name = None
        self.w.propertiesStack.setCurrentIndex(0)

    def _show_properties(self, name: str):
        self._current_name = name
        tracked = self.state.get_tracked(name)
        item = self.state.get_item(name)
        if not tracked or not item:
            return

        self._updating = True
        self.w.propertiesStack.setCurrentIndex(1)  # propsTextPage
        self.w.editObjName.setText(name)
        self.w.editLatexCode.setPlainText(tracked.latex)
        self.w.btnTextColor.setText(tracked.color)
        self.w.btnTextColor.setStyleSheet(f"background-color: {tracked.color};")

        pos = item.pos()
        self.w.spinPosX.setValue(pos.x() / 100.0)
        self.w.spinPosY.setValue(-pos.y() / 100.0)
        self._updating = False

    # --- Property edits ---

    def _on_name_edited(self):
        if self._updating or not self._current_name:
            return
        new_name = self.w.editObjName.text().strip()
        if not new_name or new_name == self._current_name:
            return
        if new_name in self.state.object_names():
            self.w.editObjName.setText(self._current_name)
            return

        tracked = self.state.get_tracked(self._current_name)
        item = self.state.get_item(self._current_name)
        # Update animation references before unregister removes them
        for anim in self.state.all_animations():
            if anim.target_name == self._current_name:
                anim.target_name = new_name
        self.state.unregister(self._current_name)
        tracked.name = new_name
        self.state.register(new_name, tracked, item)
        self._current_name = new_name

    def _on_latex_edited(self):
        if self._updating or not self._current_name:
            return
        self._latex_timer.start(500)

    def _apply_latex_change(self):
        if not self._current_name:
            return
        tracked = self.state.get_tracked(self._current_name)
        item = self.state.get_item(self._current_name)
        if tracked and item:
            new_latex = self.w.editLatexCode.toPlainText()
            tracked.latex = new_latex
            item.set_latex(new_latex)

    def _on_color_btn_clicked(self):
        if not self._current_name:
            return
        tracked = self.state.get_tracked(self._current_name)
        item = self.state.get_item(self._current_name)
        if not tracked or not item:
            return
        color = QColorDialog.getColor(QColor(tracked.color), self.w, "Text Color")
        if color.isValid():
            hex_color = color.name()
            tracked.color = hex_color
            item.set_color(hex_color)
            self.w.btnTextColor.setText(hex_color)
            self.w.btnTextColor.setStyleSheet(f"background-color: {hex_color};")

    def _on_position_changed(self):
        if self._updating or not self._current_name:
            return
        item = self.state.get_item(self._current_name)
        if item:
            x = self.w.spinPosX.value() * 100.0
            y = -self.w.spinPosY.value() * 100.0
            item.setPos(x, y)

    # --- Drag sync ---

    def _on_scene_changed(self, _regions):
        if not self._current_name or self._updating:
            return
        try:
            item = self.state.get_item(self._current_name)
            if item:
                self._updating = True
                pos = item.pos()
                self.w.spinPosX.setValue(pos.x() / 100.0)
                self.w.spinPosY.setValue(-pos.y() / 100.0)
                self._updating = False
        except RuntimeError:
            return
